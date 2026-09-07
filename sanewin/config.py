# -*- coding: utf-8 -*-
"""
读取 SANEWinDS.ini 主机配置（与 VB 版 SharedSettings 的 Host.N 段对应）。

典型格式::

    [Host.0]
    NameOrAddress=192.168.1.10
    Port=6566
    Username=
    Password=
    TCP_Timeout_ms=30000
    Image_Timeout_s=120
    Open=False
    Device=test:0
    AutoLocateDevice=
"""
from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class HostInfo:
    name_or_address: str = ""
    port: int = 6566
    username: str = ""
    password: str = ""
    tcp_timeout_ms: int = 30000
    image_timeout_s: int = 120
    device: str = ""
    auto_locate_device: str = ""


@dataclass
class SANEConfig:
    hosts: List[HostInfo] = field(default_factory=list)

    @classmethod
    def load(cls, path: Optional[str] = None) -> "SANEConfig":
        path = path or _default_config_path()
        cfg = cls()
        if not path or not os.path.isfile(path):
            return cfg
        parser = configparser.ConfigParser()
        try:
            parser.read(path, encoding="utf-8-sig")
        except (configparser.Error, OSError, UnicodeDecodeError):
            try:
                parser.read(path, encoding="gbk")
            except (configparser.Error, OSError, UnicodeDecodeError):
                return cfg

        for section in parser.sections():
            if not section.lower().startswith("host."):
                continue
            host = HostInfo()
            get = lambda key, default="": parser.get(section, key, fallback=default)  # noqa: E731
            host.name_or_address = get("NameOrAddress")
            try:
                host.port = int(get("Port", "6566"))
            except ValueError:
                host.port = 6566
            host.username = get("Username")
            host.password = get("Password")
            try:
                host.tcp_timeout_ms = int(get("TCP_Timeout_ms", "30000"))
            except ValueError:
                host.tcp_timeout_ms = 30000
            try:
                host.image_timeout_s = int(get("Image_Timeout_s", "120"))
            except ValueError:
                host.image_timeout_s = 120
            host.device = get("Device")
            host.auto_locate_device = get("AutoLocateDevice")
            if host.name_or_address:
                cfg.hosts.append(host)
        return cfg


def _default_config_path() -> str:
    """默认读取 ProgramData\\SANEWinDS\\SANEWinDS.ini（与 VB 版一致）。"""
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    return os.path.join(program_data, "SANEWinDS", "SANEWinDS.ini")


def parse_host_spec(spec: str) -> tuple:
    """解析 'host[:port]'，缺省端口 6566。"""
    spec = spec.strip()
    if spec.startswith("["):  # IPv6 字面量
        if "]" in spec:
            addr, _, rest = spec.partition("]")
            addr += "]"
            port = 6566
            if rest.startswith(":"):
                try:
                    port = int(rest[1:])
                except ValueError:
                    port = 6566
            return addr, port
    if spec.count(":") == 1:
        addr, _, port_str = spec.partition(":")
        try:
            return addr, int(port_str)
        except ValueError:
            return spec, 6566
    return spec, 6566
