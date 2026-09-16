"""Today's slate: schedule fetch plus assembly into the JSON contract."""

from datetime import datetime
from functools import lru_cache

from engine.api import ET, code_for, dig, get_json
from engine.notes import form_tag, pitcher_notes
from engine.pitchers import (game_log_rows, gamelog_starts, name_display, pitcher_season,
                             pitcher_vshand)


SLATE_LAST_STARTS = 4   # game-log rows per starter on the slate card

# Home ballpark by team abbreviation, used only when the schedule does not name
# a venue. The schedule wins: ballparks get renamed and teams move (Tampa Bay
# played 2025 at Steinbrenner Field), and a neutral-site game is not played at
# the home team's park at all. Aliases cover both spellings the API has used for
# Arizona and the White Sox.
BALLPARKS = {
    "ARI": "Chase Field",
    "AZ": "Chase Field",
    "ATL": "Truist Park",
    "BAL": "Oriole Park at Camden Yards",
    "BOS": "Fenway Park",
    "CHC": "Wrigley Field",
    "CWS": "Rate Field",
    "CHW": "Rate Field",
    "CIN": "Great American Ball Park",
    "CLE": "Progressive Field",
    "COL": "Coors Field",
    "DET": "Comerica Park",
    "HOU": "Daikin Park",
    "KC": "Kauffman Stadium",
    "LAA": "Angel Stadium",
    "LAD": "Dodger Stadium",
    "MIA": "loanDepot park",
    "MIL": "American Family Field",
    "MIN": "Target Field",
    "NYM": "Citi Field",
    "NYY": "Yankee Stadium",
    "ATH": "Sutter Health Park",
    "PHI": "Citizens Bank Park",
    "PIT": "PNC Park",
    "SD": "Petco Park",
    "SF": "Oracle Park",
    "SEA": "T-Mobile Park",
    "STL": "Busch Stadium",
    "TB": "George M. Steinbrenner Field",
    "TEX": "Globe Life Field",
    "TOR": "Rogers Centre",
    "WSH": "Nationals Park",
}


def venue_for(api_venue, home_abbr) -> str:
    """The venue the schedule reports, falling back to the home team's park."""
    return api_venue or BALLPARKS.get((home_abbr or "").upper()) or ""


def target_date(argv_date=None) -> str:
    """The date to build, defaulting to today in US/Eastern."""
    return argv_date or datetime.now(ET).date().isoformat()


def date_display(date: str) -> str:
    """'2026-08-27' -> 'Thursday, Aug 27'."""
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return date
    return f"{d.strftime('%A, %b')} {d.day}"


def time_display(iso_utc: str) -> str:
    """UTC game time -> '1:05 PM' in Eastern."""
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(ET)
    except (ValueError, TypeError, AttributeError):
        return ""
    return f"{dt.strftime('%I').lstrip('0')}:{dt.strftime('%M %p')}"


@lru_cache(maxsize=4)
def todays_games(date: str) -> list[dict]:
    """Raw-ish schedule rows for `date`, with probable starters hydrated."""
    js = get_json("/schedule", {"sportId": 1, "date": date,
                                "hydrate": "probablePitcher"})
    games = dig(js, "dates", 0, "games", default=[])

    out = []
    for g in games:
        a = dig(g, "teams", "away", default={})
        h = dig(g, "teams", "home", default={})
        out.append({
            "start_utc": g.get("gameDate", ""),
            "venue": dig(g, "venue", "name", default=""),
            "game_number": g.get("gameNumber"),
            "doubleheader": g.get("doubleHeader"),
            "away_name": dig(a, "team", "name", default=""),
            "home_name": dig(h, "team", "name", default=""),
            "away_id": dig(a, "team", "id"),
            "home_id": dig(h, "team", "id"),
            "away_abbr": code_for(dig(a, "team", "id"), dig(a, "team", "name")),
            "home_abbr": code_for(dig(h, "team", "id"), dig(h, "team", "name")),
            "away_pitcher": a.get("probablePitcher"),
            "home_pitcher": h.get("probablePitcher"),
        })
    return out


def game_id(date: str, g: dict) -> str:
    """'2026-08-27-COL-WSH', with '-G2' appended for the nightcap."""
    gid = f"{date}-{g['away_abbr']}-{g['home_abbr']}"
    if g.get("doubleheader") in ("Y", "S") and (g.get("game_number") or 1) > 1:
        gid += f"-G{g['game_number']}"
    return gid


def season_read(prof: dict) -> str:
    """Fallback 'read' when a pitcher generates no notes."""
    if prof.get("era") is None:
        return "No season line posted yet."
    bits = [f"{prof['era']} ERA"]
    if prof.get("k_per_9") is not None:
        bits.append(f"{prof['k_per_9']} K/9")
    line = " with ".join(bits)
    if prof.get("ip"):
        return f"{line} over {prof['ip']} innings this season."
    return f"{line} this season."


def build_starter(pitcher, team_abbr, season, date) -> dict:
    """One side of a matchup. A TBD probable is data, not an error."""
    if not pitcher or not pitcher.get("id"):
        return {"tbd": True, "pitcher_id": None, "name_display": None,
                "name_full": None, "throws": None, "team_abbr": team_abbr,
                "stats": None, "form_tag": None, "read": None, "last_4": None}

    pid = pitcher["id"]
    # Exclude a start dated today: the build can run while a game is live.
    starts = gamelog_starts(pid, season, exclude_date=date)
    prof = pitcher_season(pid, season)
    vshand = pitcher_vshand(pid, season)
    tag = form_tag(starts, prof["era"], as_of=date)
    notes = pitcher_notes(starts, prof, vshand, season, tag, as_of=date)

    return {
        "tbd": False,
        "pitcher_id": str(pid),
        "name_display": name_display(pitcher.get("fullName", "")),
        "name_full": pitcher.get("fullName") or None,
        "throws": prof["throws"] or None,
        "team_abbr": team_abbr,
        # ip is the same season figure the Deep-Dive tile shows, in baseball
        # notation (151.2 = 151 and 2/3), so the two views can't disagree.
        "stats": {"era": prof["era"], "k_per_9": prof["k_per_9"],
                  "ip": prof["ip"], "k": prof["k"]},
        "form_tag": tag,
        "read": notes[0] if notes else season_read(prof),
        # Same rows and order as the Deep-Dive table, newest first. `starts`
        # already excludes today, so a live game never shows up here.
        "last_4": game_log_rows(starts, SLATE_LAST_STARTS),
    }


def build_slate(date: str) -> dict:
    """The full public/slate/today.json payload."""
    season = int(date[:4])
    games = []
    for g in todays_games(date):
        games.append({
            "game_id": game_id(date, g),
            "away_team": g["away_name"],
            "home_team": g["home_name"],
            "away_abbr": g["away_abbr"],
            "home_abbr": g["home_abbr"],
            "start_time_display": time_display(g["start_utc"]),
            "start_time_utc": g["start_utc"],
            "venue": venue_for(g.get("venue"), g["home_abbr"]),
            "starters": {
                "away": build_starter(g["away_pitcher"], g["away_abbr"], season, date),
                "home": build_starter(g["home_pitcher"], g["home_abbr"], season, date),
            },
        })
    return {
        "date": date,
        "date_display": date_display(date),
        "game_count": len(games),
        "games": games,
    }
