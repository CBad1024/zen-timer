from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Button, Static
from textual.reactive import reactive
from textual.theme import Theme

from alarm import AlarmPlayer
from duration_dialog import DurationDialog
from night_sky import NightSky

SCENE_THEME = "rose-pine-moon"


class TimeDisplay(Static):
    """A widget to display the timer."""
    time_left = reactive(25 * 60)

    def render(self) -> str:
        hours, rest = divmod(self.time_left, 3600)
        minutes, seconds = divmod(rest, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
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
        /* Size to the label so it sits exactly centered (no odd leftover cell) */
        min-width: 0;
        padding: 0 1;
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
                # Purple in rose-pine-moon ($primary = iris); label follows `running`
                self.reset_button = Button("Reset", id="reset", variant="primary")
                yield self.reset_button
            with Horizontal():
                self.adjust_button = Button("Adjust Focus Time", id="adjust")
                yield self.adjust_button
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
        """Wane full -> new over a focus phase; wax new -> full over a break."""
        elapsed = 1 - self.time_left / self.current_duration
        self.sky.waxing = self.phase == "break"
        self.sky.progress = elapsed if self.phase == "focus" else 1 - elapsed

    def watch_phase(self, phase: str) -> None:
        """Called when phase is modified."""
        self.phase_label.update(phase.upper())
        self.container.set_class(phase == "break", "break-phase")
        self.start_button.variant = "success" if phase == "break" else "warning"
        self.adjust_button.label = f"Adjust {phase.capitalize()} Time"
        self.adjust_button.refresh(layout=True)

    def watch_running(self, running: bool) -> None:
        """Reset doubles as Skip while the timer is counting."""
        self.reset_button.label = "Skip" if running else "Reset"
        self.reset_button.refresh(layout=True)  # re-fit width so the label stays centered

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
            if self.running:
                self.stop_timer()
                self.advance_phase()
            else:
                self.reset_timer()
        elif button_id == "adjust":
            self.adjust_duration()

    def adjust_duration(self) -> None:
        """Pop up a dialog to set the current phase's duration (h/m/s)."""
        phase = self.phase

        def apply(seconds: int | None) -> None:
            if seconds is None or phase != self.phase:
                return
            if phase == "focus":
                self.focus_time = seconds
            else:
                self.break_time = seconds
            self.reset_timer()

        title = f"{phase.capitalize()} duration"
        self.push_screen(DurationDialog(title, self.current_duration), apply)

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
