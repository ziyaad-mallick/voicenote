import EvalApp from '@/components/EvalApp';
import { loadEvalData } from './data';

const REPO = 'https://github.com/ziyaad-mallick/voicenote';

function Header() {
  return (
    <header>
      <p className="font-mono text-xs dim tracking-wider uppercase">
        voicenote — evaluation harness
      </p>
      <h1 className="mt-4 text-3xl sm:text-4xl font-semibold tracking-tight max-w-3xl leading-tight">
        The metric found the bug. Fixing the bug made the metric blind.
      </h1>
      <p className="mt-5 max-w-3xl leading-relaxed">
        <strong>voicenote</strong> is a local-only voice-to-structured-note tool: microphone →
        Vosk speech recognition → a local Ollama model → a Markdown note plus scheduled
        reminders. Nothing leaves the machine.
      </p>
      <div
        className="mt-5 max-w-3xl border-l-2 pl-5 py-1"
        style={{ borderColor: 'var(--rule-strong)' }}
      >
        <p className="leading-relaxed">
          <strong>This page is not the app running.</strong> voicenote cannot run here: Vosk is a
          40&nbsp;MB native package and Ollama is a local server. Nothing on this page transcribes
          audio or calls a model. What you are looking at is the project&apos;s{' '}
          <span className="font-mono text-[13px]">evals/</span> harness — a recorded run, replayed,
          re-scored in your browser — and the scheduling bug the harness&apos;s metric design
          exposed.
        </p>
        <p className="mt-3 leading-relaxed">
          <strong>The bug is fixed, and the numbers below are the run after the fix.</strong>{' '}
          Datetime accuracy went 0.250 → 0.875 and reminder precision 0.800 → 1.000. The more
          useful result is what that exposed: the metric answers “can the scheduler use this
          string”, never “is this the right moment”, and now that everything parses, that is the
          only question left.
        </p>
      </div>
    </header>
  );
}

function Provenance({ data }) {
  const rows = [
    ['pinned now', data.pinned_now],
    ['case_set_hash', data.case_set_hash],
    ['prompt_sha', data.prompt_sha],
    ['categories', (data.categories || []).join(', ')],
    ['cases', String((data.cases || []).length)],
  ];
  return (
    <dl className="mt-10 grid gap-x-8 gap-y-2 sm:grid-cols-2 max-w-3xl text-[13px]">
      {rows.map(([k, v]) => (
        <div key={k} className="flex gap-3 border-b rule py-1.5">
          <dt className="dim font-mono text-[11px] uppercase tracking-wider w-40 shrink-0 pt-0.5">
            {k}
          </dt>
          <dd className="font-mono break-all">{v ?? 'n/a'}</dd>
        </div>
      ))}
    </dl>
  );
}

function Footer({ data }) {
  return (
    <footer className="border-t rule mt-20 pt-8 pb-20 max-w-3xl">
      <h2 className="text-sm font-semibold uppercase tracking-wider dim">What this is not</h2>
      <ul className="mt-4 space-y-3 leading-relaxed">
        <li>
          <strong>n=8 is a regression suite, not a benchmark.</strong> Eight cases are enough to
          demonstrate the method and to catch a parser regression. They are not enough to support
          a claim about how good the model is — the confidence interval on a precision figure over
          six true positives would swallow any prompt change worth detecting.
        </li>
        <li>
          <strong>The labels are human-signed-off,</strong> not derived. Every case carries{' '}
          <span className="font-mono text-[13px]">label_status: approved</span>; until they were
          approved the runner treated the numbers as the model measured against a guess. Three
          labels were genuinely contestable and were decided rather than assumed — each one&apos;s
          reasoning is in its case note above.
        </li>
        <li>
          <strong>The numbers come from a recorded run</strong> against{' '}
          <span className="font-mono text-[13px]">goekdenizguelmez/JOSIEFIED-Qwen3</span>, replayed
          deterministically so the same inputs always produce the same score. Time is pinned to{' '}
          <span className="font-mono text-[13px]">{data.pinned_now ?? 'n/a'}</span>, because
          &ldquo;is this datetime in the future?&rdquo; is otherwise a different question every day.
        </li>
        <li>
          <strong>Replay cannot evaluate a prompt change.</strong> A recorded response was produced
          by the prompt in effect when it was recorded, so each recording stores a{' '}
          <span className="font-mono text-[13px]">prompt_sha</span> and a case whose prompt has
          since changed is reported stale rather than silently scored.
        </li>
        <li>
          <strong>Audio → note is not measured here.</strong> This measures transcript → note.
          Users experience speech, and ASR errors propagate into what looks like an LLM failure.
        </li>
      </ul>
      <p className="mt-8 font-mono text-[13px]">
        <a
          href={REPO}
          className="underline underline-offset-4"
          style={{ textDecorationColor: 'var(--rule-strong)' }}
        >
          github.com/ziyaad-mallick/voicenote
        </a>
      </p>
      <p className="mt-2 text-xs dim">
        Harness and metric rationale: <span className="font-mono">evals/README.md</span> in the
        repository. Source of these numbers:{' '}
        <span className="font-mono">public/eval-data.json</span>, generated by{' '}
        <span className="font-mono">python -m evals.export_web</span>.
      </p>
    </footer>
  );
}

function MissingData() {
  return (
    <section className="border rule rounded-md p-6 mt-12 max-w-3xl">
      <h2 className="font-semibold">No exported run present</h2>
      <p className="mt-3 leading-relaxed">
        <span className="font-mono text-[13px]">public/eval-data.json</span> is not in this build.
        This page renders no metrics rather than placeholder ones — a page about measurement
        should not invent its own numbers.
      </p>
      <p className="mt-3 leading-relaxed">
        Generate it from the repository root and rebuild:
      </p>
      <pre className="mt-3 font-mono text-[13px] sunk rounded-md p-4 overflow-x-auto">
        python -m evals.export_web{'\n'}npm run build
      </pre>
    </section>
  );
}

export default function Page() {
  const data = loadEvalData();
  return (
    <main className="mx-auto max-w-5xl px-6 sm:px-10 py-16 sm:py-24">
      <Header />
      {data ? (
        <>
          <Provenance data={data} />
          <EvalApp data={data} />
          <Footer data={data} />
        </>
      ) : (
        <MissingData />
      )}
    </main>
  );
}
