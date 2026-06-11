"""Temperature health check module.

Collects CPU and GPU temperature readings.
Windows: WMI MSAcpi_ThermalZoneTemperature (may not be available on VMs).
Linux: psutil sensors_temperatures() via lm-sensors.
Both: nvidia-smi for GPU temp if NVIDIA GPU present.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from typing import Any

from .config import Config
from .dataclasses import HealthStatus, MetricValue, ModuleResult


def _collect_temps_windows() -> tuple[list[MetricValue], dict[str, Any]]:
    """Collect temperatures on Windows via WMI.

    Note: Most VMs and many physical Windows machines do not expose
    thermal zones through WMI, so this often returns N/A.
    """
    metrics: list[MetricValue] = []
    raw: dict[str, Any] = {}

    try:
        # Try WMI thermal zone
        ps_cmd = (
            "Get-CimInstance -Namespace root/wmi MSAcpi_ThermalZoneTemperature | "
            "Select-Object InstanceName, CurrentTemperature | "
            "ConvertTo-Json"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]

            for entry in data:
                name = entry.get("InstanceName", "CPU")
                temp_k = entry.get("CurrentTemperature", 0)
                # WMI returns temperature in tenths of Kelvin
                temp_c = round((temp_k / 10.0) - 273.15, 1)

                raw[f"thermal_zone_{name}"] = {
                    "name": name,
                    "temperature_celsius": temp_c,
                    "raw_kelvin_tenths": temp_k,
                }

                metrics.append(
                    MetricValue(
                        name=f"temp_{name.lower().replace(' ', '_')}",
                        value=temp_c,
                        unit="°C",
                        message=f"{name}: {temp_c}°C",
                    )
                )

        if not metrics:
            metrics.append(
                MetricValue(
                    name="temp_cpu",
                    status=HealthStatus.NA,
                    message="CPU temperature not available via WMI "
                    "(common on VMs and servers without thermal drivers)",
                )
            )
    except Exception as e:
        metrics.append(
            MetricValue(
                name="temp_cpu",
                status=HealthStatus.NA,
                message=f"CPU temperature not available: {e}",
            )
        )

    return metrics, raw


def _collect_temps_linux() -> tuple[list[MetricValue], dict[str, Any]]:
    """Collect temperatures on Linux via psutil (lm-sensors)."""
    metrics: list[MetricValue] = []
    raw: dict[str, Any] = {}

    try:
        import psutil
        sensors = psutil.sensors_temperatures()
        if not sensors:
            metrics.append(
                MetricValue(
                    name="temp_cpu",
                    status=HealthStatus.NA,
                    message="No temperature sensors found. "
                    "Install lm-sensors and run sensors-detect.",
                )
            )
            return metrics, raw

        for chip_name, entries in sensors.items():
            for entry in entries:
                if entry.current is None:
                    continue

                raw[f"{chip_name}_{entry.label or 'unknown'}"] = {
                    "chip": chip_name,
                    "label": entry.label,
                    "current": entry.current,
                    "high": entry.high,
                    "critical": entry.critical,
                }

                metrics.append(
                    MetricValue(
                        name=f"temp_{chip_name.replace('-', '_')}_{entry.label or 'sensor'}".lower(),
                        value=round(entry.current, 1),
                        unit="°C",
                        message=f"{chip_name}/{entry.label or 'sensor'}: {entry.current:.1f}°C",
                    )
                )
    except Exception as e:
        metrics.append(
            MetricValue(
                name="temp_cpu",
                status=HealthStatus.ERROR,
                message=f"Error reading temperature sensors: {e}",
            )
        )

    return metrics, raw


def _collect_nvidia_gpu_temp() -> tuple[list[MetricValue], dict[str, Any]]:
    """Collect NVIDIA GPU temperature via nvidia-smi if available."""
    metrics: list[MetricValue] = []
    raw: dict[str, Any] = {}

    if not shutil.which("nvidia-smi"):
        return metrics, raw

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    idx, name, temp, util, mem_used, mem_total = parts[:6]

                    raw[f"gpu_{idx}"] = {
                        "index": idx,
                        "name": name,
                        "temperature": float(temp) if temp else None,
                        "utilization": float(util) if util else None,
                        "memory_used_mb": float(mem_used) if mem_used else None,
                        "memory_total_mb": float(mem_total) if mem_total else None,
                    }

                    if temp:
                        metrics.append(
                            MetricValue(
                                name=f"temp_gpu_{idx}",
                                value=float(temp),
                                unit="°C",
                                message=f"GPU {idx} ({name}): {temp}°C",
                            )
                        )
    except Exception:
        pass

    return metrics, raw


def collect_temperatures(config: Config | None = None) -> ModuleResult:
    """Collect CPU and GPU temperature readings.

    Args:
        config: Config for temperature thresholds.

    Returns:
        ModuleResult with temperature metrics.
    """
    if config is None:
        config = Config()

    metrics: list[MetricValue] = []
    raw_data: dict[str, Any] = {}

    try:
        # Platform-specific CPU temps
        if platform.system() == "Windows":
            cpu_metrics, cpu_raw = _collect_temps_windows()
        else:
            cpu_metrics, cpu_raw = _collect_temps_linux()

        # Apply thresholds
        cpu_threshold = config.get_threshold("temperature.cpu_celsius")
        if cpu_threshold:
            for m in cpu_metrics:
                if m.value is not None and m.threshold is None:
                    m.threshold = cpu_threshold
                    # Re-compute status
                    if m.value >= cpu_threshold.critical:
                        m.status = HealthStatus.CRITICAL
                    elif m.value >= cpu_threshold.warning:
                        m.status = HealthStatus.WARNING

        metrics.extend(cpu_metrics)
        raw_data.update(cpu_raw)

        # GPU temps (nvidia)
        gpu_metrics, gpu_raw = _collect_nvidia_gpu_temp()
        gpu_threshold = config.get_threshold("temperature.gpu_celsius")
        if gpu_threshold:
            for m in gpu_metrics:
                if m.value is not None and m.threshold is None:
                    m.threshold = gpu_threshold
                    if m.value >= gpu_threshold.critical:
                        m.status = HealthStatus.CRITICAL
                    elif m.value >= gpu_threshold.warning:
                        m.status = HealthStatus.WARNING

        metrics.extend(gpu_metrics)
        raw_data.update(gpu_raw)

        return ModuleResult(
            module="temperature",
            metrics=metrics,
            raw_data=raw_data,
        )

    except Exception as e:
        return ModuleResult(
            module="temperature",
            metrics=metrics,
            raw_data=raw_data,
            error=str(e),
        )


# Alias for consistency
collect = collect_temperatures


if __name__ == "__main__":
    result = collect()
    print(f"Temperature Status: {result.status.value}")
    for m in result.metrics:
        status_icon = {
            HealthStatus.OK: "✓",
            HealthStatus.WARNING: "⚠",
            HealthStatus.CRITICAL: "✗",
            HealthStatus.ERROR: "!",
            HealthStatus.NA: "?",
        }
        print(f"  {status_icon.get(m.status, ' ')} {m.name}: {m.message}")
