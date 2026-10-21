#!/bin/bash
# Installs the agent commands, reviewer and permissions into .claude/ (one time).
cd "$(dirname "$0")/.."
mkdir -p .claude
cp -R setup/claude/. .claude/
echo "Installed the commands (/spec, /task, /fix, /draft, /new-project, /onboard), the reviewer and mapper agents, and the settings into .claude/"
