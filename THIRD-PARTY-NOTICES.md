# Third-party notices

voicenote is MIT-licensed (see [LICENSE](LICENSE)). It depends on the packages below,
plus one downloaded model. Versions are the minimums pinned in `requirements.txt`;
licences were verified against each project's own licence file or PyPI classifier
metadata, not guessed.

## Runtime dependencies (pip-installed)

| package | version | licence | upstream |
|---|---|---|---|
| [vosk](https://github.com/alphacep/vosk-api) | >=0.3.45 | Apache-2.0 | github.com/alphacep/vosk-api |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | >=1.0.3 | MIT | github.com/SYSTRAN/faster-whisper |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | >=0.5.0 | MIT | github.com/spatialaudio/python-sounddevice |
| [textual](https://github.com/Textualize/textual) | >=0.80.0 | MIT | github.com/Textualize/textual |
| [python-docx](https://github.com/python-openxml/python-docx) | >=1.1.0 | MIT | github.com/python-openxml/python-docx |
| [PyYAML](https://github.com/yaml/pyyaml) | >=6.0 | MIT | github.com/yaml/pyyaml |
| [winotify](https://github.com/versa-syahptr/winotify) | >=1.1.0 | MIT | github.com/versa-syahptr/winotify |
| [numpy](https://github.com/numpy/numpy) | >=1.26.0 | BSD-3-Clause (a few vendored components under 0BSD/MIT/Zlib/CC0-1.0) | github.com/numpy/numpy |
| [scipy](https://github.com/scipy/scipy) | >=1.13.0 | BSD-3-Clause | github.com/scipy/scipy |
| [requests](https://github.com/psf/requests) | >=2.31.0 | Apache-2.0 | github.com/psf/requests |
| [python-dateutil](https://github.com/dateutil/dateutil) | >=2.9.0 | Dual: Apache-2.0 or BSD-3-Clause, your choice | github.com/dateutil/dateutil |
| [keyboard](https://github.com/boppreh/keyboard) | >=0.13.5 | MIT | github.com/boppreh/keyboard |

All are pip-installed, not vendored — nothing above ships inside this repo.

Note: `keyboard` is listed in `requirements.txt` but is not imported anywhere in the
current codebase (checked by grepping `*.py` for `import keyboard`). It appears to be
an unused dependency. Also, `requirements.txt` and `pyproject.toml` disagree:
`pyproject.toml`'s `dependencies` list is missing both `vosk` and `keyboard`, even
though `vosk` is imported unconditionally by `transcriber.py` and is the default ASR
backend — `pip install .` from `pyproject.toml` alone would not install it.
`requirements.txt` is the complete list. Flagging, not fixing — outside this task's
scope and `pyproject.toml`/dependency changes are explicitly out of bounds.

### Dev-only, not shipped

`pytest>=8.0` (MIT, github.com/pytest-dev/pytest) is a `[project.optional-dependencies]`
dev extra — installed for testing/CI, never required to run the app.

### Optional, not declared

`transcriber.py`'s `groq` backend does a bare `import groq` inside a `try/except
ImportError`. The `groq` package (Apache-2.0, github.com/groq/groq-python) is not in
`requirements.txt` or `pyproject.toml` — if it isn't installed, or `GROQ_API_KEY` isn't
set, the backend silently falls back to `vosk`. Nothing extra to install unless you want
that backend.

## Downloaded at runtime (not bundled)

| what | licence | fetched by | where it lands |
|---|---|---|---|
| [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models) (~40MB) | Apache-2.0 | `transcriber.ensure_vosk_model()`, on first recording | `~/.voicenote/models/vosk-small-en/` |
| Whisper model weights (via faster-whisper / CTranslate2) | MIT (OpenAI's original Whisper weights are MIT-licensed; faster-whisper's converted copies inherit that) | `faster_whisper.WhisperModel(...)`, on first use of the `whisper` backend | faster-whisper's own Hugging Face cache (outside `~/.voicenote`) |

Neither model is bundled in this repository or in the pip packages above — both are
fetched over the network the first time their code path runs, per the README's ASR
backend table.
