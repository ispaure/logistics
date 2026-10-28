"""Foreground-only Wi-Fi identity reads; unavailable information never grants access."""
import json


def network_names(value):
    names = json.loads(value)
    if (not isinstance(names, list) or len(names) > 32
            or any(not isinstance(name, str) or not name or len(name.encode('utf-8')) > 32
                   or any(char in name for char in '\r\n\x00') for name in names)
            or len(set(names)) != len(names)):
        raise ValueError('Use up to 32 unique Wi-Fi names, each at most 32 UTF-8 bytes.')
    return names


def trusted(app, ssid):
    values = getattr(getattr(app, 'preferences', None), 'values', {})
    return bool(ssid and values.get('session_trusted_wifi') == 'true'
                and ssid in network_names(values.get('trusted_wifi_networks', '[]')))


def current_ssid(app):
    """Read the current association, never scan or infer identity from an IP address."""
    try:
        backend = type(app._impl).__module__
        if backend.startswith('toga_android.'):
            activity = app._impl.native
            if activity.checkSelfPermission('android.permission.ACCESS_FINE_LOCATION') != 0:
                return None
            connectivity = activity.getSystemService('connectivity')
            capabilities = connectivity.getNetworkCapabilities(connectivity.getActiveNetwork())
            if capabilities is None or not capabilities.hasTransport(1):  # TRANSPORT_WIFI
                return None
            manager = activity.getApplicationContext().getSystemService('wifi')
            info = manager.getConnectionInfo()
            if info is None or info.getNetworkId() == -1:
                return None
            name = str(info.getSSID())
            if name.startswith('"') and name.endswith('"'):
                name = name[1:-1]
            return name if name and name != '<unknown ssid>' else None

    except Exception:
        # Permission revocation, missing entitlement and transient disconnects
        # must all preserve the normal password challenge.
        return None
    return None


_ios_callbacks = set()


async def read_ssid(app):
    """Use Apple's asynchronous foreground API; never block the UI for a callback."""
    if not type(app._impl).__module__.startswith('toga_iOS.'):
        return current_ssid(app)
    import asyncio
    from ctypes import CDLL
    try:
        from rubicon.objc import ObjCClass, ObjCInstance, Block, objc_id
        CDLL('/System/Library/Frameworks/NetworkExtension.framework/NetworkExtension')
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        def deliver(name):
            if not future.done():
                future.set_result(name)
        def completed(pointer):
            try:
                network = ObjCInstance(pointer) if pointer else None
                value = network.SSID if network is not None else None
                name = str(value) if value else None
            except Exception:
                name = None
            finally:
                _ios_callbacks.discard(block)
            if not loop.is_closed():
                loop.call_soon_threadsafe(deliver, name or None)
        block = Block(completed, None, objc_id)
        _ios_callbacks.add(block)
        try:
            ObjCClass('NEHotspotNetwork').fetchCurrentWithCompletionHandler(block)
        except Exception:
            _ios_callbacks.discard(block)
            raise
        return await asyncio.wait_for(future, timeout=3)
    except Exception:
        return None


def access_state(app):
    """Return granted, prompt or settings without requesting location updates."""
    try:
        backend = type(app._impl).__module__
        if backend.startswith('toga_android.'):
            activity = app._impl.native
            if activity.checkSelfPermission('android.permission.ACCESS_FINE_LOCATION') == 0:
                return 'granted'
            if (getattr(app, '_wifi_permission_requested', False)
                    and not activity.shouldShowRequestPermissionRationale(
                        'android.permission.ACCESS_FINE_LOCATION')):
                return 'settings'
            return 'prompt'
        if backend.startswith('toga_iOS.'):
            from ctypes import CDLL
            from rubicon.objc import ObjCClass
            CDLL('/System/Library/Frameworks/CoreLocation.framework/CoreLocation')
            if not hasattr(app, '_wifi_location_manager'):
                app._wifi_location_manager = ObjCClass('CLLocationManager').alloc().init()
            manager = app._wifi_location_manager
            status = manager.authorizationStatus
            if status in (3, 4):  # Always / When In Use
                return 'granted' if manager.accuracyAuthorization == 0 else 'settings'
            return 'prompt' if status == 0 else 'settings'
        return 'granted' if app.location.has_permission else 'prompt'
    except Exception:
        return 'settings'


async def request_access(app):
    """Await the foreground permission decision through Toga's native callbacks."""
    if access_state(app) == 'granted':
        return True
    if access_state(app) == 'settings':
        return False
    app._wifi_permission_requested = True
    if type(app._impl).__module__.startswith('toga_android.'):
        # Toga's location API accepts coarse permission too, and would skip
        # upgrading an existing approximate grant. SSID access needs fine.
        import asyncio
        loop = asyncio.get_running_loop()
        result = loop.create_future()
        def deliver(granted):
            if not result.done():
                result.set_result(granted)
        def completed(permissions, results):
            grants = dict(zip(permissions, results))
            granted = grants.get('android.permission.ACCESS_FINE_LOCATION') == 0
            if not loop.is_closed():
                loop.call_soon_threadsafe(deliver, granted)
        app._impl.request_permissions([
            'android.permission.ACCESS_COARSE_LOCATION',
            'android.permission.ACCESS_FINE_LOCATION'], on_complete=completed)
        return bool(await result and access_state(app) == 'granted')
    # Permission alone does not subscribe to location or read coordinates.
    if not await app.location.request_permission():
        return False
    return access_state(app) == 'granted'


class WifiResume:
    """A window's pending Wi-Fi read, tied to explicit shared lifecycle challenges."""
    def __init__(self):
        self.pending = ()

    def capture(self, gates, credentials):
        eligible = set(credentials)
        self.pending = tuple((gate, gate.revision if gate.locked else gate.revision + 1)
            for gate in gates if gate in eligible and gate.proof is not None
            and (not gate.locked or (gate.reason == 'lifecycle' and gate.wifi_eligible)))

    def resume(self, app, gates, credentials, ssid):
        pending, self.pending = self.pending, ()
        if not trusted(app, ssid):
            for gate, revision in pending:
                gate.deny_wifi(revision)
            return
        eligible = set(credentials) & set(gates)
        for gate, revision in pending:
            if gate in eligible and gate.locked:
                gate.waive_lifecycle(revision)
