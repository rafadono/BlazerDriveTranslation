"""Redraws text inside DS textures (.sbd containers) while preserving palette and style.

For a box (x, y, w, h) of a texture:
  1. Samples the original text style: outline color index (the darkest one)
     and a per-row gradient (most frequent fill index in each row).
  2. Clears the box (transparent).
  3. Rasterizes the English text without antialiasing (narrow bold font), fitting it to the box.
  4. Paints shadow (+1,+1), outline (8-neighbor dilation) and fill with the gradient.
Only uses colors that already exist in the texture's palette.
"""
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from blazer_drive.sbd import Sbd, Texture

FONTS = [
    Path("C:/Windows/Fonts/ARIALNB.TTF"),   # Arial Narrow Bold
    Path("C:/Windows/Fonts/tahomabd.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
]


# --- pixel access (index, alpha 0-255) ----------------------------------------------
def get_px(s: Sbd, t: Texture, x: int, y: int) -> tuple[int, int]:
    i = y * t.width + x
    d = s.data
    if t.fmt == 4:
        v = d[t.data_pos + i]
        return v, 255 if v else 0
    if t.fmt == 3:
        v = (d[t.data_pos + (i >> 1)] >> ((i & 1) * 4)) & 15
        return v, 255 if v else 0
    if t.fmt == 2:
        v = (d[t.data_pos + (i >> 2)] >> ((i & 3) * 2)) & 3
        return v, 255 if v else 0
    if t.fmt == 1:
        v = d[t.data_pos + i]
        return v & 31, (v >> 5) * 255 // 7
    if t.fmt == 6:
        v = d[t.data_pos + i]
        return v & 7, (v >> 3) * 255 // 31
    raise ValueError(f"unsupported format {t.fmt}")


def set_px(s: Sbd, t: Texture, x: int, y: int, idx: int, alpha: int = 255) -> None:
    i = y * t.width + x
    d = s.data
    if t.fmt == 4:
        d[t.data_pos + i] = idx if alpha else 0
    elif t.fmt == 3:
        p = t.data_pos + (i >> 1)
        sh = (i & 1) * 4
        d[p] = (d[p] & ~(15 << sh) & 0xFF) | ((idx if alpha else 0) << sh)
    elif t.fmt == 2:
        p = t.data_pos + (i >> 2)
        sh = (i & 3) * 2
        d[p] = (d[p] & ~(3 << sh) & 0xFF) | ((idx if alpha else 0) << sh)
    elif t.fmt == 1:
        d[t.data_pos + i] = (idx & 31) | ((alpha * 7 // 255) << 5)
    elif t.fmt == 6:
        d[t.data_pos + i] = (idx & 7) | ((alpha * 31 // 255) << 3)
    else:
        raise ValueError(f"unsupported format {t.fmt}")


# --- style -------------------------------------------------------------------------
def sample_style(s: Sbd, t: Texture, box: tuple[int, int, int, int]):
    x0, y0, w, h = box
    pal = s.palette_colors(s.palette_for(t))
    lum = lambda i: sum(pal[i]) if i < len(pal) else 0
    opaque = [(x, y, *get_px(s, t, x, y)) for y in range(y0, y0 + h) for x in range(x0, x0 + w)]
    opaque = [(x, y, i, a) for x, y, i, a in opaque if a > 128 and i]
    if not opaque:
        raise ValueError(f"empty box {box}")
    outline = min({i for _, _, i, _ in opaque}, key=lum)
    rows: dict[int, int] = {}
    for yy in range(y0, y0 + h):
        c = Counter(i for x, y, i, a in opaque if y == yy and lum(i) > lum(outline) + 60)
        if c:
            rows[yy - y0] = c.most_common(1)[0][0]
    return outline, rows


def _row_index(rows: dict[int, int], ry: int, text_top: int, text_h: int, src_top: int, src_h: int) -> int:
    """Maps a row of the new text to the equivalent row of the original gradient."""
    if not rows:
        return 1
    keys = sorted(rows)
    rel = (ry - text_top) / max(1, text_h - 1)
    target = src_top + rel * (src_h - 1)
    return rows[min(keys, key=lambda k: abs(k - target))]


def render_mask(text: str, w: int, h: int, max_px: int | None = None) -> list[list[bool]]:
    """1-bit mask of the text, the largest that fits in w x h (no antialiasing)."""
    for font_path in FONTS:
        if font_path.exists():
            break
    for size in range(max_px or h + 4, 5, -1):
        font = ImageFont.truetype(str(font_path), size)
        bbox = font.getbbox(text)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= w and th <= h:
            img = Image.new("1", (w, h), 0)
            ImageDraw.Draw(img).text(((w - tw) // 2 - bbox[0], (h - th) // 2 - bbox[1]), text, font=font, fill=1)
            px = img.load()
            return [[bool(px[x, y]) for x in range(w)] for y in range(h)]
    raise ValueError(f"'{text}' does not fit in {w}x{h}")


def redraw(s: Sbd, tex_index: int, box: tuple[int, int, int, int], text: str, max_px: int | None = None) -> None:
    t = s.textures[tex_index]
    x0, y0, w, h = box
    if not text:  # clear only
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                set_px(s, t, x, y, 0, 0)
        return
    outline, rows = sample_style(s, t, box)
    src_rows = sorted(rows)
    src_top, src_h = (src_rows[0], src_rows[-1] - src_rows[0] + 1) if src_rows else (0, h)
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            set_px(s, t, x, y, 0, 0)
    # leave 1 px for the outline on each side and 1 extra at bottom/right for the shadow
    m = render_mask(text, w - 3, h - 3, max_px)
    mh, mw = len(m), len(m[0])
    ys = [y for y in range(mh) if any(m[y])]
    top, th = (ys[0], ys[-1] - ys[0] + 1) if ys else (0, mh)
    filled = lambda xx, yy: 0 <= yy < mh and 0 <= xx < mw and m[yy][xx]
    for yy in range(-1, mh + 2):
        for xx in range(-1, mw + 2):
            X, Y = x0 + 1 + xx, y0 + 1 + yy
            if not (x0 <= X < x0 + w and y0 <= Y < y0 + h):
                continue
            if filled(xx, yy):
                set_px(s, t, X, Y, _row_index(rows, yy, top, th, src_top, src_h))
            elif any(filled(xx + dx, yy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)) or filled(xx - 1, yy - 1):
                set_px(s, t, X, Y, outline)


def components(s: Sbd, tex_index: int, min_px: int = 6) -> list[tuple[int, int, int, int]]:
    """Boxes (x, y, w, h) of the connected (8-neighbor) opaque pieces of a texture."""
    t = s.textures[tex_index]
    W, H = t.width, t.height
    op = [[get_px(s, t, x, y)[1] > 128 and get_px(s, t, x, y)[0] != 0 for x in range(W)] for y in range(H)]
    seen = [[False] * W for _ in range(H)]
    boxes = []
    for y in range(H):
        for x in range(W):
            if op[y][x] and not seen[y][x]:
                stack, pts = [(x, y)], []
                seen[y][x] = True
                while stack:
                    cx, cy = stack.pop()
                    pts.append((cx, cy))
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < W and 0 <= ny < H and op[ny][nx] and not seen[ny][nx]:
                                seen[ny][nx] = True
                                stack.append((nx, ny))
                if len(pts) >= min_px:
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    boxes.append((min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1))
    return sorted(boxes, key=lambda b: (b[1], b[0]))
