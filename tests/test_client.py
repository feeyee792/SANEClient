# -*- coding: utf-8 -*-
"""纯单元测试：图像编码（不依赖任何 SANE 服务器）。"""
from __future__ import annotations

import struct
import unittest

from sanewin.constants import SANEFrame
from sanewin.images import combine_frames, frame_to_bmp
from sanewin.models import SANEImageFrame, SANEParameters


class TestImageEncoding(unittest.TestCase):
    def test_bmp_gray8(self):
        w, h = 4, 2
        data = bytes(range(w * h))
        frame = SANEImageFrame(
            params=SANEParameters(format=int(SANEFrame.SANE_FRAME_GRAY), last_frame=True,
                                  bytes_per_line=w, pixels_per_line=w, lines=h, depth=8),
            data=data,
        )
        bmp = frame_to_bmp(frame)
        # 文件头
        self.assertEqual(bmp[:2], b"BM")
        self.assertEqual(struct.unpack("<i", bmp[18:22])[0], w)
        self.assertEqual(struct.unpack("<i", bmp[22:26])[0], h)
        self.assertEqual(struct.unpack("<H", bmp[28:30])[0], 8)  # bit count
        # 8-bit BMP: 文件头 14 + 信息头 40 + 调色板 1024
        pixel_offset = struct.unpack("<I", bmp[10:14])[0]
        self.assertEqual(pixel_offset, 54 + 1024)
        self.assertEqual(len(bmp), pixel_offset + 4 * 2)  # 4 字节/行，2 行
        pixel = bmp[pixel_offset:]
        # BMP 自下而上：底部行（y=1）在前
        self.assertEqual(pixel[:w], data[w:])
        self.assertEqual(pixel[w:w + w], data[:w])

    def test_bmp_gray8_unaligned_width(self):
        # 宽度 5：每行像素 5 字节，需对齐到 8 字节
        w, h = 5, 1
        data = bytes(range(w))
        frame = SANEImageFrame(
            params=SANEParameters(format=int(SANEFrame.SANE_FRAME_GRAY), last_frame=True,
                                  bytes_per_line=w, pixels_per_line=w, lines=h, depth=8),
            data=data,
        )
        bmp = frame_to_bmp(frame)
        pixel_offset = struct.unpack("<I", bmp[10:14])[0]
        self.assertEqual(len(bmp), pixel_offset + 8)  # 5 -> 对齐 8
        pixel = bmp[pixel_offset:pixel_offset + 5]
        self.assertEqual(pixel, data)

    def test_bmp_rgb24(self):
        w, h = 2, 1
        # 一行两个像素 R,G,B
        data = bytes([255, 0, 0, 0, 255, 0])
        frame = SANEImageFrame(
            params=SANEParameters(format=int(SANEFrame.SANE_FRAME_RGB), last_frame=True,
                                  bytes_per_line=6, pixels_per_line=w, lines=h, depth=8),
            data=data,
        )
        bmp = frame_to_bmp(frame)
        self.assertEqual(struct.unpack("<H", bmp[28:30])[0], 24)
        pixel_offset = struct.unpack("<I", bmp[10:14])[0]
        pixel = bmp[pixel_offset:pixel_offset + 8]  # 含行对齐填充
        # BGR 顺序：第一个像素应为 B=0,G=0,R=255
        self.assertEqual(pixel[0], 0)   # B
        self.assertEqual(pixel[1], 0)   # G
        self.assertEqual(pixel[2], 255)  # R
        # 第二个像素 B=255,G=0,R=0
        self.assertEqual(pixel[4], 255)
        self.assertEqual(pixel[5], 0)
        self.assertEqual(pixel[6], 0)

    def test_bmp_gray16_converts_to_8(self):
        # 16-bit 大端灰度 → 8-bit（取高字节）
        w, h = 2, 1
        data = bytes([0xAB, 0xCD, 0x12, 0x34])  # 大端样本
        frame = SANEImageFrame(
            params=SANEParameters(format=int(SANEFrame.SANE_FRAME_GRAY), last_frame=True,
                                  bytes_per_line=4, pixels_per_line=w, lines=h, depth=16),
            data=data,
        )
        bmp = frame_to_bmp(frame)
        self.assertEqual(struct.unpack("<H", bmp[28:30])[0], 8)
        pixel_offset = struct.unpack("<I", bmp[10:14])[0]
        pixel = bmp[pixel_offset:pixel_offset + w]
        self.assertEqual(pixel, bytes([0xAB, 0x12]))

    def test_unknown_lines_computed_from_stride(self):
        # 手扫仪：lines 未知（-1 或 0），按 stride 推算
        w, h = 3, 4
        data = bytes(range(w * h))
        frame = SANEImageFrame(
            params=SANEParameters(format=int(SANEFrame.SANE_FRAME_GRAY), last_frame=True,
                                  bytes_per_line=w, pixels_per_line=w, lines=0, depth=8),
            data=data,
        )
        bmp = frame_to_bmp(frame)
        self.assertEqual(struct.unpack("<i", bmp[22:26])[0], h)

    def test_combine_rgb_frames(self):
        def make(fmt, vals):
            return SANEImageFrame(
                params=SANEParameters(format=fmt, last_frame=False,
                                      bytes_per_line=2, pixels_per_line=2, lines=1, depth=8),
                data=bytes(vals),
            )

        red = make(SANEFrame.SANE_FRAME_RED, [10, 20])
        green = make(SANEFrame.SANE_FRAME_GREEN, [30, 40])
        blue = make(SANEFrame.SANE_FRAME_BLUE, [50, 60])
        combined = combine_frames([red, green, blue])
        self.assertEqual(combined.params.format, SANEFrame.SANE_FRAME_RGB)
        self.assertEqual(combined.params.bytes_per_line, 6)
        self.assertEqual(combined.data, bytes([10, 30, 50, 20, 40, 60]))

    def test_combine_missing_channel_raises(self):
        from sanewin.models import SANEImageFrame, SANEParameters
        def make(fmt, vals):
            return SANEImageFrame(
                params=SANEParameters(format=fmt, last_frame=False,
                                      bytes_per_line=2, pixels_per_line=2, lines=1, depth=8),
                data=bytes(vals),
            )
        with self.assertRaises(ValueError):
            combine_frames([make(SANEFrame.SANE_FRAME_RED, [10, 20]),
                            make(SANEFrame.SANE_FRAME_GREEN, [30, 40])])


if __name__ == "__main__":
    unittest.main()
