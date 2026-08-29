# bump-engine

A JSON-first data engine for MLB starting pitchers. It reads the free MLB Stats
API, builds today's slate of probable starters, and writes plain JSON for a
frontend to render. No HTML, no email, no projections.

## Layout

```
engine/api.py          HTTP helper + cached reference lookups (team abbrs, results)
engine/pitchers.py     season line, game logs, handedness splits, small helpers
engine/notes.py        auto-notes + form tag, thresholds as named constants
engine/rankings.py     league-wide percentiles and ranks (also powers Leaderboards)
engine/slate.py        schedule fetch + assembly into the slate contract
engine/matchup.py      Deep-Dive matchup JSON, one file per game
engine/build.py        entry point — writes the JSON outputs
engine/log_actuals.py  validation log — what starters actually did
public/slate/          today's slate + dated archive copies
public/matchup/        one Deep-Dive file per game
public/index/          pitcher_id -> {game_id, side} lookup
data/actual_ks.csv     appended log of real strikeout totals
```

## Run it

```bash
pip install -r requirements.txt
python -m engine.build                # today (US/Eastern)
python -m engine.build 2026-08-27     # a specific date
python -m engine.log_actuals          # yesterday's finals -> data/actual_ks.csv
```

`.github/workflows/daily.yml` runs both each morning and commits the results.

One run makes one schedule fetch and one league-wide stats fetch, shared across
every game — never a request per pitcher for rankings.

## Output shape

`public/slate/today.json` (a dated copy is written alongside it):

```json
{
  "date": "2026-08-27",
  "date_display": "Thursday, Aug 27",
  "game_count": 7,
  "games": [{
    "game_id": "2026-08-27-COL-WSH",
    "away_team": "Rockies", "home_team": "Nationals",
    "away_abbr": "COL", "home_abbr": "WSH",
    "start_time_display": "1:05 PM",
    "start_time_utc": "2026-08-27T17:05:00Z",
    "starters": {
      "away": {
        "tbd": false,
        "pitcher_id": "694973",
        "name_display": "G. Hughes",
        "throws": "RHP",
        "team_abbr": "COL",
        "stats": { "era": 6.61, "k_per_9": 7.17 },
        "form_tag": "cold",
        "read": "Struggling lately — 4+ runs in three of his last four."
      },
      "home": { "...": "same shape" }
    }
  }]
}
```

Notes on the contract:

- `pitcher_id` is the MLBAM id as a string. `name_display` is first initial +
  the rest of the name (middle initials and suffixes preserved).
- `stats` are raw numbers — the frontend does the formatting. `null` when the
  API has nothing. There is no projected-strikeout figure anywhere.
- A TBD probable comes back as `{"tbd": true, ...}` with `null` stats, never an
  error. `tbd` is present on every starter so the frontend has one
  discriminator to check.
- `game_id` gets a `-G2` suffix for the second game of a doubleheader.
- Network failures degrade to `null` fields rather than failing the build.

## Tuning

`engine/notes.py` holds every threshold as a named constant. The form tag:

| Constant | Default | Meaning |
| --- | --- | --- |
| `FORM_WINDOW` | 4 | starts in the recency window |
| `FORM_MIN_STARTS` | 3 | fewer than this -> `steady` |
| `HOT_ERA_DELTA` | 1.00 | last-4 ERA this much below season ERA -> `hot` |
| `COLD_ERA_DELTA` | 1.25 | last-4 ERA this much above season ERA -> `cold` |
| `HOT_ERA_ABS` | 3.00 | ...or last-4 ERA at/under this |
| `COLD_ERA_ABS` | 5.50 | ...or last-4 ERA at/over this |
| `FORM_MAX_DAYS_BACK` | 45 | starts older than this leave the form window |

The recency cutoff matters for injured arms: without it a pitcher back from the
IL has a "last 4" spanning months, and a pre-injury start reads as current form.
Note text reports the number of starts actually used, so a trimmed window says
"his last 3".

Cold is evaluated first, so a bad stretch isn't masked by an already-bad season
ERA. `read` is the top line from `pitcher_notes`, falling back to a plain
season line when a pitcher generates no notes.

## Deep-Dive matchups

`public/matchup/{game_id}.json` per game, plus
`public/index/pitcher-to-matchup.json` mapping every starter's id to
`{"game_id": ..., "side": "away"|"home"}` so a pitcher link resolves straight to
the right matchup and tab.

Each pitcher block carries `headline_stats`, a `read` (segments, each with a
`highlight` flag — a highlighted vs-opponent sentence is a later enhancement),
eight `season_stats` tiles, handedness `splits`, and `last_starts`. TBD
probables come back as `{"tbd": true}` with null fields.

### Rankings and percentiles

`engine/rankings.py` pulls every pitcher in one league-wide call and ranks the
qualified subset:

| Constant | Default | Meaning |
| --- | --- | --- |
| `QUALIFY_MIN_GS` | 10 | games started |
| `QUALIFY_START_SHARE` | 0.5 | starts as a share of appearances |
| `QUALIFY_MIN_IP` | 40.0 | innings pitched |
| `TOP_N_LEAGUE_RANK` | 15 | rank lines show only inside this (in `matchup.py`) |

All three gate conditions must pass. The ranked population is **starters only** —
relievers would drag every percentile around, since a 3.80 ERA means something
different against 170 starters than against 650 arms working an inning at a
time. The start-share rule is what fences out swing men and openers (a pitcher
with 11 starts in 41 appearances is not a starter). Each pitcher block carries
`"qualified"` so the frontend can caveat an outsider's placement percentiles.

Percentiles are "goodness": higher is always better, so ERA, BB/9, HR/9 and FIP
are inverted. K and IP rank on volume — being a strikeout or innings leader is
genuinely good — while BB and HR rank on their per-9 *rate*, so a pitcher isn't
credited for having thrown fewer innings. The BB and BB/9 tiles therefore share
a percentile: same skill, shown two ways.

FIP is `(13*HR + 3*(BB+HBP) - 2*K) / IP + cFIP`, with `cFIP` solved from the
30-club season totals so league FIP lands on league ERA (2026: league ERA 4.158,
cFIP 3.075). Every innings figure goes through `ip_to_float` — the API sends
`"151.2"` meaning 151⅔, so a plain `float()` would quietly understate innings.

`league_rank` appears only when the pitcher is top-15 in his own league, and
`mlb_rank` only alongside it. Nothing elite is hidden: a league is a subset of
MLB, so anyone top-15 in MLB is automatically top-15 in his league. Pitchers
below the qualified gate are still *placed* on the distribution for a
percentile, but carry null ranks — they are not in the ranked population.
