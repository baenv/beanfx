"""Bring a pixelfx effect into a Python draft: keep its light (the glow pixelfx does well), redraw or recolour its
colour base, and put them back together. Used by the /beanfx skill.

    node <skill>/tools/layers.mjs fire/fireball --out <dir>        # writes fireball_color.png, _light.png, .json
    fx = pfx.load(<dir>, "fireball")    # fx.color (n, h, w, 4) uint8, fx.light (n, h, w, 3) float 0..1, fx.meta
    L = pfx.tint(fx.light, ["#4a1060", "#c040ff", "#ffe0ff"])     # same glow shape, new hue ramp
    L = pfx.gain(L, 0.8)                                            # weaker or stronger
    L = pfx.keep(L, mask)                                           # light only where mask is true
    L = pfx.bands(L)                                                # stepped light for a hard pixel look (optional)
    base = pfx.paint(shades, palette)    # an fxlib-style shade map (h, w) of palette indices, -1 empty, to RGBA
    out = pfx.composite(base, L[i], bg="#101018")                  # one frame; bg None keeps transparency
    pfx.strip(frames, path) / pfx.gif(frames, path, fps, scale=4)  # write the result
    pfx.contact(path, frames, fps, ref=(ref_frames, ref_fps))       # labelled moments, the draft over a reference
    pfx.takes(path, [("subtle", fr1), ("medium", fr2)], fps)        # takes side by side to pick from: png, and gif

Colour and light keep the pixelfx contract: colour is ordinary RGBA (opaque, dithered or translucent), light is
added on top. Over transparency the light becomes colour with alpha equal to its brightest channel.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


class Layers:
    def __init__(self, color, light, meta):
        self.color, self.light, self.meta = color, light, meta


def _hexa(s):
    """#rgb, #rgba, #rrggbb or #rrggbbaa to (r, g, b, a) floats 0..255."""
    s = s.lstrip("#")
    if len(s) in (3, 4):
        s = "".join(c * 2 for c in s)
    if len(s) not in (6, 8):
        raise ValueError(f"bad hex colour #{s}")
    return np.array([int(s[i:i + 2], 16) for i in range(0, len(s), 2)] + ([255] if len(s) == 6 else []), float)


def _hex(s):
    return _hexa(s)[:3]


def _cells(img, n, w):
    return np.stack([img[:, i * w:(i + 1) * w] for i in range(n)])


def load(folder, name):
    folder = Path(folder)
    meta = json.loads((folder / f"{name}.json").read_text())
    n, w = meta["frames"], meta["w"]
    color = _cells(np.asarray(Image.open(folder / f"{name}_color.png").convert("RGBA")), n, w)
    light = _cells(np.asarray(Image.open(folder / f"{name}_light.png").convert("RGB")), n, w) / 255.0
    return Layers(color, light, meta)


def luma(light):
    return light.max(axis=-1)


def tint(light, ramp):
    """Recolour light by its strength along a hex ramp, weak to strong (the strongest light takes the last tone).
    The tones set hue and saturation only; the brightness stays the source light's, so scale it with gain."""
    v = luma(light)
    tones = np.stack([_hex(c) / 255.0 for c in ramp])
    t = v * (len(tones) - 1)
    i = np.clip(t.astype(int), 0, len(tones) - 2)
    f = (t - i)[..., None]
    rgb = tones[i] * (1 - f) + tones[i + 1] * f
    return rgb * (v / np.maximum(rgb.max(axis=-1), 1e-6))[..., None]


def gain(light, k):
    return np.clip(light * k, 0, 1)


def keep(light, mask):
    return light * mask[..., None]


def bands(light, cuts=(0.08, 0.2, 0.4), levels=(0.3, 0.55, 0.8)):
    """Light cut into hard steps; the outer band is checker dithered, as light.bands does. The top step caps
    the light (0.8 by default); add a cut and a level of 1.0 to keep a white-hot core."""
    v = luma(light)
    out = np.zeros_like(v)
    for c, lv in zip(cuts, levels):
        out = np.where(v >= c, lv, out)
    yy, xx = np.indices(v.shape[-2:])
    outer = (v >= cuts[0]) & (v < cuts[1]) & (((xx + yy) % 2) == 1)
    out = np.where(outer, 0, out)
    return light / np.maximum(v, 1e-6)[..., None] * out[..., None]


def paint(shades, palette):
    """Shade map (h, w) of palette indices, -1 or out of range for empty, to RGBA uint8."""
    out = np.zeros((*shades.shape, 4), np.uint8)
    for s, c in enumerate(palette):
        if c is not None:
            out[shades == s] = _hexa(c).astype(np.uint8)
    return out


def composite(color, light, bg=None):
    """One frame: colour (h, w, 4) uint8 plus light (h, w, 3) 0..1. bg a hex for a flat ground, None for alpha."""
    a = color[..., 3:4] / 255.0
    rgb = color[..., :3] / 255.0
    if bg is not None:
        rgb = rgb * a + _hex(bg) / 255.0 * (1 - a)
        rgb = np.clip(rgb + light, 0, 1)
        alpha = np.ones_like(a)
    else:
        pre = rgb * a + light
        alpha = np.clip(np.maximum(a, light.max(axis=-1, keepdims=True)), 0, 1)
        rgb = np.clip(pre / np.maximum(alpha, 1e-6), 0, 1)
    return (np.concatenate([rgb, alpha], axis=-1) * 255).round().astype(np.uint8)


def strip(frames, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.concatenate(list(frames), axis=1), "RGBA").save(path)


def gif(frames, path, fps, scale=4, bg="#101018"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ims = []
    for f in frames:
        if f[..., 3].min() < 255:
            f = composite(f, np.zeros((*f.shape[:2], 3)), bg)
        im = Image.fromarray(f[..., :3]).resize((f.shape[1] * scale, f.shape[0] * scale), Image.NEAREST)
        ims.append(im)
    ims[0].save(path, save_all=True, append_images=ims[1:], duration=round(1000 / fps), loop=0, disposal=2)


def _flat(f, bg):
    return composite(f, np.zeros((*f.shape[:2], 3)), bg)[..., :3] if f[..., 3].min() < 255 else f[..., :3]


def contact(path, frames, fps, n=12, scale=3, bg="#101018", ref=None, by="phase", names=("draft", "ref")):
    """A contact sheet: n moments of the effect in a row, each labelled with its frame and time, so timing reads
    without the gif. ref (frames, fps) adds a second row at the same moments for the benchmark: by "phase" the same
    share of each one's length (0, 1/(n-1), .. 1), by "time" the same seconds (a cell past the end stays empty).
    Frames are RGBA uint8 (h, w, 4) as composite gives; transparency goes over bg. Returns the frame indices used."""
    runs = [(names[0], list(frames), fps)] + ([(names[1], list(ref[0]), ref[1])] if ref is not None else [])
    span = max((len(fr) - 1) / f for _, fr, f in runs)
    picks = []
    for _, fr, f in runs:
        N = len(fr)
        if by == "time":
            idx = [round(k / max(1, n - 1) * span * f) for k in range(n)]
            picks.append([i if i < N else None for i in idx])
        else:
            picks.append([round(k / max(1, n - 1) * (N - 1)) for k in range(n)])
    ch = max(fr[0].shape[0] for _, fr, _ in runs) * scale
    cw = max(fr[0].shape[1] for _, fr, _ in runs) * scale
    lab, gap, head = 12, 4, 14
    im = Image.new("RGB", (n * (cw + gap) + gap, len(runs) * (ch + lab + head + gap) + gap), tuple(_hex(bg).astype(int)))
    dr = ImageDraw.Draw(im)
    for r, ((name, fr, f), idx) in enumerate(zip(runs, picks)):
        y0 = gap + r * (ch + lab + head + gap)
        dr.text((gap, y0), f"{name}: {len(fr)} frames, {f} fps, {len(fr) / f:.2f} s", fill=(220, 220, 230))
        for k, i in enumerate(idx):
            if i is None:
                continue
            a = _flat(fr[i], bg)
            cell = Image.fromarray(a).resize((a.shape[1] * scale, a.shape[0] * scale), Image.NEAREST)
            x = gap + k * (cw + gap)
            im.paste(cell, (x + (cw - cell.width) // 2, y0 + head + (ch - cell.height) // 2))
            dr.text((x, y0 + head + ch + 1), f"f{i} {i / f:.2f}s", fill=(170, 170, 185))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return picks


def takes(path, options, fps=None, scale=4, bg="#101018"):
    """Takes to pick from, side by side at scale, each labelled: options is [(label, frames)], frames a list of RGBA
    uint8 (h, w, 4) as composite gives (a peak frame alone, or the frames round it). Writes path (png, the first frame
    of each take) and, when fps is given and a take has more than one frame, the same name as a gif that plays them
    in step, the shortest take holding its last frame. Returns the paths written."""
    path = Path(path)
    runs = [(str(lab), list(fr)) for lab, fr in options]
    ch = max(fr[0].shape[0] for _, fr in runs) * scale
    cw = max(fr[0].shape[1] for _, fr in runs) * scale
    gap, head = 8, 16
    size = (len(runs) * (cw + gap) + gap, ch + head + 2 * gap)

    def board(k):
        im = Image.new("RGB", size, tuple(_hex(bg).astype(int)))
        dr = ImageDraw.Draw(im)
        for n, (lab, fr) in enumerate(runs):
            a = _flat(fr[min(k, len(fr) - 1)], bg)
            cell = Image.fromarray(a).resize((a.shape[1] * scale, a.shape[0] * scale), Image.NEAREST)
            x = gap + n * (cw + gap)
            dr.text((x, gap), "%d. %s" % (n + 1, lab), fill=(220, 220, 230))
            im.paste(cell, (x + (cw - cell.width) // 2, gap + head + (ch - cell.height) // 2))
        return im

    path.parent.mkdir(parents=True, exist_ok=True)
    board(0).save(path)
    written = [path]
    n = max(len(fr) for _, fr in runs)
    if fps and n > 1:
        g = path.with_suffix(".gif")
        ims = [board(k) for k in range(n)]
        ims[0].save(g, save_all=True, append_images=ims[1:], duration=round(1000 / fps), loop=0)
        written.append(g)
    return written
