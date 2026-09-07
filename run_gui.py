# -*- coding: utf-8 -*-
"""SANE 扫描客户端 打包入口（PyInstaller 使用）。"""
import logging

from sanewin.gui import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    main()
