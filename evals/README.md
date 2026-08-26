# evals

Measurement for the transcript → note path.

```bash
python -m evals.run                  # replay recorded responses; no Ollama needed
python -m evals.run --live           # call the real Ollama
python -m evals.run --live --record  # ...and save the responses for replay
python -m evals.run --diff           # compare the two most recent runs
pytest tests/test_evals.py           # the CI gate
```

## What this found

The first live run against `goekdenizguelmez/JOSIEFIED-Qwen3` produced this:

```
reminder precision   : 0.857   tp=6 fp=1 fn=3
reminder recall      : 0.667
datetime accuracy    : 0.167   {'absent': 0, 'unparseable_or_past': 5, 'future': 1}
```

Five of the six reminders it got *right* fire at the wrong time. The model finds
exactly the right obligations and attaches a datetime to each one that **fires a
Windows toast the instant the note is saved**, because `reminders.py` fires
immediately whenever the delay computes below one second — which covers a
missing datetime, an unparseable one, and one in the past.

Two separate causes, both real:

- **Hallucinated year.** The transcript says "Friday the 5th of September" and
  names no year. The model emitted `2023-09-05T00:00:00Z`. It is 2026, so the
  reminder is three years overdue and fires on save.
- **Unparseable prose.** `"tomorrow morning"` and `"in two weeks"` are not things
  `dateutil.parser.parse(..., fuzzy=True)` resolves, and `reminders.py` swallows
  the exception and leaves the delay at zero.

This is the entire argument for the metric design below. Had the case schema
asserted `has_datetime: true`, as originally specified, **all five of these
would have scored as correct** — they do all have a datetime. The bug is not
whether a datetime is present; it is whether the datetime is one the scheduler
can use.

## The four numbers, and why they are shaped this way

| Metric | Denominator | Why not simpler |
|---|---|---|
| Category accuracy | non-fallback cases | `formatter._parse` silently rewrites an off-list category to `categories[0]`. Without the `_category_coerced` flag added alongside this harness, **every total failure would score as a correct "Projects" prediction** — the cheapest metric would be the least trustworthy. |
| Schema conformance | cases that *received a body* | When the transport fails, `_parse` never runs. Counting those in the denominator double-counts the same failure in two metrics. |
| Fallback rate | all cases | Split by `_fallback_kind`: `transport` (the request never came back) vs `parse` (it did, and the body was unusable). Before this harness those two were distinguishable only by string-matching the literal `"parse error"`. |
| **Reminder precision / recall** | non-fallback cases | Reported separately, never averaged. A false positive invents an obligation and interrupts you; a false negative loses one. An F1 hides which of those you have. |
| Datetime accuracy | matched reminders | Three states — `absent` / `unparseable_or_past` / `future` — mirroring what `reminders.py` will actually do with the string. |

### Fallbacks are excluded from reminder scoring, deliberately

`formatter._fallback` returns `reminders: []` by construction. Score it and every
expected reminder books as a false negative, so a run with Ollama down is
arithmetically identical to a model that missed every deadline. Worse, aggregate
precision is `tp/(tp+fp)` and a fallback contributes neither — so a corpus that
half-failed would report **precision 1.00**. The harness therefore scores
reminders over the non-fallback subset only and always prints `n_scored`
alongside. A precision number without its `n_scored` is not a number.

### Counters, not per-case averages

Scores accumulate corpus-level TP/FP/FN and divide once at the end. Per-case
recall is `0/0` on the most important case in the set — the one with no deadline
at all — and both ways of resolving that are wrong: `1.0` hides a model that
found nothing, `0.0` punishes a correct empty answer. With counters, the negative
case contributes only to FP, which is exactly why it exists.

An empty denominator reports `n/a`, never `0.0` and never `1.0`.

## Replay, and the thing replay cannot do

CI has no Ollama, so a live-only eval could never gate a merge. Responses are
recorded once and replayed deterministically.

**Replay cannot evaluate a prompt change.** The recorded response was produced by
whatever prompt was in effect when it was recorded. Replay discards the payload
the formatter builds, so editing `_SYSTEM` moves no metric at all — a CI gate
that did not know this would green-tick every prompt regression while appearing
to protect against them.

So each recording stores `prompt_sha`, a hash of the system prompt as actually
sent. If the prompt has since changed, the case is reported **STALE** and is not
scored. A prompt edit becomes a loud "re-record required" instead of a silent
pass.

What replay *does* gate is the deterministic half: fence-stripping, key
validation, category coercion, and both fallback paths. Those are worth gating
exactly because they are deterministic, so the gate is an **exact per-case
match** against `evals/baseline.json` rather than an aggregate threshold. With
this few cases a threshold would either flake on one case flipping or gate
nothing at all.

## Case status: approved

All 8 cases carry `"label_status": "approved"` — signed off 2026-08-26. Until
they were, the runner printed a warning on every run and treated the numbers as
the model measured against a guess. `is_labelled` gates on `approved`, and any
new case starts at `proposed`.

Three labels were genuinely contestable and were decided rather than assumed:

- `short-transcript-01` ("Buy milk.") — **is** a reminder, with
  `datetime_state: absent`. Note the consequence: `reminders.py` fires a dateless
  reminder immediately, so the approved label and the current behaviour
  disagree. That gap is a product bug this case now pins down. Labelling it
  *not* a reminder would have hidden the bug by defining it away.
- `no-deadline-negative-02` — **not** a reminder, despite containing the literal
  words "reminder to self" and "worth going back". So the model inventing
  "Return to Thai restaurant" and scheduling it for next Monday 9am stays a
  false positive, which is what holds precision at 0.857.
- `rambling-two-topics-01` — **Projects**, because the deadline-bearing half is
  the work half. The single-category schema is a real limitation here and this
  case records it.

## Run artifacts

Every run writes `evals/runs/<iso>.json`, and `--diff` compares the two most recent
— refusing when the case-set hash differs between them, because adding a case
shifts every aggregate and the difference would be new coverage reported as a
regression.

That directory is gitignored. The committed record is `evals/baseline.json`; run
history is local working state, and committing a file per run (CI included) would
be noise.

## What is not measured here

- **Audio → note.** This measures transcript → note. Users experience speech,
  and ASR errors propagate into what looks like LLM failure. Nothing here
  separates those.
- **Model quality in CI.** See replay, above.
- **Anything at n=8.** Eight cases is a regression smoke suite. It is enough to
  demonstrate the method and to catch a parser regression; it is not enough to
  support a claim about how good the model is. The confidence interval on a
  precision figure over six true positives is wide enough to swallow any
  prompt change worth detecting.
