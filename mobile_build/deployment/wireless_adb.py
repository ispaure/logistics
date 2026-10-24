"""Bounded wireless ADB discovery with a macOS Bonjour fallback."""
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import platform
import re
import socket
import subprocess
import sys

SERVICE = '_adb-tls-connect._tcp'


def _dns(*arguments):
    # dns-sd watches indefinitely; retain its initial snapshot and reap it.
    try:
        result = subprocess.run(['dns-sd', *arguments], capture_output=True, text=True, timeout=1.5)
        return result.stdout
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ''
        return output.decode(errors='replace') if isinstance(output, bytes) else output
    except OSError:
        return ''


def _endpoint(value):
    host, separator, port = value.rpartition(':')
    host = host.strip('[]')
    if not separator or not port.isdigit() or not 0 < int(port) < 65536:
        return None
    try:
        ipaddress.ip_address(host.split('%')[0])
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', host) or not host.rstrip('.').endswith('.local'):
            return None
    return host, int(port)


def _numeric_endpoints(host, port):
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []
    # IPv4 avoids a broken link-local IPv6 route masking a usable Wi-Fi route.
    rows.sort(key=lambda row: row[0] != socket.AF_INET)
    result = []
    for family, _, _, _, address in rows:
        value = address[0]
        if family == socket.AF_INET6:
            if len(address) > 3 and address[3] and '%' not in value:
                value += '%' + str(address[3])
            value = '[' + value + ']'
        endpoint = value + ':' + str(port)
        if endpoint not in result:
            result.append(endpoint)
    return result


def _resolve(service):
    output = _dns('-L', service, SERVICE, 'local.')
    match = re.search(r'can be reached at ([^\s:]+):(\d+)', output)
    return _numeric_endpoints(match[1], int(match[2])) if match else []


def bonjour_endpoints():
    output = _dns('-B', SERVICE, 'local.')
    names = list(dict.fromkeys(re.findall(
        r'\bAdd\s+\d+\s+\d+\s+local\.\s+_adb-tls-connect\._tcp\.\s+(.+)', output)))[:8]
    if not names:
        return []
    with ThreadPoolExecutor(max_workers=4) as pool:
        return [endpoint for endpoints in pool.map(_resolve, names) for endpoint in endpoints]


def _reachable(endpoint):
    parsed = _endpoint(endpoint)
    if parsed is None:
        return False
    try:
        with socket.create_connection(parsed, timeout=.3):
            return True
    except OSError:
        return False


def restart(adb, env, run):
    """Explicit recovery; never unpair devices or alter authorization keys."""
    run([str(adb), 'kill-server'], env)
    run([str(adb), 'start-server'], env)


def discover(adb, env, run):
    candidates = []
    try:
        output = run([str(adb), 'mdns', 'services'], env)
    except (OSError, subprocess.SubprocessError):
        output = ''
    for line in output.splitlines():
        fields = line.rsplit(None, 2)
        if len(fields) == 3 and fields[1].rstrip('.') == SERVICE:
            parsed = _endpoint(fields[2])
            if parsed:
                candidates.extend(_numeric_endpoints(*parsed))
    if platform.system() == 'Darwin':
        candidates.extend(bonjour_endpoints())
    candidates = list(dict.fromkeys(candidates))[:16]
    reachable, blocked = [], False
    for endpoint in candidates:
        if not _reachable(endpoint):
            continue
        reachable.append(endpoint)
        try:
            result = run([str(adb), 'connect', endpoint], env, timeout=3)
            blocked |= 'No route to host' in result or 'Network is unreachable' in result
        except (OSError, subprocess.SubprocessError):
            continue
    if blocked:
        # A sandboxed/stale server can report no route even though the discovery
        # process can reach the same port. Do not interrupt any ready device.
        output = run([str(adb), 'devices'], env)
        ready = any(len(parts := line.split()) >= 2 and parts[1] == 'device'
                    for line in output.splitlines())
        if not ready:
            print('Recovering ADB: wireless debugging is reachable, but the local server has no route.', file=sys.stderr)
            restart(adb, env, run)
            for endpoint in reachable:
                try:
                    run([str(adb), 'connect', endpoint], env, timeout=3)
                except (OSError, subprocess.SubprocessError):
                    continue
