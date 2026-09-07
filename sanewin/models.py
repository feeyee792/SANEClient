# -*- coding: utf-8 -*-
"""
SANE 数据结构（dataclass 版本）。

对应原 SANEWinDS 中 classSANE.vb 的 SANE_Device / SANE_Option_Descriptor /
SANE_Parameters / SANE_Range / SANENetControlOption_Request / Reply 等结构。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union

from .constants import SANEConstraintType, SANEStatus, SANEValueType


@dataclass
class SANERange:
    """SANE_Range: 约束为区间时的 min / max / quant。"""
    min: int = 0
    max: int = 0
    quant: int = 0

    def to_dict(self) -> dict:
        return {"min": self.min, "max": self.max, "quant": self.quant}


@dataclass
class SANEConstraint:
    """选项约束（对应 VB 的 SANEConstraintUnion）。"""
    constraint_type: SANEConstraintType = SANEConstraintType.SANE_CONSTRAINT_NONE
    string_list: List[str] = field(default_factory=list)
    word_list: List[int] = field(default_factory=list)
    range: Optional[SANERange] = None

    def to_dict(self) -> dict:
        d: dict = {"type": self.constraint_type.name}
        if self.constraint_type == SANEConstraintType.SANE_CONSTRAINT_STRING_LIST:
            d["values"] = list(self.string_list)
        elif self.constraint_type == SANEConstraintType.SANE_CONSTRAINT_WORD_LIST:
            d["values"] = list(self.word_list)
        elif self.constraint_type == SANEConstraintType.SANE_CONSTRAINT_RANGE and self.range:
            d.update(self.range.to_dict())
        return d


@dataclass
class SANEOptionDescriptor:
    """SANE_Option_Descriptor。"""
    name: str = ""
    title: str = ""
    desc: str = ""
    type: SANEValueType = SANEValueType.SANE_TYPE_INT
    unit: int = 0
    size: int = 0
    cap: int = 0
    constraint: SANEConstraint = field(default_factory=SANEConstraint)

    @property
    def index(self) -> int:
        return getattr(self, "_index", -1)

    @index.setter
    def index(self, value: int) -> None:
        self._index = value

    def to_dict(self) -> dict:
        from .constants import UNIT_STRINGS
        return {
            "name": self.name,
            "title": self.title,
            "desc": self.desc,
            "type": self.type.name,
            "unit": UNIT_STRINGS.get(self.unit, str(self.unit)),
            "size": self.size,
            "cap": self.cap,
            "constraint": self.constraint.to_dict(),
        }


@dataclass
class SANEDevice:
    """SANE_Device。"""
    name: str = ""
    vendor: str = ""
    model: str = ""
    type: str = ""

    def __str__(self) -> str:
        return f"{self.vendor} {self.model} ({self.type}) [{self.name}]"


@dataclass
class SANEParameters:
    """SANE_Parameters。"""
    format: int = 0
    last_frame: bool = False
    bytes_per_line: int = 0
    pixels_per_line: int = 0
    lines: int = 0
    depth: int = 0


@dataclass
class SANEImageFrame:
    """一帧图像数据。"""
    params: SANEParameters = field(default_factory=SANEParameters)
    data: bytes = b""

    @property
    def is_empty(self) -> bool:
        return len(self.data) == 0


@dataclass
class SANEControlOptionRequest:
    """SANENetControlOption_Request。"""
    handle: int = 0
    option: int = 0
    action: int = 0  # SANEAction
    value_type: SANEValueType = SANEValueType.SANE_TYPE_INT
    value_size: int = 0
    values: Optional[List[object]] = None


@dataclass
class SANEControlOptionReply:
    """SANENetControlOption_Reply。"""
    status: int = 0
    info: int = 0
    value_type: SANEValueType = SANEValueType.SANE_TYPE_INT
    value_size: int = 0
    values: List[object] = field(default_factory=list)
    resource: str = ""


def status_name(status: int) -> str:
    try:
        return SANEStatus(status).name
    except ValueError:
        return f"UNKNOWN({status})"
