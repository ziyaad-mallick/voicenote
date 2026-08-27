"""Export the replay eval as static JSON for the web demo.

    python evals/export_web.py            # write web/public/eval-data.json
    python evals/export_web.py --check    # exit 1 if the on-disk file is stale

Why this script exists at all, rather than the web app reading the case files:
`harness.datetime_state` classifies a reminder's datetime with
`dateutil.parser.parse(raw, fuzzy=True)`. JavaScript's `Date` is not equivalent
-- it does not resolve "next Monday", it disagrees on bare "Monday", and it is
implementation-defined on most of the prose the model actually emits. A second
parser in JS would be a second thing that can be wrong, and when the headline
number moved you would not know which of the two moved it. So every datetime
classification is computed HERE, by the real harness, and shipped as a literal
string in the data. `web/lib/score.mjs` reads `datetime_state` off the reminder
and never parses a date.

Why `now` is pinned:
`datetime_state` compares against a `now`. A relative datetime like
"next Monday 9am" is `future` today and `unparseable_or_past` a week from now,
so an unpinned export would make the published numbers drift silently -- the
site would report a different datetime accuracy every time someone rebuilt it,
with no commit to blame. `PINNED_NOW` freezes that comparison so the export is
reproducible and `--check` is meaningful.

The one thing pinning does NOT freeze: `dateparser.parse` fills unspecified
fields from the real system clock (that is dateutil's own default, and
`harness.datetime_state` deliberately mirrors reminders.py rather than inventing
a second parse). So a bare weekday still resolves relative to the real today.
Pinning `now` removes the drift this script controls; it does not claim to
remove all of it.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import config  # noqa: E402

# Absolute, not relative: this file is meant to be runnable both as
# `python evals/export_web.py` and as `python -m evals.export_web`, and a
# relative import breaks the first form.
from evals.harness import (  # noqa: E402
    Case,
    case_set_hash,
    datetime_state,
    load_cases,
    prompt_hash,
)
from evals.runner import run_case  # noqa: E402

PINNED_NOW = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

OUT_PATH = _ROOT / "web" / "public" / "eval-data.json"


def _predicted(note: dict) -> dict:
    """The note the real formatter produced, plus precomputed datetime states."""
    reminders = []
    for r in note.get("reminders") or []:
        raw = r.get("datetime")
        reminders.append(
            {
                "text": r.get("text", ""),
                "datetime": raw if raw else None,
                "datetime_state": datetime_state(raw, now=PINNED_NOW),
            }
        )
    return {
        "title": note.get("title"),
        "category": note.get("category"),
        "summary": note.get("summary"),
        "tags": note.get("tags") or [],
        "category_coerced": bool(note.get("_category_coerced")),
        "reminders": reminders,
    }


def _outcome(note: dict) -> str:
    kind = note.get("_fallback_kind")
    if kind == "transport":
        return "fallback_transport"
    if kind == "parse":
        return "fallback_parse"
    return "scored"


def _case_entry(case: Case, categories: list[str]) -> dict:
    # The REAL replay path: formatter.format_note against the recorded body,
    # exactly as evals/run.py drives it. Parsing the recorded JSON here instead
    # would bypass fence-stripping, key validation and category coercion, and
    # the demo would show a note the product never produces.
    note = run_case(case, categories, live=False)
    return {
        "id": case.id,
        "label_status": case.label_status,
        "transcript": case.transcript,
        "notes": case.notes,
        "expected": {
            "category": case.expected.get("category"),
            "reminders": [
                {
                    "text": r.get("text", ""),
                    "datetime_state": r.get("datetime_state", "future"),
                }
                for r in case.expected.get("reminders", [])
            ],
        },
        "outcome": _outcome(note),
        "predicted": _predicted(note),
        "raw_response": (case.recorded or {}).get("response"),
    }


def build() -> dict:
    # Same source the eval run uses: config.load()["categories"]. Hardcoding a
    # guess here would let the export and the eval disagree about the prompt,
    # which is precisely what prompt_sha exists to catch.
    categories = config.load()["categories"]
    cases = load_cases()
    return {
        "pinned_now": PINNED_NOW.isoformat(),
        "case_set_hash": case_set_hash(cases),
        "prompt_sha": prompt_hash(categories),
        "categories": categories,
        "cases": [_case_entry(c, categories) for c in cases],
    }


def _serialize(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="regenerate in memory and exit 1 if the committed file differs",
    )
    args = ap.parse_args()

    payload = _serialize(build())
    rel = OUT_PATH.relative_to(_ROOT)

    if args.check:
        if not OUT_PATH.exists():
            print(f"FAIL: {rel} does not exist. Run `python evals/export_web.py`.")
            return 1
        on_disk = OUT_PATH.read_text(encoding="utf-8")
        if on_disk != payload:
            print(f"FAIL: {rel} is stale. Run `python evals/export_web.py`.")
            return 1
        print(f"OK: {rel} is up to date.")
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
