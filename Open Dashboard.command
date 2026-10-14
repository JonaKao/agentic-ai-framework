#!/bin/bash
# Double-click in Finder to start the dashboard and open it in your browser.
cd "$(dirname "$0")"
bash setup/install.sh   # keeps .claude/ in sync with setup/claude/
(sleep 1 && open "http://localhost:8765") &
python3 dashboard/server.py
