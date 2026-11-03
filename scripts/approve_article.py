#!/usr/bin/env python3
"""Approve an article after re-running every check. Approval is not deployment.

  python scripts/approve_article.py <slug>
  python scripts/approve_article.py <slug> --skip-build     # only if the site toolchain is unavailable
  python scripts/approve_article.py <slug> --reject "reason"
"""
import argparse
import subprocess
import sys

import _path  # noqa: F401
from research import articles as A
from research.config import load_config, resolve


def build_site(cfg) -> tuple[bool, str]:
    site = resolve(cfg, "site")
    if not (site / "node_modules").exists():
        return False, "site/node_modules is missing: run `npm install` in site/ first"
    r = subprocess.run(["npm", "run", "build"], cwd=site, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr)[-1200:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--reject", metavar="REASON")
    args = ap.parse_args()
    cfg = load_config()
    meta, body, path = A.load_article(args.slug, cfg)
    if args.reject:
        meta["status"], meta["rejected_reason"] = "REJECTED", args.reject
        path.write_text(A.dump(meta, body))
        sys.exit(f"REJECTED: {args.slug}")
    packet = A.load_packet(meta["evidence_packet"], cfg)
    steps = []
    report = A.evaluate(meta, body, packet, cfg)
    errors = [i for i in report["issues"] if i["level"] == "error"]
    facts = [i for i in errors if i["code"] not in ("metadata", "fake_freshness", "broken_link")]
    steps.append(("1. factual checks", not facts, "; ".join(i["detail"] for i in facts)))
    md = [i for i in errors if i["code"] in ("metadata", "fake_freshness")]
    steps.append(("2. required metadata", not md, "; ".join(i["detail"] for i in md)))
    steps.append(("3. duplicate content", not report["duplicates"], ", ".join(report["duplicates"])))
    links = [i for i in errors if i["code"] == "broken_link"]
    steps.append(("4. internal links", not links, "; ".join(i["detail"] for i in links)))
    gate_ok = report["gate"] != "DO_NOT_PUBLISH"
    steps.append(("   publication gate", gate_ok, "" if gate_ok else "; ".join(report["gate_reasons"])))
    if args.skip_build:
        steps.append(("5. site build", True, "SKIPPED by --skip-build"))
    elif all(ok for _, ok, _ in steps):
        ok, out = build_site(cfg)
        steps.append(("5. site build", ok, "" if ok else out))
    else:
        steps.append(("5. site build", False, "not run: earlier checks failed"))
    for name, ok, detail in steps:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    for w in [i for i in report["issues"] if i["level"] == "warning"]:
        print(f"NOTE  {w['code']}: {w['detail']}")
    if not all(ok for _, ok, _ in steps):
        sys.exit(f"\nNOT APPROVED: {args.slug} stays {meta['status']}.")
    meta.update(status="APPROVED", approved_at=A.iso(A.now_utc()), gate=report["gate"],
                gate_reasons=report["gate_reasons"], originality_score=report["originality_score"],
                quality_score=report["quality_score"])
    path.write_text(A.dump(meta, body))
    print(f"\nAPPROVED: {args.slug}. Not published and not deployed. "
          f"To publish locally: python scripts/publish_article.py {args.slug}")


if __name__ == "__main__":
    main()
