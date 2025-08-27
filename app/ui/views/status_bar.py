"""
状态栏组件 - 显示统计信息和状态
"""
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QFrame, 
                               QProgressBar, QPushButton)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap

from typing import Dict


class StatusIndicator(QFrame):
    """状态指示器组件"""
    
    def __init__(self, label: str, color: str = "#666"):
        super().__init__()
        self.setObjectName("status-indicator")
        self.setFrameStyle(QFrame.StyledPanel)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        
        # 标签
        self.label = QLabel(label)
        self.label.setObjectName("status-label")
        font = QFont()
        font.setPointSize(9)
        self.label.setFont(font)
        
        # 数值
        self.value_label = QLabel("0")
        self.value_label.setObjectName("status-value")
        self.value_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.value_label.setFont(font)
        
        layout.addWidget(self.label)
        layout.addWidget(self.value_label)
        
        self.setLayout(layout)
    
    def set_value(self, value: int):
        """设置数值"""
        self.value_label.setText(str(value))


class DatabaseStatus(QFrame):
    """数据库连接状态"""
    
    def __init__(self):
        super().__init__()
        self.setObjectName("database-status")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        
        # 图标/指示灯
        self.indicator = QLabel("●")
        self.indicator.setObjectName("db-indicator")
        font = QFont()
        font.setPointSize(12)
        self.indicator.setFont(font)
        
        # 状态文本
        self.status_label = QLabel("数据库连接")
        self.status_label.setObjectName("db-status-label")
        font = QFont()
        font.setPointSize(9)
        self.status_label.setFont(font)
        
        layout.addWidget(self.indicator)
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
        self.set_connected(False)
    
    def set_connected(self, connected: bool):
        """设置连接状态"""
        if connected:
            self.indicator.setStyleSheet("color: #4CAF50;")  # 绿色
            self.status_label.setText("数据库已连接")
        else:
            self.indicator.setStyleSheet("color: #F44336;")  # 红色
            self.status_label.setText("数据库断开")


class StatusBar(QWidget):
    """状态栏"""
    
    # 信号
    database_check_requested = Signal()
    
    def __init__(self):
        super().__init__()
        self.last_update_time = None
        self._setup_ui()
        self._setup_timer()
    
    def _setup_ui(self):
        """设置UI"""
        self.setObjectName("status-bar")
        self.setMaximumHeight(40)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)
        
        # 数据库状态
        self.db_status = DatabaseStatus()
        layout.addWidget(self.db_status)
        
        # 分隔线
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.VLine)
        separator1.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator1)
        
        # 统计指示器
        self.found_indicator = StatusIndicator("成功找到", "#4CAF50")
        layout.addWidget(self.found_indicator)
        
        self.none_indicator = StatusIndicator("成功但无内容", "#FF9800")
        layout.addWidget(self.none_indicator)
        
        self.fail_indicator = StatusIndicator("失败", "#F44336")
        layout.addWidget(self.fail_indicator)
        
        # 分隔线
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator2)
        
        # 任务状态
        self.running_indicator = StatusIndicator("运行中", "#2196F3")
        layout.addWidget(self.running_indicator)
        
        self.pending_indicator = StatusIndicator("待处理", "#9C27B0")
        layout.addWidget(self.pending_indicator)
        
        # 弹性空间
        layout.addStretch()
        
        # 分隔线
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.VLine)
        separator3.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator3)
        
        # 最后更新时间
        self.update_time_label = QLabel("未更新")
        self.update_time_label.setObjectName("update-time")
        font = QFont()
        font.setPointSize(8)
        self.update_time_label.setFont(font)
        self.update_time_label.setStyleSheet("color: #666;")
        layout.addWidget(self.update_time_label)
        
        # 数据库测试按钮
        test_db_btn = QPushButton("测试连接")
        test_db_btn.setObjectName("test-db-button")
        test_db_btn.setMaximumHeight(24)
        test_db_btn.clicked.connect(self.database_check_requested.emit)
        layout.addWidget(test_db_btn)
        
        self.setLayout(layout)
    
    def _setup_timer(self):
        """设置更新时间显示的定时器"""
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self._update_time_display)
        self.time_timer.start(1000)  # 每秒更新一次
    
    def update_counts(self, counts: Dict[str, int]):
        """更新统计计数"""
        self.found_indicator.set_value(counts.get('found', 0))
        self.none_indicator.set_value(counts.get('none', 0))
        self.fail_indicator.set_value(counts.get('fail', 0))
        self.running_indicator.set_value(counts.get('running', 0))
        self.pending_indicator.set_value(counts.get('pending', 0))
        
        # 更新最后更新时间
        from datetime import datetime
        self.last_update_time = datetime.now()
    
    def set_database_connected(self, connected: bool):
        """设置数据库连接状态"""
        self.db_status.set_connected(connected)
    
    def _update_time_display(self):
        """更新时间显示"""
        if self.last_update_time:
            from datetime import datetime
            now = datetime.now()
            delta = now - self.last_update_time
            
            if delta.total_seconds() < 60:
                self.update_time_label.setText(f"{int(delta.total_seconds())}秒前")
            elif delta.total_seconds() < 3600:
                self.update_time_label.setText(f"{int(delta.total_seconds() / 60)}分钟前")
            else:
                self.update_time_label.setText(self.last_update_time.strftime("%H:%M:%S"))
        else:
            self.update_time_label.setText("未更新")
    
    def show_message(self, message: str, duration: int = 3000):
        """显示临时消息"""
        # 可以扩展为显示临时状态消息
        pass