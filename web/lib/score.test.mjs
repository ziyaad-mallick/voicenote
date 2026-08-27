/**
 * node --test web/lib/score.test.mjs
 *
 * Zero dependencies, no build step. The headline test is the PARITY test: the
 * JS port must reproduce `evals/baseline.json` exactly, per case. Without it
 * the port is an unverified second implementation of the metric, and a demo
 * that quietly disagrees with the harness is worse than no demo.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { matchReminders, ratio, scoreAll } from "./score.mjs";

const here = (p) => fileURLToPath(new URL(p, import.meta.url));

const data = JSON.parse(readFileSync(here("../public/eval-data.json"), "utf8"));
const baseline = JSON.parse(readFileSync(here("../../evals/baseline.json"), "utf8"));

// --------------------------------------------------------------------------
// parity with the Python harness
// --------------------------------------------------------------------------

test("export and baseline describe the same corpus", () => {
  // Comparing a run against a baseline built from a different case set
  // compares nothing.
  assert.equal(data.case_set_hash, baseline.case_set_hash);
});

test("PARITY: per_case deep-equals evals/baseline.json", () => {
  const result = scoreAll(data.cases);
  assert.deepStrictEqual(result.per_case, baseline.per_case);
});

test("PARITY: aggregates match what `python -m evals.run` reports", () => {
  const result = scoreAll(data.cases);
  assert.deepStrictEqual(result.reminder_counts, { tp: 6, fp: 1, fn: 3 });
  assert.deepStrictEqual(result.datetime_breakdown, {
    absent: 0,
    unparseable_or_past: 5,
    future: 1,
  });
  assert.equal(result.metrics.reminder_precision, 0.8571);
  assert.equal(result.metrics.reminder_recall, 0.6667);
  assert.equal(result.metrics.datetime_accuracy, 0.1667);
  assert.equal(result.metrics.category_accuracy, 1.0);
  assert.equal(result.metrics.schema_conformance, 1.0);
  assert.equal(result.metrics.fallback_rate, 0.125);
  assert.equal(result.n_cases, 8);
  assert.equal(result.n_scored, 7);
  assert.equal(result.n_responded, 7);
  assert.equal(result.fallback_transport, 1);
  assert.equal(result.fallback_parse, 0);
});

// --------------------------------------------------------------------------
// ratio
// --------------------------------------------------------------------------

test("ratio returns null on an empty denominator, never 0 and never 1", () => {
  assert.equal(ratio(0, 0), null);
  assert.equal(ratio(5, 0), null);
  assert.equal(ratio(0, 4), 0);
  assert.equal(ratio(6, 7), 0.8571);
});

test("an all-fallback corpus reports null, not perfect precision", () => {
  const result = scoreAll([
    { id: "a", outcome: "fallback_transport", expected: {}, predicted: {} },
    { id: "b", outcome: "fallback_parse", expected: {}, predicted: {} },
  ]);
  assert.equal(result.metrics.reminder_precision, null);
  assert.equal(result.metrics.reminder_recall, null);
  assert.equal(result.metrics.datetime_accuracy, null);
  assert.equal(result.metrics.category_accuracy, null);
  assert.equal(result.metrics.fallback_rate, 1);
  // Not null: the parse fallback DID receive a body, so it is a legitimate
  // schema-conformance denominator. 0 of 1 conformed.
  assert.equal(result.metrics.schema_conformance, 0);
});

// --------------------------------------------------------------------------
// the greedy matcher
// --------------------------------------------------------------------------

test("one prediction cannot satisfy two expected reminders", () => {
  const expected = [
    { text: "send the invoice to Marcus", datetime_state: "future" },
    { text: "send the invoice to Priya", datetime_state: "future" },
  ];
  const predicted = [
    { text: "send the invoice", datetime: null, datetime_state: "absent" },
  ];
  const r = matchReminders(expected, predicted);
  assert.equal(r.tp, 1, "one-to-one: the single prediction matches once");
  assert.equal(r.fn, 1);
  assert.equal(r.fp, 0);
});

test("tie-break follows Python's (-score, expectedIndex, predictedIndex)", () => {
  // Both expected texts score 1.0 against the single prediction, so the tie is
  // broken by expected index: expected[0] wins.
  const expected = [
    { text: "alpha beta", datetime_state: "future" },
    { text: "alpha beta", datetime_state: "future" },
  ];
  const predicted = [
    { text: "alpha beta gamma", datetime: null, datetime_state: "absent" },
  ];
  const r = matchReminders(expected, predicted);
  assert.deepStrictEqual(r.matched, [[0, 0]]);
});

test("stopwords are stripped before overlap is measured", () => {
  // "buy milk" vs "Purchase the milk": one shared content word out of a
  // min-size of 2, so 0.5 -- exactly the threshold, which counts.
  const r = matchReminders(
    [{ text: "buy milk", datetime_state: "absent" }],
    [{ text: "Purchase the milk", datetime: null, datetime_state: "absent" }]
  );
  assert.equal(r.tp, 1);
});

test("an empty side scores 0 overlap and matches nothing", () => {
  const r = matchReminders(
    [{ text: "", datetime_state: "absent" }],
    [{ text: "buy milk", datetime: null, datetime_state: "absent" }]
  );
  assert.equal(r.tp, 0);
  assert.equal(r.fp, 1);
  assert.equal(r.fn, 1);
});

// --------------------------------------------------------------------------
// the datetime metric toggle -- the finding the demo exists to show
// --------------------------------------------------------------------------

test("has_datetime scores HIGHER than three_state on this corpus", () => {
  const threeState = scoreAll(data.cases).metrics.datetime_accuracy;
  const hasDatetime = scoreAll(data.cases, { datetimeMetric: "has_datetime" })
    .metrics.datetime_accuracy;

  assert.ok(
    hasDatetime > threeState,
    `has_datetime (${hasDatetime}) should exceed three_state (${threeState})`
  );
  // Every one of the 6 matched reminders carries a non-empty datetime string,
  // so the naive metric calls all 6 correct -- including the hallucinated 2023
  // dates and the unparseable prose that fire a toast the instant the note is
  // saved.
  assert.equal(hasDatetime, 1.0);
  assert.equal(threeState, 0.1667);
});

test("the toggle changes only datetime accuracy", () => {
  const a = scoreAll(data.cases);
  const b = scoreAll(data.cases, { datetimeMetric: "has_datetime" });
  assert.deepStrictEqual(a.per_case, b.per_case);
  assert.deepStrictEqual(a.reminder_counts, b.reminder_counts);
  assert.deepStrictEqual(a.datetime_breakdown, b.datetime_breakdown);
  assert.equal(a.metrics.reminder_precision, b.metrics.reminder_precision);
  assert.equal(a.metrics.category_accuracy, b.metrics.category_accuracy);
});

test("has_datetime does not credit an absent datetime", () => {
  const r = matchReminders(
    [{ text: "buy milk", datetime_state: "future" }],
    [{ text: "buy milk", datetime: null, datetime_state: "absent" }],
    { datetimeMetric: "has_datetime" }
  );
  assert.equal(r.tp, 1);
  assert.equal(r.datetime_correct, 0);
});

// --------------------------------------------------------------------------
// the port must not parse dates
// --------------------------------------------------------------------------

test("datetime_state is read off the data, not recomputed", () => {
  // A deliberately impossible pairing: an unparseable string labelled `future`
  // by the exporter. If score.mjs ever parses dates itself, this flips.
  const r = matchReminders(
    [{ text: "buy milk", datetime_state: "future" }],
    [{ text: "buy milk", datetime: "sometime next sprint", datetime_state: "future" }]
  );
  assert.equal(r.datetime_correct, 1);
  assert.deepStrictEqual(r.datetime_breakdown, {
    absent: 0,
    unparseable_or_past: 0,
    future: 1,
  });
});
