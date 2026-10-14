# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

zen-timer is a Pomodoro-style focus timer TUI built with [Textual](https://textual.textualize.io/). The app lives in `main.py`; the animated background scene lives in `night_sky.py`.

## Commands

This project uses `uv` for dependency and environment management. All commands are wrapped in the `Makefile`.

- `make install` — install dependencies / sync the venv (`uv sync`)
- `make run` — run the app (`uv run main.py`)
- `make dev` — run the app in Textual dev mode (`uv run textual run --dev main.py`); pair with `uvx --from textual-dev textual console` in a separate terminal to see live logs, since the TUI takes over the terminal and print/logging output isn't visible otherwise. **Caveat:** the `textual` CLI comes from the `textual-dev` package, which is not currently a project dependency, so `make dev` fails until it's added (e.g. `uv add --dev textual-dev`)
- `make format` — auto-fix and format with Ruff (`uvx ruff check --fix .` then `uvx ruff format .`)
- `make lint` — check with Ruff, no fixes (`uvx ruff check .`)
- `make clean` — remove `.venv`, `.ruff_cache`, and `__pycache__` directories

There is no test suite in this repository yet. To sanity-check changes without a real terminal, drive the app headlessly with Textual's test harness, e.g.:

```python
async with ZenTimerApp().run_test() as pilot:
    await pilot.pause()
    ...
```

`set_interval`-driven state (like the timer tick) only advances with real wall-clock time under `run_test`, so use `await pilot.pause(seconds)` with enough real seconds to cross the interval, not just a single short pause.

## Architecture

`main.py` defines two widget classes (plus the `DurationDialog` popup in `duration_dialog.py`):

- `TimeDisplay(Static)` — renders `time_left` (seconds) as `MM:SS`. It has its own `reactive` `time_left`, separate from the app's; the app pushes values into it rather than it owning any state.
- `ZenTimerApp(App)` — owns all real state and drives `TimeDisplay` via `watch_time_left`.

Key state and flow:
- The app cycles between two phases, `"focus"` and `"break"` (`self.phase`, a reactive), each with its own duration (`self.focus_time` default 25 min, `self.break_time` default 5 min). `current_duration` picks the right one for the active phase.
- A single `set_interval(1, self.tick, pause=True)` is created once in `on_mount` and stored as `self.timer_task`; Start/Stop just call `.resume()` / `.pause()` on it rather than creating/destroying timers.
- `tick()` decrements `time_left`; when it's already at 0, it pauses the timer, plays the alarm (`self.alarm.play()`, see below), and calls `advance_phase()`, which flips `self.phase` and reloads `time_left` from the new phase's duration — but leaves the timer paused, so the user must press **Start** again to begin the next phase (no auto-run between focus and break).
- `watch_phase` updates the on-screen phase label and toggles a `break-phase` CSS class on the timer container, and swaps the Start button variant. Colors come from theme variables, not literals: FOCUS = `$warning` (e.g. gold in rose-pine), BREAK = `$success`; Start is `variant="warning"`/`"success"` to match, Stop stays `"error"`. Keep new colors as theme variables so they follow the user's chosen theme.
- The **Adjust Focus/Break Time** button (`#adjust`, label swapped in `watch_phase`) opens `DurationDialog` (`duration_dialog.py`, a `ModalScreen[int | None]` with hours/minutes/seconds inputs, Enter/Save to confirm, Esc/Cancel to close). `adjust_duration` writes the result to `focus_time` or `break_time` for the phase that was active when it opened (ignored if the phase changed meanwhile) and resets that countdown, paused. `TimeDisplay` shows `H:MM:SS` once a duration reaches an hour.
- The purple (`$primary`, iris in rose-pine-moon) `#reset` button doubles as **Skip**: `watch_running` relabels it. While running, Skip pauses and calls `advance_phase()`; while paused, Reset re-loads `current_duration` for the active phase without switching phases. Buttons are sized to their labels (`min-width: 0`) so text stays exactly centered, and the label swap calls `refresh(layout=True)` to re-fit.
- `self.running` is a reactive that Start/Stop/Reset/tick keep updated; `watch_running` uses it for the Reset/Skip label and the button handler reads it to pick Skip vs Reset.
- All layout/styling is inline Textual CSS in the `CSS` class variable, not a separate `.tcss` file.

### Alarm sounds (`alarm.py`)

`AlarmPlayer` replaces `self.bell()` when a phase completes. Sounds are discovered from files at runtime: bundled `sounds/` (credits in `sounds/CREDITS.md`), then `~/.config/zen-timer/sounds/` (overrides same-named files), then a few macOS system sounds, plus the `terminal bell` and `off` pseudo-entries. Playback shells out to the first available OS player (`afplay`, `ffplay`, `mpv`, `paplay`, `aplay`; `winsound` for WAVs on Windows) via a non-blocking `Popen`, falling back to the terminal bell. The `s` binding cycles and previews; the choice persists in `~/.config/zen-timer/settings.json`. Pressing Start silences a still-ringing alarm.

### Night sky scene (`night_sky.py`)

`NightSky(Widget)` is a full-screen animated background (stars, a phased moon, Mount Fuji, a swaying cherry blossom tree, falling petals, and a koi pond on a rock ledge), drawn only for the `rose-pine-moon` theme. The app sets that theme on mount and toggles `self.sky.display` via `theme_changed_signal`. All of it is procedural; there is no third-party art.
- Layering: `Screen` declares `layers: sky ui`; `NightSky` is on `sky` (with `margin: 1 0` so the hill sits above the Footer), everything else on `ui`. Textual arranges each layer independently, which is why the sky can fill the screen while the timer stays centered.
- Rendering: the static scene is built on a square-pixel grid of 2×4 pixels per cell (`_static`, generated with a fixed seed on resize), in draw order sky gradient (plus faint fixed pixel stars) → Fuji (`_fuji`) → hill → ledge and pond (`_ledge`, own seed). The tree is *not* in `_static`: `_grow` builds a `Branch` hierarchy once (same seeded rng order as the old direct drawing) and `_tree_pixels(sway)` draws it into a cached `{row: {x: color}}` layer. Anything that isn't open sky clears `_sky_mask`, which keeps stars and moon glow off it; for the tree that's the union of its rest and full-gust poses. `_apply_moon` stores the moonlit background (`_bg`), and `_compose_rows` layers the tree on top while averaging vertical pixel pairs into a 2×2-per-cell display grid (`_quad`), and `render_line` shows each 2×2 block with a quadrant glyph (`fit_quadrant`: one fg + one bg color, best two-color split when a block has more). Fits are memoized per color block in `_fits` and per-row `Strip`s are cached, so only dirty rows (petals, koi, twinkling text stars, swaying tree rows) rebuild each frame (~12 FPS). Petals, floating petals and koi are applied at render time, in display pixels.
- Moon phase: the app sets `sky.progress` in `update_moon` (0 = full, 1 = new): it wanes full → new over a focus phase and waxes new → full over a break, with `sky.waxing` set for breaks. The terminator always sweeps right-to-left; waning lights the side left of it (dark grows from the right), waxing the side right of it (light grows from the right). It's quantized to `MOON_STEPS` and cached per `(step, waxing)`; `_apply_moon` draws the moon (gold-tinted, with craters) and its glow, and also dims Fuji's snow (`self._snow`) with the moon's illumination.
- Petals spawn only from `_blossom_pixels` and die when they reach the ground; ones that land in the pond become short-lived floaters.
- Sway: every `SWAY_EVERY` frames (5 s) a gust eases the branches out and back over `GUST_FRAMES`, peaking at `SWAY` rad; each branch level adds `sway * (6 - depth) / 15`, so the trunk is rigid and the tips bend most. Sway is quantized so `_tree_cache` stays small, and only the tree's rows are recomposed, which is why the moon never repaints during a gust. Gusts also boost wind and petal spawning.
- Koi (`Koi`, patterns in `KOI_PATTERNS`: kohaku, ogon, showa) live in display-pixel coordinates (y foreshortened ×0.5), wander with a damped random turn, and steer back toward the middle when a look-ahead point leaves the pond ellipse (`_pond`). The pond sits under the moon's x so `_apply_moon` can paint a faint reflection that fades with the moon.
- Scene colors are hard-coded Rosé Pine Moon RGB constants, not theme variables, because the scene only shows for that theme.

### Naming gotcha

`display` is a reserved property on every Textual `App`/`Widget` (it maps to the CSS `display: block|none` rule). Don't name an app-level widget reference `self.display` — assigning a widget to it raises `StyleValueError` at runtime. The `TimeDisplay` widget instance is stored as `self.time_display` for this reason. The same applies to private names: `Widget` already uses `_size`, `_animate`, `_compose`, etc., and shadowing them breaks layout in confusing ways (`NightSky` uses `_scene_size` / `_next_frame` for this reason).

Reactives declared with the default `init=True` (e.g. `phase`) fire their watcher on first access/assignment. Don't read such a reactive inside `compose()` before the widgets its watcher touches (e.g. `phase_label`, `container`) have been assigned — seed any initial on-screen text with a literal instead.
