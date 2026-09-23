"""Host and per-process resource metrics using psutil."""

from __future__ import annotations

from typing import Any

import psutil

from core.supervisor import ProcessSupervisor


def collect_metrics() -> dict[str, Any]:
    payload = {
        "cpu_percent": 0.0,
        "cpu_per_core": [],
        "cpu_count": 1,
        "memory": {"total": 0, "available": 0, "percent": 0},
        "disk": {"total": 0, "used": 0, "percent": 0},
        "network": {"bytes_sent": 0, "bytes_recv": 0},
        "temperatures": {},
        "processes": _process_metrics(),
    }
    try:
        vm = psutil.virtual_memory()
        payload["memory"] = {
            "total": vm.total,
            "available": vm.available,
            "percent": vm.percent,
        }
    except Exception:
        pass
    try:
        payload["cpu_percent"] = psutil.cpu_percent(interval=None)
        payload["cpu_per_core"] = psutil.cpu_percent(interval=None, percpu=True)
        payload["cpu_count"] = psutil.cpu_count() or 1
    except Exception:
        pass
    try:
        disk = psutil.disk_usage("/")
        payload["disk"] = {"total": disk.total, "used": disk.used, "percent": disk.percent}
    except Exception:
        pass
    try:
        net = psutil.net_io_counters()
        payload["network"] = {
            "bytes_sent": getattr(net, "bytes_sent", 0),
            "bytes_recv": getattr(net, "bytes_recv", 0),
        }
    except Exception:
        pass
    try:
        payload["temperatures"] = {
            name: [{"label": t.label, "current": t.current} for t in entries]
            for name, entries in (psutil.sensors_temperatures() or {}).items()
        }
    except Exception:
        pass
    return payload


def _process_metrics() -> list[dict[str, Any]]:
    rows = []
    try:
        processes = ProcessSupervisor.get().list_processes()
    except Exception:
        return rows
    for item in processes:
        pid = item.get("pid")
        row = {
            "name": item["name"],
            "pid": pid,
            "cpu_percent": None,
            "memory_rss": None,
        }
        if pid:
            try:
                proc = psutil.Process(pid)
                row["cpu_percent"] = proc.cpu_percent(interval=None)
                row["memory_rss"] = proc.memory_info().rss
            except Exception:
                pass
        rows.append(row)
    return rows
