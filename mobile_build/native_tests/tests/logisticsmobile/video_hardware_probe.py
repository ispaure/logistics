"""Interactive, isolated iPhone acceptance with synthetic local/LocalCrypt video."""

import asyncio
from io import BytesIO
import json
from pathlib import Path
import time
import traceback

from mobile.app import LogisticsMobile
from mobile.screen_privacy import native_value

PASSWORD = "Video-QA-2026"


async def exercise(app):
    root = Path(app.paths.cache)
    report = dict(
        scope="Physical iPhone; user-operated calls, lock and audio routes",
        phase="starting",
        events=[],
        violations=[],
    )
    blocks = []
    observers = []
    owner = None

    def save():
        target = root / "video-hardware-result.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2))
        temp.replace(target)

    def sample(event="sample"):
        player = getattr(app, "video_player", None)
        if player is None or player.native is None:
            return
        native = player.native.native
        try:
            gates = app.screen_privacy.gates()
            authorized = (
                not app.screen_privacy.inactive
                and not any(g.locked for g in gates)
                and app.screen_privacy.saved_content is None
            )
            visible = (
                not native_value(native.movie, "isHidden")
                and native_value(native.view, "window") is not None
            )
            playing = bool(native_value(native.player, "isPlaying"))
            muted = bool(native_value(native.player.audio, "isMuted"))
            state = dict(
                at=time.time(),
                event=event,
                phase=report["phase"],
                session_only=player.restricted,
                authorized=authorized,
                visible=visible,
                playing=playing,
                muted=muted,
                manual_resume_required=bool(native.manualResumeRequired),
                active_call=bool(native.hasActiveCall()),
            )
            if (
                player.restricted
                and not authorized
                and (visible or (playing and not muted))
            ):
                report["violations"].append(state)
            last = report["events"][-1] if report["events"] else None
            if (
                event != "sample"
                or last is None
                or any(
                    state[k] != last.get(k)
                    for k in (
                        "phase",
                        "authorized",
                        "visible",
                        "playing",
                        "muted",
                        "active_call",
                        "manual_resume_required",
                    )
                )
            ):
                report["events"].append(state)
                save()
        except Exception as error:
            report["sample_error"] = str(error)
            save()

    try:
        if getattr(app, "startup_task", None) is not None:
            await asyncio.shield(app.startup_task)
        from rubicon.objc import ObjCClass, Block, objc_id

        center = ObjCClass("NSNotificationCenter").defaultCenter
        for name in (
            "UIApplicationWillResignActiveNotification",
            "UIApplicationDidBecomeActiveNotification",
            "UIApplicationProtectedDataWillBecomeUnavailable",
            "UIApplicationProtectedDataDidBecomeAvailable",
            "AVAudioSessionInterruptionNotification",
            "AVAudioSessionRouteChangeNotification",
        ):

            def receive(notification, name=name):
                app.loop.call_later(0.02, sample, name)

            block = Block(receive, None, objc_id)
            blocks.append(block)
            observers.append(
                center.addObserverForName(
                    name, object=None, queue=None, usingBlock=block
                )
            )
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.mobile.player import open_video

        fixtures = Path(__file__).with_name("video-fixtures")
        local = root / "hardware-local"
        local.mkdir(exist_ok=True)
        (local / "hardware.mp4").write_bytes((fixtures / "hardware.mp4").read_bytes())

        async def observe(phase, provider, path, message):
            nonlocal owner
            report["phase"] = phase
            save()
            assert await open_video(app, provider, path)
            owner = app.video_player
            owner.native.status(message)
            while not owner.closed:
                sample()
                await asyncio.sleep(0.02)
            report["events"].append(
                dict(at=time.time(), event="user_done", phase=phase)
            )
            save()

        await observe(
            "ordinary",
            LocalFiles(local),
            "hardware.mp4",
            "QA 1/3: Press Play. Test calls, headphone unplug and Bluetooth loss. Playback must stay paused afterward. Done advances.",
        )
        from .audio_hardware_probe import phase as audio_phase
        await audio_phase(app, 'ordinary')
        fixture = json.loads(
            Path(__file__).with_name("localcrypt_fixture.json").read_text()
        )
        app.show_cloud(present=False)
        if getattr(app, "cloud_restore_task", None):
            await app.cloud_restore_task
        app.cloud_client.request(
            "import",
            package=fixture["package"],
            password=PASSWORD,
            package_name="HardwareVideoQA.zip",
            session_only=True,
        )
        from features.rclone.localcrypt.mobile.resources import encrypted_storage

        provider = encrypted_storage(
            root / "hardware-crypt", app.cloud_client, "Secret"
        )
        await asyncio.to_thread(
            provider.create_file,
            "hardware.mp4",
            BytesIO((local / "hardware.mp4").read_bytes()),
        )
        app.preferences.save(session_trusted_wifi="false")
        await observe(
            "session-only password required",
            provider,
            "hardware.mp4",
            "QA 2/3: Test app switching, lock, calls and headset loss. Resume password: Video-QA-2026. No autoplay. Done advances.",
        )
        await audio_phase(app, 'session-only loaded')
        report["phase"] = "requesting Wi-Fi permission"
        save()
        from mobile.trusted_wifi import request_access, read_ssid

        allowed = await request_access(app)
        ssid = await read_ssid(app) if allowed else None
        report["trusted_wifi_available"] = bool(ssid)
        if ssid:
            app.preferences.save(
                session_trusted_wifi="true", trusted_wifi_networks=json.dumps([ssid])
            )
            # Permission dialogs can themselves lock the credential session.
            while any(g.locked for g in app.screen_privacy.gates()):
                await asyncio.sleep(0.1)
            await observe(
                "session-only trusted Wi-Fi",
                provider,
                "hardware.mp4",
                "QA 3/3: Trusted Wi-Fi enabled. Switch apps and lock: video/audio must remain hidden until the check finishes, then stay paused. Done finishes.",
            )
        else:
            report["trusted_wifi_limitation"] = (
                "Current Wi-Fi identity unavailable; password remains required."
            )
            app.preferences.save(session_trusted_wifi="true")
            await observe(
                "session-only Wi-Fi unavailable",
                provider,
                "hardware.mp4",
                "QA: Wi-Fi exception enabled but identity unavailable. Switching apps must still require the password. No autoplay. Done finishes.",
            )
        provider.close()
        report["phase"] = "complete"
        report["automated_state_success"] = not report["violations"]
        save()
    except Exception:
        report["phase"] = "error"
        report["error"] = traceback.format_exc()
        save()
    finally:
        if owner is not None and not owner.closed:
            await owner.close()
        if observers:
            for observer in observers:
                center.removeObserver(observer)
        save()


class HardwareVideoProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / "hardware-video-qa-private"
        super().startup()

    def on_running(self):
        if getattr(self, "_hardware_task", None) is None:
            self._hardware_task = self.loop.create_task(exercise(self))


def main():
    return HardwareVideoProbe(
        "Video Privacy QA", "io.github.ispaure.logisticsvideoprivacyqa"
    )
