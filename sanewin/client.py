# -*- coding: utf-8 -*-
"""
SANE 网络协议客户端。

对应原 SANEWinDS 项目 classSANE.vb 的完整功能：所有 RPC 过程
(Init / GetDevices / Open / Close / Cancel / GetOptionDescriptors /
ControlOption / GetParameters / Start / Authorize / Exit) 与图像帧采集。

与 VB 原版的行为差异（重构时修正的原缺陷）：
1. GetDevices / GetOptionDescriptors 中数组按协议规范精确解析，
   不再依赖“最后一条记录必为空”的约定（原 VB 代码按上界-1 重定义数组，
   若服务端最后一条非空会越界崩溃）；
2. STRING_LIST 约束按 saned 实际语义读取 count 个字符串，不再多读一次；
3. 字符串编解码统一为 Latin-1（对应 VB 的 Chr/Asc 逐字节语义）。
"""
from __future__ import annotations

import hashlib
import locale
import logging
import socket
import struct
from typing import Callable, List, Optional, Tuple

from .constants import (
    SANENetByteOrder,
    SANENetProcedureNumber,
    SANEStatus,
    SANEValueType,
    SANEConstraintType,
    SANEFrame,
    SaneDataType,
    SANE_TRUE,
    VERSION_CODE,
    sane_fix,
    sane_unfix,
    sane_version_major,
    sane_version_minor,
    sane_version_build,
)
from .models import (
    SANEControlOptionReply,
    SANEControlOptionRequest,
    SANEConstraint,
    SANEDevice,
    SANEImageFrame,
    SANEOptionDescriptor,
    SANEParameters,
    SANERange,
)
from .protocol import WireReader, WireWriter, option_value_array_length

logger = logging.getLogger("sanewin.client")

DEFAULT_TCP_TIMEOUT_MS = 30000
DEFAULT_IMAGE_TIMEOUT_S = 120
DEFAULT_IMAGE_PORT_TIMEOUT_MS = 5000  # 图像数据端口读取超时下限


class SaneError(Exception):
    """SANE 操作失败（携带状态码）。"""

    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message or f"SANE status {status}")
        self.status = status


class EmptyFrameException(Exception):
    """服务端返回了空图像帧（对应 VB 的 EmptyFrameException）。"""


class ServerDisconnectedException(Exception):
    """服务端在传输中断开连接。"""


class SaneClient:
    """SANEWinDS 的 SANE 网络客户端。

    典型用法::

        client = SaneClient(host, port, username, password, tcp_timeout_ms)
        client.init()
        devices = client.get_devices()
        client.open(devices[0].name)
        descriptors = client.get_option_descriptors()
        client.control_option(option_index, action=SANE_ACTION_SET_VALUE, values=[...])
        port, byte_order = client.start()
        frame = client.acquire_frame(port, byte_order)
        client.close()
    """

    def __init__(
        self,
        host: str,
        port: int = 6566,
        username: str = "",
        password: str = "",
        tcp_timeout_ms: int = DEFAULT_TCP_TIMEOUT_MS,
        image_timeout_s: int = DEFAULT_IMAGE_TIMEOUT_S,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username or ""
        self.password = password or ""
        self.tcp_timeout_ms = max(tcp_timeout_ms, 5000)
        self.image_timeout_s = image_timeout_s
        self._control: Optional[socket.socket] = None
        self._reader: Optional[WireReader] = None
        self.handle: int = -1
        self.version_code: int = VERSION_CODE
        self.server_version_code: int = 0
        self._progress_callback: Optional[Callable[[int], None]] = None

    # ------------------------------------------------------------ 连接管理

    def connect(self) -> None:
        """建立控制连接（不执行 SANE 协议）。"""
        if self._control is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=self.tcp_timeout_ms / 1000.0)
        self._control = sock
        self._reader = WireReader(sock, self.tcp_timeout_ms)

    @property
    def connected(self) -> bool:
        return self._control is not None

    def _require_connection(self) -> socket.socket:
        if self._control is None:
            # 连接层语义错误：统一为 ConnectionError，便于调用方与网络中断一并处理
            raise ConnectionError("not connected")
        return self._control

    def _send(self, writer: WireWriter) -> None:
        self._require_connection().sendall(writer.to_bytes())

    def _request(self, rpc: SANENetProcedureNumber, *items: Tuple[object, SaneDataType]) -> WireReader:
        """发送 RPC 请求并返回用于读取回复的 reader。"""
        writer = WireWriter()
        writer.write_word(int(rpc))
        for value, data_type in items:
            writer.write(value, data_type)
        self._send(writer)
        if self._reader is None:
            raise SaneError(SANEStatus.SANE_STATUS_IO_ERROR, "reader is None")
        return self._reader

    def _set_progress_callback(self, callback: Optional[Callable[[int], None]]) -> None:
        self._progress_callback = callback

    def _emit_progress(self, percent: int) -> None:
        if self._progress_callback is not None:
            self._progress_callback(percent)

    # ------------------------------------------------------------ RPC: INIT

    def init(self, username: Optional[str] = None) -> int:
        """SANE_NET_INIT：返回服务端状态码。"""
        self.connect()
        user = self.username if username is None else username
        reader = self._request(
            SANENetProcedureNumber.SANE_NET_INIT,
            (self.version_code, SaneDataType.SANE_Word),
            (user, SaneDataType.SANE_String),
        )
        status = reader.read_word()
        self.server_version_code = reader.read_word()
        logger.info(
            "client version = %d.%d.%d, server version = %d.%d.%d",
            sane_version_major(self.version_code),
            sane_version_minor(self.version_code),
            sane_version_build(self.version_code),
            sane_version_major(self.server_version_code),
            sane_version_minor(self.server_version_code),
            sane_version_build(self.server_version_code),
        )
        if self.server_version_code != self.version_code:
            logger.warning("version mismatch with server")
        return status

    # ------------------------------------------------------------ RPC: GET_DEVICES

    def get_devices(self) -> List[SANEDevice]:
        """SANE_NET_GET_DEVICES：返回设备列表。"""
        reader = self._request(SANENetProcedureNumber.SANE_NET_GET_DEVICES)
        status = reader.read_word()
        if status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(status)
        array_len = reader.read_word()
        if array_len < 0:
            raise SaneError(SANEStatus.SANE_STATUS_IO_ERROR, f"invalid device array length {array_len}")
        devices: List[SANEDevice] = []
        for _ in range(array_len):
            empty = reader.read_boolean()
            if empty:
                break
            device = SANEDevice(
                name=reader.read_string(),
                vendor=reader.read_string(),
                model=reader.read_string(),
                type=reader.read_string(),
            )
            devices.append(device)
        return devices

    # ------------------------------------------------------------ RPC: OPEN

    def open(self, device_name: str) -> int:
        """SANE_NET_OPEN：打开设备，返回状态码。"""
        reader = self._request(
            SANENetProcedureNumber.SANE_NET_OPEN,
            (device_name, SaneDataType.SANE_String),
        )
        status = reader.read_word()
        self.handle = reader.read_word()
        resource = reader.read_string()
        if resource:
            self._authorize(reader, resource)
            status = reader.read_word()
            self.handle = reader.read_word()
            resource = reader.read_string()
        logger.debug("opened device '%s', handle=%d, status=%d", device_name, self.handle, status)
        return status

    def close(self) -> None:
        """SANE_NET_CLOSE：关闭设备。"""
        if self.handle < 0:
            return
        try:
            reader = self._request(
                SANENetProcedureNumber.SANE_NET_CLOSE,
                (self.handle, SaneDataType.SANE_Word),
            )
            reader.read_word()  # dummy
        except (ConnectionError, OSError):
            pass
        finally:
            self.handle = -1

    def cancel(self) -> None:
        """SANE_NET_CANCEL：取消当前操作。"""
        if self.handle < 0:
            return
        reader = self._request(
            SANENetProcedureNumber.SANE_NET_CANCEL,
            (self.handle, SaneDataType.SANE_Word),
        )
        reader.read_word()  # dummy

    def exit(self) -> None:
        """SANE_NET_EXIT：通知服务端退出并关闭控制连接。"""
        if self._control is None:
            return
        try:
            writer = WireWriter()
            writer.write_word(int(SANENetProcedureNumber.SANE_NET_EXIT))
            self._control.sendall(writer.to_bytes())
        except OSError:
            pass
        finally:
            self.disconnect()

    def disconnect(self) -> None:
        """关闭控制连接。"""
        if self._control is not None:
            try:
                self._control.close()
            except OSError:
                pass
            self._control = None
            self._reader = None

    # ------------------------------------------------------------ RPC: GET_OPTION_DESCRIPTORS

    def get_option_descriptors(self) -> List[SANEOptionDescriptor]:
        """SANE_NET_GET_OPTION_DESCRIPTORS：返回全部选项描述符。"""
        reader = self._request(
            SANENetProcedureNumber.SANE_NET_GET_OPTION_DESCRIPTORS,
            (self.handle, SaneDataType.SANE_Word),
        )
        array_len = reader.read_word()
        if array_len < 0:
            raise SaneError(SANEStatus.SANE_STATUS_IO_ERROR, f"invalid descriptor array length {array_len}")
        descriptors: List[SANEOptionDescriptor] = []
        for _ in range(array_len):
            empty = reader.read_boolean()
            if empty:
                break
            desc = SANEOptionDescriptor()
            desc.name = reader.read_string()
            desc.title = reader.read_string()
            desc.desc = reader.read_string()
            desc.type = SANEValueType(reader.read_word())
            desc.unit = reader.read_word()
            desc.size = reader.read_word()
            desc.cap = reader.read_word()
            ctype = reader.read_word()
            constraint = SANEConstraint()
            constraint.constraint_type = SANEConstraintType(ctype)
            if constraint.constraint_type == SANEConstraintType.SANE_CONSTRAINT_STRING_LIST:
                count = reader.read_word()
                # saned 的计数包含终止空字符串（NULL 项），读取后丢弃
                for _ in range(count):
                    constraint.string_list.append(reader.read_string())
                if constraint.string_list and constraint.string_list[-1] == "":
                    constraint.string_list.pop()
                # 原 VB 针对 hp3500 后端的修正：size 至少覆盖最长字符串+1
                if constraint.string_list:
                    longest = max(len(s) for s in constraint.string_list)
                    desc.size = max(desc.size, longest + 1)
            elif constraint.constraint_type == SANEConstraintType.SANE_CONSTRAINT_WORD_LIST:
                count = reader.read_word()  # 第一个 word 为数量（-1 计数语义，见规范）
                count = reader.read_word()  # 规范: 实际发送的是 count-1，这里补回
                for _ in range(count):
                    constraint.word_list.append(reader.read_word())
            elif constraint.constraint_type == SANEConstraintType.SANE_CONSTRAINT_RANGE:
                empty_range = reader.read_boolean()
                if not empty_range:
                    constraint.range = SANERange(
                        min=reader.read_word(),
                        max=reader.read_word(),
                        quant=reader.read_word(),
                    )
            desc.constraint = constraint
            descriptors.append(desc)
        return descriptors

    def find_option(self, name: str) -> Tuple[int, SANEOptionDescriptor]:
        """按名称查找选项，返回 (index, descriptor)。"""
        descriptors = self.get_option_descriptors()
        for idx, desc in enumerate(descriptors):
            if desc.name == name:
                return idx, desc
        raise KeyError(f"option '{name}' not found")

    # ------------------------------------------------------------ RPC: CONTROL_OPTION

    def control_option(self, request: SANEControlOptionRequest) -> SANEControlOptionReply:
        """SANE_NET_CONTROL_OPTION：读写/自动设置选项值。"""
        from .constants import SANEAction

        if request.value_type == SANEValueType.SANE_TYPE_GROUP:
            reply = SANEControlOptionReply()
            reply.status = SANEStatus.SANE_STATUS_INVAL
            return reply

        writer = WireWriter()
        writer.write_word(int(SANENetProcedureNumber.SANE_NET_CONTROL_OPTION))
        writer.write_word(request.handle)
        writer.write_word(request.option)
        writer.write_word(int(request.action))
        writer.write_word(int(request.value_type))
        writer.write_word(request.value_size)

        values = request.values
        array_len = option_value_array_length(request.value_size, int(request.value_type))
        if request.value_type in (SANEValueType.SANE_TYPE_BOOL, SANEValueType.SANE_TYPE_FIXED, SANEValueType.SANE_TYPE_INT):
            writer.write_word(array_len)
            if values is None:
                values = [None] * array_len
            for i in range(array_len):
                v = values[i] if i < len(values) else None
                if request.value_type == SANEValueType.SANE_TYPE_BOOL:
                    writer.write_boolean(bool(v) if v is not None else False)
                elif request.value_type == SANEValueType.SANE_TYPE_FIXED:
                    writer.write_word(sane_fix(float(v) if v is not None else 0.0))
                else:
                    writer.write_word(int(v) if v is not None else 0)
        elif request.value_type == SANEValueType.SANE_TYPE_BUTTON:
            writer.write_word(0)
        elif request.value_type == SANEValueType.SANE_TYPE_STRING:
            s = str(values[0]) if values and values[0] is not None else ""
            # 填充到 value_size-1（保留末尾 null 的位置），对应 VB 行为
            pad = request.value_size - 1
            if len(s) < pad:
                s = s + "\x00" * (pad - len(s))
            writer.write_string(s)

        self._control.sendall(writer.to_bytes())

        reply = self._read_control_option_reply()
        if reply.resource:
            self._authorize(self._reader, reply.resource)  # type: ignore[arg-type]
            reply = self._read_control_option_reply()
        return reply

    def _read_control_option_reply(self) -> SANEControlOptionReply:
        if self._reader is None:
            raise SaneError(SANEStatus.SANE_STATUS_IO_ERROR, "reader is None")
        reply = SANEControlOptionReply()
        reply.status = self._reader.read_word()
        reply.info = self._reader.read_word()
        reply.value_type = SANEValueType(self._reader.read_word())
        reply.value_size = self._reader.read_word()
        self._read_reply_values(reply)
        reply.resource = self._reader.read_string()
        return reply

    def _read_reply_values(self, reply: SANEControlOptionReply) -> None:
        if self._reader is None:
            raise SaneError(SANEStatus.SANE_STATUS_IO_ERROR, "reader is None")
        vt = reply.value_type
        if vt in (SANEValueType.SANE_TYPE_BOOL, SANEValueType.SANE_TYPE_FIXED, SANEValueType.SANE_TYPE_INT):
            array_len = self._reader.read_word()
            for _ in range(array_len):
                word = self._reader.read_word()
                if vt == SANEValueType.SANE_TYPE_FIXED:
                    reply.values.append(sane_unfix(word))
                elif vt == SANEValueType.SANE_TYPE_BOOL:
                    reply.values.append(word != 0)
                else:
                    reply.values.append(word)
        elif vt == SANEValueType.SANE_TYPE_BUTTON:
            array_len = self._reader.read_word()
        elif vt == SANEValueType.SANE_TYPE_STRING:
            s = self._reader.read_string()
            reply.values.append(s.replace("\x00", ""))
        elif vt == SANEValueType.SANE_TYPE_GROUP:
            pass

    # ------------------------------------------------------------ RPC: GET_PARAMETERS

    def get_parameters(self) -> SANEParameters:
        """SANE_NET_GET_PARAMETERS：读取当前帧参数。"""
        reader = self._request(
            SANENetProcedureNumber.SANE_NET_GET_PARAMETERS,
            (self.handle, SaneDataType.SANE_Word),
        )
        status = reader.read_word()
        if status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(status)
        params = SANEParameters()
        params.format = reader.read_word()
        params.last_frame = reader.read_word() != 0
        params.bytes_per_line = reader.read_word()
        params.pixels_per_line = reader.read_word()
        params.lines = reader.read_word()
        params.depth = reader.read_word()
        return params

    # ------------------------------------------------------------ RPC: START

    def start(self) -> Tuple[int, int]:
        """SANE_NET_START：开始扫描，返回 (数据端口, 字节序)。"""
        reader = self._request(
            SANENetProcedureNumber.SANE_NET_START,
            (self.handle, SaneDataType.SANE_Word),
        )
        status = reader.read_word()
        port = reader.read_word()
        byte_order = reader.read_word()
        resource = reader.read_string()
        if resource:
            self._authorize(reader, resource)
            status = reader.read_word()
            port = reader.read_word()
            byte_order = reader.read_word()
            resource = reader.read_string()
        if status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(status)
        logger.debug("start: data port=%d, byte order=0x%04x", port, byte_order)
        return port, byte_order

    # ------------------------------------------------------------ RPC: AUTHORIZE

    def _authorize(self, reader: WireReader, resource: str) -> None:
        """SANE_NET_AUTHORIZE。处理 $MD5$ 挑战并发送凭据。"""
        password = self.password or ""
        if "$MD5$" in resource.upper():
            p = resource.upper().index("$MD5$")
            md5_salt = resource[p + len("$MD5$"):]
            if len(md5_salt) > 128:
                raise SaneError(SANEStatus.SANE_STATUS_ACCESS_DENIED,
                                "the MD5 portion of the resource string is too long")
            digest = hashlib.md5(_default_encoding_encode(md5_salt + password)).hexdigest()
            password = f"$MD5${digest}"

        writer = WireWriter()
        writer.write_word(int(SANENetProcedureNumber.SANE_NET_AUTHORIZE))
        writer.write_string(resource)
        writer.write_string(self.username or "")
        writer.write_string(password)
        self._control.sendall(writer.to_bytes())
        # 回复为一个无意义 word
        reader.read_word()

    # ------------------------------------------------------------ 图像采集

    def acquire_frame(
        self,
        port: int,
        byte_order: int = SANENetByteOrder.SANE_NET_BIG_ENDIAN,
        timeout_s: Optional[int] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> SANEImageFrame:
        """连接数据端口，读取一帧图像。

        对应 VB 的 AcquireFrame。字节序参数用于兼容性保留
        （协议中图像数据长度字段按网络字节序传输，与 byte_order 无关）。
        """
        timeout_s = timeout_s or self.image_timeout_s
        timeout_ms = max(timeout_s * 1000, DEFAULT_IMAGE_PORT_TIMEOUT_MS)
        control = self._require_connection()
        host_ip = control.getpeername()[0]

        data_sock = socket.create_connection((host_ip, port), timeout=timeout_ms / 1000.0)
        data_sock.settimeout(timeout_ms / 1000.0)
        data_reader = WireReader(data_sock, timeout_ms)

        # 必须先连接数据端口再查询参数（对应 VB 的注释要求）
        params = self.get_parameters()
        logger.debug("beginning image transfer: %s", params)

        chunks: List[bytes] = []
        transferred = 0
        expected_total = params.lines * params.bytes_per_line if params.lines > 0 else 0

        next_progress_at = 1
        try:
            while True:
                length_raw = data_reader._read_exact(4)
                datalen = struct.unpack(">I", length_raw)[0]
                if datalen == 0xFFFFFFFF:
                    if expected_total > 0 and transferred < expected_total:
                        logger.debug(
                            "server underran expected byte count (%d < %d)",
                            transferred, expected_total,
                        )
                    if transferred == 0:
                        raise EmptyFrameException(
                            "an empty image frame was received from the SANE server"
                        )
                    break
                if expected_total > 0 and transferred >= expected_total:
                    logger.debug("server overran expected byte count without EOF; aborting")
                    break
                if datalen >= 32768 + 4096:
                    # 原 VB 逻辑: 数据长度字段异常（正常情况下为接收缓冲区大小附近）
                    logger.warning("bogus data length field: 0x%08x; aborting transfer", datalen)
                    break
                payload = data_reader._read_exact(datalen)
                chunks.append(payload)
                transferred += len(payload)
                # 进度
                if expected_total > 0:
                    progress = int((transferred / expected_total) * 100)
                    if progress > next_progress_at:
                        self._emit_progress(progress)
                        next_progress_at = progress + 10
                elif next_progress_at == 1:
                    next_progress_at = 2
                    self._emit_progress(-1)
        except ConnectionError as e:
            if "timeout" in str(e):
                raise SaneError(SANEStatus.SANE_STATUS_IO_ERROR, "timeout waiting for image data")
            raise ServerDisconnectedException(str(e))
        finally:
            try:
                data_sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                data_sock.close()
            except OSError:
                pass

        if expected_total > 0:
            self._emit_progress(100)

        data = b"".join(chunks)
        if expected_total > 0 and len(data) < expected_total:
            # 原 VB workaround：不足时补零到期望大小
            data = data + b"\x00" * (expected_total - len(data))

        return SANEImageFrame(params=params, data=data)

    def scan_all_frames(
        self,
        port: int,
        byte_order: int = SANENetByteOrder.SANE_NET_BIG_ENDIAN,
        timeout_s: Optional[int] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> List[SANEImageFrame]:
        """连续读取多帧（ADF 多页），直到服务端返回空帧/EOF。"""
        frames: List[SANEImageFrame] = []
        self._set_progress_callback(progress_callback)
        try:
            while True:
                try:
                    frame = self.acquire_frame(port, byte_order, timeout_s)
                except EmptyFrameException:
                    break
                frames.append(frame)
                # 检查参数中的 last_frame 标志；为兼容后端，遇空帧即停止
                if frame.params.last_frame:
                    break
                if len(frame.data) == 0:
                    break
        finally:
            self._set_progress_callback(None)
        return frames

    # ------------------------------------------------------------ 便捷方法

    def set_option(self, option: int, values: List[object]) -> SANEControlOptionReply:
        """便捷：设置选项值（自动推断类型）。"""
        from .constants import SANEAction, SANEValueType

        descriptors = self.get_option_descriptors()
        desc = descriptors[option]
        req = SANEControlOptionRequest(
            handle=self.handle,
            option=option,
            action=int(SANEAction.SANE_ACTION_SET_VALUE),
            value_type=desc.type,
            value_size=desc.size,
            values=values,
        )
        return self.control_option(req)

    def get_option(self, option: int) -> SANEControlOptionReply:
        """便捷：读取选项当前值。"""
        from .constants import SANEAction

        descriptors = self.get_option_descriptors()
        desc = descriptors[option]
        req = SANEControlOptionRequest(
            handle=self.handle,
            option=option,
            action=int(SANEAction.SANE_ACTION_GET_VALUE),
            value_type=desc.type,
            value_size=desc.size,
        )
        return self.control_option(req)


def _default_encoding_encode(text: str) -> bytes:
    """模拟 VB 的 Encoding.Default.GetBytes（系统 ANSI 代码页）。"""
    enc = locale.getpreferredencoding(False)
    try:
        return text.encode(enc, errors="replace")
    except LookupError:
        return text.encode("utf-8", errors="replace")
