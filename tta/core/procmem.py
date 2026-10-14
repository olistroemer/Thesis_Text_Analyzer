"""Resident set size of another process, standard library only (ADR-0013
"Recycling", #86).

The runner reads a worker's resident set after each thesis to decide whether
to recycle it. psutil would do this everywhere but is not a dependency of the
application, so this module covers what the standard library can:

- **Windows:** ``GetProcessMemoryInfo`` via ``ctypes``, ``WorkingSetSize`` -
  the figure Task Manager and psutil report as the resident set.
- **Linux:** ``/proc/<pid>/statm``, resident pages times the page size.
- **Elsewhere (macOS):** there is no standard-library way to read another
  process's resident set, so the probe reports ``None`` and the runner falls
  back to recycling by thesis count only.

Every failure - an exited process, a denied handle, a missing ``/proc`` -
degrades to ``None`` as well. The probe must never be the reason a run fails.
"""

from __future__ import annotations

import os
import sys


def rss_bytes(pid: int) -> int | None:
    """Current resident set of process ``pid`` in bytes, or ``None`` if it
    cannot be read on this platform or for this process."""
    try:
        if sys.platform == "win32":
            return _rss_windows(pid)
        if sys.platform.startswith("linux"):
            return _rss_linux(pid)
    except Exception:  # noqa: BLE001 - degrade, never fail the run
        return None
    return None


def _rss_linux(pid: int) -> int | None:
    with open(f"/proc/{int(pid)}/statm", encoding="ascii") as fh:
        fields = fh.read().split()
    return int(fields[1]) * os.sysconf("SC_PAGE_SIZE")


_win_api = None


def _windows_api():
    """Bind the three kernel32 calls once (lazily, so non-Windows platforms
    never touch ``ctypes.WinDLL``)."""
    global _win_api
    if _win_api is not None:
        return _win_api
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    # K32GetProcessMemoryInfo is kernel32's export of psapi's function
    # (Windows 7+), so no second DLL is needed.
    get_info = kernel32.K32GetProcessMemoryInfo
    get_info.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    get_info.restype = wintypes.BOOL
    _win_api = (ctypes, ProcessMemoryCounters, open_process, close_handle, get_info)
    return _win_api


#: Least access GetProcessMemoryInfo accepts (Windows 8.1+ allows
#: PROCESS_QUERY_LIMITED_INFORMATION in place of PROCESS_QUERY_INFORMATION).
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_VM_READ = 0x0010


def _rss_windows(pid: int) -> int | None:
    ctypes, counters_type, open_process, close_handle, get_info = _windows_api()
    handle = open_process(
        _PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_VM_READ, False, int(pid)
    )
    if not handle:
        return None
    try:
        counters = counters_type()
        counters.cb = ctypes.sizeof(counters_type)
        if not get_info(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    finally:
        close_handle(handle)
