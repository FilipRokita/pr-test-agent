#!/usr/bin/env bash
set -e

# The app reads its configuration from .env (see .env.example).
[ -f .env ] || cp .env.example .env

# Local PostgreSQL 17 + the role and database from .env
bash ".devcontainer/db-setup.sh"

# Backend: virtual environment and pinned dependencies
python -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

# Frontend: dependencies
(cd frontend && npm ci)