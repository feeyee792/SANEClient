# -*- coding: utf-8 -*-
"""
SANE 原始帧数据 → BMP 编码（零第三方依赖）。

对应原 SANEWinDS 在 modGlobals.vb 中的图像组装逻辑：
- 16-bit 深度数据按大端交换字节（对应 SwapImageBytes）；
- RGB 帧按 BMP 需要转为 BGR（对应 RGBtoBGR）；
- 分离的 R/G/B 三帧合并为 RGB（对应 CombineImageFrames）；
- lines 未知（手扫仪，lines=-1）时按 stride 推算行数。
"""
from __future__ import annotations

import struct
import zlib
from typing import List

from .constants import SANEFrame
from .models import SANEImageFrame, SANEParameters


def _align4(n: int) -> int:
    return (n + 3) & ~3


def _bmp_palette_gray8() -> bytes:
    """256 级灰度调色板（B,G,R,A 每项 4 字节）。"""
    out = bytearray()
    for i in range(256):
        out += bytes((i, i, i, 0))
    return bytes(out)


def _bmp_palette_gray1() -> bytes:
    """1-bit 灰度调色板：白(0)、黑(1)。"""
    return bytes((255, 255, 255, 0, 0, 0, 0, 0))


def _bmp_header(width: int, height: int, bit_count: int, palette_bytes: int,
                pixel_data: bytes, dpi: int = 0) -> bytes:
    row_size = _align4((width * bit_count) // 8)
    image_size = row_size * height
    palette_size = palette_bytes
    file_size = 14 + 40 + palette_size + image_size
    dpm = int(dpi * 1000.0 / 25.4) if dpi > 0 else 0

    header = struct.pack(
        "<2sIHHI",
        b"BM", file_size, 0, 0, 14 + 40 + palette_size,
    )
    info = struct.pack(
        "<IiiHHIIiiII",
        40, width, height, 1, bit_count, 0, image_size, dpm, dpm, 0, 0,
    )
    return header + info


def _pack_rows(data: bytes, width: int, height: int, stride: int, bytes_per_pixel: int,
               swap16: bool = False, rgb_to_bgr: bool = False) -> bytes:
    """把 SANE 原始行数据打包为 BMP 像素区（行 4 字节对齐，自下而上）。

    - swap16: 16-bit 数据按大端交换字节序
    - rgb_to_bgr: 将 R,G,B 通道顺序改为 B,G,R
    """
    row_bytes = (width * bytes_per_pixel) // (2 if swap16 else 1)
    if stride <= 0:
        stride = row_bytes
    if height <= 0 and stride > 0:
        height = len(data) // stride

    lines = []
    for r in range(height):
        offset = r * stride
        line = bytearray(data[offset:offset + row_bytes])
        if swap16:
            _swap_every_2(line)
        if rgb_to_bgr:
            _swap_rgb(line)
        # BMP 需要每行 4 字节对齐
        line += b"\x00" * (_align4(len(line)) - len(line))
        lines.append(bytes(line))
    # BMP 像素区自下而上存储
    lines.reverse()
    return b"".join(lines)


def _swap_every_2(buf: bytearray) -> None:
    for i in range(0, len(buf) - 1, 2):
        buf[i], buf[i + 1] = buf[i + 1], buf[i]


def _swap_rgb(buf: bytearray) -> None:
    for i in range(0, len(buf) - 2, 3):
        buf[i], buf[i + 2] = buf[i + 2], buf[i]


def combine_frames(frames: List[SANEImageFrame]) -> SANEImageFrame:
    """合并分离的 R/G/B 单色帧为 RGB 帧（对应 CombineImageFrames）。"""
    if not frames:
        raise ValueError("no frames to combine")
    if len(frames) == 1:
        return frames[0]

    channels: dict = {}
    for frame in frames:
        channels[frame.params.format] = frame.data

    missing = [f for f in (SANEFrame.SANE_FRAME_RED, SANEFrame.SANE_FRAME_GREEN, SANEFrame.SANE_FRAME_BLUE) if f not in channels]
    if missing:
        raise ValueError("one or more frames is missing from the image data")

    base = frames[0].params
    sample_bytes = 2 if base.depth == 16 else 1
    red, green, blue = channels[SANEFrame.SANE_FRAME_RED], channels[SANEFrame.SANE_FRAME_GREEN], channels[SANEFrame.SANE_FRAME_BLUE]
    sample_count = min(len(red), len(green), len(blue)) // sample_bytes

    out = bytearray()
    for i in range(sample_count):
        s = i * sample_bytes
        out += red[s:s + sample_bytes]
        out += green[s:s + sample_bytes]
        out += blue[s:s + sample_bytes]

    params = SANEParameters(
        format=int(SANEFrame.SANE_FRAME_RGB),
        last_frame=True,
        lines=base.lines,
        pixels_per_line=base.pixels_per_line,
        bytes_per_line=base.bytes_per_line * 3,
        depth=base.depth,
    )
    return SANEImageFrame(params=params, data=bytes(out))


def frame_to_bmp(frame: SANEImageFrame, dpi: int = 0, big_endian: bool = True) -> bytes:
    """把单个 SANE 图像帧编码为 BMP 文件字节。

    支持: gray 1/8/16-bit, RGB 8/16-bit。
    16-bit 灰度/彩色在 BMP 中无标准表示，转为 8-bit（取高字节）。
    big_endian 对应 SANE_NET_START 返回的字节序（0x4321=大端）。
    """
    params = frame.params
    fmt = params.format
    depth = params.depth
    width = params.pixels_per_line
    lines = params.lines
    stride = params.bytes_per_line
    data = frame.data

    if lines <= 0:
        if stride > 0:
            lines = len(data) // stride
        else:
            raise ValueError("cannot determine image height")

    # 16-bit 大端样本: [hi, lo]，取高字节；小端样本: [lo, hi]，取 index+1
    hi_idx = 0 if big_endian else 1

    if fmt == SANEFrame.SANE_FRAME_GRAY:
        if depth == 1:
            row_bytes = (width + 7) // 8
            pixel = _pack_rows(data, width, lines, stride, 1)
            # 1bpp：BMP 行以 4 字节对齐、自下而上
            palette = _bmp_palette_gray1()
            header = _bmp_header(width, lines, 1, len(palette), pixel, dpi)
            return header + palette + pixel
        if depth == 8:
            palette = _bmp_palette_gray8()
            pixel = _pack_rows(data, width, lines, stride, 1)
            header = _bmp_header(width, lines, 8, len(palette), pixel, dpi)
            return header + palette + pixel
        if depth == 16:
            # 16-bit 灰度 → 取高字节转 8-bit
            row_bytes = width * 2
            converted = bytearray()
            for r in range(lines):
                offset = r * stride
                line = data[offset:offset + row_bytes]
                converted.extend(line[i + hi_idx] for i in range(0, len(line) - 1, 2))
            palette = _bmp_palette_gray8()
            pixel = _pack_rows(bytes(converted), width, lines, width, 1)
            header = _bmp_header(width, lines, 8, len(palette), pixel, dpi)
            return header + palette + pixel
        raise ValueError(f"unsupported gray depth: {depth}")

    if fmt == SANEFrame.SANE_FRAME_RGB:
        if depth == 8:
            pixel = _pack_rows(data, width, lines, stride, 3, rgb_to_bgr=True)
            header = _bmp_header(width, lines, 24, 0, pixel, dpi)
            return header + pixel
        if depth == 16:
            # 48-bit RGB → 每通道取高字节转 24-bit，并转 BGR
            row_bytes = width * 6
            converted = bytearray()
            for r in range(lines):
                offset = r * stride
                line = data[offset:offset + row_bytes]
                for i in range(0, len(line) - 5, 6):
                    converted.append(line[i + hi_idx])    # R
                    converted.append(line[i + 2 + hi_idx])  # G
                    converted.append(line[i + 4 + hi_idx])  # B
            pixel = _pack_rows(bytes(converted), width, lines, width * 3, 3, rgb_to_bgr=True)
            header = _bmp_header(width, lines, 24, 0, pixel, dpi)
            return header + pixel
        raise ValueError(f"unsupported rgb depth: {depth}")

    if fmt in (SANEFrame.SANE_FRAME_RED, SANEFrame.SANE_FRAME_GREEN, SANEFrame.SANE_FRAME_BLUE):
        raise ValueError("single-band frames must be combined with combine_frames() first")

    raise ValueError(f"unsupported frame format: {fmt}")


def frames_to_bmp(frames: List[SANEImageFrame], dpi: int = 0, big_endian: bool = True) -> bytes:
    """多帧（多页/多通道）→ 单张 BMP。多页时只取第一页；多通道时合并。"""
    if not frames:
        raise ValueError("no frames")
    combined = combine_frames(frames)
    return frame_to_bmp(combined, dpi, big_endian)


# ---------------------------------------------------------------- PNG 编码

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _png_ihdr(width: int, height: int, bit_depth: int, color_type: int) -> bytes:
    return _png_chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0),
    )


def _png_idat(raw: bytes) -> bytes:
    return _png_chunk(b"IDAT", zlib.compress(raw, 6))


def _png_iend() -> bytes:
    return _png_chunk(b"IEND", b"")


def _png_scanlines(data: bytes, width: int, height: int, stride: int,
                   bytes_per_pixel: int, hi_idx: int = 0,
                   rgb_to_rgb: bool = False) -> bytes:
    """SANE 原始行数据 → PNG 扫描线（每行前置 filter 0）。"""
    row_bytes = width * bytes_per_pixel
    if stride <= 0:
        stride = row_bytes
    if height <= 0 and stride > 0:
        height = len(data) // stride
    out = bytearray()
    for r in range(height):
        offset = r * stride
        line = bytearray(data[offset:offset + row_bytes])
        if hi_idx == 1 and bytes_per_pixel == 2:
            # 小端 16-bit: 取低字节
            line = bytearray(line[i + 1] for i in range(0, len(line) - 1, 2))
            row_bytes = width * 1
            line = line[:row_bytes]
        out.append(0)  # filter type 0
        out.extend(line)
    return bytes(out)


def frame_to_png(frame: SANEImageFrame, big_endian: bool = True) -> bytes:
    """把单个 SANE 图像帧编码为 PNG（用于 GUI 预览）。

    支持 gray 1/8/16-bit 与 RGB 8/16-bit；16-bit 取高字节转 8-bit。
    """
    params = frame.params
    fmt = params.format
    depth = params.depth
    width = params.pixels_per_line
    lines = params.lines
    stride = params.bytes_per_line
    data = frame.data

    if lines <= 0:
        if stride > 0:
            lines = len(data) // stride
        else:
            raise ValueError("cannot determine image height")

    hi_idx = 0 if big_endian else 1

    if fmt == SANEFrame.SANE_FRAME_GRAY:
        if depth == 1:
            # 1-bit → 8-bit 灰度（白=0/黑=1），逐位展开
            row_bytes = (width + 7) // 8
            raw = bytearray()
            for r in range(lines):
                raw.append(0)  # filter 0
                offset = r * stride
                row = data[offset:offset + row_bytes]
                bits = "".join(f"{b:08b}" for b in row)[:width]
                raw.extend(255 if ch == "1" else 0 for ch in bits)
            return (
                _PNG_SIGNATURE
                + _png_ihdr(width, lines, 8, 0)
                + _png_idat(bytes(raw))
                + _png_iend()
            )
        if depth == 8:
            raw = _png_scanlines(data, width, lines, stride, 1)
            return _PNG_SIGNATURE + _png_ihdr(width, lines, 8, 0) + _png_idat(raw) + _png_iend()
        if depth == 16:
            row_bytes = width * 2
            converted = bytearray()
            for r in range(lines):
                offset = r * stride
                line = data[offset:offset + row_bytes]
                converted.extend(line[i + hi_idx] for i in range(0, len(line) - 1, 2))
            raw = _png_scanlines(bytes(converted), width, lines, width, 1)
            return _PNG_SIGNATURE + _png_ihdr(width, lines, 8, 0) + _png_idat(raw) + _png_iend()
        raise ValueError(f"unsupported gray depth: {depth}")

    if fmt == SANEFrame.SANE_FRAME_RGB:
        if depth == 8:
            raw = _png_scanlines(data, width, lines, stride, 3)
            return _PNG_SIGNATURE + _png_ihdr(width, lines, 8, 2) + _png_idat(raw) + _png_iend()
        if depth == 16:
            row_bytes = width * 6
            converted = bytearray()
            for r in range(lines):
                offset = r * stride
                line = data[offset:offset + row_bytes]
                for i in range(0, len(line) - 5, 6):
                    converted.append(line[i + hi_idx])
                    converted.append(line[i + 2 + hi_idx])
                    converted.append(line[i + 4 + hi_idx])
            raw = _png_scanlines(bytes(converted), width, lines, width * 3, 3)
            return _PNG_SIGNATURE + _png_ihdr(width, lines, 8, 2) + _png_idat(raw) + _png_iend()
        raise ValueError(f"unsupported rgb depth: {depth}")

    if fmt in (SANEFrame.SANE_FRAME_RED, SANEFrame.SANE_FRAME_GREEN, SANEFrame.SANE_FRAME_BLUE):
        raise ValueError("single-band frames must be combined with combine_frames() first")

    raise ValueError(f"unsupported frame format: {fmt}")


# ---------------------------------------------------------------- PDF 编码

def _frame_to_8bit(frame: SANEImageFrame, big_endian: bool = True) -> tuple:
    """帧 → (color_mode, width, height, pixels)：归一化到 8-bit 原始像素。

    color_mode: 'L'（DeviceGray 每像素 1 字节）或 'RGB'（每像素 3 字节）。
    支持 gray 1/8/16-bit 与 RGB 8/16-bit；1-bit 展开为 0/255，16-bit 取高字节。
    """
    params = frame.params
    fmt, depth = params.format, params.depth
    width = params.pixels_per_line
    lines = params.lines
    stride = params.bytes_per_line
    data = frame.data

    if lines <= 0:
        if stride > 0:
            lines = len(data) // stride
        else:
            raise ValueError("cannot determine image height")

    hi_idx = 0 if big_endian else 1

    if fmt == SANEFrame.SANE_FRAME_GRAY:
        if depth == 1:
            row_bytes = (width + 7) // 8
            out = bytearray()
            for r in range(lines):
                offset = r * stride
                row = data[offset:offset + row_bytes]
                bits = "".join(f"{b:08b}" for b in row)[:width]
                out.extend(255 if ch == "1" else 0 for ch in bits)
            return "L", width, lines, bytes(out)
        if depth == 8:
            out = bytearray()
            for r in range(lines):
                out.extend(data[r * stride:r * stride + width])
            return "L", width, lines, bytes(out)
        if depth == 16:
            row_bytes = width * 2
            out = bytearray()
            for r in range(lines):
                offset = r * stride
                line = data[offset:offset + row_bytes]
                out.extend(line[i + hi_idx] for i in range(0, len(line) - 1, 2))
            return "L", width, lines, bytes(out)
        raise ValueError(f"unsupported gray depth: {depth}")

    if fmt == SANEFrame.SANE_FRAME_RGB:
        if depth == 8:
            out = bytearray()
            for r in range(lines):
                out.extend(data[r * stride:r * stride + width * 3])
            return "RGB", width, lines, bytes(out)
        if depth == 16:
            row_bytes = width * 6
            out = bytearray()
            for r in range(lines):
                offset = r * stride
                line = data[offset:offset + row_bytes]
                for i in range(0, len(line) - 5, 6):
                    out.append(line[i + hi_idx])      # R
                    out.append(line[i + 2 + hi_idx])  # G
                    out.append(line[i + 4 + hi_idx])  # B
            return "RGB", width, lines, bytes(out)
        raise ValueError(f"unsupported rgb depth: {depth}")

    if fmt in (SANEFrame.SANE_FRAME_RED, SANEFrame.SANE_FRAME_GREEN, SANEFrame.SANE_FRAME_BLUE):
        raise ValueError("single-band frames must be combined with combine_frames() first")

    raise ValueError(f"unsupported frame format: {fmt}")


def frames_to_pdf(frames: List[SANEImageFrame], dpi: int = 300,
                  big_endian: bool = True) -> bytes:
    """把一页或多页 SANE 帧编码为 PDF 文件字节（零第三方依赖，PDF 1.4）。

    - 每帧一页；分离的 R/G/B 帧自动合并为一页 RGB
    - 图像以 FlateDecode（zlib）压缩存储，灰度用 DeviceGray、彩色用 DeviceRGB
    - 页面尺寸按 dpi 换算（1 英寸 = 72pt），默认 300dpi
    """
    if not frames:
        raise ValueError("no frames")

    fmts = {f.params.format for f in frames}
    if {SANEFrame.SANE_FRAME_RED, SANEFrame.SANE_FRAME_GREEN, SANEFrame.SANE_FRAME_BLUE} <= fmts:
        frames = [combine_frames(frames)]

    pages = []
    for fr in frames:
        mode, w, h, px = _frame_to_8bit(fr, big_endian)
        pages.append((mode, w, h, zlib.compress(px, 6)))

    n_pages = len(pages)
    total_objs = 2 + n_pages * 3  # Catalog + Pages + 每页(Page, XObject, Contents)

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (total_objs + 1)

    def obj(num: int, body) -> None:
        nonlocal out
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode()
        out += body if isinstance(body, bytes) else body.encode()
        out += b"\nendobj\n"

    obj(1, "<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(str(3 + 3 * i) + " 0 R" for i in range(n_pages))
    obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")

    for i, (mode, w, h, pdata) in enumerate(pages):
        base = 3 + 3 * i
        pw, ph = w * 72.0 / dpi, h * 72.0 / dpi
        cs = "/DeviceGray" if mode == "L" else "/DeviceRGB"
        obj(base, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.2f} {ph:.2f}] "
                   f"/Resources << /XObject << /Im0 {base + 1} 0 R >> >> "
                   f"/Contents {base + 2} 0 R >>"))
        # 图像 XObject：dict + stream + 二进制数据 + endstream（不用 obj，避免提前 endobj）
        offsets[base + 1] = len(out)
        out += (f"{base + 1} 0 obj\n<< /Type /XObject /Subtype /Image "
                f"/Width {w} /Height {h} /ColorSpace {cs} /BitsPerComponent 8 "
                f"/Filter /FlateDecode /Length {len(pdata)} >>\nstream\n").encode()
        out += pdata
        out += b"\nendstream\nendobj\n"
        contents = f"q\n{pw:.2f} 0 0 {ph:.2f} 0 0 cm\n/Im0 Do\nQ"
        obj(base + 2, f"<< /Length {len(contents)} >>\nstream\n{contents}\nendstream")

    xref_pos = len(out)
    out += f"xref\n0 {total_objs + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {total_objs + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)
