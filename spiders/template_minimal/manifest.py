"""
最小爬虫模板 - Manifest 配置
用于快速创建新爬虫的模板，复制此目录并修改相应配置即可
"""

METADATA = {
    "id": "template_minimal",
    "name": "最小爬虫模板",
    "desc": "用于快速创建新爬虫的最小模板，包含标准的配置结构和入口点",
    "entry": "spiders.template_minimal.runner",
    "default_args": {
        "timeout": 30,
        "retries": 3,
        "threads": 1,
        "verbose": False
    }
}