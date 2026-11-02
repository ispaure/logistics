"""VLC-owned receiver discovery; provider HTTP remains bound to loopback."""

import ctypes
from threading import Lock

from commonUtils.ui import pyside as qt


class VLCReceivers:
    def __init__(self, player):
        self.player = player
        self.vlc = player.vlc
        self.items = {}
        self.lock = Lock()
        self.discoverers = []
        self.closed = False
        services = ctypes.POINTER(ctypes.POINTER(self.vlc.RdDescription))()
        count = player.instance.renderer_discoverer_list_get(ctypes.byref(services))
        try:
            names = [services[index].contents.name for index in range(count)]
        finally:
            self.vlc.libvlc_renderer_discoverer_list_release(services, count)
        for name in names:
            discoverer = player.instance.renderer_discoverer_new(name)
            if discoverer is None:
                continue
            events = discoverer.event_manager()
            for event in (self.vlc.EventType.RendererDiscovererItemAdded,
                          self.vlc.EventType.RendererDiscovererItemDeleted):
                events.event_attach(event, self.changed)
            if discoverer.start() == 0:
                self.discoverers.append(discoverer)
            else:
                discoverer.release()

    def changed(self, event):
        # python-vlc 3's generated renderer union has no item field. Read the
        # documented first pointer of the C event union without changing bindings.
        identity = ctypes.c_void_p.from_address(ctypes.addressof(event) + type(event).u.offset).value
        if not identity:
            return
        with self.lock:
            if self.closed:
                return
            if event.type == self.vlc.EventType.RendererDiscovererItemAdded:
                if identity not in self.items:
                    renderer = self.vlc.Renderer(identity)
                    renderer.hold()
                    self.items[identity] = renderer
            else:
                renderer = self.items.pop(identity, None)
                if renderer is not None:
                    renderer.release()

    def menu(self, owner, anchor):
        menu = qt.QMenu(owner)
        menu.addAction('Stop casting / return to this window', lambda: self.choose(owner, None))
        with self.lock:
            for identity, renderer in self.items.items():
                label = renderer.name()
                if isinstance(label, bytes):
                    label = label.decode('utf-8', 'replace')
                menu.addAction(str(label), lambda checked=False, key=identity: self.choose(owner, key))
            if not self.items:
                menu.addAction('Searching… Reopen Cast to refresh.').setEnabled(False)
        menu.popup(anchor.mapToGlobal(qt.QPoint(0, anchor.height())))
        owner.receiver_menu = menu

    def choose(self, owner, identity):
        if self.closed:
            return
        try:
            from services.desktop_video_access import require_external
            require_external(owner.content)
            if owner.resume_guard is not None and owner.resume_guard.blocked:
                return
            with self.lock:
                renderer = self.items.get(identity) if identity is not None else None
                if identity is not None and renderer is None:
                    owner.status.setText('The receiver is no longer available. Reopen Cast.')
                    return
                if renderer is not None:
                    renderer.hold()
            try:
                routed = self.player.route_renderer(renderer)
            finally:
                if renderer is not None:
                    renderer.release()
            if not routed:
                owner.status.setText('The receiver could not be selected. Try again.')
                return
            owner.casting = identity is not None
            owner.status.setText('Casting. Use Cast to return to this window.' if owner.casting else 'Playback returned to this window.')
        except (OSError, ValueError):
            owner.status.setText('Unlock the source before changing receivers.')

    def close(self):
        with self.lock:
            self.closed = True
        for discoverer in self.discoverers:
            discoverer.stop()
            events = discoverer.event_manager()
            for event in (self.vlc.EventType.RendererDiscovererItemAdded,
                          self.vlc.EventType.RendererDiscovererItemDeleted):
                events.event_detach(event)
            discoverer.release()
        self.discoverers = []
        with self.lock:
            for renderer in self.items.values():
                renderer.release()
            self.items.clear()
