"""Swappable alarm sounds, played through the OS's own audio player.

Sounds are plain audio files discovered at runtime, so adding one is just
dropping a file into `sounds/` (bundled) or `~/.config/zen-timer/sounds/`
(personal). The chosen sound is remembered in `~/.config/zen-timer/settings.json`.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

BUNDLED_DIR = Path(__file__).parent / "sounds"
CONFIG_DIR = Path.home() / ".config" / "zen-timer"
USER_DIR = CONFIG_DIR / "sounds"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
SYSTEM_DIR = Path("/System/Library/Sounds")  # macOS built-ins

EXTENSIONS = {".wav", ".mp3", ".ogg", ".oga", ".flac", ".aiff", ".aif", ".m4a"}
DEFAULT_SOUND = "tibetan-bowl"
TERMINAL_BELL = "terminal bell"
SILENT = "off"

# First player found wins. paplay/aplay can't decode mp3, so they come last.
PLAYERS = [
    ["afplay"],
    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
    ["mpv", "--no-video", "--really-quiet"],
    ["paplay"],
    ["aplay", "-q"],
]


def discover_sounds() -> dict[str, Path | None]:
    """Map sound name -> file, in cycle order. Later dirs override earlier names."""
    sounds: dict[str, Path | None] = {}
    for directory in (BUNDLED_DIR, USER_DIR):
        if directory.is_dir():
            for path in sorted(directory.iterdir()):
                if path.suffix.lower() in EXTENSIONS:
                    sounds[path.stem] = path
    # A few of the gentler macOS system sounds, when present.
    for name in ("Glass", "Purr", "Tink"):
        path = SYSTEM_DIR / f"{name}.aiff"
        if path.exists():
            sounds.setdefault(f"mac {name.lower()}", path)
    sounds[TERMINAL_BELL] = None
    sounds[SILENT] = None
    return sounds


class AlarmPlayer:
    """Holds the selected sound and plays it without blocking the UI."""

    def __init__(self, terminal_bell) -> None:
        self._terminal_bell = terminal_bell
        self._player = next((cmd for cmd in PLAYERS if shutil.which(cmd[0])), None)
        self._process: subprocess.Popen | None = None
        self.sounds = discover_sounds()
        self.name = self._load_choice()

    def _load_choice(self) -> str:
        try:
            name = json.loads(SETTINGS_FILE.read_text()).get("sound")
        except (OSError, ValueError):
            name = None
        if name in self.sounds:
            return name
        return DEFAULT_SOUND if DEFAULT_SOUND in self.sounds else next(iter(self.sounds))

    def _save_choice(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps({"sound": self.name}, indent=2) + "\n")
        except OSError:
            pass  # Not remembering the choice is fine; the sound still works.

    def cycle(self) -> str:
        """Select the next sound, remember it, and return its name."""
        self.sounds = discover_sounds()  # Pick up files added while running.
        names = list(self.sounds)
        index = names.index(self.name) if self.name in names else -1
        self.name = names[(index + 1) % len(names)]
        self._save_choice()
        return self.name

    def play(self) -> None:
        """Play the selected sound, cutting off any sound still playing."""
        self.stop()
        if self.name == SILENT:
            return
        path = self.sounds.get(self.name)
        if path is None or not path.exists():
            self._terminal_bell()
            return
        try:
            if sys.platform == "win32" and path.suffix.lower() == ".wav":
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif self._player:
                self._process = subprocess.Popen(
                    [*self._player, str(path)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                self._terminal_bell()
        except OSError:
            self._terminal_bell()

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self._process = None
