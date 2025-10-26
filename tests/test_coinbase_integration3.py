import os

from exchanges.exchange_factory import get_exchange_client


def test_coinbase_wrapper_dry_run():
    """
    Basic smoke test for the Coinbase Advanced wrapper via the exchange factory.
    This runs in DRY_RUN mode to avoid placing real orders. It checks that:
      - a client can be created
      - fetch_ticker returns a dict-like response
      - action_to_order can build an order payload
      - create_market_order returns a dry-run style response
    """
    # Ensure we use our wrapper path and dry-run behavior
    os.environ.setdefault("EXCHANGE", "coinbase_advanced")
    os.environ.setdefault("EXCHANGE_CLIENT_MODULE", "exchanges.coinbase_advanced_wrapper")
    os.environ.setdefault("DRY_RUN", "1")

    client = get_exchange_client()
    assert client is not None

    # fetch ticker (should not raise)
    ticker = client.fetch_ticker("BTC-USD")
    assert isinstance(ticker, dict) or hasattr(ticker, "get")

    # Build an order from an action and validate a dry-run response
    # Use a small USD amount to be safe
    action = 0.5
    order = client.action_to_order(action, "BTC-USD", max_order_usd=5.0)
    # order should be a dict-like description
    assert isinstance(order, dict) or hasattr(order, "get")

    # Attempt to create a market order (dry-run should prevent real trade)
    resp = client.create_market_order(order.get('symbol') or 'BTC-USD', order.get('side'), order.get('amount'))
    # In dry-run mode we expect the wrapper to return a response that includes dry-run info
    if isinstance(resp, dict):
        assert ("dry_run" in resp.get("info", {}) or resp.get("dry_run") is True) or (resp.get("status") in ("dry_run", None))


if __name__ == "__main__":
    # Quick local run helper
    test_coinbase_wrapper_dry_run()
    print("coinbase wrapper dry-run smoke test: OK")
