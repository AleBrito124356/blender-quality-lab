"""Exposure and layout metrics for rendered PNGs, in pure Python (no Pillow or numpy).

The decoder supports non-interlaced 8/16-bit grayscale, grayscale+alpha, RGB and RGBA, and 8-bit
palette images - what Blender and most tools write. Anything else is rejected with a clear error.
Luminance is Rec.709 luma of the display-encoded values (what a viewer sees), in 0..1.
"""

import struct
import zlib
from collections import Counter
from dataclasses import dataclass
from itertools import accumulate, islice
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
MODES = {0: "gray", 2: "RGB", 3: "palette", 4: "gray+alpha", 6: "RGBA"}
BINS = 1000
ASCII_RAMP = " .:-=+*#%@"


class PngError(ValueError):
    """The file is not a PNG this decoder supports."""


@dataclass
class Png:
    width: int
    height: int
    bit_depth: int
    color_type: int
    rows: list
    palette: list | None = None
    palette_alpha: list | None = None

    @property
    def channels(self):
        return CHANNELS[self.color_type]

    @property
    def mode(self):
        return f"{MODES[self.color_type]} {self.bit_depth}-bit"


def _paeth(left, item):
    raw, up, up_left = item
    estimate = left + up - up_left
    pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - up_left)
    if pa <= pb and pa <= pc:
        return (raw + left) & 255
    if pb <= pc:
        return (raw + up) & 255
    return (raw + up_left) & 255


def _average(left, item):
    raw, up = item
    return (raw + ((left + up) >> 1)) & 255


def _sub(left, raw):
    return (left + raw) & 255


def unfilter(kind, line, previous, bpp):
    """Undo one scanline filter. Each channel byte lane is a running recurrence, run by accumulate()."""
    if kind == 0:
        return bytes(line)
    if kind == 2:
        return bytes((a + b) & 255 for a, b in zip(line, previous))
    out = bytearray(len(line))
    for lane in range(bpp):
        raw = line[lane::bpp]
        if kind == 1:
            out[lane::bpp] = bytes(accumulate(raw, _sub))
        elif kind == 3:
            out[lane::bpp] = bytes(
                islice(accumulate(zip(raw, previous[lane::bpp]), _average, initial=0), 1, None)
            )
        elif kind == 4:
            up = previous[lane::bpp]
            up_left = bytes(1) + up[:-1]
            out[lane::bpp] = bytes(islice(accumulate(zip(raw, up, up_left), _paeth, initial=0), 1, None))
        else:
            raise PngError(f"invalid scanline filter type {kind}")
    return bytes(out)


def decode_png(data):
    """Parse and defilter a PNG from bytes."""
    if not data.startswith(SIGNATURE):
        raise PngError("not a PNG file (bad signature)")
    offset, header, idat = len(SIGNATURE), None, []
    palette = palette_alpha = None
    while offset + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[offset : offset + 8])
        body = data[offset + 8 : offset + 8 + length]
        crc = data[offset + 8 + length : offset + 12 + length]
        if len(body) != length or len(crc) != 4:
            raise PngError("truncated PNG")
        if zlib.crc32(kind + body) != struct.unpack(">I", crc)[0]:
            raise PngError(f"corrupt PNG: CRC mismatch in {kind.decode('latin-1')} chunk")
        offset += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = [tuple(body[i : i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"tRNS":
            palette_alpha = list(body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if header is None:
        raise PngError("PNG has no IHDR chunk")
    width, height, depth, color_type, _compression, _filter, interlace = header
    if color_type not in CHANNELS:
        raise PngError(f"unknown PNG color type {color_type}")
    if interlace:
        raise PngError("interlaced (Adam7) PNGs are not supported; save without interlacing")
    if depth not in (8, 16) or (color_type == 3 and depth != 8):
        raise PngError(
            f"{depth}-bit {MODES[color_type]} PNGs are not supported; save as 8 or 16 bits per channel"
        )
    if color_type == 3 and not palette:
        raise PngError("palette PNG without a PLTE chunk")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise PngError(f"corrupt PNG image data: {exc}") from None
    bpp = CHANNELS[color_type] * depth // 8
    stride = width * bpp
    if len(raw) < height * (stride + 1):
        raise PngError("PNG image data is shorter than its dimensions")
    rows, previous = [], bytes(stride)
    for y in range(height):
        start = y * (stride + 1)
        previous = unfilter(raw[start], raw[start + 1 : start + 1 + stride], previous, bpp)
        rows.append(previous)
    return Png(width, height, depth, color_type, rows, palette, palette_alpha)


def read_png(path):
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        raise PngError(f"{path}: file not found") from None
    return decode_png(data)


def row_samples(image, row):
    """(integer luma list scaled to 0..scale, max-channel list, alpha list or None, scale, maxval)."""
    maxval = 255 if image.bit_depth == 8 else 65535
    if image.bit_depth == 16:
        values = struct.unpack(f">{len(row) // 2}H", row)
    else:
        values = row
    channels = image.channels
    alpha = None
    if image.color_type == 3:
        luma_of = [2126 * r + 7152 * g + 722 * b for r, g, b in image.palette]
        peak_of = [max(entry) for entry in image.palette]
        luma = [luma_of[i] for i in values]
        peak = [peak_of[i] for i in values]
        if image.palette_alpha:
            table = image.palette_alpha + [255] * (len(image.palette) - len(image.palette_alpha))
            alpha = [table[i] for i in values]
    elif channels <= 2:
        gray = values[0::channels]
        luma = [10000 * v for v in gray]
        peak = list(gray)
        if channels == 2:
            alpha = values[1::2]
    else:
        red, green, blue = values[0::channels], values[1::channels], values[2::channels]
        luma = [2126 * r + 7152 * g + 722 * b for r, g, b in zip(red, green, blue)]
        peak = list(map(max, red, green, blue))
        if channels == 4:
            alpha = values[3::4]
    return luma, peak, alpha, 10000 * maxval, maxval


def _bounds(size, parts):
    return [size * i // parts for i in range(parts + 1)]


def measure(image, grid=8, ascii_columns=48):
    """Luminance statistics, clipping, contrast and coarse layout grids for one image."""
    width, height = image.width, image.height
    xs, ys = _bounds(width, grid), _bounds(height, grid)
    ascii_rows = max(4, round(ascii_columns * height / width / 2))
    axs, ays = _bounds(width, ascii_columns), _bounds(height, ascii_rows)
    cell_sum = [[0] * grid for _ in range(grid)]
    cell_detail = [[0] * grid for _ in range(grid)]
    ascii_sum = [[0] * ascii_columns for _ in range(ascii_rows)]
    histogram = Counter()
    total = squares = clipped = crushed = transparent = counted = 0
    previous = None
    scale = maxval = 1
    for y, row in enumerate(image.rows):
        luma, peak, alpha, scale, maxval = row_samples(image, row)
        cy = y * grid // height
        ay = y * ascii_rows // height
        if alpha is not None:
            opaque = [a > 0 for a in alpha]
            transparent += len(alpha) - sum(opaque)
            kept = [v for v, keep in zip(luma, opaque) if keep]
            kept_peak = [p for p, keep in zip(peak, opaque) if keep]
        else:
            kept, kept_peak = luma, peak
        counted += len(kept)
        total += sum(kept)
        squares += sum(v * v for v in kept)
        histogram.update(v * BINS // scale for v in kept)
        clip_level = maxval - maxval // 100
        clipped += sum(1 for p in kept_peak if p >= clip_level)
        crushed += sum(1 for v in kept if v * 50 <= scale)
        for cx in range(grid):
            cell_sum[cy][cx] += sum(luma[xs[cx] : xs[cx + 1]])
        for ax in range(ascii_columns):
            ascii_sum[ay][ax] += sum(luma[axs[ax] : axs[ax + 1]])
        horizontal = [abs(a - b) for a, b in zip(luma[1:], luma)] + [0]
        vertical = [abs(a - b) for a, b in zip(luma, previous)] if previous is not None else [0] * width
        detail = [h + v for h, v in zip(horizontal, vertical)]
        for cx in range(grid):
            cell_detail[cy][cx] += sum(detail[xs[cx] : xs[cx + 1]])
        previous = luma
    pixels = width * height
    result = {
        "width": width,
        "height": height,
        "mode": image.mode,
        "transparent": round(transparent / pixels, 4),
    }
    if counted == 0:
        result.update(luminance=None, near_uniform=True, empty=True)
        result["warnings"] = [{"id": "fully_transparent", "message": "Every pixel is transparent"}]
        return result
    mean = total / counted / scale
    variance = max(0.0, squares / counted / scale / scale - mean * mean)
    std = variance**0.5

    def percentile(fraction):
        target, running = fraction * counted, 0
        for value in sorted(histogram):
            running += histogram[value]
            if running >= target:
                return round(value / BINS, 3)
        return 1.0

    cells = [[(xs[c + 1] - xs[c]) * (ys[r + 1] - ys[r]) or 1 for c in range(grid)] for r in range(grid)]
    grid_luma = [[round(cell_sum[r][c] / cells[r][c] / scale, 3) for c in range(grid)] for r in range(grid)]
    grid_detail = [
        [round(cell_detail[r][c] / cells[r][c] / scale, 4) for c in range(grid)] for r in range(grid)
    ]
    weight = sum(sum(row) for row in grid_detail)
    if weight > 0:
        center_x = (
            sum((c + 0.5) / grid * grid_detail[r][c] for r in range(grid) for c in range(grid)) / weight
        )
        center_y = (
            sum((r + 0.5) / grid * grid_detail[r][c] for r in range(grid) for c in range(grid)) / weight
        )
        detail_center = [round(center_x, 3), round(center_y, 3)]
    else:
        detail_center = None
    ascii_cells = [
        [(axs[c + 1] - axs[c]) * (ays[r + 1] - ays[r]) or 1 for c in range(ascii_columns)]
        for r in range(ascii_rows)
    ]
    ascii_map = [
        "".join(
            ASCII_RAMP[
                min(len(ASCII_RAMP) - 1, int(ascii_sum[r][c] / ascii_cells[r][c] / scale * len(ASCII_RAMP)))
            ]
            for c in range(ascii_columns)
        )
        for r in range(ascii_rows)
    ]
    result.update(
        luminance={
            "mean": round(mean, 4),
            "std": round(std, 4),
            "p2": percentile(0.02),
            "p50": percentile(0.5),
            "p98": percentile(0.98),
        },
        clipped_highlights=round(clipped / counted, 4),
        crushed_shadows=round(crushed / counted, 4),
        rms_contrast=round(std, 4),
        near_uniform=std < 0.02,
        grid={"size": [grid, grid], "luminance": grid_luma, "detail": grid_detail},
        detail_center=detail_center,
        max_cell_detail=max(max(row) for row in grid_detail),
        ascii=ascii_map,
    )
    result["empty"] = result["near_uniform"] or result["max_cell_detail"] < 0.004
    result["warnings"] = exposure_warnings(result)
    return result


def exposure_warnings(metrics):
    lum = metrics["luminance"]
    found = []

    def warn(key, message):
        found.append({"id": key, "message": message})

    if lum["mean"] < 0.02:
        warn("black_frame", f"The frame is essentially black (mean luminance {lum['mean']:.3f})")
    elif lum["mean"] < 0.12 or lum["p98"] < 0.35:
        warn(
            "underexposed",
            f"Underexposed: mean luminance {lum['mean']:.3f}, 98th percentile {lum['p98']:.2f} (aim for 0.25-0.5 mean)",
        )
    if metrics["clipped_highlights"] > 0.02 or lum["mean"] > 0.85:
        warn("overexposed", f"{100 * metrics['clipped_highlights']:.1f}% of pixels are clipped to white")
    if metrics["crushed_shadows"] > 0.25 and lum["mean"] >= 0.02:
        warn("crushed_shadows", f"{100 * metrics['crushed_shadows']:.1f}% of pixels are crushed to black")
    if lum["mean"] < 0.02:
        pass  # a black frame is uniform too; one warning says it
    elif metrics["near_uniform"]:
        warn(
            "near_uniform",
            f"The frame is nearly uniform (luminance std {lum['std']:.3f}): the subject is missing or invisible",
        )
    elif metrics["empty"]:
        warn("empty_frame", "No region of the frame has visible detail")
    elif lum["std"] < 0.06:
        warn("low_contrast", f"Low contrast (luminance std {lum['std']:.3f})")
    return found


def measure_file(path, grid=8):
    result = measure(read_png(path), grid=grid)
    return {"file": Path(path).name, **result}
