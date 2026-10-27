#!/usr/bin/env bash
# Make the workspace readable but not writable for the sandbox user, and hide .git from it.
# Run on a GitHub-hosted runner after the dependencies are installed and before any model-written code runs.
set -euo pipefail

SANDBOX_UID=65534
workspace="${GITHUB_WORKSPACE:?GITHUB_WORKSPACE is not set}"

sudo apt-get install -y -q acl >/dev/null
sudo setfacl -R -m "u:${SANDBOX_UID}:rX" "$workspace"
sudo setfacl -R -m "u:${SANDBOX_UID}:---" "$workspace/.git"

# The sandbox user must be able to walk down to the workspace.
dir="$workspace"
while [ "$dir" != "/" ]; do
  sudo setfacl -m "u:${SANDBOX_UID}:x" "$dir"
  dir="$(dirname "$dir")"
done
