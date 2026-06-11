"""Disk health check module.

Collects disk partition, usage, and I/O metrics.
Works on both Windows and Linux using psutil with platform-specific additions.
"""

from __future__ import annotations

import os
import platform
from typing import Any

import psutil

from .config import Config
from .dataclasses import HealthStatus, MetricValue, ModuleResult


def _bytes_to_gb(b: int) -> float:
    """Convert bytes to gigabytes."""
    return round(b / (1024 ** 3), 2)


def _get_disk_type(partition: str, mountpoint: str) -> str:
    """Guess disk type from mountpoint/device."""
    mp = mountpoint.lower()
    if platform.system() == "Windows":
        # Windows: check if it's a system drive
        system_drive = os.environ.get("SystemDrive", "C:")
        if partition.startswith(system_drive):
            return "system"
        return "data"
    else:
        if mountpoint == "/":
            return "system"
        elif mountpoint.startswith("/boot"):
            return "boot"
        elif mountpoint.startswith("/home"):
            return "home"
        return "data"


def collect_disk_partitions(config: Config | None = None) -> list[MetricValue]:
    """Collect disk partition usage metrics.

    Args:
        config: Config for thresholds.

    Returns:
        List of MetricValue objects, one usage_percent per partition.
    """
    threshold = config.get_threshold("disk.usage_percent") if config else None
    metrics: list[MetricValue] = []

    try:
        partitions = psutil.disk_partitions(all=False)
        # Filter out squashfs/loopback snap devices (always 100%)
        partitions = [
            p for p in partitions
            if p.fstype not in ("squashfs",) and not p.device.startswith("/dev/loop")
        ]
        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_gb = _bytes_to_gb(usage.total)
                used_gb = _bytes_to_gb(usage.used)
                free_gb = _bytes_to_gb(usage.free)
                disk_type = _get_disk_type(part.device, part.mountpoint)

                metric_name = f"disk_{disk_type}_{part.mountpoint.replace(':', '').replace('/', '_')}_percent".replace("__", "_")

                metrics.append(
                    MetricValue(
                        name=metric_name,
                        value=usage.percent,
                        unit="%",
                        threshold=threshold,
                        message=(
                            f"{part.mountpoint} ({part.device}): "
                            f"{usage.percent:.1f}% used "
                            f"({used_gb:.1f}/{total_gb:.1f} GB, "
                            f"{free_gb:.1f} GB free)"
                        ),
                        extra={
                            "mountpoint": part.mountpoint,
                            "device": part.device,
                            "filesystem": part.fstype,
                            "total_gb": total_gb,
                            "used_gb": used_gb,
                            "free_gb": free_gb,
                            "disk_type": disk_type,
                        },
                    )
                )

                # Linux-specific: inode usage
                if platform.system() == "Linux":
                    try:
                        st = os.statvfs(part.mountpoint)
                        inode_total = st.f_files
                        inode_free = st.f_ffree
                        inode_used = inode_total - inode_free
                        inode_pct = (inode_used / inode_total * 100) if inode_total > 0 else 0
                        inode_threshold = (
                            config.get_threshold("disk.inode_percent") if config else None
                        )
                        metrics.append(
                            MetricValue(
                                name=f"disk_inode_{part.mountpoint.replace('/', '_')}_percent".replace("__", "_"),
                                value=inode_pct,
                                unit="%",
                                threshold=inode_threshold,
                                message=(
                                    f"{part.mountpoint} inodes: "
                                    f"{inode_pct:.1f}% used "
                                    f"({inode_used:,}/{inode_total:,})"
                                ),
                                extra={
                                    "mountpoint": part.mountpoint,
                                    "inode_total": inode_total,
                                    "inode_used": inode_used,
                                    "inode_free": inode_free,
                                },
                            )
                        )
                    except OSError:
                        pass

            except PermissionError:
                # CD/DVD drives often show as permission denied — that's normal
                metrics.append(
                    MetricValue(
                        name=f"disk_{part.mountpoint}_access",
                        status=HealthStatus.NA,
                        message=f"{part.mountpoint}: Not accessible (CD/DVD or permission denied)",
                    )
                )

    except Exception as e:
        metrics.append(
            MetricValue(
                name="disk_partitions",
                status=HealthStatus.ERROR,
                message=f"Failed to enumerate partitions: {e}",
            )
        )

    if not metrics:
        metrics.append(
            MetricValue(
                name="disk_partitions",
                status=HealthStatus.NA,
                message="No disk partitions found",
            )
        )

    return metrics


def collect_disk_io(config: Config | None = None) -> list[MetricValue]:
    """Collect disk I/O statistics.

    Args:
        config: Config for thresholds.

    Returns:
        List of MetricValue objects for read/write totals.
    """
    metrics: list[MetricValue] = []

    try:
        io = psutil.disk_io_counters(perdisk=True)
        if not io:
            metrics.append(
                MetricValue(
                    name="disk_io",
                    status=HealthStatus.NA,
                    message="Disk I/O stats not available",
                )
            )
            return metrics

        for disk_name, counters in io.items():
            read_gb = _bytes_to_gb(counters.read_bytes)
            write_gb = _bytes_to_gb(counters.write_bytes)
            read_count = counters.read_count
            write_count = counters.write_count

            metrics.append(
                MetricValue(
                    name=f"disk_io_{disk_name}_read_gb",
                    value=read_gb,
                    unit="GB",
                    message=f"{disk_name}: {read_gb:.1f} GB read ({read_count:,} ops)",
                    extra={
                        "disk": disk_name,
                        "read_bytes": counters.read_bytes,
                        "write_bytes": counters.write_bytes,
                        "read_count": read_count,
                        "write_count": write_count,
                        "read_time_ms": counters.read_time,
                        "write_time_ms": counters.write_time,
                    },
                )
            )
            metrics.append(
                MetricValue(
                    name=f"disk_io_{disk_name}_write_gb",
                    value=write_gb,
                    unit="GB",
                    message=f"{disk_name}: {write_gb:.1f} GB written ({write_count:,} ops)",
                )
            )

    except Exception as e:
        metrics.append(
            MetricValue(
                name="disk_io",
                status=HealthStatus.ERROR,
                message=f"Failed to get disk I/O: {e}",
            )
        )

    return metrics


def collect(config: Config | None = None) -> ModuleResult:
    """Run all disk health checks.

    Args:
        config: Optional Config for thresholds.

    Returns:
        ModuleResult with all disk metrics.
    """
    if config is None:
        config = Config()

    metrics: list[MetricValue] = []
    raw_data: dict[str, Any] = {}

    try:
        metrics.extend(collect_disk_partitions(config))
        metrics.extend(collect_disk_io(config))

        return ModuleResult(module="disk", metrics=metrics, raw_data=raw_data)

    except Exception as e:
        return ModuleResult(
            module="disk",
            metrics=metrics,
            raw_data=raw_data,
            error=str(e),
        )


if __name__ == "__main__":
    result = collect()
    print(f"Disk Status: {result.status.value}")
    for m in result.metrics:
        status_icon = {
            HealthStatus.OK: "✓",
            HealthStatus.WARNING: "⚠",
            HealthStatus.CRITICAL: "✗",
            HealthStatus.ERROR: "!",
            HealthStatus.NA: "?",
        }
        print(f"  {status_icon.get(m.status, ' ')} {m.name}: {m.message}")
