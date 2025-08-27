#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spidermind GUI 启动脚本
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    from app.main_gui import main
    sys.exit(main())