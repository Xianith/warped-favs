# Warped Orlando 2026 — My Schedule

Static GitHub Pages site. Star favorites per day, paste set times, and get a personal schedule with conflicts flagged.

- `data/lineup.json` — full Sat/Sun lineup
- `data/favorites.json` — default favorites (overridden by stars saved in your browser)
- `data/schedule.json` — set times (`{band, stage, start, end, endEstimated}`, 24h)
- `tools/import_board.py` — turns a transcribed set-time board (`{day, stages:[{name, sets:[[time, band]]}]}`) into `schedule.json`: AM/PM inference, end-time estimates, fuzzy band matching against the lineup, and a report of anything to double-check. `--dry-run` to preview.
- `tools/tests/board-2025-sample.json` — 2025 test fixture only

**In the site:** Set Times tab → 📷 *From a photo of the board* → Read with Claude (needs an Anthropic API key, stored only in your browser) or Read on device (Tesseract OCR, rougher) → review/edit → Save. Same rules as the Python importer.

CLI workflow: photo of the board → Claude transcribes each stage column into a board JSON → `python3 tools/import_board.py board.json` → commit & push.
