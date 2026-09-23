import random
import struct
import time
import zlib
from pathlib import Path

import pytest

from blender_quality.image_metrics import PngError, decode_png, measure, measure_file

ROOT = Path(__file__).parent.parent
RENDERS = Path(__file__).parent / "fixtures" / "renders"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def reference_filter(kind, row, previous, bpp):
    """Straightforward per-byte PNG filter (the encoder side), independent of the decoder."""
    out = bytearray()
    for i, value in enumerate(row):
        a = row[i - bpp] if i >= bpp else 0
        b = previous[i]
        c = previous[i - bpp] if i >= bpp else 0
        if kind == 0:
            predictor = 0
        elif kind == 1:
            predictor = a
        elif kind == 2:
            predictor = b
        elif kind == 3:
            predictor = (a + b) // 2
        else:
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            predictor = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
        out.append((value - predictor) & 255)
    return bytes(out)


def encode_png(rows, color_type, depth, filters=(0, 1, 2, 3, 4), palette=None, trns=None, interlace=0):
    """rows: list of rows, each a flat list of samples."""
    height = len(rows)
    width = len(rows[0]) // CHANNELS[color_type]
    bpp = CHANNELS[color_type] * depth // 8
    raw = [struct.pack(f">{len(r)}{'H' if depth == 16 else 'B'}", *r) for r in rows]
    stream, previous = bytearray(), bytes(len(raw[0]))
    for y, row in enumerate(raw):
        kind = filters[y % len(filters)]
        stream += bytes([kind]) + reference_filter(kind, row, previous, bpp)
        previous = row
    data = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color_type, 0, 0, interlace)
    )
    if palette:
        data += chunk(b"PLTE", bytes(v for entry in palette for v in entry))
    if trns:
        data += chunk(b"tRNS", bytes(trns))
    return data + chunk(b"IDAT", zlib.compress(bytes(stream))) + chunk(b"IEND", b""), raw


@pytest.mark.parametrize(
    ("color_type", "depth"), [(0, 8), (0, 16), (4, 8), (4, 16), (2, 8), (2, 16), (6, 8), (6, 16), (3, 8)]
)
def test_every_filter_decodes_exactly(color_type, depth):
    rng = random.Random(color_type * 100 + depth)
    maximum = 15 if color_type == 3 else (1 << depth) - 1
    width, height = 13, 11
    rows = [[rng.randint(0, maximum) for _ in range(width * CHANNELS[color_type])] for _ in range(height)]
    palette = [(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(16)]
    data, raw = encode_png(rows, color_type, depth, palette=palette if color_type == 3 else None)
    image = decode_png(data)
    assert (image.width, image.height, image.channels) == (width, height, CHANNELS[color_type])
    assert image.rows == raw


def test_luminance_statistics_are_exact():
    # Left half black, right half white: mean 0.5, std 0.5, half clipped, half crushed.
    rows = [[0] * 30 + [255] * 30 for _ in range(4)]
    stats = measure(decode_png(encode_png([r for r in rows], 0, 8)[0]))
    assert stats["luminance"]["mean"] == 0.5 and stats["luminance"]["std"] == 0.5
    assert stats["clipped_highlights"] == 0.5 and stats["crushed_shadows"] == 0.5
    assert stats["luminance"]["p2"] == 0.0 and stats["luminance"]["p98"] == 1.0


def test_rec709_weights_on_rgb():
    red, green, blue = [255, 0, 0], [0, 255, 0], [0, 0, 255]
    for pixel, expected in ((red, 0.2126), (green, 0.7152), (blue, 0.0722)):
        stats = measure(decode_png(encode_png([pixel * 4] * 4, 2, 8)[0]))
        assert stats["luminance"]["mean"] == pytest.approx(expected, abs=1e-4)


def test_sixteen_bit_precision():
    stats = measure(decode_png(encode_png([[32768] * 8] * 8, 0, 16)[0]))
    assert stats["luminance"]["mean"] == pytest.approx(32768 / 65535, abs=1e-4)


def test_transparent_pixels_are_excluded():
    # RGBA: left half transparent red (ignored), right half opaque mid grey.
    row = [255, 0, 0, 0] * 4 + [128, 128, 128, 255] * 4
    stats = measure(decode_png(encode_png([row] * 4, 6, 8)[0]))
    assert stats["transparent"] == 0.5
    assert stats["luminance"]["mean"] == pytest.approx(128 / 255, abs=1e-4)
    palette = [(0, 0, 0), (255, 255, 255)]
    stats = measure(decode_png(encode_png([[0, 1] * 4] * 2, 3, 8, palette=palette, trns=[0])[0]))
    assert stats["transparent"] == 0.5 and stats["luminance"]["mean"] == 1.0


def test_layout_grid_finds_the_detail():
    # A checkerboard patch in the top-left quadrant of a flat grey image.
    rows = []
    for y in range(64):
        rows.append([(255 if (x // 2 + y // 2) % 2 else 0) if x < 24 and y < 24 else 120 for x in range(64)])
    stats = measure(decode_png(encode_png(rows, 0, 8)[0]))
    x, y = stats["detail_center"]
    assert x < 0.4 and y < 0.4  # image coordinates: y grows downward
    assert len(stats["ascii"]) == 24 and all(len(line) == 48 for line in stats["ascii"])
    assert stats["grid"]["detail"][0][0] > stats["grid"]["detail"][7][7]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: b"GIF89a" + d[6:], "not a PNG"),
        (lambda d: d[:40], "truncated"),
        (lambda d: d[:30] + bytes([d[30] ^ 1]) + d[31:], "CRC mismatch"),
    ],
)
def test_broken_files_are_rejected(mutate, message):
    data, _ = encode_png([[1, 2, 3] * 3] * 3, 2, 8)
    with pytest.raises(PngError, match=message):
        decode_png(mutate(data))


def test_unsupported_formats_are_rejected_clearly():
    data, _ = encode_png([[0] * 4] * 4, 0, 8, interlace=1)
    with pytest.raises(PngError, match="interlaced"):
        decode_png(data)
    header = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 4, 0, 0, 0, 0))
    with pytest.raises(PngError, match="4-bit gray PNGs are not supported"):
        decode_png(header + chunk(b"IEND", b""))


def test_black_and_uniform_renders_are_flagged():
    """Previews rendered by Blender 5.2 from the sabotaged scenes (tests/fixtures/renders)."""
    black = measure_file(RENDERS / "abstract-no_lights_unused_emission-preview.png")
    assert [w["id"] for w in black["warnings"]] == ["black_frame"]
    uniform = measure_file(RENDERS / "abstract-hidden_collection-preview.png")
    assert "near_uniform" in [w["id"] for w in uniform["warnings"]]
    good = measure_file(RENDERS / "abstract-preview.png")
    assert good["warnings"] == [] and not good["empty"]


def test_full_render_matches_blender_numpy_and_is_fast():
    # Reference values computed inside Blender 5.2 with numpy on the same file:
    # mean=0.2971 std=0.1943 p2=0.046 p50=0.327 p98=0.621
    started = time.perf_counter()
    stats = measure_file(ROOT / "docs" / "abstract.png")
    elapsed = time.perf_counter() - started
    lum = stats["luminance"]
    assert (stats["width"], stats["height"]) == (960, 720)
    assert lum["mean"] == pytest.approx(0.2971, abs=0.001)
    assert lum["std"] == pytest.approx(0.1943, abs=0.001)
    assert lum["p50"] == pytest.approx(0.327, abs=0.002)
    assert lum["p98"] == pytest.approx(0.621, abs=0.002)
    assert elapsed < 5
