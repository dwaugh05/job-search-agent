"""Rubric regression test.

The rubric is meant to evolve as Doran gives feedback. That is also the risk: a
learned rule added to fix one bad match can quietly wreck scoring everywhere
else. These five anchors pin both ends of the pass band, so drift is caught
immediately instead of silently corrupting months of scans.

Calibration anchors live in ref-docs/ and are never written into the postings
table -- they must not leak into a real scan report.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from . import config

SCORES_PATH = config.DATA_DIR / "calibration-scores.json"
QUEUE_PATH = config.DATA_DIR / "calibration-queue.md"

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def load_anchor_docs() -> dict[str, dict[str, Any]]:
    """Read every anchor markdown file keyed by its frontmatter `key`."""
    docs: dict[str, dict[str, Any]] = {}
    for folder in ("golden", "anti-examples"):
        directory = config.REF_DIR / folder
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            match = _FRONTMATTER.match(raw)
            if not match:
                continue
            meta = yaml.safe_load(match.group(1)) or {}
            key = meta.get("key")
            if key:
                docs[key] = {"meta": meta, "body": match.group(2), "path": path}
    return docs


def render_queue() -> Path:
    """Emit the calibration scoring queue."""
    anchors = config.scoring().get("calibration_anchors", [])
    docs = load_anchor_docs()

    lines = [
        "# Calibration queue",
        "",
        "Score each anchor with the CURRENT rubric, exactly as you would a real",
        "posting -- load `rubric/rubric-A-G.md` and `rubric/learned-rules.md` first,",
        "and do not look at the expected band while scoring.",
        "",
        "Score the RUBRIC ONLY. Do not add the connection bump from",
        "`config/connections.yml`, even if the anchor's company is on that list --",
        "several anchors are real companies, and a silent +1 here would read as",
        "rubric drift when it is nothing of the kind.",
        "",
        "Write results to `data/calibration-scores.json`:",
        "",
        "```json",
        json.dumps(
            {
                "rubric_version": str(config.scoring().get("version", 1)),
                "scores": {a["key"]: {"weighted_score": 0.0, "dimension_scores": {}}
                           for a in anchors},
            },
            indent=2,
        ),
        "```",
        "",
        "Then run `python cli.py calibrate --check`.",
        "",
        "---",
        "",
    ]

    for anchor in anchors:
        key = anchor["key"]
        doc = docs.get(key)
        lines.append(f"## {anchor['label']}  (`{key}`)")
        lines.append("")
        if not doc:
            lines.append(
                f"**MISSING** - no anchor document found for `{key}`. "
                f"Expected a markdown file in ref-docs/golden or ref-docs/anti-examples "
                f"with `key: {key}` in its frontmatter."
            )
            lines.append("")
            continue
        lines.append(doc["body"].strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    config.ensure_dirs()
    QUEUE_PATH.write_text("\n".join(lines), encoding="utf-8")
    return QUEUE_PATH


def check() -> int:
    """Compare recorded anchor scores against their asserted bands."""
    anchors = config.scoring().get("calibration_anchors", [])
    if not SCORES_PATH.exists():
        print(f"No {SCORES_PATH.name}. Run `python cli.py calibrate` first, "
              "score the anchors, then re-run with --check.")
        return 1

    payload = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
    scores = payload.get("scores", {})

    failures = 0
    missing = 0
    print(f"Rubric version {payload.get('rubric_version', '?')} "
          f"(config says {config.scoring().get('version')})\n")
    print(f"{'anchor':46} {'score':>6}  {'band':>12}   result")
    print("-" * 84)

    for anchor in anchors:
        key = anchor["key"]
        low = float(anchor["expect_min"])
        high = float(anchor["expect_max"])
        entry = scores.get(key)
        if not entry or entry.get("weighted_score") in (None, 0, 0.0):
            print(f"{anchor['label'][:46]:46} {'--':>6}  {low:.1f}-{high:.1f}   NOT SCORED")
            missing += 1
            continue
        value = float(entry["weighted_score"])
        ok = low <= value <= high
        verdict = "pass" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"{anchor['label'][:46]:46} {value:6.2f}  {low:.1f}-{high:.1f}   {verdict}"
              + ("" if ok else f"   <- {'too high' if value > high else 'too low'}"))

    print()
    if missing:
        print(f"{missing} anchor(s) not scored yet.")
    if failures:
        print(f"CALIBRATION FAILED: {failures} anchor(s) outside their band.")
        print("The rubric has drifted. Fix it before trusting any scan.")
        return 1
    if missing:
        return 1
    print("CALIBRATION PASSED - all anchors inside their bands.")
    return 0


def run_calibration(*, check_only: bool = False) -> int:
    if check_only:
        return check()
    path = render_queue()
    anchors = config.scoring().get("calibration_anchors", [])
    docs = load_anchor_docs()
    found = sum(1 for a in anchors if a["key"] in docs)
    print(f"Calibration queue -> {path}")
    print(f"{found}/{len(anchors)} anchor documents found.")
    if found < len(anchors):
        missing = [a["key"] for a in anchors if a["key"] not in docs]
        print(f"Missing anchor docs: {', '.join(missing)}")
    print("\nScore them, write data/calibration-scores.json, "
          "then run `python cli.py calibrate --check`.")
    return 0
