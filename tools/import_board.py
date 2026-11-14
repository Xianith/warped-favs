#!/usr/bin/env python3
"""
Turn a transcription of a Warped Tour set-time board into data/schedule.json.

The board photo is a grid: one column pair (TIME | BAND) per stage, start times only.
Claude reads the photo into a small JSON "board" file, then this script does the
error-prone parts deterministically:

  * 12h -> 24h (festival runs ~11am-11pm: bare 11 = AM, 12 = noon, 1-10 = PM)
  * fills hour-less times ("38" under a "12:" row -> 12:38) via the "hour" field
  * estimates end times (board shows starts only)
  * fuzzy-matches band names to data/lineup.json and flags anything shaky
  * merges into data/schedule.json for the given day

Board file format:
{
  "day": "sat",                      # sat | sun
  "stages": [
    {"name": "Vans Left Foot",
     "sets": [["12:10", "Escape the Fate"], ["1:05", "Story of the Year"], ...]},
    ...
  ],
  "lineup": [...]                    # optional: overrides data/lineup.json (tests only)
}

Usage:
  python3 tools/import_board.py board.json            # merge into data/schedule.json
  python3 tools/import_board.py board.json --dry-run  # print result + report only
"""
import argparse, json, re, sys, unicodedata
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SET = 40      # minutes, when the next set on the stage is far away or unknown
LAST_SET = 60         # minutes, for the final set on a stage
CHANGEOVER = 5        # minutes between a set ending and the next one starting
MIN_SET = 15


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("&", "and")
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def to_min(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m


def hhmm(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}"


def parse_time(raw, prev_min=None):
    """'1:05', '1:05 PM', '13:05', '12.38' -> minutes since midnight (24h)."""
    s = raw.strip().lower().replace(".", ":").replace(" ", "")
    m = re.fullmatch(r"(\d{1,2})(?::?(\d{2}))?(am|pm|a|p)?", s)
    if not m:
        raise ValueError(f"unreadable time {raw!r}")
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap:
        if ap.startswith("p") and h < 12: h += 12
        if ap.startswith("a") and h == 12: h = 0
    elif h <= 10:
        h += 12                       # 1-10 with no am/pm = afternoon/evening
    t = h * 60 + mi
    # A time that goes backwards on the same stage is almost always an AM/PM slip.
    if prev_min is not None and t < prev_min and t + 12 * 60 > prev_min and t + 12 * 60 < 24 * 60:
        t += 12 * 60
    return t


def best_match(name, lineup):
    n = norm(name)
    scored = []
    for b in lineup:
        bn = norm(b)
        if n == bn:
            return b, 1.0
        r = SequenceMatcher(None, n, bn).ratio()
        if n and (n in bn or bn in n):
            r = max(r, 0.85)
        scored.append((r, b))
    scored.sort(reverse=True)
    return (scored[0][1], scored[0][0]) if scored else (None, 0)


def build(board, lineup):
    out, report = [], {"matched": 0, "fuzzy": [], "unmatched": [], "notes": []}
    for stage in board["stages"]:
        rows, prev = [], None
        for raw_time, raw_band in stage["sets"]:
            try:
                t = parse_time(raw_time, prev)
            except ValueError as e:
                report["notes"].append(f"{stage['name']}: {e} ({raw_band})")
                continue
            if prev is not None and t <= prev:
                report["notes"].append(f"{stage['name']}: {raw_band} at {raw_time} is not after the previous set — check the photo")
            prev = t
            band, score = best_match(raw_band, lineup)
            if score >= 0.92:
                report["matched"] += 1
            elif score >= 0.72:
                report["fuzzy"].append(f"{raw_band!r} -> {band!r} ({score:.2f})")
            else:
                report["unmatched"].append(f"{raw_band!r} on {stage['name']} at {raw_time} (closest: {band!r} {score:.2f})")
                band = raw_band.strip()
            rows.append({"band": band, "stage": stage["name"], "start": t})
        for i, r in enumerate(rows):
            nxt = rows[i + 1]["start"] if i + 1 < len(rows) else None
            end = r["start"] + (LAST_SET if nxt is None else min(DEFAULT_SET, max(MIN_SET, nxt - r["start"] - CHANGEOVER)))
            out.append({"band": r["band"], "stage": r["stage"], "start": hhmm(r["start"]),
                        "end": hhmm(min(end, 23 * 60 + 59)), "endEstimated": True})
    seen = {}
    for e in out:
        k = norm(e["band"])
        if k in seen:
            report["notes"].append(f"{e['band']} appears twice ({seen[k]} and {e['stage']} {e['start']})")
        seen[k] = f"{e['stage']} {e['start']}"
    out.sort(key=lambda e: (to_min(e["start"]), e["stage"]))
    missing = [b for b in lineup if norm(b) not in seen]
    if missing:
        report["notes"].append(f"{len(missing)} lineup bands not on the board: " + ", ".join(missing))
    return out, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    board = json.loads(Path(args.board).read_text())
    day = board["day"]
    if "lineup" in board:
        lineup = board["lineup"]
    else:
        L = json.loads((ROOT / "data/lineup.json").read_text())
        lineup = next(d["bands"] for d in L["days"] if d["id"] == day)
    sets, report = build(board, lineup)

    print(f"{day}: {len(sets)} sets · {report['matched']} exact matches")
    for k in ("fuzzy", "unmatched", "notes"):
        for line in report[k]:
            print(f"  [{k}] {line}")
    if args.dry_run:
        print(json.dumps(sets, indent=1))
        return
    path = ROOT / "data/schedule.json"
    sched = json.loads(path.read_text())
    sched[day] = sets
    path.write_text(json.dumps(sched, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {path.relative_to(ROOT)}")
    sys.exit(1 if report["unmatched"] else 0)


if __name__ == "__main__":
    main()
