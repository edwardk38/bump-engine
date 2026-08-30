#!/usr/bin/env python3
"""Entry point: build today's slate and write the JSON outputs.

Usage:
  python -m engine.build                # today (US/Eastern)
  python -m engine.build 2026-08-27     # a specific date

Writes:
  public/slate/today.json               the current slate (what the site reads)
  public/slate/<date>.json              a dated archive copy of the same payload
  public/matchup/<game_id>.json         one Deep-Dive file per game
  public/index/pitcher-to-matchup.json  pitcher_id -> {game_id, side}
  public/leaderboards.json              every category x league, precomputed
"""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python engine/build.py` too
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.leaderboards import build_leaderboards  # noqa: E402
from engine.matchup import build_all  # noqa: E402
from engine.slate import build_slate, target_date  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
SLATE_DIR = PUBLIC / "slate"
MATCHUP_DIR = PUBLIC / "matchup"
INDEX_DIR = PUBLIC / "index"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    date = target_date(sys.argv[1] if len(sys.argv) > 1 else None)
    slate = build_slate(date)

    write_json(SLATE_DIR / "today.json", slate)
    write_json(SLATE_DIR / f"{date}.json", slate)

    # Deep-Dive files reuse the same schedule fetch and one league-wide
    # rankings pull shared across every game.
    matchups, index = build_all(date)
    for m in matchups:
        write_json(MATCHUP_DIR / f"{m['game_id']}.json", m)
    write_json(INDEX_DIR / "pitcher-to-matchup.json", index)

    # Reuses the same league-wide rankings pull the matchups just used.
    boards = build_leaderboards(date)
    write_json(PUBLIC / "leaderboards.json", boards)

    tbd = sum(1 for g in slate["games"] for s in g["starters"].values() if s["tbd"])
    print(f"{date}: {slate['game_count']} games, {tbd} TBD starters", file=sys.stderr)
    print(f"  public/slate/today.json", file=sys.stderr)
    print(f"  public/matchup/ — {len(matchups)} files", file=sys.stderr)
    print(f"  public/index/pitcher-to-matchup.json — {len(index)} pitchers",
          file=sys.stderr)
    print(f"  public/leaderboards.json — {len(boards['categories'])} categories",
          file=sys.stderr)


if __name__ == "__main__":
    main()
