"""Shared data structures for all health check modules."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class HealthStatus(Enum):
    """Health status with severity weight for aggregation (higher = worse)."""

    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    NA = "N/A"

    @property
    def weight(self) -> int:
        """Return severity weight for status comparison."""
        _weights = {
            HealthStatus.NA: 0,
            HealthStatus.OK: 0,
            HealthStatus.WARNING: 1,
            HealthStatus.CRITICAL: 2,
            HealthStatus.ERROR: 3,
        }
        return _weights[self]


@dataclass
class Threshold:
    """Threshold values for a metric."""

    warning: float
    critical: float

    def to_dict(self) -> dict[str, float]:
        return {"warning": self.warning, "critical": self.critical}


@dataclass
class MetricValue:
    """A single metric measurement with computed health status.

    Status is auto-computed from threshold in __post_init__.
    For metrics where higher is worse (usage%, temperature), set
    value and threshold normally. For metrics where lower is worse
    (free space), handle the inversion in the module logic.
    """

    name: str
    value: Optional[float] = None
    unit: str = ""
    status: HealthStatus = HealthStatus.OK
    message: str = ""
    threshold: Optional[Threshold] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Auto-compute status from threshold if value is present."""
        if self.value is not None and self.threshold is not None:
            if self.value >= self.threshold.critical:
                self.status = HealthStatus.CRITICAL
            elif self.value >= self.threshold.warning:
                self.status = HealthStatus.WARNING
            else:
                self.status = HealthStatus.OK

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "message": self.message,
            "threshold": self.threshold.to_dict() if self.threshold else None,
            "extra": self.extra,
        }


@dataclass
class ModuleResult:
    """Result from a single health check module.

    Aggregate status is the worst status among all metrics.
    If error is set, status becomes ERROR regardless of metrics.
    """

    module: str
    timestamp: str = ""
    status: HealthStatus = HealthStatus.OK
    metrics: list[MetricValue] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def __post_init__(self) -> None:
        """Set timestamp and compute aggregate status from metrics."""
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if self.error:
            self.status = HealthStatus.ERROR
        else:
            # Worst metric status wins
            worst = HealthStatus.OK
            for m in self.metrics:
                if m.status.weight > worst.weight:
                    worst = m.status
            self.status = worst

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "module": self.module,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "metrics": [m.to_dict() for m in self.metrics],
            "raw_data": self.raw_data,
            "error": self.error,
        }

    @property
    def is_healthy(self) -> bool:
        """Return True if status is OK or NA."""
        return self.status in (HealthStatus.OK, HealthStatus.NA)
