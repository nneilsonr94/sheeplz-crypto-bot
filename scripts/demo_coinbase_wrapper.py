"""Small demo for the Coinbase Advanced wrapper.

Usage examples:
  # Dry-run demo with defaults
  python scripts/demo_coinbase_wrapper.py

  # Use env vars to toggle dry-run and set symbol
  DRY_RUN=0 SYMBOL=BTC-USD python scripts/demo_coinbase_wrapper.py --api-key K --api-secret S --max-order-usd 5

This script accepts both environment variables and CLI flags. CLI flags override env vars.
"""
import os
import argparse
from exchanges import coinbase_advanced_wrapper as cbw


def parse_args():
    p = argparse.ArgumentParser(description='Demo for coinbase_advanced_wrapper')
    p.add_argument('--api-key', default=os.getenv('EXCHANGE_API_KEY'))
    p.add_argument('--api-secret', default=os.getenv('EXCHANGE_API_SECRET'))
    p.add_argument('--api-passphrase', default=os.getenv('EXCHANGE_API_PASSPHRASE'))
    p.add_argument('--dry-run', type=int, default=int(os.getenv('DRY_RUN', '1')),
                   help='1 = dry-run (default), 0 = live (only for demo purposes)')
    p.add_argument('--symbol', default=os.getenv('SYMBOL', 'BTC-USD'))
    p.add_argument('--max-order-usd', type=float, default=float(os.getenv('MAX_ORDER_USD', '10.0')))
    p.add_argument('--action', type=float, default=float(os.getenv('ACTION', '0.5')),
                   help='Action magnitude between -1 and 1 (positive=buy, negative=sell)')
    return p.parse_args()


def main():
    args = parse_args()
    dry_run = bool(args.dry_run)
    client = cbw.get_client(api_key=args.api_key, api_secret=args.api_secret, api_passphrase=args.api_passphrase, dry_run=dry_run)

    print('client type:', type(client))
    print('markets available (sample):', list(getattr(client, 'markets', {}).keys())[:5])

    sym = args.symbol
    print('\nfetch_ticker =>', client.fetch_ticker(sym))

    order = client.action_to_order(args.action, sym, max_order_usd=args.max_order_usd)
    print('\naction_to_order(%s) =>' % args.action, order)

    resp = client.create_market_order(sym, order.get('side'), order.get('amount'), params={'price': order.get('price'), 'usd_notional': order.get('usd_notional')})
    print('\ncreate_market_order =>', resp)


if __name__ == '__main__':
    main()
