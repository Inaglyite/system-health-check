"""Tests for shared data structures in healthcheck.dataclasses."""

from healthcheck.dataclasses import (
    HealthStatus,
    MetricValue,
    ModuleResult,
    Threshold,
)


class TestHealthStatus:
    def test_weight_ordering(self):
        """Higher severity must have higher weight."""
        assert HealthStatus.NA.weight < HealthStatus.WARNING.weight
        assert HealthStatus.OK.weight < HealthStatus.WARNING.weight
        assert HealthStatus.WARNING.weight < HealthStatus.CRITICAL.weight
        assert HealthStatus.CRITICAL.weight < HealthStatus.ERROR.weight

    def test_ok_and_na_both_zero(self):
        """OK and NA are equally non-alarming."""
        assert HealthStatus.OK.weight == 0
        assert HealthStatus.NA.weight == 0


class TestMetricValue:
    def test_status_auto_computed_ok_below_warning(self):
        m = MetricValue(name="x", value=50, threshold=Threshold(80, 95))
        assert m.status == HealthStatus.OK

    def test_status_auto_computed_warning(self):
        m = MetricValue(name="x", value=85, threshold=Threshold(80, 95))
        assert m.status == HealthStatus.WARNING

    def test_status_auto_computed_critical(self):
        m = MetricValue(name="x", value=95, threshold=Threshold(80, 95))
        assert m.status == HealthStatus.CRITICAL

    def test_status_uses_default_when_no_value(self):
        m = MetricValue(name="x")
        assert m.status == HealthStatus.OK

    def test_to_dict_round_trips_status_value(self):
        m = MetricValue(name="temp", value=42.0, unit="C",
                        threshold=Threshold(70, 90))
        d = m.to_dict()
        assert d["value"] == 42.0
        assert d["status"] == "OK"
        assert d["threshold"] == {"warning": 70, "critical": 90}


class TestModuleResult:
    def test_aggregate_status_takes_worst(self):
        m_ok = MetricValue(name="a", value=10, threshold=Threshold(80, 95))
        m_crit = MetricValue(name="b", value=99, threshold=Threshold(80, 95))
        r = ModuleResult(module="x", metrics=[m_ok, m_crit])
        assert r.status == HealthStatus.CRITICAL

    def test_error_forces_error_status(self):
        m_ok = MetricValue(name="a", value=10, threshold=Threshold(80, 95))
        r = ModuleResult(module="x", metrics=[m_ok], error="boom")
        assert r.status == HealthStatus.ERROR
        assert not r.is_healthy

    def test_timestamp_autoset(self):
        r = ModuleResult(module="x")
        assert r.timestamp  # non-empty ISO string

    def test_is_healthy_for_ok_and_na(self):
        assert ModuleResult(module="x").is_healthy
        r_na = ModuleResult(
            module="x",
            metrics=[MetricValue(name="a", status=HealthStatus.NA)],
        )
        assert r_na.is_healthy
