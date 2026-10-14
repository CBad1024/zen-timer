from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class DurationDialog(ModalScreen[int | None]):
    """Popup asking for a duration in hours, minutes and seconds.

    Dismisses with the total in seconds, or None if cancelled.
    """

    DEFAULT_CSS = """
    DurationDialog {
        align: center middle;
        background: $background 60%;
    }

    #dialog {
        width: 44;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #dialog-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
    }

    #fields {
        height: auto;
        margin-top: 1;
    }

    .field {
        width: 1fr;
        height: auto;
    }

    .field Label {
        width: 100%;
        content-align: center middle;
        color: $text-muted;
    }

    .field Input {
        width: 100%;
        margin: 0;
    }

    #dialog-error {
        width: 100%;
        content-align: center middle;
        color: $error;
        height: 1;
    }

    #dialog-buttons {
        height: auto;
        align: center middle;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, title: str, seconds: int) -> None:
        super().__init__()
        self.title_text = title
        self.initial = seconds

    def compose(self) -> ComposeResult:
        hours, rest = divmod(self.initial, 3600)
        minutes, seconds = divmod(rest, 60)
        with Vertical(id="dialog"):
            yield Static(self.title_text, id="dialog-title")
            with Horizontal(id="fields"):
                for name, value in (("hours", hours), ("minutes", minutes), ("seconds", seconds)):
                    with Vertical(classes="field"):
                        yield Label(name.capitalize())
                        yield Input(str(value), id=name, type="integer", select_on_focus=True)
            yield Static("", id="dialog-error")
            with Horizontal(id="dialog-buttons"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#minutes", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "save":
            self.save()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def save(self) -> None:
        try:
            hours, minutes, seconds = (
                int(self.query_one(f"#{name}", Input).value or 0)
                for name in ("hours", "minutes", "seconds")
            )
        except ValueError:
            return self.show_error("Enter whole numbers only")
        if min(hours, minutes, seconds) < 0:
            return self.show_error("Values can't be negative")
        total = hours * 3600 + minutes * 60 + seconds
        if total <= 0:
            return self.show_error("Duration must be more than 0")
        self.dismiss(total)

    def show_error(self, message: str) -> None:
        self.query_one("#dialog-error", Static).update(message)
