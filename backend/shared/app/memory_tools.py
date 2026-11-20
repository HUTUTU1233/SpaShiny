import gc
import os

import psutil


def format_bytes(n):
    n = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def current_process_memory():
    process = psutil.Process(os.getpid())
    mem = process.memory_info()
    return {
        "rss": mem.rss,
        "rss_text": format_bytes(mem.rss),
        "vms": mem.vms,
        "vms_text": format_bytes(mem.vms),
    }


def force_gc():
    before = current_process_memory()
    collected = gc.collect()
    after = current_process_memory()
    return {
        "collected": collected,
        "before": before,
        "after": after,
    }
