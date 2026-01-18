import time
import os
import psutil

class PerformanceMonitor:
    """性能监控工具，用于记录和分析关键操作的耗时"""
    
    def __init__(self):
        self.timings = {}
        self.memory_usage = {}
        self.enabled = True
    
    def start_timing(self, operation_name: str):
        """开始计时一个操作"""
        if not self.enabled:
            return
        
        self.timings[operation_name] = {
            'start_time': time.perf_counter(),
            'start_memory': self._get_memory_usage()
        }
        print(f"开始 {operation_name}...")
    
    def end_timing(self, operation_name: str, details: str = ""):
        """结束计时并输出结果"""
        if not self.enabled or operation_name not in self.timings:
            return
        
        end_time = time.perf_counter()
        end_memory = self._get_memory_usage()
        
        timing_data = self.timings[operation_name]
        duration = end_time - timing_data['start_time']
        memory_diff = end_memory - timing_data['start_memory']
        
        # 格式化输出
        duration_str = f"{duration:.3f}s" if duration >= 1 else f"{duration*1000:.1f}ms"
        memory_str = f"{memory_diff:+.1f}MB" if abs(memory_diff) >= 1 else f"{memory_diff*1024:+.0f}KB"
        
        status = "快速" if duration < 0.5 else "警告" if duration < 2.0 else "缓慢"
        
        print(f"{status} 完成 {operation_name}: {duration_str} | 内存: {memory_str} {details}")
        
        # 清理记录
        del self.timings[operation_name]
    
    def _get_memory_usage(self) -> float:
        """获取当前进程内存使用量(MB)"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except:
            return 0.0
    
    def print_summary(self):
        """打印性能总结"""
        if self.timings:
            print("\n未完成的操作:")
            for name in self.timings.keys():
                print(f"   - {name}")

# 全局性能监控实例
perf_monitor = PerformanceMonitor()
