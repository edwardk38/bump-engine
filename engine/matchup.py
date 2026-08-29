"""Deep-Dive matchup JSON — one file per game.

Reuses the slate's schedule fetch, pitchers.py for the per-arm data, notes.py
for the read and the form tag, and rankings.py for the stat boxes. Nothing
here projects anything.
"""

from datetime import datetime

from engine.notes import form_tag, pitcher_notes
from engine.pitchers import (gamelog_starts, name_display, pitcher_season,
                             pitcher_vshand, to_float)
from engine.rankings import STATS, table
from engine.slate import (date_display, game_id, season_read, time_display,
                          todays_games)

# A rank line only earns its place when the pitcher is near the top of his
# league. Below that the percentile carries the story on its own.
TOP_N_LEAGUE_RANK = 15
LAST_STARTS_COUNT = 5


def is_qualified(pitcher_id, season) -> bool:
    """Is this arm inside the ranked starter population?"""
    rec = table(season).row(pitcher_id)
    return bool(rec and rec["qualified"])


def start_date_display(iso_date: str) -> str:
    """'2026-08-21' -> 'Aug 21'."""
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_date or ""
    return f"{d.strftime('%b')} {d.day}"


def gate_ranks(line: dict) -> dict:
    """Show ranks only for a top-15-in-league stat; both or neither.

    A league rank is always at least as good as the MLB rank (a league is a
    subset of MLB), so nothing elite is hidden by gating on the league number.
    """
    league_rank = line.get("league_rank")
    if league_rank is None or league_rank > TOP_N_LEAGUE_RANK:
        return {**line, "league_rank": None, "mlb_rank": None}
    return line


def season_stats(pitcher_id, prof) -> list[dict]:
    """The stat boxes, in display order. Percentile is always present."""
    tbl = table(int(prof["season"]))
    out = []
    for stat in STATS:
        line = tbl.stat_line(pitcher_id, stat.key)
        if line is None:
            # Not in the league pull at all (a debut). Fall back to what the
            # per-pitcher season line knows, placed on the distribution.
            value = prof.get(stat.key)
            line = {"value": value,
                    "percentile": tbl.percentile(stat.key, value),
                    "league": None, "league_rank": None, "mlb_rank": None}
        line = gate_ranks(line)
        out.append({"key": stat.key, "label": stat.label, **line})
    return out


def read_segments(notes, prof) -> list[dict]:
    """The read as highlightable segments.

    Every segment is plain today; the vs-opponent sentence lands here later as
    a segment with "highlight": true, without reshaping the contract.
    """
    if not notes:
        return [{"text": season_read(prof), "highlight": False}]
    return [{"text": n, "highlight": False} for n in notes]


def splits_block(vshand) -> dict:
    def side(v):
        if not v:
            return None
        return {"avg": to_float(v.get("avg")), "ab": v.get("ab")}
    return {"vs_lhb": side(vshand.get("L")), "vs_rhb": side(vshand.get("R"))}


def last_starts(starts) -> list[dict]:
    """Most recent starts, newest first."""
    recent = list(reversed(starts[-LAST_STARTS_COUNT:]))
    return [{
        "date_display": start_date_display(s["date"]),
        "opp_abbr": s["opp_abbr"],
        "is_home": s["is_home"],
        "ip": s["ip_str"],
        "h": s["hits"],
        "er": s["er"],
        "hr": s["hr"],
        "bb": s["bb"],
        "so": s["k"],
        "pitches": s["pitches"],
        "strikes": s["strikes"],
    } for s in recent]


def build_pitcher(pitcher, team_abbr, opponent_abbr, season, date) -> dict:
    """One arm's Deep-Dive block. A TBD probable is data, not an error."""
    if not pitcher or not pitcher.get("id"):
        return {"tbd": True, "pitcher_id": None, "name_display": None,
                "throws": None, "team_abbr": team_abbr,
                "opponent_abbr": opponent_abbr, "qualified": None, "form_tag": None,
                "headline_stats": None, "read": None, "season_stats": None,
                "splits": None, "last_starts": None}

    pid = pitcher["id"]
    # Same live-game guard as the slate: a start dated today is in progress.
    starts = gamelog_starts(pid, season, exclude_date=date)
    prof = pitcher_season(pid, season)
    prof["season"] = season
    vshand = pitcher_vshand(pid, season)
    tag = form_tag(starts, prof["era"], as_of=date)
    notes = pitcher_notes(starts, prof, vshand, season, tag, as_of=date)

    return {
        "tbd": False,
        "pitcher_id": str(pid),
        "name_display": name_display(pitcher.get("fullName", "")),
        "throws": prof["throws"] or None,
        "team_abbr": team_abbr,
        "opponent_abbr": opponent_abbr,
        # False = ranked-population outsider: percentiles are by placement and
        # both ranks are null, so the frontend can caveat a small sample.
        "qualified": is_qualified(pid, season),
        "form_tag": tag,
        "headline_stats": {"era": prof["era"], "k_per_9": prof["k_per_9"]},
        "read": read_segments(notes, prof),
        "season_stats": season_stats(pid, prof),
        "splits": splits_block(vshand),
        "last_starts": last_starts(starts),
    }


def build_matchup(g: dict, date: str, season: int) -> dict:
    """The full public/matchup/{game_id}.json payload for one game."""
    return {
        "game_id": game_id(date, g),
        "date_display": date_display(date),
        "start_time_display": time_display(g["start_utc"]),
        "venue": g.get("venue", ""),
        "away_team": g["away_name"],
        "home_team": g["home_name"],
        "away_abbr": g["away_abbr"],
        "home_abbr": g["home_abbr"],
        "pitchers": {
            "away": build_pitcher(g["away_pitcher"], g["away_abbr"],
                                  g["home_abbr"], season, date),
            "home": build_pitcher(g["home_pitcher"], g["home_abbr"],
                                  g["away_abbr"], season, date),
        },
    }


def build_all(date: str) -> tuple[list[dict], dict]:
    """Every matchup for `date`, plus the pitcher_id -> matchup index."""
    season = int(date[:4])
    matchups, index = [], {}
    for g in todays_games(date):
        m = build_matchup(g, date, season)
        matchups.append(m)
        for side in ("away", "home"):
            p = m["pitchers"][side]
            if not p["tbd"]:
                index[p["pitcher_id"]] = {"game_id": m["game_id"], "side": side}
    return matchups, index
