"""
数据访问对象(DAO) - 用于GUI界面的只读数据查询
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from app.config import mysql_params, mysql_dsn, mask_dsn


class DatabaseDAO:
    """数据库访问对象，专门用于GUI界面的只读查询"""
    
    def __init__(self):
        """初始化数据库连接"""
        self.pool = None
        self.logger = logging.getLogger(__name__)
        self._init_connection_pool()
    
    def _init_connection_pool(self):
        """初始化数据库连接池"""
        try:
            # 使用配置桥获取数据库连接参数
            params = mysql_params()
            
            self.pool = MySQLConnectionPool(
                pool_name="gui_pool",
                pool_size=5,
                pool_reset_session=True,
                host=params["host"],
                port=params["port"],
                user=params["user"],
                password=params["password"],
                database=params["database"],
                charset=params.get("charset", "utf8mb4"),
                autocommit=True
            )
            
            # 初始化成功时打印脱敏的连接信息
            self.logger.info(f"数据库连接池初始化成功，连接: {mask_dsn(mysql_dsn())}")
            
        except Exception as e:
            self.logger.error(f"数据库连接池初始化失败: {e}")
            raise
    
    def _get_connection(self):
        """获取数据库连接"""
        if not self.pool:
            raise Exception("数据库连接池未初始化")
        return self.pool.get_connection()
    
    def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"数据库连接测试失败: {e}")
            return False
    
    def get_recent_logs(self, limit: int = 100, task_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取最近的日志记录
        
        Args:
            limit: 返回记录数量限制
            task_id: 可选的任务ID筛选
            
        Returns:
            日志记录列表
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            if task_id:
                query = """
                SELECT cl.id, cl.task_id, cl.source, cl.task_type, cl.url, 
                       cl.status, cl.message, cl.trace_id, cl.created_at,
                       ct.status as task_status, ct.github_login, ct.openreview_profile_id
                FROM crawl_logs cl
                LEFT JOIN crawl_tasks ct ON cl.task_id = ct.id
                WHERE cl.task_id = %s
                ORDER BY cl.created_at DESC
                LIMIT %s
                """
                cursor.execute(query, (task_id, limit))
            else:
                query = """
                SELECT cl.id, cl.task_id, cl.source, cl.task_type, cl.url, 
                       cl.status, cl.message, cl.trace_id, cl.created_at,
                       ct.status as task_status, ct.github_login, ct.openreview_profile_id
                FROM crawl_logs cl
                LEFT JOIN crawl_tasks ct ON cl.task_id = ct.id
                ORDER BY cl.created_at DESC
                LIMIT %s
                """
                cursor.execute(query, (limit,))
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return results
            
        except Exception as e:
            self.logger.error(f"获取日志记录失败: {e}")
            return []
    
    def get_counts(self, task_id: Optional[int] = None) -> Dict[str, int]:
        """获取任务和日志统计计数
        
        Args:
            task_id: 可选的任务ID筛选
            
        Returns:
            统计计数字典: {found, none, fail, running, total_tasks, pending_tasks}
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 日志状态统计
            if task_id:
                # 按任务ID筛选的日志统计
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN status = 'success' AND message LIKE '%found%' THEN 1 ELSE 0 END) as found,
                        SUM(CASE WHEN status = 'success' AND message NOT LIKE '%found%' THEN 1 ELSE 0 END) as none,
                        SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) as fail,
                        COUNT(*) as total_logs
                    FROM crawl_logs 
                    WHERE task_id = %s
                """, (task_id,))
                
                log_result = cursor.fetchone()
                
                # 任务状态统计
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                        COUNT(*) as total_tasks
                    FROM crawl_tasks 
                    WHERE id = %s
                """, (task_id,))
                
                task_result = cursor.fetchone()
                
            else:
                # 全部日志统计
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN status = 'success' AND message LIKE '%found%' THEN 1 ELSE 0 END) as found,
                        SUM(CASE WHEN status = 'success' AND message NOT LIKE '%found%' THEN 1 ELSE 0 END) as none,
                        SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) as fail,
                        COUNT(*) as total_logs
                    FROM crawl_logs
                """)
                
                log_result = cursor.fetchone()
                
                # 全部任务状态统计
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                        COUNT(*) as total_tasks
                    FROM crawl_tasks
                """)
                
                task_result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return {
                'found': log_result[0] or 0,
                'none': log_result[1] or 0,
                'fail': log_result[2] or 0,
                'total_logs': log_result[3] or 0,
                'running': task_result[0] or 0,
                'pending': task_result[1] or 0,
                'total_tasks': task_result[2] or 0,
            }
            
        except Exception as e:
            self.logger.error(f"获取统计计数失败: {e}")
            return {
                'found': 0, 'none': 0, 'fail': 0, 'total_logs': 0,
                'running': 0, 'pending': 0, 'total_tasks': 0
            }
    
    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """获取正在运行的任务列表"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id, source, type, url, github_login, openreview_profile_id,
                       status, created_at, started_at, batch_id, progress_stage
                FROM crawl_tasks 
                WHERE status IN ('running', 'pending')
                ORDER BY created_at DESC
            """)
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return results
            
        except Exception as e:
            self.logger.error(f"获取活跃任务失败: {e}")
            return []
    
    def get_task_sources(self) -> List[str]:
        """获取所有任务来源类型"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT DISTINCT source FROM crawl_tasks ORDER BY source")
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return [row[0] for row in results]
            
        except Exception as e:
            self.logger.error(f"获取任务来源失败: {e}")
            return []
    
    def fetch_one_pending_task(self, source: str = 'github', task_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取一个待处理任务
        
        Args:
            source: 任务来源，默认'github'
            task_id: 指定任务ID，如果为None则自动选择
            
        Returns:
            任务信息字典或None
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            if task_id:
                # 查询指定任务ID
                cursor.execute("""
                    SELECT id, source, github_login, status, type, url, 
                           created_at, updated_at, started_at, batch_id, progress_stage
                    FROM crawl_tasks 
                    WHERE id = %s AND source = %s
                """, (task_id, source))
            else:
                # 自动选择第一个pending任务
                cursor.execute("""
                    SELECT id, source, github_login, status, type, url,
                           created_at, updated_at, started_at, batch_id, progress_stage
                    FROM crawl_tasks 
                    WHERE source = %s AND status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                """, (source,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                self.logger.debug(f"获取到任务: ID={result['id']}, 用户={result['github_login']}")
                return result
            else:
                self.logger.warning(f"未找到符合条件的任务 (source={source}, task_id={task_id})")
                return None
                
        except Exception as e:
            self.logger.error(f"获取待处理任务失败: {e}")
            return None
    
    def update_task_status(self, task_id: int, status: str, started_at: Optional[str] = None) -> bool:
        """更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态 ('pending', 'running', 'done', 'failed')
            started_at: 开始时间（可选）
            
        Returns:
            是否更新成功
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if started_at:
                cursor.execute("""
                    UPDATE crawl_tasks 
                    SET status = %s, started_at = %s, updated_at = NOW()
                    WHERE id = %s
                """, (status, started_at, task_id))
            else:
                cursor.execute("""
                    UPDATE crawl_tasks 
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s
                """, (status, task_id))
            
            rows_affected = cursor.rowcount
            cursor.close()
            conn.close()
            
            if rows_affected > 0:
                self.logger.debug(f"任务状态更新成功: task_id={task_id}, status={status}")
                return True
            else:
                self.logger.warning(f"任务状态更新失败，未找到任务: task_id={task_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"更新任务状态失败: {e}")
            return False
    
    def write_crawl_log(self, task_id: int, source: str, status: str, message: str, 
                       url: Optional[str] = None, task_type: Optional[str] = None) -> Optional[int]:
        """写入爬虫日志
        
        Args:
            task_id: 任务ID
            source: 来源
            status: 状态 ('success', 'fail', 'skip')
            message: 消息
            url: URL（可选）
            task_type: 任务类型（可选）
            
        Returns:
            日志ID或None
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO crawl_logs (task_id, source, task_type, url, status, message, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (task_id, source, task_type, url, status, message))
            
            log_id = cursor.lastrowid
            cursor.close()
            conn.close()
            
            self.logger.debug(f"爬虫日志写入成功: log_id={log_id}, task_id={task_id}")
            return log_id
            
        except Exception as e:
            self.logger.error(f"写入爬虫日志失败: {e}")
            return None
    
    def upsert_github_login(self, login: str) -> Tuple[bool, int]:
        """
        将 login 插入 github_users 表（仅填 github_login；candidate_id/github_id 为空）
        
        Args:
            login: GitHub 登录名
            
        Returns:
            tuple: (是否为新插入, 记录ID)
                  成功插入返回 (True, new_id)
                  若已存在返回 (False, existing_id 或 0)
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 使用 INSERT IGNORE 避免重复键异常
            cursor.execute("""
                INSERT IGNORE INTO github_users (github_login, created_at)
                VALUES (%s, NOW())
            """, (login,))
            
            # 检查是否插入了新记录
            if cursor.rowcount > 0:
                # 新插入
                new_id = cursor.lastrowid
                cursor.close()
                conn.close()
                self.logger.debug(f"新插入 GitHub 用户: {login}, ID={new_id}")
                return True, new_id
            else:
                # 已存在，查询现有记录的ID
                cursor.execute("""
                    SELECT id FROM github_users WHERE github_login = %s
                """, (login,))
                
                result = cursor.fetchone()
                existing_id = result[0] if result else 0
                
                cursor.close()
                conn.close()
                
                self.logger.debug(f"GitHub 用户已存在: {login}, ID={existing_id}")
                return False, existing_id
                
        except Exception as e:
            self.logger.error(f"插入 GitHub 用户失败: {login}, 错误: {e}")
            return False, 0
    
    def ensure_candidate_binding(self, login: str, base_profile: Optional[Dict[str, Any]] = None) -> int:
        """
        确保候选人绑定：若 github_users 无映射 → 最小建档到 candidates 并绑定
        
        Args:
            login: GitHub 登录名
            base_profile: 基础档案信息（可选）
            
        Returns:
            int: 候选人ID
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            
            # 1. 查询或创建 github_users 记录
            cursor.execute("""
                SELECT id, candidate_id FROM github_users WHERE github_login = %s
            """, (login,))
            
            github_user = cursor.fetchone()
            
            if not github_user:
                # 如果不存在，创建新的github_users记录（仅填github_login，github_id留空）
                cursor.execute("""
                    INSERT INTO github_users (github_login, created_at)
                    VALUES (%s, NOW())
                """, (login,))
                github_user_id = cursor.lastrowid
                candidate_id = None
            else:
                github_user_id = github_user['id']
                candidate_id = github_user['candidate_id']
            
            # 2. 如果还没有绑定 candidate，则创建最小建档
            if not candidate_id:
                # 提取基础档案信息
                profile = base_profile or {}
                
                # 创建候选人记录（最小建档）
                cursor.execute("""
                    INSERT INTO candidates (
                        name, bio, company, location, hireable, blog, twitter_username,
                        followers, following, public_repos, organizations, 
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """, (
                    profile.get('name', login),                    # 默认使用login作为name
                    profile.get('bio', ''),
                    profile.get('company', ''),
                    profile.get('location', ''),
                    profile.get('hireable'),
                    profile.get('blog', ''),
                    profile.get('twitter_username', ''),
                    profile.get('followers', 0),
                    profile.get('following', 0),
                    profile.get('public_repos', 0),
                    profile.get('organizations', 0)
                ))
                
                candidate_id = cursor.lastrowid
                
                # 绑定 github_user 到 candidate
                cursor.execute("""
                    UPDATE github_users 
                    SET candidate_id = %s, updated_at = NOW()
                    WHERE id = %s
                """, (candidate_id, github_user_id))
                
                self.logger.info(f"为用户 {login} 创建最小建档: candidate_id={candidate_id}")
            
            cursor.close()
            conn.close()
            
            return candidate_id
            
        except Exception as e:
            self.logger.error(f"候选人绑定失败: {login}, 错误: {e}")
            return 0
    
    def save_raw_text(self, candidate_id: int, url: str, plain_text: str, source: str) -> str:
        """
        保存原文到 raw_texts 表
        
        Args:
            candidate_id: 候选人ID
            url: 源URL
            plain_text: 纯文本内容
            source: 来源标识 ('github_io', 'homepage' 等)
            
        Returns:
            str: 'inserted' 或 'duplicate'
        """
        try:
            import hashlib
            
            # 计算URL哈希
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查是否已存在（幂等性）
            cursor.execute("""
                SELECT id FROM raw_texts 
                WHERE candidate_id = %s AND url_hash = %s
            """, (candidate_id, url_hash))
            
            if cursor.fetchone():
                cursor.close()
                conn.close()
                self.logger.debug(f"原文已存在: candidate_id={candidate_id}, url={url}")
                return 'duplicate'
            
            # 插入新记录
            cursor.execute("""
                INSERT INTO raw_texts (
                    candidate_id, url, url_hash, plain_text, source, created_at
                ) VALUES (%s, %s, %s, %s, %s, NOW())
            """, (candidate_id, url, url_hash, plain_text, source))
            
            cursor.close()
            conn.close()
            
            self.logger.info(f"原文保存成功: candidate_id={candidate_id}, source={source}, 长度={len(plain_text)}")
            return 'inserted'
            
        except Exception as e:
            self.logger.error(f"保存原文失败: candidate_id={candidate_id}, url={url}, 错误: {e}")
            return 'error'