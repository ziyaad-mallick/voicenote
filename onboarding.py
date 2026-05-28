from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label, RadioButton, RadioSet
from textual.containers import Vertical, Horizontal, Container
from textual.screen import Screen
from textual import on
from pathlib import Path
import config


class WelcomeScreen(Screen):
    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
    }

    #welcome-container {
        width: 70;
        height: auto;
        border: solid $accent;
        padding: 2 4;
    }

    #title {
        text-align: center;
        color: $accent;
        width: 100%;
        padding: 1 0;
    }

    #subtitle {
        text-align: center;
        width: 100%;
        color: $text-muted;
        padding: 1 0 2 0;
    }

    #form-container {
        width: 100%;
    }

    Input {
        margin: 1 0;
    }

    #button-row {
        width: 100%;
        height: auto;
        margin-top: 2;
    }

    Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="welcome-container"):
            yield Label("VOICENOTE", id="title")
            yield Label("On-device voice notes. No cloud. No accounts needed.", id="subtitle")
            with Vertical(id="form-container"):
                yield Input(placeholder="Your name (optional)", id="name-input")
                yield Input(placeholder="Email for reminders (optional)", id="email-input")
            with Horizontal(id="button-row"):
                yield Button("Continue →", variant="primary", id="welcome-continue")

    @on(Button.Pressed, "#welcome-continue")
    def on_continue(self) -> None:
        name = self.query_one("#name-input", Input).value
        email = self.query_one("#email-input", Input).value
        self.app.user_name = name
        self.app.user_email = email
        self.app.switch_screen("transcription")


class TranscriptionScreen(Screen):
    DEFAULT_CSS = """
    TranscriptionScreen {
        align: center middle;
    }

    #transcription-container {
        width: 70;
        height: auto;
        border: solid $accent;
        padding: 2 4;
    }

    #heading {
        color: $accent;
        width: 100%;
        text-align: center;
        margin-bottom: 2;
    }

    RadioSet {
        width: 100%;
        margin: 1 0;
    }

    RadioButton {
        margin: 1 0;
    }

    #button-row {
        width: 100%;
        height: auto;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="transcription-container"):
            yield Label("Choose transcription quality", id="heading")
            with RadioSet(id="model-radios"):
                yield RadioButton("Fast  — 140 MB  (good for quick notes)", id="model-base")
                yield RadioButton("Balanced  — 460 MB  (recommended)", id="model-small")
                yield RadioButton("Accurate  — 1.5 GB  (best quality)", id="model-medium")
            with Horizontal(id="button-row"):
                yield Button("Continue →", variant="primary", id="transcription-continue")

    def on_mount(self) -> None:
        self.query_one("#model-small", RadioButton).value = True

    @on(Button.Pressed, "#transcription-continue")
    def on_continue(self) -> None:
        radio_set = self.query_one(RadioSet)
        selected = radio_set.pressed_button
        if selected:
            model_map = {"model-base": "base", "model-small": "small", "model-medium": "medium"}
            self.app.whisper_model = model_map.get(selected.id, "small")
        self.app.switch_screen("categories")


class CategoriesScreen(Screen):
    DEFAULT_CSS = """
    CategoriesScreen {
        align: center middle;
    }

    #categories-container {
        width: 70;
        height: auto;
        border: solid $accent;
        padding: 2 4;
    }

    #heading {
        color: $accent;
        width: 100%;
        text-align: center;
        margin-bottom: 2;
    }

    #form-container {
        width: 100%;
    }

    Input {
        margin: 1 0;
    }

    #button-row {
        width: 100%;
        height: auto;
        margin-top: 2;
    }
    """

    DEFAULT_CATEGORIES = ["Projects", "Ideas", "Uni", "Personal"]

    def compose(self) -> ComposeResult:
        with Container(id="categories-container"):
            yield Label("Organise your notes into projects", id="heading")
            with Vertical(id="form-container"):
                for i, category in enumerate(self.DEFAULT_CATEGORIES):
                    yield Input(value=category, id=f"category-{i}")
            with Horizontal(id="button-row"):
                yield Button("Continue →", variant="primary", id="categories-continue")

    @on(Button.Pressed, "#categories-continue")
    def on_continue(self) -> None:
        categories = []
        for i in range(len(self.DEFAULT_CATEGORIES)):
            value = self.query_one(f"#category-{i}", Input).value.strip()
            if value:
                categories.append(value)
        self.app.categories = categories if categories else self.DEFAULT_CATEGORIES
        self.app.switch_screen("complete")


class CompleteScreen(Screen):
    DEFAULT_CSS = """
    CompleteScreen {
        align: center middle;
    }

    #complete-container {
        width: 70;
        height: auto;
        border: solid $accent;
        padding: 2 4;
    }

    #ready-message {
        color: $accent;
        width: 100%;
        text-align: center;
        margin-bottom: 2;
    }

    #summary {
        width: 100%;
        margin: 2 0;
    }

    .summary-line {
        margin: 1 0;
    }

    #button-row {
        width: 100%;
        height: auto;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="complete-container"):
            yield Label("VoiceNote is ready.", id="ready-message")
            with Vertical(id="summary"):
                if self.app.user_name:
                    yield Label(f"Name: {self.app.user_name}", classes="summary-line")
                yield Label(f"Transcription: {self._get_model_label()}", classes="summary-line")
                yield Label(f"Notes folder: {self._get_notes_dir()}", classes="summary-line")
            with Horizontal(id="button-row"):
                yield Button("Start recording →", variant="primary", id="complete-start")

    def _get_model_label(self) -> str:
        models = {
            "base": "Fast (140 MB)",
            "small": "Balanced (460 MB)",
            "medium": "Accurate (1.5 GB)",
        }
        return models.get(self.app.whisper_model, "Balanced (460 MB)")

    def _get_notes_dir(self) -> str:
        home = Path.home()
        return str(home / ".voicenote" / "notes")

    @on(Button.Pressed, "#complete-start")
    def on_start(self) -> None:
        cfg = config.get_default()

        cfg["user"]["name"] = self.app.user_name
        cfg["user"]["email"] = self.app.user_email
        cfg["whisper"]["model"] = self.app.whisper_model
        cfg["categories"] = self.app.categories

        config.save(cfg)
        self.app.exit()


class OnboardingApp(App):
    TITLE = "VoiceNote Onboarding"
    CSS = """
    Screen {
        background: $surface;
    }

    Button {
        margin: 0 1;
    }

    Input {
        border: solid $accent;
    }
    """

    def __init__(self):
        super().__init__()
        self.user_name = ""
        self.user_email = ""
        self.whisper_model = "small"
        self.categories = CategoriesScreen.DEFAULT_CATEGORIES.copy()

    def on_mount(self) -> None:
        self.install_screen(WelcomeScreen, "welcome")
        self.install_screen(TranscriptionScreen, "transcription")
        self.install_screen(CategoriesScreen, "categories")
        self.install_screen(CompleteScreen, "complete")
        self.switch_screen("welcome")


def main():
    app = OnboardingApp()
    app.run()


if __name__ == "__main__":
    main()
