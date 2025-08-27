"""
子进程管理器 - 用于启动和管理爬虫子进程
"""
import os
import sys
import subprocess
import logging
import signal
import time
from typing import Dict, List, Optional, Any
from subprocess import Popen, PIPE


class SubprocessManager:
    """子进程管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running_processes: Dict[str, Popen] = {}
    
    def start_spider(self, spider_entry: str, args: List[str], env: Optional[Dict[str, str]] = None) -> Optional[Popen]:
        """启动爬虫子进程
        
        Args:
            spider_entry: 爬虫入口脚本路径或模块名
            args: 命令行参数列表
            env: 环境变量字典
            
        Returns:
            Popen 对象或 None（如果启动失败）
        """
        try:
            # 构建完整的命令
            if spider_entry.endswith('.py'):
                # 直接执行Python脚本
                cmd = [sys.executable, spider_entry] + args
            else:
                # 执行Python模块
                cmd = [sys.executable, '-m', spider_entry] + args
            
            # 设置环境变量
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            # 启动子进程
            process = Popen(
                cmd,
                stdout=PIPE,
                stderr=PIPE,
                env=process_env,
                cwd=os.getcwd(),
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )
            
            # 记录进程
            process_id = f"{spider_entry}_{process.pid}"
            self.running_processes[process_id] = process
            
            self.logger.info(f"爬虫进程启动成功: {spider_entry}, PID: {process.pid}")
            self.logger.debug(f"命令: {' '.join(cmd)}")
            
            return process
            
        except Exception as e:
            self.logger.error(f"启动爬虫进程失败: {spider_entry}, 错误: {e}")
            return None
    
    def stop_spider(self, process: Popen, timeout: int = 10) -> bool:
        """停止爬虫子进程
        
        Args:
            process: 要停止的进程对象
            timeout: 等待超时时间（秒）
            
        Returns:
            是否成功停止
        """
        if not process or not self.is_running(process):
            return True
        
        try:
            pid = process.pid
            
            # 首先尝试优雅停止
            if sys.platform == "win32":
                # Windows下发送CTRL_BREAK_EVENT
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                except:
                    # 如果信号发送失败，直接terminate
                    process.terminate()
            else:
                # Unix/Linux下发送SIGTERM
                process.terminate()
            
            # 等待进程退出
            try:
                process.wait(timeout=timeout)
                self.logger.info(f"爬虫进程优雅停止成功: PID {pid}")
                return True
            except subprocess.TimeoutExpired:
                # 超时则强制杀死
                self.logger.warning(f"爬虫进程超时未退出，强制杀死: PID {pid}")
                process.kill()
                process.wait()
                return True
                
        except Exception as e:
            self.logger.error(f"停止爬虫进程失败: PID {getattr(process, 'pid', 'unknown')}, 错误: {e}")
            return False
        finally:
            # 从运行列表中移除
            self._remove_from_running_list(process)
    
    def is_running(self, process: Popen) -> bool:
        """检查进程是否正在运行
        
        Args:
            process: 进程对象
            
        Returns:
            是否正在运行
        """
        if not process:
            return False
        
        return_code = process.poll()
        return return_code is None
    
    def get_process_output(self, process: Popen, timeout: float = 0.1) -> tuple[List[str], List[str]]:
        """非阻塞获取进程输出
        
        Args:
            process: 进程对象
            timeout: 超时时间（秒）
            
        Returns:
            (stdout_lines, stderr_lines)
        """
        stdout_lines = []
        stderr_lines = []
        
        if not process or not self.is_running(process):
            return stdout_lines, stderr_lines
        
        try:
            # 非阻塞读取stdout
            if process.stdout:
                while True:
                    try:
                        line = process.stdout.readline()
                        if line:
                            stdout_lines.append(line.strip())
                        else:
                            break
                    except:
                        break
            
            # 非阻塞读取stderr
            if process.stderr:
                while True:
                    try:
                        line = process.stderr.readline()
                        if line:
                            stderr_lines.append(line.strip())
                        else:
                            break
                    except:
                        break
                        
        except Exception as e:
            self.logger.debug(f"读取进程输出失败: {e}")
        
        return stdout_lines, stderr_lines
    
    def stop_all_processes(self, timeout: int = 10) -> int:
        """停止所有运行的进程
        
        Args:
            timeout: 每个进程的停止超时时间
            
        Returns:
            成功停止的进程数量
        """
        stopped_count = 0
        processes_to_stop = list(self.running_processes.values())
        
        for process in processes_to_stop:
            if self.stop_spider(process, timeout):
                stopped_count += 1
        
        self.running_processes.clear()
        return stopped_count
    
    def get_running_processes(self) -> Dict[str, Dict[str, Any]]:
        """获取当前运行的进程信息
        
        Returns:
            进程信息字典
        """
        result = {}
        
        # 清理已结束的进程
        finished_processes = []
        for process_id, process in self.running_processes.items():
            if not self.is_running(process):
                finished_processes.append(process_id)
            else:
                result[process_id] = {
                    'pid': process.pid,
                    'command': ' '.join(process.args) if hasattr(process, 'args') else 'unknown',
                    'running': True
                }
        
        # 移除已结束的进程
        for process_id in finished_processes:
            del self.running_processes[process_id]
        
        return result
    
    def _remove_from_running_list(self, process: Popen):
        """从运行列表中移除进程"""
        to_remove = []
        for process_id, p in self.running_processes.items():
            if p == process:
                to_remove.append(process_id)
        
        for process_id in to_remove:
            del self.running_processes[process_id]


# 全局单例
subprocess_manager = SubprocessManager()


def start_spider(spider_entry: str, args: List[str], env: Optional[Dict[str, str]] = None) -> Optional[Popen]:
    """启动爬虫子进程（便捷函数）"""
    return subprocess_manager.start_spider(spider_entry, args, env)


def stop_spider(process: Popen, timeout: int = 10) -> bool:
    """停止爬虫子进程（便捷函数）"""
    return subprocess_manager.stop_spider(process, timeout)


def is_running(process: Popen) -> bool:
    """检查进程是否正在运行（便捷函数）"""
    return subprocess_manager.is_running(process)