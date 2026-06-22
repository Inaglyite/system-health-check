"""Tests for Config, with focus on the threshold-override behavior."""

import pytest

from healthcheck.config import Config


class TestDefaultsFromYAML:
    def test_loads_bundled_defaults(self):
        c = Config()
        t = c.get_threshold("cpu.usage_percent")
        assert t is not None
        assert t.warning == 80
        assert t.critical == 95

    def test_unknown_metric_returns_none(self):
        c = Config()
        assert c.get_threshold("does.not.exist") is None

    def test_typed_accessors(self):
        c = Config()
        assert c.sampling_interval == 1.0
        assert c.ping_count == 3
        # ping_targets default is supplied by the YAML
        assert "8.8.8.8" in c.ping_targets


class TestOverridesByCliAlias:
    """The bug: CLI docs said `cpu_percent=90` but the code only matched the
    dotted-path suffix (`usage_percent`), so overrides silently did nothing.
    These tests pin the fixed behavior."""

    def test_cli_alias_critical_only(self):
        c = Config(overrides={"cpu_percent": 90})
        t = c.get_threshold("cpu.usage_percent")
        assert t.critical == 90
        assert t.warning < 90  # derived from critical

    def test_cli_alias_warn_crit_string(self):
        c = Config(overrides={"memory_percent": "70/85"})
        t = c.get_threshold("memory.usage_percent")
        assert t.warning == 70
        assert t.critical == 85

    def test_full_dotted_path_also_accepted(self):
        c = Config(overrides={"cpu.usage_percent": 88})
        t = c.get_threshold("cpu.usage_percent")
        assert t.critical == 88

    def test_override_does_not_leak_to_other_metrics(self):
        c = Config(overrides={"cpu_percent": 90})
        # memory threshold must still come from YAML defaults
        t = c.get_threshold("memory.usage_percent")
        assert t.warning == 80
        assert t.critical == 95

    def test_disk_percent_alias(self):
        c = Config(overrides={"disk_percent": 99})
        t = c.get_threshold("disk.usage_percent")
        assert t.critical == 99


class TestOverrideCoercion:
    def test_derived_warning_is_reasonable(self):
        c = Config(overrides={"cpu_percent": 90})
        t = c.get_threshold("cpu.usage_percent")
        # derived warning should sit between a sensible band and critical
        assert 70 <= t.warning < 90

    def test_warn_crit_string_parses_floats(self):
        c = Config(overrides={"cpu_percent": "79.5/94.5"})
        t = c.get_threshold("cpu.usage_percent")
        assert t.warning == 79.5
        assert t.critical == 94.5
