# Run Maestro in production

This stack runs on any machine with Docker: laptop, VPS, or another office computer. One public port. Postgres and Redis stay inside the stack.

## What you need

- Docker with the Compose plugin (Docker Desktop on Mac/Windows, or Docker Engine on Linux)
- Port **8080** free (or change `MAESTRO_PORT` in `.env.production`)
- About 2 GB of free RAM for the first build

You do **not** need a local Python or Node install.

## Start

From the `tradeguard` folder:

```bash
chmod +x scripts/run-production.sh
./scripts/run-production.sh
```

The first run creates `.env.production` with new secrets and an owner password, then builds and starts the stack. Save the printed email and password.

Open:

- This computer: `http://127.0.0.1:8080`
- Phone or another device: `http://THIS-COMPUTER-IP:8080`

Login with `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` from `.env.production`.

## Useful commands

All of these are run from `tradeguard/`:

```bash
# Status
docker compose -p maestro --env-file .env.production -f docker/docker-compose.prod.yml ps

# Logs
docker compose -p maestro --env-file .env.production -f docker/docker-compose.prod.yml logs -f

# Stop (keeps data)
docker compose -p maestro --env-file .env.production -f docker/docker-compose.prod.yml down

# Start again after a reboot
./scripts/run-production.sh

# Wipe database and Redis
docker compose -p maestro --env-file .env.production -f docker/docker-compose.prod.yml down -v
```

## Move the stack to another computer

1. Copy the `tradeguard` folder **and** `.env.production`.
2. Run `./scripts/run-production.sh` there.
3. To keep existing wallets and users, also copy Docker volumes, or take a Postgres dump first.

Do not commit `.env.production`. It holds the database password, signing key, and owner login.

## HTTPS later

When you have a domain and TLS in front of port 8080:

1. Set `COOKIE_SECURE=true` in `.env.production`
2. Set `PUBLIC_BASE_URL=https://your-domain`
3. Set `CORS_ORIGINS=https://your-domain`
4. Run `./scripts/run-production.sh` again

## Notes

- Options Trading browser login needs Chrome on the machine that runs the API. MetaAPI, wallet, mining, and Project Coin do not.
- Do not point this stack at the local development `.env`. Production uses its own Postgres inside Docker.
- Change the owner password after first login if this host is reachable from a network.
