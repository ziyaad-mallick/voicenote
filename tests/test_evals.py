"""The eval's CI gate.

This is deliberately NOT a quality gate. With replayed responses the model never
runs, so nothing here can tell you whether the notes got better or worse. What
it gates is the deterministic half: given a fixed response body, does the parser
still produce the same note, and does the scoring code still produce the same
counts?

That is worth gating precisely because it is deterministic. A statistical gate
over 8 cases would flake -- one case flipping is a 12-point swing -- whereas a
replayed parser should be bit-identical or something changed.

The quality question is answered by `python -m evals.run --live`, which needs a
real Ollama and therefore cannot run here.
"""
import json

import pytest

from evals.harness import (
    Metrics,
    datetime_state,
    load_cases,
    match_reminders,
    normalize,
    overlap,
    score,
)
from evals.runner import StaleRecording, run_case

CATEGORIES = ["Projects", "Ideas", "Uni", "Personal"]


# -- the case set itself is data, and data can be malformed ------------------

def test_every_case_file_loads_and_validates():
    cases = load_cases()
    assert cases, "no eval cases found"
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids)), f"duplicate case ids: {ids}"


def test_every_case_declares_its_label_status():
    for case in load_cases():
        assert case.label_status in ("proposed", "approved")


def test_expected_reminders_use_a_known_datetime_state():
    valid = {"absent", "unparseable_or_past", "future"}
    for case in load_cases():
        for r in case.expected.get("reminders", []):
            state = r.get("datetime_state", "future")
            assert state in valid, f"{case.id}: bad datetime_state {state!r}"


# -- the matcher -------------------------------------------------------------

def test_normalize_drops_stopwords_and_punctuation():
    assert normalize("Send the invoice, please!") == {"send", "invoice", "please"}


def test_overlap_ignores_padding_on_the_longer_side():
    # The generated reminder is usually wordier than the expected one. That is
    # not a miss, so the overlap coefficient must not punish it.
    assert overlap("send the invoice", "send the invoice to the client by Friday") == 1.0


def test_overlap_is_zero_for_unrelated_text():
    assert overlap("send the invoice", "book a table") == 0.0


def test_a_single_prediction_cannot_satisfy_two_expected_reminders():
    """Without one-to-one assignment, recall comes out above the truth."""
    expected = [{"text": "send the invoice"}, {"text": "send the invoice"}]
    predicted = [{"text": "send the invoice", "datetime": "2099-01-01"}]
    r = match_reminders(expected, predicted)
    assert r["tp"] == 1
    assert r["fn"] == 1
    assert r["fp"] == 0


def test_unmatched_predictions_count_as_false_positives():
    r = match_reminders([], [{"text": "buy a horse", "datetime": "2099-01-01"}])
    assert (r["tp"], r["fp"], r["fn"]) == (0, 1, 0)


def test_unmatched_expectations_count_as_false_negatives():
    r = match_reminders([{"text": "buy a horse"}], [])
    assert (r["tp"], r["fp"], r["fn"]) == (0, 0, 1)


# -- the three datetime states ----------------------------------------------

def test_absent_datetime():
    assert datetime_state(None) == "absent"
    assert datetime_state("") == "absent"


def test_a_future_datetime_is_future():
    assert datetime_state("2099-01-01T09:00:00") == "future"


def test_a_past_datetime_is_not_future():
    assert datetime_state("2001-01-01T09:00:00") == "unparseable_or_past"


def test_unparseable_prose_is_not_treated_as_a_valid_datetime():
    """The case `has_datetime: true` would have got wrong.

    reminders.py fires its toast when delay < 1, and an unparseable string
    leaves delay at 0.0 -- so "sometime next sprint" interrupts the user the
    instant the note is saved. Scoring it as "has a datetime" would hide that.
    """
    assert datetime_state("sometime next sprint") == "unparseable_or_past"


# -- metric arithmetic -------------------------------------------------------

def test_an_empty_denominator_reports_none_not_a_number():
    """A run with no data must not report perfect precision."""
    m = Metrics()
    assert m.reminder_precision is None
    assert m.category_accuracy is None
    assert m.schema_conformance is None


def test_a_transport_fallback_is_excluded_from_reminder_scoring():
    """Otherwise 'Ollama was down' is indistinguishable from 'the model missed
    a deadline', and precision reads 1.00 because a fallback has no predictions
    to be wrong about."""
    m = Metrics()
    case = load_cases()[0]
    note = {
        "title": "x", "category": "Projects", "summary": "", "body": "",
        "tags": [], "reminders": [],
        "_fallback_reason": "boom", "_fallback_kind": "transport",
    }
    entry = score(case, note, m, now=None)
    assert entry["outcome"] == "fallback_transport"
    assert m.n_scored == 0
    assert (m.tp, m.fp, m.fn) == (0, 0, 0)
    assert m.reminder_precision is None
    assert m.fallback_rate == 1.0


def test_transport_failures_are_not_schema_conformance_denominators():
    """_parse never runs when the request never came back."""
    m = Metrics()
    m.n_cases = 4
    m.n_transport_fallback = 2
    m.n_scored = 2
    assert m.n_responded == 2
    assert m.schema_conformance == 1.0


def test_parse_and_transport_fallbacks_are_counted_separately():
    m = Metrics()
    case = load_cases()[0]
    for kind in ("transport", "parse"):
        score(case, {"reminders": [], "_fallback_kind": kind}, m)
    assert m.n_transport_fallback == 1
    assert m.n_parse_fallback == 1


# -- the replay contract -----------------------------------------------------

def test_a_case_with_no_recording_is_stale_not_silently_skipped():
    from evals.harness import Case

    case = Case(id="nope", transcript="x", expected={}, label_status="proposed")
    with pytest.raises(StaleRecording):
        run_case(case, CATEGORIES, live=False)


def test_a_recording_made_against_a_different_prompt_is_stale():
    """The whole reason replay cannot gate prompt changes.

    A recorded response came from the prompt in effect when it was recorded.
    Replay discards the payload, so a changed prompt would otherwise score
    against stale behaviour and pass silently.
    """
    from evals.harness import Case

    case = Case(
        id="nope",
        transcript="x",
        expected={},
        label_status="proposed",
        recorded={"prompt_sha": "0000deadbeef0000", "response": "{}"},
    )
    with pytest.raises(StaleRecording, match="re-record"):
        run_case(case, CATEGORIES, live=False)


def test_the_unreachable_ollama_case_falls_back_and_keeps_the_transcript():
    """The one case that needs no recording, and the one that must never regress:
    if the LLM is unreachable the user still gets their words back."""
    cases = {c.id: c for c in load_cases()}
    case = cases["ollama-unreachable-01"]
    note = run_case(case, CATEGORIES, live=False)
    assert note["_fallback_kind"] == "transport"
    assert note["body"] == case.transcript
    assert note["reminders"] == []


# -- the deterministic regression gate ---------------------------------------

def test_recorded_cases_reproduce_their_committed_per_case_result():
    """Exact per-case match, not an aggregate threshold.

    Replay is deterministic, so the right gate is 'bit-identical or something
    changed'. An aggregate threshold over this few cases would either flake or
    gate nothing.
    """
    from evals.harness import CASES_DIR

    baseline_path = CASES_DIR.parent / "baseline.json"
    if not baseline_path.exists():
        pytest.skip("no baseline committed yet; run `python -m evals.run` and commit it")

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    m = Metrics()
    stale = []
    for case in load_cases():
        try:
            note = run_case(case, CATEGORIES, live=False)
        except StaleRecording as exc:
            stale.append(str(exc))
            continue
        score(case, note, m)

    # A fully-stale corpus must not pass by scoring nothing and matching nothing.
    assert not stale, (
        f"{len(stale)} case(s) could not be scored. If the prompt changed, "
        f"re-record with `python -m evals.run --live --record`:\n  "
        + "\n  ".join(stale)
    )

    for case_id, expected_entry in baseline["per_case"].items():
        assert case_id in m.per_case, f"{case_id} no longer produces a result"
        assert m.per_case[case_id] == expected_entry, (
            f"{case_id} changed against the committed baseline.\n"
            f"  was: {expected_entry}\n"
            f"  now: {m.per_case[case_id]}\n"
            "If this change is intended, re-run `python -m evals.run` and commit "
            "the new evals/baseline.json."
        )
