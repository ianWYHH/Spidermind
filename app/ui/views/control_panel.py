"""
控制面板组件 - 显示爬虫参数和控制按钮
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton,
                               QTextEdit, QFrame, QGridLayout, QComboBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from app.spiders_registry import SpiderMeta


class ParameterWidget(QFrame):
    """参数配置组件"""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.spider = None
    
    def _setup_ui(self):
        """设置UI"""
        self.setObjectName("parameter-widget")
        self.setFrameStyle(QFrame.StyledPanel)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        
        # 标题
        title = QLabel("参数配置")
        title.setObjectName("parameter-title")
        font = QFont()
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        # 参数表单
        form_layout = QGridLayout()
        form_layout.setSpacing(8)
        
        # 超时时间
        form_layout.addWidget(QLabel("超时时间(秒):"), 0, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 300)
        self.timeout_spin.setValue(30)
        form_layout.addWidget(self.timeout_spin, 0, 1)
        
        # 重试次数
        form_layout.addWidget(QLabel("重试次数:"), 1, 0)
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(3)
        form_layout.addWidget(self.retries_spin, 1, 1)
        
        # 工作线程数
        form_layout.addWidget(QLabel("工作线程数:"), 2, 0)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 8)
        self.threads_spin.setValue(1)
        form_layout.addWidget(self.threads_spin, 2, 1)
        
        # 启用Selenium
        self.selenium_check = QCheckBox("启用 Selenium 浏览器")
        form_layout.addWidget(self.selenium_check, 3, 0, 1, 2)
        
        # 仓库有效性检查
        self.repo_validation_check = QCheckBox("启用仓库有效性检查")
        self.repo_validation_check.setChecked(True)  # 默认启用
        self.repo_validation_check.setToolTip("预检查GitHub仓库是否存在，跳过无效仓库以提升效率")
        form_layout.addWidget(self.repo_validation_check, 4, 0, 1, 2)
        
        # 任务ID筛选
        form_layout.addWidget(QLabel("任务ID筛选:"), 5, 0)
        self.task_id_edit = QLineEdit()
        self.task_id_edit.setPlaceholderText("留空表示全部任务")
        form_layout.addWidget(self.task_id_edit, 5, 1)
        
        layout.addLayout(form_layout)
        
        # 自定义参数
        layout.addWidget(QLabel("自定义参数:"))
        self.custom_args_edit = QLineEdit()
        self.custom_args_edit.setPlaceholderText("例如: --verbose --output /tmp")
        layout.addWidget(self.custom_args_edit)
        
        self.setLayout(layout)
    
    def set_spider(self, spider: SpiderMeta):
        """设置当前爬虫并应用默认参数"""
        self.spider = spider
        
        # 解析默认参数
        args = spider.default_args
        for i, arg in enumerate(args):
            if arg == '--timeout' and i + 1 < len(args):
                try:
                    self.timeout_spin.setValue(int(args[i + 1]))
                except ValueError:
                    pass
            elif arg == '--retries' and i + 1 < len(args):
                try:
                    self.retries_spin.setValue(int(args[i + 1]))
                except ValueError:
                    pass
            elif arg == '--threads' and i + 1 < len(args):
                try:
                    self.threads_spin.setValue(int(args[i + 1]))
                except ValueError:
                    pass
            elif arg == '--enable-selenium':
                self.selenium_check.setChecked(True)
    
    def get_args(self):
        """获取当前配置的参数列表"""
        args = []
        
        # 添加基本参数
        args.extend(['--timeout', str(self.timeout_spin.value())])
        args.extend(['--retries', str(self.retries_spin.value())])
        args.extend(['--threads', str(self.threads_spin.value())])
        
        if self.selenium_check.isChecked():
            args.append('--enable-selenium')
        
        if not self.repo_validation_check.isChecked():
            args.append('--disable-repo-validation')
        
        # 添加自定义参数
        custom_args = self.custom_args_edit.text().strip()
        if custom_args:
            args.extend(custom_args.split())
        
        return args
    
    def get_task_id_filter(self):
        """获取任务ID筛选"""
        task_id_text = self.task_id_edit.text().strip()
        if task_id_text:
            try:
                return int(task_id_text)
            except ValueError:
                return None
        return None


class ControlPanel(QWidget):
    """控制面板"""
    
    # 信号
    start_spider = Signal(SpiderMeta, list)  # 启动爬虫 (spider, args)
    stop_spider = Signal()                   # 停止爬虫
    
    def __init__(self):
        super().__init__()
        self.current_spider = None
        self.is_running = False
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        self.setObjectName("control-panel")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 爬虫信息区域
        self.info_widget = self._create_info_widget()
        layout.addWidget(self.info_widget)
        
        # 参数配置区域
        self.param_widget = ParameterWidget()
        layout.addWidget(self.param_widget)
        
        # 控制按钮区域
        self.control_widget = self._create_control_widget()
        layout.addWidget(self.control_widget)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def _create_info_widget(self) -> QWidget:
        """创建爬虫信息显示区域"""
        widget = QFrame()
        widget.setObjectName("spider-info")
        widget.setFrameStyle(QFrame.StyledPanel)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        
        # 标题
        self.title_label = QLabel("请选择爬虫")
        self.title_label.setObjectName("spider-info-title")
        font = QFont()
        font.setBold(True)
        font.setPointSize(14)
        self.title_label.setFont(font)
        
        # 描述
        self.desc_label = QLabel("暂无选中的爬虫")
        self.desc_label.setObjectName("spider-info-desc")
        self.desc_label.setWordWrap(True)
        
        # 详细信息
        self.details_edit = QTextEdit()
        self.details_edit.setObjectName("spider-info-details")
        self.details_edit.setMaximumHeight(80)
        self.details_edit.setReadOnly(True)
        
        layout.addWidget(self.title_label)
        layout.addWidget(self.desc_label)
        layout.addWidget(self.details_edit)
        
        widget.setLayout(layout)
        return widget
    
    def _create_control_widget(self) -> QWidget:
        """创建控制按钮区域"""
        widget = QFrame()
        widget.setObjectName("control-buttons")
        widget.setFrameStyle(QFrame.StyledPanel)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        
        # 启动按钮
        self.start_btn = QPushButton("启动爬虫")
        self.start_btn.setObjectName("start-button")
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.start_btn.setEnabled(False)
        
        # 停止按钮
        self.stop_btn = QPushButton("停止爬虫")
        self.stop_btn.setObjectName("stop-button")
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.stop_btn.setEnabled(False)
        
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
    
    def set_spider(self, spider: SpiderMeta):
        """设置当前爬虫"""
        self.current_spider = spider
        
        # 更新信息显示
        self.title_label.setText(spider.name)
        self.desc_label.setText(spider.desc)
        
        # 显示详细信息
        details = []
        details.append(f"ID: {spider.id}")
        details.append(f"入口: {spider.entry}")
        details.append(f"来源类型: {self._get_spider_type(spider.id)}")
        details.append(f"默认参数: {' '.join(spider.default_args)}")
        self.details_edit.setText('\n'.join(details))
        
        # 设置参数
        self.param_widget.set_spider(spider)
        
        # 启用开始按钮
        self.start_btn.setEnabled(True)
    
    def set_running_state(self, is_running: bool):
        """设置运行状态"""
        self.is_running = is_running
        self.start_btn.setEnabled(not is_running and self.current_spider is not None)
        self.stop_btn.setEnabled(is_running)
        
        if is_running:
            self.start_btn.setText("运行中...")
        else:
            self.start_btn.setText("启动爬虫")
    
    def _on_start_clicked(self):
        """处理启动按钮点击"""
        if self.current_spider:
            args = self.param_widget.get_args()
            self.start_spider.emit(self.current_spider, args)
    
    def _on_stop_clicked(self):
        """处理停止按钮点击"""
        self.stop_spider.emit()
    
    def get_task_id_filter(self):
        """获取任务ID筛选条件"""
        return self.param_widget.get_task_id_filter()
    
    def _get_spider_type(self, spider_id: str) -> str:
        """根据爬虫ID推断类型"""
        type_mapping = {
            'github_readme': 'GitHub',
            'github': 'GitHub', 
            'openreview': 'OpenReview',
            'homepage': '主页爬虫',
            'template_minimal': '模板'
        }
        return type_mapping.get(spider_id, '未知类型')