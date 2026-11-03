#!/usr/bin/env python3
"""Create the SQLite database from data/schema.sql (idempotent)."""
import _path  # noqa: F401
from research.config import load_config, resolve
from research.db import connect

cfg = load_config()
p = resolve(cfg, cfg["settings"]["database_path"])
connect(p).close()
print(f"Database ready: {p}")
