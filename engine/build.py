#!/usr/bin/env python3
"""Entry point: build today's slate and write the JSON outputs.

Usage:
  python -m engine.build                # today (US/Eastern)
  python -m engine.build 2026-08-27     # a specific date

Writes:
  public/slate/today.json         the current slate (what the site reads)
  public/slate/<date>.json        a dated archive copy of the same payload
"""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python engine/build.py` too
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.slate import build_slate, target_date  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SLATE_DIR = ROOT / "public" / "slate"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    date = target_date(sys.argv[1] if len(sys.argv) > 1 else None)
    slate = build_slate(date)

    write_json(SLATE_DIR / "today.json", slate)
    write_json(SLATE_DIR / f"{date}.json", slate)

    tbd = sum(1 for g in slate["games"] for s in g["starters"].values() if s["tbd"])
    print(f"{date}: {slate['game_count']} games, {tbd} TBD starters "
          f"-> public/slate/today.json", file=sys.stderr)


if __name__ == "__main__":
    main()
