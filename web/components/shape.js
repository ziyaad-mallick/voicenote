/**
 * Normalizes whatever `scoreAll` hands back into the field names this UI uses.
 *
 * `scoreAll` mirrors the Python harness's `Metrics.as_dict()`, which nests some
 * counters (`metrics.*`, `reminder_counts.*`) and leaves others at the top
 * level. Rather than guess one layout and render zeros when the guess is wrong,
 * every field is looked up in each plausible place and left `undefined` when it
 * is genuinely absent. `undefined` renders as "n/a", never as a number.
 */
function find(obj, keys) {
  if (!obj) return undefined;
  const pools = [obj, obj.metrics, obj.reminder_counts, obj.counters, obj.totals];
  for (const pool of pools) {
    if (!pool || typeof pool !== 'object') continue;
    for (const k of keys) {
      if (pool[k] !== undefined) return pool[k];
    }
  }
  return undefined;
}

export function readCorpus(res) {
  return {
    n_cases: find(res, ['n_cases']),
    n_scored: find(res, ['n_scored']),
    n_responded: find(res, ['n_responded']),
    fallback_transport: find(res, ['fallback_transport', 'n_transport_fallback']),
    fallback_parse: find(res, ['fallback_parse', 'n_parse_fallback']),
    category_coerced: find(res, ['category_coerced', 'n_category_coerced']),
    tp: find(res, ['tp']),
    fp: find(res, ['fp']),
    fn: find(res, ['fn']),
    datetime_correct: find(res, ['datetime_correct']),
    datetime_breakdown: find(res, ['datetime_breakdown']),
    category_accuracy: find(res, ['category_accuracy']),
    schema_conformance: find(res, ['schema_conformance']),
    fallback_rate: find(res, ['fallback_rate']),
    reminder_precision: find(res, ['reminder_precision']),
    reminder_recall: find(res, ['reminder_recall']),
    datetime_accuracy: find(res, ['datetime_accuracy']),
    per_case: find(res, ['per_case']) || {},
  };
}

/** Ratios are `null` when the denominator is empty. Never render that as 0. */
export function ratio(v) {
  if (v === null) return 'n/a';
  if (v === undefined) return 'n/a';
  return Number(v).toFixed(3);
}

export function count(v) {
  return v === undefined || v === null ? '—' : String(v);
}
