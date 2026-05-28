"""
VoiceNote — on-device audio note-taking with Whisper + Ollama.

Controls:
    SPACE / R   — start / stop recording
    Q / Ctrl-C  — quit
    D           — toggle DOCX export
    O           — open notes folder in Explorer
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, RichLog, Static

import config as cfg_module
import recorder as rec_module
import transcriber
import formatter
import writer
import reminders as rem_module


CFG: dict = {}
RECORDER: rec_module.Recorder | None = None

_BAR_CHARS = " ▁▂▃▄▅▆▇█"


def _rms_to_bar(rms: float, width: int = 32) -> str:
    filled = int(rms * width * 12)
    bar = ""
    for _ in range(width):
        idx = min(filled, 8)
        bar += _BAR_CHARS[idx]
        filled = max(0, filled - 8)
    return bar


class WaveBar(Static):
    rms: reactive[float] = reactive(0.0)

    def render(self) -> str:
        if not RECORDER.is_recording:
            return "[dim]" + ("─" * 32) + "[/dim]"
        bar = _rms_to_bar(self.rms, 32)
        return f"[bold red]{bar}[/bold red]"


class StatusLine(Static):
    state: reactive[str] = reactive("idle")
    elapsed: reactive[float] = reactive(0.0)

    def render(self) -> str:
        if self.state == "idle":
            return "[dim]Idle  —  press [bold]SPACE[/bold] to start recording[/dim]"
        if self.state == "recording":
            t = int(self.elapsed)
            return f"[bold red]● REC[/bold red]  {t // 60:02d}:{t % 60:02d}  —  press [bold]SPACE[/bold] to stop"
        if self.state == "transcribing":
            return "[yellow]Transcribing with Whisper…[/yellow]"
        if self.state == "formatting":
            return "[yellow]Formatting with Ollama…[/yellow]"
        if self.state == "saving":
            return "[green]Saving note…[/green]"
        if self.state == "done":
            return "[bold green]✓ Note saved![/bold green]"
        if self.state == "error":
            return "[bold red]Error — see log below[/bold red]"
        return self.state


class VoiceNoteApp(App):
    CSS = """
    Screen {
        background: $surface;
    }
    #panel {
        border: round $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    #title-label {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #wave {
        height: 1;
        margin: 0 0 1 0;
    }
    #status {
        height: 1;
        margin-bottom: 1;
    }
    #last-note {
        color: $text-muted;
        height: auto;
        margin-top: 1;
    }
    #log {
        margin: 0 2 1 2;
        height: 12;
        border: round $surface-lighten-2;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_recording", "Record/Stop", show=True),
        Binding("r", "toggle_recording", "Record/Stop", show=False),
        Binding("d", "toggle_docx", "Toggle DOCX", show=True),
        Binding("o", "open_folder", "Open Folder", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    docx_enabled: reactive[bool] = reactive(False)
    _recording_start: float = 0.0
    _last_note_path: Path | None = None
    _processing = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Vertical(
                Label("VoiceNote", id="title-label"),
                WaveBar(id="wave"),
                StatusLine(id="status"),
                Label("", id="last-note"),
            ),
            id="panel",
        )
        yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self):
        self._wave_timer = self.set_interval(0.05, self._update_wave)
        self._elapsed_timer = self.set_interval(0.5, self._update_elapsed)
        name = CFG.get("user", {}).get("name", "")
        if name:
            self._log(f"Welcome back, [bold]{name}[/bold]")
        else:
            self._log("VoiceNote started. Press [bold]SPACE[/bold] to record.")
        self._log(f"Model: [cyan]{CFG['ollama']['model']}[/cyan]")
        self._log(
            f"Whisper: [cyan]{CFG['whisper']['model']}[/cyan]  |  "
            f"Notes: [cyan]{CFG['notes_dir']}[/cyan]"
        )

    # ── Reactive update helpers ──────────────────────────────────────────────

    def _update_wave(self):
        wave = self.query_one("#wave", WaveBar)
        wave.rms = RECORDER.get_rms()

    def _update_elapsed(self):
        if RECORDER.is_recording:
            status = self.query_one("#status", StatusLine)
            status.elapsed = time.time() - self._recording_start

    def _log(self, msg: str):
        self.query_one("#log", RichLog).write(msg)

    def _set_state(self, state: str):
        self.query_one("#status", StatusLine).state = state

    # ── Actions ─────────────────────────────────────────────────────────────

    def action_toggle_recording(self):
        if self._processing:
            return
        if RECORDER.is_recording:
            self._stop_and_process()
        else:
            self._start_recording()

    def action_toggle_docx(self):
        self.docx_enabled = not self.docx_enabled
        state = "ON" if self.docx_enabled else "OFF"
        self._log(f"DOCX export: [bold]{state}[/bold]")

    def action_open_folder(self):
        folder = CFG["notes_dir"]
        if folder.exists():
            subprocess.Popen(["explorer", str(folder)])
        else:
            self._log(
                "[yellow]Notes folder does not exist yet — record a note first.[/yellow]"
            )

    # ── Recording flow ───────────────────────────────────────────────────────

    def _start_recording(self):
        RECORDER.start()
        self._recording_start = time.time()
        self._set_state("recording")
        self._log("[red]Recording started…[/red]")

    def _stop_and_process(self):
        audio = RECORDER.stop()
        elapsed = time.time() - self._recording_start
        self._log(f"Recording stopped — {elapsed:.1f}s captured")
        min_samples = int(CFG["audio"]["sample_rate"] * 0.5)
        if len(audio) < min_samples:
            self._log("[yellow]Too short — nothing to transcribe.[/yellow]")
            self._set_state("idle")
            return
        self._processing = True
        thread = threading.Thread(target=self._process, args=(audio,), daemon=True)
        thread.start()

    def _process(self, audio):
        try:
            self._set_state("transcribing")
            backend = CFG["whisper"].get("backend", "whisper")
            self._log(f"Transcribing via [cyan]{backend}[/cyan]…")
            transcript = transcriber.transcribe(
                audio,
                sample_rate=CFG["audio"]["sample_rate"],
                model_size=CFG["whisper"]["model"],
                language=CFG["whisper"]["language"],
                device=CFG["whisper"]["device"],
                compute_type=CFG["whisper"]["compute_type"],
                backend=backend,
            )
            if not transcript:
                self._log("[yellow]No speech detected.[/yellow]")
                self._set_state("idle")
                return
            preview = transcript[:120] + ("…" if len(transcript) > 120 else "")
            self._log(f"Transcript: [italic]{preview}[/italic]")

            self._set_state("formatting")
            self._log("Sending to Ollama…")
            note = formatter.format_note(
                transcript,
                categories=CFG["categories"],
                ollama_host=CFG["ollama"]["host"],
                model=CFG["ollama"]["model"],
            )
            if "_fallback_reason" in note:
                self._log(
                    f"[yellow]LLM unavailable ({note['_fallback_reason']}), "
                    "saving raw transcript.[/yellow]"
                )

            self._set_state("saving")
            md_path = writer.write_markdown(note, CFG["notes_dir"])
            self._last_note_path = md_path
            self._log(f"Saved: [bold green]{md_path}[/bold green]")

            if self.docx_enabled or CFG["output"].get("docx"):
                docx_path = writer.write_docx(note, CFG["notes_dir"])
                self._log(f"DOCX:  [bold green]{docx_path}[/bold green]")

            self._update_last_note_label(note, md_path)

            if note.get("reminders"):
                rem_module.schedule_reminders(note["reminders"], note["title"])
                for r in note["reminders"]:
                    self._log(f"Reminder set: {r['text']} @ {r['datetime']}")

            self._set_state("done")

        except Exception as exc:
            self._log(f"[bold red]Error: {exc}[/bold red]")
            self._set_state("error")
        finally:
            self._processing = False
            threading.Timer(3.0, lambda: self._set_state("idle")).start()

    def _update_last_note_label(self, note: dict, path: Path):
        label = self.query_one("#last-note", Label)
        label.update(
            f"Last note: [bold]{note['title']}[/bold]  ›  "
            f"[cyan]{note['category']}[/cyan]  ·  {path.name}"
        )


def main():
    global CFG, RECORDER
    if cfg_module.is_first_run():
        from onboarding import OnboardingApp
        OnboardingApp().run()
    CFG = cfg_module.load()
    RECORDER = rec_module.Recorder(
        sample_rate=CFG["audio"]["sample_rate"],
        channels=CFG["audio"]["channels"],
    )
    VoiceNoteApp().run()


if __name__ == "__main__":
    main()
