"""Animated moonlit cherry-blossom scene drawn behind the timer.

The scene is built on a grid of square pixels, two across and four down per
terminal cell. It is shown with quadrant block characters ("▘", "▚", "▙", ...),
each cell showing a 2x2 block with one foreground and one background color, so
every displayed pixel averages two square pixels vertically. Twinkling stars
are drawn on top as text characters.
"""

import math
import random

from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

RGB = tuple[int, int, int]

# Rosé Pine Moon palette
BASE: RGB = (0x23, 0x21, 0x36)
SUBTLE: RGB = (0x90, 0x8C, 0xAA)
TEXT: RGB = (0xE0, 0xDE, 0xF4)
LOVE: RGB = (0xEB, 0x6F, 0x92)
ROSE: RGB = (0xEA, 0x9A, 0x97)
GOLD: RGB = (0xF6, 0xC1, 0x77)
HL_MED: RGB = (0x44, 0x41, 0x5A)
SILHOUETTE: RGB = (0x19, 0x17, 0x24)

SKY_TOP: RGB = (0x1A, 0x18, 0x2A)
SKY_HORIZON: RGB = (0x30, 0x2C, 0x48)
BARK: RGB = (0x33, 0x2D, 0x45)
BARK_LIT: RGB = (0x58, 0x50, 0x6E)
PETAL_PALE: RGB = (0xF2, 0xCD, 0xD3)
BLOSSOMS: tuple[RGB, ...] = (ROSE, ROSE, PETAL_PALE, LOVE, (0xD8, 0x86, 0x9A))

MOON_LIT: RGB = (0xF4, 0xE2, 0xB4)
MOON_LIMB: RGB = (0xC9, 0xA8, 0x86)
MOON_MARE: RGB = (0xC2, 0xAE, 0x96)
MOON_DARK: RGB = (0x34, 0x31, 0x48)
GLOW: RGB = (0xA8, 0x92, 0x9E)

FUJI_SHADOW: RGB = (0x1D, 0x1B, 0x2D)
FUJI_LIT: RGB = (0x2C, 0x29, 0x42)
SNOW_LIT: RGB = (0xC9, 0xC6, 0xE0)
SNOW_SHADOW: RGB = (0x82, 0x7E, 0xA0)
SNOW_DARK: RGB = (0x4E, 0x4A, 0x66)

# Rock ledge and koi pond in the right foreground
ROCK: RGB = (0x24, 0x21, 0x33)
ROCK_MID: RGB = (0x2E, 0x2A, 0x40)
ROCK_LIT: RGB = (0x4A, 0x44, 0x62)
GRASS: RGB = (0x2C, 0x45, 0x44)
GRASS_LIT: RGB = (0x4E, 0x77, 0x6C)
WATER_SKY: RGB = (0x35, 0x3A, 0x5E)
WATER_DEEP: RGB = (0x16, 0x1D, 0x33)
KOHAKU_W: RGB = (0xF2, 0xE9, 0xE1)
KOHAKU_R: RGB = (0xEB, 0x6F, 0x60)
SUMI: RGB = (0x12, 0x10, 0x1C)
# Head-to-tail pixel colors for each koi variety: kohaku, ogon, showa
KOI_PATTERNS: tuple[tuple[RGB, ...], ...] = (
    (KOHAKU_W, KOHAKU_R, KOHAKU_R, KOHAKU_W, KOHAKU_W),
    (GOLD, GOLD, GOLD, GOLD),
    (SUMI, KOHAKU_R, KOHAKU_W, SUMI),
)

# (u, v, radius) on the unit moon disc
CRATERS = (
    (-0.35, -0.3, 0.22),
    (0.3, 0.25, 0.28),
    (-0.1, 0.5, 0.15),
    (0.45, -0.4, 0.12),
    (0.05, -0.05, 0.08),
    (-0.55, 0.2, 0.09),
)

# Quadrant glyph for each foreground mask (bits: top-left 8, top-right 4, bottom-left 2, bottom-right 1)
QUADRANTS = {
    1: "▗", 2: "▖", 3: "▄", 4: "▝", 5: "▐", 6: "▞", 7: "▟",
    8: "▘", 9: "▚", 10: "▌", 11: "▙", 12: "▀", 13: "▜", 14: "▛",
}  # fmt: skip
QUAD_BITS = (8, 4, 2, 1)

MOON_STEPS = 120
FPS = 12

# Every SWAY_EVERY frames a gust bends the branches for GUST_FRAMES, peaking at SWAY radians
SWAY_EVERY = 5 * FPS
GUST_FRAMES = int(1.5 * FPS)
SWAY = 0.05


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _avg(colors: list[RGB]) -> RGB:
    n = len(colors)
    return (
        sum(c[0] for c in colors) // n,
        sum(c[1] for c in colors) // n,
        sum(c[2] for c in colors) // n,
    )


def _dist2(a: RGB, b: RGB) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def fit_quadrant(px: tuple[RGB, RGB, RGB, RGB]) -> tuple[str, RGB | None, RGB]:
    """Pick the quadrant glyph and two colors that best show a 2x2 pixel block."""
    a = px[0]
    if px[1] == a and px[2] == a and px[3] == a:
        return " ", None, a
    others = {p for p in px if p != a}
    if len(others) == 1:
        mask = sum(bit for bit, p in zip(QUAD_BITS, px) if p == a)
        return QUADRANTS[mask], a, others.pop()

    best = None
    for mask in range(1, 8):
        fg_px = [p for bit, p in zip(QUAD_BITS, px) if mask & bit]
        bg_px = [p for bit, p in zip(QUAD_BITS, px) if not mask & bit]
        fg, bg = _avg(fg_px), _avg(bg_px)
        err = sum(_dist2(p, fg) for p in fg_px) + sum(_dist2(p, bg) for p in bg_px)
        if best is None or err < best[0]:
            best = (err, mask, fg, bg)
    _, mask, fg, bg = best
    return QUADRANTS[mask], fg, bg


class Petal:
    __slots__ = ("color", "freq", "phase", "vy", "x", "y")

    def __init__(self, x: float, y: float, rng: random.Random) -> None:
        self.x = x
        self.y = y
        self.vy = rng.uniform(0.24, 0.6)
        self.phase = rng.uniform(0, math.tau)
        self.freq = rng.uniform(0.05, 0.12)
        self.color = rng.choice(BLOSSOMS)


class Branch:
    """One branch of the cherry tree, kept so the tree can be redrawn as it sways."""

    __slots__ = ("angle", "blossom", "children", "depth", "length", "thick")

    def __init__(self, angle: float, length: float, thick: float, depth: int) -> None:
        # The trunk's angle is absolute; every other branch's is relative to its parent
        self.angle = angle
        self.length = length
        self.thick = thick
        self.depth = depth
        # (dx, dy, color) offsets around the branch tip
        self.blossom: list[tuple[int, int, RGB]] = []
        self.children: list[Branch] = []


class Koi:
    """A koi in display pixels; y is foreshortened because the pond is seen at an angle."""

    __slots__ = ("heading", "pattern", "phase", "speed", "turn", "x", "y")

    def __init__(
        self, x: float, y: float, pattern: tuple[RGB, ...], rng: random.Random
    ) -> None:
        self.x = x
        self.y = y
        self.pattern = pattern
        self.heading = rng.uniform(0, math.tau)
        self.speed = rng.uniform(0.1, 0.18)
        self.turn = 0.0
        self.phase = rng.uniform(0, math.tau)

    def pixels(self, t: int) -> list[tuple[int, int, RGB]]:
        dx, dy = math.cos(self.heading), math.sin(self.heading) * 0.5
        out = []
        last = len(self.pattern) - 1
        for i, color in enumerate(self.pattern):
            px, py = self.x - dx * i, self.y - dy * i
            if i == last:
                # flick the tail side to side
                wag = 0.7 * math.sin(t * 0.35 + self.phase)
                px, py = px - dy * wag * 2, py + dx * wag * 0.5
            out.append((int(px), int(py), color))
        return out


class NightSky(Widget):
    """Full-screen animated background: stars, a phased moon, Mount Fuji, a swaying cherry tree, and a koi pond."""

    # 0.0 = full moon, 1.0 = new moon
    progress = reactive(0.0, layout=False, repaint=False)
    # False = waning (dark side grows from the right), True = waxing (lit side grows from the right)
    waxing = reactive(False, layout=False, repaint=False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._scene_size = (0, 0)
        self._frame = 0
        self._rng = random.Random()
        # Square-pixel scene (2 x 4 pixels per cell) and its 2 x 2 per cell display grid
        self._static: list[list[RGB]] = []
        self._sky_mask: list[list[bool]] = []
        self._quad: list[list[RGB]] = []
        self._moon_step: tuple[int, bool] | None = None
        self._blossom_pixels: list[tuple[int, int]] = []
        self._snow: list[tuple[int, int, float]] = []
        self._ground: list[int] = []
        self._stars: list[tuple[int, int, float, float, float]] = []
        self._star_cells: dict[tuple[int, int], tuple[str, RGB]] = {}
        self._petals: list[Petal] = []
        self._petal_rows: set[int] = set()
        self._strips: list[Strip | None] = []
        self._styles: dict[tuple, Style] = {}
        self._fits: dict[tuple, tuple[str, Style]] = {}
        # Moonlit scene without the tree; the tree is layered on top so a swaying
        # branch only ever repaints its own pixels, never the moon or the sky
        self._bg: list[list[RGB]] = []
        self._tree: tuple[float, float, Branch] | None = None
        self._tree_cache: dict[float, dict[int, dict[int, RGB]]] = {}
        self._tree_rows: dict[int, dict[int, RGB]] = {}
        self._sway = 0.0
        # Pond as (cx, cy, rx, ry) in square pixels, plus its koi and floating petals
        self._pond: tuple[float, float, float, float] | None = None
        self._pond_pixels: set[tuple[int, int]] = set()
        self._koi: list[Koi] = []
        self._koi_rows: set[int] = set()
        self._floaters: list[list] = []  # [x, qy, color, frames_left]
        self._floater_rows: set[int] = set()

    def on_mount(self) -> None:
        self.set_interval(1 / FPS, self._next_frame)

    # --- scene construction -------------------------------------------------

    def _build(self) -> None:
        w, h = self.size
        self._scene_size = (w, h)
        sw, sh = w * 2, h * 4
        rng = random.Random(7)

        self._static = [
            [mix(SKY_TOP, SKY_HORIZON, (y / sh) ** 1.6)] * sw for y in range(sh)
        ]
        self._sky_mask = [[True] * sw for _ in range(sh)]
        self._blossom_pixels = []
        self._styles = {}
        self._fits = {}

        self._fuji()

        # Rolling hill along the bottom
        base = sh - max(6, int(sh * 0.08))
        self._ground = [
            int(
                base
                - 5 * math.sin(x / max(sw, 1) * math.pi * 1.4 + 0.5)
                - 2.4 * math.sin(x * 0.055)
            )
            for x in range(sw)
        ]
        for x, gy in enumerate(self._ground):
            for y in range(max(gy, 0), sh):
                self._set(x, y, SILHOUETTE)
            if 0 <= gy < sh - 1 and rng.random() < 0.12:
                color = rng.choice(BLOSSOMS[:3])
                self._set(x, gy, color)
                self._set(x, gy + 1, color)

        # Rock ledge and koi pond, with their own seed so the tree and stars stay put
        self._ledge(random.Random(11))

        # Cherry tree, rooted left of center
        self._tree = None
        self._tree_cache = {}
        self._sway = 0.0
        root_x = int(sw * 0.17)
        if 0 <= root_x < sw:
            root_y = self._ground[root_x]
            trunk = max(12.0, min(sh * 0.22, sw * 0.14))
            self._tree = (
                root_x,
                root_y,
                self._grow(-math.pi / 2 + 0.12, trunk, max(3.0, trunk / 7), 6, rng),
            )
            # Keep stars and moon glow off anywhere the tree can reach mid-gust
            for sway in (0.0, SWAY):
                for y, row in self._tree_pixels(sway).items():
                    for x in row:
                        if 0 <= y < sh and 0 <= x < sw:
                            self._sky_mask[y][x] = False
        self._tree_rows = self._tree_pixels(0.0)

        mx, my, r = self._moon_geometry()

        # Faint fixed stars, one display pixel each
        for _ in range(sw * sh // 200):
            x, y = rng.randrange(sw), rng.randrange(0, sh - 1, 2)
            if not (self._sky_mask[y][x] and self._sky_mask[y + 1][x]):
                continue
            if y > self._ground[x] - 16 or math.hypot(x - mx, y - my) < r * 3.2:
                continue
            color = mix(
                self._static[y][x],
                rng.choice((SUBTLE, SUBTLE, TEXT, GOLD)),
                rng.uniform(0.2, 0.6),
            )
            self._static[y][x] = self._static[y + 1][x] = color

        # Twinkling stars, kept away from the moon and anything that isn't open sky
        self._stars = []
        for _ in range(int(w * h / 20)):
            cx, cy = rng.randrange(w), rng.randrange(max(1, h - 2))
            px, py = cx * 2, cy * 4
            if py + 3 >= sh or not all(
                self._sky_mask[py + dy][px + dx] for dy in range(4) for dx in range(2)
            ):
                continue
            if math.hypot(px - mx, py - my) < r * 3.2 or py > self._ground[px] - 12:
                continue
            self._stars.append(
                (
                    cx,
                    cy,
                    rng.uniform(0.3, 1.0),
                    rng.uniform(0.04, 0.15),
                    rng.uniform(0, math.tau),
                )
            )

        self._petals = []
        self._floaters = []
        self._koi = []
        if self._pond is not None:
            cx, cy, rx, _ = self._pond
            koi_rng = random.Random(5)
            for i, pattern in enumerate(KOI_PATTERNS):
                kx = cx + rx * (i - 1) * 0.4
                self._koi.append(Koi(kx, cy / 2, pattern, koi_rng))
        self._moon_step = None
        self._star_cells = {}
        self._strips = [None] * h

    def _set(self, x: int, y: int, color: RGB) -> None:
        if 0 <= y < len(self._static) and 0 <= x < len(self._static[0]):
            self._static[y][x] = color
            self._sky_mask[y][x] = False

    def _fuji(self) -> None:
        """Mount Fuji on the horizon, moonlit from the right, with a streaky snow cap."""
        sh, sw = len(self._static), len(self._static[0])
        peak_x = sw * 0.78
        half_w = sw * 0.34
        foot_y = sh * 0.95
        peak_y = sh * 0.54
        height = foot_y - peak_y
        plateau = half_w * 0.07
        self._snow = []

        for x in range(max(0, int(peak_x - half_w)), min(sw, int(peak_x + half_w) + 1)):
            dx = x + 0.5 - peak_x
            t = max(0.0, (abs(dx) - plateau) / (half_w - plateau))
            if t >= 1:
                continue
            # Concave flanks rising to a broad, flat summit
            top = int(foot_y - height * (1 - t) ** 1.45)
            # Snow follows elevation, with evenly spaced gullies carrying streaks further down
            gully = max(0.0, math.sin(x * 0.275 + 0.7)) ** 6
            snow_y = peak_y + height * (0.26 + 0.03 * math.sin(x * 0.45) + 0.14 * gully)
            # 0 = shadowed (left) flank, 1 = moonlit (right) flank
            lit = min(1.0, max(0.0, 0.5 + dx / half_w * 2.5))

            for y in range(max(0, top), min(sh, int(foot_y) + 1)):
                if y < snow_y:
                    self._set(x, y, mix(SNOW_SHADOW, SNOW_LIT, lit))
                    self._snow.append((x, y, lit))
                    continue
                body = mix(FUJI_SHADOW, FUJI_LIT, lit)
                # Fade the lower slopes into the horizon haze so the mountain reads as distant
                haze = (y - peak_y) / height
                if haze > 0.55:
                    body = mix(body, self._static[y][x], (haze - 0.55) / 0.45 * 0.7)
                self._set(x, y, body)

    def _ledge(self, rng: random.Random) -> None:
        """A rocky ledge rising on the right, with grass tufts and a koi pond set into it."""
        sh, sw = len(self._static), len(self._static[0])
        start = sw * 0.68
        rise = max(8.0, sh * 0.16)
        for x in range(int(start), sw):
            t = (x - start) / (sw - start)
            top = int(
                sh
                - 5
                - rise * math.sin(min(1.0, t * 1.3) * math.pi / 2)
                + 1.5 * math.sin(x * 0.21)
            )
            top = min(top, self._ground[x])
            for y in range(max(0, top), sh):
                depth = y - top
                slab = (x // 14 + y // 10) % 3 == 0
                if depth < 2:
                    color = ROCK_LIT
                elif depth < 4 or (slab and depth < 12):
                    color = ROCK_MID
                else:
                    color = ROCK
                self._set(x, y, color)
            if rng.random() < 0.35:
                for k in range(rng.choice((2, 4, 4, 6))):
                    self._set(
                        x,
                        top - 1 - k,
                        GRASS_LIT if k < 2 and rng.random() < 0.5 else GRASS,
                    )
            self._ground[x] = top

        # Pond sits under the moon so it catches the moon's reflection
        self._pond = None
        self._pond_pixels = set()
        cx, cy, rx, ry = sw * 0.8, sh - 14.0, sw * 0.085, 9.0
        if rx < 8 or cy - ry < sh * 0.5:
            return
        self._pond = (cx, cy, rx, ry)
        water = set()
        for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
            for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
                if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1:
                    water.add((x, y))
        for x, y in water:
            depth = (y - (cy - ry)) / (2 * ry)
            self._set(x, y, mix(WATER_SKY, WATER_DEEP, depth))
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in water:
                    self._set(nx, ny, ROCK_LIT if ny <= y else ROCK_MID)
            # petals stop at the water's surface
            if 0 <= x < sw:
                self._ground[x] = min(self._ground[x], y)
        self._pond_pixels = water

    def _grow(
        self, angle: float, length: float, thick: float, depth: int, rng: random.Random
    ) -> Branch:
        """Grow the tree's shape once; drawing happens in _tree_pixels so it can sway."""
        node = Branch(angle, length, thick, depth)
        if depth == 0 or length < 5:
            node.blossom = self._blossom(max(5.0, length * 0.9), rng)
            return node
        if depth <= 3:
            node.blossom = self._blossom(max(4.0, length * 0.55), rng)
        for _ in range(rng.choice((2, 2, 3))):
            spread = rng.uniform(0.3, 0.65) * rng.choice((-1, 1))
            # bias growth sideways so the canopy spreads wide
            node.children.append(
                self._grow(
                    spread,
                    length * rng.uniform(0.68, 0.8),
                    thick * 0.68,
                    depth - 1,
                    rng,
                )
            )
        return node

    def _blossom(self, radius: float, rng: random.Random) -> list[tuple[int, int, RGB]]:
        out = []
        ir = int(radius + 1)
        for dy in range(-ir, ir + 1):
            for dx in range(-ir, ir + 1):
                d = math.hypot(dx, dy * 1.15) / radius
                if d > 1 or rng.random() > 0.85 - d * 0.45:
                    continue
                color = rng.choice(BLOSSOMS)
                if dx > 0 and dy < 0:
                    color = mix(color, PETAL_PALE, 0.35)
                elif dy > radius * 0.4:
                    color = mix(color, BARK, 0.35)
                out.append((dx, dy, color))
        return out

    def _tree_pixels(self, sway: float) -> dict[int, dict[int, RGB]]:
        """Draw the tree bent by `sway` radians, as {row: {column: color}} in square pixels."""
        cached = self._tree_cache.get(sway)
        if cached is not None:
            return cached
        rows: dict[int, dict[int, RGB]] = {}
        blossoms: list[tuple[int, int]] = []
        if self._tree is None:
            return rows

        def walk(node: Branch, x: float, y: float, parent: float) -> None:
            # The trunk stays rigid; each level out bends a little more with the wind
            angle = parent + node.angle + sway * (6 - node.depth) / 15
            ex = x + math.cos(angle) * node.length
            ey = y + math.sin(angle) * node.length
            steps = max(1, int(node.length * 1.5))
            for i in range(steps + 1):
                t = i / steps
                px, py = x + (ex - x) * t, y + (ey - y) * t
                rad = node.thick * (1 - 0.35 * t)
                ir = int(rad + 1)
                for dy in range(-ir, ir + 1):
                    for dx in range(-ir, ir + 1):
                        if dx * dx + dy * dy <= rad * rad:
                            # moonlight comes from the upper right
                            lit = dx > rad * 0.3 and dy < rad * 0.3
                            row = rows.setdefault(int(py + dy), {})
                            row[int(px + dx)] = BARK_LIT if lit else BARK
            for dx, dy, color in node.blossom:
                bx, by = int(ex + dx), int(ey + dy)
                rows.setdefault(by, {})[bx] = color
                blossoms.append((bx, by))
            for child in node.children:
                walk(child, ex, ey, angle)

        root_x, root_y, trunk = self._tree
        walk(trunk, root_x, root_y, 0.0)
        if sway == 0.0:
            self._blossom_pixels = blossoms
        self._tree_cache[sway] = rows
        return rows

    # --- moon ---------------------------------------------------------------

    def _moon_geometry(self) -> tuple[int, int, float]:
        w, h = self._scene_size
        sw, sh = w * 2, h * 4
        r = max(7.0, min(sw * 0.07, sh * 0.12))
        return int(sw * 0.8), int(sh * 0.2 + r * 0.5), r

    def _apply_moon(self, step: int, waxing: bool) -> None:
        """Rebuild the display grid with the moon at the given phase step."""
        bg = [row[:] for row in self._static]
        if not bg:
            return
        sh, sw = len(bg), len(bg[0])
        mx, my, r = self._moon_geometry()
        phi = math.pi * step / MOON_STEPS
        illum = (1 + math.cos(phi)) / 2

        # Fuji's snow catches less light as the moon wanes
        for x, y, lit in self._snow:
            bg[y][x] = mix(
                SNOW_DARK, mix(SNOW_SHADOW, SNOW_LIT, lit), 0.35 + 0.65 * illum
            )

        reach = int(r * 3) + 1
        for y in range(max(0, my - reach), min(sh, my + reach + 1)):
            for x in range(max(0, mx - reach), min(sw, mx + reach + 1)):
                dx, dy = x - mx + 0.5, y - my + 0.5
                d = math.hypot(dx, dy) / r
                if d <= 1:
                    u, v = dx / r, dy / r
                    # The terminator sweeps right-to-left either way: a waning moon
                    # is lit left of it, a waxing moon right of it
                    terminator = math.cos(phi) * math.sqrt(max(0.0, 1 - v * v))
                    edge = u + terminator if waxing else terminator - u
                    lit_amt = edge * r * 0.35 + 0.5
                    lit = mix(MOON_LIT, MOON_LIMB, d**3)
                    dark = MOON_DARK
                    for cu, cv, cr in CRATERS:
                        if (u - cu) ** 2 + (v - cv) ** 2 < cr * cr:
                            lit = mix(lit, MOON_MARE, 0.6)
                            dark = mix(dark, BASE, 0.3)
                            break
                    color = mix(dark, lit, lit_amt)
                    if d > 0.94:  # soften the rim
                        color = mix(color, self._static[y][x], (d - 0.94) / 0.06 * 0.5)
                    bg[y][x] = color
                elif d < 3 and self._sky_mask[y][x]:
                    glow = illum * 0.3 * (1 - (d - 1) / 2) ** 2
                    bg[y][x] = mix(self._static[y][x], GLOW, glow)

        # A broken strip of moonlight on the pond, fading as the moon wanes
        for x, y in self._pond_pixels:
            off = abs(x - mx)
            if off <= 1 and (y // 2) % 2 == 0 and 0 <= y < sh:
                bg[y][x] = mix(bg[y][x], MOON_LIT, (0.3 if off == 0 else 0.12) * illum)

        self._bg = bg
        self._quad = [[] for _ in range(sh // 2)]
        self._compose_rows(range(sh // 2))
        self._moon_step = (step, waxing)

    def _compose_rows(self, qrows) -> None:
        """Rebuild display rows from the moonlit background with the tree layered on top."""
        bg, tree = self._bg, self._tree_rows
        sw = len(bg[0])
        for qy in qrows:
            pair = []
            for y in (qy * 2, qy * 2 + 1):
                row = bg[y]
                branch = tree.get(y)
                if branch:
                    row = row[:]
                    for x, color in branch.items():
                        if 0 <= x < sw:
                            row[x] = color
                pair.append(row)
            # Each display pixel averages two square pixels stacked vertically
            self._quad[qy] = [
                _avg([top, bot]) if top != bot else top for top, bot in zip(*pair)
            ]

    # --- animation ----------------------------------------------------------

    def _next_frame(self) -> None:
        if not self.display or self.size.area == 0:
            return
        w, h = self.size
        if (w, h) != self._scene_size:
            self._build()

        dirty: set[int] = set()
        step = round(self.progress * MOON_STEPS)
        if (step, self.waxing) != self._moon_step:
            self._apply_moon(step, self.waxing)
            dirty.update(range(h))

        self._frame += 1
        t = self._frame

        # A gust every few seconds bends the branches, then lets them settle back
        g = t % SWAY_EVERY
        gust = math.sin(math.pi * g / GUST_FRAMES) ** 2 if g < GUST_FRAMES else 0.0
        sway = round(SWAY * gust / 0.003) * 0.003
        if sway != self._sway and self._tree is not None:
            old = self._tree_rows
            self._sway = sway
            self._tree_rows = self._tree_pixels(sway)
            # only the rows the tree covers are repainted; the moon is never touched
            qrows = {
                y // 2 for y in old.keys() | self._tree_rows.keys() if 0 <= y < h * 4
            }
            self._compose_rows(qrows)
            dirty.update(qy // 2 for qy in qrows)

        # Twinkling stars
        stars: dict[tuple[int, int], tuple[str, RGB]] = {}
        for cx, cy, base, speed, off in self._stars:
            b = base * (0.55 + 0.45 * math.sin(t * speed + off))
            if b < 0.25:
                continue
            char = "·" if b < 0.5 else "∙" if b < 0.7 else "•" if b < 0.88 else "+"
            stars[(cx, cy)] = (
                char,
                mix(SUBTLE, TEXT, b) if b > 0.6 else mix(HL_MED, SUBTLE, b),
            )
        for key in stars.keys() | self._star_cells.keys():
            if stars.get(key) != self._star_cells.get(key):
                dirty.add(key[1])
        self._star_cells = stars

        # Falling petals drift right on a gusting breeze
        sw = w * 2
        wind = (
            0.36 + 0.28 * math.sin(t * 0.021) + 0.16 * math.sin(t * 0.057) + 0.5 * gust
        )
        target = min(120, max(12, w * h // 80))
        rng = self._rng
        if (
            self._blossom_pixels
            and len(self._petals) < target
            and rng.random() < 0.5 + 0.4 * gust
        ):
            bx, by = rng.choice(self._blossom_pixels)
            self._petals.append(Petal(bx, by, rng))
        alive = []
        for p in self._petals:
            p.y += p.vy
            p.x += wind + 0.44 * math.sin(t * p.freq + p.phase)
            ix = int(p.x)
            if 0 <= ix < sw and p.y < self._ground[ix]:
                alive.append(p)
            elif (ix, int(p.y)) in self._pond_pixels and len(self._floaters) < 12:
                # petals that land in the pond float for a while
                self._floaters.append(
                    [p.x, int(p.y) // 2, p.color, rng.randint(90, 170)]
                )
        self._petals = alive
        rows = {int(p.y) // 4 for p in alive}
        dirty |= rows | self._petal_rows
        self._petal_rows = rows

        # Floating petals drift slowly with the wind and sink away
        floating = []
        for f in self._floaters:
            f[0] += 0.02 * wind
            f[3] -= 1
            if f[3] > 0 and (int(f[0]), f[1] * 2 + 1) in self._pond_pixels:
                floating.append(f)
        self._floaters = floating
        rows = {f[1] // 2 for f in floating}
        dirty |= rows | self._floater_rows
        self._floater_rows = rows

        # Koi wander, turning back toward the middle before they reach the rim
        if self._pond is not None:
            cx, cy, rx, ry = self._pond
            qcy, qry = cy / 2, ry / 2
            for k in self._koi:
                k.turn = max(
                    -0.06, min(0.06, k.turn * 0.92 + rng.uniform(-0.012, 0.012))
                )
                k.heading += k.turn
                ax = k.x + math.cos(k.heading) * 4
                ay = k.y + math.sin(k.heading) * 2
                if ((ax - cx) / (rx - 3)) ** 2 + ((ay - qcy) / (qry - 1.2)) ** 2 > 1:
                    home = math.atan2((qcy - k.y) * 2, cx - k.x)
                    diff = (home - k.heading + math.pi) % math.tau - math.pi
                    k.heading += max(-0.12, min(0.12, diff))
                k.x += math.cos(k.heading) * k.speed
                k.y += math.sin(k.heading) * k.speed * 0.5
            rows = {qy // 2 for k in self._koi for _, qy, _ in k.pixels(t)}
            dirty |= rows | self._koi_rows
            self._koi_rows = rows

        for y in dirty:
            if 0 <= y < h:
                self._strips[y] = None
        if dirty:
            self.refresh()

    # --- rendering ----------------------------------------------------------

    def _style(self, fg: RGB | None, bg: RGB) -> Style:
        key = (fg, bg)
        style = self._styles.get(key)
        if style is None:
            style = Style.from_color(
                None if fg is None else Color.from_rgb(*fg), Color.from_rgb(*bg)
            )
            self._styles[key] = style
        return style

    def render_line(self, y: int) -> Strip:
        w = self.size.width
        if (
            (w, self.size.height) != self._scene_size
            or self._moon_step is None
            or y >= len(self._strips)
        ):
            return Strip.blank(w, self._style(None, BASE))
        strip = self._strips[y]
        if strip is None:
            strip = self._render_row(y)
            self._strips[y] = strip
        return strip

    def _render_row(self, cy: int) -> Strip:
        top = self._quad[cy * 2][:]
        bot = self._quad[cy * 2 + 1][:]
        qw = len(top)
        # Koi swim just under the surface, so take on a little of the water's color
        t = self._frame
        for k in self._koi:
            for qx, qy, color in k.pixels(t):
                if qy // 2 == cy and (qx, qy * 2 + 1) in self._pond_pixels:
                    row = top if qy % 2 == 0 else bot
                    row[qx] = mix(color, row[qx], 0.15)
        for fx, qy, color, left in self._floaters:
            if qy // 2 == cy:
                row = top if qy % 2 == 0 else bot
                qx = int(fx)
                row[qx] = mix(row[qx], color, min(1.0, left / 40))
        # Each petal is one display pixel
        for p in self._petals:
            qy, qx = int(p.y) // 2, int(p.x)
            if qy // 2 == cy and 0 <= qx < qw:
                (top if qy % 2 == 0 else bot)[qx] = p.color

        segments: list[Segment] = []
        run_text, run_style = "", None
        for x in range(qw // 2):
            block = (top[x * 2], top[x * 2 + 1], bot[x * 2], bot[x * 2 + 1])
            star = self._star_cells.get((x, cy))
            if star is not None:
                text, style = star[0], self._style(star[1], _avg(list(block)))
            else:
                # Sky and foliage blocks repeat constantly, so cache the fit per color block
                fit = self._fits.get(block)
                if fit is None:
                    if len(self._fits) > 200_000:
                        self._fits.clear()
                    text, fg, bg = fit_quadrant(block)
                    fit = self._fits[block] = (text, self._style(fg, bg))
                text, style = fit
            if style is run_style:
                run_text += text
            else:
                if run_text:
                    segments.append(Segment(run_text, run_style))
                run_text, run_style = text, style
        if run_text:
            segments.append(Segment(run_text, run_style))
        return Strip(segments, qw // 2)
