"""Load YAML config + .env. Paths are relative to the repo root."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_env(root: Path) -> None:
    env = root / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if v.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def load_config(root: Path = ROOT) -> dict:
    _load_env(root)
    cfg = {}
    for name in ("settings", "scoring", "verification", "categories", "sources", "publishing", "evergreen",
                 "games", "flags", "affiliates", "design"):
        with open(root / "config" / f"{name}.yaml") as f:
            cfg[name] = yaml.safe_load(f)
    total = sum(cfg["scoring"]["weights"].values())
    if total != 100:
        raise ValueError(f"config/scoring.yaml weights must total 100 (got {total})")
    cfg["root"] = root
    # Feature flags are the single switchboard; the gate reads the auto-publish flag from there.
    cfg["flags"] = cfg["flags"]["flags"]
    cfg["publishing"]["gate"]["auto_publish"]["enabled"] = bool(cfg["flags"]["auto_publish_enabled"])
    return cfg


def resolve(cfg: dict, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else cfg["root"] / p
