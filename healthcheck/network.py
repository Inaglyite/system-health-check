"""Network health check module.

Collects network interface information, I/O statistics,
and performs ping connectivity tests.
"""

from __future__ import annotations

import platform
import re
import subprocess
from typing import Any

import psutil

from .config import Config
from .dataclasses import HealthStatus, MetricValue, ModuleResult, Threshold


def _format_bytes(b: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def collect_network_interfaces(config: Config | None = None) -> list[MetricValue]:
    """Collect network interface addresses and stats.

    Returns:
        List of MetricValue objects for each interface.
    """
    metrics: list[MetricValue] = []

    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        for iface_name, iface_addrs in addrs.items():
            iface_stats = stats.get(iface_name)
            is_up = iface_stats.isup if iface_stats else False
            speed = iface_stats.speed if iface_stats else 0

            ipv4 = None
            ipv6 = None
            mac = None

            for addr in iface_addrs:
                if addr.family.name == "AF_INET":
                    ipv4 = addr.address
                elif addr.family.name == "AF_INET6":
                    ipv6 = addr.address.split("%")[0]  # strip scope ID
                elif addr.family.name in ("AF_LINK", "AF_PACKET"):
                    mac = addr.address

            # Skip loopback
            if iface_name.lower().startswith("lo"):
                continue

            msg_parts = []
            if ipv4:
                msg_parts.append(ipv4)
            if mac:
                msg_parts.append(f"MAC: {mac}")
            msg_parts.append("UP" if is_up else "DOWN")
            if speed and speed > 0:
                msg_parts.append(f"{speed} Mbps")

            status = HealthStatus.OK if is_up else HealthStatus.WARNING

            metrics.append(
                MetricValue(
                    name=f"net_iface_{iface_name}",
                    value=speed if speed > 0 else None,
                    unit="Mbps" if speed > 0 else "",
                    status=status,
                    message=f"{iface_name}: {', '.join(msg_parts)}",
                    extra={
                        "interface": iface_name,
                        "ipv4": ipv4,
                        "ipv6": ipv6,
                        "mac": mac,
                        "is_up": is_up,
                        "speed_mbps": speed,
                    },
                )
            )

    except Exception as e:
        metrics.append(
            MetricValue(
                name="net_interfaces",
                status=HealthStatus.ERROR,
                message=f"Failed to get network interfaces: {e}",
            )
        )

    return metrics


def collect_network_io(config: Config | None = None) -> list[MetricValue]:
    """Collect network I/O counters.

    Returns:
        List of MetricValue objects with bytes/packets sent and received.
    """
    metrics: list[MetricValue] = []

    try:
        io = psutil.net_io_counters(pernic=True)
        for iface_name, counters in io.items():
            if iface_name.lower().startswith("lo"):
                continue

            sent_str = _format_bytes(counters.bytes_sent)
            recv_str = _format_bytes(counters.bytes_recv)

            metrics.append(
                MetricValue(
                    name=f"net_io_{iface_name}_sent",
                    value=counters.bytes_sent,
                    unit="bytes",
                    message=f"{iface_name}: sent {sent_str} ({counters.packets_sent:,} pkts)",
                    extra={
                        "interface": iface_name,
                        "bytes_sent": counters.bytes_sent,
                        "bytes_recv": counters.bytes_recv,
                        "packets_sent": counters.packets_sent,
                        "packets_recv": counters.packets_recv,
                        "errin": counters.errin,
                        "errout": counters.errout,
                        "dropin": counters.dropin,
                        "dropout": counters.dropout,
                    },
                )
            )
            metrics.append(
                MetricValue(
                    name=f"net_io_{iface_name}_recv",
                    value=counters.bytes_recv,
                    unit="bytes",
                    message=f"{iface_name}: received {recv_str} ({counters.packets_recv:,} pkts)",
                )
            )
    except Exception as e:
        metrics.append(
            MetricValue(
                name="net_io",
                status=HealthStatus.ERROR,
                message=f"Failed to get network I/O: {e}",
            )
        )

    return metrics


def _ping_host(
    host: str, count: int = 3, timeout: float = 2.0
) -> dict[str, Any]:
    """Ping a single host and return results.

    Args:
        host: IP or hostname to ping.
        count: Number of pings (Windows: -n, Linux: -c).
        timeout: Timeout in seconds per ping.

    Returns:
        Dict with keys: host, sent, received, lost, loss_pct,
        min_ms, avg_ms, max_ms, success.
    """
    is_windows = platform.system() == "Windows"
    if is_windows:
        cmd = ["ping", "-n", str(count), "-w", str(int(timeout * 1000)), host]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(int(timeout)), host]

    result = {
        "host": host,
        "sent": count,
        "received": 0,
        "lost": count,
        "loss_pct": 100.0,
        "min_ms": None,
        "avg_ms": None,
        "max_ms": None,
        "success": False,
    }

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout * count + 3,
        )
        output = proc.stdout

        # Parse packet loss
        if is_windows:
            # "Packets: Sent = 3, Received = 3, Lost = 0 (0% loss)"
            loss_match = re.search(
                r"Sent\s*=\s*(\d+).*?Received\s*=\s*(\d+).*?Lost\s*=\s*(\d+).*?(\d+)%",
                output,
            )
            if loss_match:
                result["sent"] = int(loss_match.group(1))
                result["received"] = int(loss_match.group(2))
                result["lost"] = int(loss_match.group(3))
                result["loss_pct"] = float(loss_match.group(4))

            # "Minimum = 1ms, Maximum = 2ms, Average = 1ms"
            rtt_match = re.search(
                r"Minimum\s*=\s*(\d+)ms.*?Maximum\s*=\s*(\d+)ms.*?Average\s*=\s*(\d+)ms",
                output,
            )
            if rtt_match:
                result["min_ms"] = float(rtt_match.group(1))
                result["max_ms"] = float(rtt_match.group(2))
                result["avg_ms"] = float(rtt_match.group(3))
        else:
            # "3 packets transmitted, 3 received, 0% packet loss"
            loss_match = re.search(
                r"(\d+) packets transmitted.*?(\d+) received.*?(\d+(?:\.\d+)?)% packet loss",
                output,
            )
            if loss_match:
                result["sent"] = int(loss_match.group(1))
                result["received"] = int(loss_match.group(2))
                result["loss_pct"] = float(loss_match.group(3))
                result["lost"] = result["sent"] - result["received"]

            # "rtt min/avg/max/mdev = 1.234/2.345/3.456/0.555 ms"
            rtt_match = re.search(
                r"rtt min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)",
                output,
            )
            if rtt_match:
                result["min_ms"] = float(rtt_match.group(1))
                result["avg_ms"] = float(rtt_match.group(2))
                result["max_ms"] = float(rtt_match.group(3))

        result["success"] = result["received"] > 0

    except subprocess.TimeoutExpired:
        result["lost"] = count
        result["loss_pct"] = 100.0
    except Exception:
        pass

    return result


def collect_ping_test(config: Config | None = None) -> list[MetricValue]:
    """Ping configured targets to test network connectivity.

    Args:
        config: Config for ping targets and thresholds.

    Returns:
        List of MetricValue objects per target.
    """
    if config is None:
        config = Config()

    targets = config.ping_targets
    ping_count = config.ping_count
    ping_timeout = config.ping_timeout
    loss_threshold = config.get_threshold("network.packet_loss_percent")
    latency_threshold = config.get_threshold("network.latency_ms")

    metrics: list[MetricValue] = []

    for target in targets:
        result = _ping_host(target, count=ping_count, timeout=ping_timeout)

        # Packet loss metric
        metrics.append(
            MetricValue(
                name=f"ping_loss_{target.replace('.', '_')}",
                value=result["loss_pct"],
                unit="%",
                threshold=loss_threshold,
                message=(
                    f"{target}: {result['received']}/{result['sent']} received, "
                    f"{result['loss_pct']:.0f}% loss"
                ),
                extra=result,
            )
        )

        # Latency metric
        if result["avg_ms"] is not None:
            metrics.append(
                MetricValue(
                    name=f"ping_latency_{target.replace('.', '_')}",
                    value=result["avg_ms"],
                    unit="ms",
                    threshold=latency_threshold,
                    message=(
                        f"{target}: avg {result['avg_ms']:.1f}ms "
                        f"(min: {result['min_ms']:.1f}, max: {result['max_ms']:.1f})"
                    ),
                )
            )
        elif result["loss_pct"] == 100:
            metrics.append(
                MetricValue(
                    name=f"ping_latency_{target.replace('.', '_')}",
                    status=HealthStatus.CRITICAL,
                    message=f"{target}: unreachable (100% packet loss)",
                )
            )

    return metrics


def collect(config: Config | None = None) -> ModuleResult:
    """Run all network health checks.

    Args:
        config: Optional Config for thresholds.

    Returns:
        ModuleResult with all network metrics.
    """
    if config is None:
        config = Config()

    metrics: list[MetricValue] = []
    raw_data: dict[str, Any] = {}

    try:
        metrics.extend(collect_network_interfaces(config))
        metrics.extend(collect_network_io(config))
        metrics.extend(collect_ping_test(config))

        return ModuleResult(module="network", metrics=metrics, raw_data=raw_data)

    except Exception as e:
        return ModuleResult(
            module="network",
            metrics=metrics,
            raw_data=raw_data,
            error=str(e),
        )


if __name__ == "__main__":
    result = collect()
    print(f"Network Status: {result.status.value}")
    for m in result.metrics:
        status_icon = {
            HealthStatus.OK: "✓",
            HealthStatus.WARNING: "⚠",
            HealthStatus.CRITICAL: "✗",
            HealthStatus.ERROR: "!",
            HealthStatus.NA: "?",
        }
        print(f"  {status_icon.get(m.status, ' ')} {m.name}: {m.message}")
