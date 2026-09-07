# -*- coding: utf-8 -*-
"""
SANE 网络协议的序列化层（WireWriter / WireReader）。

忠实还原原 SANEWinDS classSANE.vb 的 Serialize / DeSerialize：
- 所有 word（32 位整数）以网络字节序（big-endian）在线上传输；
- 字符串为 `word 长度(含终止 null) + 字节 + null`；
- 字符按 Latin-1 逐字节编解码（对应 VB 的 Chr / Asc 语义）。
"""
from __future__ import annotations

import socket
import struct
from typing import List, Optional, Union

from .constants import SaneDataType


class WireWriter:
    """把 SANE 数据类型顺序写入字节缓冲区。"""

    def __init__(self) -> None:
        self._buf = bytearray()

    @property
    def buffer(self) -> bytearray:
        return self._buf

    def to_bytes(self) -> bytes:
        return bytes(self._buf)

    def write_word(self, value: int) -> None:
        self._buf.extend(struct.pack(">i", int(value)))

    def write_byte(self, value: int) -> None:
        self._buf.append(int(value) & 0xFF)

    def write_char(self, ch: str) -> None:
        self._buf.append(ord(ch) & 0xFF)

    def write_string(self, value: Optional[str]) -> None:
        if value is None:
            value = ""
        # 现代 saned 使用 UTF-8 传输字符串（VB 原版逐字节 Chr/Asc 会产生乱码，
        # 这是重构时修正的缺陷之一）
        encoded = value.encode("utf-8", errors="replace")
        self.write_word(len(encoded) + 1)  # +1 为终止 null
        self._buf.extend(encoded)
        self._buf.append(0)

    def write_boolean(self, value: bool) -> None:
        self.write_word(1 if value else 0)

    def write(self, data: object, data_type: SaneDataType) -> None:
        """通用写入口，对应 VB 的 Serialize(Object, Buffer, DataType)。"""
        if data_type == SaneDataType.SANE_Word:
            self.write_word(int(data))
        elif data_type == SaneDataType.SANE_Byte:
            self.write_byte(int(data))
        elif data_type == SaneDataType.SANE_Char:
            self.write_char(str(data))
        elif data_type == SaneDataType.SANE_String:
            self.write_string(str(data) if data is not None else None)
        elif data_type == SaneDataType.SANE_Boolean:
            self.write_boolean(bool(data))
        else:
            raise ValueError(f"Unimplemented Sane_DataType: {data_type}")


class WireReader:
    """从 socket 读取并解析 SANE 数据类型（带内部缓冲）。"""

    def __init__(self, sock: socket.socket, timeout_ms: int = 30000) -> None:
        self._sock = sock
        self._sock.settimeout(timeout_ms / 1000.0)
        self._buf = bytearray()
        self._pos = 0

    def _read_exact(self, n: int) -> bytes:
        """从缓冲 + socket 精确读取 n 字节，服务端提前断开则抛异常。"""
        if n < 0:
            raise ValueError("negative read length")
        try:
            while len(self._buf) - self._pos < n:
                chunk = self._sock.recv(65536)
                if not chunk:
                    raise ConnectionError("server sent incomplete data")
                self._buf.extend(chunk)
        except socket.timeout:
            raise ConnectionError("timeout waiting for server data")
        start = self._pos
        self._pos += n
        return bytes(self._buf[start:self._pos])

    def read_word(self) -> int:
        raw = self._read_exact(4)
        return struct.unpack(">i", raw)[0]

    def read_byte(self) -> int:
        raw = self._read_exact(1)
        return raw[0]

    def read_char(self) -> str:
        raw = self._read_exact(1)
        return chr(raw[0])

    def read_string(self) -> str:
        length = self.read_word()
        if length < 0:
            raise ValueError(f"invalid string length: {length}")
        raw = self._read_exact(length)
        value = raw.decode("utf-8", errors="replace")
        if value.endswith("\x00"):
            value = value[:-1]
        return value

    def read_boolean(self) -> bool:
        return self.read_word() != 0

    def read(self, data_type: SaneDataType) -> object:
        if data_type == SaneDataType.SANE_Word:
            return self.read_word()
        if data_type == SaneDataType.SANE_Byte:
            return self.read_byte()
        if data_type == SaneDataType.SANE_Char:
            return self.read_char()
        if data_type == SaneDataType.SANE_String:
            return self.read_string()
        if data_type == SaneDataType.SANE_Boolean:
            return self.read_boolean()
        raise ValueError(f"Unimplemented Sane_DataType: {data_type}")


def option_value_array_length(option_size: int, option_type: int) -> int:
    """对应 VB 的 OptionValueArrayLength。"""
    from .constants import SANEValueType
    try:
        vt = SANEValueType(option_type)
    except ValueError:
        return 0
    if vt in (SANEValueType.SANE_TYPE_BUTTON, SANEValueType.SANE_TYPE_GROUP):
        return 0
    if vt == SANEValueType.SANE_TYPE_STRING:
        return 1  # 原代码注释: 不支持字符串数组
    if option_size % 4 == 0:
        return option_size // 4
    return option_size // 4
