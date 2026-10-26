#!/usr/bin/env bash
set -e

# On every start: bring the database back up. The app creates its tables itself on startup.
bash ".devcontainer/db-start.sh"