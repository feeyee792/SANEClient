# -*- coding: utf-8 -*-
"""PDF 编码器结构验证：合成帧 → frames_to_pdf → 校验 PDF 结构与像素完整。

用法: python tests/test_pdf.py
"""
from __future__ import annotations

import re
import sys
import zlib

sys.path.insert(0, ".")

from sanewin.constants import SANEFrame  # noqa: E402
from sanewin.images import frames_to_pdf  # noqa: E402
from sanewin.models import SANEImageFrame, SANEParameters  # noqa: E402


def make_frame(fmt: int, depth: int, w: int, h: int, fill: int) -> SANEImageFrame:
    bpp = 2 if depth == 16 else 1
    channels = 3 if fmt == SANEFrame.SANE_FRAME_RGB else 1
    stride = w * channels * bpp
    data = bytes([fill & 0xFF]) * (stride * h)
    return SANEImageFrame(
        params=SANEParameters(
            format=fmt, last_frame=True, lines=h,
            pixels_per_line=w, bytes_per_line=stride, depth=depth,
        ),
        data=data,
    )


def validate(pdf: bytes, expect_pages: int, expect_pixel_bytes: list) -> None:
    assert pdf.startswith(b"%PDF-1.4"), "PDF 头错误"
    assert pdf.rstrip().endswith(b"%%EOF"), "缺少 EOF"
    # 页数
    m = re.search(rb"/Count (\d+)", pdf)
    assert m and int(m.group(1)) == expect_pages, f"页数错误: {m.group(1) if m else None}"
    # 图像流数量
    streams = re.findall(rb"/Filter /FlateDecode /Length (\d+) >>\nstream\n", pdf)
    assert len(streams) == expect_pages, f"图像流数量错误: {len(streams)}"
    for length in streams:
        assert int(length) > 0, "压缩长度应为正"
    # 解压每个图像流并核对解压后长度
    body = pdf.split(b"startxref")[0]
    dec = []
    for m2 in re.finditer(rb"stream\n(.*?)\nendstream", body, re.S):
        try:
            dec.append(zlib.decompress(m2.group(1)))
        except zlib.error:
            pass
    for i, expect in enumerate(expect_pixel_bytes):
        assert any(len(d) == expect for d in dec), f"第 {i} 页像素解压长度不匹配"
    print(f"PDF 校验 OK: {expect_pages} 页, 解压像素长度 {[len(d) for d in dec]}")


# gray 8-bit 单页
g8 = make_frame(SANEFrame.SANE_FRAME_GRAY, 8, 10, 8, 128)
validate(frames_to_pdf([g8], dpi=300), 1, [10 * 8 * 1])

# RGB 8-bit 单页
rgb = make_frame(SANEFrame.SANE_FRAME_RGB, 8, 6, 4, 255)
validate(frames_to_pdf([rgb], dpi=300), 1, [6 * 4 * 3])

# 两页 gray（连续扫描场景）
validate(frames_to_pdf([g8, g8], dpi=150), 2, [10 * 8, 10 * 8])

# gray 16-bit 大端（取高字节）与 1-bit
g16 = make_frame(SANEFrame.SANE_FRAME_GRAY, 16, 5, 3, 0x12)
validate(frames_to_pdf([g16], dpi=300, big_endian=True), 1, [5 * 3])
g1 = make_frame(SANEFrame.SANE_FRAME_GRAY, 1, 9, 4, 0xFF)
validate(frames_to_pdf([g1], dpi=300), 1, [9 * 4])

# RGB 16-bit
rgb16 = make_frame(SANEFrame.SANE_FRAME_RGB, 16, 4, 3, 0xAB)
validate(frames_to_pdf([rgb16], dpi=300, big_endian=True), 1, [4 * 3 * 3])

# 分离 R/G/B 三帧合并
def band(fmt, w, h):
    stride = w
    return SANEImageFrame(
        params=SANEParameters(format=fmt, last_frame=False, lines=h,
                              pixels_per_line=w, bytes_per_line=stride, depth=8),
        data=bytes([128]) * (stride * h),
    )
sep = [band(SANEFrame.SANE_FRAME_RED, 6, 4),
       band(SANEFrame.SANE_FRAME_GREEN, 6, 4),
       band(SANEFrame.SANE_FRAME_BLUE, 6, 4)]
validate(frames_to_pdf(sep, dpi=300), 1, [6 * 4 * 3])

print("PDF 全部结构验证通过")
