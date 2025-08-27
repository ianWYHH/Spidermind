"""
GitHub README 联系方式爬虫 - Manifest 配置
"""

METADATA = {
    "id": "github_readme",
    "name": "GitHub README 联系方式爬虫",
    "desc": "从 crawl_tasks(source=github) 读取任务并按 github_login 爬取联系方式",
    "entry": "spiders.github_readme.runner",
    "default_args": {
        "timeout": 10,
        "retries": 2,
        "threads": 1,
        "use_selenium": False
    }
}