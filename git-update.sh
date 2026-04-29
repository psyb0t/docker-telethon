#!/usr/bin/env bash
set -euo pipefail

git add requirements.txt git-update.sh

git commit -m "$(cat <<'EOF'
fix: skip cryptg on aarch64 — no prebuilt wheel, needs Rust to build

cryptg is an optional Telethon crypto accelerator. No arm64 wheel exists
for 0.5.0 so builds fail on aarch64. Restrict install to x86_64 where
the wheel is available. Telethon falls back to pyaes automatically.
EOF
)"

git push origin main

git tag -a v0.1.1 -m "$(cat <<'EOF'
v0.1.1 — fix arm64 build

Skip cryptg on aarch64 to unblock multi-arch Docker builds.
EOF
)"

git push origin v0.1.1
