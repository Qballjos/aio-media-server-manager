"""Host and per-process resource metrics using psutil."""

from __future__ import annotations

from typing import Any

import psutil

from core.supervisor import ProcessSupervisor

# psutil.Process.cpu_percent(interval=None) is 0.0 until a process has been sampled once.
_proc_cache: dict[int, psutil.Process] = {}


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
    rows: list[dict[str, Any]] = []
    used_pids: set[int] = set()
    try:
        processes = ProcessSupervisor.get().list_processes()
    except Exception:
        return rows
    for item in processes:
        pid = item.get("pid")
        cpu, rss, mem_pct, child_count, pids = _tree_usage(int(pid)) if pid else (None, None, None, 0, set())
        used_pids.update(pids)
        rows.append(
            {
                "name": item["name"],
                "state": item.get("state"),
                "pid": pid,
                "cpu_percent": cpu,
                "memory_rss": rss,
                "memory_percent": mem_pct,
                "child_count": child_count,
            }
        )
    for cached in list(_proc_cache):
        if cached not in used_pids:
            _proc_cache.pop(cached, None)
    rows.sort(key=lambda item: (-(item["cpu_percent"] or 0), -(item["memory_rss"] or 0), item["name"]))
    return rows


def _cached_proc(pid: int) -> psutil.Process | None:
    proc = _proc_cache.get(pid)
    try:
        if proc is None or not proc.is_running() or proc.pid != pid:
            proc = psutil.Process(pid)
            _proc_cache[pid] = proc
            proc.cpu_percent(interval=None)
        return proc
    except (psutil.Error, OSError):
        _proc_cache.pop(pid, None)
        return None


def _tree_usage(pid: int) -> tuple[float | None, int | None, float | None, int, set[int]]:
    """CPU and RSS for the supervised PID plus its descendants."""
    if _cached_proc(pid) is None:
        return None, None, None, 0, set()
    cpu = 0.0
    rss = 0
    mem_pct = 0.0
    children = 0
    seen: set[int] = set()
    stack = [pid]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        proc = _cached_proc(current)
        if proc is None:
            continue
        try:
            cpu += float(proc.cpu_percent(interval=None) or 0.0)
            rss += int(proc.memory_info().rss)
            mem_pct += float(proc.memory_percent() or 0.0)
            kids = proc.children(recursive=False)
            children += len(kids)
            stack.extend(child.pid for child in kids)
        except (psutil.Error, OSError):
            _proc_cache.pop(current, None)
    return round(cpu, 1), rss, round(mem_pct, 2), children, seen
