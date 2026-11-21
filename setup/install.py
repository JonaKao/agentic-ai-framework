#!/usr/bin/env python3
"""Installs the agent commands, reviewer and permissions into .claude/ (one time).

Same as setup/install.sh, without bash (works on Windows), and also puts setup/mcp.json
at .mcp.json. Run from anywhere: python3 setup/install.py"""
import os
import shutil

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
setup = os.path.join(root, "setup")
shutil.copytree(os.path.join(setup, "claude"), os.path.join(root, ".claude"), dirs_exist_ok=True)
shutil.copyfile(os.path.join(setup, "mcp.json"), os.path.join(root, ".mcp.json"))
print("Installed the commands (/spec, /task, /fix, /draft, /new-project, /onboard), the reviewer "
      "and mapper agents, and the settings into .claude/, and the MCP servers into .mcp.json")
