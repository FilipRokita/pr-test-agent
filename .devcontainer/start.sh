#!/usr/bin/env bash
set -e

# Local PostgreSQL is installed and set up by setup.sh but not started automatically:
# the README runs the app and its database with docker compose (same port 5432).
# Start it manually with db-start.sh when needed.
# bash ".devcontainer/db-start.sh"