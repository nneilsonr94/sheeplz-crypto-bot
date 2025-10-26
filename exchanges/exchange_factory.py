"""Generic exchange factory to instantiate ccxt-based exchange clients.

This lets `run_live` select the exchange at runtime via the EXCHANGE env var
without hardcoding Kraken. It returns an object with the same surface used
elsewhere (fetch_ticker, create_market_order, action_to_order, markets).
"""
from __future__ import annotations
import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_exchange_client(exchange_id: str | None = None, api_key: Optional[str] = None,
                        api_secret: Optional[str] = None, api_passphrase: Optional[str] = None,
                        testnet: bool = False, dry_run: bool = True, rate_limit_sleep: float = 0.2) -> Any:
    exchange_id = exchange_id or os.getenv('EXCHANGE', 'kraken')
    # support common aliases (e.g., 'coinbase_advanced' -> 'coinbasepro')
    alias_map = {
        'coinbase_advanced': 'coinbasepro',
        'coinbase-advanced': 'coinbasepro',
        'coinbaseadvanced': 'coinbasepro',
        'coinbase_advanced_trade': 'coinbasepro',
        'coinbase': 'coinbasepro',
    }
    exchange_id_normalized = alias_map.get(exchange_id.lower(), exchange_id)
    if exchange_id_normalized != exchange_id:
        logger.info(f"Mapping exchange alias {exchange_id} -> {exchange_id_normalized}")
    exchange_id = exchange_id_normalized

    # Special-case the official Coinbase Advanced package if requested: try to
    # instantiate coinbase.rest.RESTClient directly for a tighter integration.
    if exchange_id.lower() in ('coinbase', 'coinbasepro', 'coinbase_advanced', 'coinbase-advanced', 'coinbaseadvanced'):
        try:
            import coinbase.rest as _coinbase_rest
            # instantiate with provided keys (None is acceptable for read-only/dry-run)
            client = _coinbase_rest.RESTClient(api_key=api_key, api_secret=api_secret)
            # minimal wrapper to match run_live expectations
            class _CBWrapper:
                def __init__(self, c):
                    self._c = c
                    self.markets = getattr(c, 'markets', {})

                def fetch_ticker(self, symbol: str):
                    # coinbase RESTClient has market data endpoints under market_data
                    try:
                        # try to use products/market_data
                        p = getattr(self._c, 'market_data', None)
                        if p and hasattr(p, 'get_ticker'):
                            return p.get_ticker(symbol)
                    except Exception:
                        pass
                    # fallback to a generic call
                    return {'last': '0', 'volume': '0'}

                def create_market_order(self, symbol: str, side: str, amount: float, params: dict | None = None):
                    # try common client order methods
                    try:
                        orders = getattr(self._c, 'orders', None)
                        if orders and hasattr(orders, 'create'):
                            return orders.create(product_id=symbol, side=side, size=amount, type='market')
                    except Exception:
                        pass
                    return {'info': {'dry_run': True}, 'symbol': symbol, 'side': side, 'amount': amount}

                def action_to_order(self, action: float, symbol: str, max_order_usd: float = 100.0, price: float | None = None):
                    if abs(action) < 1e-9:
                        return {'side': None, 'amount': 0.0, 'price': price, 'usd_notional': 0.0}
                    side = 'buy' if action > 0 else 'sell'
                    usd = min(abs(action), 1.0) * float(max_order_usd)
                    if price is None:
                        t = self.fetch_ticker(symbol)
                        price = float(t.get('last') or 0.0)
                    amount = usd / float(price) if price else 0.0
                    return {'side': side, 'amount': amount, 'price': price, 'usd_notional': usd}

            logger.info('Using coinbase.rest.RESTClient for exchange client')
            return _CBWrapper(client)
        except Exception as e:
            logger.warning(f'Could not instantiate coinbase REST client directly: {e}; falling back to generic factory')
    # allow explicitly specifying a third-party exchange client module via
    # EXCHANGE_CLIENT_MODULE, e.g. if you've installed a library for Coinbase
    # Advanced Trade. If provided, we'll import it and call a factory function
    # named `get_client` or `create_client` with (api_key, api_secret, api_passphrase, dry_run).
    client_module_name = os.getenv('EXCHANGE_CLIENT_MODULE')
    if client_module_name:
        try:
            import importlib
            m = importlib.import_module(client_module_name)
            factory = getattr(m, 'get_client', None) or getattr(m, 'create_client', None)
            if factory:
                return factory(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase, dry_run=dry_run)
            else:
                logger.warning(f"Module {client_module_name} has no get_client/create_client factory; falling back to ccxt path")
        except Exception as e:
            logger.warning(f"Failed to import EXCHANGE_CLIENT_MODULE '{client_module_name}': {e}; falling back to ccxt/stub")

    try:
        import ccxt
        exchange_cls = getattr(ccxt, exchange_id)
        params = {"enableRateLimit": True}
        if api_key and api_secret:
            params.update({"apiKey": api_key, "secret": api_secret})
        client = exchange_cls(params)

        # switch to testnet urls if requested (best-effort)
        if testnet:
            try:
                client.urls['api'] = client.urls.get('test', client.urls.get('api'))
            except Exception:
                logger.warning('Could not set testnet urls for exchange %s', exchange_id)

        # load markets
        try:
            markets = client.load_markets()
        except Exception:
            markets = {}

    # wrap minimal surface expected by run_live (keep create_market_order and action_to_order semantics)
        class _ClientWrapper:
            def __init__(self, client, markets, dry_run, rate_limit_sleep):
                self.client = client
                self.markets = markets
                self.dry_run = dry_run
                self.rate_limit_sleep = rate_limit_sleep

            def fetch_ticker(self, symbol: str):
                return self.client.fetch_ticker(symbol)

            def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[dict] = None):
                if self.dry_run:
                    logger.info(f"DRY RUN ORDER ({exchange_id}): {side} {amount} {symbol}")
                    return {"info": {"dry_run": True}, "symbol": symbol, "side": side, "amount": amount}
                return self.client.create_order(symbol, 'market', side, amount, None, params or {})

            def action_to_order(self, action: float, symbol: str, max_order_usd: float = 100.0, price: Optional[float] = None):
                # Similar conversion as KrakenClient.action_to_order
                if abs(action) < 1e-6:
                    return {"side": None, "amount": 0.0, "price": price, "usd_notional": 0.0}
                side = 'buy' if action > 0 else 'sell'
                magnitude = min(abs(action), 1.0)
                usd = magnitude * float(max_order_usd)
                if price is None:
                    ticker = self.fetch_ticker(symbol)
                    price = float(ticker.get('last') or ticker.get('close') or ticker.get('info', {}).get('price'))
                amount = usd / float(price)
                market = self.markets.get(symbol)
                if market:
                    precision = market.get('precision', {})
                    base_prec = precision.get('amount')
                    if base_prec is not None:
                        try:
                            base_prec_int = int(base_prec)
                        except Exception:
                            base_prec_int = 8
                        amount = float(round(amount, base_prec_int))
                return {"side": side, "amount": amount, "price": price, "usd_notional": usd}

        return _ClientWrapper(client, markets, dry_run, rate_limit_sleep)
    except Exception as e:
        logger.warning(f"Failed to create ccxt client for {exchange_id}: {e}")
        # fallback stub that simulates a client for dry-run testing
        class _Stub:
            def __init__(self):
                self.markets = {'BTC/USD': {'precision': {'amount': 8}}, 'BTC/USDT': {'precision': {'amount': 8}}}

            def fetch_ticker(self, symbol: str):
                import random
                return {'last': str(100 + (random.random() - 0.5)), 'volume': '1'}

            def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[dict] = None):
                return {'info': {'dry_run': True}, 'symbol': symbol, 'side': side, 'amount': amount}

            def action_to_order(self, action: float, symbol: str, max_order_usd: float = 100.0, price: Optional[float] = None):
                if abs(action) < 1e-6:
                    return {"side": None, "amount": 0.0, "price": price, "usd_notional": 0.0}
                side = 'buy' if action > 0 else 'sell'
                price = float(self.fetch_ticker(symbol)['last'])
                amount = max_order_usd / price
                return {"side": side, "amount": amount, "price": price, 'usd_notional': max_order_usd}

        return _Stub()
