"""
日志视图组件 - 显示爬虫日志
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                               QTableWidgetItem, QHeaderView, QPushButton, QLabel,
                               QFrame, QComboBox, QSpinBox, QCheckBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from datetime import datetime
from typing import List, Dict, Any, Optional


class LogTableWidget(QTableWidget):
    """日志表格组件"""
    
    def __init__(self):
        super().__init__()
        self._setup_table()
    
    def _setup_table(self):
        """设置表格"""
        # 设置列
        columns = ["时间", "任务ID", "来源", "类型", "URL", "状态", "消息"]
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        
        # 设置表格属性
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # 设置列宽
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)      # 时间
        header.setSectionResizeMode(1, QHeaderView.Fixed)      # 任务ID
        header.setSectionResizeMode(2, QHeaderView.Fixed)      # 来源
        header.setSectionResizeMode(3, QHeaderView.Fixed)      # 类型
        header.setSectionResizeMode(4, QHeaderView.Stretch)    # URL
        header.setSectionResizeMode(5, QHeaderView.Fixed)      # 状态
        header.setSectionResizeMode(6, QHeaderView.Stretch)    # 消息
        
        self.setColumnWidth(0, 120)  # 时间
        self.setColumnWidth(1, 80)   # 任务ID
        self.setColumnWidth(2, 80)   # 来源
        self.setColumnWidth(3, 80)   # 类型
        self.setColumnWidth(5, 80)   # 状态
    
    def update_logs(self, logs: List[Dict[str, Any]]):
        """更新日志显示"""
        # 防护：确保logs不为None
        if logs is None:
            logs = []
        
        self.setRowCount(len(logs))
        
        for row, log in enumerate(logs):
            # 时间
            created_at = log.get('created_at', '')
            if isinstance(created_at, datetime):
                time_str = created_at.strftime('%H:%M:%S')
            else:
                time_str = str(created_at)[:8] if created_at else ''
            
            self.setItem(row, 0, QTableWidgetItem(time_str))
            
            # 任务ID
            task_id = str(log.get('task_id', ''))
            self.setItem(row, 1, QTableWidgetItem(task_id))
            
            # 来源
            source = log.get('source', '')
            self.setItem(row, 2, QTableWidgetItem(source))
            
            # 类型
            task_type = log.get('task_type', '') or ''  # 防护：确保task_type不为None
            self.setItem(row, 3, QTableWidgetItem(task_type))
            
            # URL
            url = log.get('url', '') or ''  # 防护：确保url不为None
            if len(url) > 50:
                url = url[:47] + '...'
            self.setItem(row, 4, QTableWidgetItem(url))
            
            # 状态
            status = log.get('status', '') or ''  # 防护：确保status不为None
            status_item = QTableWidgetItem(status)
            
            # 根据状态设置颜色
            if status == 'success':
                status_item.setBackground(QColor(200, 255, 200))  # 淡绿色
            elif status == 'fail':
                status_item.setBackground(QColor(255, 200, 200))  # 淡红色
            elif status == 'skip':
                status_item.setBackground(QColor(255, 255, 200))  # 淡黄色
            
            self.setItem(row, 5, status_item)
            
            # 消息
            message = log.get('message', '') or ''  # 防护：确保message不为None
            if len(message) > 100:
                message = message[:97] + '...'
            self.setItem(row, 6, QTableWidgetItem(message))
        
        # 滚动到最新日志
        if logs:
            self.scrollToTop()


class LogView(QWidget):
    """日志视图"""
    
    # 信号
    refresh_requested = Signal()
    
    def __init__(self):
        super().__init__()
        self.current_task_id = None
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        self.setObjectName("log-view")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 控制栏
        control_bar = self._create_control_bar()
        layout.addWidget(control_bar)
        
        # 日志表格
        self.log_table = LogTableWidget()
        layout.addWidget(self.log_table)
        
        self.setLayout(layout)
    
    def _create_control_bar(self) -> QWidget:
        """创建控制栏"""
        widget = QFrame()
        widget.setObjectName("log-control-bar")
        widget.setFrameStyle(QFrame.StyledPanel)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 标题
        title = QLabel("日志记录")
        title.setObjectName("log-title")
        font = QFont()
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        layout.addStretch()
        
        # 显示条数
        layout.addWidget(QLabel("显示:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 1000)
        self.limit_spin.setValue(100)
        self.limit_spin.setSuffix(" 条")
        layout.addWidget(self.limit_spin)
        
        # 任务ID筛选
        layout.addWidget(QLabel("任务ID:"))
        self.task_filter_combo = QComboBox()
        self.task_filter_combo.setEditable(True)
        self.task_filter_combo.addItem("全部", None)
        self.task_filter_combo.setMinimumWidth(100)
        layout.addWidget(self.task_filter_combo)
        
        # 自动刷新
        self.auto_refresh_check = QCheckBox("自动刷新")
        self.auto_refresh_check.setChecked(True)
        layout.addWidget(self.auto_refresh_check)
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("log-refresh-button")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh_btn)
        
        # 清空按钮
        clear_btn = QPushButton("清空显示")
        clear_btn.setObjectName("log-clear-button")
        clear_btn.clicked.connect(self._clear_logs)
        layout.addWidget(clear_btn)
        
        widget.setLayout(layout)
        return widget
    
    def update_logs(self, logs: List[Dict[str, Any]]):
        """更新日志显示"""
        # 防护：确保logs不为None
        if logs is None:
            logs = []
        self.log_table.update_logs(logs)
    
    def set_task_id_filter(self, task_id: Optional[int]):
        """设置任务ID筛选"""
        self.current_task_id = task_id
        
        # 更新下拉框
        current_text = str(task_id) if task_id else "全部"
        index = self.task_filter_combo.findText(current_text)
        if index >= 0:
            self.task_filter_combo.setCurrentIndex(index)
        else:
            self.task_filter_combo.setEditText(current_text)
    
    def get_current_filter(self) -> Dict[str, Any]:
        """获取当前筛选条件"""
        # 获取任务ID
        task_id = None
        current_text = self.task_filter_combo.currentText().strip()
        if current_text and current_text != "全部":
            try:
                task_id = int(current_text)
            except ValueError:
                pass
        
        return {
            'task_id': task_id,
            'limit': self.limit_spin.value()
        }
    
    def is_auto_refresh_enabled(self) -> bool:
        """是否启用自动刷新"""
        return self.auto_refresh_check.isChecked()
    
    def _clear_logs(self):
        """清空日志显示"""
        self.log_table.setRowCount(0)
    
    def add_task_to_filter(self, task_id: int):
        """添加任务ID到筛选下拉框"""
        task_id_str = str(task_id)
        if self.task_filter_combo.findText(task_id_str) < 0:
            self.task_filter_combo.addItem(task_id_str, task_id)