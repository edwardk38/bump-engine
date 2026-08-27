#!/usr/bin/env python3
"""Validation log: what the starters actually did.

For a given date, pulls every FINAL game and records each team's starting
pitcher (the first arm used — an opener counts, which is the point: this
reflects reality, not the pre-game projection) and his strikeout total.

Appends to data/actual_ks.csv so the file builds up day over day. This is the
ground truth the slate's reads and form tags get checked against.

Usage:
  python -m engine.log_actuals                # yesterday (US/Eastern)
  python -m engine.log_actuals 2026-08-26     # a specific date
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.api import ET, dig, get_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "actual_ks.csv"
COLUMNS = ["date", "matchup", "team", "starter", "strikeouts"]


def target_date(argv_date=None) -> str:
    """Defaults to yesterday in US/Eastern — the last fully finished slate."""
    if argv_date:
        return argv_date
    return (datetime.now(ET).date() - timedelta(days=1)).isoformat()


def starters_from_boxscore(game_pk) -> list[dict]:
    """One row per starting pitcher in a single finished game."""
    js = get_json(f"/game/{game_pk}/boxscore")
    if not js:
        return []

    rows = []
    for side in ("away", "home"):
        team = dig(js, "teams", side, default={})
        pitcher_ids = team.get("pitchers", [])
        if not pitcher_ids:
            continue  # no pitchers recorded yet
        starter_id = pitcher_ids[0]
        player = dig(team, "players", f"ID{starter_id}", default={})
        rows.append({
            "team": dig(team, "team", "name", default=""),
            "starter": dig(player, "person", "fullName", default=""),
            "strikeouts": int(dig(player, "stats", "pitching", "strikeOuts", default=0) or 0),
        })
    return rows


def compile_day(date: str) -> list[dict]:
    js = get_json("/schedule", {"sportId": 1, "date": date})
    games = dig(js, "dates", 0, "games", default=[])

    results = []
    for g in games:
        # Only completed games have final strikeout numbers.
        if dig(g, "status", "abstractGameState") != "Final":
            continue

        matchup = (f"{dig(g, 'teams', 'away', 'team', 'name', default='')} @ "
                   f"{dig(g, 'teams', 'home', 'team', 'name', default='')}")
        # Doubleheaders come through as separate games with game numbers.
        if g.get("doubleHeader") in ("Y", "S") and g.get("gameNumber"):
            matchup += f" (G{g['gameNumber']})"

        for row in starters_from_boxscore(g.get("gamePk")):
            row["date"] = date
            row["matchup"] = matchup
            results.append(row)
    return results


def already_logged(date: str) -> bool:
    """Keep the log idempotent — a re-run shouldn't duplicate a day."""
    if not CSV_PATH.exists():
        return False
    with CSV_PATH.open(newline="") as f:
        return any(row.get("date") == date for row in csv.DictReader(f))


def write_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in COLUMNS})


def main() -> None:
    date = target_date(sys.argv[1] if len(sys.argv) > 1 else None)
    if already_logged(date):
        print(f"{date}: already in {CSV_PATH.name}, skipping", file=sys.stderr)
        return

    rows = compile_day(date)
    if not rows:
        print(f"{date}: no final games found", file=sys.stderr)
        return

    write_csv(rows)
    print(f"{date}: appended {len(rows)} starters to {CSV_PATH.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
