"""HTTP helpers and cached reference lookups against the MLB Stats API.

Every network call in the engine goes through `get_json`, which returns None
instead of raising. Callers degrade to null fields rather than failing the
build, so a flaky API never produces a missing output file.

No API key required. Only dependency: requests.
"""

from functools import lru_cache
from zoneinfo import ZoneInfo

import requests

API = "https://statsapi.mlb.com/api/v1"
ET = ZoneInfo("America/New_York")
TIMEOUT = 20


def get_json(path: str, params: dict | None = None) -> dict | None:
    """GET `API/path` and return parsed JSON, or None on any transport error."""
    try:
        r = requests.get(f"{API}{path}", params=params or {}, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def dig(data, *keys, default=None):
    """Walk nested dicts/lists safely: dig(js, 'stats', 0, 'splits', 0)."""
    cur = data
    for k in keys:
        try:
            cur = cur[k]
        except (KeyError, IndexError, TypeError):
            return default
    return cur if cur is not None else default


# --------------------------------------------------------------------------- #
# Reference data (cached for the life of the process)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def team_abbr_map() -> dict:
    """MLBAM team id -> official abbreviation ('COL', 'WSH', ...)."""
    js = get_json("/teams", {"sportId": 1})
    return {t["id"]: t["abbreviation"] for t in (js or {}).get("teams", []) if "id" in t}


def code_for(team_id, name) -> str:
    """Team abbreviation, falling back to the first three letters of the name."""
    return team_abbr_map().get(team_id) or (name or "")[:3].upper()


@lru_cache(maxsize=64)
def team_results_map(team_id, season) -> dict:
    """gamePk -> did this team win, for every decided regular-season game."""
    out = {}
    js = get_json("/schedule", {"sportId": 1, "teamId": team_id,
                                "season": season, "gameType": "R"})
    for d in (js or {}).get("dates", []):
        for g in d.get("games", []):
            for side in ("home", "away"):
                t = dig(g, "teams", side, default={})
                if dig(t, "team", "id") == team_id and t.get("isWinner") is not None:
                    out[g.get("gamePk")] = bool(t["isWinner"])
    return out
