"""真实系统指标：查询运行这个 AIOps 服务的宿主机本身的 CPU/内存/磁盘/进程数。

和 data/mock/metrics.py 的区别是这个项目里刻意做出来的一条分界线：mock/ 目录下
是虚构公司服务（order-service等）编造的固定快照数据，real/ 目录下是用 psutil
直接读操作系统拿到的、每次调用都会变的真实数字。两者放在不同目录、用不同函数名，
是为了让"这个系统到底哪部分是真的"这件事在代码结构上一眼可辨，不用靠注释解释。
"""
import os

import psutil


def get_host_metrics() -> dict:
    cpu_percent = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    degraded = cpu_percent > 85 or mem.percent > 90 or disk.percent > 90
    return {
        "service": "aiops-agent-host（本机真实数据，非mock）",
        "status": "degraded" if degraded else "healthy",
        "cpu_percent": round(cpu_percent, 1),
        "memory_percent": round(mem.percent, 1),
        "disk_percent": round(disk.percent, 1),
        "process_count": len(psutil.pids()),
    }
