"""Internationalization (i18n) module for System Health Check.

Supports Chinese (zh) and English (en) with runtime switching.
All user-visible strings should be accessed via t() function.
"""

from __future__ import annotations

from typing import Any

_current_lang: str = "zh"


def set_language(lang: str) -> None:
    """Set the current language. 'zh' or 'en'."""
    global _current_lang
    if lang in TRANSLATIONS:
        _current_lang = lang


def get_language() -> str:
    """Get the current language code."""
    return _current_lang


def t(key: str, **kwargs: Any) -> str:
    """Translate a key to the current language.

    Supports Python format() style placeholders:
        t("cpu_usage", percent=85) -> "CPU 使用率: 85%" or "CPU Usage: 85%"

    Falls back to English if key not found in current language.
    """
    table = TRANSLATIONS.get(_current_lang, TRANSLATIONS["en"])
    template = _get_nested(table, key)
    if template is None:
        # Fallback to English
        template = _get_nested(TRANSLATIONS["en"], key)
    if template is None:
        return key
    if kwargs:
        return template.format(**kwargs)
    return template


def _get_nested(d: dict, key: str) -> str | None:
    """Get a nested dict value by dotted key: 'gui.title' -> d['gui']['title']."""
    parts = key.split(".")
    node: Any = d
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node if isinstance(node, str) else None


# =============================================================================
# Translation Tables
# =============================================================================

TRANSLATIONS: dict[str, dict[str, Any]] = {
    "en": {
        "gui": {
            "title": "System Health Check",
            "run_check": "Run Check",
            "running": "Running health checks...",
            "ready": "Ready. Click 'Run Check' to start.",
            "complete": "Check complete. Click 'Run Check' to refresh.",
            "overall_status": "Overall Status",
            "language": "中文",
        },
        "status": {
            "OK": "PASS",
            "WARNING": "WARN",
            "CRITICAL": "FAIL",
            "ERROR": "ERROR",
            "NA": "N/A",
        },
        "modules": {
            "cpu": "CPU",
            "memory": "Memory",
            "disk": "Disk",
            "smart": "S.M.A.R.T.",
            "network": "Network",
            "temperature": "Temperature",
        },
        "module_desc": {
            "cpu": "CPU usage, frequency, and load average",
            "memory": "RAM and swap usage",
            "disk": "Disk partitions, usage, and I/O",
            "smart": "S.M.A.R.T. disk health status",
            "network": "Network interfaces, I/O, and ping test",
            "temperature": "CPU and GPU temperatures",
        },
        "cpu": {
            "cpu_model": "Model",
            "cpu_cores_physical": "Physical Cores",
            "cpu_cores_logical": "Logical Cores",
            "cpu_frequency_mhz": "Frequency",
            "cpu_usage_percent": "CPU Usage",
            "load_1m": "Load 1min",
            "load_5m": "Load 5min",
            "load_15m": "Load 15min",
            "load_emulated": "(emulated on Windows)",
            "freq_msg": "{current} MHz (max: {max} MHz)",
            "freq_msg_no_max": "{current} MHz",
            "usage_msg": "{pct:.1f}% over {interval}s interval",
        },
        "memory": {
            "memory_total_gb": "Total RAM",
            "memory_available_gb": "Available",
            "memory_used_gb": "Used",
            "memory_usage_percent": "RAM Usage",
            "memory_buffers_gb": "Buffers",
            "memory_cached_gb": "Cached",
            "memory_linux_available_gb": "Linux Available",
            "swap_total_gb": "Total Swap",
            "swap_used_gb": "Swap Used",
            "swap_usage_percent": "Swap Usage",
            "swap_sin_gb": "Swap In",
            "swap_sout_gb": "Swap Out",
            "usage_msg": "{pct:.1f}% ({used:.1f}/{total:.1f} GB)",
            "no_swap": "No swap configured",
        },
        "disk": {
            "usage_msg": "{mp} ({dev}): {pct:.1f}% used ({used:.1f}/{total:.1f} GB, {free:.1f} GB free)",
            "inode_msg": "{mp} inodes: {pct:.1f}% used ({used}/{total})",
            "io_read": "{disk}: {size} read ({count:,} ops)",
            "io_write": "{disk}: {size} written ({count:,} ops)",
            "perm_denied": "Not accessible (CD/DVD or permission denied)",
            "no_partitions": "No disk partitions found",
            "io_not_available": "Disk I/O stats not available",
        },
        "smart": {
            "healthy": "{name}: Healthy",
            "warning": "{name}: Warning - disk may need attention",
            "critical": "{name}: {health} - disk needs attention",
            "temp": "{disk} temperature: {temp}°C",
            "wear": "{disk} wear: {wear}%",
            "hours": "{disk} power-on hours: {hours}",
            "read_errors": "{disk} read errors: {errors}",
            "passed": "{dev}: S.M.A.R.T. health PASSED",
            "failed": "{dev}: S.M.A.R.T. health FAILED",
            "not_installed": "smartctl not installed. Install smartmontools package.",
            "no_devices": "No disk devices found for S.M.A.R.T. check",
            "perm_denied": "Cannot access {dev}: permission denied (run as root)",
            "not_available": "S.M.A.R.T. not available (no physical disk data)",
            "timed_out": "S.M.A.R.T. check timed out",
        },
        "network": {
            "interface_up": "UP",
            "interface_down": "DOWN",
            "iface_msg": "{name}: {ip}, MAC: {mac}, {state}, {speed} Mbps",
            "sent": "sent {size} ({pkts:,} pkts)",
            "recv": "received {size} ({pkts:,} pkts)",
            "ping_loss": "{host}: {recv}/{sent} received, {loss:.0f}% loss",
            "ping_latency": "{host}: avg {avg:.1f}ms (min: {min:.1f}, max: {max:.1f})",
            "unreachable": "{host}: unreachable (100% packet loss)",
        },
        "temperature": {
            "cpu_na": "CPU temperature not available via WMI (common on VMs)",
            "cpu_error": "CPU temperature not available: {error}",
            "no_sensors": "No temperature sensors found. Install lm-sensors.",
            "gpu_temp": "GPU {idx} ({name}): {temp}°C",
        },
        "report": {
            "system_health_check": "SYSTEM HEALTH CHECK",
            "overall_status": "Overall Status",
            "healthy": "All systems healthy",
            "warning": "Some metrics at warning levels",
            "critical": "Critical issues detected!",
            "error": "Errors occurred during health check",
            "generated": "Generated",
            "json_saved": "JSON report saved to {file}",
            "html_saved": "HTML report saved to {file}",
            "report_saved": "Report saved to {file}",
        },
    },
    "zh": {
        "gui": {
            "title": "系统健康检查",
            "run_check": "运行检查",
            "running": "正在运行健康检查...",
            "ready": "就绪。点击「运行检查」开始。",
            "complete": "检查完成。点击「运行检查」重新检测。",
            "overall_status": "总体状态",
            "language": "English",
        },
        "status": {
            "OK": "正常",
            "WARNING": "警告",
            "CRITICAL": "严重",
            "ERROR": "错误",
            "NA": "无数据",
        },
        "modules": {
            "cpu": "CPU",
            "memory": "内存",
            "disk": "磁盘",
            "smart": "S.M.A.R.T.",
            "network": "网络",
            "temperature": "温度",
        },
        "module_desc": {
            "cpu": "CPU 使用率、频率和负载",
            "memory": "内存和虚拟内存使用率",
            "disk": "磁盘分区、使用率和 I/O",
            "smart": "S.M.A.R.T. 磁盘健康状态",
            "network": "网络接口、流量和连通性测试",
            "temperature": "CPU 和 GPU 温度",
        },
        "cpu": {
            "cpu_model": "型号",
            "cpu_cores_physical": "物理核心",
            "cpu_cores_logical": "逻辑核心",
            "cpu_frequency_mhz": "频率",
            "cpu_usage_percent": "CPU 使用率",
            "load_1m": "1分钟负载",
            "load_5m": "5分钟负载",
            "load_15m": "15分钟负载",
            "load_emulated": "(Windows 模拟)",
            "freq_msg": "{current} MHz (最大: {max} MHz)",
            "freq_msg_no_max": "{current} MHz",
            "usage_msg": "{pct:.1f}% ({interval}秒采样)",
        },
        "memory": {
            "memory_total_gb": "总内存",
            "memory_available_gb": "可用",
            "memory_used_gb": "已用",
            "memory_usage_percent": "内存使用率",
            "memory_buffers_gb": "缓冲区",
            "memory_cached_gb": "缓存",
            "memory_linux_available_gb": "Linux 可用",
            "swap_total_gb": "总交换空间",
            "swap_used_gb": "已用交换",
            "swap_usage_percent": "交换使用率",
            "swap_sin_gb": "换入",
            "swap_sout_gb": "换出",
            "usage_msg": "{pct:.1f}% ({used:.1f}/{total:.1f} GB)",
            "no_swap": "未配置交换空间",
        },
        "disk": {
            "usage_msg": "{mp} ({dev}): 已用 {pct:.1f}% ({used:.1f}/{total:.1f} GB, 可用 {free:.1f} GB)",
            "inode_msg": "{mp} inode: 已用 {pct:.1f}% ({used}/{total})",
            "io_read": "{disk}: 读取 {size} ({count:,} 次)",
            "io_write": "{disk}: 写入 {size} ({count:,} 次)",
            "perm_denied": "无法访问 (光驱或权限不足)",
            "no_partitions": "未找到磁盘分区",
            "io_not_available": "磁盘 I/O 统计不可用",
        },
        "smart": {
            "healthy": "{name}: 健康",
            "warning": "{name}: 警告 - 磁盘可能需要关注",
            "critical": "{name}: {health} - 磁盘需要立即关注",
            "temp": "{disk} 温度: {temp}°C",
            "wear": "{disk} 磨损: {wear}%",
            "hours": "{disk} 通电时间: {hours} 小时",
            "read_errors": "{disk} 读取错误: {errors}",
            "passed": "{dev}: S.M.A.R.T. 健康状态正常",
            "failed": "{dev}: S.M.A.R.T. 健康状态异常",
            "not_installed": "未安装 smartctl。请安装 smartmontools 包。",
            "no_devices": "未找到可检查 S.M.A.R.T. 的磁盘设备",
            "perm_denied": "无法访问 {dev}: 权限不足 (请以 root 运行)",
            "not_available": "S.M.A.R.T. 不可用 (无物理磁盘数据)",
            "timed_out": "S.M.A.R.T. 检查超时",
        },
        "network": {
            "interface_up": "已连接",
            "interface_down": "已断开",
            "iface_msg": "{name}: {ip}, MAC: {mac}, {state}, {speed} Mbps",
            "sent": "发送 {size} ({pkts:,} 包)",
            "recv": "接收 {size} ({pkts:,} 包)",
            "ping_loss": "{host}: {recv}/{sent} 收到, {loss:.0f}% 丢失",
            "ping_latency": "{host}: 平均 {avg:.1f}ms (最小: {min:.1f}, 最大: {max:.1f})",
            "unreachable": "{host}: 不可达 (100% 丢包)",
        },
        "temperature": {
            "cpu_na": "CPU 温度不可用 (虚拟机通常无 WMI 温度传感器)",
            "cpu_error": "CPU 温度不可用: {error}",
            "no_sensors": "未找到温度传感器。请安装 lm-sensors。",
            "gpu_temp": "GPU {idx} ({name}): {temp}°C",
        },
        "report": {
            "system_health_check": "系统健康检查",
            "overall_status": "总体状态",
            "healthy": "所有系统正常",
            "warning": "部分指标处于警告级别",
            "critical": "检测到严重问题！",
            "error": "健康检查过程中发生错误",
            "generated": "生成时间",
            "json_saved": "JSON 报告已保存到 {file}",
            "html_saved": "HTML 报告已保存到 {file}",
            "report_saved": "报告已保存到 {file}",
        },
    },
}
