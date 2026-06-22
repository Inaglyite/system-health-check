"""Configuration loader for system health check tool.

Loads YAML config file with per-metric thresholds and general settings.
Supports CLI overrides for individual thresholds.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from .dataclasses import Threshold

# Default config bundled with the package
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"

# Map CLI override keys (what users pass via --threshold-override) to the dotted
# metric paths they should affect. Users may write either form; both work.
_OVERRIDE_ALIASES: dict[str, list[str]] = {
    "cpu_percent": ["cpu.usage_percent"],
    "cpu_celsius": ["cpu.temperature_celsius"],
    "memory_percent": ["memory.usage_percent"],
    "swap_percent": ["memory.swap_percent"],
    "disk_percent": ["disk.usage_percent"],
    "inode_percent": ["disk.inode_percent"],
    "smart_temp_celsius": ["smart.temperature_celsius"],
    "packet_loss_percent": ["network.packet_loss_percent"],
    "latency_ms": ["network.latency_ms"],
    "gpu_celsius": ["temperature.gpu_celsius"],
}


def _override_warning(critical: float) -> float:
    """Derive a sane warning level from a critical level when only one is given.

    Uses 80% of critical, clamped to a reasonable range so tiny or huge
    critical values still produce a useful warning band.
    """
    return round(min(critical * 0.8, critical - 5), 1)


class Config:
    """Health check configuration with threshold definitions.

    Loads from a YAML file and provides typed access to thresholds
    and general settings. CLI overrides are merged on top.
    """

    def __init__(
        self,
        config_path: Optional[str | Path] = None,
        overrides: Optional[dict[str, float]] = None,
    ) -> None:
        """Load config from file.

        Args:
            config_path: Path to YAML config file. Uses bundled default if None.
            overrides: Dict of metric_name -> value to override thresholds.
        """
        self._path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        self._data: dict[str, Any] = {}
        self._overrides = overrides or {}
        self._load()

    def _load(self) -> None:
        """Load and merge YAML config."""
        # Load bundled defaults
        try:
            with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            self._data = {}

        # Merge user config on top if it's different
        if self._path != _DEFAULT_CONFIG_PATH and self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                user_data = yaml.safe_load(f) or {}
            self._deep_merge(self._data, user_data)

    @staticmethod
    def _deep_merge(base: dict, overlay: dict) -> None:
        """Recursively merge overlay into base."""
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                Config._deep_merge(base[key], value)
            else:
                base[key] = value

    def get_threshold(self, metric_path: str) -> Optional[Threshold]:
        """Get threshold for a metric by dotted path (e.g., 'cpu.usage_percent').

        Checks overrides first, then config data.

        Overrides may be supplied in any of these forms per key:
            "cpu_percent" -> 90                  # critical only; warning derived
            "cpu_percent" -> "80/90"             # warning/critical as string
            "cpu.usage_percent" -> 90            # full dotted path also accepted
        The CLI key (e.g. 'cpu_percent') is matched via _OVERRIDE_ALIASES so it
        resolves to the same threshold as the dotted metric path.
        """
        if self._overrides:
            threshold = self._lookup_override(metric_path)
            if threshold is not None:
                return threshold

        # Navigate nested config
        parts = metric_path.split(".")
        node: Any = self._data
        try:
            for part in parts:
                node = node[part]
            if isinstance(node, dict) and "warning" in node and "critical" in node:
                return Threshold(warning=node["warning"], critical=node["critical"])
        except (KeyError, TypeError):
            pass
        return None

    def _lookup_override(self, metric_path: str) -> Optional[Threshold]:
        """Find an override value matching the given metric path, if any.

        Tries the full dotted path, the last segment, and any alias that maps
        to the dotted path. Returns None if no override applies.
        """
        candidates: list[str] = [metric_path, metric_path.split(".")[-1]]
        # Add CLI alias keys whose dotted path equals metric_path
        for alias, paths in _OVERRIDE_ALIASES.items():
            if metric_path in paths:
                candidates.append(alias)

        for key in candidates:
            if key in self._overrides:
                return self._coerce_override(self._overrides[key])
        return None

    @staticmethod
    def _coerce_override(val: Any) -> Threshold:
        """Coerce a raw override value into a Threshold.

        Accepts a number (treated as critical) or a 'warning/critical' string.
        """
        if isinstance(val, str) and "/" in val:
            w_str, c_str = val.split("/", 1)
            return Threshold(warning=float(w_str), critical=float(c_str))
        critical = float(val)
        return Threshold(warning=_override_warning(critical), critical=critical)

    def get(self, path: str, default: Any = None) -> Any:
        """Get arbitrary config value by dotted path."""
        parts = path.split(".")
        node: Any = self._data
        try:
            for part in parts:
                node = node[part]
            return node
        except (KeyError, TypeError):
            return default

    @property
    def sampling_interval(self) -> float:
        """CPU sampling interval in seconds."""
        return float(self.get("general.sampling_interval", 1.0))

    @property
    def ping_targets(self) -> list[str]:
        """List of hosts to ping for connectivity check."""
        return self.get("network.ping_targets", ["8.8.8.8", "1.1.1.1"])

    @property
    def ping_count(self) -> int:
        """Number of pings per target."""
        return int(self.get("network.ping_count", 3))

    @property
    def ping_timeout(self) -> float:
        """Ping timeout in seconds."""
        return float(self.get("network.ping_timeout", 2.0))

    @property
    def smart_devices(self) -> list[str]:
        """List of disk devices to check with SMART."""
        return self.get("smart.devices", [])

    @property
    def output_dir(self) -> str:
        """Default output directory for reports."""
        return str(self.get("general.output_dir", "."))
