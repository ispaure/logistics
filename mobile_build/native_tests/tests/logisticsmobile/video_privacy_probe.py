"""Native privacy/interruption acceptance; only synthetic data on owned QA devices.

Network identity and route/AVAudioSession injections are labelled synthetic.
External app/screen/cellular actions are driven by video_privacy_tools.
"""

import asyncio
import base64
from io import BytesIO
import json
from pathlib import Path
import traceback
from unittest.mock import patch
from zipfile import ZipFile

from mobile.app import LogisticsMobile
from .video_probe import until, android_player
from .video_webdav import VideoWebDAV
from mobile.screen_privacy import native_value

PASSWORD = "synthetic-session-password"


async def exercise(app):
    report = dict(
        success=False,
        cases=[],
        limitations=[
            "Wi-Fi identity and native audio-route/interruption events are injected where device APIs cannot reproduce them.",
            "State sampling cannot establish zero acoustic leakage on physical speakers.",
            "iOS protected-data lock notifications are injected and combined with real app switching; this is not physical sleep acceptance.",
            "No physical Bluetooth, headset, casting receiver, or iPhone-to-iPad Continuity call was used.",
        ],
    )
    root = Path(app.paths.cache)
    server = None
    sequence = 0
    try:
        if getattr(app, "startup_task", None) is not None:
            await asyncio.shield(app.startup_task)
        selection_file = Path(__file__).with_name("video-privacy-context.txt")
        selection = (
            selection_file.read_text().strip() if selection_file.exists() else "all"
        )
        report["context_selection"] = selection
        android = type(app._impl).__module__.startswith("toga_android.")
        report["platform"] = "android" if android else "ios"
        server = VideoWebDAV(Path(__file__).with_name("video-cloud-fixtures"))
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.mobile_storage import open_provider_document
        from features.video.mobile.player import open_video
        from features.rclone.mobile.service import native_service
        from features.rclone.remote_access import NativeRemoteLocation
        from features.rclone.localcrypt.mobile.resources import encrypted_storage

        def field(native, name):
            value = native.getClass().getDeclaredField(name)
            value.setAccessible(True)
            return value

        def actual(owner):
            return android_player(owner) if android else owner.native.native.player

        def playing(owner):
            player = actual(owner)
            return bool(
                player.isPlaying() if android else native_value(player, "isPlaying")
            )

        def visible(owner):
            native = owner.native.native
            if android:
                return bool(field(native, "attached").getBoolean(native))
            return (
                not bool(native_value(native.movie, "isHidden"))
                and native_value(native.view, "window") is not None
            )

        def user_play(owner):
            native = owner.native.native
            if android:
                field(native, "play").get(native).performClick()
            else:
                native.togglePlay(None)

        def playback_state(owner):
            """Report permission and decoder facts without capability URLs or paths."""
            audio = owner.audio_output
            state = dict(hidden=owner.hidden, allowed=owner.allowed(),
                         position=owner.native.position(), playing=playing(owner),
                         audio_available=audio.available(), audio_permitted=audio.permitted(),
                         manual_play=audio.policy.manual_play, protected=audio.protected(),
                         interrupted=audio.interrupted, captured=audio.captured,
                         transport_suspended=owner.transport.paused.is_set())
            if android:
                native = owner.native.native
                state['native'] = {name: bool(field(native, name).getBoolean(native))
                                   for name in ('focusHeld', 'manualResumeRequired',
                                                'pausePending', 'lockHidden', 'audioSuppressed')}
                state['decoder_state'] = int(actual(owner).getPlayerState())
            return state

        async def start(owner):
            if not playing(owner):
                user_play(owner)
            report['startup_states'] = [playback_state(owner)]
            def ready():
                state = playback_state(owner)
                if state != report['startup_states'][-1]:
                    report['startup_states'].append(state)
                    report['startup_states'] = report['startup_states'][-20:]
                return state['playing']
            await until(ready, timeout=30)
            await asyncio.sleep(0.12)

        async def quiet(owner, seconds=0.4, hidden=False):
            samples = 0
            deadline = app.loop.time() + seconds
            while app.loop.time() < deadline:
                assert not playing(owner), (
                    "Unexpected playback before explicit Play/authorization"
                )
                player = actual(owner)
                assert (
                    player.getVolume() == 0 or player.getPlayerState() in (0, 5, 6, 7)
                    if android
                    else bool(native_value(player.audio, "isMuted"))
                ), "Paused decoder was not muted"
                if hidden:
                    assert not visible(owner), (
                        "Native video surface visible before authorization"
                    )
                    assert not owner.allowed(), (
                        "Native controls admitted pending authentication"
                    )
                samples += 1
                await asyncio.sleep(0.02)
            # Native clock notifications can arrive after Paused. The settled
            # OS-pause test below separately checks position without this race.
            return samples

        async def external(action):
            nonlocal sequence
            sequence += 1
            (root / "video-privacy-action.json").write_text(
                json.dumps(dict(sequence=sequence, action=action))
            )
            response = root / "video-privacy-action-done.json"
            await until(
                lambda: response.exists()
                and json.loads(response.read_text()).get("sequence") == sequence,
                timeout=45,
            )
            return json.loads(response.read_text())

        def interruption(owner, began):
            native = owner.native.native
            if android:
                listener = field(native, "focusListener").get(native)
                listener.onAudioFocusChange(-2 if began else 1)
            else:
                from rubicon.objc import ObjCClass, ns_from_py

                ObjCClass("NSNotificationCenter").defaultCenter.postNotificationName(
                    "AVAudioSessionInterruptionNotification",
                    object=None,
                    userInfo=ns_from_py(
                        {
                            "AVAudioSessionInterruptionTypeKey": 1 if began else 0,
                            "AVAudioSessionInterruptionOptionKey": 1,
                        }
                    ),
                )

        def route_loss(owner):
            native = owner.native.native
            if android:
                from java import jclass

                receiver = field(native, "noisy").get(native)
                receiver.onReceive(
                    app._impl.native,
                    jclass("android.content.Intent")(
                        "android.media.AUDIO_BECOMING_NOISY"
                    ),
                )
            else:
                from rubicon.objc import ObjCClass, ns_from_py

                ObjCClass("NSNotificationCenter").defaultCenter.postNotificationName(
                    "AVAudioSessionRouteChangeNotification",
                    object=None,
                    userInfo=ns_from_py({"AVAudioSessionRouteChangeReasonKey": 2}),
                )

        # Every mode uses the same native callbacks, including when the OS has already paused it.
        async def interruptions(owner, context):
            if android:
                await start(owner)
                await external("call_begin")
                await until(lambda: not playing(owner), timeout=10)
                await quiet(owner)
                await external("call_answer")
                await quiet(owner)
                await external("call_end")
                await quiet(owner)
                await until(
                    lambda: app._impl.native.getSystemService("audio").getMode() == 0,
                    timeout=15,
                )
                report["cases"].append(
                    dict(
                        context=context, emulator_cellular_call=True, no_autoresume=True
                    )
                )
                # Any session lock caused by the dialer must be authenticated before the next test.
                privacy = app.screen_privacy
                await until(lambda: not privacy.inactive)
                if owner.hidden:
                    privacy.lock_password.value = PASSWORD
                    await privacy.unlock()
                    await until(lambda: not owner.hidden)
            await start(owner)
            interruption(owner, True)
            await until(lambda: not playing(owner))
            interruption(owner, True)
            await quiet(owner)
            interruption(owner, False)
            interruption(owner, False)
            await quiet(owner)
            await start(owner)
            actual(
                owner
            ).pause()  # Real native decoder pause before the app receives an OS notification.
            await until(lambda: not playing(owner))
            await asyncio.sleep(
                0.3
            )  # Native time notifications can trail the Paused state.
            before = owner.native.position()[0]
            interruption(owner, True)
            interruption(owner, True)
            interruption(owner, False)
            await quiet(owner)
            after = owner.native.position()[0]
            assert abs(after - before) < 250, (
                "OS pause changed position",
                before,
                after,
                playing(owner),
            )
            await start(owner)
            route_loss(owner)
            await until(lambda: not playing(owner))
            route_loss(owner)
            await quiet(owner)
            # A second route loss after an OS pause remains idempotent too.
            await start(owner)
            actual(owner).pause()
            await until(lambda: not playing(owner))
            route_loss(owner)
            await quiet(owner)
            report["cases"].append(
                dict(
                    context=context,
                    native_audio_interruption=True,
                    route_loss_notification=True,
                    wired_and_bluetooth_notification_path=True,
                    system_pause_before_callback=True,
                    duplicate_events=True,
                    no_autoresume=True,
                    route_hardware=False,
                )
            )

        async def lifecycle(owner, context, action, mode):
            privacy = app.screen_privacy
            app.preferences.save(
                session_trusted_wifi="false" if mode == "off" else "true",
                trusted_wifi_networks='["QA Home"]',
            )
            ready = app.loop.create_future()

            async def read(app):
                if mode == "failed":
                    raise OSError("Synthetic lookup failure")
                return await ready

            conceal_count = [0]
            conceal = owner.conceal

            def counted():
                conceal_count[0] += 1
                conceal()

            owner.conceal = counted
            await start(owner)
            with patch("mobile.trusted_wifi.read_ssid", side_effect=read):
                if not android and action == "sleep":
                    from rubicon.objc import ObjCClass

                    ObjCClass(
                        "NSNotificationCenter"
                    ).defaultCenter.postNotificationName(
                        "UIApplicationProtectedDataWillBecomeUnavailable", object=None
                    )
                outcome = await external(action)
                await asyncio.sleep(0.12)
                if conceal_count[0] == 0:
                    # Do not mislabel simulator display power as a real lock transition.
                    report["cases"].append(
                        dict(
                            context=context,
                            action=action,
                            wifi=mode,
                            lifecycle_observed=False,
                            limitation="Display power API did not generate app lifecycle/lock notifications",
                            host=outcome,
                        )
                    )
                    owner.conceal = conceal
                    return
                assert owner.hidden, (
                    "Session video did not conceal during native lifecycle"
                )
                if mode not in ("off", "failed"):
                    await quiet(owner, hidden=True)
                    assert privacy.inactive, (
                        "Wi-Fi decision restored content speculatively"
                    )
                    if mode == "stale":
                        # A repeated REAL app switch must invalidate the in-flight Wi-Fi result.
                        await external("switch")
                        await asyncio.sleep(0.1)
                        assert owner.hidden
                    ready.set_result(
                        "QA Home"
                        if mode in ("trusted", "stale")
                        else None
                        if mode == "unavailable"
                        else "QA Public"
                    )
                await until(lambda: not privacy.inactive)
                if mode in ("trusted", "stale"):
                    await until(lambda: not owner.hidden)
                    await quiet(owner)
                else:
                    await quiet(owner, hidden=True)
                    # Cancelled authentication is represented by leaving the prompt untouched.
                    await quiet(owner, hidden=True)
                    privacy.lock_password.value = "wrong-password"
                    await privacy.unlock()
                    await quiet(owner, hidden=True)
                    user_play(owner)
                    await quiet(owner, hidden=True)
                    privacy.lock_password.value = PASSWORD
                    await privacy.unlock()
                    await until(lambda: not owner.hidden)
                    await quiet(owner)
            owner.conceal = conceal
            report["cases"].append(
                dict(
                    context=context,
                    action=action,
                    wifi=mode,
                    lifecycle_observed=True,
                    no_pre_auth_surface=True,
                    no_pre_auth_playback=True,
                    wrong_cancelled_password_denied=mode not in ("trusted", "stale"),
                    no_autoplay=True,
                    wifi_identity="synthetic",
                    host=outcome,
                )
            )

        # Public local video before any credential account is loaded.
        local = root / "plain-video"
        local.mkdir(exist_ok=True)
        movie = (
            Path(__file__).with_name("video-cloud-fixtures") / "remote/plain/long.mp4"
        )
        (local / "long.mp4").write_bytes(movie.read_bytes())
        assert await open_video(app, LocalFiles(local), "long.mp4")
        await interruptions(app.video_player, "local ordinary")
        await app.video_player.close()
        app.show_cloud(present=False)
        if getattr(app, "cloud_restore_task", None):
            await app.cloud_restore_task

        def package():
            content = BytesIO()
            with ZipFile(content, "w") as archive:
                archive.writestr(
                    "Cloud.txt",
                    f"[Cloud]\ntype=webdav\nurl={server.url}\nvendor=other\n",
                )
                archive.writestr(
                    "Secret.txt",
                    "[Secret]\ntype=crypt\nremote=Cloud:encrypted\n"
                    "password=E7Tt68UUDf297fEq6fQq6vjnnyj003Lrpf5FuniO2qlBJqGXXm5tIg\n",
                )
            return base64.b64encode(content.getvalue()).decode()

        for restricted in (False, True):
            app.cloud_client.lock()
            if not restricted:
                await asyncio.to_thread(app.cloud_client.restore, create=True)
            names = await asyncio.to_thread(
                app.cloud_client.request,
                "import",
                package=package(),
                password=PASSWORD,
                package_name="PrivacyFixture.zip",
                session_only=restricted,
            )
            app.set_loaded_remote_names(names)
            for remote, path in (("Cloud", "plain/long.mp4"), ("Secret", "long.mp4")):
                if selection != "all" and selection != (
                    "remote" if remote == "Cloud" else "crypt"
                ):
                    continue
                resource = await asyncio.to_thread(
                    native_service(app.cloud_client).remotes.open,
                    NativeRemoteLocation(remote),
                )
                try:
                    assert await open_provider_document(app, resource, path)
                finally:
                    resource.close()
                owner = app.video_player
                assert owner.content.restricted == restricted
                context = remote + (" session-only" if restricted else " saved")
                await interruptions(owner, context)
                if restricted:
                    assert not owner.allowed(external=True)
                    for action in ("switch", "sleep"):
                        for mode in (
                            "off",
                            "trusted",
                            "public",
                            "unavailable",
                            "failed",
                            "stale",
                        ):
                            await lifecycle(owner, context, action, mode)
                await owner.close()
            if restricted and selection in ("all", "localcrypt"):
                provider = encrypted_storage(
                    root / "private-video", app.cloud_client, "Secret"
                )
                await asyncio.to_thread(
                    provider.create_file, "long.mp4", BytesIO(movie.read_bytes())
                )
                assert await open_video(app, provider, "long.mp4")
                owner = app.video_player
                await interruptions(owner, "local crypt session-only")
                for action in ("switch", "sleep"):
                    for mode in (
                        "off",
                        "trusted",
                        "public",
                        "unavailable",
                        "failed",
                        "stale",
                    ):
                        await lifecycle(owner, "local crypt session-only", action, mode)
                await owner.close()
                provider.close()
        report["success"] = True
    except Exception:
        report["error"] = traceback.format_exc()
        traceback.print_exc()
    finally:
        owner = getattr(app, "video_player", None)
        if owner is not None:
            if owner.native is not None:
                report["last_state"] = playback_state(owner)
            await owner.close()
        if server is not None:
            await asyncio.to_thread(server.close)
        (root / "video-probe-result.json").write_text(json.dumps(report, indent=2))
        print("VIDEO_PRIVACY_RESULT=" + json.dumps(report), flush=True)


class VideoPrivacyProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / "privacy-video-private"
        super().startup()

    def on_running(self):
        if getattr(self, "_privacy_video_task", None) is None:
            self._privacy_video_task = self.loop.create_task(exercise(self))


def main():
    return VideoPrivacyProbe("Video Privacy QA", "io.github.ispaure.logisticsmobile")
