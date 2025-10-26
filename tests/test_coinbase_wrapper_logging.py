import types
import pytest

import exchanges.coinbase_advanced_wrapper as cbw


def make_enhanced_module_with_logging():
    class FakeEnhanced:
        def __init__(self, api_key=None, api_secret=None, **kwargs):
            pass

        def fiat_market_buy(self, product_id, fiat_amount):
            return {"result": "fiat_buy", "product_id": product_id, "fiat_amount": fiat_amount}

    fake_mod = types.SimpleNamespace()
    fake_mod.rest = types.SimpleNamespace(RESTClient=FakeEnhanced)
    return fake_mod


def test_logs_when_using_enhanced_helpers(monkeypatch, caplog):
    fake_mod = make_enhanced_module_with_logging()
    monkeypatch.setattr(cbw, '_find_candidate_module', lambda: fake_mod)

    caplog.clear()
    client = cbw.get_client(api_key='k', api_secret='s', dry_run=False)
    assert client is not None

    with caplog.at_level('INFO'):
        resp = client.create_market_order('BTC-USD', 'buy', 0.001, params={'price': '20000'})

    # Ensure we logged that we used the Enhanced-style helper
    assert any('Enhanced-style fiat_market_buy' in rec.message for rec in caplog.records)
    assert isinstance(resp, dict)
    assert resp.get('result') == 'fiat_buy'
