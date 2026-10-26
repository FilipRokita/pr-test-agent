#!/usr/bin/env bash
set -e

# The app reads its configuration from .env (see .env.example).
[ -f .env ] || cp .env.example .env

# Backend: virtual environment and pinned dependencies.
# --clear rebuilds it, so a stale .venv from an earlier image cannot break setup.
python -m venv --clear backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

# Frontend: dependencies
(cd frontend && npm ci)