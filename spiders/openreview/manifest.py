"""
OpenReview 爬虫配置清单
"""

METADATA = {
    'id': 'openreview_profile',
    'name': 'OpenReview 用户档案爬虫',
    'description': '爬取OpenReview平台的用户信息、论文发表和评审记录',
    'entry': 'spiders.openreview.runner',
    'default_args': ['--timeout', '30', '--retries', '3'],
    'source_type': 'openreview',
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
            'name': '--threads',
            'type': 'int',
            'default': 1,
            'description': '工作线程数'
        }
    ]
}