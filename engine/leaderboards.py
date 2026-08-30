"""Leaderboards JSON — every category x league slice, precomputed.

All ranking comes from engine/rankings.py: the same starters-only qualified
pool, the same competition ranks, the same per-league maps used by the
Deep-Dive tiles. Nothing here re-sorts or re-ranks; it assembles and adds the
display bar.
"""

from engine.api import code_for, get_json
from engine.pitchers import HAND_LABEL, name_display
from engine.rankings import STAT_BY_KEY, table
from engine.slate import date_display

TOP_N = 40          # rows per slice; the frontend shows a chunk with "show all"
PEOPLE_CHUNK = 100  # ids per /people call


class Category:
    def __init__(self, key, label, stat_key, explainer):
        self.key = key
        self.label = label
        self.stat_key = stat_key
        self.explainer = explainer


CATEGORIES = [
    Category("most_strikeouts", "Most strikeouts", "k",
             "Total strikeouts this season — a volume number, so it rewards "
             "staying healthy and pitching deep as much as missing bats."),
    Category("hardest_to_hit", "Hardest to hit", "avg",
             "Opponent batting average — how often hitters actually get a hit "
             "off him."),
    Category("best_control", "Best control", "bb_per_9",
             "Walks per nine innings — who gives up the fewest free passes."),
    Category("workhorses", "Workhorses", "ip",
             "Innings pitched — who keeps taking the ball and working deep "
             "into games."),
    Category("lowest_era", "Lowest ERA", "era",
             "Earned runs allowed per nine innings — the classic "
             "run-prevention number."),
    Category("fip", "FIP", "fip",
             "FIP — a truer read on pitching skill; lower is better."),
]

# JSON key -> the league value in the rankings records (None = whole pool)
SLICES = {"all": None, "al": "AL", "nl": "NL"}


def throws_map(pitcher_ids) -> dict:
    """pitcher_id -> 'RHP'/'LHP', in batched calls rather than one per arm."""
    out = {}
    ids = list(pitcher_ids)
    for i in range(0, len(ids), PEOPLE_CHUNK):
        chunk = ids[i:i + PEOPLE_CHUNK]
        js = get_json("/people", {"personIds": ",".join(chunk)})
        for p in (js or {}).get("people", []):
            code = (p.get("pitchHand") or {}).get("code", "")
            out[str(p.get("id"))] = HAND_LABEL.get(code) or None
    return out


def bar_pct(value, leader, higher_better) -> int | None:
    """0-100 bar where the slice leader is always 100.

    Lower-is-better categories invert the ratio, so the best ERA still draws
    the longest bar rather than the shortest.
    """
    if value is None or leader is None:
        return None
    try:
        pct = (value / leader) if higher_better else (leader / value)
    except ZeroDivisionError:
        return 100 if value == leader else None
    return max(0, min(100, round(100 * pct)))


def rows_for(tbl, category, league, hands) -> list[dict]:
    stat = STAT_BY_KEY[category.stat_key]
    ranked = tbl.leaderboard(category.stat_key, league, TOP_N)
    leader = ranked[0][1][stat.key] if ranked else None

    out = []
    for rank, rec in ranked:
        pid = rec["pitcher_id"]
        out.append({
            "rank": rank,
            "pitcher_id": pid,
            "name_display": name_display(rec["name"]),
            "throws": hands.get(pid),
            "team_abbr": code_for(rec["team_id"], None) or None,
            "value": rec[stat.key],
            "bar_pct": bar_pct(rec[stat.key], leader, stat.higher_better),
        })
    return out


def build_leaderboards(date: str) -> dict:
    """The full public/leaderboards.json payload."""
    season = int(date[:4])
    tbl = table(season)
    hands = throws_map(r["pitcher_id"] for r in tbl.qualified)

    categories = []
    for cat in CATEGORIES:
        stat = STAT_BY_KEY[cat.stat_key]
        categories.append({
            "key": cat.key,
            "label": cat.label,
            "explainer": cat.explainer,
            "lower_is_better": not stat.higher_better,
            "leagues": {name: rows_for(tbl, cat, lg, hands)
                        for name, lg in SLICES.items()},
        })

    return {
        "season": str(season),
        "date_display": date_display(date),
        "categories": categories,
    }
