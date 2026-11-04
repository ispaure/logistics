"""Current RSS for a probe and its descendants, including WebEngine processes."""
import os
import platform
import subprocess


def tree_memory(rows, root):
    """Rows contain only PID, parent PID and resident bytes, never command lines."""
    by_pid = {pid: (parent, rss) for pid, parent, rss in rows}
    if root not in by_pid:
        raise RuntimeError('Probe process missing from memory sample')
    selected = {root}
    while True:
        children = {pid for pid, (parent, _) in by_pid.items() if parent in selected}
        if children <= selected:
            break
        selected.update(children)
    return dict(rss_bytes=sum(by_pid[pid][1] for pid in selected),
                processes=[dict(pid=pid, rss_bytes=by_pid[pid][1]) for pid in sorted(selected)])


def process_tree_memory():
    if platform.system() == 'Windows':
        rows = windows_processes()
    else:
        # RSS queries for every process can stall large macOS hosts. Discover
        # ancestry cheaply, then read memory only for this probe's descendants.
        output = subprocess.check_output(['ps', '-axo', 'pid=,ppid='], text=True, timeout=10)
        parents = {int(pid): int(parent) for pid, parent in (line.split() for line in output.splitlines())}
        selected = tree_memory([(pid, parent, 0) for pid, parent in parents.items()], os.getpid())
        pids = ','.join(str(row['pid']) for row in selected['processes'])
        output = subprocess.check_output(['ps', '-p', pids, '-o', 'pid=,rss='], text=True, timeout=10)
        # A short-lived sampler child may exit between enumeration and readout.
        rows = [(int(pid), parents[int(pid)], int(kib) * 1024)
                for pid, kib in (line.split() for line in output.splitlines())]
    return tree_memory(rows, os.getpid())


def windows_processes():
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
                    ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                    ('exe', wintypes.WCHAR * 260)]

    class Counters(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('faults', wintypes.DWORD),
                    *[(name, ctypes.c_size_t) for name in ('peak', 'resident', 'peak_paged', 'paged',
                                                         'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    query = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        parents = []
        available = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            parents.append((entry.pid, entry.parent, 0))
            available = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        selected = tree_memory(parents, os.getpid())
        by_pid = {pid: parent for pid, parent, _ in parents}
        rows = []
        for row in selected['processes']:
            pid = row['pid']
            process = kernel.OpenProcess(0x410, False, pid)
            if process:
                try:
                    counters = Counters()
                    counters.size = ctypes.sizeof(counters)
                    if query(process, ctypes.byref(counters), counters.size):
                        rows.append((pid, by_pid[pid], counters.resident))
                finally:
                    kernel.CloseHandle(process)
        return rows
    finally:
        kernel.CloseHandle(snapshot)
