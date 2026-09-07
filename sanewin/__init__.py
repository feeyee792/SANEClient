# -*- coding: utf-8 -*-
"""
sanewin —— SANE 网络协议客户端（Python 重构版）。

对应原 SANEWinDS 项目 classSANE.vb 的核心功能：与远程 SANE 服务器
通信、枚举设备、读写选项、采集扫描图像，并提供 CLI 工具。
"""
from .client import (
    DEFAULT_IMAGE_TIMEOUT_S,
    DEFAULT_TCP_TIMEOUT_MS,
    EmptyFrameException,
    SaneClient,
    SaneError,
    ServerDisconnectedException,
)
from .constants import (
    SANEAction,
    SANEConstraintType,
    SANEFrame,
    SANEStatus,
    SANEValueType,
    SANEUnit,
)
from .images import combine_frames, frame_to_bmp, frames_to_bmp
from .models import (
    SANEControlOptionReply,
    SANEControlOptionRequest,
    SANEDevice,
    SANEImageFrame,
    SANEOptionDescriptor,
    SANEParameters,
)

__all__ = [
    "SaneClient",
    "SaneError",
    "EmptyFrameException",
    "ServerDisconnectedException",
    "SANEAction",
    "SANEFrame",
    "SANEStatus",
    "SANEValueType",
    "SANEUnit",
    "SANEConstraintType",
    "SANEDevice",
    "SANEOptionDescriptor",
    "SANEParameters",
    "SANEImageFrame",
    "SANEControlOptionRequest",
    "SANEControlOptionReply",
    "frame_to_bmp",
    "frames_to_bmp",
    "combine_frames",
    "DEFAULT_TCP_TIMEOUT_MS",
    "DEFAULT_IMAGE_TIMEOUT_S",
]

__version__ = "1.0.0"
