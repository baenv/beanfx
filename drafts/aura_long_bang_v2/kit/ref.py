"""Reverse a detailed reference image into maps to draw from: the object's mask, its edges from the image's
derivative, its value levels (how light each part is), and its skeleton. Used when the owner asks for an
object's true structure (a dragon, a sword, a creature): trace the reference, then paint the maps in the
effect's own palette and style.

    import ref
    t = ref.trace("refs/dragon.png", height=96, tones=4)
    t.mask      # (h, w) bool, the object (alpha, else what differs from the border colour)
    t.lum       # (h, w) float 0..1, luminance
    t.grad      # (h, w) float, gradient magnitude (Sobel): where value changes fast
    t.edges     # (h, w) bool, the outline plus inner lines where the gradient is strongest
    t.shade     # (h, w) int8, value level 0 (darkest) .. tones - 1 (lightest), -1 outside
    t.outline   # (x, y) points round the silhouette, clockwise (derive.outline)
    t.spine     # centre-line chains, longest first (derive.spine): the skeleton
    m = ref.paint(t, ramp_index=[0, 1, 2, 3], edge=0)   # shade map in the effect's palette indices

Then draw on top with the kit (fxkit, light) and feed t.outline, t.spine to derive for build-up states.
"""
from types import SimpleNamespace

import numpy as np
from PIL import Image

import derive

SOBEL = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], float)


def load(path, height=None, width=None):
    """RGBA float 0..1 of the image at path, scaled (box filter, so detail averages) to height or width px."""
    im = Image.open(path).convert("RGBA")
    if height or width:
        w = width or round(im.width * height / im.height)
        h = height or round(im.height * width / im.width)
        im = im.resize((max(1, w), max(1, h)), Image.BOX)
    return np.asarray(im, float) / 255.0


def luminance(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _conv3(a, k):
    p = np.pad(a, 1, mode="edge")
    h, w = a.shape
    return sum(k[j, i] * p[j:j + h, i:i + w] for j in range(3) for i in range(3))


def gradient(lum):
    """(magnitude, angle) of the luminance derivative, Sobel 3 x 3."""
    gx, gy = _conv3(lum, SOBEL), _conv3(lum, SOBEL.T)
    return np.hypot(gx, gy), np.arctan2(gy, gx)


def mask_of(img, tol=0.12):
    """The object: the alpha when the image has one, else the pixels whose colour differs from the median border
    colour by more than tol; the largest blob only."""
    a = img[..., 3]
    if a.min() < 0.99:
        m = a > 0.5
    else:
        rgb = img[..., :3]
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        bg = np.median(border, axis=0)
        m = np.abs(rgb - bg).max(axis=-1) > tol
    return derive._largest(m)


def levels(lum, m, tones):
    """Value levels inside mask m: tones bands split at luminance quantiles, 0 darkest; -1 outside."""
    out = np.full(lum.shape, -1, np.int8)
    if not m.any():
        return out
    cuts = np.quantile(lum[m], np.linspace(0, 1, tones + 1)[1:-1])
    out[m] = np.searchsorted(cuts, lum[m], side="right").astype(np.int8)
    return out


def edge_map(grad, m, share=0.12):
    """The silhouette's rim plus the strongest share of the gradient inside it (the inner lines a pixel artist
    would ink: jaw, scale rows, the blade's ridge)."""
    on = np.pad(m, 1)
    rim = m & ~(on[:-2, 1:-1] & on[2:, 1:-1] & on[1:-1, :-2] & on[1:-1, 2:])
    inner = np.zeros_like(m)
    g = grad[m & ~rim]
    if g.size:
        inner = m & ~rim & (grad >= np.quantile(g, 1 - share))
    return rim | inner


def trace(path, height=None, width=None, tones=4, share=0.12, tol=0.12):
    """Every map of the reference at path, at the target size (see the module docstring)."""
    img = load(path, height, width)
    lum = luminance(img[..., :3])
    m = mask_of(img, tol)
    grad, ang = gradient(lum)
    return SimpleNamespace(img=img, mask=m, lum=lum, grad=grad, angle=ang, edges=edge_map(grad, m, share),
                           shade=levels(lum, m, tones), outline=derive.outline(m), spine=derive.spine(m))


def paint(t, ramp_index=None, edge=0):
    """A shade map from the traced levels: level k becomes ramp_index[k] (default k), and the edges become index
    edge (None leaves them to the levels). Draw it with pfx.paint(m, palette)."""
    tones = int(t.shade.max()) + 1
    idx = np.asarray(ramp_index if ramp_index is not None else range(tones), np.int8)
    m = np.where(t.shade >= 0, idx[np.clip(t.shade, 0, len(idx) - 1)], -1).astype(np.int8)
    if edge is not None:
        m[t.edges] = edge
    return m
