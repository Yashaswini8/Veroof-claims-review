"""Start the VeRoof server as a detached background process (dev helper)."""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
LOG = os.path.join(os.environ.get("TEMP", "/tmp"), "opencode", "veroof-server.log")
ERR = os.path.join(os.environ.get("TEMP", "/tmp"), "opencode", "veroof-server.err.log")

flags = 0
if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
    flags |= subprocess.CREATE_NEW_PROCESS_GROUP
if hasattr(subprocess, "DETACHED_PROCESS"):
    flags |= subprocess.DETACHED_PROCESS
if hasattr(subprocess, "CREATE_NO_WINDOW"):
    flags |= subprocess.CREATE_NO_WINDOW

with open(LOG, "w", encoding="utf-8") as out, open(ERR, "w", encoding="utf-8") as err:
    proc = subprocess.Popen(
        [PYTHON, "-W", "ignore", "app.py"],
        cwd=ROOT,
        stdout=out,
        stderr=err,
        creationflags=flags,
    )
print(f"started pid={proc.pid}")