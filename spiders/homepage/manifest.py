"""
个人主页爬虫配置清单
"""

METADATA = {
    'id': 'homepage_crawler',
    'name': '个人主页爬虫',
    'description': '爬取学者的个人主页，提取联系信息、研究方向和发表论文',
    'entry': 'spiders.homepage.runner',
    'default_args': ['--timeout', '60', '--retries', '2', '--enable-selenium'],
    'source_type': 'homepage',
    'enabled': True,
    'version': '1.0.0',
    'author': 'Spidermind Team',
    'supported_args': [
        {
            'name': '--timeout',
            'type': 'int',
            'default': 60,
            'description': '请求超时时间（秒）'
        },
        {
            'name': '--retries',
            'type': 'int',
            'default': 2,
            'description': '重试次数'
        },
        {
            'name': '--enable-selenium',
            'type': 'bool',
            'default': True,
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