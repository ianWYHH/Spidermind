#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spidermind GUI 主入口
"""
import sys
import os
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QDir, qInstallMessageHandler, QtMsgType
from PySide6.QtGui import QFont

from app.ui.windows import MainWindow


def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('spidermind_gui.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def qt_message_handler(mode, context, message):
    """Qt消息处理器"""
    if mode == QtMsgType.QtDebugMsg:
        logging.getLogger('Qt').debug(message)
    elif mode == QtMsgType.QtWarningMsg:
        logging.getLogger('Qt').warning(message)
    elif mode == QtMsgType.QtCriticalMsg:
        logging.getLogger('Qt').error(message)
    elif mode == QtMsgType.QtFatalMsg:
        logging.getLogger('Qt').critical(message)


def setup_application():
    """设置应用程序"""
    # 启用高DPI支持
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # 创建应用
    app = QApplication(sys.argv)
    
    # 设置应用信息
    app.setApplicationName("Spidermind")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Spidermind Team")
    app.setOrganizationDomain("spidermind.com")
    
    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    # 安装Qt消息处理器
    qInstallMessageHandler(qt_message_handler)
    
    return app


def check_dependencies():
    """检查依赖"""
    required_modules = [
        'mysql.connector',
        'requests',
        'bs4',
        'lxml'
    ]
    
    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        error_msg = f"缺少必要的依赖模块:\n{', '.join(missing_modules)}\n\n"
        error_msg += "请安装缺失的模块:\n"
        error_msg += f"pip install {' '.join(missing_modules)}"
        
        QMessageBox.critical(None, "依赖检查失败", error_msg)
        return False
    
    return True


def check_config():
    """检查配置文件"""
    config_file = project_root / "config.ini"
    if not config_file.exists():
        error_msg = "配置文件 config.ini 不存在！\n\n"
        error_msg += "请确保项目根目录下有正确的 config.ini 文件。"
        
        QMessageBox.critical(None, "配置文件缺失", error_msg)
        return False
    
    return True


def main():
    """主函数"""
    # 设置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("启动 Spidermind GUI")
        
        # 创建应用
        app = setup_application()
        
        # 检查依赖
        if not check_dependencies():
            return 1
        
        # 检查配置
        if not check_config():
            return 1
        
        # 创建主窗口
        logger.info("创建主窗口")
        window = MainWindow()
        window.show()
        
        # 显示启动信息
        logger.info("GUI 启动成功")
        QMessageBox.information(
            window, 
            "欢迎使用 Spidermind",
            "Spidermind 爬虫管理系统已启动！\n\n"
            "功能说明：\n"
            "• 左侧：选择要使用的爬虫\n"
            "• 中间：配置参数并启动/停止爬虫\n"
            "• 右侧：查看实时日志\n"
            "• 底部：查看统计信息和系统状态\n\n"
            "请先在左侧选择一个爬虫开始使用。"
        )
        
        # 运行应用
        return app.exec()
        
    except Exception as e:
        logger.error(f"GUI 启动失败: {e}", exc_info=True)
        
        if 'app' in locals():
            QMessageBox.critical(
                None, 
                "启动失败", 
                f"Spidermind GUI 启动失败：\n\n{str(e)}\n\n"
                "请检查日志文件 spidermind_gui.log 获取详细信息。"
            )
        else:
            print(f"GUI 启动失败: {e}")
        
        return 1


if __name__ == "__main__":
    sys.exit(main())