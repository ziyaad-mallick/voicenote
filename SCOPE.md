# Scope

What voicenote actually does today, verified by reading the code and running the
suite — not by reading the README.

## What it does today

`python -m pytest -q` passes all 54 tests in under a second, offline — no mic, no
Ollama, no network, no real model file (`tests/conftest.py` resets the two cached
ASR-model globals around every test; every network/hardware boundary is mocked at
the call site, see each test file's own docstring). The README's "offline" and
"tested" claims hold.

The product is a Textual terminal app (`main.py`). `SPACE`/`R` starts and stops a
mic recording (`recorder.py`, `sounddevice`, 16kHz mono float32), the audio goes to
`transcriber.transcribe()`, then to `formatter.format_note()` (an Ollama chat call
asking for strict JSON — title/category/summary/body/tags/reminders), then to
`writer.write_markdown()` and optionally `write_docx()`
(`writer.py:19`, `:56`). `D` toggles DOCX export, `O` shells out to Explorer on the
notes folder, `Q` quits.

Three ASR backends exist behind one `transcribe(backend=...)` call
(`transcriber.py:133`): `vosk` (default — small-en model, downloaded on first
recording into `~/.voicenote/models/vosk-small-en/`, cached in a module-level
global after that), `whisper` (`faster-whisper`, heavier, more accurate), and
`groq` (hosted API, falls back to `vosk` automatically if `groq` isn't installed or
`GROQ_API_KEY` isn't set — `transcriber.py:99-109`). If Ollama is unreachable or
returns something that doesn't parse, `formatter.format_note()` doesn't raise — it
returns the raw transcript with a `_fallback_reason` and `writer.py` still saves it
(`formatter.py:56-67`, tested explicitly in `test_formatter.py`). Reminders extracted
from a transcript fire as Windows toast notifications, immediately if the parsed
datetime is missing/past/unparsable, or via `threading.Timer` if it's in the future
(`reminders.py`).

## Who this is actually useful to, right now

The author, on his own Windows machine, with Ollama already running and a model
already pulled. Someone reading the code to judge engineering quality is the other
real audience — the test suite is written for that reader (docstrings state the
public claim each file is proving, not just what the code does).

It is not yet useful to a stranger who just wants voice notes. There's no
installer: `git clone` → `pip install -r requirements.txt` → install and start
Ollama yourself → `ollama pull <model>` → `python main.py` → sit through onboarding.
Skip any step and the failure is quiet rather than blocking — e.g. no Ollama running
doesn't error, it silently degrades to raw transcripts (which is the intended
behavior, per `README.md`'s "Degrading instead of failing" section, but it means a
new user never finds out formatting isn't happening unless they read the log line).

## What's stubbed or misleading

- **The onboarding "transcription quality" screen is inert.** `onboarding.py`'s
  `TranscriptionScreen` (`onboarding.py:75-131`) lets a new user pick Fast/Balanced
  /Accurate (140MB/460MB/1.5GB), and `CompleteScreen.on_start` writes that choice
  into `cfg["whisper"]["model"]` (`onboarding.py:256`). But it never touches
  `cfg["whisper"]["backend"]`, which comes from `config.get_default()` and is
  always `"vosk"` (`config.py:28`). Vosk's small model size isn't configurable and
  ignores `whisper.model` entirely (`transcriber.py:18-58`). So every new user is
  asked to make a choice that has no effect until they manually edit
  `~/.voicenote/config.yaml` to switch `whisper.backend` to `"whisper"` — something
  the app never tells them is necessary.
- **`pyproject.toml` and `requirements.txt` disagree.** `pyproject.toml`'s
  `dependencies` list is missing `vosk` and `keyboard`, even though `vosk` is
  imported unconditionally by `transcriber.py` and is the default backend.
  `pip install .` (the `pyproject.toml` path) would not install it; only
  `pip install -r requirements.txt` gets a working environment. See
  `THIRD-PARTY-NOTICES.md` for the full breakdown.
- **`keyboard` is an unused dependency.** Nothing in the current codebase imports
  it (checked by grep). It's declared in `requirements.txt` with no code behind it.
- **The `groq` backend isn't a real install path.** The `groq` package isn't
  declared anywhere; it's a bare `import groq` inside a `try/except`
  (`transcriber.py:106-109`). It works if you happen to `pip install groq`
  yourself, otherwise it's just a documented dead end.
- **The CI badge is unpopulated until this branch is pushed.**
  `.github/workflows/tests.yml` runs `pytest -m "not hardware"` on `windows-latest`
  / Python 3.11 on push/PR, and the local run above is what that job will do — but
  it has never executed on GitHub, because nothing has been pushed yet. The badge
  on `README.md` will show "no status" until the first push runs it once.

## The smallest next change that gets it there

Not an installer — that's a real project on its own, and this repo doesn't need to
be a downloadable consumer product to be honest about what it is.

The smallest change with real leverage: make `TranscriptionScreen`'s choice
actually do something. Either (a) have `CompleteScreen.on_start` set
`cfg["whisper"]["backend"] = "whisper"` when the user picks anything other than the
default, so the onboarding question maps to a real decision, or (b) if vosk-only is
the intended default experience, drop the quality-tier screen from onboarding
entirely rather than asking a new user to make a choice that's silently discarded.
Either fix removes the one place where the running app currently asks for input it
doesn't use — everything else in the pipeline (recording, transcription, Ollama
formatting, reminders, DOCX) already does what the README says it does.
