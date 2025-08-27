# 爬虫注册中心使用指南

## 概述

爬虫注册中心提供了统一的爬虫管理机制，通过 manifest 配置文件和注册中心实现爬虫的发现、加载和验证。

## 架构说明

### 核心组件

1. **Manifest 文件** (`spiders/*/manifest.py`)
   - 定义每个爬虫的元数据
   - 包含 ID、名称、描述、入口点和默认参数

2. **注册中心** (`app/spiders_registry.py`)
   - 统一管理所有爬虫
   - 提供验证和查询功能
   - 确保配置的完整性

3. **Runner 模块** (`spiders/*/runner.py`)
   - 实现具体的爬虫逻辑
   - 标准化的命令行接口

## 使用方法

### 1. 查看所有已注册的爬虫

```python
from app.spiders_registry import list_spiders

spiders = list_spiders()
for spider in spiders:
    print(f"ID: {spider.id}, 名称: {spider.name}")
```

### 2. 获取特定爬虫配置

```python
from app.spiders_registry import get_spider_by_id

spider = get_spider_by_id("github_readme")
print(f"入口: {spider.entry}")
print(f"默认参数: {spider.default_args}")
```

### 3. 运行爬虫

```bash
# 使用默认参数
python -m spiders.github_readme.runner

# 使用自定义参数
python -m spiders.github_readme.runner --timeout 60 --verbose
```

## 新增爬虫步骤

### 第1步：复制模板

```bash
cp -r spiders/template_minimal spiders/your_spider_name
```

### 第2步：修改 manifest

编辑 `spiders/your_spider_name/manifest.py`：

```python
METADATA = {
    "id": "your_spider_name",
    "name": "您的爬虫名称",
    "desc": "爬虫功能描述（不超过80字）",
    "entry": "spiders.your_spider_name.runner",
    "default_args": {
        "timeout": 30,
        "retries": 3,
        # 添加其他默认参数
    }
}
```

### 第3步：在注册中心注册

编辑 `app/spiders_registry.py` 的 `_import_manifests()` 函数：

```python
try:
    from spiders.your_spider_name.manifest import METADATA as your_spider_metadata
    _validate_metadata(your_spider_metadata, "your_spider_name")
    manifests.append(your_spider_metadata)
    logger.debug("成功加载爬虫: your_spider_name")
except ImportError as e:
    logger.warning(f"无法导入 your_spider_name manifest: {e}")
except ValueError as e:
    logger.error(f"your_spider_name manifest 验证失败: {e}")
    raise
```

### 第4步：实现 runner

编辑 `spiders/your_spider_name/runner.py`，实现具体的爬虫逻辑。

## 配置字段说明

### METADATA 必需字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 爬虫唯一标识，建议使用下划线命名法 |
| `name` | string | 显示名称，用于界面展示 |
| `desc` | string | 功能描述，不超过80字 |
| `entry` | string | 入口模块路径，格式：`spiders.module.runner` |
| `default_args` | dict/list | 默认参数，建议使用字典格式 |

### default_args 推荐参数

```python
"default_args": {
    "timeout": 30,          # 超时时间（秒）
    "retries": 3,           # 重试次数
    "threads": 1,           # 工作线程数
    "verbose": False,       # 详细输出
    "output_format": "json" # 输出格式
}
```

## 验证机制

注册中心会自动验证：

1. **字段完整性**：确保所有必需字段存在
2. **字段类型**：验证字段类型正确性
3. **ID唯一性**：防止重复的爬虫ID
4. **导入完整性**：确保 manifest 可以正常导入

如果验证失败，会抛出详细的 `ValueError` 异常。

## 调试和测试

### 查看所有注册的爬虫

```bash
python -m app.spiders_registry
```

### 测试特定爬虫

```bash
python -m spiders.github_readme.runner --help
python -m spiders.template_minimal.runner --verbose
```

## 最佳实践

1. **命名规范**：
   - 爬虫 ID 使用下划线分隔的小写字母
   - 目录名与爬虫 ID 保持一致

2. **参数设计**：
   - 提供合理的默认值
   - 使用字典格式的 default_args
   - 参数名使用下划线命名法

3. **错误处理**：
   - 在 runner 中添加完善的错误处理
   - 提供清晰的日志输出
   - 使用适当的退出码

4. **文档完善**：
   - 在 runner 文件顶部添加详细的功能说明
   - 在 manifest 中提供准确的描述
   - 保持代码注释的完整性

## 故障排除

### 常见错误

1. **ImportError**: 检查模块路径是否正确
2. **ValueError**: 检查 manifest 字段是否完整
3. **ID重复**: 确保每个爬虫的 ID 唯一

### 调试步骤

1. 运行注册中心测试：`python -m app.spiders_registry`
2. 检查具体爬虫：`python -m spiders.your_spider.runner --help`
3. 查看详细日志：添加 `--verbose` 参数