/**
 * A faithful JS port of the PURE scoring logic in `evals/harness.py`.
 *
 * Scope, deliberately narrow: string normalization, the overlap coefficient,
 * the greedy reminder matcher, and corpus-level counter accumulation. That is
 * everything in the harness that is a function of strings and sets.
 *
 * What is NOT here, and must never be added: date parsing. The harness
 * classifies a reminder's datetime with `dateutil.parser.parse(raw,
 * fuzzy=True)`, which JavaScript's `Date` does not reproduce. Every
 * `datetime_state` is precomputed by `evals/export_web.py` and read straight
 * off the predicted reminder object. A second parser here would be a second
 * thing that can be wrong, and when the headline number moved you would not
 * know which of the two moved it.
 *
 * `web/lib/score.test.mjs` asserts this port reproduces `evals/baseline.json`
 * per case. That test is the only reason to trust any number this file emits.
 */

// Frozen scoring parameters, copied verbatim from harness.py. Changing either
// changes what every number means.
export const OVERLAP_THRESHOLD = 0.5;

export const STOPWORDS = new Set(
  (
    "a an the to for of and or is are be do i my me we our you your it this that " +
    "on at in by with need needs got have has about"
  ).split(" ")
);

const WORD_RE = /[a-z0-9']+/g;

/** Mirrors `re.findall(r"[a-z0-9']+", text.lower())` then stopword removal. */
export function normalize(text) {
  const words = String(text ?? "").toLowerCase().match(WORD_RE) ?? [];
  const out = new Set();
  for (const w of words) if (!STOPWORDS.has(w)) out.add(w);
  return out;
}

/** Overlap coefficient: |A n B| / min(|A|, |B|). 0.0 if either side is empty. */
export function overlap(a, b) {
  const sa = normalize(a);
  const sb = normalize(b);
  if (sa.size === 0 || sb.size === 0) return 0.0;
  let inter = 0;
  for (const w of sa) if (sb.has(w)) inter += 1;
  return inter / Math.min(sa.size, sb.size);
}

/**
 * `None`, never 0 and never 1, when the denominator is empty.
 *
 * An empty denominator means "not measured". Rendering that as a number is how
 * a run with no data comes to report perfect precision.
 *
 * Rounds to 4dp to match Python's `round(x, 4)`. `toFixed` rounds ties away
 * from zero where Python rounds ties to even; an exact tie requires the double
 * `num/den` to be a dyadic rational whose 4th decimal digit lands on a half,
 * which the small integer denominators in this corpus cannot produce.
 */
export function ratio(num, den) {
  if (!den) return null;
  return Number((num / den).toFixed(4));
}

/**
 * Greedy one-to-one match, identical tie-break ordering to Python.
 *
 * Python builds `(score, ei, pi)` triples and sorts by `(-score, ei, pi)`.
 * The comparator below produces the same total order, so the greedy walk
 * consumes candidates in the same sequence and picks the same pairs.
 *
 * One-to-one matters: without removing a matched prediction from the pool, one
 * predicted reminder can satisfy two expected ones and recall comes out above
 * the truth.
 *
 * @param options.datetimeMetric "three_state" (default) or "has_datetime".
 */
export function matchReminders(expected, predicted, options = {}) {
  const metric = options.datetimeMetric ?? "three_state";
  const exp = expected ?? [];
  const pred = predicted ?? [];

  const pairs = [];
  for (let ei = 0; ei < exp.length; ei += 1) {
    for (let pi = 0; pi < pred.length; pi += 1) {
      const score = overlap(exp[ei].text ?? "", pred[pi].text ?? "");
      if (score >= OVERLAP_THRESHOLD) pairs.push([score, ei, pi]);
    }
  }
  pairs.sort((x, y) => y[0] - x[0] || x[1] - y[1] || x[2] - y[2]);

  const usedE = new Set();
  const usedP = new Set();
  const matched = [];
  for (const [, ei, pi] of pairs) {
    if (usedE.has(ei) || usedP.has(pi)) continue;
    usedE.add(ei);
    usedP.add(pi);
    matched.push([ei, pi]);
  }

  let dtCorrect = 0;
  const dtBreakdown = { absent: 0, unparseable_or_past: 0, future: 0 };
  for (const [ei, pi] of matched) {
    // Read, never parse. See the module header.
    const state = pred[pi].datetime_state;
    if (state in dtBreakdown) dtBreakdown[state] += 1;
    if (metric === "has_datetime") {
      // The naive metric the case schema originally specified: "did it attach
      // a datetime at all". It scores a hallucinated year and unparseable
      // prose as correct, which is the whole reason the three-state metric
      // exists. Kept so the demo can show the gap rather than assert it.
      const raw = pred[pi].datetime;
      if (typeof raw === "string" && raw.length > 0) dtCorrect += 1;
    } else if (state === (exp[ei].datetime_state ?? "future")) {
      dtCorrect += 1;
    }
  }

  return {
    tp: matched.length,
    fp: pred.length - matched.length,
    fn: exp.length - matched.length,
    matched,
    datetime_correct: dtCorrect,
    datetime_breakdown: dtBreakdown,
  };
}

/**
 * Corpus-level counters, reproducing `harness.score` + `Metrics.as_dict`.
 *
 * Counters, not per-case averages: per-case recall is 0/0 on the most
 * important case in the set -- the one with no deadline at all -- and both
 * ways of resolving that are wrong.
 *
 * @param cases the `cases` array from `web/public/eval-data.json`.
 */
export function scoreAll(cases, options = {}) {
  const metric = options.datetimeMetric ?? "three_state";

  let nCases = 0;
  let nTransport = 0;
  let nParse = 0;
  let nScored = 0;
  let nCategoryCorrect = 0;
  let nCategoryCoerced = 0;
  let tp = 0;
  let fp = 0;
  let fn = 0;
  let datetimeCorrect = 0;
  const datetimeBreakdown = { absent: 0, unparseable_or_past: 0, future: 0 };
  const perCase = {};

  for (const c of cases ?? []) {
    nCases += 1;
    const entry = { id: c.id };

    if (c.outcome === "fallback_transport") {
      nTransport += 1;
      entry.outcome = "fallback_transport";
      // A fallback returns reminders: [] by construction, so scoring it would
      // book every expected reminder as a false negative and make "Ollama was
      // down" indistinguishable from "the model missed the deadline".
      perCase[c.id] = entry;
      continue;
    }
    if (c.outcome === "fallback_parse") {
      nParse += 1;
      entry.outcome = "fallback_parse";
      perCase[c.id] = entry;
      continue;
    }

    nScored += 1;
    entry.outcome = "scored";

    if (c.predicted?.category_coerced) {
      nCategoryCoerced += 1;
      entry.category_coerced = true;
    }

    entry.category = c.predicted?.category ?? null;
    entry.category_expected = c.expected?.category ?? null;
    if (entry.category === entry.category_expected) {
      nCategoryCorrect += 1;
      entry.category_correct = true;
    } else {
      entry.category_correct = false;
    }

    const r = matchReminders(c.expected?.reminders ?? [], c.predicted?.reminders ?? [], {
      datetimeMetric: metric,
    });
    tp += r.tp;
    fp += r.fp;
    fn += r.fn;
    datetimeCorrect += r.datetime_correct;
    for (const k of Object.keys(datetimeBreakdown)) {
      datetimeBreakdown[k] += r.datetime_breakdown[k];
    }
    entry.reminders = { tp: r.tp, fp: r.fp, fn: r.fn };

    perCase[c.id] = entry;
  }

  // Transport failures are not schema-conformance denominators: `_parse` never
  // had a chance to run.
  const nResponded = nCases - nTransport;

  return {
    n_cases: nCases,
    n_scored: nScored,
    n_responded: nResponded,
    fallback_transport: nTransport,
    fallback_parse: nParse,
    category_coerced: nCategoryCoerced,
    reminder_counts: { tp, fp, fn },
    datetime_breakdown: datetimeBreakdown,
    per_case: perCase,
    metrics: {
      category_accuracy: ratio(nCategoryCorrect, nScored),
      schema_conformance: ratio(nScored, nResponded),
      fallback_rate: ratio(nTransport + nParse, nCases),
      reminder_precision: ratio(tp, tp + fp),
      reminder_recall: ratio(tp, tp + fn),
      datetime_accuracy: ratio(datetimeCorrect, tp),
    },
  };
}
