# -*- coding: utf-8 -*-
"""
sanewin 命令行工具。

用法示例::

    # 列出远程 SANE 服务器设备
    python -m sanewin list --host 192.168.1.10:6566

    # 列出设备选项与当前值
    python -m sanewin options --host 192.168.1.10 --device test:0

    # 读取/设置选项
    python -m sanewin get  --host 192.168.1.10 --device test:0 --option resolution
    python -m sanewin set  --host 192.168.1.10 --device test:0 --option resolution --value 300

    # 扫描并保存
    python -m sanewin scan --host 192.168.1.10 --device test:0 -o page.bmp \\
        --option mode=Gray --option resolution=300
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional

from .client import SaneClient, SaneError
from .config import SANEConfig, parse_host_spec
from .constants import (
    SANEAction,
    SANEConstraintType,
    SANEFrame,
    SANEStatus,
    SANEValueType,
)
from .images import frame_to_bmp
from .models import SANEControlOptionRequest, SANEOptionDescriptor, SANEParameters, status_name

logger = logging.getLogger("sanewin")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sanewin",
        description="SANE network protocol client (Python port of SANEWinDS)",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, help="increase log verbosity")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--host", default=None, help="server host[:port] (default 6566)")
        p.add_argument("--user", default="", help="username")
        p.add_argument("--password", default="", help="password")
        p.add_argument("--timeout", type=int, default=30000, help="TCP timeout in ms")
        p.add_argument("--ini", default=None, help="SANEWinDS.ini path (uses [Host.N] sections)")

    p_list = sub.add_parser("list", help="list devices on the server")
    add_common(p_list)

    p_options = sub.add_parser("options", help="list options of an opened device")
    add_common(p_options)
    p_options.add_argument("--device", required=True, help="device name (e.g. test:0)")

    p_get = sub.add_parser("get", help="read an option value")
    add_common(p_get)
    p_get.add_argument("--device", required=True, help="device name")
    p_get.add_argument("--option", required=True, help="option name or index")

    p_set = sub.add_parser("set", help="set an option value")
    add_common(p_set)
    p_set.add_argument("--device", required=True, help="device name")
    p_set.add_argument("--option", required=True, help="option name or index")
    p_set.add_argument("--value", required=True, help="value(s), comma separated for arrays")

    p_scan = sub.add_parser("scan", help="scan and save image(s) as BMP")
    add_common(p_scan)
    p_scan.add_argument("--device", required=True, help="device name")
    p_scan.add_argument("-o", "--output", required=True, help="output file pattern (e.g. page.bmp -> page_1.bmp)")
    p_scan.add_argument("--option", action="append", default=[], metavar="NAME=VALUE", help="option to set before scan")
    p_scan.add_argument("--dpi", type=int, default=0, help="DPI stored in BMP header")
    p_scan.add_argument("--all-pages", action="store_true", help="keep scanning until empty frame (ADF)")

    return parser


def _resolve_host(args) -> tuple:
    """返回 (host, port, user, password, timeout_ms, image_timeout_s)。"""
    host, port, user, password = args.host or "", 6566, args.user or "", args.password or ""
    timeout_ms = args.timeout or 30000
    image_timeout_s = 120
    if args.ini:
        cfg = SANEConfig.load(args.ini)
        if cfg.hosts:
            h = cfg.hosts[0]
            host = host or h.name_or_address
            port = h.port
            user = user or h.username
            password = password or h.password
            timeout_ms = h.tcp_timeout_ms
            image_timeout_s = h.image_timeout_s
            if args.host is None and hasattr(args, "device") and not getattr(args, "device", None) and h.device:
                pass
    if host:
        parsed_host, parsed_port = parse_host_spec(host)
        host, port = parsed_host, parsed_port if args.host else port
    if not host:
        raise SystemExit("error: --host is required (or a valid --ini with hosts)")
    return host, port, user, password, timeout_ms, image_timeout_s


def _connect(args) -> SaneClient:
    host, port, user, password, timeout_ms, image_timeout_s = _resolve_host(args)
    client = SaneClient(host, port, user, password, timeout_ms, image_timeout_s)
    status = client.init()
    if status != SANEStatus.SANE_STATUS_GOOD:
        raise SaneError(status, f"init failed: {status_name(status)}")
    return client


def _parse_option_ref(ref: str) -> int:
    try:
        return int(ref)
    except ValueError:
        return -1  # 名称，调用方解析


def _find_option(client: SaneClient, ref: str):
    descriptors = client.get_option_descriptors()
    idx = _parse_option_ref(ref)
    if idx >= 0 and idx < len(descriptors):
        return idx, descriptors[idx]
    for i, d in enumerate(descriptors):
        if d.name == ref:
            return i, d
    raise SystemExit(f"error: option '{ref}' not found")


def _format_value(desc: SANEOptionDescriptor, value) -> str:
    if desc.type == SANEValueType.SANE_TYPE_BOOL:
        return "True" if value else "False"
    if desc.type == SANEValueType.SANE_TYPE_FIXED:
        return f"{value:g}"
    return str(value)


def _format_constraint(desc: SANEOptionDescriptor) -> str:
    c = desc.constraint
    if c.constraint_type == SANEConstraintType.SANE_CONSTRAINT_STRING_LIST:
        return ", ".join(c.string_list)
    if c.constraint_type == SANEConstraintType.SANE_CONSTRAINT_WORD_LIST:
        return ", ".join(str(w) for w in c.word_list)
    if c.constraint_type == SANEConstraintType.SANE_CONSTRAINT_RANGE and c.range is not None:
        r = c.range
        q = f" step {r.quant}" if r.quant else ""
        return f"{r.min}..{r.max}{q}"
    return "-"


def cmd_list(args) -> int:
    client = _connect(args)
    try:
        devices = client.get_devices()
        if not devices:
            print("(no devices reported)")
        for d in devices:
            print(f"{d.name}\t{d.vendor}\t{d.model}\t{d.type}")
    finally:
        client.exit()
    return 0


def cmd_options(args) -> int:
    client = _connect(args)
    try:
        status = client.open(args.device)
        if status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(status, f"open failed: {status_name(status)}")
        descriptors = client.get_option_descriptors()
        for idx, desc in enumerate(descriptors):
            req = SANEControlOptionRequest(
                handle=client.handle,
                option=idx,
                action=int(SANEAction.SANE_ACTION_GET_VALUE),
                value_type=desc.type,
                value_size=desc.size,
            )
            reply = client.control_option(req)
            if desc.type in (SANEValueType.SANE_TYPE_BUTTON, SANEValueType.SANE_TYPE_GROUP):
                value_str = ""
            else:
                value_str = ", ".join(_format_value(desc, v) for v in reply.values)
            flags = []
            if desc.cap & (1 << 5):
                flags.append("inactive")
            if desc.cap & (1 << 0):
                flags.append("settable")
            print(f"[{idx}] {desc.name} ({desc.type.name}) = {value_str}")
            print(f"    title: {desc.title}")
            print(f"    unit : {desc.unit}  size: {desc.size}  flags: {','.join(flags) or '-'}")
            print(f"    constraint: {_format_constraint(desc)}")
    finally:
        client.exit()
    return 0


def cmd_get(args) -> int:
    client = _connect(args)
    try:
        status = client.open(args.device)
        if status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(status, f"open failed: {status_name(status)}")
        idx, desc = _find_option(client, args.option)
        req = SANEControlOptionRequest(
            handle=client.handle, option=idx,
            action=int(SANEAction.SANE_ACTION_GET_VALUE),
            value_type=desc.type, value_size=desc.size,
        )
        reply = client.control_option(req)
        if reply.status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(reply.status, f"get failed: {status_name(reply.status)}")
        print(", ".join(_format_value(desc, v) for v in reply.values) or "(no value)")
    finally:
        client.exit()
    return 0


def _parse_values(text: str, desc: SANEOptionDescriptor) -> List[object]:
    parts = [p.strip() for p in text.split(",")]
    out: List[object] = []
    for p in parts:
        if desc.type == SANEValueType.SANE_TYPE_BOOL:
            out.append(p.lower() in ("1", "true", "yes", "on"))
        elif desc.type == SANEValueType.SANE_TYPE_INT:
            out.append(int(p))
        elif desc.type == SANEValueType.SANE_TYPE_FIXED:
            out.append(float(p))
        else:
            out.append(p)
    return out


def cmd_set(args) -> int:
    client = _connect(args)
    try:
        status = client.open(args.device)
        if status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(status, f"open failed: {status_name(status)}")
        idx, desc = _find_option(client, args.option)
        values = _parse_values(args.value, desc)
        req = SANEControlOptionRequest(
            handle=client.handle, option=idx,
            action=int(SANEAction.SANE_ACTION_SET_VALUE),
            value_type=desc.type, value_size=desc.size, values=values,
        )
        reply = client.control_option(req)
        if reply.status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(reply.status, f"set failed: {status_name(reply.status)}")
        print(f"set {desc.name} -> {', '.join(_format_value(desc, v) for v in values)}")
        if reply.info & (1 << 1):
            print("note: server requests options reload")
        if reply.info & (1 << 2):
            print("note: server requests parameters reload")
    finally:
        client.exit()
    return 0


def cmd_scan(args) -> int:
    client = _connect(args)
    try:
        status = client.open(args.device)
        if status != SANEStatus.SANE_STATUS_GOOD:
            raise SaneError(status, f"open failed: {status_name(status)}")

        # 应用预设选项
        descriptors = client.get_option_descriptors()
        for spec in args.option:
            name, _, value = spec.partition("=")
            idx = _parse_option_ref(name)
            if idx < 0 or idx >= len(descriptors):
                for i, d in enumerate(descriptors):
                    if d.name == name:
                        idx, name = i, d.name
                        break
                else:
                    raise SystemExit(f"error: option '{name}' not found")
            desc = descriptors[idx]
            values = _parse_values(value, desc)
            req = SANEControlOptionRequest(
                handle=client.handle, option=idx,
                action=int(SANEAction.SANE_ACTION_SET_VALUE),
                value_type=desc.type, value_size=desc.size, values=values,
            )
            reply = client.control_option(req)
            if reply.status != SANEStatus.SANE_STATUS_GOOD:
                raise SaneError(reply.status, f"set {name} failed: {status_name(reply.status)}")
            logger.info("set %s = %s", name, value)

        port, byte_order = client.start()
        frames = client.scan_all_frames(port, byte_order, progress_callback=_progress)
        if not frames:
            raise SystemExit("error: no image frames received (empty document?)")

        base, ext = os.path.splitext(args.output)
        big_endian = (byte_order == 0x4321)  # SANE_NET_BIG_ENDIAN
        for i, frame in enumerate(frames):
            out_path = f"{base}_{i + 1}{ext}" if len(frames) > 1 else args.output
            data = frame_to_bmp(frame, dpi=args.dpi, big_endian=big_endian)
            with open(out_path, "wb") as f:
                f.write(data)
            print(f"saved {out_path} ({frame.params.pixels_per_line}x{frame.params.lines}, {_frame_name(frame.params)})")
    finally:
        client.exit()
    return 0


def _frame_name(params) -> str:
    from .constants import FRAME_NAMES
    name = FRAME_NAMES.get(params.format, f"format{params.format}")
    return f"{name} {params.depth}-bit"


def _progress(percent: int) -> None:
    if percent < 0:
        print("scanning... (unknown length)", file=sys.stderr)
    else:
        print(f"\rscanning... {percent}%", end="", file=sys.stderr)
        if percent >= 100:
            print(file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    level = logging.WARNING
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    try:
        return {
            "list": cmd_list,
            "options": cmd_options,
            "get": cmd_get,
            "set": cmd_set,
            "scan": cmd_scan,
        }[args.command](args)
    except SaneError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (ConnectionError, OSError) as e:
        print(f"error: connection problem: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
