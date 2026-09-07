# -*- coding: utf-8 -*-
"""
SANE 网络协议常量与枚举。

逐项对应原 SANEWinDS 项目 classSANE.vb 中 "SANE.h" 区域的定义，
以及 SANE 网络协议（SANE Net Protocol）规范中的过程号 / 字节序约定。
"""
from __future__ import annotations

import enum

# ---------------------------------------------------------------- 布尔值
SANE_FALSE = 0
SANE_TRUE = 1

# ---------------------------------------------------------------- 版本
SANE_CURRENT_MAJOR = 1
SANE_CURRENT_MINOR = 0
SANE_CURRENT_BUILD = 3

SANE_MAX_USERNAME_LEN = 128
SANE_MAX_PASSWORD_LEN = 128

SANE_FIXED_SCALE_SHIFT = 16


def sane_version_code(major: int, minor: int, build: int) -> int:
    """SANE_VERSION_CODE: 打包为 32 位版本码。"""
    return ((major & 0xFF) << 24) | ((minor & 0xFF) << 16) | ((build & 0xFFFF) << 0)


def sane_version_major(code: int) -> int:
    return (code >> 24) & 0xFF


def sane_version_minor(code: int) -> int:
    return (code >> 16) & 0xFF


def sane_version_build(code: int) -> int:
    return code & 0xFFFF


VERSION_CODE = sane_version_code(SANE_CURRENT_MAJOR, SANE_CURRENT_MINOR, SANE_CURRENT_BUILD)


def sane_fix(value: float) -> int:
    """SANE_FIX: double -> SANE_FIXED（定点数，16 位小数）。

    原 VB 实现对溢出时钳制到 Int32 极值，这里保留该行为。
    """
    try:
        result = int(value * (1 << SANE_FIXED_SCALE_SHIFT))
        if result > 0x7FFFFFFF:
            return 0x7FFFFFFF
        if result < -0x80000000:
            return -0x80000000
        return result
    except (OverflowError, ValueError):
        return 0x7FFFFFFF if value > 0 else -0x80000000


def sane_unfix(word: int) -> float:
    """SANE_UNFIX: SANE_FIXED -> double，保留 4 位小数。"""
    return round(word / float(1 << SANE_FIXED_SCALE_SHIFT), 4)


# ---------------------------------------------------------------- 选项能力
SANE_CAP_SOFT_SELECT = 1 << 0
SANE_CAP_HARD_SELECT = 1 << 1
SANE_CAP_SOFT_DETECT = 1 << 2
SANE_CAP_EMULATED = 1 << 3
SANE_CAP_AUTOMATIC = 1 << 4
SANE_CAP_INACTIVE = 1 << 5
SANE_CAP_ADVANCED = 1 << 6


def sane_option_is_readable(cap: int) -> bool:
    if not sane_option_is_active(cap):
        return False
    if (cap & SANE_CAP_HARD_SELECT) and not (cap & SANE_CAP_SOFT_DETECT):
        return False
    return True


def sane_option_is_active(cap: int) -> bool:
    return (cap & SANE_CAP_INACTIVE) == 0


def sane_option_is_settable(cap: int) -> bool:
    return (cap & SANE_CAP_SOFT_SELECT) != 0


# ---------------------------------------------------------------- 信息位
SANE_INFO_INEXACT = 1 << 0
SANE_INFO_RELOAD_OPTIONS = 1 << 1
SANE_INFO_RELOAD_PARAMS = 1 << 2


# ---------------------------------------------------------------- 枚举


class SANEConstraintType(enum.IntEnum):
    SANE_CONSTRAINT_NONE = 0
    SANE_CONSTRAINT_RANGE = 1
    SANE_CONSTRAINT_WORD_LIST = 2
    SANE_CONSTRAINT_STRING_LIST = 3


class SANEAction(enum.IntEnum):
    SANE_ACTION_GET_VALUE = 0
    SANE_ACTION_SET_VALUE = 1
    SANE_ACTION_SET_AUTO = 2


class SANEFrame(enum.IntEnum):
    SANE_FRAME_GRAY = 0
    SANE_FRAME_RGB = 1
    SANE_FRAME_RED = 2
    SANE_FRAME_GREEN = 3
    SANE_FRAME_BLUE = 4


class SANEStatus(enum.IntEnum):
    SANE_STATUS_GOOD = 0
    SANE_STATUS_UNSUPPORTED = 1
    SANE_STATUS_CANCELLED = 2
    SANE_STATUS_DEVICE_BUSY = 3
    SANE_STATUS_INVAL = 4
    SANE_STATUS_EOF = 5
    SANE_STATUS_JAMMED = 6
    SANE_STATUS_NO_DOCS = 7
    SANE_STATUS_COVER_OPEN = 8
    SANE_STATUS_IO_ERROR = 9
    SANE_STATUS_NO_MEM = 10
    SANE_STATUS_ACCESS_DENIED = 11


STATUS_NAMES = {s.name: s.value for s in SANEStatus}


class SANEValueType(enum.IntEnum):
    SANE_TYPE_BOOL = 0
    SANE_TYPE_INT = 1
    SANE_TYPE_FIXED = 2
    SANE_TYPE_STRING = 3
    SANE_TYPE_BUTTON = 4
    SANE_TYPE_GROUP = 5


class SANEUnit(enum.IntEnum):
    SANE_UNIT_NONE = 0
    SANE_UNIT_PIXEL = 1
    SANE_UNIT_BIT = 2
    SANE_UNIT_MM = 3
    SANE_UNIT_DPI = 4
    SANE_UNIT_PERCENT = 5
    SANE_UNIT_MICROSECOND = 6


UNIT_STRINGS = {
    SANEUnit.SANE_UNIT_NONE: None,
    SANEUnit.SANE_UNIT_PIXEL: "pixels",
    SANEUnit.SANE_UNIT_BIT: "bits",
    SANEUnit.SANE_UNIT_MM: "mm",
    SANEUnit.SANE_UNIT_DPI: "dpi",
    SANEUnit.SANE_UNIT_PERCENT: "%",
    SANEUnit.SANE_UNIT_MICROSECOND: "ms",
}


class SANENetProcedureNumber(enum.IntEnum):
    SANE_NET_INIT = 0
    SANE_NET_GET_DEVICES = 1
    SANE_NET_OPEN = 2
    SANE_NET_CLOSE = 3
    SANE_NET_GET_OPTION_DESCRIPTORS = 4
    SANE_NET_CONTROL_OPTION = 5
    SANE_NET_GET_PARAMETERS = 6
    SANE_NET_START = 7
    SANE_NET_CANCEL = 8
    SANE_NET_AUTHORIZE = 9
    SANE_NET_EXIT = 10


class SANENetByteOrder(enum.IntEnum):
    SANE_NET_LITTLE_ENDIAN = 0x1234
    SANE_NET_BIG_ENDIAN = 0x4321


class SaneDataType(enum.IntEnum):
    """序列化层使用的内部数据类型（对应 VB 的同名枚举）。"""
    SANE_Word = 0
    SANE_Byte = 1
    SANE_Char = 2
    SANE_String = 3
    SANE_Boolean = 4


# 帧格式名称（用于 CLI 显示）
FRAME_NAMES = {
    SANEFrame.SANE_FRAME_GRAY: "gray",
    SANEFrame.SANE_FRAME_RGB: "rgb",
    SANEFrame.SANE_FRAME_RED: "red",
    SANEFrame.SANE_FRAME_GREEN: "green",
    SANEFrame.SANE_FRAME_BLUE: "blue",
}
