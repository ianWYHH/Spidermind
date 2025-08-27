"""
侧边栏组件 - 显示爬虫列表
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                               QListWidgetItem, QPushButton, QLabel, QFrame)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from app.spiders_registry import SpiderMeta


class SpiderListItem(QFrame):
    """爬虫列表项组件"""
    
    def __init__(self, spider: SpiderMeta):
        super().__init__()
        self.spider = spider
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        self.setObjectName("spider-list-item")
        self.setFrameStyle(QFrame.Box)
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        
        # 爬虫名称
        name_label = QLabel(self.spider.name)
        name_label.setObjectName("spider-name")
        font = QFont()
        font.setBold(True)
        name_label.setFont(font)
        
        # 爬虫描述
        desc_label = QLabel(self.spider.desc)
        desc_label.setObjectName("spider-description")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignTop)
        
        # 来源类型标签（基于ID推断）
        source_type = self._get_spider_type(self.spider.id)
        source_label = QLabel(f"类型: {source_type}")
        source_label.setObjectName("spider-source")
        
        layout.addWidget(name_label)
        layout.addWidget(desc_label)
        layout.addWidget(source_label)
        
        self.setLayout(layout)
    
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


class Sidebar(QWidget):
    """侧边栏组件"""
    
    # 信号
    spider_selected = Signal(SpiderMeta)  # 爬虫被选中
    refresh_requested = Signal()           # 请求刷新
    
    def __init__(self):
        super().__init__()
        self.spiders = []
        self.current_spider = None
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        self.setObjectName("sidebar")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏
        header = self._create_header()
        layout.addWidget(header)
        
        # 爬虫列表
        self.spider_list = QListWidget()
        self.spider_list.setObjectName("spider-list")
        self.spider_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.spider_list)
        
        # 底部按钮
        footer = self._create_footer()
        layout.addWidget(footer)
        
        self.setLayout(layout)
    
    def _create_header(self) -> QWidget:
        """创建标题栏"""
        header = QFrame()
        header.setObjectName("sidebar-header")
        header.setFrameStyle(QFrame.StyledPanel)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        
        title = QLabel("可用爬虫")
        title.setObjectName("sidebar-title")
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        title.setFont(font)
        
        layout.addWidget(title)
        header.setLayout(layout)
        
        return header
    
    def _create_footer(self) -> QWidget:
        """创建底部按钮区域"""
        footer = QFrame()
        footer.setObjectName("sidebar-footer")
        footer.setFrameStyle(QFrame.StyledPanel)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("refresh-button")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        
        layout.addWidget(refresh_btn)
        layout.addStretch()
        
        footer.setLayout(layout)
        return footer
    
    def update_spiders(self, spiders):
        """更新爬虫列表"""
        self.spiders = spiders
        self._refresh_list()
    
    def _refresh_list(self):
        """刷新列表显示"""
        self.spider_list.clear()
        
        for spider in self.spiders:
            # 创建自定义的列表项
            item = QListWidgetItem()
            item.setData(Qt.UserRole, spider)
            
            # 创建自定义widget
            item_widget = SpiderListItem(spider)
            
            # 设置项的大小
            item.setSizeHint(item_widget.sizeHint())
            
            # 添加到列表
            self.spider_list.addItem(item)
            self.spider_list.setItemWidget(item, item_widget)
    
    def _on_item_clicked(self, item):
        """处理列表项点击"""
        spider = item.data(Qt.UserRole)
        if spider:
            self.current_spider = spider
            self.spider_selected.emit(spider)
            
            # 更新选中状态的视觉效果
            for i in range(self.spider_list.count()):
                list_item = self.spider_list.item(i)
                widget = self.spider_list.itemWidget(list_item)
                if widget:
                    if list_item == item:
                        widget.setProperty("selected", True)
                    else:
                        widget.setProperty("selected", False)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
    
    def get_selected_spider(self) -> SpiderMeta:
        """获取当前选中的爬虫"""
        return self.current_spider
    
    def select_spider_by_id(self, spider_id: str):
        """根据ID选中爬虫"""
        for i in range(self.spider_list.count()):
            item = self.spider_list.item(i)
            spider = item.data(Qt.UserRole)
            if spider and spider.id == spider_id:
                self.spider_list.setCurrentItem(item)
                self._on_item_clicked(item)
                break