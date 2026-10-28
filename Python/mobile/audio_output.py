"""App audio consent owner; native adapters report routes, players supply pause."""
import json
from weakref import WeakSet
from services.audio_output import OutputPolicy, approvals

_owners = WeakSet()


def for_app(app):
    owner = getattr(app, 'audio_output', None)
    if owner is None:
        app.audio_output = owner = AudioOutput(app)
    return owner


class AudioOutput:
    def __init__(self, app, native=None):
        self.app = app
        self.policy = OutputPolicy()
        self.players = {}
        self.closed = False
        self.prompt = None
        self.prompted_revision = None
        self.native = native
        self.interrupted = False
        self.captured = False
        _owners.add(self)
        if native is None:
            from .audio_output_native import monitor
            self.native = monitor(app, self.refresh, self.interrupt)
        self.refresh()
        privacy = getattr(app, 'screen_privacy', None)
        self.capture_changed(bool(privacy is not None and privacy.sensitive() and getattr(privacy, 'captured', False)))

    def approved(self):
        return approvals(self.app.preferences.values.get('approved_bluetooth_devices', '[]'))

    def register(self, player, pause):
        self.players[player] = pause

    def unregister(self, player):
        self.players.pop(player, None)

    def refresh(self):
        if self.closed:
            return
        try:
            route = self.native.outputs()
        except Exception:
            route = None
        if self.policy.observe(route):
            self.pause()
            if self.players:
                self.offer()

    def pause(self):
        self.policy.pause()
        for pause in tuple(self.players.values()):
            pause()  # Explicit, idempotent pause; never toggle, seek or resume.

    def interrupt(self, active):
        self.interrupted = bool(active)
        self.pause()  # Ending an interruption does not grant playback permission.

    def capture_changed(self, blocked):
        changed = bool(blocked) and not self.captured
        self.captured = bool(blocked)  # Close permission before reentrant pause callbacks.
        if changed:
            for owner in tuple(_owners):
                if owner.app.preferences.path == self.app.preferences.path:
                    owner.pause()

    def available(self):
        captured = any(owner.captured for owner in tuple(_owners)
                       if owner.app.preferences.path == self.app.preferences.path)
        try:
            return (not self.closed and not self.interrupted and not captured
                    and getattr(self.app, 'active_host', True) and not self.native.in_call())
        except Exception:
            return False

    def permitted(self):
        self.refresh()
        return self.available() and self.policy.permitted(self.approved())

    def prepare(self):
        try:
            prepare = getattr(self.native, 'prepare', None)
            if prepare is None or prepare():
                return True
        except Exception:
            pass
        self.policy.observe(None)
        self.pause()
        return False

    def request_play(self):
        if not self.available():
            return False
        if not self.prepare():
            self.offer(explicit=True)
            return False
        self.refresh()
        if not self.available():
            return False
        if self.policy.request_play(self.approved()):
            return True
        self.offer(explicit=True)
        return False

    def interactive(self):
        privacy = getattr(self.app, 'screen_privacy', None)
        return self.available() and (privacy is None or (
            not privacy.inactive and getattr(privacy, 'saved_content', None) is None
            and not any(gate.locked for gate in privacy.gates())))

    def offer(self, *, explicit=False):
        if self.closed or self.prompt is not None or not self.interactive():
            return
        if explicit:
            self.prompted_revision = None
        if self.prompted_revision == self.policy.revision:
            return
        self.prompted_revision = self.policy.revision
        if not self.policy.identified() or self.policy.pending(self.approved()):
            self.prompt = self.app.loop.create_task(self.ask(self.policy.revision))

    async def ask(self, revision):
        import toga
        try:
            if revision != self.policy.revision or not self.interactive():
                return
            pending = self.policy.pending(self.approved())
            if not self.policy.identified():
                await self.app.main_window.dialog(toga.InfoDialog('Audio output unavailable',
                    'Playback is paused because the selected audio output cannot be identified. '
                    'Select an identifiable output in system controls and press Play again. '
                    'Manage saved approvals in Settings → Audio playback.'))
                return
            if not pending:
                return
            names = ', '.join(item.label for item in pending)
            accepted = await self.app.main_window.dialog(toga.ConfirmDialog('Approve Bluetooth audio?',
                f'Allow audio playback through {names}? This applies to video and read-aloud. '
                'Adding approval leaves playback paused. Press Play separately when ready. '
                'You can remove approval in Settings → Audio playback.'))
            self.refresh()
            # A route/credential/lifecycle transition invalidates an old decision.
            if (accepted and self.available() and self.policy.revision == revision
                    and self.policy.pending(self.approved()) == pending):
                self.save({**self.approved(), **{item.identity: item.label for item in pending}})
        except (OSError, ValueError):
            await self.app.main_window.dialog(toga.InfoDialog('Approval was not saved',
                'Playback remains paused. Try again in Settings → Audio playback.'))
        finally:
            self.prompt = None
            # A stale decision leaves playback paused; only a new Play asks again.

    def save(self, values):
        self.app.preferences.save(approved_bluetooth_devices=json.dumps(
            [dict(id=key, name=name) for key, name in sorted(values.items())]))
        # One preference file is shared by scenes; approval changes always pause.
        for owner in tuple(_owners):
            if owner.app.preferences.path == self.app.preferences.path:
                if owner is not self:
                    owner.app.preferences.reload()
                owner.policy.revision += 1
                owner.pause()

    def invalidate(self, *, pause=True):
        self.policy.revision += 1
        if pause:
            self.pause()

    def dispose(self):
        if self.closed:
            return
        self.closed = True
        self.pause()
        self.players.clear()
        if self.prompt is not None:
            self.prompt.cancel()
        self.native.dispose()
        _owners.discard(self)
