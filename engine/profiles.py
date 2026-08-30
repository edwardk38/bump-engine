"""Per-pitcher profile JSON — one standalone file per starter.

This is the matchup pitcher block minus its matchup framing. It calls the very
same builder, so a pitcher's tiles, splits, notes and form tag are identical
whether you arrive from a leaderboard or from a game card. Nothing per-pitcher
is computed twice, and no new analysis happens here — the pitch-level breakdown
is a later layer.
"""

from engine.api import code_for
from engine.matchup import build_pitcher
from engine.pitchers import name_display
from engine.rankings import table
from engine.slate import todays_games

# Carried straight through from the matchup block. opponent_abbr and
# headline_stats are deliberately absent: the first is matchup-only framing, the
# second just repeats the era and k_per_9 tiles.
PROFILE_FIELDS = ("pitcher_id", "throws", "form_tag", "qualified",
                  "read", "season_stats", "splits", "last_starts")


def build_profile(pid, full_name, team_abbr, season, date) -> dict:
    """One pitcher's profile, built by the matchup builder and reshaped."""
    block = build_pitcher({"id": pid, "fullName": full_name},
                          team_abbr, None, season, date)

    profile = {
        "pitcher_id": block["pitcher_id"],
        "name_display": block["name_display"],
        "name_full": full_name or None,
        "throws": block["throws"],
        "team_abbr": team_abbr,
    }
    profile.update({k: block[k] for k in PROFILE_FIELDS if k not in profile})
    return profile


def _todays_starters(date) -> dict:
    """pitcher_id -> (full_name, team_abbr) for today's probables.

    Included even when unqualified, so a name on a matchup card always resolves
    to a profile instead of a 404.
    """
    out = {}
    for g in todays_games(date):
        for side in ("away", "home"):
            p = g.get(f"{side}_pitcher")
            if p and p.get("id"):
                out[str(p["id"])] = (p.get("fullName", ""), g[f"{side}_abbr"])
    return out


def build_all(date: str) -> list[dict]:
    """Profiles for the whole qualified pool plus today's starters."""
    season = int(date[:4])
    tbl = table(season)

    # The qualified pool first, then today's arms — the pool's team code comes
    # from its own record, today's from the schedule.
    people = {r["pitcher_id"]: (r["name"], code_for(r["team_id"], None) or None)
              for r in tbl.qualified}
    for pid, (full_name, team_abbr) in _todays_starters(date).items():
        people.setdefault(pid, (full_name, team_abbr))

    return [build_profile(pid, full_name, team_abbr, season, date)
            for pid, (full_name, team_abbr) in sorted(people.items())]
