"""
通用任务运行器

实现通用的任务消费循环框架
Author: Spidermind
"""
import asyncio
from typing import Dict, Any, Callable, Optional, List, Awaitable
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime

from models.base import SessionLocal
from models.crawl import CrawlTask, CrawlLog, CrawlLogCandidate
from services.progress_service import progress_tracker


class TaskRunner:
    """通用任务运行器"""
    
    def __init__(self):
        self.is_running = False
        self.should_stop = False
        
    async def run_batch(
        self,
        task_filters: Dict[str, Any],
        processor: Callable[[Any], Awaitable[Dict[str, Any]]],
        batch_size: int = 10,
        max_tasks: Optional[int] = None,
        progress_source: str = None,
        progress_type: str = None,
        batch_id: str = None
    ):
        """
        运行任务批次处理
        
        Args:
            task_filters: 任务过滤条件 {source, type, status, priority, ...}
            processor: 任务处理函数，接收task参数，返回处理结果字典
            batch_size: 每批处理数量
            max_tasks: 最大处理任务数，None表示处理所有
            progress_source: 进度跟踪来源
            progress_type: 进度跟踪类型
            batch_id: 批次ID
        """
        self.is_running = True
        self.should_stop = False
        
        processed_count = 0
        
        try:
            while not self.should_stop:
                # 获取待处理任务
                tasks = self._get_pending_tasks(task_filters, batch_size)
                
                if not tasks:
                    print(f"没有更多待处理任务，批次完成。已处理: {processed_count}")
                    break
                
                # 检查是否达到最大处理数量
                if max_tasks and processed_count >= max_tasks:
                    print(f"达到最大处理数量 {max_tasks}，批次结束。")
                    break
                
                print(f"开始处理批次，任务数量: {len(tasks)}")
                
                # 处理当前批次
                batch_results = await self._process_batch(
                    tasks, 
                    processor,
                    progress_source,
                    progress_type,
                    batch_id
                )
                
                processed_count += len(batch_results)
                
                # 输出批次处理结果
                success_count = sum(1 for r in batch_results if r.get('status') == 'success')
                fail_count = sum(1 for r in batch_results if r.get('status') == 'fail')
                skip_count = sum(1 for r in batch_results if r.get('status') == 'skip')
                
                print(f"批次处理完成: 成功 {success_count}, 失败 {fail_count}, 跳过 {skip_count}")
                
                # 短暂延迟避免过于频繁的数据库查询
                await asyncio.sleep(0.1)
            
        except Exception as e:
            print(f"任务运行器异常: {e}")
            if progress_source and progress_type:
                progress_tracker.record_failure(
                    progress_source, 
                    progress_type, 
                    f"运行器异常: {str(e)}", 
                    batch_id
                )
            raise
        
        finally:
            self.is_running = False
            if progress_source and progress_type and batch_id:
                progress_tracker.finish_batch(progress_source, progress_type, batch_id)
            
            print(f"任务批次完成，总计处理: {processed_count}")
    
    def _get_pending_tasks(self, filters: Dict[str, Any], limit: int) -> List[CrawlTask]:
        """
        获取待处理任务
        
        Args:
            filters: 过滤条件
            limit: 数量限制
            
        Returns:
            List[CrawlTask]: 任务列表
        """
        db = SessionLocal()
        try:
            query = db.query(CrawlTask)
            
            # 应用过滤条件
            conditions = []
            
            if 'source' in filters:
                conditions.append(CrawlTask.source == filters['source'])
            
            if 'type' in filters:
                conditions.append(CrawlTask.type == filters['type'])
            
            if 'status' in filters:
                conditions.append(CrawlTask.status == filters['status'])
            
            if 'priority' in filters:
                conditions.append(CrawlTask.priority >= filters['priority'])
            
            if 'candidate_id' in filters:
                conditions.append(CrawlTask.candidate_id == filters['candidate_id'])
            
            if 'batch_id' in filters:
                conditions.append(CrawlTask.batch_id == filters['batch_id'])
            
            # 应用条件
            if conditions:
                query = query.filter(and_(*conditions))
            
            # 按优先级和创建时间排序
            tasks = query.order_by(
                CrawlTask.priority.desc(),
                CrawlTask.created_at.asc()
            ).limit(limit).all()
            
            return tasks
            
        finally:
            db.close()
    
    async def _process_batch(
        self,
        tasks: List[CrawlTask],
        processor: Callable[[Any], Awaitable[Dict[str, Any]]],
        progress_source: str = None,
        progress_type: str = None,
        batch_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        处理任务批次
        
        Args:
            tasks: 任务列表
            processor: 处理函数
            progress_source: 进度来源
            progress_type: 进度类型
            batch_id: 批次ID
            
        Returns:
            List[Dict]: 处理结果列表
        """
        results = []
        
        for task in tasks:
            if self.should_stop:
                break
                
            try:
                # 更新任务状态为处理中
                self._update_task_status(task.id, 'processing')
                
                # 调用处理函数
                result = await processor(task)
                
                # 处理结果
                status = result.get('status', 'fail')
                message = result.get('message', '')
                error = result.get('error', '')
                
                # 更新任务状态
                if status == 'success':
                    self._update_task_status(task.id, 'done')
                    if progress_source and progress_type:
                        progress_tracker.record_success(progress_source, progress_type, batch_id)
                elif status == 'skip':
                    self._update_task_status(task.id, 'done')  # 跳过也标记为完成
                    if progress_source and progress_type:
                        progress_tracker.record_skip(progress_source, progress_type, message, batch_id)
                else:
                    # 失败时增加重试次数
                    self._increment_task_retries(task.id)
                    self._update_task_status(task.id, 'failed')
                    if progress_source and progress_type:
                        progress_tracker.record_failure(progress_source, progress_type, error or message, batch_id)
                
                # 记录处理日志
                log_id = self._create_task_log(
                    task_id=task.id,
                    source=task.source,
                    url=task.url,
                    status=status,
                    message=message or error
                )
                
                # 如果有关联的候选人，记录关联关系
                if task.candidate_id and log_id:
                    self._create_log_candidate_link(log_id, task.candidate_id)
                
                results.append({
                    'task_id': task.id,
                    'status': status,
                    'message': message,
                    'error': error,
                    'log_id': log_id
                })
                
            except Exception as e:
                error_message = f"处理任务 {task.id} 时发生异常: {str(e)}"
                print(error_message)
                
                # 记录异常
                self._increment_task_retries(task.id)
                self._update_task_status(task.id, 'failed')
                
                if progress_source and progress_type:
                    progress_tracker.record_failure(progress_source, progress_type, error_message, batch_id)
                
                # 记录错误日志
                log_id = self._create_task_log(
                    task_id=task.id,
                    source=task.source,
                    url=task.url,
                    status='fail',
                    message=error_message
                )
                
                results.append({
                    'task_id': task.id,
                    'status': 'fail',
                    'message': error_message,
                    'error': str(e),
                    'log_id': log_id
                })
        
        return results
    
    def _update_task_status(self, task_id: int, status: str):
        """更新任务状态"""
        db = SessionLocal()
        try:
            task = db.query(CrawlTask).filter(CrawlTask.id == task_id).first()
            if task:
                task.status = status
                task.updated_at = datetime.now()
                db.commit()
        except Exception as e:
            db.rollback()
            print(f"更新任务状态失败: {e}")
        finally:
            db.close()
    
    def _increment_task_retries(self, task_id: int):
        """增加任务重试次数"""
        db = SessionLocal()
        try:
            task = db.query(CrawlTask).filter(CrawlTask.id == task_id).first()
            if task:
                task.retries = (task.retries or 0) + 1
                task.updated_at = datetime.now()
                db.commit()
        except Exception as e:
            db.rollback()
            print(f"更新任务重试次数失败: {e}")
        finally:
            db.close()
    
    def _create_task_log(
        self, 
        task_id: int, 
        source: str, 
        url: str, 
        status: str, 
        message: str
    ) -> Optional[int]:
        """创建任务日志"""
        db = SessionLocal()
        try:
            log = CrawlLog(
                task_id=task_id,
                source=source,
                url=url,
                status=status,
                message=message,
                created_at=datetime.now()
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log.id
        except Exception as e:
            db.rollback()
            print(f"创建任务日志失败: {e}")
            return None
        finally:
            db.close()
    
    def _create_log_candidate_link(self, log_id: int, candidate_id: int):
        """创建日志与候选人的关联"""
        db = SessionLocal()
        try:
            # 检查是否已存在关联
            existing = db.query(CrawlLogCandidate).filter(
                CrawlLogCandidate.log_id == log_id,
                CrawlLogCandidate.candidate_id == candidate_id
            ).first()
            
            if not existing:
                link = CrawlLogCandidate(
                    log_id=log_id,
                    candidate_id=candidate_id
                )
                db.add(link)
                db.commit()
        except Exception as e:
            db.rollback()
            print(f"创建日志候选人关联失败: {e}")
        finally:
            db.close()
    
    def stop(self):
        """停止任务运行器"""
        self.should_stop = True
        print("任务运行器收到停止信号")


class TaskBatchManager:
    """任务批次管理器"""
    
    @staticmethod
    def create_tasks(
        source: str,
        task_type: str,
        task_data_list: List[Dict[str, Any]],
        batch_id: str = None,
        priority: int = 0
    ) -> List[int]:
        """
        批量创建任务
        
        Args:
            source: 任务来源
            task_type: 任务类型
            task_data_list: 任务数据列表
            batch_id: 批次ID
            priority: 优先级
            
        Returns:
            List[int]: 创建的任务ID列表
        """
        db = SessionLocal()
        created_task_ids = []
        
        try:
            for task_data in task_data_list:
                # 检查是否已存在相同任务（根据去重键）
                existing_task = db.query(CrawlTask).filter(
                    CrawlTask.source == source,
                    CrawlTask.type == task_type,
                    CrawlTask.url == task_data.get('url', ''),
                    CrawlTask.github_login == task_data.get('github_login', ''),
                    CrawlTask.openreview_profile_id == task_data.get('openreview_profile_id', '')
                ).first()
                
                if existing_task:
                    print(f"任务已存在，跳过: {task_data}")
                    continue
                
                # 创建新任务
                task = CrawlTask(
                    source=source,
                    type=task_type,
                    url=task_data.get('url'),
                    github_login=task_data.get('github_login'),
                    openreview_profile_id=task_data.get('openreview_profile_id'),
                    candidate_id=task_data.get('candidate_id'),
                    depth=task_data.get('depth', 0),
                    status='pending',
                    priority=priority,
                    batch_id=batch_id,
                    retries=0,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                db.add(task)
                db.flush()  # 获取ID但不提交
                created_task_ids.append(task.id)
            
            db.commit()
            print(f"批量创建任务完成，创建数量: {len(created_task_ids)}")
            
        except Exception as e:
            db.rollback()
            print(f"批量创建任务失败: {e}")
            raise
        finally:
            db.close()
        
        return created_task_ids
    
    @staticmethod
    def get_task_stats(source: str = None, task_type: str = None) -> Dict[str, int]:
        """
        获取任务统计信息
        
        Args:
            source: 来源过滤
            task_type: 类型过滤
            
        Returns:
            Dict: 统计信息
        """
        db = SessionLocal()
        try:
            query = db.query(CrawlTask)
            
            if source:
                query = query.filter(CrawlTask.source == source)
            if task_type:
                query = query.filter(CrawlTask.type == task_type)
            
            # 统计各状态数量
            from sqlalchemy import func
            
            stats = db.query(
                CrawlTask.status,
                func.count(CrawlTask.id).label('count')
            ).filter(
                *([CrawlTask.source == source] if source else []),
                *([CrawlTask.type == task_type] if task_type else [])
            ).group_by(CrawlTask.status).all()
            
            result = {
                'pending': 0,
                'processing': 0, 
                'done': 0,
                'failed': 0,
                'total': 0
            }
            
            for status, count in stats:
                result[status] = count
                result['total'] += count
            
            return result
            
        finally:
            db.close()