"""
爬虫注册中心 - 管理所有可用的爬虫及其配置

## 如何新增一个爬虫入口

1. **复制模板**: 复制 `spiders/template_minimal/` 目录到新的爬虫目录
   ```bash
   cp -r spiders/template_minimal spiders/your_spider_name
   ```

2. **修改 manifest**: 编辑 `spiders/your_spider_name/manifest.py`
   - 修改 METADATA 中的 id, name, desc, entry 字段
   - 根据需要调整 default_args

3. **在此文件中注册**: 在下面的 `_import_manifests()` 函数中添加导入语句
   ```python
   from spiders.your_spider_name.manifest import METADATA as your_spider_metadata
   ```
   然后在 manifests 列表中添加该 metadata

4. **实现 runner**: 在 `spiders/your_spider_name/runner.py` 中实现具体的爬虫逻辑

注意：所有 manifest 必须包含完整的字段，否则会在启动时抛出 ValueError
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Union
import logging


logger = logging.getLogger(__name__)


@dataclass
class SpiderMeta:
    """爬虫元数据"""
    id: str                           # 爬虫唯一标识
    name: str                         # 显示名称
    desc: str                         # 描述信息
    entry: str                        # 入口模块路径
    default_args: Union[Dict, List]   # 默认参数


def _validate_metadata(metadata: Dict[str, Any], source_name: str) -> None:
    """
    验证 manifest METADATA 的字段完整性
    
    Args:
        metadata: 从 manifest 导入的 METADATA 字典
        source_name: 来源名称，用于错误提示
        
    Raises:
        ValueError: 当字段缺失或类型不正确时
    """
    required_fields = ["id", "name", "desc", "entry", "default_args"]
    
    for field in required_fields:
        if field not in metadata:
            raise ValueError(f"爬虫 {source_name} 的 manifest 缺少必需字段: {field}")
    
    # 验证字段类型
    if not isinstance(metadata["id"], str) or not metadata["id"].strip():
        raise ValueError(f"爬虫 {source_name} 的 id 字段必须是非空字符串")
    
    if not isinstance(metadata["name"], str) or not metadata["name"].strip():
        raise ValueError(f"爬虫 {source_name} 的 name 字段必须是非空字符串")
    
    if not isinstance(metadata["desc"], str):
        raise ValueError(f"爬虫 {source_name} 的 desc 字段必须是字符串")
    
    if not isinstance(metadata["entry"], str) or not metadata["entry"].strip():
        raise ValueError(f"爬虫 {source_name} 的 entry 字段必须是非空字符串")
    
    if not isinstance(metadata["default_args"], (dict, list)):
        raise ValueError(f"爬虫 {source_name} 的 default_args 字段必须是字典或列表")


def _import_manifests() -> List[Dict[str, Any]]:
    """
    导入所有爬虫的 manifest 配置
    
    新增爬虫时，在此函数中添加相应的 import 语句和 manifests 列表项
    
    Returns:
        List[Dict[str, Any]]: 所有有效的 manifest 数据列表
        
    Raises:
        ValueError: 当任何 manifest 字段不完整时
    """
    manifests = []
    
    try:
        # 导入 GitHub README 爬虫
        from spiders.github_readme.manifest import METADATA as github_readme_metadata
        _validate_metadata(github_readme_metadata, "github_readme")
        manifests.append(github_readme_metadata)
        logger.debug("成功加载爬虫: github_readme")
        
    except ImportError as e:
        logger.warning(f"无法导入 github_readme manifest: {e}")
    except ValueError as e:
        logger.error(f"github_readme manifest 验证失败: {e}")
        raise
    
    try:
        # 导入模板爬虫（通常在生产环境中可以注释掉）
        from spiders.template_minimal.manifest import METADATA as template_minimal_metadata
        _validate_metadata(template_minimal_metadata, "template_minimal")
        manifests.append(template_minimal_metadata)
        logger.debug("成功加载爬虫: template_minimal")
        
    except ImportError as e:
        logger.warning(f"无法导入 template_minimal manifest: {e}")
    except ValueError as e:
        logger.error(f"template_minimal manifest 验证失败: {e}")
        raise
    
    # TODO: 新增爬虫时在此处添加导入语句
    # 例如:
    # try:
    #     from spiders.your_spider_name.manifest import METADATA as your_spider_metadata
    #     _validate_metadata(your_spider_metadata, "your_spider_name")
    #     manifests.append(your_spider_metadata)
    #     logger.debug("成功加载爬虫: your_spider_name")
    # except ImportError as e:
    #     logger.warning(f"无法导入 your_spider_name manifest: {e}")
    # except ValueError as e:
    #     logger.error(f"your_spider_name manifest 验证失败: {e}")
    #     raise
    
    if not manifests:
        logger.warning("未找到任何有效的爬虫 manifest")
    else:
        logger.info(f"总共加载了 {len(manifests)} 个爬虫配置")
    
    return manifests


def list_spiders() -> List[SpiderMeta]:
    """
    获取所有已注册的爬虫列表
    
    Returns:
        List[SpiderMeta]: 爬虫元数据列表
        
    Raises:
        ValueError: 当任何爬虫的 manifest 配置不正确时
    """
    manifests = _import_manifests()
    
    spider_metas = []
    spider_ids = set()
    
    for metadata in manifests:
        # 检查 ID 唯一性
        spider_id = metadata["id"]
        if spider_id in spider_ids:
            raise ValueError(f"爬虫 ID 重复: {spider_id}")
        spider_ids.add(spider_id)
        
        # 创建 SpiderMeta 对象
        spider_meta = SpiderMeta(
            id=metadata["id"],
            name=metadata["name"],
            desc=metadata["desc"],
            entry=metadata["entry"],
            default_args=metadata["default_args"]
        )
        
        spider_metas.append(spider_meta)
        logger.debug(f"注册爬虫: {spider_meta.name} (ID: {spider_meta.id})")
    
    # 按名称排序
    spider_metas.sort(key=lambda x: x.name)
    
    return spider_metas


def get_spider_by_id(spider_id: str) -> SpiderMeta:
    """
    根据 ID 获取特定的爬虫配置
    
    Args:
        spider_id: 爬虫唯一标识
        
    Returns:
        SpiderMeta: 爬虫元数据
        
    Raises:
        ValueError: 当找不到指定 ID 的爬虫时
    """
    spiders = list_spiders()
    
    for spider in spiders:
        if spider.id == spider_id:
            return spider
    
    available_ids = [s.id for s in spiders]
    raise ValueError(f"未找到 ID 为 '{spider_id}' 的爬虫。可用的爬虫 ID: {available_ids}")


def reload_spiders() -> None:
    """
    重新加载爬虫配置 (与 list_spiders 等价的别名，便于 GUI 调用)
    
    此函数主要为了兼容 GUI 调用，实际上爬虫配置是动态导入的，
    无需显式重新加载，但提供此接口保持 API 一致性。
    """
    # 爬虫配置是通过动态导入实现的，每次调用 list_spiders() 都会重新导入
    # 这里可以执行一些缓存清理或其他重加载逻辑，目前保持空实现
    logger.debug("重新加载爬虫配置（动态导入，无需显式重加载）")


def get_all_spiders() -> List[SpiderMeta]:
    """
    获取所有爬虫列表 (与 list_spiders 等价的别名，便于 GUI 调用)
    
    Returns:
        List[SpiderMeta]: 爬虫元数据列表
        
    Raises:
        ValueError: 当任何爬虫的 manifest 配置不正确时
    """
    return list_spiders()


# 便于测试和调试的函数
def _debug_print_spiders():
    """调试函数：打印所有已注册的爬虫信息"""
    try:
        spiders = list_spiders()
        print(f"\n=== 已注册的爬虫 ({len(spiders)} 个) ===")
        for spider in spiders:
            print(f"ID: {spider.id}")
            print(f"名称: {spider.name}")
            print(f"描述: {spider.desc}")
            print(f"入口: {spider.entry}")
            print(f"默认参数: {spider.default_args}")
            print("-" * 50)
    except Exception as e:
        print(f"错误: {e}")


if __name__ == "__main__":
    # 测试模式：直接运行此文件可以查看所有注册的爬虫
    logging.basicConfig(level=logging.DEBUG)
    _debug_print_spiders()