#!/usr/bin/env bash
set -e

# Local PostgreSQL 17 (Debian's native version, no third-party repo needed).
# Data lives in the container layer, so it is wiped on every rebuild.
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql-17

# The package creates the cluster but nothing starts it inside a container
bash ".devcontainer/db-start.sh"

# Role and database come from .env so the app connects with the same values.
set -a
# shellcheck disable=SC1091
. ./.env
set +a

sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${POSTGRES_USER}'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE ROLE \"${POSTGRES_USER}\" LOGIN PASSWORD '${POSTGRES_PASSWORD}';"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'" | grep -q 1 \
  || sudo -u postgres createdb -O "${POSTGRES_USER}" "${POSTGRES_DB}"