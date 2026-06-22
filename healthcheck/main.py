#!/usr/bin/env python3
"""System Health Check - Main Entry Point.

Orchestrates all health check modules and generates reports.

Usage:
    python -m healthcheck.main [options]
    healthcheck [options]  # if installed as package
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable

from .config import Config
from .dataclasses import HealthStatus, ModuleResult
from .report import generate_report

# Module registry: name -> (import_path, description)
MODULE_REGISTRY: dict[str, tuple[str, str]] = {
    "cpu": ("healthcheck.cpu", "CPU usage, frequency, and load average"),
    "memory": ("healthcheck.memory", "RAM and swap usage"),
    "disk": ("healthcheck.disk", "Disk partitions, usage, and I/O"),
    "smart": ("healthcheck.smart", "S.M.A.R.T. disk health status"),
    "network": ("healthcheck.network", "Network interfaces, I/O, and ping test"),
    "temperature": ("healthcheck.temperature", "CPU and GPU temperatures"),
}

ALL_MODULES = list(MODULE_REGISTRY.keys())


def _import_module(name: str) -> Callable:
    """Lazy-import a health check module and return its collect() function.

    Args:
        name: Module short name (e.g., 'cpu', 'memory').

    Returns:
        The module's collect() callable.

    Raises:
        ImportError: If the module cannot be imported.
        AttributeError: If the module has no collect().
    """
    import importlib
    module_path, _ = MODULE_REGISTRY[name]
    mod = importlib.import_module(module_path)
    return mod.collect


def run_checks(
    modules: list[str] | None = None,
    config: Config | None = None,
    **kwargs: Any,
) -> list[ModuleResult]:
    """Run health checks for specified modules.

    Args:
        modules: List of module names to run. None means all.
        config: Config instance. Creates default if None.
        **kwargs: Extra arguments passed to each module's collect().

    Returns:
        List of ModuleResult, one per checked module.
    """
    if config is None:
        config = Config()

    if modules is None:
        modules = ALL_MODULES

    results: list[ModuleResult] = []

    for mod_name in modules:
        if mod_name not in MODULE_REGISTRY:
            results.append(
                ModuleResult(
                    module=mod_name,
                    error=f"Unknown module: {mod_name}",
                )
            )
            continue

        try:
            collect_fn = _import_module(mod_name)
            result = collect_fn(config=config, **kwargs)
            results.append(result)
        except ImportError as e:
            results.append(
                ModuleResult(
                    module=mod_name,
                    error=f"Failed to import module: {e}",
                )
            )
        except Exception as e:
            results.append(
                ModuleResult(
                    module=mod_name,
                    error=f"Unexpected error: {e}",
                )
            )

    return results


def compute_exit_code(results: list[ModuleResult]) -> int:
    """Compute CLI exit code from results.

    0 = OK (all healthy)
    1 = WARNING (at least one warning)
    2 = CRITICAL (at least one critical)
    3 = ERROR (at least one error)
    """
    worst = HealthStatus.OK
    for r in results:
        if r.status.weight > worst.weight:
            worst = r.status

    exit_codes = {
        HealthStatus.OK: 0,
        HealthStatus.NA: 0,
        HealthStatus.WARNING: 1,
        HealthStatus.CRITICAL: 2,
        HealthStatus.ERROR: 3,
    }
    return exit_codes.get(worst, 3)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="healthcheck",
        description="Cross-platform system health check tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available modules:
{chr(10).join(f'  {n:<14} {d}' for n, (_, d) in MODULE_REGISTRY.items())}

Exit codes:
  0  All checks OK
  1  WARNING level issues found
  2  CRITICAL issues found
  3  Errors occurred during checks

Examples:
  healthcheck                              # Run all checks, console output
  healthcheck -o json                      # JSON output
  healthcheck -o html -f report.html       # HTML report to file
  healthcheck -m cpu memory disk           # Only specific modules
  healthcheck -v                           # Verbose (per-core CPU, etc.)
  healthcheck -q                           # Quiet (only summary and errors)
  healthcheck --threshold-override cpu_percent=90,memory_percent=85
        """,
    )

    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="Path to YAML config file (default: built-in config.yaml)",
    )
    parser.add_argument(
        "-o", "--output-format",
        choices=["console", "json", "html"],
        default="console",
        help="Output format (default: console)",
    )
    parser.add_argument(
        "-f", "--output-file",
        type=str,
        default=None,
        help="Write report to file instead of stdout",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output (per-core CPU, extra details)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Quiet mode: only show summary and errors",
    )
    parser.add_argument(
        "-m", "--modules",
        type=str,
        default=None,
        help=(
            "Comma-separated list of modules to run "
            "(default: all). Available: "
            + ", ".join(ALL_MODULES)
        ),
    )
    parser.add_argument(
        "--threshold-override",
        type=str,
        default=None,
        help=(
            "Override thresholds, format: key=value pairs separated by commas. "
            "Value can be a number (critical only) or 'warn/c crit'. "
            "Keys: cpu_percent, memory_percent, disk_percent, "
            "swap_percent, cpu_celsius, gpu_celsius"
        ),
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output (console mode only)",
    )
    parser.add_argument(
        "--list-modules",
        action="store_true",
        help="List available modules and exit",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    return parser


def parse_overrides(override_str: str | None) -> dict[str, float | str]:
    """Parse --threshold-override string into dict.

    Format: "key1=value1,key2=value2"
    Each value is either a number (treated as critical) or "warning/critical".
    """
    if not override_str:
        return {}
    overrides: dict[str, float | str] = {}
    for part in override_str.split(","):
        part = part.strip()
        if "=" in part:
            key, val = part.split("=", 1)
            key = key.strip()
            val = val.strip()
            if "/" in val:
                # warning/critical form — keep as string, validated by Config
                overrides[key] = val
            else:
                try:
                    overrides[key] = float(val)
                except ValueError:
                    print(f"Warning: invalid override value '{part}'", file=sys.stderr)
    return overrides


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments (None = sys.argv).

    Returns:
        Exit code: 0=OK, 1=WARNING, 2=CRITICAL, 3=ERROR.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Handle special flags
    if args.version:
        from . import __version__
        print(f"healthcheck v{__version__}")
        return 0

    if args.list_modules:
        print("Available modules:")
        for name, (_, desc) in MODULE_REGISTRY.items():
            print(f"  {name:<14} {desc}")
        return 0

    # Parse module list
    modules: list[str] | None = None
    if args.modules:
        modules = [m.strip() for m in args.modules.split(",") if m.strip()]
        invalid = [m for m in modules if m not in MODULE_REGISTRY]
        if invalid:
            print(f"Error: Unknown modules: {', '.join(invalid)}", file=sys.stderr)
            print(f"Available: {', '.join(ALL_MODULES)}", file=sys.stderr)
            return 3

    # Parse threshold overrides
    overrides = parse_overrides(args.threshold_override)

    # Load config
    try:
        config = Config(
            config_path=args.config,
            overrides=overrides,
        )
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 3

    # Run health checks
    kwargs: dict[str, Any] = {}
    if args.verbose:
        kwargs["per_cpu"] = True

    results = run_checks(modules=modules, config=config, **kwargs)

    # Filter quiet output
    if args.quiet and args.output_format == "console":
        results = _filter_quiet(results)

    # Generate report
    generate_report(
        results,
        format=args.output_format,
        output_file=args.output_file,
        use_color=not args.no_color,
    )

    # Compute exit code
    return compute_exit_code(results)


def _filter_quiet(results: list[ModuleResult]) -> list[ModuleResult]:
    """In quiet mode, only keep non-OK metrics."""
    filtered: list[ModuleResult] = []
    for r in results:
        # Keep error/warning/critical metrics
        important = [
            m for m in r.metrics
            if m.status not in (HealthStatus.OK, HealthStatus.NA)
        ]
        if important or r.status != HealthStatus.OK:
            filtered.append(
                ModuleResult(
                    module=r.module,
                    timestamp=r.timestamp,
                    metrics=important,
                    error=r.error,
                )
            )
    return filtered


if __name__ == "__main__":
    sys.exit(main())
