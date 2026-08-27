# voicenote

[![tests](https://github.com/ziyaad-mallick/voicenote/actions/workflows/tests.yml/badge.svg)](https://github.com/ziyaad-mallick/voicenote/actions/workflows/tests.yml)

**Talk. Get a structured note. Nothing leaves the machine.**

Hold space, say what you're thinking, let go. A local ASR model turns it into text, a local LLM turns
the text into a titled, categorised, tagged Markdown note — and if you mentioned a deadline, a
reminder gets scheduled. No account, no API key, no network.

It's a terminal app, so it starts in about a second and lives in the corner of a tmux pane.

```
  SPACE / R   start / stop recording
  D           toggle DOCX export
  O           open the notes folder
  Q           quit
```

---

## Why it's built this way

The interesting problem here was never the model. It was everything around it:

- **The 40MB download.** Vosk's small English model is fetched on first run into
  `~/.voicenote/models/` with a progress callback, then never again. A tool that makes you go find a
  model file yourself is a tool nobody uses twice.
- **Cold start.** Both the Vosk model and the Whisper model are cached in module-level globals after
  first load, because paying model-init cost on every note makes a 4-second note take 15 seconds.
- **What the small model gets wrong that the big one doesn't.** This is why there are three ASR
  backends rather than one — see below.
- **Degrading instead of failing.** If Ollama isn't running, the note still saves. The formatter
  returns a `_fallback_reason` and the raw transcript gets written to disk. Losing a thought because
  a daemon was down is the one unacceptable failure for a note-taking tool.

## The pipeline

```
  mic ──> recorder.py ──> transcriber.py ──> formatter.py ──> writer.py ──> ~/Documents/VoiceNotes
          sounddevice     Vosk small-en      Ollama           Markdown
          16kHz mono      (offline)          (local)          + optional DOCX
                                                  │
                                                  └──> reminders.py (Windows notifications)
```

`formatter.py` asks the local model for strict JSON — `title`, `category`, `summary`, `body`,
`tags`, `reminders` — and the category is constrained to the list in your config, so notes stay
filed in a taxonomy you chose rather than one the model invents each time.

## ASR backends

Configurable in `~/.voicenote/config.yaml` under `whisper.backend`:

| backend  | what it is                        | offline | notes                                  |
|----------|-----------------------------------|---------|----------------------------------------|
| `vosk`   | Vosk small-en-us-0.15, 40MB       | yes     | **default.** Fast, small, no GPU       |
| `whisper`| faster-whisper, int8 on CPU       | yes     | more accurate, noticeably slower       |
| `groq`   | whisper-large-v3-turbo over API   | no      | reference quality, for comparison only |

The default path is fully offline. `groq` exists so there's a ceiling to measure the local backends
against — it falls back to `vosk` automatically if `GROQ_API_KEY` isn't set, so the offline promise
holds even if you leave it configured.

## Setup

Requires Python 3.11+, a working microphone, and [Ollama](https://ollama.com) running locally.

```bash
git clone https://github.com/ziyaad-mallick/voicenote && cd voicenote
pip install -r requirements.txt
ollama pull goekdenizguelmez/JOSIEFIED-Qwen3   # or any local model you prefer
python main.py
```

First run walks you through a short onboarding and writes `~/.voicenote/config.yaml`. The Vosk model
downloads on the first recording.

Any Ollama model works — point `ollama.model` at whatever you have pulled.

## Configuration

`~/.voicenote/config.yaml`:

```yaml
notes_dir: "~/Documents/VoiceNotes"
categories: [Projects, Ideas, Uni, Personal]   # the model must pick from these
ollama:
  host: "http://localhost:11434"
  model: "goekdenizguelmez/JOSIEFIED-Qwen3:latest"
whisper:
  backend: "vosk"        # vosk | whisper | groq
output:
  markdown: true
  docx: false
```

## Tests and evals

```bash
pytest                 # the whole suite
python -m evals.run    # the eval, in replay mode
```

`pytest` installs with `requirements.txt`, and the suite needs no microphone, no model
download and no network — every external boundary is mocked at the call site, and `vosk` is
imported lazily so the tests run without the ASR stack present.

The evals are the more interesting half. `evals/` measures the transcript → note path:
category accuracy, schema conformance, fallback rate split by cause, and reminder
precision and recall reported separately. The first live run scored **0.86 precision and
0.67 recall on reminder extraction, and 0.17 on datetime accuracy** — five of the six
reminders it got right fire a notification the instant the note is saved rather than when
the thing is due, because the model hallucinates a year three years in the past when the
transcript does not give one. It also invented an obligation from a note about a restaurant
being good, and scheduled it for next Monday at 9am.

That result is the argument for how the metrics are shaped, and
[evals/README.md](evals/README.md) is the long version: why fallbacks are excluded from
precision, why counters beat per-case averages, and why a replayed response can gate the
parser but can never evaluate a prompt change.

Eight cases, labels signed off. That is a regression suite, not a benchmark: enough to
demonstrate the method and catch a parser regression, not enough to support a claim about
how good the model is.

## Status

Built May 2026. Windows-first — the reminder layer uses `winotify` and `O` opens Explorer; the rest
of the pipeline is platform-neutral and the recorder/transcriber/formatter path should run anywhere
`sounddevice` does.

There's a Flutter port of the same idea for Android in
[ramble](https://github.com/ziyaad-mallick/ramble), using on-device Gemma instead of Ollama.

MIT. See [LICENSE](LICENSE). Third-party licences: [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
