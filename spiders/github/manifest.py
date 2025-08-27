"""
GitHub 爬虫配置清单
"""

METADATA = {
    'id': 'github_profile',
    'name': 'GitHub 用户档案爬虫',
    'description': '爬取GitHub用户的基本信息、仓库列表和贡献统计数据',
    'entry': 'spiders.github.runner',
    'default_args': ['--timeout', '30', '--retries', '3'],
    'source_type': 'github',
    'enabled': True,
    'version': '1.0.0',
    'author': 'Spidermind Team',
    'supported_args': [
        {
            'name': '--timeout',
            'type': 'int',
            'default': 30,
            'description': '请求超时时间（秒）'
        },
        {
            'name': '--retries',
            'type': 'int',
            'default': 3,
            'description': '重试次数'
        },
        {
            'name': '--enable-selenium',
            'type': 'bool',
            'default': False,
            'description': '是否启用Selenium浏览器'
        },
        {
            'name': '--threads',
            'type': 'int',
            'default': 1,
            'description': '工作线程数'
        }
    ]
}