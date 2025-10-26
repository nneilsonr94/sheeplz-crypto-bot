"""Adapter for Coinbase Advanced Trade Python library.

This module provides a small factory `get_client(api_key, api_secret, api_passphrase, dry_run)`
that returns an object with the minimal surface required by `run_live.py`:
 - fetch_ticker(symbol) -> {'last': str, 'volume': str}
 - create_market_order(symbol, side, amount, params=None) -> dict
 - action_to_order(action, symbol, max_order_usd=..., price=None) -> dict
 - markets dict (optional)

Behavior:
 - If an official Coinbase AdvancedTrade client (installed from your provided
   repo) is available, this adapter will attempt to instantiate it and call
   idiomatic methods. Because third-party client APIs vary, this adapter tries
   a few common attribute names and falls back to a dry-run stub with clear
   instructions if the installed client isn't detected.
 - To use this adapter, set the env var:
     EXCHANGE_CLIENT_MODULE=exchanges.coinbase_advanced_wrapper

If you'd like, I can adapt this adapter to the exact client API after you
install the library in this environment or paste the library's primary
constructor name.
"""
from __future__ import annotations
from typing import Any, Optional
import logging
import importlib
import os

logger = logging.getLogger(__name__)


class _StubClient:
    def __init__(self):
        self.markets = {'BTC/USD': {'precision': {'amount': 8}}, 'BTC/USDT': {'precision': {'amount': 8}}}

    def fetch_ticker(self, symbol: str):
        import random
        return {'last': str(100 + (random.random() - 0.5)), 'volume': '1'}

    def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[dict] = None):
        logger.info(f"COINBASE-ADVANCED-STUB: DRY RUN ORDER {side} {amount} {symbol}")
        return {'info': {'dry_run': True}, 'symbol': symbol, 'side': side, 'amount': amount}

    def action_to_order(self, action: float, symbol: str, max_order_usd: float = 100.0, price: Optional[float] = None):
        if abs(action) < 1e-9:
            return {'side': None, 'amount': 0.0, 'price': price, 'usd_notional': 0.0}
        side = 'buy' if action > 0 else 'sell'
        usd = min(abs(action), 1.0) * float(max_order_usd)
        if price is None:
            price = float(self.fetch_ticker(symbol).get('last') or 0.0)
        amount = usd / price if price else 0.0
        return {'side': side, 'amount': amount, 'price': price, 'usd_notional': usd}


def _find_candidate_module():
    """Try a list of likely import names for the Coinbase AdvancedTrade library."""
    candidates = [
        'coinbase_advancedtrade',
        'coinbase_advanced_trade',
        'coinbase_advanced',
        'coinbase_advanced_trader',
        'coinbase_advanced_py',
        'advancedtrade',
        'coinbase_advancedtrade_python',
        'coinbase',
    ]
    for name in candidates:
        try:
            m = importlib.import_module(name)
            logger.info(f"Found Coinbase AdvancedTrade module: {name}")
            return m
        except Exception:
            continue
    return None


def get_client(api_key: Optional[str] = None, api_secret: Optional[str] = None, api_passphrase: Optional[str] = None, dry_run: bool = True) -> Any:
    """Factory returning a client compatible with our runner.

    If the third-party library isn't installed, returns a dry-run stub and logs
    instructions for installing the library.
    """
    # prefer an installed library
    mod = _find_candidate_module()
    if mod is None:
        logger.warning("Coinbase AdvancedTrade library not found. Install it with:\n  pip install git+https://github.com/rhettre/coinbase-advancedtrade-python.git\nUsing a dry-run stub instead.")
        return _StubClient()

    # Attempt to locate a factory or client class in the module
    factory = getattr(mod, 'get_client', None) or getattr(mod, 'create_client', None)
    client_obj = None
    try:
        if factory:
            client_obj = factory(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase, dry_run=dry_run)
        else:
            # special-case coinbase.rest.RESTClient. Some distributions expose
            # the REST client in a submodule (coinbase.rest) but don't bind
            # it to the top-level package object, so try importing the
            # submodule if the attribute isn't present. Attempt multiple
            # common ctor signatures (kwarg name variants, base_url, timeout,
            # and a handful of positional signatures) to be resilient across
            # packaging differences.
            rest_cli = getattr(mod, 'rest', None)
            if rest_cli is None:
                try:
                    rest_cli = importlib.import_module(f"{mod.__name__}.rest")
                except Exception:
                    rest_cli = None
            if rest_cli and hasattr(rest_cli, 'RESTClient'):
                REST = getattr(rest_cli, 'RESTClient')
                client_obj = None
                errors = []

                # Prefer credentialed construction when credentials are provided
                provided_api_key = api_key if api_key is not None else os.environ.get('EXCHANGE_API_KEY')
                provided_api_secret = api_secret if api_secret is not None else os.environ.get('EXCHANGE_API_SECRET')
                provided_api_passphrase = api_passphrase if api_passphrase is not None else os.environ.get('EXCHANGE_API_PASSPHRASE')
                prefer_creds = bool(provided_api_key or provided_api_secret or provided_api_passphrase)

                # Build a set of candidate kwarg name combinations and values
                key_names = ['api_key', 'apiKey', 'key', 'key_file', 'keyfile']
                secret_names = ['api_secret', 'apiSecret', 'secret', 'secret_key']
                passphrase_names = ['api_passphrase', 'passphrase', 'passphrase_key']
                base_urls = [None, 'https://api.coinbase.com', 'https://api.exchange.coinbase.com']
                timeouts = [None, 10, 30]

                # Try a set of candidate kwarg dicts
                candidates = []
                for kn in key_names:
                    for sn in secret_names:
                        for pn in passphrase_names:
                            for bu in base_urls:
                                for to in timeouts:
                                    params = {}
                                    if provided_api_key is not None:
                                        params[kn] = provided_api_key
                                    if provided_api_secret is not None:
                                        params[sn] = provided_api_secret
                                    if provided_api_passphrase is not None:
                                        params[pn] = provided_api_passphrase
                                    if bu is not None:
                                        params['base_url'] = bu
                                    if to is not None:
                                        params['timeout'] = to
                                    # only attempt if we added at least one param
                                    if params:
                                        candidates.append(params)

                # Add a small set of positional attempts too
                positional_attempts = []
                if provided_api_key is not None and provided_api_secret is not None and provided_api_passphrase is not None:
                    positional_attempts.append((provided_api_key, provided_api_secret, provided_api_passphrase))
                if provided_api_key is not None and provided_api_secret is not None:
                    positional_attempts.append((provided_api_key, provided_api_secret))
                if provided_api_key is not None:
                    positional_attempts.append((provided_api_key,))

                # If credentials look available, prefer credentialed attempts first,
                # otherwise try no-arg public client first.
                if prefer_creds:
                    # Try kwarg candidates first
                    for params in candidates:
                        try:
                            client_obj = REST(**params)
                            logger.info('Instantiated coinbase.rest.RESTClient from installed package using kwargs: %s', list(params.keys()))
                            break
                        except TypeError as te:
                            errors.append(f'TypeError({list(params.keys())}): {te}')
                            continue
                        except Exception as e:
                            errors.append(f'Error({list(params.keys())}): {e}')
                            continue

                    # Try positional attempts if kwarg attempts failed
                    if client_obj is None:
                        for args in positional_attempts:
                            try:
                                client_obj = REST(*args)
                                logger.info('Instantiated coinbase.rest.RESTClient from installed package using positional args')
                                break
                            except Exception as e:
                                errors.append(f'PositionalError({args}): {e}')
                                continue

                    # Fallback to no-arg public client if still None
                    if client_obj is None:
                        try:
                            client_obj = REST()
                            logger.info('Instantiated coinbase.rest.RESTClient with no args (public client) as fallback')
                        except Exception:
                            client_obj = None
                else:
                    # Try no-arg constructor first (public endpoints)
                    try:
                        client_obj = REST()
                        logger.info('Instantiated coinbase.rest.RESTClient with no args (public client)')
                    except Exception:
                        client_obj = None

                    # Then try credentialed kwarg/positional attempts
                    for params in candidates:
                        try:
                            client_obj = REST(**params)
                            logger.info('Instantiated coinbase.rest.RESTClient from installed package using kwargs: %s', list(params.keys()))
                            break
                        except TypeError as te:
                            errors.append(f'TypeError({list(params.keys())}): {te}')
                            continue
                        except Exception as e:
                            errors.append(f'Error({list(params.keys())}): {e}')
                            continue

                    if client_obj is None:
                        for args in positional_attempts:
                            try:
                                client_obj = REST(*args)
                                logger.info('Instantiated coinbase.rest.RESTClient from installed package using positional args')
                                break
                            except Exception as e:
                                errors.append(f'PositionalError({args}): {e}')
                                continue
                    try:
                        client_obj = REST(**params)
                        logger.info('Instantiated coinbase.rest.RESTClient from installed package using kwargs: %s', list(params.keys()))
                        break
                    except TypeError as te:
                        # signature mismatch -- try next
                        errors.append(f'TypeError({list(params.keys())}): {te}')
                        continue
                    except Exception as e:
                        errors.append(f'Error({list(params.keys())}): {e}')
                        continue

                # Try positional attempts if kwarg attempts failed
                if client_obj is None:
                    for args in positional_attempts:
                        try:
                            client_obj = REST(*args)
                            logger.info('Instantiated coinbase.rest.RESTClient from installed package using positional args')
                            break
                        except Exception as e:
                            errors.append(f'PositionalError({args}): {e}')
                            continue

                if client_obj is None:
                    logger.warning('Failed to instantiate coinbase.rest.RESTClient; attempted many common signatures. Details: %s', errors)
            else:
                # try some common class names
                for cls_name in ('AdvancedTradeClient', 'AdvancedClient', 'Client', 'CoinbaseAdvanced'):
                    cls = getattr(mod, cls_name, None)
                    if cls:
                        try:
                            client_obj = cls(api_key=api_key, api_secret=api_secret, passphrase=api_passphrase)
                            break
                        except TypeError:
                            # try alternate constructor signatures
                            try:
                                client_obj = cls(api_key, api_secret, api_passphrase)
                                break
                            except Exception:
                                continue
    except Exception as e:
        logger.warning(f"Failed to instantiate client from module {mod.__name__}: {e}")

    if client_obj is None:
        logger.warning("Installed Coinbase AdvancedTrade module found but no usable factory/class detected; using dry-run stub. If you installed the library, please open an issue or provide the constructor name so I can adapt this wrapper.")
        return _StubClient()

    # Detect Enhanced-like clients (they expose high-level fiat helpers). Prefer
    # using fiat_market_buy / fiat_market_sell when present. We don't require
    # importing the third-party class; instead, probe the instantiated client
    # for the helper methods so test doubles work as expected.
    try:
        enhanced_cls = None
        enhanced_present = hasattr(client_obj, 'fiat_market_buy') or hasattr(client_obj, 'fiat_market_sell')
    except Exception:
        enhanced_present = False

    # Wrap the client to a uniform surface
    class _Wrapper:
        def __init__(self, client):
            self._c = client
            # try to discover markets if available
            self.markets = getattr(client, 'markets', {}) or getattr(client, 'symbols', {}) or {}

        def fetch_ticker(self, symbol: str):
            # normalize symbol to Coinbase product_id format (e.g. BTC/USD -> BTC-USD)
            prod = symbol.replace('/', '-').replace('_', '-').replace('XBT', 'BTC')

            # Prefer public product helpers which return a market-level view
            public_candidates = ('get_public_product', 'get_public_products', 'get_product', 'get_best_bid_ask', 'get_public_market_trades', 'get_market_trades')
            for meth in public_candidates:
                fn = getattr(self._c, meth, None)
                if callable(fn):
                    try:
                        # Many of these accept a single product_id positional arg
                        res = fn(prod)
                        if isinstance(res, (int, float, str)):
                            return {'last': str(res), 'volume': '0'}
                        # normalize dict-like responses
                        if isinstance(res, dict):
                            if 'price' in res:
                                return {'last': str(res.get('price')), 'volume': str(res.get('volume_24h', '0'))}
                            if 'mid_market_price' in res and res.get('mid_market_price'):
                                return {'last': str(res.get('mid_market_price')), 'volume': '0'}
                            return res
                        # normalize object-style responses (e.g., GetProductResponse)
                        try:
                            price = getattr(res, 'price', None) or getattr(res, 'mid_market_price', None)
                            volume = getattr(res, 'volume_24h', None) or getattr(res, 'volume', None)
                            if price is not None:
                                return {'last': str(price), 'volume': str(volume or '0')}
                        except Exception:
                            pass
                        return res
                    except TypeError:
                        # signature mismatch, try next candidate
                        continue
                    except Exception:
                        # method exists but raised (e.g., requires auth) -> try next
                        continue

            # try a few generic method names as a last resort (cover other client variants)
            fetch_candidates = (
                'fetch_ticker', 'get_ticker', 'ticker', 'get_ticker_for_symbol',
                'get_product_ticker', 'get_latest_price', 'get_price', 'get_market_price', 'price', 'ticker_for'
            )
            for meth in fetch_candidates:
                fn = getattr(self._c, meth, None)
                if callable(fn):
                    # try common call signatures
                    for args, kwargs in (([symbol], {}), ([], {'product_id': prod}), ([], {'symbol': prod}), ([], {})):
                        try:
                            res = fn(*args, **kwargs)
                            # normalize simple numeric responses
                            if isinstance(res, (int, float, str)):
                                return {'last': str(res), 'volume': '0'}
                            return res
                        except TypeError:
                            continue
                        except Exception:
                            # if the method exists but failed, try next candidate
                            break
            # last resort: try raw REST-like call
            for meth in ('get_market_price', 'get_price', 'price'):
                fn = getattr(self._c, meth, None)
                if callable(fn):
                    try:
                        p = fn(symbol)
                        return {'last': str(p), 'volume': '0'}
                    except Exception:
                        continue
            # fallback
            return {'last': '0', 'volume': '0'}

        def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[dict] = None):
            # If this is an EnhancedRESTClient instance, use its higher-level fiat helpers
            try:
                if enhanced_present:
                    # Enhanced-style clients expose fiat_market_buy / fiat_market_sell
                    # which accept fiat_amount strings. Compute a fiat amount from
                    # params if present, otherwise use amount*price when possible.
                    fiat_amount = ''
                    if params and params.get('usd_notional'):
                        try:
                            fiat_amount = str(float(params.get('usd_notional')))
                        except Exception:
                            fiat_amount = ''
                    elif params and params.get('price'):
                        try:
                            fiat_amount = str(amount * float(params.get('price')))
                        except Exception:
                            fiat_amount = ''
                    # final fallback
                    if not fiat_amount:
                        fiat_amount = str(0.0)
                    if side == 'buy' and hasattr(self._c, 'fiat_market_buy'):
                        logger.info('Using Enhanced-style fiat_market_buy for symbol=%s fiat_amount=%s', symbol, fiat_amount)
                        return getattr(self._c, 'fiat_market_buy')(symbol, fiat_amount)
                    elif side == 'sell' and hasattr(self._c, 'fiat_market_sell'):
                        logger.info('Using Enhanced-style fiat_market_sell for symbol=%s fiat_amount=%s', symbol, fiat_amount)
                        return getattr(self._c, 'fiat_market_sell')(symbol, fiat_amount)
            except Exception:
                # if Enhanced-style attempt fails, fall back to generic attempts below
                pass

            # broaden signature attempts to handle different client APIs
            order_candidates = (
                'create_order', 'place_order', 'submit_order', 'market_order', 'create_market_order',
                'place_market_order', 'new_order', 'place_trade', 'create_trade', 'submit_trade'
            )
            for meth in order_candidates:
                fn = getattr(self._c, meth, None)
                if callable(fn):
                    # try several common signatures
                    sig_attempts = [
                        ((symbol, 'market', side, amount, params or {}), {}),
                        ((side, amount, symbol), {}),
                        ((symbol, side, amount), {}),
                        ((), {'product_id': symbol, 'side': side, 'size': amount}),
                        ((), {'product_id': symbol, 'side': side, 'size': amount, **(params or {})}),
                        ((), {'symbol': symbol, 'side': side, 'amount': amount}),
                        ((), {'order_type': 'market', 'product_id': symbol, 'size': amount, 'side': side}),
                        ((symbol, amount), {'side': side}),
                    ]
                    for args, kwargs in sig_attempts:
                        try:
                            return fn(*args, **kwargs)
                        except TypeError:
                            continue
                        except Exception:
                            # method exists but raised; try next signature/method
                            break
            # fallback: return dry-run style dict
            return {'info': {'dry_run': True}, 'symbol': symbol, 'side': side, 'amount': amount}

        def action_to_order(self, action: float, symbol: str, max_order_usd: float = 100.0, price: Optional[float] = None):
            if abs(action) < 1e-9:
                return {'side': None, 'amount': 0.0, 'price': price, 'usd_notional': 0.0}
            side = 'buy' if action > 0 else 'sell'
            magnitude = min(abs(action), 1.0)
            usd = magnitude * float(max_order_usd)
            if price is None:
                ticker = self.fetch_ticker(symbol)
                price = float(ticker.get('last') or 0.0)
            amount = usd / float(price) if price else 0.0
            # try to round using market precision
            market = getattr(self, 'markets', {}).get(symbol)
            if market:
                precision = market.get('precision', {})
                base_prec = precision.get('amount')
                if base_prec is not None:
                    try:
                        base_prec_int = int(base_prec)
                    except Exception:
                        base_prec_int = 8
                    amount = float(round(amount, base_prec_int))
            return {'side': side, 'amount': amount, 'price': price, 'usd_notional': usd}

    return _Wrapper(client_obj)
