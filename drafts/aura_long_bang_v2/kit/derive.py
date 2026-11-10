"""Points and lines derived from a finished drawing, for the states that build up to it or break down from it.

Draw the peak frame first (the hero: the carrier whole, posed as it reads best), then take every build-up and
break-down state from its masks, never from hand-placed points. The stars of a constellation sit on its outline,
gathering motes land inside it, a sketch-in stroke runs its spine, shards and dissolve motes leave from its
pixels. One source: a change to the drawing moves every state with it. Learnt on drafts/tinh_long_chuong (the
constellation traced from the solid head).

    import derive as dv
    tone, parts = draw_head(..., trace=True)          # shade map (-1 empty) and part ids (-1 empty) at the peak
    m = tone >= 0
    ring = dv.simplify(dv.outline(m), 90)            # ~90 corners round the silhouette, in order: stars, threads
    inner = [dv.simplify(c, 12, closed=False) for c in dv.part_lines(parts)]   # jaw line, eye, horn roots
    axis = dv.spine(m)                                # centre lines: a body that uncoils, a sketch stroke
    seeds = dv.scatter(m, 60)                         # even points inside: landing spots, shards, motes
    loc = dv.local(ring, anchor, ang, scale)          # store in the carrier's frame ...
    pts = dv.world(loc, anchor_f, ang_f, scale_f)     # ... and place them on any frame as the carrier moves

Points are (x, y) at pixel centres (column, row), as float arrays of shape (n, 2).
"""
import math

import numpy as np

_D8 = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def outline(m):
    """Outer boundary of the largest blob in mask m, clockwise on screen, as (x, y) pixels; holes are ignored."""
    m = _largest(np.asarray(m, bool))
    p = np.pad(m, 1)
    ys, xs = np.nonzero(p)
    i = np.lexsort((xs, ys))[0]
    x0, y0 = int(xs[i]), int(ys[i])
    out, x, y, d, first = [(x0, y0)], x0, y0, 0, None
    for _ in range(4 * p.size):
        for k in range(8):
            nd = (d + 6 + k) % 8
            nx, ny = x + _D8[nd][0], y + _D8[nd][1]
            if p[ny, nx]:
                break
        else:
            break                                   # a single pixel
        if (x, y) == (x0, y0):
            if first is None:
                first = nd
            elif nd == first:
                break
        x, y, d = nx, ny, nd
        out.append((x, y))
    P = np.array(out[:-1] if len(out) > 1 else out, float) - 1
    return P


def simplify(P, n, closed=True):
    """The n most telling corners of polyline P, kept in order: each point is ranked by the error it fixes when
    Ramer-Douglas-Peucker splits there, and the top n stay. closed: P is a loop, split at the point farthest
    from P[0] so both halves keep their corners."""
    P = np.asarray(P, float)
    if len(P) <= n:
        return P.copy()
    if closed:
        far = int(np.argmax(np.hypot(*(P - P[0]).T)))
        rank = np.zeros(len(P))
        rank[[0, far]] = np.inf
        rank[:far + 1] = np.maximum(rank[:far + 1], _rank(P[:far + 1]))
        tail = _rank(np.vstack([P[far:], P[:1]]))[:-1]
        rank[far:] = np.maximum(rank[far:], tail)
    else:
        rank = _rank(P)
    keep = np.sort(np.argsort(-rank, kind="stable")[:n])
    return P[keep]


def part_lines(parts, min_len=3):
    """Lines where two labelled parts meet (the jaw against the skull, an eye in the face), as ordered chains.
    parts: int map, -1 empty. Each boundary pixel is taken on the side of the larger id, so a line is 1 px."""
    p = np.asarray(parts)
    b = np.zeros(p.shape, bool)
    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        q = np.full(p.shape, -1)
        q[max(dy, 0):p.shape[0] + min(dy, 0), max(dx, 0):p.shape[1] + min(dx, 0)] = \
            p[max(-dy, 0):p.shape[0] + min(-dy, 0), max(-dx, 0):p.shape[1] + min(-dx, 0)]
        b |= (p >= 0) & (q >= 0) & (q < p)
    return [c for c in chains(b) if len(c) >= min_len]


def spine(m, min_len=3):
    """Centre lines of mask m (Zhang-Suen thinning), as ordered chains, longest first."""
    return [c for c in chains(_thin(np.asarray(m, bool))) if len(c) >= min_len]


def scatter(m, n, seed=0):
    """n points spread evenly inside mask m (farthest point sampling from a seeded start), as (x, y) pixels."""
    ys, xs = np.nonzero(m)
    C = np.stack([xs, ys], 1).astype(float)
    if len(C) <= n:
        return C
    rng = np.random.default_rng(seed)
    pick = [int(rng.integers(len(C)))]
    d = np.hypot(*(C - C[pick[0]]).T)
    for _ in range(n - 1):
        k = int(np.argmax(d))
        pick.append(k)
        d = np.minimum(d, np.hypot(*(C - C[k]).T))
    return C[pick]


def chains(b):
    """1 px wide pixels of mask b as ordered 8-connected chains, each from an end where it has one, longest first."""
    b = np.asarray(b, bool).copy()
    pts = set(zip(*np.nonzero(b)))
    deg = {}
    for (y, x) in pts:
        deg[(y, x)] = sum((y + dy, x + dx) in pts for dx, dy in _D8)
    out = []
    while pts:
        ends = [q for q in pts if deg[q] <= 1]
        start = min(ends) if ends else min(pts)
        chain, cur = [start], start
        pts.discard(start)
        while True:
            y, x = cur
            nb = [(y + dy, x + dx) for dx, dy in _D8 if (y + dy, x + dx) in pts]
            if not nb:
                break
            nb.sort(key=lambda q: (abs(q[0] - y) + abs(q[1] - x), q))       # side neighbours before corners
            cur = nb[0]
            pts.discard(cur)
            chain.append(cur)
        out.append(np.array([(x, y) for y, x in chain], float))
    out.sort(key=len, reverse=True)
    return out


def local(P, anchor, ang=0.0, scale=1.0):
    """World points to the carrier's frame: about anchor, unrotated by ang, divided by scale."""
    P = np.asarray(P, float) - np.asarray(anchor, float)
    c, s = math.cos(-ang), math.sin(-ang)
    return np.stack([P[:, 0] * c - P[:, 1] * s, P[:, 0] * s + P[:, 1] * c], 1) / scale


def world(L, anchor, ang=0.0, scale=1.0):
    """Points in the carrier's frame back to the world for a frame whose carrier sits at anchor, ang, scale."""
    L = np.asarray(L, float) * scale
    c, s = math.cos(ang), math.sin(ang)
    return np.stack([L[:, 0] * c - L[:, 1] * s, L[:, 0] * s + L[:, 1] * c], 1) + np.asarray(anchor, float)


# ---- internals ----
def _rank(P):
    """Per point, the deviation at which Ramer-Douglas-Peucker keeps it (inf for the two ends), capped by its
    parent's so a child never outranks the split that made it."""
    rank = np.zeros(len(P))
    rank[0] = rank[-1] = np.inf
    stack = [(0, len(P) - 1, np.inf)]
    while stack:
        i, j, cap = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        ab = b - a
        ln = np.hypot(*ab)
        seg = P[i + 1:j]
        if ln < 1e-9:
            d = np.hypot(*(seg - a).T)
        else:
            d = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / ln
        k = int(np.argmax(d))
        r = min(float(d[k]), cap)
        rank[i + 1 + k] = r
        stack += [(i, i + 1 + k, r), (i + 1 + k, j, r)]
    return rank


def _largest(m):
    """The largest 8-connected blob of m (flood fill, no scipy)."""
    lab = np.zeros(m.shape, int)
    best, best_n, cur = 0, 0, 0
    H, W = m.shape
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        cur += 1
        stack, n = [(y0, x0)], 0
        lab[y0, x0] = cur
        while stack:
            y, x = stack.pop()
            n += 1
            for dx, dy in _D8:
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = cur
                    stack.append((yy, xx))
        if n > best_n:
            best, best_n = cur, n
    return lab == best if best else m


def _thin(m):
    """Zhang-Suen thinning to a 1 px skeleton."""
    img = np.pad(m, 1).astype(np.uint8)
    while True:
        changed = False
        for step in (0, 1):
            P = [np.roll(np.roll(img, -dy, 0), -dx, 1) for dx, dy in
                 ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))]   # p2..p9 clockwise
            B = sum(P)
            A = sum((P[k] == 0) & (P[(k + 1) % 8] == 1) for k in range(8))
            if step == 0:
                c = (P[0] * P[2] * P[4] == 0) & (P[2] * P[4] * P[6] == 0)
            else:
                c = (P[0] * P[2] * P[6] == 0) & (P[0] * P[4] * P[6] == 0)
            rm = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if rm.any():
                img[rm] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1].astype(bool)
