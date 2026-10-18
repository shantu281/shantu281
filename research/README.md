# Research scripts (scratch, kept for reproducibility)

Run from the repo root after `scripts/download_options.py --start 2024-09-01` and the
extra BTC index history (May 2024 on). Outputs go to `research/out/` (create it first).
They are exploratory: quick to read, not part of the bot.

| Script | What it tests |
|---|---|
| `grid.py` | GMMA seller: entry time, strike width, P&L stops |
| `control.py` | Luck test: same days and strikes, side flipped or random |
| `gfilter.py` | Movement strangle filtered or leaned by the GMMA trend |
| `stops.py` | Movement strangle with a P&L stop |
| `final.py` | Best 3 with Delta's real fees and spreads of $2.5 / $5 / $10 |
| `pm.py` | Delta portfolio margin for short options (from Delta's guide) |
| `feat.py`, `filt.py` | Greeks at entry; filters by thirds, cut-offs set on year 1 |
| `greek_grid.py` | Strike chosen by delta |
| `dstop.py` | Exit when the short leg's delta passes a limit |
| `hero.py` | Hero-zero: buy ATM to 1.5% OTM options 1-3 h before expiry |
| `cmp.py` | Summary table for trade files |
