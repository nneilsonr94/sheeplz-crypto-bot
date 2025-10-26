import types
import pytest

import exchanges.coinbase_advanced_wrapper as cbw


def make_brittle_enhanced(monkeypatch):
    """Fake Enhanced-style client where fiat helpers raise exceptions."""
    class BrittleEnhanced:
        def __init__(self, api_key=None, api_secret=None, **kwargs):
            pass

        def fiat_market_buy(self, product_id, fiat_amount):
            raise RuntimeError("simulated fiat helper failure")

        def fiat_market_sell(self, product_id, fiat_amount):
            raise RuntimeError("simulated fiat helper failure")

    fake_mod = types.SimpleNamespace()
    fake_mod.rest = types.SimpleNamespace(RESTClient=BrittleEnhanced)
    return fake_mod


def test_enhanced_helper_failure_falls_back_to_generic(monkeypatch):
    """If Enhanced helpers exist but raise, the wrapper should fall back to generic order methods when available."""
    # Fake module where the instantiated client has fiat helpers that raise,
    # but also provide a create_order method to fall back to.
    class FallbackClient:
        def __init__(self, api_key=None, api_secret=None, **kwargs):
            pass

        def fiat_market_buy(self, product_id, fiat_amount):
            raise RuntimeError("fiat failure")

        def create_order(self, product_id, side, size):
            return {'result': 'fallback_ok', 'product_id': product_id, 'side': side, 'size': size}

    fake_mod = types.SimpleNamespace()
    fake_mod.rest = types.SimpleNamespace(RESTClient=FallbackClient)
    monkeypatch.setattr(cbw, '_find_candidate_module', lambda: fake_mod)

    client = cbw.get_client(api_key='k', api_secret='s', dry_run=False)
    assert client is not None

    resp = client.create_market_order('BTC-USD', 'buy', 0.001, params={'price': '20000'})
    assert isinstance(resp, dict)
    # fallback create_order should be used
    assert resp.get('result') == 'fallback_ok'


def test_enhanced_helper_failure_with_no_fallback_returns_dryrun(monkeypatch):
    """If Enhanced helpers exist and raise and no generic order method exists, we return a dry-run dict."""
    fake_mod = make_brittle_enhanced(monkeypatch)
    monkeypatch.setattr(cbw, '_find_candidate_module', lambda: fake_mod)

    client = cbw.get_client(api_key='k', api_secret='s', dry_run=False)
    assert client is not None

    resp = client.create_market_order('BTC-USD', 'sell', 0.002)
    assert isinstance(resp, dict)
    # wrapper fallback returns a dry-run style dict when no real method succeeded
    assert resp.get('info', {}).get('dry_run') is True or 'result' not in resp
