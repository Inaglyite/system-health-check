"""S.M.A.R.T. disk health check module.

Collects S.M.A.R.T. attributes and overall disk health status.
Windows: Uses PowerShell Get-StorageReliabilityCounter / Get-PhysicalDisk.
Linux: Uses smartctl from smartmontools package.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from typing import Any

from .config import Config
from .dataclasses import HealthStatus, MetricValue, ModuleResult, Threshold


def _check_smartctl_available() -> bool:
    """Check if smartctl is available."""
    return shutil.which("smartctl") is not None


def _collect_smart_windows(config: Config) -> tuple[list[MetricValue], dict[str, Any]]:
    """Collect S.M.A.R.T. data on Windows via PowerShell.

    Uses Get-PhysicalDisk to get disk health status and
    Get-StorageReliabilityCounter for detailed reliability info.
    """
    metrics: list[MetricValue] = []
    raw: dict[str, Any] = {}

    try:
        # Get physical disk health status
        ps_cmd = (
            "Get-PhysicalDisk | "
            "Select-Object DeviceId, FriendlyName, MediaType, HealthStatus, "
            "OperationalStatus, Size, BusType | "
            "ConvertTo-Json"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0 or not result.stdout.strip():
            metrics.append(
                MetricValue(
                    name="smart_status",
                    status=HealthStatus.NA,
                    message="S.M.A.R.T. not available (no physical disk data)",
                )
            )
            return metrics, raw

        disks = json.loads(result.stdout)
        if isinstance(disks, dict):
            disks = [disks]

        for disk in disks:
            disk_id = disk.get("DeviceId", "unknown")
            disk_name = disk.get("FriendlyName", f"PhysicalDisk{disk_id}")
            health = disk.get("HealthStatus", "Unknown")
            media = disk.get("MediaType", "Unknown")
            size_gb = round(disk.get("Size", 0) / (1024 ** 3), 1) if disk.get("Size") else 0

            raw[f"disk_{disk_id}"] = disk

            # Map Windows health status to our HealthStatus
            if health == "Healthy":
                status = HealthStatus.OK
                message = f"{disk_name}: Healthy"
            elif health == "Warning":
                status = HealthStatus.WARNING
                message = f"{disk_name}: Warning - disk may need attention"
            else:
                status = HealthStatus.CRITICAL
                message = f"{disk_name}: {health} - disk needs immediate attention"

            metrics.append(
                MetricValue(
                    name=f"smart_health_disk{disk_id}",
                    value=None,
                    status=status,
                    message=f"{message} ({media}, {size_gb:.1f} GB, {disk.get('BusType', 'N/A')})",
                    extra={
                        "device_id": disk_id,
                        "name": disk_name,
                        "media_type": media,
                        "size_gb": size_gb,
                        "health_status": health,
                        "bus_type": disk.get("BusType", ""),
                    },
                )
            )

        # Attempt to get reliability counters (more detailed SMART info)
        try:
            rel_cmd = (
                "Get-PhysicalDisk | Get-StorageReliabilityCounter | "
                "Select-Object DeviceId, Temperature, ReadErrorsTotal, "
                "WriteErrorsTotal, Wear, PowerOnHours | "
                "ConvertTo-Json"
            )
            rel_result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", rel_cmd],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if rel_result.returncode == 0 and rel_result.stdout.strip():
                rel_data = json.loads(rel_result.stdout)
                if isinstance(rel_data, dict):
                    rel_data = [rel_data]

                for rel in rel_data:
                    disk_id = rel.get("DeviceId", "unknown")
                    raw[f"disk_{disk_id}_reliability"] = rel

                    temp = rel.get("Temperature")
                    if temp is not None:
                        temp_threshold = config.get_threshold("smart.temperature_celsius")
                        metrics.append(
                            MetricValue(
                                name=f"smart_temp_disk{disk_id}",
                                value=float(temp),
                                unit="°C",
                                threshold=temp_threshold,
                                message=f"Disk {disk_id} temperature: {temp}°C",
                            )
                        )

                    wear = rel.get("Wear")
                    if wear is not None:
                        metrics.append(
                            MetricValue(
                                name=f"smart_wear_disk{disk_id}",
                                value=float(wear),
                                unit="%",
                                threshold=Threshold(warning=80, critical=95),
                                message=f"Disk {disk_id} wear: {wear}%",
                            )
                        )

                    power_hours = rel.get("PowerOnHours")
                    if power_hours is not None:
                        metrics.append(
                            MetricValue(
                                name=f"smart_poweron_disk{disk_id}",
                                value=float(power_hours),
                                unit="hours",
                                message=f"Disk {disk_id} power-on hours: {power_hours}",
                            )
                        )

                    read_errors = rel.get("ReadErrorsTotal")
                    if read_errors is not None and read_errors > 0:
                        metrics.append(
                            MetricValue(
                                name=f"smart_read_errors_disk{disk_id}",
                                value=float(read_errors),
                                threshold=Threshold(warning=1, critical=10),
                                message=f"Disk {disk_id} read errors: {read_errors}",
                            )
                        )
        except Exception:
            pass  # Reliability counters are optional

    except subprocess.TimeoutExpired:
        metrics.append(
            MetricValue(
                name="smart_status",
                status=HealthStatus.ERROR,
                message="S.M.A.R.T. check timed out",
            )
        )
    except Exception as e:
        metrics.append(
            MetricValue(
                name="smart_status",
                status=HealthStatus.ERROR,
                message=f"S.M.A.R.T. check failed: {e}",
            )
        )

    return metrics, raw


def _collect_smart_linux(config: Config) -> tuple[list[MetricValue], dict[str, Any]]:
    """Collect S.M.A.R.T. data on Linux via smartctl."""
    metrics: list[MetricValue] = []
    raw: dict[str, Any] = {}

    if not _check_smartctl_available():
        metrics.append(
            MetricValue(
                name="smart_status",
                status=HealthStatus.NA,
                message="smartctl not installed. Install smartmontools package.",
            )
        )
        return metrics, raw

    # Determine which devices to check
    devices = config.smart_devices
    if not devices:
        # Auto-detect: find all /dev/sdX and /dev/nvmeXnY devices
        import glob
        devices = sorted(glob.glob("/dev/sd?")) + sorted(glob.glob("/dev/nvme?n?"))
        if not devices:
            metrics.append(
                MetricValue(
                    name="smart_status",
                    status=HealthStatus.NA,
                    message="No disk devices found for S.M.A.R.T. check",
                )
            )
            return metrics, raw

    for device in devices:
        device_name = device.split("/")[-1]
        try:
            result = subprocess.run(
                ["smartctl", "-a", "-j", device],
                capture_output=True,
                text=True,
                timeout=15,
            )

            # Permission denied — skip gracefully
            if "Permission denied" in result.stderr or "requires a device" in result.stderr:
                metrics.append(
                    MetricValue(
                        name=f"smart_health_{device_name}",
                        status=HealthStatus.NA,
                        message=f"Cannot access {device}: permission denied (run as root)",
                    )
                )
                continue

            if result.returncode & 0x3F:  # bit 0-5: command error
                # smartctl returns bit 0-5 for errors, bit 6 for smart errors
                metrics.append(
                    MetricValue(
                        name=f"smart_health_{device_name}",
                        status=HealthStatus.ERROR,
                        message=f"smartctl error on {device}: {result.stderr.strip() or 'unknown error'}",
                    )
                )
                continue

            data = json.loads(result.stdout)
            raw[device_name] = data

            # Overall health
            smart_status = data.get("smart_status", {})
            passed = smart_status.get("passed", False)
            if passed:
                status = HealthStatus.OK
                msg = f"{device}: S.M.A.R.T. health PASSED"
            else:
                status = HealthStatus.CRITICAL
                msg = f"{device}: S.M.A.R.T. health FAILED"

            # Device info
            model = data.get("model_name", "") or data.get("model_family", "")
            serial = data.get("serial_number", "")
            capacity_gb: float = 0.0
            capacity = data.get("user_capacity", "")
            if capacity:
                try:
                    capacity_gb = round(
                        int(capacity.replace(",", "").split()[0]) / 1e9, 1
                    )
                except (ValueError, IndexError):
                    capacity_gb = 0.0

            if model:
                detail = f"{msg} ({model}, {capacity_gb:.1f} GB)"
            else:
                detail = msg
            metrics.append(
                MetricValue(
                    name=f"smart_health_{device_name}",
                    value=None,
                    status=status,
                    message=detail,
                    extra={
                        "device": device,
                        "model": model,
                        "serial": serial,
                        "passed": passed,
                    },
                )
            )

            # Parse individual S.M.A.R.T. attributes
            attrs = data.get("ata_smart_attributes", {}).get("table", [])
            key_attrs = {
                "Reallocated_Sector_Ct": "reallocated_sectors",
                "Current_Pending_Sector": "pending_sectors",
                "Offline_Uncorrectable": "uncorrectable_sectors",
                "Temperature_Celsius": "temperature_celsius",
                "Power_On_Hours": "power_on_hours",
                "Wear_Leveling_Count": "wear_level",
                "Program_Fail_Count": "program_fail",
                "Erase_Fail_Count": "erase_fail",
                "Unused_Rsvd_Blk_Cnt": "reserved_blocks",
            }

            for attr in attrs:
                attr_name = attr.get("name", "")
                if attr_name in key_attrs:
                    raw_val = attr.get("raw", {}).get("value", 0)
                    val = float(raw_val) if raw_val is not None else 0
                    metric_key = key_attrs[attr_name]

                    # Get threshold for this metric
                    threshold = config.get_threshold(f"smart.{metric_key}")
                    if metric_key == "temperature_celsius":
                        threshold = config.get_threshold("smart.temperature_celsius")

                    metrics.append(
                        MetricValue(
                            name=f"smart_{metric_key}_{device_name}",
                            value=val,
                            unit=("°C" if "temp" in metric_key.lower() else ""),
                            threshold=threshold,
                            message=f"{device}: {attr_name} = {raw_val}",
                        )
                    )

        except subprocess.TimeoutExpired:
            metrics.append(
                MetricValue(
                    name=f"smart_health_{device_name}",
                    status=HealthStatus.ERROR,
                    message=f"S.M.A.R.T. check timed out for {device}",
                )
            )
        except (json.JSONDecodeError, KeyError) as e:
            metrics.append(
                MetricValue(
                    name=f"smart_health_{device_name}",
                    status=HealthStatus.ERROR,
                    message=f"Failed to parse S.M.A.R.T. data for {device}: {e}",
                )
            )
        except Exception as e:
            metrics.append(
                MetricValue(
                    name=f"smart_health_{device_name}",
                    status=HealthStatus.ERROR,
                    message=f"Error checking {device}: {e}",
                )
            )

    return metrics, raw


def collect_smart_attributes(config: Config | None = None) -> ModuleResult:
    """Collect S.M.A.R.T. health status for all disks.

    Args:
        config: Optional Config for thresholds.

    Returns:
        ModuleResult with S.M.A.R.T. metrics.
    """
    if config is None:
        config = Config()

    metrics: list[MetricValue] = []
    raw_data: dict[str, Any] = {}

    try:
        if platform.system() == "Windows":
            metrics, raw_data = _collect_smart_windows(config)
        else:
            metrics, raw_data = _collect_smart_linux(config)

        return ModuleResult(
            module="smart",
            metrics=metrics,
            raw_data=raw_data,
        )

    except Exception as e:
        return ModuleResult(
            module="smart",
            metrics=metrics,
            raw_data=raw_data,
            error=str(e),
        )


# Alias for consistency with other modules
collect = collect_smart_attributes


if __name__ == "__main__":
    result = collect()
    print(f"SMART Status: {result.status.value}")
    for m in result.metrics:
        status_icon = {
            HealthStatus.OK: "✓",
            HealthStatus.WARNING: "⚠",
            HealthStatus.CRITICAL: "✗",
            HealthStatus.ERROR: "!",
            HealthStatus.NA: "?",
        }
        print(f"  {status_icon.get(m.status, ' ')} {m.name}: {m.message}")
