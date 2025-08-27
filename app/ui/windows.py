"""
主窗口 - 组装所有UI组件
"""
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                               QSplitter, QMessageBox, QApplication)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon

from app.ui.views.sidebar import Sidebar
from app.ui.views.control_panel import ControlPanel
from app.ui.views.log_view import LogView
from app.ui.views.status_bar import StatusBar
from app.spiders_registry import SpiderMeta
from db.dao import DatabaseDAO
from app.run_subprocess import subprocess_manager

import logging


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        
        # 组件
        self.dao = None
        self.current_process = None
        self.refresh_timer = QTimer()
        
        # 初始化
        self._init_database()
        self._setup_ui()
        self._setup_timer()
        self._connect_signals()
        self._load_styles()
        
        # 初始化数据
        self._initial_load()
    
    def _init_database(self):
        """初始化数据库连接"""
        try:
            self.dao = DatabaseDAO()
            db_connected = self.dao.test_connection()
            self.logger.info(f"数据库连接状态: {'成功' if db_connected else '失败'}")
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            self.dao = None
    
    def _setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("Spidermind - 爬虫管理系统")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)
        
        # 设置窗口图标（如果有的话）
        # self.setWindowIcon(QIcon("assets/icon.png"))
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建主分割器
        main_splitter = QSplitter(Qt.Horizontal)
        
        # 侧边栏
        self.sidebar = Sidebar()
        main_splitter.addWidget(self.sidebar)
        
        # 右侧区域（控制面板 + 日志视图）
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # 右侧水平分割器
        right_splitter = QSplitter(Qt.Horizontal)
        
        # 控制面板
        self.control_panel = ControlPanel()
        right_splitter.addWidget(self.control_panel)
        
        # 日志视图
        self.log_view = LogView()
        right_splitter.addWidget(self.log_view)
        
        # 设置右侧分割器比例 (控制面板:日志视图 = 1:2)
        right_splitter.setSizes([400, 800])
        
        right_layout.addWidget(right_splitter)
        
        # 状态栏
        self.status_bar = StatusBar()
        right_layout.addWidget(self.status_bar)
        
        right_widget.setLayout(right_layout)
        main_splitter.addWidget(right_widget)
        
        # 设置主分割器比例 (侧边栏:右侧 = 1:4)
        main_splitter.setSizes([250, 1000])
        
        main_layout.addWidget(main_splitter)
        central_widget.setLayout(main_layout)
    
    def _setup_timer(self):
        """设置定时器"""
        # 数据刷新定时器（每2秒）
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(2000)
    
    def _connect_signals(self):
        """连接信号槽"""
        # 侧边栏信号
        self.sidebar.spider_selected.connect(self._on_spider_selected)
        self.sidebar.refresh_requested.connect(self._refresh_spiders)
        
        # 控制面板信号
        self.control_panel.start_spider.connect(self._start_spider)
        self.control_panel.stop_spider.connect(self._stop_spider)
        
        # 日志视图信号
        self.log_view.refresh_requested.connect(self._refresh_logs)
        
        # 状态栏信号
        self.status_bar.database_check_requested.connect(self._test_database_connection)
    
    def _load_styles(self):
        """加载样式表"""
        try:
            style_path = os.path.join("app", "ui", "styles.qss")
            if os.path.exists(style_path):
                with open(style_path, 'r', encoding='utf-8') as f:
                    self.setStyleSheet(f.read())
                self.logger.info("样式表加载成功")
            else:
                self.logger.warning(f"样式表文件不存在: {style_path}")
        except Exception as e:
            self.logger.error(f"样式表加载失败: {e}")
    
    def _initial_load(self):
        """初始加载数据"""
        self._refresh_spiders()
        self._refresh_data()
        
        # 设置数据库连接状态
        if self.dao:
            self.status_bar.set_database_connected(self.dao.test_connection())
        else:
            self.status_bar.set_database_connected(False)
    
    def _refresh_spiders(self):
        """刷新爬虫列表"""
        try:
            from app.spiders_registry import reload_spiders, get_all_spiders
            reload_spiders()
            spiders = get_all_spiders()
            self.sidebar.update_spiders(spiders)
            self.logger.info(f"刷新爬虫列表: 找到 {len(spiders)} 个爬虫")
        except Exception as e:
            self.logger.error(f"刷新爬虫列表失败: {e}")
            self._show_error("刷新爬虫列表失败", str(e))
    
    def _refresh_data(self):
        """刷新数据（统计和日志）"""
        if not self.dao:
            return
        
        try:
            # 获取筛选条件
            filter_conditions = self.log_view.get_current_filter()
            # 防护：确保filter_conditions不为None
            if filter_conditions is None:
                filter_conditions = {'task_id': None, 'limit': 100}
            
            task_id = self.control_panel.get_task_id_filter()
            
            if task_id is not None:
                filter_conditions['task_id'] = task_id
            
            # 刷新统计计数
            counts = self.dao.get_counts(filter_conditions.get('task_id'))
            # 防护：确保counts不为None
            if counts is None:
                counts = {'found': 0, 'none': 0, 'fail': 0, 'total_logs': 0, 'running': 0, 'pending': 0, 'total_tasks': 0}
            self.status_bar.update_counts(counts)
            
            # 刷新日志（如果启用自动刷新）
            if self.log_view.is_auto_refresh_enabled():
                # 确保limit存在且有效
                limit = filter_conditions.get('limit', 100)
                if limit is None:
                    limit = 100
                    
                logs = self.dao.get_recent_logs(
                    limit,
                    filter_conditions.get('task_id')
                )
                # 防护：确保logs不为None
                if logs is None:
                    logs = []
                self.log_view.update_logs(logs)
            
        except Exception as e:
            self.logger.error(f"刷新数据失败: {e}")
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
    
    def _refresh_logs(self):
        """手动刷新日志"""
        if not self.dao:
            return
        
        try:
            filter_conditions = self.log_view.get_current_filter()
            # 防护：确保filter_conditions不为None
            if filter_conditions is None:
                filter_conditions = {'task_id': None, 'limit': 100}
                
            task_id = self.control_panel.get_task_id_filter()
            
            if task_id is not None:
                filter_conditions['task_id'] = task_id
            
            # 确保limit存在且有效
            limit = filter_conditions.get('limit', 100)
            if limit is None:
                limit = 100
                
            logs = self.dao.get_recent_logs(
                limit,
                filter_conditions.get('task_id')
            )
            # 防护：确保logs不为None
            if logs is None:
                logs = []
            self.log_view.update_logs(logs)
            self.logger.info(f"手动刷新日志: 获取到 {len(logs)} 条记录")
            
        except Exception as e:
            self.logger.error(f"刷新日志失败: {e}")
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
            self._show_error("刷新日志失败", str(e))
    
    def _test_database_connection(self):
        """测试数据库连接"""
        if self.dao:
            connected = self.dao.test_connection()
            self.status_bar.set_database_connected(connected)
            
            if connected:
                QMessageBox.information(self, "数据库连接", "数据库连接正常！")
            else:
                QMessageBox.warning(self, "数据库连接", "数据库连接失败，请检查配置！")
        else:
            self.status_bar.set_database_connected(False)
            QMessageBox.critical(self, "数据库连接", "数据库未初始化！")
    
    def _on_spider_selected(self, spider: SpiderMeta):
        """处理爬虫选择"""
        self.control_panel.set_spider(spider)
        self.logger.info(f"选择爬虫: {spider.name}")
    
    def _start_spider(self, spider: SpiderMeta, args: list):
        """启动爬虫"""
        try:
            # 停止当前运行的爬虫（如果有）
            if self.current_process and subprocess_manager.is_running(self.current_process):
                self._stop_spider()
            
            self.logger.info(f"启动爬虫: {spider.name}, 参数: {args}")
            
            # 启动新的爬虫进程
            self.current_process = subprocess_manager.start_spider(spider.entry, args)
            
            if self.current_process:
                self.control_panel.set_running_state(True)
                self.logger.info(f"爬虫启动成功: PID {self.current_process.pid}")
                QMessageBox.information(self, "爬虫启动", 
                                      f"爬虫 {spider.name} 启动成功！\nPID: {self.current_process.pid}")
            else:
                self.logger.error("爬虫启动失败")
                QMessageBox.warning(self, "爬虫启动", "爬虫启动失败，请检查配置！")
                
        except Exception as e:
            self.logger.error(f"启动爬虫失败: {e}")
            self._show_error("启动爬虫失败", str(e))
    
    def _stop_spider(self):
        """停止爬虫"""
        try:
            if self.current_process and subprocess_manager.is_running(self.current_process):
                pid = self.current_process.pid
                success = subprocess_manager.stop_spider(self.current_process)
                
                if success:
                    self.logger.info(f"爬虫停止成功: PID {pid}")
                    QMessageBox.information(self, "爬虫停止", f"爬虫已成功停止！")
                else:
                    self.logger.warning(f"爬虫停止失败: PID {pid}")
                    QMessageBox.warning(self, "爬虫停止", "爬虫停止失败！")
                
                self.current_process = None
                self.control_panel.set_running_state(False)
            else:
                QMessageBox.information(self, "爬虫停止", "没有正在运行的爬虫！")
                
        except Exception as e:
            self.logger.error(f"停止爬虫失败: {e}")
            self._show_error("停止爬虫失败", str(e))
    
    def _show_error(self, title: str, message: str):
        """显示错误消息"""
        QMessageBox.critical(self, title, message)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 检查是否有正在运行的进程
        running_processes = subprocess_manager.get_running_processes()
        
        if running_processes:
            reply = QMessageBox.question(
                self, "确认退出",
                f"当前有 {len(running_processes)} 个爬虫进程正在运行，确定要退出吗？\n"
                "退出将会停止所有正在运行的爬虫。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # 停止所有进程
                stopped_count = subprocess_manager.stop_all_processes()
                self.logger.info(f"退出时停止了 {stopped_count} 个进程")
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()