#!/usr/bin/env bash
set -e

# Bring the cluster up unless it is already online.
#
# The Debian package creates the cluster but nothing starts it inside a
# container, and it does not come back after a plain container restart. Called
# from db-setup.sh on creation and from postStartCommand on every start, so it
# has to be idempotent.
sudo pg_lsclusters -h | grep -q online || sudo pg_ctlcluster 17 main start