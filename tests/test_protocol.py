# -*- coding: utf-8 -*-
"""协议序列化层的往返测试。"""
from __future__ import annotations

import socket
import struct
import threading
import unittest

from sanewin.constants import (
    SaneDataType,
    sane_fix,
    sane_unfix,
    sane_version_code,
    sane_version_major,
    sane_version_minor,
    sane_version_build,
)
from sanewin.protocol import WireReader, WireWriter, option_value_array_length


class _PipePair:
    """内存 socket 对，用于测试 WireReader。"""

    def __init__(self) -> None:
        self._a, self._b = socket.socketpair()
        self.server = self._a
        self.client = self._b

    def feed(self, data: bytes) -> None:
        self.server.sendall(data)

    def close(self) -> None:
        self._a.close()
        self._b.close()


class TestWireWriterReader(unittest.TestCase):
    def setUp(self) -> None:
        self.pair = _PipePair()

    def tearDown(self) -> None:
        self.pair.close()

    def _roundtrip(self, values, data_types):
        writer = WireWriter()
        for v, t in zip(values, data_types):
            writer.write(v, t)
        self.pair.feed(writer.to_bytes())
        reader = WireReader(self.pair.client, 5000)
        return [reader.read(t) for t in data_types]

    def test_word_roundtrip(self):
        for v in (0, 1, -1, 0x7FFFFFFF, -0x80000000, 300, 0x12345678):
            out = self._roundtrip([v], [SaneDataType.SANE_Word])[0]
            self.assertEqual(out, v)

    def test_word_network_order(self):
        writer = WireWriter()
        writer.write_word(0x01020304)
        self.assertEqual(writer.to_bytes(), b"\x01\x02\x03\x04")

    def test_string_roundtrip(self):
        for s in ("", "Gray", "test:0", "with, comma", "中文", "null\x00inside"):
            out = self._roundtrip([s], [SaneDataType.SANE_String])[0]
            self.assertEqual(out, s)

    def test_string_wire_format(self):
        writer = WireWriter()
        writer.write_string("AB")
        # 长度 3（含 null），然后 'A' 'B' 0
        self.assertEqual(writer.to_bytes(), struct.pack(">i", 3) + b"AB\x00")

    def test_boolean_roundtrip(self):
        for b in (True, False):
            out = self._roundtrip([b], [SaneDataType.SANE_Boolean])[0]
            self.assertEqual(out, b)

    def test_byte_char_roundtrip(self):
        out = self._roundtrip([0x7F, "X"], [SaneDataType.SANE_Byte, SaneDataType.SANE_Char])
        self.assertEqual(out, [0x7F, "X"])

    def test_composite_roundtrip(self):
        values = [42, "mode", True, 0x4321, ""]
        types = [SaneDataType.SANE_Word, SaneDataType.SANE_String,
                 SaneDataType.SANE_Boolean, SaneDataType.SANE_Word, SaneDataType.SANE_String]
        self.assertEqual(self._roundtrip(values, types), values)

    def test_incomplete_data_raises(self):
        self.pair.feed(b"\x00\x01")
        self.pair.server.close()  # 对端关闭 → recv 返回空 → ConnectionError
        reader = WireReader(self.pair.client, 5000)
        with self.assertRaises(ConnectionError):
            reader.read_word()


class TestFixedPoint(unittest.TestCase):
    def test_fix_unfix(self):
        for v in (0.0, 1.0, -1.0, 0.5, 3.14159, 215.9, 0.0001):
            fixed = sane_fix(v)
            back = sane_unfix(fixed)
            self.assertAlmostEqual(back, round(v, 4), places=3)

    def test_fix_clamps(self):
        self.assertEqual(sane_fix(1e12), 0x7FFFFFFF)
        self.assertEqual(sane_fix(-1e12), -0x80000000)


class TestVersionCode(unittest.TestCase):
    def test_version(self):
        code = sane_version_code(1, 0, 3)
        self.assertEqual((sane_version_major(code), sane_version_minor(code), sane_version_build(code)), (1, 0, 3))

    def test_matches_constant(self):
        from sanewin.constants import VERSION_CODE
        self.assertEqual(VERSION_CODE, sane_version_code(1, 0, 3))


class TestOptionValueArrayLength(unittest.TestCase):
    def test_lengths(self):
        from sanewin.constants import SANEValueType
        self.assertEqual(option_value_array_length(4, int(SANEValueType.SANE_TYPE_INT)), 1)
        self.assertEqual(option_value_array_length(8, int(SANEValueType.SANE_TYPE_FIXED)), 2)
        self.assertEqual(option_value_array_length(16, int(SANEValueType.SANE_TYPE_BOOL)), 4)
        self.assertEqual(option_value_array_length(16, int(SANEValueType.SANE_TYPE_STRING)), 1)
        self.assertEqual(option_value_array_length(4, int(SANEValueType.SANE_TYPE_BUTTON)), 0)
        self.assertEqual(option_value_array_length(0, int(SANEValueType.SANE_TYPE_GROUP)), 0)


if __name__ == "__main__":
    unittest.main()
