"""Case loading, reminder matching and metric accumulation.

The whole eval is three ideas:

1. A case is a transcript plus what the note should have contained. Cases live
   in `evals/cases/*.json` and are plain data.

2. Running a case means calling the real `formatter.format_note` with the one
   network seam (`formatter.requests.post`) replaced. In replay mode the
   replacement returns a response recorded earlier; in live mode nothing is
   replaced and the real Ollama answers.

3. Scoring is corpus-level counters, not per-case scores that get averaged.
   Averaging per-case recall is undefined on the most important case in the set
   -- the one with no deadline at all, where recall is 0/0 -- and both ways of
   resolving that are wrong. Counters have no such problem: the negative case
   simply contributes to FP or to nothing.

What is deliberately dumb here: the reminder matcher. It normalizes text,
measures token overlap, and assigns greedily. A cleverer matcher would be a
second thing that can be wrong, and when the headline number moves you would
not know which of the two moved it.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dateutil import parser as dateparser

CASES_DIR = Path(__file__).parent / "cases"
RUNS_DIR = Path(__file__).parent / "runs"

# Frozen scoring parameters. These are part of the metric definition: changing
# either one changes what every number means, so a change here invalidates the
# committed baseline and must be a deliberate, reviewed act.
OVERLAP_THRESHOLD = 0.5
STOPWORDS = frozenset(
    "a an the to for of and or is are be do i my me we our you your it this that "
    "on at in by with need needs got have has about".split()
)


# --------------------------------------------------------------------------
# cases
# --------------------------------------------------------------------------

@dataclass
class Case:
    id: str
    transcript: str
    expected: dict
    label_status: str
    recorded: dict | None = None
    notes: str = ""

    @property
    def is_labelled(self) -> bool:
        """True only once a human has signed the labels off.

        Metrics computed against `proposed` labels are not measurements of the
        model. They are measurements of the model against a guess.
        """
        return self.label_status == "approved"

    @property
    def expects_transport_failure(self) -> bool:
        return bool(self.recorded and self.recorded.get("transport_error"))


def load_cases(cases_dir: Path = CASES_DIR) -> list[Case]:
    cases = []
    for path in sorted(cases_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        missing = {"id", "transcript", "expected", "label_status"} - set(raw)
        if missing:
            raise ValueError(f"{path.name}: missing keys {sorted(missing)}")
        if raw["label_status"] not in ("proposed", "approved"):
            raise ValueError(
                f"{path.name}: label_status must be 'proposed' or 'approved', "
                f"got {raw['label_status']!r}"
            )
        cases.append(
            Case(
                id=raw["id"],
                transcript=raw["transcript"],
                expected=raw["expected"],
                label_status=raw["label_status"],
                recorded=raw.get("recorded"),
                notes=raw.get("notes", ""),
            )
        )
    return cases


def case_set_hash(cases: list[Case]) -> str:
    """Identifies the corpus. Adding a case shifts every aggregate, so a diff
    across two different case sets compares nothing and must refuse to run."""
    blob = json.dumps(
        [{"id": c.id, "transcript": c.transcript, "expected": c.expected} for c in cases],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def prompt_hash(categories: list[str]) -> str:
    """Hash of the system prompt as actually sent.

    This is what makes replay honest. A recorded response was produced by the
    prompt in effect when it was recorded; if the prompt has since changed, the
    recording no longer tells you anything about current behaviour. Storing this
    lets the runner refuse to score a stale recording instead of quietly
    reporting the old prompt's numbers as the new prompt's.
    """
    import formatter

    system = formatter._SYSTEM.replace("{categories}", ", ".join(categories))
    return hashlib.sha256(system.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# reminder scoring
# --------------------------------------------------------------------------

def normalize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return {w for w in words if w not in STOPWORDS}


def overlap(a: str, b: str) -> float:
    """Overlap coefficient: |A n B| / min(|A|, |B|).

    Chosen over Jaccard because expected reminder texts are terse ("send the
    invoice") while generated ones are often padded ("send the invoice to the
    client before Friday"). Jaccard punishes that padding as if it were a miss;
    the reminder is still the right reminder.
    """
    sa, sb = normalize(a), normalize(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def datetime_state(raw: str | None, now: datetime | None = None) -> str:
    """Classify a reminder's datetime the way reminders.py will treat it.

    Three states, not two, because `has_datetime` cannot distinguish the two
    that matter. reminders.py fires its toast when `delay < 1`, which covers an
    absent datetime, one dateutil cannot parse, AND one already in the past. All
    three interrupt the user the instant the note is saved. A reminder for
    "sometime next sprint" has a datetime and is still broken.

    Mirrors reminders.py's own parse (dateutil, fuzzy=True, naive treated as
    UTC) rather than inventing a second one -- if that parse is wrong, this
    should be wrong the same way, so the eval measures the product and not a
    parallel implementation.
    """
    if not raw:
        return "absent"
    now = now or datetime.now(tz=timezone.utc)
    try:
        dt = dateparser.parse(raw, fuzzy=True)
    except Exception:
        return "unparseable_or_past"
    if dt is None:
        return "unparseable_or_past"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return "future" if (dt - now).total_seconds() >= 1 else "unparseable_or_past"


def match_reminders(expected: list[dict], predicted: list[dict], now=None) -> dict:
    """Greedy one-to-one match. Returns counters plus the datetime breakdown.

    One-to-one matters: without removing a matched prediction from the pool, a
    single predicted reminder can satisfy two expected ones and recall comes out
    above the truth.
    """
    pairs = []
    for ei, e in enumerate(expected):
        for pi, p in enumerate(predicted):
            score = overlap(e.get("text", ""), p.get("text", ""))
            if score >= OVERLAP_THRESHOLD:
                pairs.append((score, ei, pi))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))

    used_e, used_p, matched = set(), set(), []
    for score, ei, pi in pairs:
        if ei in used_e or pi in used_p:
            continue
        used_e.add(ei)
        used_p.add(pi)
        matched.append((ei, pi))

    dt_correct = 0
    dt_breakdown = {"absent": 0, "unparseable_or_past": 0, "future": 0}
    for ei, pi in matched:
        state = datetime_state(predicted[pi].get("datetime"), now=now)
        dt_breakdown[state] += 1
        if state == expected[ei].get("datetime_state", "future"):
            dt_correct += 1

    return {
        "tp": len(matched),
        "fp": len(predicted) - len(matched),
        "fn": len(expected) - len(matched),
        "datetime_correct": dt_correct,
        "datetime_breakdown": dt_breakdown,
    }


# --------------------------------------------------------------------------
# metric accumulation
# --------------------------------------------------------------------------

@dataclass
class Metrics:
    n_cases: int = 0
    n_transport_fallback: int = 0
    n_parse_fallback: int = 0
    n_scored: int = 0            # produced a parsed note; the only scorable ones
    n_category_correct: int = 0
    n_category_coerced: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    datetime_correct: int = 0
    datetime_breakdown: dict = field(
        default_factory=lambda: {"absent": 0, "unparseable_or_past": 0, "future": 0}
    )
    per_case: dict = field(default_factory=dict)

    # -- derived ----------------------------------------------------------
    @property
    def n_responded(self) -> int:
        """Cases where a body actually came back, so `_parse` had a chance to
        run. Transport failures are not schema-conformance denominators."""
        return self.n_cases - self.n_transport_fallback

    @property
    def schema_conformance(self) -> float | None:
        return _ratio(self.n_scored, self.n_responded)

    @property
    def fallback_rate(self) -> float | None:
        return _ratio(self.n_transport_fallback + self.n_parse_fallback, self.n_cases)

    @property
    def category_accuracy(self) -> float | None:
        return _ratio(self.n_category_correct, self.n_scored)

    @property
    def reminder_precision(self) -> float | None:
        return _ratio(self.tp, self.tp + self.fp)

    @property
    def reminder_recall(self) -> float | None:
        return _ratio(self.tp, self.tp + self.fn)

    @property
    def datetime_accuracy(self) -> float | None:
        return _ratio(self.datetime_correct, self.tp)

    def as_dict(self) -> dict:
        return {
            "n_cases": self.n_cases,
            "n_scored": self.n_scored,
            "n_responded": self.n_responded,
            "fallback_transport": self.n_transport_fallback,
            "fallback_parse": self.n_parse_fallback,
            "category_coerced": self.n_category_coerced,
            "reminder_counts": {"tp": self.tp, "fp": self.fp, "fn": self.fn},
            "datetime_breakdown": self.datetime_breakdown,
            "per_case": self.per_case,
            "metrics": {
                "category_accuracy": self.category_accuracy,
                "schema_conformance": self.schema_conformance,
                "fallback_rate": self.fallback_rate,
                "reminder_precision": self.reminder_precision,
                "reminder_recall": self.reminder_recall,
                "datetime_accuracy": self.datetime_accuracy,
            },
        }


def _ratio(num: int, den: int) -> float | None:
    """None, never 0.0 or 1.0, when the denominator is empty.

    An empty denominator means "not measured". Rendering that as a number is how
    a run with no data comes to report perfect precision.
    """
    return round(num / den, 4) if den else None


def score(case: Case, note: dict, metrics: Metrics, now=None) -> dict:
    """Fold one produced note into the running counters."""
    metrics.n_cases += 1
    entry: dict = {"id": case.id}

    kind = note.get("_fallback_kind")
    if kind == "transport":
        metrics.n_transport_fallback += 1
        entry["outcome"] = "fallback_transport"
        # A fallback returns reminders: [] by construction, so scoring it would
        # book every expected reminder as a false negative and make "Ollama was
        # down" indistinguishable from "the model missed the deadline".
        metrics.per_case[case.id] = entry
        return entry
    if kind == "parse":
        metrics.n_parse_fallback += 1
        entry["outcome"] = "fallback_parse"
        metrics.per_case[case.id] = entry
        return entry

    metrics.n_scored += 1
    entry["outcome"] = "scored"

    if note.get("_category_coerced"):
        metrics.n_category_coerced += 1
        entry["category_coerced"] = True

    entry["category"] = note.get("category")
    entry["category_expected"] = case.expected.get("category")
    if note.get("category") == case.expected.get("category"):
        metrics.n_category_correct += 1
        entry["category_correct"] = True
    else:
        entry["category_correct"] = False

    r = match_reminders(
        case.expected.get("reminders", []), note.get("reminders", []), now=now
    )
    metrics.tp += r["tp"]
    metrics.fp += r["fp"]
    metrics.fn += r["fn"]
    metrics.datetime_correct += r["datetime_correct"]
    for k, v in r["datetime_breakdown"].items():
        metrics.datetime_breakdown[k] += v
    entry["reminders"] = {"tp": r["tp"], "fp": r["fp"], "fn": r["fn"]}

    metrics.per_case[case.id] = entry
    return entry
