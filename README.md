# bump-engine

A JSON-first data engine for MLB starting pitchers. It reads the free MLB Stats
API, builds today's slate of probable starters, and writes plain JSON for a
frontend to render. No HTML, no email, no projections.

## Layout

```
engine/api.py          HTTP helper + cached reference lookups (team abbrs, results)
engine/pitchers.py     season line, game logs, handedness splits, small helpers
engine/notes.py        auto-notes + form tag, thresholds as named constants
engine/slate.py        schedule fetch + assembly into the JSON contract
engine/build.py        entry point — writes the JSON outputs
engine/log_actuals.py  validation log — what starters actually did
public/slate/          generated JSON (web-servable)
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

Cold is evaluated first, so a bad stretch isn't masked by an already-bad season
ERA. `read` is the top line from `pitcher_notes`, falling back to a plain
season line when a pitcher generates no notes.
