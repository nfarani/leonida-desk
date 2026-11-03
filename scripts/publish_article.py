#!/usr/bin/env python3
"""Mark an APPROVED article as PUBLISHED so it appears in the built site. This is a local status
change. Deployment is a separate step and stays manual until the operator enables it.

  python scripts/publish_article.py <slug>
"""
import argparse
import sys

import _path  # noqa: F401
from research import articles as A
from research.config import load_config, resolve
from research.deploy import deploy_if_enabled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    args = ap.parse_args()
    cfg = load_config()
    meta, body, path = A.load_article(args.slug, cfg)
    if meta.get("status") != "APPROVED":
        sys.exit(f"{args.slug} is {meta.get('status')}; only an APPROVED article can be published. "
                 "Run /approve-article first.")
    now = A.iso(A.now_utc())
    meta["status"] = "PUBLISHED"
    if not meta.get("published_at"):                            # set once, never moved
        meta["published_at"] = meta["updated_at"] = now
    path.write_text(A.dump(meta, body))
    print(f"PUBLISHED locally: {args.slug} (published_at {meta['published_at']})")
    print(deploy_if_enabled(cfg, resolve(cfg, "site"), [args.slug]))


if __name__ == "__main__":
    main()
