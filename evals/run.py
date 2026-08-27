"""Report an eval run, and diff it against the previous one.

    python -m evals.run                  # replay; no Ollama needed
    python -m evals.run --live           # call the real Ollama
    python -m evals.run --live --record  # ...and save the responses for replay
    python -m evals.run --diff           # compare the last two runs

The gate that CI enforces lives in tests/test_evals.py. This is the reporting
surface: it writes evals/runs/<iso>.json so "did that prompt change regress
anything" is a command rather than an opinion.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

from .harness import CASES_DIR, RUNS_DIR, case_set_hash, load_cases, prompt_hash  # noqa: E402
from .runner import record_case, run_all  # noqa: E402


def _fmt(v):
    return "  n/a" if v is None else f"{v:5.3f}"


def report(metrics, cases, stale, live: bool) -> dict:
    unlabelled = [c.id for c in cases if not c.is_labelled]
    d = metrics.as_dict()
    d["mode"] = "live" if live else "replay"
    d["case_set_hash"] = case_set_hash(cases)
    d["timestamp"] = datetime.now(tz=timezone.utc).isoformat()
    d["stale"] = stale
    d["unlabelled_cases"] = unlabelled

    m = d["metrics"]
    print(f"=== voicenote eval ({d['mode']}) ===")
    print(f"cases        : {d['n_cases']}   scored: {d['n_scored']}   "
          f"responded: {d['n_responded']}")
    print(f"case set     : {d['case_set_hash']}")
    print()
    print(f"category accuracy    : {_fmt(m['category_accuracy'])}   "
          f"(coerced: {d['category_coerced']})")
    print(f"schema conformance   : {_fmt(m['schema_conformance'])}   "
          f"(parses / responses received)")
    print(f"fallback rate        : {_fmt(m['fallback_rate'])}   "
          f"(transport {d['fallback_transport']}, parse {d['fallback_parse']})")
    print()
    c = d["reminder_counts"]
    print(f"reminder precision   : {_fmt(m['reminder_precision'])}   "
          f"tp={c['tp']} fp={c['fp']} fn={c['fn']}")
    print(f"reminder recall      : {_fmt(m['reminder_recall'])}")
    print(f"datetime accuracy    : {_fmt(m['datetime_accuracy'])}   "
          f"{d['datetime_breakdown']}")
    print()
    print("precision and recall are computed over the "
          f"{d['n_scored']} non-fallback cases only; a fallback returns "
          "reminders: [] by construction, so scoring it would make 'Ollama was "
          "down' look identical to 'the model missed a deadline'.")

    if stale:
        print()
        print("STALE -- these cases were not scored:")
        for s in stale:
            print(f"  {s}")
    if unlabelled:
        print()
        print(f"WARNING: {len(unlabelled)}/{len(cases)} cases carry PROPOSED labels, "
              "not approved ones.")
        print("These numbers are the model measured against a guess. They are not "
              "a result until a human signs the labels off.")
        print(f"  {', '.join(unlabelled)}")
    return d


def diff_last_two() -> int:
    runs = sorted(RUNS_DIR.glob("*.json"))
    if len(runs) < 2:
        print(f"need two runs to diff; found {len(runs)} in {RUNS_DIR}")
        return 1
    prev, cur = json.loads(runs[-2].read_text()), json.loads(runs[-1].read_text())
    if prev["case_set_hash"] != cur["case_set_hash"]:
        print("refusing to diff: the case set changed between these runs "
              f"({prev['case_set_hash']} -> {cur['case_set_hash']}).")
        print("Adding or editing a case shifts every aggregate, so the "
              "difference would be new coverage reported as a regression.")
        return 1
    print(f"{runs[-2].name}  ->  {runs[-1].name}")
    for k, before in prev["metrics"].items():
        after = cur["metrics"][k]
        if before == after:
            continue
        if before is None or after is None:
            print(f"  {k:22s} {before} -> {after}")
        else:
            arrow = "+" if after > before else ""
            print(f"  {k:22s} {before:.4f} -> {after:.4f}  ({arrow}{after - before:.4f})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="call the real Ollama instead of replaying")
    ap.add_argument("--record", action="store_true",
                    help="with --live, write the responses back into the case files")
    ap.add_argument("--write-baseline", action="store_true",
                    help="write evals/baseline.json from this run; the CI gate "
                         "asserts every future replay reproduces it exactly")
    ap.add_argument("--diff", action="store_true",
                    help="diff the two most recent runs and exit")
    ap.add_argument("--record-timeout", type=int, default=600,
                    help="seconds to allow a recording call (default 600). "
                         "Recording captures what the model says; it is not a "
                         "latency measurement. formatter's own 120s limit is "
                         "unaffected and still applies in real use.")
    args = ap.parse_args()

    if args.diff:
        return diff_last_two()

    cfg = config.load()
    categories = cfg["categories"]
    cases = load_cases()
    if not cases:
        print(f"no cases in {CASES_DIR}")
        return 1

    if args.record:
        if not args.live:
            print("--record requires --live")
            return 1
        failed = []
        for case in cases:
            if case.expects_transport_failure:
                print(f"skipped  {case.id} (simulates Ollama being down; "
                      "nothing to record)")
                continue
            try:
                rec = record_case(case, categories, timeout=args.record_timeout)
            except Exception as exc:
                # Keep going. One slow or refused generation should not cost the
                # recordings that already succeeded.
                failed.append((case.id, str(exc)[:120]))
                print(f"FAILED   {case.id}: {str(exc)[:120]}")
                continue
            path = CASES_DIR / f"{case.id}.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["recorded"] = {"prompt_sha": rec["prompt_sha"],
                               "response": rec["response"]}
            path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            print(f"recorded {case.id}")
        if failed:
            print(f"\n{len(failed)} case(s) did not record; they will show as STALE "
                  "below rather than being scored against a guess.\n")
        cases = load_cases()

    metrics, stale = run_all(cases, categories, live=args.live)
    d = report(metrics, cases, stale, live=args.live)

    RUNS_DIR.mkdir(exist_ok=True)
    stamp = d["timestamp"].replace(":", "").replace("-", "").split(".")[0]
    out = RUNS_DIR / f"{stamp}Z.json"
    out.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"wrote {out.relative_to(Path(__file__).parent.parent)}")

    if args.write_baseline:
        if args.live:
            print("refusing to write a baseline from a live run: it would not be "
                  "reproducible, so the gate could never pass twice.")
            return 1
        if stale:
            print(f"refusing to write a baseline with {len(stale)} stale case(s).")
            return 1
        base = Path(__file__).parent / "baseline.json"
        base.write_text(
            json.dumps(
                {"case_set_hash": d["case_set_hash"], "per_case": d["per_case"]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {base.name}")

    # Non-zero on stale, so CI fails loudly rather than reporting a green tick
    # over a corpus it never actually scored. A prompt edit lands here.
    if stale:
        print()
        print(f"FAIL: {len(stale)}/{len(cases)} cases were not scored (see STALE above).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
