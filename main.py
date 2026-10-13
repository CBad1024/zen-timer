from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Button, Static, Input
from textual.reactive import reactive
from textual.theme import Theme

from alarm import AlarmPlayer
from night_sky import NightSky

SCENE_THEME = "rose-pine-moon"


class TimeDisplay(Static):
    """A widget to display the timer."""
    time_left = reactive(25 * 60)

    def render(self) -> str:
        minutes, seconds = divmod(self.time_left, 60)
        return f"{minutes:02d}:{seconds:02d}"


class ZenTimerApp(App):
    """A simple Pomodoro timer TUI."""

    CSS = """
    Screen {
        align: center middle;
        layers: sky ui;
        overflow: hidden;
    }

    NightSky {
        layer: sky;
        width: 100%;
        height: 1fr;
        margin: 1 0;
    }

    Header, Footer, #timer-container {
        layer: ui;
    }
    
    #timer-container {
        layout: vertical;
        align: center middle;
        height: auto;
        width: 40;
        border: solid $warning;
        background: $surface;
        padding: 1 2;
    }
    
    TimeDisplay {
        content-align: center middle;
        text-style: bold;
        padding: 1;
        width: 100%;
    }

    #phase-label {
        content-align: center middle;
        text-style: bold;
        color: $warning;
        width: 100%;
    }

    #timer-container.break-phase {
        border: solid $success;
    }

    #timer-container.break-phase #phase-label {
        color: $success;
    }

    Horizontal {
        align: center middle;
        height: auto;
        width: 100%;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
    }
    
    Input {
        margin-top: 1;
        width: 100%;
    }
    """

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("s", "cycle_sound", "Change sound"),
        ("q", "quit", "Quit app"),
    ]

    time_left = reactive(25 * 60)
    running = reactive(False)
    phase = reactive("focus")

    def __init__(self):
        super().__init__()
        self.timer_task = None
        self.focus_time = 25 * 60
        self.break_time = 5 * 60
        self.alarm = AlarmPlayer(terminal_bell=self.bell)

    @property
    def current_duration(self) -> int:
        """The full duration (in seconds) of the current phase."""
        return self.focus_time if self.phase == "focus" else self.break_time

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        self.sky = NightSky()
        yield self.sky
        yield Header()
        with Container(id="timer-container") as container:
            self.container = container
            self.phase_label = Static("FOCUS", id="phase-label")
            yield self.phase_label
            self.time_display = TimeDisplay()
            yield self.time_display
            with Horizontal():
                self.start_button = Button("Start", id="start", variant="warning")
                yield self.start_button
                yield Button("Stop", id="stop", variant="error")
                yield Button("Reset", id="reset", variant="primary")
            yield Input(placeholder="Set focus minutes (e.g. 25)", id="time-input", type="integer")
        yield Footer()

    def on_mount(self) -> None:
        """Event handler called when app is mounted."""
        self.update_timer()
        self.timer_task = self.set_interval(1, self.tick, pause=True)
        self.theme_changed_signal.subscribe(self, self.on_theme_changed)
        self.theme = SCENE_THEME

    def on_theme_changed(self, theme: Theme) -> None:
        """Only show the moonlit scene for the theme it was drawn for."""
        self.sky.display = theme.name == SCENE_THEME

    def watch_time_left(self, time_left: int) -> None:
        """Called when time_left is modified."""
        self.time_display.time_left = time_left
        self.update_moon()

    def update_moon(self) -> None:
        """Wane the moon from full to new as the current phase counts down."""
        self.sky.progress = 1 - self.time_left / self.current_duration

    def watch_phase(self, phase: str) -> None:
        """Called when phase is modified."""
        self.phase_label.update(phase.upper())
        self.container.set_class(phase == "break", "break-phase")
        self.start_button.variant = "success" if phase == "break" else "warning"

    def tick(self) -> None:
        """Update the timer by one second."""
        if self.time_left > 0:
            self.time_left -= 1
        else:
            self.running = False
            self.timer_task.pause()
            self.alarm.play()
            self.advance_phase()

    def advance_phase(self) -> None:
        """Switch between focus and break; user must press Start to begin it."""
        self.phase = "break" if self.phase == "focus" else "focus"
        self.time_left = self.current_duration

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        button_id = event.button.id
        if button_id == "start":
            self.start_timer()
        elif button_id == "stop":
            self.stop_timer()
        elif button_id == "reset":
            self.reset_timer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Event handler for when user submits new focus duration."""
        try:
            minutes = int(event.value)
            if minutes > 0:
                self.focus_time = minutes * 60
                if self.phase == "focus":
                    self.reset_timer()
                event.input.value = ""
        except ValueError:
            pass

    def action_cycle_sound(self) -> None:
        """Switch to the next alarm sound and play it as a preview."""
        name = self.alarm.cycle()
        self.alarm.play()
        self.notify(f"Alarm sound: {name}", timeout=2)

    def on_unmount(self) -> None:
        self.alarm.stop()

    def start_timer(self) -> None:
        self.alarm.stop()
        self.running = True
        self.timer_task.resume()

    def stop_timer(self) -> None:
        self.running = False
        self.timer_task.pause()

    def reset_timer(self) -> None:
        self.running = False
        self.timer_task.pause()
        self.time_left = self.current_duration

    def update_timer(self):
        self.time_display.time_left = self.time_left

if __name__ == "__main__":
    app = ZenTimerApp()
    app.run()
