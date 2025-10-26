# sheeplz-crypto-bot

Short ops notes: recommended production env vars and safety checklist.

## Recommended production environment variables
- EXCHANGE: exchange id to use (e.g. `coinbase_advanced` or `kraken`)
- EXCHANGE_API_KEY / EXCHANGE_API_SECRET / EXCHANGE_API_PASSPHRASE: credentials stored in secrets
- DRY_RUN: set to `0` for live trading; keep `1` by default during rollout
- RUN_STEPS: leave unset for continuous running; set small integer for smoke tests
- MAX_ACCOUNT_NOTIONAL_USD: maximum USD exposure allowed by PositionManager
- MIN_ORDER_USD: smallest order notional permitted
- PM_COOLDOWN_SECONDS: cooldown between trades enforced by PositionManager
- PM_STOP_LOSS_PCT / PM_TAKE_PROFIT_PCT: stop-loss / take-profit percentages
- MODEL_1MIN_PATH: path to 1-minute model artifact (if used)

<<<<<<< HEAD
### Suggested default values (example)
- DRY_RUN=1
- MAX_ACCOUNT_NOTIONAL_USD=1000
- MIN_ORDER_USD=1.0
- PM_COOLDOWN_SECONDS=5
- PM_STOP_LOSS_PCT=0.05
- PM_TAKE_PROFIT_PCT=0.1

## Deployment (example: systemd service)
Below is an example `systemd` unit file you can adapt for running the live loop on a server. It assumes you use a virtualenv at `/opt/sheeplz/venv` and a deploy user `sleeper`.

Create file `/etc/systemd/system/sheeplz-live.service` with the following content:

```ini
[Unit]
Description=Sheeplz Crypto Bot live runner
After=network.target

[Service]
Type=simple
User=sleeper
# sheeplz-crypto-bot

Short ops notes: recommended production env vars and safety checklist.

## Recommended production environment variables
- EXCHANGE: exchange id to use (e.g. `coinbase_advanced` or `kraken`)
- EXCHANGE_API_KEY / EXCHANGE_API_SECRET / EXCHANGE_API_PASSPHRASE: credentials stored in secrets
- DRY_RUN: set to `0` for live trading; keep `1` by default during rollout
- RUN_STEPS: leave unset for continuous running; set small integer for smoke tests
- MAX_ACCOUNT_NOTIONAL_USD: maximum USD exposure allowed by PositionManager
- MIN_ORDER_USD: smallest order notional permitted
- PM_COOLDOWN_SECONDS: cooldown between trades enforced by PositionManager
- PM_STOP_LOSS_PCT / PM_TAKE_PROFIT_PCT: stop-loss / take-profit percentages
- MODEL_1MIN_PATH: path to 1-minute model artifact (if used)

### Suggested default values (example)
- DRY_RUN=1
- MAX_ACCOUNT_NOTIONAL_USD=1000
- MIN_ORDER_USD=1.0
- PM_COOLDOWN_SECONDS=5
- PM_STOP_LOSS_PCT=0.05
- PM_TAKE_PROFIT_PCT=0.1

## Deployment (example: systemd service)
Below is an example `systemd` unit file you can adapt for running the live loop on a server. It assumes you use a virtualenv at `/opt/sheeplz/venv` and a deploy user `sleeper`.
Create file `/etc/systemd/system/sheeplz-live.service` with the following content:

```ini
[Unit]
Description=Sheeplz Crypto Bot live runner
After=network.target

[Service]
Type=simple
User=sleeper
WorkingDirectory=/opt/sheeplz
Environment=DRY_RUN=1
Environment=EXCHANGE=coinbase_advanced
Environment=MAX_ACCOUNT_NOTIONAL_USD=1000
Environment=MIN_ORDER_USD=1.0
Environment=PM_COOLDOWN_SECONDS=5
Environment=MODEL_1MIN_PATH=/opt/sheeplz/models/lgbm_1min.pkl
ExecStart=/opt/sheeplz/venv/bin/python run_live.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Notes:
- Start in dry-run mode first and monitor logs: `journalctl -u sheeplz-live -f`.
- Use a secrets manager (HashiCorp Vault, AWS Secrets Manager, or GitHub Actions secrets) to provide API keys securely.
- When confident, flip `DRY_RUN=0` and monitor circuit-breaker/alerts closely.

## Safety checklist before going live
1. Validate credentials are stored in a secure secrets manager (do not hardcode keys).
2. Run the fake-exchange demo locally with `DRY_RUN=1` and `USE_FAKE_EXCHANGE=1` and verify behavior:

```bash
USE_FAKE_EXCHANGE=1 DRY_RUN=1 RUN_STEPS=12 POLL_INTERVAL=0.5 python run_live.py
```

3. Run unit tests and smoke tests in CI (the repo includes a `smoke-demo` CI job that runs on pushes to `main` and on tags).
4. Ensure monitoring/alerts are configured to capture CircuitBreaker opens and order failures.
5. Start with conservative position limits: `MAX_ACCOUNT_NOTIONAL_USD` small and `MIN_ORDER_USD` low.
6. Flip `DRY_RUN` to `0` only after a sustained, successful dry-run and code review.

For demo/test env vars see `docs/FAKE_EXCHANGE.md`.
