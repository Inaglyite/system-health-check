"""Tests for main.py: exit-code computation, override parsing, module registry."""

import pytest

from healthcheck.dataclasses import HealthStatus, MetricValue, ModuleResult, Threshold
from healthcheck.main import (
    ALL_MODULES,
    MODULE_REGISTRY,
    _filter_quiet,
    compute_exit_code,
    parse_overrides,
)


def _result(status: HealthStatus, error: str | None = None) -> ModuleResult:
    """Build a ModuleResult whose aggregate status is forced via a metric."""
    return ModuleResult(
        module="x",
        metrics=[MetricValue(name="m", status=status)],
        error=error,
    )


class TestExitCode:
    def test_all_ok_returns_0(self):
        assert compute_exit_code([_result(HealthStatus.OK)]) == 0

    def test_na_is_treated_as_ok(self):
        assert compute_exit_code([_result(HealthStatus.NA)]) == 0

    def test_warning_returns_1(self):
        assert compute_exit_code([_result(HealthStatus.WARNING)]) == 1

    def test_critical_returns_2(self):
        assert compute_exit_code([_result(HealthStatus.CRITICAL)]) == 2

    def test_error_returns_3(self):
        assert compute_exit_code([_result(HealthStatus.ERROR)]) == 3

    def test_worst_status_wins(self):
        results = [
            _result(HealthStatus.OK),
            _result(HealthStatus.WARNING),
            _result(HealthStatus.CRITICAL),
        ]
        assert compute_exit_code(results) == 2

    def test_error_dominates_critical(self):
        results = [_result(HealthStatus.CRITICAL), _result(HealthStatus.ERROR)]
        assert compute_exit_code(results) == 3


class TestParseOverrides:
    def test_none_returns_empty(self):
        assert parse_overrides(None) == {}

    def test_single_number(self):
        assert parse_overrides("cpu_percent=90") == {"cpu_percent": 90.0}

    def test_multiple_numbers(self):
        out = parse_overrides("cpu_percent=90,memory_percent=85")
        assert out == {"cpu_percent": 90.0, "memory_percent": 85.0}

    def test_warn_crit_string_form(self):
        out = parse_overrides("memory_percent=70/85")
        assert out == {"memory_percent": "70/85"}

    def test_invalid_value_is_skipped(self, capsys):
        out = parse_overrides("cpu_percent=abc")
        assert out == {}
        captured = capsys.readouterr()
        assert "invalid override" in captured.err

    def test_whitespace_tolerated(self):
        out = parse_overrides(" cpu_percent = 90 , memory_percent = 80 ")
        assert out == {"cpu_percent": 90.0, "memory_percent": 80.0}


class TestModuleRegistry:
    def test_registry_keys_match_all_modules(self):
        assert set(ALL_MODULES) == set(MODULE_REGISTRY.keys())

    def test_every_module_has_collect(self):
        """Every registered module must expose a collect() callable."""
        import importlib

        for name, (path, _desc) in MODULE_REGISTRY.items():
            mod = importlib.import_module(path)
            assert callable(getattr(mod, "collect", None)), (
                f"module {name} ({path}) has no collect()"
            )


class TestQuietFilter:
    def test_keeps_only_non_ok_metrics(self):
        r = ModuleResult(
            module="cpu",
            metrics=[
                MetricValue(name="ok_metric", value=10,
                            threshold=Threshold(80, 95)),
                MetricValue(name="bad_metric", value=99,
                            threshold=Threshold(80, 95)),
            ],
        )
        filtered = _filter_quiet([r])
        assert len(filtered) == 1
        assert len(filtered[0].metrics) == 1
        assert filtered[0].metrics[0].name == "bad_metric"

    def test_drops_fully_ok_module(self):
        r = ModuleResult(
            module="cpu",
            metrics=[MetricValue(name="ok", value=10,
                                 threshold=Threshold(80, 95))],
        )
        assert _filter_quiet([r]) == []
