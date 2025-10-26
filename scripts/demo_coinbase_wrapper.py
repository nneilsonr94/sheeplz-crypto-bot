"""Small DRY_RUN demo for the Coinbase Advanced wrapper.

Run this script to see example outputs from `get_client` in dry-run mode.
"""
from exchanges import coinbase_advanced_wrapper as cbw


def main():
    client = cbw.get_client(dry_run=True)
    print("client:", type(client), getattr(client, 'markets', None))

    sym = 'BTC-USD'
    print('\nfetch_ticker =>', client.fetch_ticker(sym))
    order = client.action_to_order(0.5, sym, max_order_usd=10.0)
    print('\naction_to_order(0.5) =>', order)
    resp = client.create_market_order(sym, order.get('side'), order.get('amount'), params={'price': order.get('price')})
    print('\ncreate_market_order =>', resp)


if __name__ == '__main__':
    main()
