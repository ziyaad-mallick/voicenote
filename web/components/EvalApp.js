'use client';

import { useMemo, useState } from 'react';
import { scoreAll } from '@/lib/score.mjs';
import { readCorpus, ratio, count } from './shape';

const FALSE_POSITIVE_CASE = 'no-deadline-negative-02';
const TRANSPORT_CASE = 'ollama-unreachable-01';

const STATE_STYLE = {
  future: { color: 'var(--good)', label: 'future' },
  unparseable_or_past: { color: 'var(--bad)', label: 'unparseable_or_past' },
  absent: { color: 'var(--bad)', label: 'absent' },
};

function Mono({ children, className = '' }) {
  return <span className={`font-mono ${className}`}>{children}</span>;
}

function StateTag({ state }) {
  const s = STATE_STYLE[state] || { color: 'var(--fg-dim)', label: state || 'unknown' };
  return (
    <span
      className="font-mono text-[11px] px-1.5 py-0.5 rounded-sm border"
      style={{ color: s.color, borderColor: 'var(--rule-strong)' }}
    >
      {s.label}
    </span>
  );
}

function Section({ n, title, children, sub }) {
  return (
    <section className="border-t rule pt-8 mt-16">
      <div className="flex items-baseline gap-3">
        <Mono className="text-xs dim">{n}</Mono>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      </div>
      {sub ? <p className="dim text-sm mt-2 max-w-3xl leading-relaxed">{sub}</p> : null}
      <div className="mt-6">{children}</div>
    </section>
  );
}

/* ---------------------------------------------------------------- metrics */

function MetricRow({ name, value, denom, note, emphasis }) {
  return (
    <tr>
      <td style={{ fontWeight: emphasis ? 600 : 400 }}>{name}</td>
      <td className="num">
        <Mono className={emphasis ? 'font-semibold' : ''}>{value}</Mono>
      </td>
      <td className="num dim">
        <Mono className="text-xs">{denom}</Mono>
      </td>
      <td className="dim text-sm pl-6">{note}</td>
    </tr>
  );
}

function MetricPanel({ c, metricLabel }) {
  const b = c.datetime_breakdown || {};
  return (
    <table className="data font-[inherit]">
      <thead>
        <tr>
          <th>Metric</th>
          <th className="num">Value</th>
          <th className="num">Denominator</th>
          <th className="pl-6">Why that denominator</th>
        </tr>
      </thead>
      <tbody>
        <MetricRow
          name="Category accuracy"
          value={ratio(c.category_accuracy)}
          denom={`n_scored=${count(c.n_scored)}`}
          note={`Coerced off-list categories flagged, not counted as correct (coerced=${count(c.category_coerced)}).`}
        />
        <MetricRow
          name="Schema conformance"
          value={ratio(c.schema_conformance)}
          denom={`n_responded=${count(c.n_responded)}`}
          note="Only cases where a body came back, so _parse had a chance to run."
        />
        <MetricRow
          name="Fallback rate"
          value={ratio(c.fallback_rate)}
          denom={`n_cases=${count(c.n_cases)}`}
          note={`transport=${count(c.fallback_transport)} · parse=${count(c.fallback_parse)} — split by cause, never merged.`}
        />
        <MetricRow
          name="Reminder precision"
          value={ratio(c.reminder_precision)}
          denom={`n_scored=${count(c.n_scored)} · tp=${count(c.tp)} fp=${count(c.fp)}`}
          note="A false positive invents an obligation and fires a toast. Reported apart from recall; never averaged into F1."
        />
        <MetricRow
          name="Reminder recall"
          value={ratio(c.reminder_recall)}
          denom={`n_scored=${count(c.n_scored)} · tp=${count(c.tp)} fn=${count(c.fn)}`}
          note="A false negative silently loses one."
        />
        <MetricRow
          emphasis
          name={`Datetime accuracy (${metricLabel})`}
          value={ratio(c.datetime_accuracy)}
          denom={`tp=${count(c.tp)}`}
          note={`Matched reminders only. Breakdown: absent=${count(b.absent)} · unparseable_or_past=${count(b.unparseable_or_past)} · future=${count(b.future)}`}
        />
      </tbody>
    </table>
  );
}

/* ----------------------------------------------------------------- toggle */

function Toggle({ metric, setMetric }) {
  const opts = [
    ['has_datetime', 'has_datetime', 'the naive metric'],
    ['three_state', 'three-state', 'what reminders.py actually does'],
  ];
  return (
    <div className="inline-flex rounded-md border overflow-hidden" style={{ borderColor: 'var(--rule-strong)' }}>
      {opts.map(([val, label, sub]) => {
        const on = metric === val;
        return (
          <button
            key={val}
            type="button"
            onClick={() => setMetric(val)}
            aria-pressed={on}
            className="px-4 py-2.5 text-left transition-colors"
            style={{
              background: on ? 'var(--fg)' : 'transparent',
              color: on ? 'var(--bg)' : 'var(--fg-dim)',
            }}
          >
            <span className="font-mono text-sm block">{label}</span>
            <span className="text-[11px] block opacity-75">{sub}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------- case explorer */

function Reminder({ r, showState }) {
  return (
    <li className="py-1.5 border-b rule last:border-0">
      <Mono className="text-[13px]">{r.text}</Mono>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        {r.datetime !== undefined ? (
          <Mono className="text-[11px] dim">
            datetime={r.datetime === null || r.datetime === '' ? '∅' : JSON.stringify(r.datetime)}
          </Mono>
        ) : null}
        {showState ? <StateTag state={r.datetime_state} /> : null}
      </div>
    </li>
  );
}

function CaseCard({ kase, per }) {
  const isFP = kase.id === FALSE_POSITIVE_CASE;
  // The false-positive case is the evidence for the precision number, so it
  // opens without a click. The rest stay collapsed to keep the list scannable.
  const [open, setOpen] = useState(isFP);
  const isTransport = kase.id === TRANSPORT_CASE || kase.outcome === 'fallback_transport';
  const pred = kase.predicted;
  // per_case entries nest the reminder counters under `reminders` in the Python
  // harness; accept either shape, and show nothing when the case was excluded.
  const raw = per && (per.reminders || per);
  const counts = raw && raw.tp !== undefined ? raw : undefined;

  return (
    <article
      className="border rule rounded-md overflow-hidden"
      style={{
        borderColor: isFP || isTransport ? 'var(--rule-strong)' : 'var(--rule)',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-2 sunk"
      >
        <Mono className="text-[13px] font-medium">{kase.id}</Mono>
        <Mono className="text-[11px] dim">{kase.outcome}</Mono>
        <Mono className="text-[11px] dim">label={kase.label_status}</Mono>
        <span className="ml-auto flex items-center gap-3">
          {counts ? (
            <Mono className="text-[11px]">
              tp={count(counts.tp)} fp={count(counts.fp)} fn={count(counts.fn)}
            </Mono>
          ) : (
            <Mono className="text-[11px] dim">not scored for reminders</Mono>
          )}
          <Mono className="text-[11px] dim">{open ? '−' : '+'}</Mono>
        </span>
      </button>

      {isFP ? (
        <p className="px-4 py-2 text-sm border-t rule" style={{ color: 'var(--bad)' }}>
          The false positive. The transcript reports that a restaurant was good. The model
          returned an obligation nobody stated and gave it a time.
        </p>
      ) : null}
      {isTransport ? (
        <p className="px-4 py-2 text-sm border-t rule dim">
          Excluded from reminder precision and recall by design. The fallback returns{' '}
          <Mono>reminders: []</Mono> by construction, so scoring it would book every expected
          reminder as a false negative — making “Ollama was down” arithmetically identical to
          “the model missed a deadline”.
        </p>
      ) : null}

      {open ? (
        <div className="px-4 py-4 border-t rule grid gap-6 md:grid-cols-2">
          <div className="md:col-span-2">
            <h4 className="text-[11px] uppercase tracking-wider dim mb-2">Transcript</h4>
            <p className="font-mono text-[13px] leading-relaxed">{kase.transcript}</p>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wider dim mb-2">
              Expected reminders ({(kase.expected?.reminders || []).length})
            </h4>
            {(kase.expected?.reminders || []).length ? (
              <ul>
                {kase.expected.reminders.map((r, i) => (
                  <Reminder key={i} r={r} showState />
                ))}
              </ul>
            ) : (
              <p className="text-sm dim">None. Any reminder here is a false positive.</p>
            )}
            <p className="text-[11px] dim mt-3">
              expected category: <Mono>{kase.expected?.category}</Mono>
            </p>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wider dim mb-2">
              Predicted reminders ({(pred?.reminders || []).length})
            </h4>
            {pred ? (
              (pred.reminders || []).length ? (
                <ul>
                  {pred.reminders.map((r, i) => (
                    <Reminder key={i} r={r} showState />
                  ))}
                </ul>
              ) : (
                <p className="text-sm dim">None returned.</p>
              )
            ) : (
              <p className="text-sm dim">
                No parsed note — the request never returned a usable body.
              </p>
            )}
            {pred ? (
              <p className="text-[11px] dim mt-3">
                predicted category: <Mono>{pred.category}</Mono>
                {pred.category_coerced ? (
                  <span style={{ color: 'var(--bad)' }}> (coerced)</span>
                ) : null}
              </p>
            ) : null}
          </div>

          {kase.notes ? (
            <div className="md:col-span-2 border-t rule pt-4">
              <h4 className="text-[11px] uppercase tracking-wider dim mb-2">Labelling note</h4>
              <p className="text-sm leading-relaxed dim">{kase.notes}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

/* -------------------------------------------------------------------- app */

export default function EvalApp({ data }) {
  const [metric, setMetric] = useState('three_state');

  const results = useMemo(() => {
    const cases = data.cases || [];
    return {
      three_state: readCorpus(scoreAll(cases, { datetimeMetric: 'three_state' })),
      has_datetime: readCorpus(scoreAll(cases, { datetimeMetric: 'has_datetime' })),
    };
  }, [data]);

  const c = results[metric];
  const other = results[metric === 'three_state' ? 'has_datetime' : 'three_state'];
  const metricLabel = metric === 'three_state' ? 'three-state' : 'has_datetime';

  const naive = results.has_datetime.datetime_accuracy;
  const real = results.three_state.datetime_accuracy;
  const brokenCount = results.three_state.datetime_breakdown
    ? (results.three_state.datetime_breakdown.unparseable_or_past ?? 0) +
      (results.three_state.datetime_breakdown.absent ?? 0)
    : undefined;

  return (
    <>
      <Section
        n="01"
        title="The four numbers"
        sub="Computed in your browser from the recorded run, by the same scoring rules as evals/harness.py. Ratios with an empty denominator read n/a — never 0.000, never 1.000."
      >
        <MetricPanel c={c} metricLabel={metricLabel} />
      </Section>

      <Section
        n="02"
        title="The metric that found the bug"
        sub="Flip the datetime metric. Nothing about the model changes — the same recorded responses are scored twice. Only the question being asked changes."
      >
        <div className="flex flex-wrap items-center gap-6">
          <Toggle metric={metric} setMetric={setMetric} />
          <div>
            <Mono className="text-4xl font-semibold tabular-nums">
              {ratio(c.datetime_accuracy)}
            </Mono>
            <div className="text-xs dim mt-1">
              datetime accuracy · {metricLabel} · other metric reads{' '}
              <Mono>{ratio(other.datetime_accuracy)}</Mono>
            </div>
          </div>
        </div>

        <div
          className="mt-6 border-l-2 pl-5 py-1 max-w-3xl"
          style={{ borderColor: metric === 'three_state' ? 'var(--bad)' : 'var(--accent)' }}
        >
          {metric === 'has_datetime' ? (
            <p className="leading-relaxed">
              <strong>This is the naive metric, and it is lying to you.</strong>{' '}
              <Mono className="text-[13px]">has_datetime</Mono> scores a reminder correct because a
              datetime is <em>present</em>. It never asks whether that datetime is in the future.{' '}
              <Mono className="text-[13px]">&quot;2023-09-05T00:00:00Z&quot;</Mono>,{' '}
              <Mono className="text-[13px]">&quot;tomorrow morning&quot;</Mono> and{' '}
              <Mono className="text-[13px]">&quot;in two weeks&quot;</Mono> all pass. Every one of
              them fires a Windows toast the instant the note is saved.
            </p>
          ) : (
            <p className="leading-relaxed">
              <strong>This is what the scheduler actually does.</strong>{' '}
              <Mono className="text-[13px]">reminders.py</Mono> parses the string with{' '}
              <Mono className="text-[13px]">dateutil(fuzzy=True)</Mono> and fires immediately
              whenever the computed delay falls under one second — which covers an absent
              datetime, an unparseable one, and one already in the past alike. So the metric has
              three states, not two, and{' '}
              {brokenCount === undefined ? 'the broken matches' : <Mono>{brokenCount}</Mono>} of the
              matched reminders land in the two that interrupt the user.
            </p>
          )}
        </div>

        <p className="mt-6 text-sm dim max-w-3xl leading-relaxed">
          Had the case schema asserted <Mono className="text-[13px]">has_datetime: true</Mono>, as
          originally specified, every one of the broken reminders would have scored as correct —
          they do all have a datetime. The bug is not whether a datetime is present; it is whether
          the datetime is one the scheduler can use. The naive metric reads{' '}
          <Mono>{ratio(naive)}</Mono>; the honest one reads <Mono>{ratio(real)}</Mono>. The metric
          design is what found the bug.
        </p>

        <div className="mt-8 grid gap-4 sm:grid-cols-2 max-w-3xl">
          <div className="border rule rounded-md p-4">
            <h4 className="text-[11px] uppercase tracking-wider dim mb-2">Cause 1 — hallucinated year <span className="normal-case tracking-normal">(fixed)</span></h4>
            <p className="text-sm leading-relaxed">
              The prompt never told the model today&apos;s date. “Friday the 5th of September”
              came back as <Mono className="text-[13px]">2023-09-05T00:00:00Z</Mono>, years in the
              past, so the delay was negative and the toast fired on save. The prompt now carries
              the current time and requires an absolute ISO-8601 timestamp with an explicit year.
            </p>
          </div>
          <div className="border rule rounded-md p-4">
            <h4 className="text-[11px] uppercase tracking-wider dim mb-2">Cause 2 — a zero delay reached three ways <span className="normal-case tracking-normal">(fixed)</span></h4>
            <p className="text-sm leading-relaxed">
              “tomorrow morning” and “in two weeks” are not resolved by{' '}
              <Mono className="text-[13px]">dateutil.parser.parse(..., fuzzy=True)</Mono>, and{' '}
              <Mono className="text-[13px]">reminders.py</Mono> swallowed the exception, leaving
              the delay at zero — the same zero an absent datetime and a past one produced.{' '}
              It now classifies and routes: schedule only <Mono className="text-[13px]">future</Mono>,
              toast only <Mono className="text-[13px]">past</Mono>, stay silent for the rest.
            </p>
          </div>
        </div>

        <div className="mt-8 max-w-3xl border rule rounded-md p-5">
          <h4 className="text-[11px] uppercase tracking-wider dim mb-3">
            Before → after, same 8 cases, same model
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left dim">
                  <th className="py-1 pr-4 font-normal">Metric</th>
                  <th className="py-1 pr-4 font-normal">Before</th>
                  <th className="py-1 font-normal">After</th>
                </tr>
              </thead>
              <tbody className="font-mono text-[13px]">
                <tr><td className="py-1 pr-4">datetime accuracy</td><td className="py-1 pr-4">0.250</td><td className="py-1">0.875</td></tr>
                <tr><td className="py-1 pr-4">reminder precision</td><td className="py-1 pr-4">0.800</td><td className="py-1">1.000</td></tr>
                <tr><td className="py-1 pr-4">reminder recall</td><td className="py-1 pr-4">0.667</td><td className="py-1">0.889</td></tr>
                <tr><td className="py-1 pr-4">category accuracy</td><td className="py-1 pr-4">1.000</td><td className="py-1">0.857</td></tr>
                <tr><td className="py-1 pr-4">n_scored</td><td className="py-1 pr-4">6</td><td className="py-1">7</td></tr>
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-sm leading-relaxed">
            Category accuracy <strong>regressed</strong>, and it is listed rather than omitted.
            One case moved from <Mono className="text-[13px]">Ideas</Mono> to{' '}
            <Mono className="text-[13px]">Projects</Mono>; the added prompt text is all deadlines
            and tasks, which plausibly tilted a product reflection toward the work category. At
            n=7 a single case is 14 points, and that label is the most contestable in the set.
          </p>
        </div>

        <div
          className="mt-6 max-w-3xl border-l-2 pl-5 py-1"
          style={{ borderColor: 'var(--rule-strong)' }}
        >
          <h4 className="text-[11px] uppercase tracking-wider dim mb-2">
            The number went up and the metric went blind
          </h4>
          <p className="text-sm leading-relaxed">
            <Mono className="text-[13px]">datetime_state</Mono> has three states and{' '}
            <Mono className="text-[13px]">future</Mono> is one of them, so it answers “can the
            scheduler use this string” — the right question while the answer was usually “no”. It
            cannot answer “is this the right moment”. Today is Thursday 2026-08-27. For “next
            Monday” the model emits <Mono className="text-[13px]">2026-08-30</Mono> — a Sunday, and
            the wrong one. For “in two weeks” it emits{' '}
            <Mono className="text-[13px]">2026-09-14</Mono>, four days late. Both score as correct.
            0.875 is an honest measurement of a question that stopped being the interesting one the
            moment the fix landed; date-exactness against a labelled moment is what this harness
            needs next.
          </p>
        </div>
      </Section>

      <Section
        n="03"
        title="Cases"
        sub={`Every case in the suite, expanded. Expected labels are human-signed-off; predictions are the recorded model output. Per-case tp/fp/fn are the counters this case contributed to the corpus totals, under the ${metricLabel} metric.`}
      >
        <div className="grid gap-3">
          {(data.cases || []).map((k) => (
            <CaseCard key={k.id} kase={k} per={c.per_case ? c.per_case[k.id] : undefined} />
          ))}
        </div>
      </Section>
    </>
  );
}
