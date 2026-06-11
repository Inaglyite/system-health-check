"""Report generation for system health check results.

Supports three output formats:
- console: Rich-formatted terminal output with colors and tables
- json: Machine-readable JSON output
- html: Self-contained HTML report
"""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from .dataclasses import HealthStatus, ModuleResult

# Rich imports are optional for JSON/HTML modes
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.layout import Layout
    from rich import box

    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class BaseReport(ABC):
    """Abstract base class for report generators."""

    @abstractmethod
    def generate(self, results: list[ModuleResult]) -> str:
        """Generate report string from module results."""
        ...

    @abstractmethod
    def output(self, results: list[ModuleResult], file: Optional[str] = None) -> None:
        """Output the report to console or file."""
        ...


class JSONReport(BaseReport):
    """Generate JSON report."""

    def __init__(self, pretty: bool = True) -> None:
        self.pretty = pretty

    def generate(self, results: list[ModuleResult]) -> str:
        """Generate JSON report."""
        # Compute overall status
        worst = HealthStatus.OK
        for r in results:
            if r.status.weight > worst.weight:
                worst = r.status

        report: dict[str, Any] = {
            "report": {
                "generated_at": datetime.now().isoformat(),
                "overall_status": worst.value,
                "modules_checked": len(results),
                "healthy_modules": sum(
                    1 for r in results if r.status in (HealthStatus.OK, HealthStatus.NA)
                ),
                "warning_modules": sum(
                    1 for r in results if r.status == HealthStatus.WARNING
                ),
                "critical_modules": sum(
                    1 for r in results if r.status == HealthStatus.CRITICAL
                ),
                "error_modules": sum(
                    1 for r in results if r.status == HealthStatus.ERROR
                ),
            },
            "modules": [r.to_dict() for r in results],
        }

        indent = 2 if self.pretty else None
        return json.dumps(report, indent=indent, ensure_ascii=False)

    def output(self, results: list[ModuleResult], file: Optional[str] = None) -> None:
        """Write JSON report to file or stdout."""
        content = self.generate(results)
        if file:
            with open(file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"JSON report saved to {file}")
        else:
            print(content)


class ConsoleReport(BaseReport):
    """Generate colored console report using Rich."""

    STATUS_STYLES = {
        HealthStatus.OK: "green",
        HealthStatus.WARNING: "yellow",
        HealthStatus.CRITICAL: "red",
        HealthStatus.ERROR: "bold red",
        HealthStatus.NA: "dim",
    }

    STATUS_ICONS = {
        HealthStatus.OK: "✓",
        HealthStatus.WARNING: "⚠",
        HealthStatus.CRITICAL: "✗",
        HealthStatus.ERROR: "!",
        HealthStatus.NA: "?",
    }

    # ASCII-safe fallback for non-UTF-8 terminals (e.g., Chinese Windows GBK)
    STATUS_ICONS_ASCII = {
        HealthStatus.OK: "OK",
        HealthStatus.WARNING: "WARN",
        HealthStatus.CRITICAL: "FAIL",
        HealthStatus.ERROR: "ERR",
        HealthStatus.NA: "N/A",
    }

    def __init__(self, use_color: bool = True) -> None:
        self.use_color = use_color

    def _make_table(self, result: ModuleResult, ascii_only: bool = False) -> Table:
        """Create a Rich table for a single module's metrics."""
        icons = self.STATUS_ICONS_ASCII if ascii_only else self.STATUS_ICONS
        title_style = self.STATUS_STYLES.get(result.status, "")
        icon = icons.get(result.status, result.status.value)
        table = Table(
            title=f"{icon} {result.module.upper()} - {result.status.value}",
            title_style=title_style,
            box=box.ROUNDED,
            show_header=True,
            header_style="bold",
        )
        table.add_column("Status", style="bold", width=6)
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_column("Message", style="dim")

        for m in result.metrics:
            status_icon = icons.get(m.status, " ")
            status_style = self.STATUS_STYLES.get(m.status, "")

            value_str = ""
            if m.value is not None:
                value_str = f"{m.value} {m.unit}".strip()

            table.add_row(
                f"[{status_style}]{status_icon}[/]",
                m.name,
                value_str,
                m.message,
            )

        if result.error:
            table.add_row(
                f"[red]ERR[/]",
                "ERROR",
                "",
                f"[red]{result.error}[/]",
            )

        return table

    def generate(self, results: list[ModuleResult]) -> str:
        """Generate console report (returns plain text if rich unavailable)."""
        if not HAS_RICH:
            return self._generate_plain(results)
        return ""  # Rich output is direct, not string-based

    def _generate_plain(self, results: list[ModuleResult]) -> str:
        """Generate plain text report without Rich."""
        lines = []
        worst = HealthStatus.OK
        for r in results:
            if r.status.weight > worst.weight:
                worst = r.status

        lines.append("=" * 60)
        lines.append(f"SYSTEM HEALTH CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Overall Status: {worst.value}")
        lines.append("=" * 60)

        for result in results:
            icon = self.STATUS_ICONS_ASCII.get(result.status, result.status.value)
            lines.append(f"\n[{icon}] {result.module.upper()} - {result.status.value}")
            lines.append("-" * 40)
            for m in result.metrics:
                mic = self.STATUS_ICONS_ASCII.get(m.status, m.status.value)
                val = f"{m.value} {m.unit}".strip() if m.value is not None else "-"
                lines.append(f"  [{mic}] {m.name:<30} {val:>10}  {m.message}")
            if result.error:
                lines.append(f"  [ERR] ERROR: {result.error}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def output(self, results: list[ModuleResult], file: Optional[str] = None) -> None:
        """Print report to console or write plain text to file."""
        if file:
            text = self._generate_plain(results)
            with open(file, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"Report saved to {file}")
            return

        if not HAS_RICH:
            print(self._generate_plain(results))
            return

        try:
            self._output_rich(results, ascii_only=False)
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Retry with ASCII-safe characters for non-UTF-8 terminals (e.g., Chinese Windows GBK)
            try:
                self._output_rich(results, ascii_only=True)
            except (UnicodeEncodeError, UnicodeDecodeError):
                # Final fallback to plain text
                print(self._generate_plain(results))

    def _output_rich(self, results: list[ModuleResult], ascii_only: bool = False) -> None:
        """Render console report with Rich formatting."""
        icons = self.STATUS_ICONS_ASCII if ascii_only else self.STATUS_ICONS
        console = Console(color_system="auto" if self.use_color else None)

        # Header
        worst = HealthStatus.OK
        for r in results:
            if r.status.weight > worst.weight:
                worst = r.status

        status_color = self.STATUS_STYLES.get(worst, "white")
        header_style = f"bold {status_color}"

        console.print()
        console.rule("[bold]SYSTEM HEALTH CHECK[/bold]")
        console.print(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            style="dim",
        )

        # Overall status
        overall_text = Text()
        overall_text.append("Overall Status: ", style="bold")
        overall_text.append(worst.value, style=header_style)
        console.print(overall_text)
        console.print()

        # Summary counts
        counts = {
            HealthStatus.OK: 0,
            HealthStatus.WARNING: 0,
            HealthStatus.CRITICAL: 0,
            HealthStatus.ERROR: 0,
            HealthStatus.NA: 0,
        }
        for r in results:
            counts[r.status] += 1

        summary_parts = []
        for status, count in counts.items():
            if count > 0:
                color = self.STATUS_STYLES.get(status, "white")
                summary_parts.append(f"[{color}]{status.value}: {count}[/{color}]")
        console.print(" | ".join(summary_parts))
        console.print()

        # Module tables
        for result in results:
            table = self._make_table(result, ascii_only=ascii_only)
            console.print(table)
            console.print()

        # Footer
        if worst == HealthStatus.OK:
            footer = "[green]OK All systems healthy[/green]"
        elif worst == HealthStatus.WARNING:
            footer = "[yellow]WARNING Some metrics at warning levels[/yellow]"
        elif worst == HealthStatus.CRITICAL:
            footer = "[red]FAIL Critical issues detected![/red]"
        else:
            footer = "[red]ERROR Errors occurred during health check[/red]"
        console.print(footer)
        console.rule()


class HTMLReport(BaseReport):
    """Generate self-contained HTML report."""

    STATUS_COLORS = {
        HealthStatus.OK: "#28a745",
        HealthStatus.WARNING: "#ffc107",
        HealthStatus.CRITICAL: "#dc3545",
        HealthStatus.ERROR: "#dc3545",
        HealthStatus.NA: "#6c757d",
    }

    def generate(self, results: list[ModuleResult]) -> str:
        """Generate HTML report string."""
        worst = HealthStatus.OK
        for r in results:
            if r.status.weight > worst.weight:
                worst = r.status

        overall_color = self.STATUS_COLORS.get(worst, "#6c757d")

        # Build module cards
        modules_html = ""
        for result in results:
            status_color = self.STATUS_COLORS.get(result.status, "#6c757d")
            status_text = result.status.value

            rows_html = ""
            for m in result.metrics:
                row_color = self.STATUS_COLORS.get(m.status, "#6c757d")
                val_str = f"{m.value} {m.unit}".strip() if m.value is not None else "-"
                rows_html += f"""
                <tr>
                    <td><span class="badge" style="background:{row_color}">{m.status.value}</span></td>
                    <td>{m.name}</td>
                    <td style="text-align:right">{val_str}</td>
                    <td style="color:#888">{m.message}</td>
                </tr>"""

            if result.error:
                rows_html += f"""
                <tr>
                    <td><span class="badge" style="background:#dc3545">ERROR</span></td>
                    <td colspan="3" style="color:#dc3545">{result.error}</td>
                </tr>"""

            modules_html += f"""
            <div class="module">
                <h2 style="color:{status_color}">{result.module.upper()} — {status_text}</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Metric</th>
                            <th>Value</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}
                    </tbody>
                </table>
                <div class="timestamp">{result.timestamp}</div>
            </div>"""

        # Summary counts
        counts = {s: sum(1 for r in results if r.status == s) for s in HealthStatus}
        summary_items = ""
        for status, count in counts.items():
            if count > 0:
                color = self.STATUS_COLORS.get(status, "#6c757d")
                summary_items += (
                    f'<span class="summary-item" style="color:{color}">'
                    f"{status.value}: {count}</span> "
                )

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>System Health Check Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                         'Helvetica Neue', Arial, sans-serif;
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 24px;
            line-height: 1.6;
        }}
        .container {{ max-width: 960px; margin: 0 auto; }}
        .header {{
            text-align: center;
            padding: 32px 0;
            border-bottom: 2px solid #333;
            margin-bottom: 24px;
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header .overall {{
            font-size: 20px;
            font-weight: bold;
            color: {overall_color};
        }}
        .header .time {{ color: #888; font-size: 14px; }}
        .summary {{ text-align: center; margin-bottom: 24px; }}
        .summary-item {{ margin: 0 12px; font-weight: bold; }}
        .module {{
            background: #16213e;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            border-left: 4px solid {overall_color};
        }}
        .module h2 {{ font-size: 18px; margin-bottom: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ color: #aaa; font-size: 13px; text-transform: uppercase; }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            color: #fff;
            font-size: 11px;
            font-weight: bold;
        }}
        .timestamp {{ color: #555; font-size: 12px; margin-top: 8px; }}
        .footer {{
            text-align: center;
            padding: 24px;
            color: #555;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>System Health Check Report</h1>
            <div class="overall">Overall: {worst.value}</div>
            <div class="time">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
        <div class="summary">{summary_items}</div>
        {modules_html}
        <div class="footer">
            System Health Check v0.1.0 — Generated {datetime.now().isoformat()}
        </div>
    </div>
</body>
</html>"""

    def output(self, results: list[ModuleResult], file: Optional[str] = None) -> None:
        """Write HTML report to file or stdout."""
        content = self.generate(results)
        if file:
            with open(file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"HTML report saved to {file}")
        else:
            print(content)


def get_report(format: str = "console", **kwargs: Any) -> BaseReport:
    """Factory function to get the appropriate report generator.

    Args:
        format: One of 'console', 'json', 'html'.
        **kwargs: Passed to the report class constructor.

    Returns:
        BaseReport instance.
    """
    if format == "json":
        # JSONReport only accepts 'pretty'
        json_kwargs = {k: v for k, v in kwargs.items() if k in ("pretty",)}
        return JSONReport(**json_kwargs)
    elif format == "html":
        # HTMLReport has no special kwargs
        return HTMLReport()
    else:
        # ConsoleReport accepts 'use_color'
        console_kwargs = {k: v for k, v in kwargs.items() if k in ("use_color",)}
        return ConsoleReport(**console_kwargs)


def generate_report(
    results: list[ModuleResult],
    format: str = "console",
    output_file: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Generate and output a health check report.

    Args:
        results: List of ModuleResult from health check modules.
        format: Output format: 'console', 'json', or 'html'.
        output_file: Output file path. If None, writes to stdout.
        **kwargs: Extra arguments for the report generator.
    """
    report = get_report(format, **kwargs)
    report.output(results, file=output_file)
