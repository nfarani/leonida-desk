#!/usr/bin/env bash
# Mirror agents/ and commands/ into .claude/ so Claude Code discovers them.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .claude/agents .claude/commands
cp agents/*.md .claude/agents/
cp commands/*.md .claude/commands/
echo "Synced agents/ and commands/ into .claude/"
