# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-10-26

### Added
- Coinbase Advanced wrapper: enhanced detection for "Enhanced-style" clients that expose fiat helpers; runtime logging when those helpers are used. (`exchanges/coinbase_advanced_wrapper.py`)
- Unit tests covering wrapper mapping and failover behavior. (`tests/test_coinbase_wrapper_mapping.py`, `tests/test_coinbase_wrapper_enhanced_failover.py`, `tests/test_coinbase_wrapper_logging.py`)
- Dry-run demo script for the wrapper with CLI/env support. (`scripts/demo_coinbase_wrapper.py`)
- GitHub Actions CI workflow with separate jobs for unit tests and optional vendor/integration tests. (`.github/workflows/ci.yml`)
- `pytest.ini` to ignore vendor integration tests by default to keep CI and local test runs stable.

### Changed
- Vendor health test updated to skip (during pytest collection) when the local health endpoint is unreachable. (`vendor/pantheon-server/test_health.py`)

### Notes
- Vendor/integration tests are intentionally opt-in (set `RUN_VENDOR_INTEGRATION=true` in CI) because they require external services and optional dependencies.
