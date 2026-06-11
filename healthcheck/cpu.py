"""CPU health check module.

Collects CPU information, usage, frequency, and load average.
Works on both Windows and Linux using psutil with platform-specific fallbacks.
"""

from __future__ import annotations

import platform
import subprocess
import time
from typing import Any

import psutil

from .config import Config
from .dataclasses import HealthStatus, MetricValue, ModuleResult, Threshold


def _get_cpu_info_windows() -> dict[str, Any]:
    """Get detailed CPU info via Windows WMI/PowerShell."""
    info: dict[str, Any] = {}
    try:
        # PowerShell command to get CPU details
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Processor | "
            "Select-Object Name, Manufacturer, MaxClockSpeed, NumberOfCores, "
            "NumberOfLogicalProcessors, L2CacheSize, L3CacheSize, "
            "SocketDesignation | ConvertTo-Json",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            import json

            data = json.loads(result.stdout)
            # Handle both single object and array
            if isinstance(data, dict):
                data = [data]
            cpu = data[0] if data else {}
            info["model"] = cpu.get("Name", "Unknown")
            info["manufacturer"] = cpu.get("Manufacturer", "")
            info["max_freq_mhz"] = cpu.get("MaxClockSpeed", 0)
            info["l2_cache"] = cpu.get("L2CacheSize", 0)
            info["l3_cache"] = cpu.get("L3CacheSize", 0)
            info["socket"] = cpu.get("SocketDesignation", "")
    except (subprocess.TimeoutExpired, Exception):
        pass
    return info


def _get_cpu_info_linux() -> dict[str, Any]:
    """Get detailed CPU info from /proc/cpuinfo."""
    info: dict[str, Any] = {}
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if ":" in line:
                    key, val = line.split(":", 1)
                    key, val = key.strip(), val.strip()
                    if key == "model name" and "model" not in info:
                        info["model"] = val
                    elif key == "vendor_id":
                        info["manufacturer"] = val
                    elif key == "cpu MHz":
                        info["current_freq_mhz"] = float(val)
                    elif key == "cache size":
                        info["cache"] = val
    except (FileNotFoundError, PermissionError):
        pass
    return info


def collect_cpu_info(config: Config | None = None) -> dict[str, Any]:
    """Collect static CPU information.

    Returns:
        Dict with keys: model, physical_cores, logical_cores, arch,
        max_freq_mhz, min_freq_mhz, current_freq_mhz
    """
    info: dict[str, Any] = {
        "model": "Unknown",
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "arch": platform.machine(),
    }

    # Frequency info
    try:
        freq = psutil.cpu_freq()
        if freq:
            info["current_freq_mhz"] = round(freq.current, 1)
            info["min_freq_mhz"] = round(freq.min, 1) if freq.min else None
            info["max_freq_mhz"] = round(freq.max, 1) if freq.max else None
    except (NotImplementedError, FileNotFoundError):
        info["current_freq_mhz"] = None
        info["min_freq_mhz"] = None
        info["max_freq_mhz"] = None

    # Platform-specific model info
    if platform.system() == "Windows":
        extra = _get_cpu_info_windows()
    else:
        extra = _get_cpu_info_linux()

    info.update(extra)
    return info


def collect_cpu_usage(
    config: Config | None = None,
    per_cpu: bool = False,
) -> list[MetricValue]:
    """Collect CPU usage metrics.

    Args:
        config: Config for thresholds.
        per_cpu: If True, also return per-core percentages.

    Returns:
        List of MetricValue objects.
    """
    interval = config.sampling_interval if config else 1.0
    threshold = config.get_threshold("cpu.usage_percent") if config else None

    metrics: list[MetricValue] = []

    # Aggregate CPU usage (blocks for sampling_interval seconds)
    try:
        cpu_percent = psutil.cpu_percent(interval=interval)
        metrics.append(
            MetricValue(
                name="cpu_usage_percent",
                value=cpu_percent,
                unit="%",
                threshold=threshold,
                message=f"CPU usage: {cpu_percent:.1f}% over {interval}s interval",
            )
        )
    except Exception as e:
        metrics.append(
            MetricValue(
                name="cpu_usage_percent",
                status=HealthStatus.ERROR,
                message=f"Failed to get CPU usage: {e}",
            )
        )

    # Per-core usage (non-blocking, uses same interval)
    if per_cpu:
        try:
            per_core = psutil.cpu_percent(interval=0, percpu=True)
            for i, pct in enumerate(per_core):
                metrics.append(
                    MetricValue(
                        name=f"cpu_core_{i}_percent",
                        value=pct,
                        unit="%",
                        threshold=threshold,
                    )
                )
        except Exception:
            pass

    return metrics


def collect_load_avg(config: Config | None = None) -> list[MetricValue]:
    """Collect system load average.

    On Windows, psutil emulates load average but it may not be meaningful.
    We report it with a note.

    Returns:
        List of MetricValue objects (load_1m, load_5m, load_15m).
    """
    metrics: list[MetricValue] = []
    try:
        load1, load5, load15 = psutil.getloadavg()
        logical_cores = psutil.cpu_count(logical=True) or 1
        threshold = config.get_threshold("cpu.usage_percent") if config else None

        for name, val in [("load_1m", load1), ("load_5m", load5), ("load_15m", load15)]:
            # Normalize load to per-core percentage for threshold comparison
            normalized = (val / logical_cores) * 100
            note = ""
            if platform.system() == "Windows":
                note = " (emulated on Windows)"

            status = HealthStatus.OK
            if threshold and normalized >= threshold.critical:
                status = HealthStatus.CRITICAL
            elif threshold and normalized >= threshold.warning:
                status = HealthStatus.WARNING

            metrics.append(
                MetricValue(
                    name=name,
                    value=val,
                    unit=f"({logical_cores} cores)",
                    status=status,
                    message=f"Load {name}: {val:.2f}{note}",
                )
            )
    except (OSError, AttributeError):
        metrics.append(
            MetricValue(
                name="load_average",
                status=HealthStatus.NA,
                message="Load average not available",
            )
        )

    return metrics


def collect(config: Config | None = None, per_cpu: bool = False) -> ModuleResult:
    """Run all CPU health checks.

    Args:
        config: Optional Config for thresholds.
        per_cpu: If True, include per-core usage.

    Returns:
        ModuleResult with all CPU metrics.
    """
    if config is None:
        config = Config()

    metrics: list[MetricValue] = []
    raw_data: dict[str, Any] = {}

    try:
        raw_data = collect_cpu_info(config)
        # Add static info as metrics
        metrics.append(
            MetricValue(
                name="cpu_model",
                value=None,
                message=f"Model: {raw_data.get('model', 'Unknown')}",
            )
        )
        metrics.append(
            MetricValue(
                name="cpu_cores_physical",
                value=raw_data.get("physical_cores", 0),
                message=f"Physical cores: {raw_data.get('physical_cores', 0)}",
            )
        )
        metrics.append(
            MetricValue(
                name="cpu_cores_logical",
                value=raw_data.get("logical_cores", 0),
                message=f"Logical cores: {raw_data.get('logical_cores', 0)}",
            )
        )

        # Frequency (informational only — modern CPUs scale dynamically)
        current_freq = raw_data.get("current_freq_mhz")
        if current_freq:
            max_freq = raw_data.get("max_freq_mhz")
            freq_message = f"Frequency: {current_freq} MHz"
            if max_freq:
                freq_message += f" (max: {max_freq} MHz)"
            metrics.append(
                MetricValue(
                    name="cpu_frequency_mhz",
                    value=current_freq,
                    unit="MHz",
                    status=HealthStatus.OK,
                    message=freq_message,
                )
            )

        # Usage
        metrics.extend(collect_cpu_usage(config, per_cpu=per_cpu))

        # Load average
        metrics.extend(collect_load_avg(config))

        return ModuleResult(module="cpu", metrics=metrics, raw_data=raw_data)

    except Exception as e:
        return ModuleResult(
            module="cpu",
            metrics=metrics,
            raw_data=raw_data,
            error=str(e),
        )


if __name__ == "__main__":
    # Allow running as standalone script
    result = collect(per_cpu=True)
    print(f"CPU Status: {result.status.value}")
    for m in result.metrics:
        status_icon = {
            HealthStatus.OK: "✓",
            HealthStatus.WARNING: "⚠",
            HealthStatus.CRITICAL: "✗",
            HealthStatus.ERROR: "!",
            HealthStatus.NA: "?",
        }
        print(f"  {status_icon.get(m.status, ' ')} {m.name}: {m.message}")
