"""Per-pitcher data: season line, game logs, handedness splits, small helpers.

All numbers come back as raw floats/ints (or None) — formatting is the
frontend's job. Nothing here computes a projection.
"""

from engine.api import code_for, dig, get_json

HAND_LABEL = {"L": "LHP", "R": "RHP"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def to_float(x):
    """Float, or None. The API sends '-.--' for ERA with zero innings."""
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def ip_to_float(ip) -> float:
    """'5.2' innings (5 and 2/3) -> 5.667."""
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole or 0) + (int(frac or 0) / 3)
    except (ValueError, TypeError):
        return 0.0


def format_ip(ip: float) -> str:
    """Decimal innings -> baseball notation. 11.333 -> '11.1' (11 and 1/3)."""
    outs = round(float(ip) * 3)
    return f"{outs // 3}.{outs % 3}"


def clean_avg(a) -> str:
    """'.198' style, dropping the leading zero. Used inside note text."""
    try:
        return f"{float(a):.3f}".lstrip("0") or ".000"
    except (ValueError, TypeError):
        return str(a)


def name_display(full_name: str) -> str:
    """'Gavin Hughes' -> 'G. Hughes'. Keeps middle initials and suffixes."""
    parts = (full_name or "").split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0][0]}. {' '.join(parts[1:])}"


def avg_pitches_per_start(starts) -> int | None:
    p = [s["pitches"] for s in starts if s["pitches"] > 0]
    return round(sum(p) / len(p)) if p else None


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #
def gamelog_starts(pid, season, exclude_date=None) -> list[dict]:
    """This pitcher's starts this season, oldest -> newest.

    `exclude_date` drops a start on that date — the build date, so a game that
    is live while the build runs never pollutes the recent-form window.
    """
    js = get_json(f"/people/{pid}/stats",
                  {"stats": "gameLog", "group": "pitching", "season": season})
    splits = dig(js, "stats", 0, "splits", default=[])

    starts = []
    for sp in splits:
        st = sp.get("stat", {})
        if int(st.get("gamesStarted") or 0) != 1:
            continue
        if exclude_date and sp.get("date") == exclude_date:
            continue
        opp = sp.get("opponent", {})
        starts.append({
            "gamePk": dig(sp, "game", "gamePk"),
            "date": sp.get("date", ""),
            "team_id": dig(sp, "team", "id"),
            "opp": f"{'vs' if sp.get('isHome') else '@'} {code_for(opp.get('id'), opp.get('name'))}",
            "ip_str": st.get("inningsPitched", "0.0"),
            "ip": ip_to_float(st.get("inningsPitched")),
            "k": int(st.get("strikeOuts") or 0),
            "bb": int(st.get("baseOnBalls") or 0),
            "pitches": int(st.get("numberOfPitches", st.get("pitchesThrown", 0)) or 0),
            "strikes": int(st.get("strikes") or 0),
            "hits": int(st.get("hits") or 0),
            "er": int(st.get("earnedRuns") or 0),
            "hr": int(st.get("homeRuns") or 0),
        })
    return starts


def pitcher_season(pid, season) -> dict:
    """Season profile. Every value may be None if the API is unhappy."""
    prof = {"hand": "", "throws": "", "era": None, "k_per_9": None,
            "ip": None, "k": None, "ip_per_start": None}

    people = get_json(f"/people/{pid}")
    prof["hand"] = dig(people, "people", 0, "pitchHand", "code", default="")
    prof["throws"] = HAND_LABEL.get(prof["hand"], "")

    js = get_json(f"/people/{pid}/stats",
                  {"stats": "season", "group": "pitching", "season": season})
    st = dig(js, "stats", 0, "splits", 0, "stat", default={})
    prof["era"] = to_float(st.get("era"))
    prof["k_per_9"] = to_float(st.get("strikeoutsPer9Inn"))
    prof["ip"] = to_float(st.get("inningsPitched"))
    prof["k"] = int(st.get("strikeOuts") or 0) if st else None
    gs = int(st.get("gamesStarted") or 0)
    if gs:
        prof["ip_per_start"] = round(ip_to_float(st.get("inningsPitched")) / gs, 1)
    return prof


def pitcher_vshand(pid, season) -> dict:
    """Season batting-average-against vs LHB and RHB, with at-bat samples."""
    out = {"L": None, "R": None}
    js = get_json(f"/people/{pid}/stats",
                  {"stats": "statSplits", "group": "pitching",
                   "season": season, "sitCodes": "vl,vr"})
    for sp in dig(js, "stats", 0, "splits", default=[]):
        code = dig(sp, "split", "code", default="")
        side = "L" if code == "vl" else "R" if code == "vr" else None
        if side:
            st = sp.get("stat", {})
            out[side] = {"avg": st.get("avg"), "ab": int(st.get("atBats") or 0)}
    return out
