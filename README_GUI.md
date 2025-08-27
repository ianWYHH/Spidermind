# Spidermind GUI 使用说明

## 概述

Spidermind GUI 是一个基于 PySide6 的爬虫管理界面，提供了可视化的爬虫启动、监控和日志查看功能。

## 功能特性

- **爬虫管理**: 可视化选择和配置不同类型的爬虫
- **参数配置**: 直观的参数设置界面（超时、重试、线程数等）
- **实时监控**: 显示爬虫运行状态和统计信息
- **日志查看**: 实时显示爬虫执行日志
- **数据库集成**: 连接MySQL数据库查看任务和日志数据

## 系统要求

- Python 3.8+
- PySide6
- MySQL数据库
- 已安装的依赖包：mysql-connector-python, requests, bs4, lxml

## 安装和配置

### 1. 安装依赖

```bash
pip install PySide6 mysql-connector-python requests beautifulsoup4 lxml
```

### 2. 配置数据库

编辑 `config.ini` 文件：

```ini
[database]
host = localhost
port = 3306
user = your_username
password = your_password
database = spidermind
charset = utf8mb4
autocommit = true
```

### 3. 启动GUI

```bash
python run_gui.py
# 或直接运行
python app/main_gui.py
```

## 界面说明

### 主界面布局

```
┌─────────────┬─────────────────┬─────────────────┐
│             │                 │                 │
│   侧边栏    │    控制面板     │    日志视图     │
│ (爬虫列表)  │  (参数配置)     │  (实时日志)     │
│             │                 │                 │
├─────────────┴─────────────────┴─────────────────┤
│                 状态栏                          │
│           (统计信息和系统状态)                   │
└─────────────────────────────────────────────────┘
```

### 功能区域

#### 侧边栏 (Sidebar)
- 显示所有可用的爬虫列表
- 每个爬虫显示名称、描述和类型
- 点击选择要使用的爬虫
- 刷新按钮重新加载爬虫配置

#### 控制面板 (Control Panel)
- **爬虫信息**: 显示选中爬虫的详细信息
- **参数配置**:
  - 超时时间（秒）
  - 重试次数
  - 工作线程数
  - 启用Selenium选项
  - 任务ID筛选
  - 自定义参数
- **控制按钮**: 启动/停止爬虫

#### 日志视图 (Log View)
- 实时显示爬虫执行日志
- 支持按任务ID筛选
- 可设置显示条数
- 自动刷新功能
- 手动刷新和清空按钮

#### 状态栏 (Status Bar)
- 数据库连接状态指示器
- 任务统计计数（成功/失败/运行中等）
- 最后更新时间
- 数据库连接测试按钮

## 爬虫配置

### 爬虫注册

爬虫通过 `spiders/*/manifest.py` 文件注册：

```python
METADATA = {
    'id': 'spider_id',
    'name': '爬虫显示名称',
    'description': '爬虫功能描述',
    'entry': 'spiders.module.runner',  # 入口模块
    'default_args': ['--timeout', '30'],
    'source_type': 'github',  # 类型标识
    'enabled': True
}
```

### 爬虫Runner

每个爬虫需要提供一个可执行的runner模块：

```python
#!/usr/bin/env python3
import sys
import argparse

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--retries', type=int, default=3)
    # ... 其他参数
    return parser.parse_args()

def main():
    args = parse_args()
    # 爬虫逻辑
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

## 数据库要求

GUI需要访问以下数据库表：

- `crawl_tasks`: 爬虫任务表
- `crawl_logs`: 爬虫日志表

详细表结构请参考 `Spidermind_数据库表结构文档.md`。

## 使用流程

1. **启动GUI**: 运行 `python run_gui.py`
2. **选择爬虫**: 在左侧列表中点击要使用的爬虫
3. **配置参数**: 在中间面板调整参数设置
4. **启动爬虫**: 点击"启动爬虫"按钮
5. **监控执行**: 在右侧查看实时日志和状态
6. **停止爬虫**: 需要时点击"停止爬虫"按钮

## 注意事项

1. **数据库连接**: 确保数据库配置正确且服务正在运行
2. **爬虫进程**: GUI使用子进程方式运行爬虫，确保爬虫脚本可独立执行
3. **资源清理**: 退出GUI时会自动停止所有正在运行的爬虫进程
4. **日志限制**: 日志视图有数量限制，避免占用过多内存

## 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查 `config.ini` 中的数据库配置
   - 确认MySQL服务正在运行
   - 验证用户权限

2. **爬虫启动失败**
   - 检查爬虫脚本路径是否正确
   - 确认Python环境中有必要的依赖
   - 查看控制台错误信息

3. **界面显示异常**
   - 确认PySide6安装正确
   - 检查系统字体支持
   - 尝试重新启动GUI

### 日志文件

GUI运行时会生成日志文件 `spidermind_gui.log`，包含详细的运行信息和错误记录。

## 扩展开发

### 添加新爬虫

1. 在 `spiders/` 下创建新目录
2. 添加 `manifest.py` 配置文件
3. 实现 `runner.py` 爬虫逻辑
4. 重启GUI或点击刷新按钮

### 自定义UI

- 修改 `app/ui/styles.qss` 调整界面样式
- 扩展各UI组件类添加新功能
- 在主窗口中集成新的组件

## 技术架构

- **UI框架**: PySide6 (Qt for Python)
- **数据库**: MySQL + mysql-connector-python
- **进程管理**: subprocess + threading
- **配置管理**: configparser
- **日志系统**: Python logging

## 版本信息

- 版本: 1.0.0
- 作者: Spidermind Team
- 许可: 根据项目许可证