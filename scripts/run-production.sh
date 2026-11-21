#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env.production"
COMPOSE="docker compose -p maestro --env-file $ENV_FILE -f docker/docker-compose.prod.yml"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Install $1 first, then run this script again." >&2
    exit 1
  fi
}

need docker
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is required (Docker Desktop or the compose plugin)." >&2
  exit 1
fi

rand_hex() {
  openssl rand -hex "$1"
}

rand_b64() {
  openssl rand -base64 "$1" | tr -d '\n'
}

if [ ! -f "$ENV_FILE" ]; then
  PASS="$(rand_hex 10)Aa1"
  POSTGRES_PASSWORD="$(rand_hex 16)"
  cat > "$ENV_FILE" <<EOF
ENVIRONMENT=production
MAESTRO_PORT=8080
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DATABASE_URL=postgresql+psycopg://tradeguard:${POSTGRES_PASSWORD}@postgres:5432/tradeguard
REDIS_URL=redis://redis:6379/0
JWT_SECRET=$(rand_hex 32)
MASTER_KEY=$(rand_b64 32)
COOKIE_SECURE=false
CORS_ORIGINS=
PUBLIC_BASE_URL=http://localhost:8080
SEED_ADMIN_EMAIL=owner@local
SEED_ADMIN_PASSWORD=${PASS}
SEED_ADMIN_NAME=Maestro Owner
SEED_SAMPLE_DATA=false
EOF
  chmod 600 "$ENV_FILE"
  echo "Wrote $ENV_FILE"
  echo "Owner login (save this):"
  echo "  email:    owner@local"
  echo "  password: ${PASS}"
fi

PORT="$(awk -F= '/^MAESTRO_PORT=/{print $2}' "$ENV_FILE" | tr -d '\r' | tail -n 1)"
PORT="${PORT:-8080}"

echo "Building and starting Maestro on port ${PORT}..."
$COMPOSE up --build -d

healthy() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health', timeout=4)"
  else
    return 1
  fi
}

echo "Waiting for health..."
i=0
while [ "$i" -lt 90 ]; do
  if healthy; then
    echo
    echo "Maestro is up."
    echo "Open:  http://127.0.0.1:${PORT}"
    echo "From other devices on this network, use this computer's IP and port ${PORT}."
    echo "Login is in $ENV_FILE (SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD)."
    echo "Stop:  $COMPOSE down"
    echo "Wipe:  $COMPOSE down -v"
    exit 0
  fi
  i=$((i + 1))
  sleep 2
done

echo "The stack started but /health did not respond yet. Check: $COMPOSE logs" >&2
exit 1
