"""Memory health check module.

Collects RAM and swap usage metrics.
Uses psutil for cross-platform support with additional Linux /proc/meminfo detail.
"""

from __future__ import annotations

import platform
from typing import Any

import psutil

from .config import Config
from .dataclasses import HealthStatus, MetricValue, ModuleResult, Threshold


def _bytes_to_gb(b: int) -> float:
    """Convert bytes to gigabytes, rounded to 2 decimal places."""
    return round(b / (1024 ** 3), 2)


def _collect_linux_meminfo() -> dict[str, Any]:
    """Collect extra memory details from /proc/meminfo (Linux only)."""
    details: dict[str, Any] = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val_str = val.strip().split()[0]  # remove " kB" suffix
                    try:
                        val_kb = int(val_str)
                    except ValueError:
                        continue
                    if key in (
                        "MemTotal", "MemFree", "MemAvailable",
                        "Buffers", "Cached", "SwapTotal", "SwapFree",
                        "Slab", "SReclaimable", "Shmem",
                    ):
                        details[key] = _bytes_to_gb(val_kb * 1024)
    except (FileNotFoundError, PermissionError):
        pass
    return details


def collect_memory_usage(config: Config | None = None) -> list[MetricValue]:
    """Collect RAM usage metrics.

    Args:
        config: Config for thresholds.

    Returns:
        List of MetricValue objects.
    """
    threshold = config.get_threshold("memory.usage_percent") if config else None
    metrics: list[MetricValue] = []

    try:
        mem = psutil.virtual_memory()
        total_gb = _bytes_to_gb(mem.total)
        avail_gb = _bytes_to_gb(mem.available)
        used_gb = _bytes_to_gb(mem.used)
        free_gb = _bytes_to_gb(mem.free)

        metrics.append(
            MetricValue(
                name="memory_total_gb",
                value=total_gb,
                unit="GB",
                message=f"Total RAM: {total_gb:.1f} GB",
            )
        )
        metrics.append(
            MetricValue(
                name="memory_available_gb",
                value=avail_gb,
                unit="GB",
                message=f"Available: {avail_gb:.1f} GB",
            )
        )
        metrics.append(
            MetricValue(
                name="memory_used_gb",
                value=used_gb,
                unit="GB",
                message=f"Used: {used_gb:.1f} GB",
            )
        )
        metrics.append(
            MetricValue(
                name="memory_usage_percent",
                value=mem.percent,
                unit="%",
                threshold=threshold,
                message=(
                    f"RAM usage: {mem.percent:.1f}% "
                    f"({used_gb:.1f}/{total_gb:.1f} GB)"
                ),
            )
        )

        # Linux extra details
        if platform.system() == "Linux":
            extra = _collect_linux_meminfo()
            if "Buffers" in extra:
                metrics.append(
                    MetricValue(
                        name="memory_buffers_gb",
                        value=extra["Buffers"],
                        unit="GB",
                        message=f"Buffers: {extra['Buffers']:.1f} GB",
                    )
                )
            if "Cached" in extra:
                metrics.append(
                    MetricValue(
                        name="memory_cached_gb",
                        value=extra["Cached"],
                        unit="GB",
                        message=f"Cached: {extra['Cached']:.1f} GB",
                    )
                )
            if "MemAvailable" in extra:
                metrics.append(
                    MetricValue(
                        name="memory_linux_available_gb",
                        value=extra["MemAvailable"],
                        unit="GB",
                        message=f"Linux available: {extra['MemAvailable']:.1f} GB",
                    )
                )

    except Exception as e:
        metrics.append(
            MetricValue(
                name="memory_usage_percent",
                status=HealthStatus.ERROR,
                message=f"Failed to get memory info: {e}",
            )
        )

    return metrics


def collect_swap_usage(config: Config | None = None) -> list[MetricValue]:
    """Collect swap usage metrics.

    Args:
        config: Config for thresholds.

    Returns:
        List of MetricValue objects.
    """
    threshold = config.get_threshold("memory.swap_percent") if config else None
    metrics: list[MetricValue] = []

    try:
        swap = psutil.swap_memory()
        total_gb = _bytes_to_gb(swap.total)
        used_gb = _bytes_to_gb(swap.used)
        free_gb = _bytes_to_gb(swap.free)

        if swap.total > 0:
            metrics.append(
                MetricValue(
                    name="swap_total_gb",
                    value=total_gb,
                    unit="GB",
                    message=f"Total swap: {total_gb:.1f} GB",
                )
            )
            metrics.append(
                MetricValue(
                    name="swap_used_gb",
                    value=used_gb,
                    unit="GB",
                    message=f"Swap used: {used_gb:.1f} GB",
                )
            )
            metrics.append(
                MetricValue(
                    name="swap_usage_percent",
                    value=swap.percent,
                    unit="%",
                    threshold=threshold,
                    message=(
                        f"Swap usage: {swap.percent:.1f}% "
                        f"({used_gb:.1f}/{total_gb:.1f} GB)"
                    ),
                )
            )

            # Swap I/O
            metrics.append(
                MetricValue(
                    name="swap_sin_gb",
                    value=_bytes_to_gb(swap.sin),
                    unit="GB",
                    message=f"Swap in: {_bytes_to_gb(swap.sin):.2f} GB",
                )
            )
            metrics.append(
                MetricValue(
                    name="swap_sout_gb",
                    value=_bytes_to_gb(swap.sout),
                    unit="GB",
                    message=f"Swap out: {_bytes_to_gb(swap.sout):.2f} GB",
                )
            )
        else:
            metrics.append(
                MetricValue(
                    name="swap_usage_percent",
                    value=0,
                    unit="%",
                    status=HealthStatus.NA,
                    message="No swap configured",
                )
            )
    except Exception as e:
        metrics.append(
            MetricValue(
                name="swap_usage_percent",
                status=HealthStatus.ERROR,
                message=f"Failed to get swap info: {e}",
            )
        )

    return metrics


def collect(config: Config | None = None) -> ModuleResult:
    """Run all memory health checks.

    Args:
        config: Optional Config for thresholds.

    Returns:
        ModuleResult with all memory metrics.
    """
    if config is None:
        config = Config()

    metrics: list[MetricValue] = []
    raw_data: dict[str, Any] = {}

    try:
        metrics.extend(collect_memory_usage(config))
        metrics.extend(collect_swap_usage(config))

        return ModuleResult(module="memory", metrics=metrics, raw_data=raw_data)

    except Exception as e:
        return ModuleResult(
            module="memory",
            metrics=metrics,
            raw_data=raw_data,
            error=str(e),
        )


if __name__ == "__main__":
    result = collect()
    print(f"Memory Status: {result.status.value}")
    for m in result.metrics:
        status_icon = {
            HealthStatus.OK: "✓",
            HealthStatus.WARNING: "⚠",
            HealthStatus.CRITICAL: "✗",
            HealthStatus.ERROR: "!",
            HealthStatus.NA: "?",
        }
        print(f"  {status_icon.get(m.status, ' ')} {m.name}: {m.message}")
