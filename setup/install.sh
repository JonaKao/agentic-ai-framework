#!/bin/bash
# Installs the agent commands, reviewer and permissions into .claude/ (one time).
cd "$(dirname "$0")/.."
mkdir -p .claude
cp -R setup/claude/. .claude/
echo "Installed /task, /fix, /draft, /new-project, /onboard and the reviewer agent into .claude/"
