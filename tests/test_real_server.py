# -*- coding: utf-8 -*-
"""真实 SANE 服务器集成测试（只读操作，不触发扫描）。

默认目标 192.168.1.230:6566；可用环境变量覆盖：
    SANE_TEST_HOST / SANE_TEST_PORT / SANE_TEST_USER / SANE_TEST_PASSWORD
服务器不可达时自动跳过（skip）。
"""
from __future__ import annotations

import os
import socket
import time
import unittest

from sanewin.client import SaneClient
from sanewin.constants import SANEAction, SANEStatus, SANEValueType
from sanewin.models import SANEControlOptionRequest

HOST = os.environ.get("SANE_TEST_HOST", "192.168.1.230")
PORT = int(os.environ.get("SANE_TEST_PORT", "6566"))
USER = os.environ.get("SANE_TEST_USER", "")
PASSWORD = os.environ.get("SANE_TEST_PASSWORD", "")
TIMEOUT_MS = int(os.environ.get("SANE_TEST_TIMEOUT_MS", "30000"))


def _server_reachable() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=3):
            return True
    except OSError:
        return False


@unittest.skipUnless(_server_reachable(), f"真实 SANE 服务器 {HOST}:{PORT} 不可达")
class TestRealServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = SaneClient(HOST, PORT, USER, PASSWORD, TIMEOUT_MS)
        status = cls.client.init()
        if status != SANEStatus.SANE_STATUS_GOOD:
            raise unittest.SkipTest(f"服务器 init 失败: {status}")

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.client.exit()
        except Exception:
            pass

    def tearDown(self) -> None:
        # 每个测试后关闭已打开的设备，避免影响后续测试
        try:
            if self.client.handle >= 0:
                self.client.close()
        except Exception:
            pass

    def test_init(self):
        # init 已在 setUpClass 完成；这里验证握手结果
        self.assertGreater(self.client.server_version_code, 0)

    def test_get_devices(self):
        devices = self.client.get_devices()
        if not devices:
            # 真实设备后端（USB 争用）可能有瞬时状态，短暂等待后重试一次
            time.sleep(1.0)
            devices = self.client.get_devices()
        self.assertGreaterEqual(len(devices), 1)
        for d in devices:
            self.assertTrue(d.name)
        print(f"\n发现 {len(devices)} 个设备:")
        for d in devices:
            print(f"  {d.name}  {d.vendor} {d.model} ({d.type})")

    def _open(self, name: str) -> int:
        """确保设备已关闭后重新打开。"""
        if self.client.handle >= 0:
            self.client.close()
        return self.client.open(name)

    def test_open_and_descriptors(self):
        # 同一 USB 一体机可能被多个后端（epson2/epsonscan2）争用，
        # 逐个尝试，至少打开一个并读到描述符。
        devices = self.client.get_devices()
        opened = None
        descs = None
        for dev in devices:
            status = self._open(dev.name)
            if status != SANEStatus.SANE_STATUS_GOOD:
                print(f"\n设备 {dev.name} 打开失败 (status {status})，跳过")
                continue
            opened = dev
            descs = self.client.get_option_descriptors()
            break
        self.assertIsNotNone(opened, "所有设备都无法打开")
        self.assertGreater(len(descs), 0)
        print(f"\n设备 {opened.name} 共 {len(descs)} 个选项")
        for i, d in enumerate(descs):
            print(f"  [{i}] {d.name or '(unnamed)'} type={d.type.name} cap=0x{d.cap:x}")

    def test_get_option_values(self):
        devices = self.client.get_devices()
        status = self._open(devices[0].name)
        self.assertEqual(status, SANEStatus.SANE_STATUS_GOOD)
        descs = self.client.get_option_descriptors()
        for i, d in enumerate(descs):
            if d.type in (SANEValueType.SANE_TYPE_BUTTON, SANEValueType.SANE_TYPE_GROUP):
                continue
            req = SANEControlOptionRequest(
                handle=self.client.handle, option=i,
                action=int(SANEAction.SANE_ACTION_GET_VALUE),
                value_type=d.type, value_size=d.size,
            )
            reply = self.client.control_option(req)
            if reply.status == SANEStatus.SANE_STATUS_GOOD:
                print(f"  {d.name} = {reply.values}")
            else:
                print(f"  {d.name} = (status {reply.status})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
