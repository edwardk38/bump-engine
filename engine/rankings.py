"""League-wide pitcher rankings: percentiles and ranks for every season stat.

Built standalone so it can power the Deep-Dive stat boxes now and a
Leaderboards page later. One league-wide fetch per run (cached), never a
request per pitcher.

Percentiles are expressed as "goodness": higher is always better, so
lower-is-better stats are inverted. Counting stats that reward volume (K, IP)
rank on the count itself; walks and homers rank on their per-9 rate, so a
pitcher isn't credited for having thrown fewer innings.
"""

from functools import lru_cache

from engine.api import dig, get_json
from engine.pitchers import ip_to_float, to_float

# ---- Qualified-starter gate (tunable) ------------------------------------- #
# The ranked population is STARTERS ONLY. Relievers in the pool would drag
# every percentile around — a starter's 3.80 ERA means something different
# against 170 starters than against 650 arms working one inning at a time.
# All three conditions must pass.
QUALIFY_MIN_GS = 10          # games started
QUALIFY_START_SHARE = 0.5    # starts as a share of appearances — fences out
                             # relievers, swing men and openers
QUALIFY_MIN_IP = 70.0        # secondary sample-size floor

# ---- FIP ------------------------------------------------------------------ #
# FIP = (13*HR + 3*(BB+HBP) - 2*K) / IP + cFIP, where cFIP is solved from
# league totals so that league FIP lands on league ERA.
FIP_HR_WEIGHT = 13
FIP_BB_WEIGHT = 3
FIP_K_WEIGHT = 2
FIP_CONSTANT_FALLBACK = 3.10   # used only if the league totals fetch fails

PLAYER_POOL = "All"     # our own gate is stricter than the API's "Qualified"
POOL_LIMIT = 2000


class Stat:
    """One rankable stat: what to display, and what to rank on."""

    def __init__(self, key, label, higher_better, rank_on=None):
        self.key = key
        self.label = label
        self.higher_better = higher_better
        self.rank_on = rank_on or key   # metric the percentile/rank uses


# Display order for the Deep-Dive stat boxes.
STATS = [
    Stat("era",     "ERA",  higher_better=False),
    Stat("k_per_9", "K/9",  higher_better=True),
    Stat("ip",      "IP",   higher_better=True),
    Stat("k",       "K",    higher_better=True),
    Stat("bb",      "BB",   higher_better=False, rank_on="bb_per_9"),
    Stat("bb_per_9", "BB/9", higher_better=False),
    Stat("hr",      "HR",   higher_better=False, rank_on="hr_per_9"),
    Stat("fip",     "FIP",  higher_better=False),
]
# Ranked but never shown as a matchup tile. STATS is the tile contract — adding
# to it would put an extra box on every Deep-Dive card — so extras live here and
# are ranked all the same.
EXTRA_STATS = [
    Stat("avg", "AVG", higher_better=False),   # opponent batting average
]

RANKABLE = STATS + EXTRA_STATS
STAT_BY_KEY = {s.key: s for s in RANKABLE}


# --------------------------------------------------------------------------- #
# League totals -> FIP constant
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=4)
def league_totals(season) -> dict:
    """Summed pitching totals across all 30 clubs."""
    js = get_json("/teams/stats", {"stats": "season", "group": "pitching",
                                   "season": season, "sportIds": 1})
    tot = {"ip": 0.0, "hr": 0.0, "bb": 0.0, "hbp": 0.0, "k": 0.0, "er": 0.0}
    for sp in dig(js, "stats", 0, "splits", default=[]):
        st = sp.get("stat", {})
        # Innings come as '1199.2' meaning 1199 and 2/3 — never a plain float().
        tot["ip"] += ip_to_float(st.get("inningsPitched"))
        tot["hr"] += float(st.get("homeRuns") or 0)
        tot["bb"] += float(st.get("baseOnBalls") or 0)
        tot["hbp"] += float(st.get("hitByPitch") or 0)
        tot["k"] += float(st.get("strikeOuts") or 0)
        tot["er"] += float(st.get("earnedRuns") or 0)
    return tot


@lru_cache(maxsize=4)
def fip_constant(season) -> float:
    """Solve cFIP from league totals so league FIP ~= league ERA."""
    t = league_totals(season)
    if not t["ip"]:
        return FIP_CONSTANT_FALLBACK
    league_era = 9 * t["er"] / t["ip"]
    raw = (FIP_HR_WEIGHT * t["hr"]
           + FIP_BB_WEIGHT * (t["bb"] + t["hbp"])
           - FIP_K_WEIGHT * t["k"]) / t["ip"]
    return round(league_era - raw, 3)


def fip(hr, bb, hbp, k, ip, constant) -> float | None:
    if not ip:
        return None
    raw = (FIP_HR_WEIGHT * hr + FIP_BB_WEIGHT * (bb + hbp) - FIP_K_WEIGHT * k) / ip
    return round(raw + constant, 2)


# --------------------------------------------------------------------------- #
# The league-wide pull
# --------------------------------------------------------------------------- #
def is_qualified_starter(gs, gp, ip) -> bool:
    """Starters only: enough starts, mostly starting, enough innings."""
    return (gs >= QUALIFY_MIN_GS
            and gs >= QUALIFY_START_SHARE * gp
            and ip >= QUALIFY_MIN_IP)


def _record(split, constant) -> dict | None:
    """One pitcher's season metrics from a /stats split row."""
    pid = dig(split, "player", "id")
    if pid is None:
        return None
    st = split.get("stat", {})

    ip_true = ip_to_float(st.get("inningsPitched"))       # 151.2 -> 151.667
    ip_display = to_float(st.get("inningsPitched"))       # 151.2, as shown
    k = int(st.get("strikeOuts") or 0)
    bb = int(st.get("baseOnBalls") or 0)
    hbp = int(st.get("hitByPitch") or 0)
    hr = int(st.get("homeRuns") or 0)
    gs = int(st.get("gamesStarted") or 0)
    gp = int(st.get("gamesPlayed") or 0)

    return {
        "pitcher_id": str(pid),
        "name": dig(split, "player", "fullName", default=""),
        "league": dig(split, "league", "name"),
        "team_id": dig(split, "team", "id"),
        "games_started": gs,
        "games_played": gp,
        "ip_true": ip_true,
        # Displayed values
        "era": to_float(st.get("era")),
        "k_per_9": to_float(st.get("strikeoutsPer9Inn")),
        "ip": ip_display,
        "k": k,
        "bb": bb,
        "bb_per_9": to_float(st.get("walksPer9Inn")),
        "hr": hr,
        "avg": to_float(st.get("avg")),
        "fip": fip(hr, bb, hbp, k, ip_true, constant),
        # Rank-only metrics
        "hr_per_9": round(9 * hr / ip_true, 2) if ip_true else None,
        "qualified": is_qualified_starter(gs, gp, ip_true),
    }


def _rank_value(rec, stat):
    """The number this stat ranks on — the rate for BB/HR, true IP for IP."""
    if stat.key == "ip":
        return rec["ip_true"]
    return rec[stat.rank_on]


def _percentile(sorted_values, v, higher_better) -> int | None:
    """Share of the population this value is at least as good as (ties at half)."""
    if v is None or not sorted_values:
        return None
    n = len(sorted_values)
    if higher_better:
        worse = sum(1 for x in sorted_values if x < v)
    else:
        worse = sum(1 for x in sorted_values if x > v)
    ties = sum(1 for x in sorted_values if x == v)
    return round(100 * (worse + 0.5 * ties) / n)


def _ranks(records, stat) -> dict:
    """pitcher_id -> competition rank (1 = best, ties share a rank)."""
    vals = [(r["pitcher_id"], _rank_value(r, stat)) for r in records]
    vals = [(pid, v) for pid, v in vals if v is not None]
    vals.sort(key=lambda pv: pv[1], reverse=stat.higher_better)

    out, prev, prev_rank = {}, object(), 0
    for i, (pid, v) in enumerate(vals, start=1):
        if v != prev:
            prev_rank, prev = i, v
        out[pid] = prev_rank
    return out


class Table:
    """Every pitcher's stat values with percentiles and ranks attached."""

    def __init__(self, season):
        self.season = season
        self.fip_constant = fip_constant(season)

        js = get_json("/stats", {"stats": "season", "group": "pitching",
                                 "season": season, "sportId": 1,
                                 "playerPool": PLAYER_POOL, "limit": POOL_LIMIT})
        splits = dig(js, "stats", 0, "splits", default=[])

        # A traded pitcher can appear once per team; keep his fullest line.
        by_id = {}
        for sp in splits:
            rec = _record(sp, self.fip_constant)
            if rec and rec["ip_true"] >= by_id.get(rec["pitcher_id"], {}).get("ip_true", -1):
                by_id[rec["pitcher_id"]] = rec
        self.records = by_id

        self.qualified = [r for r in by_id.values() if r["qualified"]]
        self.leagues = sorted({r["league"] for r in self.qualified if r["league"]})

        # Precompute per stat: the sorted qualified population, MLB ranks, and
        # a rank map per league. Built once, reused by every matchup today.
        self._pop, self._mlb_rank, self._league_rank = {}, {}, {}
        for stat in RANKABLE:
            vals = [_rank_value(r, stat) for r in self.qualified]
            self._pop[stat.key] = sorted(v for v in vals if v is not None)
            self._mlb_rank[stat.key] = _ranks(self.qualified, stat)
            self._league_rank[stat.key] = {
                lg: _ranks([r for r in self.qualified if r["league"] == lg], stat)
                for lg in self.leagues
            }

    def percentile(self, stat_key, value) -> int | None:
        """Place any value against the qualified population, in or out of it."""
        stat = STAT_BY_KEY[stat_key]
        return _percentile(self._pop[stat.key], value, stat.higher_better)

    def row(self, pitcher_id) -> dict | None:
        return self.records.get(str(pitcher_id))

    def stat_line(self, pitcher_id, stat_key) -> dict | None:
        """{value, percentile, league, league_rank, mlb_rank} for one stat.

        Percentile is always present when the value is. Ranks are present only
        for pitchers inside the qualified population — an unqualified arm is
        placed on the distribution but is not ranked against it.
        """
        rec = self.row(pitcher_id)
        if rec is None:
            return None
        stat = STAT_BY_KEY[stat_key]
        pid = rec["pitcher_id"]

        league_rank = mlb_rank = None
        if rec["qualified"]:
            mlb_rank = self._mlb_rank[stat.key].get(pid)
            league_rank = self._league_rank[stat.key].get(rec["league"], {}).get(pid)

        return {
            "value": rec[stat.key],
            "percentile": self.percentile(stat.key, _rank_value(rec, stat)),
            "league": rec["league"],
            "league_rank": league_rank,
            "mlb_rank": mlb_rank,
        }

    def leaderboard(self, stat_key, league=None, n=None) -> list[tuple]:
        """[(rank, record)] best-first for one slice of the qualified pool.

        `league` None ranks the whole pool, "AL"/"NL" that league only. Ranks
        come from the maps built above, so each slice restarts at 1 and ties
        share a rank — no re-ranking here.
        """
        stat = STAT_BY_KEY[stat_key]
        if league is None:
            ranks = self._mlb_rank[stat.key]
            pool = self.qualified
        else:
            ranks = self._league_rank[stat.key].get(league, {})
            pool = [r for r in self.qualified if r["league"] == league]

        rows = [(ranks[r["pitcher_id"]], r) for r in pool
                if r["pitcher_id"] in ranks and _rank_value(r, stat) is not None]
        rows.sort(key=lambda pair: pair[0])
        return rows[:n] if n else rows


@lru_cache(maxsize=4)
def table(season) -> Table:
    """The league table for a season, built once per run."""
    return Table(season)
