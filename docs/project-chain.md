# Project Coin

Project Coin is Maestro's own SHA-256 proof-of-work chain. It runs inside the existing API and uses the same login. It is a single local node. It is not Bitcoin, and it is not the external Mining page that reads a payout address.

## Rules

The defaults live in the server environment:

- `CHAIN_COIN_NAME` Project Coin
- `CHAIN_SYMBOL` PCOIN
- `CHAIN_MAX_SUPPLY` 21000000
- `CHAIN_INITIAL_REWARD` 50
- `CHAIN_HALVING_INTERVAL` 210000
- `CHAIN_DIFFICULTY` 16 leading zero bits
- `CHAIN_FEE` 0.001
- `CHAIN_CPU_PERCENT` 20
- `CHAIN_CPU_MAX` 50

Amounts use 8 decimal places. The browser cannot set a balance or a block reward. A reward is stored only after the block's proof of work and the whole chain check succeed. CPU use is capped so a miner cannot take the whole machine. The default cap is 50 percent.

Private keys are encrypted with the existing `MASTER_KEY`. `GET /api/v1/chain/wallet` returns the address and public key. The private key is returned only by `POST /api/v1/chain/wallet/export` after `confirm` is true.

## Database

From `tradeguard`, with `DATABASE_URL` set to the application database:

```bash
cd database
PYTHONPATH=../backend ../.venv/bin/alembic upgrade head
```

That applies `0018_project_chain`, which adds chain wallets, blocks, transactions, sessions, hits, and the local node row.

## Run

API, from `tradeguard`:

```bash
PGCLIENTENCODING=UTF8 PYTHONPATH=risk-engine:shared/python .venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Desk, from `tradeguard/frontend`:

```bash
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Mining starts from the Project Coin page. The hash search is a child process of the API, so it does not need a separate terminal. Stopping the API stops mining.

## API

All routes are under `/api/v1/chain` and use the existing session.

- `POST /wallet`, `POST /wallet/import`, `POST /wallet/export`, `GET /wallet`, `GET /wallet/balance`, `GET /wallet/transactions`, `POST /wallet/send`
- `POST /mining/start`, `/stop`, `/pause`, `/resume`
- `GET /mining/status`, `GET /mining/statistics`
- `GET /mining/plans`, `GET /mining/hybrid`, `POST /mining/upgrades`, `GET /mining/upgrades`, `GET /mining/rewards`
- Admin: `GET/PUT /mining/admin/settings`, `GET/POST /mining/admin/plans`, `PUT /mining/admin/plans/{id}`, `GET /mining/admin/overview`, `GET /mining/admin/miners`, `GET /mining/admin/suspicious`
- `GET /blocks`, `GET /blocks/{height}`, `GET /transactions`, `GET /transactions/{hash}`, `GET /search`
- `GET /network/status`

## Hybrid mining

Free proof-of-work mining is unchanged. Existing wallets, sessions, and block rewards stay on the chain.

Paid plans add extra PCoin only while a mining session is running. The extra is `base_daily_pcoin * (multiplier - 1) * elapsed_seconds / 86400`, stored in `mining_reward_ledger` with Decimal math. Expired plans stop applying. Upgrades activate only after a wallet debit or a verified NOWPayments/Cryptomus IPN. A browser payment-success message cannot turn a plan on.

PCoin is not USDT until a verified conversion. No new environment variables are required.

Migration `0024_hybrid_mining` adds plan, upgrade, payment, and ledger tables. It does not rewrite chain blocks or balances.

`network/status` reports `decentralized: false` and an empty peer list. Block and transaction propagation is a module boundary for a later peer link. `Ledger.replace_if_stronger` already rejects a weaker chain, a different genesis block, and a repeated block hash.

## Tests

```bash
cd tradeguard
DATABASE_URL= PYTHONPATH=backend .venv/bin/pytest tests/unit/test_project_chain.py --noconftest
```

Do not run the integration client fixture while `DATABASE_URL` points at the application database.
