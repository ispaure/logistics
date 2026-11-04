"""Read-only load measurements for controlled disposable Android comparisons."""
import ctypes
from functools import lru_cache
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


def proc_cpu(text):
    line = next(line for line in text.splitlines() if line.startswith('cpu '))
    values = tuple(map(int, line.split()[1:9]))
    if len(values) != 8:
        raise ValueError('Incomplete /proc/stat CPU counters')
    return values


def cpu_idle(before, after, *, idle_index, bits=None):
    if len(before) != len(after):
        raise ValueError('CPU counter shape changed')
    values = [(b - a) & ((1 << bits) - 1) if bits else b - a for a, b in zip(before, after)]
    if any(x < 0 for x in values):
        raise ValueError('CPU counters moved backwards')
    total = sum(values)
    return values[idle_index] / total if total else None


@lru_cache(maxsize=1)
def mach_api():
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    lib.mach_host_self.restype = ctypes.c_uint32
    lib.host_statistics.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_uint32)]
    lib.host_statistics.restype = ctypes.c_int
    lib.mach_port_deallocate.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    return lib


def host_cpu():
    if sys.platform == 'darwin':
        lib = mach_api()
        host = lib.mach_host_self()
        values, count = (ctypes.c_uint32 * 4)(), ctypes.c_uint32(4)
        try:
            if lib.host_statistics(host, 3, values, ctypes.byref(count)) != 0 or count.value != 4:
                raise RuntimeError('HOST_CPU_LOAD_INFO failed')
            return tuple(values), 2, 32
        finally:
            lib.mach_port_deallocate(ctypes.c_uint32.in_dll(lib, 'mach_task_self_').value, host)
    if sys.platform.startswith('linux'):
        return proc_cpu(Path('/proc/stat').read_text()), 3, None
    raise ValueError('Controlled host load capture currently supports macOS and Linux')


def host_memory():
    if sys.platform == 'darwin':
        text = subprocess.check_output(['vm_stat'], text=True, timeout=10)
        page = int(re.search(r'page size of (\d+) bytes', text)[1])
        def pages(name):
            return int(re.search(r'^' + re.escape(name) + r':\s+(\d+)', text, re.M)[1])
        return dict(available_bytes=page * sum(pages(x) for x in
                    ('Pages free', 'Pages inactive', 'Pages speculative')), swapouts=pages('Swapouts'))
    if sys.platform.startswith('linux'):
        memory = Path('/proc/meminfo').read_text()
        swap = Path('/proc/vmstat').read_text()
        return dict(available_bytes=int(re.search(r'^MemAvailable:\s+(\d+)', memory, re.M)[1]) * 1024,
                    swapouts=int(re.search(r'^pswpout\s+(\d+)', swap, re.M)[1]))
    raise ValueError('Unsupported controlled load host')


def emulator_processes():
    result = []
    for line in subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True, timeout=10).splitlines():
        pid, _, command = line.strip().partition(' ')
        try:
            args = shlex.split(command)
        except ValueError:
            continue
        if args and (Path(args[0]).name == 'emulator' or Path(args[0]).name.startswith('qemu-system-')):
            if '-avd' in args and args.index('-avd') + 1 < len(args):
                result.append(dict(pid=int(pid), avd=args[args.index('-avd') + 1]))
    return result


def process_seconds(pid):
    value = subprocess.check_output(['ps', '-p', str(int(pid)), '-o', 'time='], text=True, timeout=10).strip()
    days, value = value.split('-', 1) if '-' in value else ('0', value)
    seconds = 0.0
    for field in value.split(':'):
        seconds = seconds * 60 + float(field)
    return seconds + int(days) * 86400


def guest_stats(text):
    return dict(cpu=proc_cpu(text), available_bytes=int(re.search(r'^MemAvailable:\s+(\d+)', text, re.M)[1]) * 1024)


def eligible(sample):
    return (sample['owned_present'] and sample['other_emulators'] == 0
        and sample['host_idle'] is not None and sample['host_idle'] >= .85
        and sample['guest_idle'] is not None and sample['guest_idle'] >= .75
        and sample['guest_iowait'] is not None and sample['guest_iowait'] <= .02
        and sample['host_available_bytes'] >= 4 * 1024 ** 3
        and sample['guest_available_bytes'] >= 256 * 1024 ** 2
        and sample['swapout_delta'] == 0)


def window_verdict(samples):
    if not samples or any(not s['owned_present'] or s['other_emulators'] for s in samples):
        return False, 'Emulator isolation changed during the measurement'
    if any(s['swapout_delta'] for s in samples):
        return False, 'Host swapped during the measurement'
    timed = [s for s in samples if s['external_busy'] is not None and s['interval'] > 0]
    duration = sum(s['interval'] for s in timed)
    if not duration:
        return False, 'No host CPU interval captured'
    busy = sum(s['external_busy'] * s['interval'] for s in timed) / duration
    if busy > .20:
        return False, 'Other host CPU load exceeded 20 percent'
    return True, 'Isolated emulator, settled pre-window load, no swap and bounded external host CPU'


def normalized_external_busy(host_idle, emulator_cpu, interval):
    if host_idle is None or interval <= 0:
        return None
    return max(0.0, 1 - host_idle - emulator_cpu / (interval * (os.cpu_count() or 1)))
