"""Auto-generated scouting notes and the form tag.

Every threshold is a named constant at the top — tune them here, the logic
below reads them by name.
"""

from engine.api import team_results_map
from engine.pitchers import clean_avg, format_ip

# ---- Form tag: last-N ERA vs season ERA ----------------------------------- #
FORM_WINDOW = 4         # starts in the recency window
FORM_MIN_STARTS = 3     # fewer starts than this -> "steady" (not enough signal)
HOT_ERA_DELTA = 1.00    # last-4 ERA this much BELOW season ERA -> "hot"
COLD_ERA_DELTA = 1.25   # last-4 ERA this much ABOVE season ERA -> "cold"
HOT_ERA_ABS = 3.00      # ...or last-4 ERA at/under this, regardless of season
COLD_ERA_ABS = 5.50     # ...or last-4 ERA at/over this

# ---- Note thresholds ------------------------------------------------------ #
BAD_START_ER = 4        # earned runs that make a start a "bad" one
BAD_START_MIN = 3       # this many bad starts in the window -> cold note
WORKHORSE_P90 = 6       # 90+ pitches in this many of last 10 -> "workhorse"
DURABLE_P80 = 8         # 80+ pitches in this many of last 10 -> "durable"
DEEP_5IP = 8            # 5+ IP in this many of last 10 -> "works into the 6th"
K9_MISSES_BATS = 9.0    # season K/9 at/above this -> "misses bats"
HOT_ERA_LAST4 = 2.75    # ERA over last 4 starts at/below this -> "rolling"
DEEP6_LAST6 = 5         # 6+ IP in this many of last 6 -> "going deep"
TEAM_WINS_LAST10 = 7    # team won this many of last 10 starts -> note
KSTREAK_MIN = 5         # 5+ K in each of this many straight starts -> streak
TOUGH_SIDE_BA = 0.220   # opp BA at/below this (with sample) -> "tough on <side>"
TOUGH_SIDE_MIN_AB = 60

MAX_NOTES = 4

WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
         6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def _word(n) -> str:
    return WORDS.get(n, str(n))


def window_era(starts, window=FORM_WINDOW):
    """(era, earned_runs, innings) over the last `window` starts, or None."""
    recent = starts[-window:]
    if len(recent) < FORM_MIN_STARTS:
        return None
    ip = sum(s["ip"] for s in recent)
    er = sum(s["er"] for s in recent)
    if ip <= 0:
        return None
    return (9 * er / ip, er, ip)


def form_tag(starts, season_era) -> str:
    """"hot" / "cold" / "steady" from recent ERA against the season number.

    Cold is tested first so an ugly stretch isn't masked by an already-bad
    season ERA.
    """
    w = window_era(starts)
    if w is None:
        return "steady"
    era_recent = w[0]

    if era_recent >= COLD_ERA_ABS:
        return "cold"
    if season_era is not None and era_recent - season_era >= COLD_ERA_DELTA:
        return "cold"
    if era_recent <= HOT_ERA_ABS:
        return "hot"
    if season_era is not None and season_era - era_recent >= HOT_ERA_DELTA:
        return "hot"
    return "steady"


def cold_note(starts) -> str | None:
    """One sentence for a pitcher in a bad stretch, or None if he isn't in one."""
    recent = starts[-FORM_WINDOW:]
    if len(recent) < FORM_MIN_STARTS:
        return None

    bad = sum(1 for s in recent if s["er"] >= BAD_START_ER)
    if bad >= BAD_START_MIN:
        return (f"Struggling lately — {BAD_START_ER}+ runs in "
                f"{_word(bad)} of his last {_word(len(recent))}.")

    w = window_era(starts)
    if w and w[0] >= COLD_ERA_ABS:
        era_recent, er, ip = w
        return (f"Rough stretch — {era_recent:.2f} ERA over his last "
                f"{_word(len(recent))} ({er} ER in {format_ip(ip)} IP).")
    return None


def pitcher_notes(starts, prof, vshand, season, tag) -> list[str]:
    """Short scouting sentences, most notable first, capped at MAX_NOTES.

    `tag` is this pitcher's form_tag. The cold note is gated on it so the
    frontend never renders a "steady" tag next to a struggling read.
    """
    notes = []

    # Cold form leads — a struggling arm shouldn't read like a neutral one.
    if tag == "cold":
        cold = cold_note(starts)
        if cold:
            notes.append(cold)

    last10 = starts[-10:]
    n10 = len(last10)

    # Durability / usage
    if n10 >= 5:
        p90 = sum(1 for s in last10 if s["pitches"] >= 90)
        p80 = sum(1 for s in last10 if s["pitches"] >= 80)
        deep5 = sum(1 for s in last10 if s["ip"] >= 5.0)
        if p90 >= WORKHORSE_P90:
            notes.append(f"Workhorse — 90+ pitches in {p90} of his last {n10} starts.")
        elif p80 >= DURABLE_P80:
            notes.append(f"Durable — 80+ pitches in {p80} of his last {n10} starts.")
        if deep5 >= DEEP_5IP:
            notes.append(f"Works into the 6th regularly — 5+ IP in {deep5} of his last {n10}.")

    # Misses bats
    if prof.get("k_per_9") and prof["k_per_9"] >= K9_MISSES_BATS:
        notes.append(f"Misses bats — {prof['k_per_9']} K/9, about a strikeout an inning.")

    # Hot form: run prevention over the recency window
    w = window_era(starts)
    if w and w[0] <= HOT_ERA_LAST4:
        era_recent, er, ip = w
        notes.append(f"Rolling — {era_recent:.2f} ERA over his last "
                     f"{len(starts[-FORM_WINDOW:])} ({er} ER in {format_ip(ip)} IP).")

    # Going deep lately
    last6 = starts[-6:]
    if len(last6) == 6:
        deep6 = sum(1 for s in last6 if s["ip"] >= 6.0)
        if deep6 >= DEEP6_LAST6:
            notes.append(f"Going deep — 6+ innings in {deep6} of his last 6 starts.")

    # Team record in his starts
    if last10 and last10[0]["team_id"]:
        results = team_results_map(last10[0]["team_id"], season)
        decided = [results[s["gamePk"]] for s in last10 if s["gamePk"] in results]
        wins = sum(1 for won in decided if won)
        if len(decided) >= 8 and wins >= TEAM_WINS_LAST10:
            notes.append(f"Team has won {wins} of his last {len(decided)} starts.")

    # Strikeout streak
    streak = 0
    for s in reversed(starts):
        if s["k"] >= 5:
            streak += 1
        else:
            break
    if streak >= KSTREAK_MIN:
        notes.append(f"Strikeout run — 5+ K in {streak} straight starts.")

    # Handedness
    for side, label in (("L", "left"), ("R", "right")):
        v = vshand.get(side)
        if v and v.get("avg") and v.get("ab", 0) >= TOUGH_SIDE_MIN_AB:
            try:
                if float(v["avg"]) <= TOUGH_SIDE_BA:
                    notes.append(f"Tough on {label}-handed bats — "
                                 f"{clean_avg(v['avg'])} against ({v['ab']} AB).")
            except (ValueError, TypeError):
                pass

    return notes[:MAX_NOTES]
