"""Minimal live-run script that wires your agent to the Kraken client.

This script is intentionally minimal and defaults to DRY_RUN=true. Replace
the state construction (`make_state_from_ticker`) to match the inputs your
agent expects (same features/shape used during training).

Usage: set environment variables (see `.env.example`) then run:
    python run_live.py
"""
import os
import time
import logging
from typing import Any

import numpy as np
import torch

from config import EnvironmentConfig
from exchanges.exchange_factory import get_exchange_client
from exchanges.position_manager import PositionManager, PositionLimits
from integrations.tradingview_adapter import PriceBuffer, VolumeBuffer, combine_indicators_to_action
from agent import MetaSACAgent
from env.environment import HistoricalEnvironment
import joblib
from integrations.indicators_tv import auto_fib_levels, watchtower_signal, believe_it_meter, livermore_3_points
from models.feature_builder import build_feature_from_window

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s:%(message)s')


def make_state_from_ticker(ticker: dict, price_window: list | None, config: EnvironmentConfig) -> Any:
    """Build a placeholder state for the agent from a ticker.

    IMPORTANT: Replace this with the same feature pipeline used during
    training/backtests. The agent expects a np.ndarray of shape
    (sequence_length, state_dim) or similar. Here we build a simple
    zero-filled window with the last price in the close column as one
    feature to allow the demo to run.
    """
    last_price = float(ticker.get('last', 0.0) or 0.0)
    state = np.zeros((config.window_size, config.state_dim), dtype=np.float32)
    # If we have a price window, use the shared feature builder to populate the
    # first columns (matching training-time features). Otherwise fall back to
    # a simple price-filled column to keep the agent happy.
    if price_window and len(price_window) >= config.window_size:
        try:
            feat = build_feature_from_window(price_window[-config.window_size:])
            # place feature vector in first columns of the last row
            nfeat = min(len(feat), config.state_dim)
            state[-1, :nfeat] = feat[:nfeat]
        except Exception:
            state[:, 0] = last_price
    else:
        state[:, 0] = last_price
    return state


def main():
    SYMBOL = os.getenv('SYMBOL', 'XBT/USD')  # change to your preferred symbol
    MAX_ORDER_USD = float(os.getenv('MAX_ORDER_USD', '10'))
    DRY_RUN = bool(str(os.getenv('DRY_RUN', 'true')).lower() in ('1', 'true', 'yes'))

    # init client via factory (select exchange via EXCHANGE env var, default 'kraken')
    EXCHANGE_ID = os.getenv('EXCHANGE', 'kraken')
    MARKET_TYPE = os.getenv('MARKET_TYPE', 'spot')
    kraken = get_exchange_client(
        EXCHANGE_ID,
        api_key=os.getenv('EXCHANGE_API_KEY') or os.getenv('KRAKEN_API_KEY'),
        api_secret=os.getenv('EXCHANGE_API_SECRET') or os.getenv('KRAKEN_API_SECRET'),
        api_passphrase=os.getenv('EXCHANGE_API_PASSPHRASE') or os.getenv('KRAKEN_API_PASSPHRASE'),
        testnet=False,
        dry_run=DRY_RUN,
    )
    # attempt to resolve the symbol name to one accepted by Kraken/ccxt
    def resolve_symbol(desired: str) -> str:
        # try exact first
        markets = getattr(kraken, 'markets', {}) or {}
        if desired in markets:
            return desired
        # try common replacements
        variants = []
        if '/' in desired:
            base, quote = desired.split('/')
            variants.extend([f"{base}/{quote}", f"{base}{quote}", f"{base}/{quote}".replace('XBT', 'BTC'), f"{base}/{quote}".replace('BTC', 'XBT')])
        else:
            variants.extend([desired, desired.replace('XBT', 'BTC'), desired.replace('BTC', 'XBT')])
        # also try swapping separator
        for v in variants:
            if v in markets:
                return v
        # fallback: pick first USD pair available for BTC/XBT
        for k in markets.keys():
            if ('BTC' in k or 'XBT' in k) and ('USD' in k or 'USDT' in k):
                return k
        # last resort return original
        return desired

    RESOLVED_SYMBOL = resolve_symbol(SYMBOL)
    if RESOLVED_SYMBOL != SYMBOL:
        logger.info(f"Resolved symbol {SYMBOL} -> {RESOLVED_SYMBOL} for Kraken client")
    # init a simple position manager with conservative default limits
    pm_limits = PositionLimits(
        max_notional_usd=float(os.getenv('MAX_ACCOUNT_NOTIONAL_USD', '1000')),
        min_order_usd=float(os.getenv('MIN_ORDER_USD', '1.0')),
        cooldown_seconds=float(os.getenv('PM_COOLDOWN_SECONDS', '5.0')),
        stop_loss_pct=(float(os.getenv('PM_STOP_LOSS_PCT')) if os.getenv('PM_STOP_LOSS_PCT') else None),
        take_profit_pct=(float(os.getenv('PM_TAKE_PROFIT_PCT')) if os.getenv('PM_TAKE_PROFIT_PCT') else None),
    )
    posman = PositionManager(pm_limits)

    # load agent (model weights optional)
    cfg = EnvironmentConfig()
    # create a tiny HistoricalEnvironment for the agent constructor to satisfy
    # the typed signature; this is lightweight and won't be used for real runs
    import numpy as _np
    dummy_hist = HistoricalEnvironment(_np.zeros((cfg.window_size + 2, cfg.state_dim)))
    agent = MetaSACAgent(cfg, env=dummy_hist)
    model_path = os.getenv('MODEL_PATH')
    if model_path:
        try:
            agent.load_state_dict(torch.load(model_path, map_location=cfg.device))
            logger.info(f"Loaded agent state from {model_path}")
        except Exception as e:
            logger.warning(f"Failed to load model from {model_path}: {e}")

    # load 1-min predictor model if present
    model_1min_path = os.getenv('MODEL_1MIN_PATH', 'models/lgbm_1min.pkl')
    model_1min = None
    if os.path.exists(model_1min_path):
        try:
            model_1min = joblib.load(model_1min_path)
            logger.info(f"Loaded 1-min model from {model_1min_path}")
        except Exception as e:
            logger.warning(f"Failed to load 1-min model: {e}")

    logger.info(f"Starting live loop for {SYMBOL} (DRY_RUN={DRY_RUN})")
    time_step = 0
    # small price/volume buffers used by the TradingView adapter
    price_buffer = PriceBuffer(size=int(os.getenv('TV_WINDOW', '20')))
    volume_buffer = VolumeBuffer(size=int(os.getenv('TV_WINDOW', '20')))

    # optional run steps (for testing/dry-run): if set, loop will stop after N steps
    max_steps = int(os.getenv('RUN_STEPS', '0'))
    try:
        while True:
            try:
                ticker = kraken.fetch_ticker(RESOLVED_SYMBOL)
            except Exception as e:
                logger.error(f"Failed to fetch ticker {SYMBOL}: {e}")
                time.sleep(1.0)
                continue

            state = make_state_from_ticker(ticker, price_buffer.to_list(), cfg)
            # update price buffer
            last_price = float(ticker.get('last', 0.0) or 0.0)
            last_vol = float(ticker.get('volume', 0.0) or 0.0)
            price_buffer.add(last_price)
            volume_buffer.add(last_vol)

            # derive model action if model loaded
            model_action = 0.0
            if model_1min is not None and len(price_buffer.to_list()) >= cfg.window_size:
                window_closes = price_buffer.to_list()[-cfg.window_size:]
                try:
                    feat = build_feature_from_window(window_closes)
                    Xf = feat.reshape(1, -1)
                    # model confidence gating
                    model_min_conf = float(os.getenv('MODEL_MIN_CONF', '0.6'))
                    prob = model_1min.predict_proba(Xf)[0][1]
                    if prob >= model_min_conf or prob <= (1.0 - model_min_conf):
                        model_action = float((prob - 0.5) * 2.0)
                    else:
                        model_action = 0.0
                except Exception as e:
                    logger.warning(f"Model inference failed: {e}")
                    model_action = 0.0

            # create dummy graph inputs required by agent.select_action
            edge_index = torch.tensor([[0], [0]], dtype=torch.long)
            graph_node_features = torch.zeros((1, cfg.graph_input_dim), dtype=torch.float32)

            action = agent.select_action(state, time_step=time_step, edge_index=edge_index, graph_node_features=graph_node_features, eval=True)

            # agent.select_action may return a scalar or vector depending on actor
            a_value = float(np.asarray(action).squeeze().item()) if hasattr(action, 'squeeze') or isinstance(action, (list, tuple, np.ndarray)) else float(action)

            # Get TradingView-derived signal and convert to an action
            # derive TV action via ported indicators combiner
            tv_action = combine_indicators_to_action(price_buffer.to_list(), volume_buffer.to_list())
            # textual TV signal for logging
            if tv_action > 0.05:
                tv_signal = 'buy'
            elif tv_action < -0.05:
                tv_signal = 'sell'
            else:
                tv_signal = 'none'

            # safety deadband
            deadband = float(os.getenv('DEADBAND', '0.02'))
            # combination weights (overridable by environment)
            w_agent = float(os.getenv('WEIGHT_AGENT', '0.6'))
            w_model = float(os.getenv('WEIGHT_MODEL', '0.2'))
            w_tv = float(os.getenv('WEIGHT_TV', '0.2'))
            total_w = max(1e-6, (w_agent + w_model + w_tv))
            w_agent /= total_w
            w_model /= total_w
            w_tv /= total_w

            combined_action = float(max(min(w_agent * a_value + w_model * model_action + w_tv * tv_action, 1.0), -1.0))

            if abs(combined_action) < deadband:
                logger.info(f"Combined action {combined_action:.4f} within deadband {deadband}; no trade (agent={a_value:.4f}, tv={tv_action:.4f}, signal={tv_signal})")
            else:
                order_info = kraken.action_to_order(combined_action, RESOLVED_SYMBOL, max_order_usd=MAX_ORDER_USD)
                if order_info.get('side') is None or order_info.get('amount', 0) <= 0:
                    logger.info(f"No order created from combined action {combined_action}")
                else:
                    logger.info(f"Placing order (pre-checks): {order_info} (agent={a_value:.4f}, tv={tv_action:.4f}, signal={tv_signal})")
                    # Safety: check cooldown and position manager limits
                    if not posman.can_trade():
                        logger.warning("Trade cooldown active; skipping new order")
                    elif posman.would_exceed_limits(order_info['side'], order_info['amount'], order_info['price']):
                        logger.warning("Order would exceed configured position limits; skipping")
                    else:
                        resp = kraken.create_market_order(SYMBOL, order_info['side'], order_info['amount'])
                        logger.info(f"Order response: {resp}")
                        # In dry-run mode, record_trade is optional; here we record for simulation
                        if DRY_RUN:
                            posman.record_trade(order_info['side'], order_info['amount'], order_info['price'])
                            logger.info(f"Simulated position: {posman.current_position()}")

                # Check stop-loss / take-profit: if configured and triggered, close position
                try:
                    should_close, close_side, close_amount = posman.should_close_for_sl_tp(last_price)
                    if should_close:
                        logger.info(f"SL/TP triggered: closing position {close_side} {close_amount} at {last_price}")
                        if posman.can_trade():
                            resp = kraken.create_market_order(SYMBOL, close_side, close_amount)
                            logger.info(f"SL/TP close order response: {resp}")
                            if DRY_RUN:
                                posman.record_trade(close_side, close_amount, last_price)
                                logger.info(f"Simulated position after SL/TP close: {posman.current_position()}")
                        else:
                            logger.warning("SL/TP close suppressed due to cooldown")
                except Exception as e:
                    logger.warning(f"Failed to evaluate/execute SL/TP close: {e}")

            time_step += 1
            if max_steps and time_step >= max_steps:
                logger.info(f"Reached max steps {max_steps}; exiting live loop")
                break
            time.sleep(float(os.getenv('POLL_INTERVAL', '1.0')))

    except KeyboardInterrupt:
        logger.info("Live loop stopped by user")


if __name__ == '__main__':
    main()
