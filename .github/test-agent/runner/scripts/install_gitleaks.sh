#!/usr/bin/env bash
# Install a pinned, checksum-verified gitleaks and export GITLEAKS_BIN for the following steps.
set -euo pipefail

version="8.30.1"
sha256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
target="${RUNNER_TEMP:?RUNNER_TEMP is not set}/gitleaks"

mkdir -p "$target"
curl -sSLo "$target/gitleaks.tar.gz" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${version}/gitleaks_${version}_linux_x64.tar.gz"
echo "${sha256}  $target/gitleaks.tar.gz" | sha256sum -c -
tar -xzf "$target/gitleaks.tar.gz" -C "$target" gitleaks
echo "GITLEAKS_BIN=$target/gitleaks" >> "${GITHUB_ENV:?GITHUB_ENV is not set}"
