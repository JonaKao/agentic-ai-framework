#!/usr/bin/env python3
"""The dashboard now lives in projects/control-room, so agents can improve it with /task.
This file only starts it, so `python3 dashboard/server.py` keeps working."""
import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
target = os.path.join(os.path.dirname(here), "projects", "control-room", "server.py")
sys.argv[0] = target
runpy.run_path(target, run_name="__main__")
