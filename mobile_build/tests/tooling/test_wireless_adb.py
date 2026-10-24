"""Wireless discovery recovers Bonjour-only peers without disrupting ready devices."""
import socket
import subprocess
import unittest
from unittest.mock import patch

from mobile_build.deployment import wireless_adb as wireless


class WirelessADBTests(unittest.TestCase):
    def test_bonjour_snapshot_retains_partial_timeout_output(self):
        error = subprocess.TimeoutExpired(['dns-sd'], 1.5, output=b'Add service\n')
        with patch.object(wireless.subprocess, 'run', side_effect=error) as run:
            self.assertEqual(wireless._dns('-B', wireless.SERVICE, 'local.'), 'Add service\n')
        self.assertEqual(run.call_args.kwargs['timeout'], 1.5)

    def test_bonjour_resolves_rotated_ports_and_deduplicates_advertisements(self):
        listing = ('10:00:00 Add 3 14 local. _adb-tls-connect._tcp. adb-boox\n'
                   '10:00:00 Add 2 14 local. _adb-tls-connect._tcp. adb-boox\n'
                   '10:00:00 Add 2 14 local. _adb-tls-connect._tcp. adb-boox (2)\n')
        with patch.object(wireless, '_dns', return_value=listing), \
                patch.object(wireless, '_resolve', side_effect=lambda name: ['192.168.2.10:' + ('42000' if '(2)' in name else '33000')]) as resolve:
            self.assertEqual(wireless.bonjour_endpoints(), ['192.168.2.10:33000', '192.168.2.10:42000'])
        self.assertEqual(resolve.call_count, 2)

    def test_ipv4_precedes_scoped_ipv6_for_the_same_hostname(self):
        rows = [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('fe80::1', 42000, 0, 14)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.2.10', 42000))]
        with patch.object(wireless.socket, 'getaddrinfo', return_value=rows):
            self.assertEqual(wireless._numeric_endpoints('Android.local.', 42000),
                             ['192.168.2.10:42000', '[fe80::1%14]:42000'])

    def discover(self, *, ready=False, route_error=False):
        calls = []
        def run(command, env, **kwargs):
            calls.append(command)
            if command[-2:] == ['mdns', 'services']:
                return 'List of discovered mdns services\n'
            if command[-1] == 'devices':
                return 'usb\tdevice\n' if ready else 'List of devices attached\n'
            if 'connect' in command:
                return 'failed to connect: No route to host' if route_error else 'connected'
            return ''
        with patch.object(wireless.platform, 'system', return_value='Darwin'), \
                patch.object(wireless, 'bonjour_endpoints', return_value=['192.168.2.10:33000', '192.168.2.10:42000', '192.168.2.10:42000']), \
                patch.object(wireless, '_reachable', side_effect=lambda endpoint: endpoint.endswith(':42000')):
            wireless.discover('/adb', {}, run)
        return calls

    def test_empty_adb_mdns_finds_live_bonjour_endpoint_and_skips_stale_port(self):
        calls = self.discover()
        self.assertEqual([c[-1] for c in calls if 'connect' in c], ['192.168.2.10:42000'])
        self.assertFalse(any('kill-server' in c for c in calls))
        self.assertFalse(any('pair' in c for c in calls))

    def test_mdns_service_names_with_spaces_keep_the_current_endpoint(self):
        calls = []
        def run(command, env, **kwargs):
            calls.append(command)
            return 'adb-boox (2) _adb-tls-connect._tcp 192.168.2.10:42000\n' if command[-1] == 'services' else 'connected'
        with patch.object(wireless.platform, 'system', return_value='Linux'), \
                patch.object(wireless, '_numeric_endpoints', return_value=['192.168.2.10:42000']), \
                patch.object(wireless, '_reachable', return_value=True):
            wireless.discover('/adb', {}, run)
        self.assertIn(['/adb', 'connect', '192.168.2.10:42000'], calls)

    def test_unreachable_adb_daemon_recovers_once_when_no_ready_devices_exist(self):
        calls = self.discover(route_error=True)
        self.assertEqual(sum('kill-server' in c for c in calls), 1)
        self.assertEqual(sum('start-server' in c for c in calls), 1)
        self.assertEqual(sum('connect' in c for c in calls), 2)

    def test_ready_usb_or_wireless_device_prevents_automatic_daemon_restart(self):
        calls = self.discover(ready=True, route_error=True)
        self.assertFalse(any('kill-server' in c for c in calls))

    def test_pairing_advertisements_and_invalid_endpoints_are_never_connected(self):
        calls = []
        def run(command, env, **kwargs):
            calls.append(command)
            return 'boox _adb-tls-pairing._tcp 192.168.2.10:42000\n'
        with patch.object(wireless.platform, 'system', return_value='Linux'):
            wireless.discover('/adb', {}, run)
        self.assertEqual(len(calls), 1)
        for value in ('--listen', '192.168.2.10:0', '192.168.2.10:70000', 'remote.example.com:42000'):
            self.assertIsNone(wireless._endpoint(value))


if __name__ == '__main__':
    unittest.main()
