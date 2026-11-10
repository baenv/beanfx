"""Shared helpers for pixel-art effects: hue-shifted ramps, shade maps, strokes, periodic noise and impact frames.

A cell is drawn as a shade map: an int8 array (h, w) where -1 is clear and 0..n-1 picks a colour of the effect's
palette (0 the cool shadow, the last the warm pale core). Palette, cell size and pivot come from the brief.
"""
import colorsys
import math

import numpy as np

COOL_HUE = 230.0  # shadows lean toward blue
WARM_HUE = 55.0  # highlights lean toward yellow


def hexc(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def tohex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb)


def _toward(h, target, deg):
    """Hue h (degrees) moved deg degrees along the short way to target."""
    d = (target - h + 540.0) % 360.0 - 180.0
    return (h + math.copysign(min(abs(d), deg), d)) % 360.0


def _hsv(rgb):
    return colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))


def _rgb(h, s, v):
    return tuple(c * 255.0 for c in colorsys.hsv_to_rgb(h, max(0.0, min(1.0, s)), max(0.0, min(1.0, v))))



def ramp(base):
    """Four hue-shifted shades from one hex colour: shadow 22 degrees cooler, base, light 12 warmer, pale core 20
    warmer."""
    h, s, v = _hsv(hexc(base))
    hd = h * 360.0
    shadow = _rgb(_toward(hd, COOL_HUE, 22.0) / 360.0, s * 1.15 + 0.1, v * 0.62)
    base = _rgb(h, s * 1.05, v)
    light = _rgb(_toward(hd, WARM_HUE, 12.0) / 360.0, s * 0.62, min(1.0, v * 1.12 + 0.06))
    core = _rgb(_toward(hd, WARM_HUE, 20.0) / 360.0, s * 0.22, 1.0)
    return [tohex(c) for c in (shadow, base, light, core)]


def empty(w, h):
    return np.full((h, w), -1, np.int8)


def grid(w, h, cx, cy):
    """Pixel-centre coordinates relative to (cx, cy): arrays x, y of shape (h, w)."""
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    return xs + 0.5 - cx, ys + 0.5 - cy


def wgrid(cw, ch, px, py, density=1.0):
    """grid over a cell (sheet px, pivot in sheet px) in world px at density sheet px per world px, so shapes
    written in world px draw finer at a density above 1; positions for put and line stay in sheet px."""
    x, y = grid(cw, ch, px, py)
    return x / density, y / density


class Pen:
    """put and line in the world px of grid and wgrid (relative to the pivot), so a draft writes every position
    in one frame: pen = Pen(px, py, density); pen.put(m, x, y, s); pen.line(m, x0, y0, x1, y1, s)."""

    def __init__(self, px, py, density=1.0):
        self.px, self.py, self.density = px, py, density

    def sheet(self, x, y):
        """World px to the sheet px that put and line take (the pixel whose centre the grid reads as x, y)."""
        return x * self.density + self.px - 0.5, y * self.density + self.py - 0.5

    def put(self, m, x, y, s):
        put(m, *self.sheet(x, y), s)

    def put_max(self, m, x, y, s):
        put_max(m, *self.sheet(x, y), s)

    def line(self, m, x0, y0, x1, y1, s, keep_max=False):
        line(m, *self.sheet(x0, y0), *self.sheet(x1, y1), s, keep_max)


def stroke(x, y, pts, w0, w1=0.0):
    """A tapered polyline over float grids x, y: arrays (d, t, side) where d < 0 is inside (distance past the local
    half width), t runs 0 to 1 from the first point to the last and side is the signed offset (left of travel < 0).
    The shape for claws, crescents, jaws, rays and cracks."""
    pts = np.asarray(pts, float)
    seg = pts[1:] - pts[:-1]
    ln = np.hypot(seg[:, 0], seg[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(ln)])
    tot = max(cum[-1], 1e-9)
    best = np.full(x.shape, np.inf)
    tt = np.zeros(x.shape)
    sd = np.zeros(x.shape)
    for i in range(len(seg)):
        (ax, ay), (dx, dy), li = pts[i], seg[i], max(ln[i], 1e-9)
        u = np.clip(((x - ax) * dx + (y - ay) * dy) / (li * li), 0, 1)
        t = (cum[i] + u * li) / tot
        d = np.hypot(x - ax - u * dx, y - ay - u * dy) - (w0 + (w1 - w0) * t) / 2
        better = d < best
        best[better] = d[better]
        tt[better] = t[better]
        sd[better] = (((x - ax) * dy - (y - ay) * dx) / li)[better]
    return best, tt, sd


def stamp(dst, src, ox=0, oy=0):
    """Draw shade map src over dst at offset, clear pixels skipped, clipped."""
    h, w = dst.shape
    sh, sw = src.shape
    for j in range(sh):
        y = oy + j
        if not 0 <= y < h:
            continue
        for i in range(sw):
            x = ox + i
            if 0 <= x < w and src[j, i] >= 0:
                dst[y, x] = src[j, i]


def put(m, x, y, s):
    x, y = int(round(x)), int(round(y))
    if 0 <= y < m.shape[0] and 0 <= x < m.shape[1]:
        m[y, x] = s


def put_max(m, x, y, s):
    """Like put, but keeps the brighter shade."""
    x, y = int(round(x)), int(round(y))
    if 0 <= y < m.shape[0] and 0 <= x < m.shape[1]:
        m[y, x] = max(int(m[y, x]), s)


def line(m, x0, y0, x1, y1, s, keep_max=False):
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for k in range(n + 1):
        t = k / max(1, n)
        (put_max if keep_max else put)(m, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, s)


def outline(m, s=0):
    """Adds a 1 px shade-s rim (4-neighbour) round the drawn pixels."""
    on = m >= 0
    grow = on.copy()
    grow[1:, :] |= on[:-1, :]
    grow[:-1, :] |= on[1:, :]
    grow[:, 1:] |= on[:, :-1]
    grow[:, :-1] |= on[:, 1:]
    out = m.copy()
    out[grow & ~on] = s
    return out


def lattice(nx, ny, seed):
    return np.random.default_rng(seed).random((ny, nx))


def noise(x, y, cells, seed, period=None):
    """Smooth value noise in [0, 1] over float arrays x, y. cells is the lattice size in px; period (px, px)
    makes it tile so loops stay seamless."""
    px, py = period if period else (1024, 1024)
    nx, ny = max(1, int(round(px / cells))), max(1, int(round(py / cells)))
    lat = lattice(nx, ny, seed)
    gx, gy = x / cells, y / cells
    x0, y0 = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = gx - x0, gy - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

    def at(i, j):
        return lat[j % ny, i % nx]
    a = at(x0, y0) * (1 - fx) + at(x0 + 1, y0) * fx
    b = at(x0, y0 + 1) * (1 - fx) + at(x0 + 1, y0 + 1) * fx
    return a * (1 - fy) + b * fy


def checker(x, y, phase=0):
    return ((np.floor(x).astype(int) + np.floor(y).astype(int) + phase) % 2) == 0


def ground_dist(x, y, rx, ry):
    """Elliptic distance over pixel grids x, y: 1.0 on the rim of (rx, ry), 0 at the centre."""
    return np.sqrt((x / max(rx, 0.5)) ** 2 + (y / max(ry, 0.5)) ** 2)


def ground_ring(m, cx, cy, rx, ry, width=3, shades=(1, 2, 3), dither=True, rim=0):
    """Paints a solid ground ring into shade map m: a band width px thick inside the ellipse (rx, ry) about
    (cx, cy), shaded outer to inner by shades, a dithered inner fade and a shade-rim outline (None skips it)."""
    h, w = m.shape
    x, y = grid(w, h, cx, cy)
    d = ground_dist(x, y, rx, ry)
    band = max(1.0, float(width)) / max(rx, 1.0)
    t = (1.0 - d) / band  # 0 on the rim, 1 at the inner edge of the band
    on = (d <= 1.0) & (t <= 1.0)
    out = m.copy()
    k = len(shades)
    for i, sh in enumerate(shades):
        sel = on & (t >= i / k) & (t <= (i + 1) / k)
        out[sel] = sh
    if dither:
        fade = (t > 1.0) & (t <= 1.6) & checker(x, y)
        out[fade & (out < 0)] = shades[0]
    if rim is not None:
        solid = np.where(on, out, -1).astype(m.dtype)
        edge = (outline(solid, rim) == rim) & ~on & (out < 0) & (d > 1.0)
        out[edge] = rim
    m[:] = out
    return m

HOT = "#fffaf0"  # the white-hot flash of an impact peak


def _lum(c):
    r, g, b = hexc(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def heat(cell, palette, steps, core=0):
    """Cell (h, w, 4) white-hot: each colour moves toward HOT (half way at steps 1, 0.8 at 2) and snaps to the nearest
    palette colour, so hues hold; the darkest colour (the rim) stays. With core > 0 only a core of about core percent of
    the shape (its inner pixels) heats up: a white core inside the coloured rim, never a whole white silhouette."""
    pal = list(dict.fromkeys(list(palette) + [HOT]))
    rgb = np.array([hexc(c) for c in pal], float)
    rim = min(pal, key=_lum)
    k = 0.5 if steps == 1 else 0.8
    out = cell.copy()
    on = cell[:, :, 3] > 0
    key = cell[:, :, 0].astype(int) << 16 | cell[:, :, 1].astype(int) << 8 | cell[:, :, 2].astype(int)
    hot = np.array(hexc(HOT), float)
    inner = on
    if core:  # erode a pixel at a time until the core is a share of the shape (core is that share in percent)
        total = max(1, int(on.sum()))
        best = np.zeros_like(on)
        cur = on
        for _ in range(40):
            p = np.pad(cur, 1)
            cur = cur & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
            if not cur.any():
                break
            best = cur
            if cur.sum() <= total * core / 100.0:
                break
        inner = best
    for c in pal:
        if c == rim:
            continue
        r, g, b = hexc(c)
        sel = inner & (key == (r << 16 | g << 8 | b))
        if sel.any():
            want = np.array((r, g, b), float) * (1 - k) + hot * k
            out[sel, :3] = rgb[int(np.argmin(((rgb - want) ** 2).sum(axis=1)))].astype(np.uint8)
    return out


def contract(cell, pivot, k):
    """Cell shrunk toward pivot by k (nearest): the gathering frame before a blow lands."""
    h, w = cell.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    rx = np.round(pivot[0] + (xs + 0.5 - pivot[0]) / k - 0.5).astype(int)
    ry = np.round(pivot[1] + (ys + 0.5 - pivot[1]) / k - 0.5).astype(int)
    inside = (rx >= 0) & (rx < w) & (ry >= 0) & (ry < h)  # off-cell sources stay clear, never smear the edge
    out = cell[np.clip(ry, 0, h - 1), np.clip(rx, 0, w - 1)].copy()
    out[~inside] = 0
    return out


def impact_order(n, peak, hold=2):
    """Source frame per slot of an n frame one-shot whose widest frame is peak: slot 0 the anticipation, slots
    1..hold the white-hot peak, the rest the dissolve eased out (it leaves fast and lingers on the last wisps)."""
    m = n - 1 - hold
    src = [peak] * (1 + hold)
    tail = list(range(peak + 1, n)) or [peak]
    for j in range(m):
        u = j / max(1, m - 1)
        src.append(tail[min(len(tail) - 1, int(round((len(tail) - 1) * (1 - (1 - u) ** 2))))])
    return src


def flash_rays(cell, palette, step, box, seed=0):
    """Radial tapered streaks of mixed length round the shape of a white-hot impact cell: step 1 bursts
    them from the shape's rim, step 2 shows them flown further out and thinner. Drawn on clear pixels only, inside box
    (y0, y1, x0, x1, the row's opaque bounds over all frames, so the blow never grows), the root in HOT and the rest in
    the palette's lightest colour; a flat shape (ground decal) lays them flat."""
    on = cell[:, :, 3] > 0
    n_on = int(on.sum())
    if n_on < 6:
        return cell
    ys, xs = np.nonzero(on)
    cy, cx = ys.mean() + 0.5, xs.mean() + 0.5
    flat = 0.5 if (ys.max() - ys.min() + 1) < 0.6 * (xs.max() - xs.min() + 1) else 1.0
    R = math.sqrt(n_on / math.pi)
    h, w = on.shape
    gy, gx = np.mgrid[0:h, 0:w].astype(float)
    dx, dy = gx + 0.5 - cx, (gy + 0.5 - cy) / flat
    r = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)
    n = 8 if R < 12 else 12
    r0 = R * (1.0 if step == 1 else 1.35)
    span = max(3.0, 0.7 * R)
    width = max(1.2, 0.14 * R) * (1.0 if step == 1 else 0.7)
    hot = np.array(hexc(HOT), np.uint8)
    light = np.array(hexc(max((c for c in palette if c != HOT), key=_lum)), np.uint8)
    y0, y1, x0, x1 = box
    inbox = np.zeros_like(on)
    inbox[y0:y1 + 1, x0:x1 + 1] = True
    out = cell.copy()
    rng = np.random.default_rng(seed)
    turn = rng.random() * math.tau
    for j in range(n):
        a = turn + math.tau * j / n + 0.3 * (rng.random() - 0.5)
        L = r0 + span * (1.0 if j % 2 == 0 else 0.55) * (0.85 + 0.3 * rng.random())
        da = (th - a + math.pi) % math.tau - math.pi
        t = (r - r0) / max(L - r0, 1e-6)
        ray = (t >= 0) & (t <= 1) & (np.abs(r * np.sin(da)) <= 0.5 * width * (1 - t) + 0.35) & (np.abs(da) < math.pi / 2)
        sel = ray & ~on & inbox
        out[sel, :3] = np.where((t[sel] < 0.4)[:, None] & (step == 1), hot, light)
        out[sel, 3] = 255
    return out

