"""Run native privacy/call probes on disposable manager-owned mobile devices."""

import argparse
from hashlib import sha1
from io import BytesIO
import json
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import time
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from build_manager.android_emulators import AndroidEmulator
from build_manager.apple_simulators import AppleSimulators
from logistics_build.build_retention import scratch
from mobile_build.deployment.android_deploy import (
    deployment_environment,
    tools_environment,
    build_tools,
)
from mobile_build.validation.video_probe_tools import prepare, cloud_fixtures
from mobile_build.validation.duo_pose_tools import prepare as prepare_ios

BUNDLE = "io.github.ispaure.logisticsmobile"
ENTRY = (
    "from tests.logisticsmobile.video_privacy_probe import main\nmain().main_loop()\n"
)


def rewrite_apk(source, destination, context):
    with ZipFile(source) as archive:
        payload = BytesIO()
        with (
            ZipFile(BytesIO(archive.read("assets/chaquopy/app.imy"))) as old,
            ZipFile(payload, "w", ZIP_DEFLATED) as new,
        ):
            for entry in old.infolist():
                new.writestr(
                    entry,
                    ENTRY
                    if entry.filename
                    in (
                        "logisticsmobile/__main__.py",
                        "tests/logisticsmobile/__main__.py",
                    )
                    else old.read(entry.filename),
                )
            new.writestr("tests/logisticsmobile/video-privacy-context.txt", context)
        build = json.loads(archive.read("assets/chaquopy/build.json"))
        build["assets"]["app.imy"] = sha1(payload.getvalue()).hexdigest()
        with ZipFile(destination, "w") as new:
            for entry in archive.infolist():
                new.writestr(
                    entry,
                    payload.getvalue()
                    if entry.filename == "assets/chaquopy/app.imy"
                    else json.dumps(build)
                    if entry.filename == "assets/chaquopy/build.json"
                    else archive.read(entry.filename),
                )


def run(platform, binary, output, *, context="all", rclone=None):
    output.mkdir(parents=True, exist_ok=False)
    events = []
    recording = None
    device = None
    emulator = None
    client = None
    cache = None
    bundle = (
        BUNDLE if platform == "android" else "io.github.ispaure.logisticsvideoprivacyqa"
    )
    label = "Build Manager Video Privacy " + uuid4().hex
    with scratch() as workspace:
        try:
            if platform == "android":
                env, _ = tools_environment(deployment_environment())
                tools = build_tools(env)
                unsigned = prepare(binary, workspace, cloud=True, rclone=rclone)
                rewritten = workspace / "privacy-unsigned.apk"
                rewrite_apk(unsigned, rewritten, context)
                key = workspace / "debug.jks"
                subprocess.run(
                    [
                        "keytool",
                        "-genkeypair",
                        "-keystore",
                        str(key),
                        "-storepass",
                        "android",
                        "-keypass",
                        "android",
                        "-alias",
                        "androiddebugkey",
                        "-dname",
                        "CN=Disposable Video Privacy QA",
                        "-keyalg",
                        "RSA",
                        "-validity",
                        "2",
                    ],
                    env=env,
                    check=True,
                    capture_output=True,
                )
                aligned, signed = workspace / "aligned.apk", workspace / "privacy.apk"
                subprocess.run(
                    [
                        str(tools / "zipalign"),
                        "-f",
                        "-P",
                        "16",
                        "4",
                        str(rewritten),
                        str(aligned),
                    ],
                    env=env,
                    check=True,
                )
                subprocess.run(
                    [
                        str(tools / "apksigner"),
                        "sign",
                        "--ks",
                        str(key),
                        "--ks-pass",
                        "pass:android",
                        "--out",
                        str(signed),
                        str(aligned),
                    ],
                    env=env,
                    check=True,
                )
                emulator = AndroidEmulator(
                    env["ANDROID_HOME"], workspace / "device", environment=env
                )
                device = emulator.start(
                    "system-images;android-36;google_apis;arm64-v8a", "pixel_9"
                )["serial"]

                def adb(*args):
                    return emulator.invoke("-s", device, *args)

                adb("install", str(signed))
                for attempt in range(3):
                    try:
                        adb("root")
                        adb("wait-for-device")
                        break
                    except RuntimeError:
                        if attempt == 2:
                            raise
                        time.sleep(1)
                ca = workspace / "video-cloud-fixtures/tls/ca.pem"
                name = (
                    subprocess.check_output(
                        [
                            "openssl",
                            "x509",
                            "-subject_hash_old",
                            "-noout",
                            "-in",
                            str(ca),
                        ],
                        text=True,
                    ).strip()
                    + ".0"
                )
                adb("shell", "mkdir", "-p", "/data/local/tmp/video-ca-store")
                adb(
                    "shell",
                    "cp /system/etc/security/cacerts/* /data/local/tmp/video-ca-store/",
                )
                adb("push", str(ca), "/data/local/tmp/video-ca-store/" + name)
                adb(
                    "shell",
                    "mount -t tmpfs -o mode=0755 tmpfs /system/etc/security/cacerts",
                )
                adb(
                    "shell",
                    "cp /data/local/tmp/video-ca-store/* /system/etc/security/cacerts/",
                )
                adb(
                    "shell",
                    "chcon -R u:object_r:system_file:s0 /system/etc/security/cacerts",
                )

                def read(name):
                    return json.loads(
                        adb("shell", "run-as", bundle, "cat", "cache/" + name)
                    )

                def write(name, value):
                    p = workspace / "response.json"
                    p.write_text(json.dumps(value))
                    adb("push", str(p), "/data/local/tmp/response.json")
                    adb(
                        "shell",
                        "run-as",
                        bundle,
                        "sh",
                        "-c",
                        "'cat /data/local/tmp/response.json > cache/"
                        + name
                        + ".tmp && mv cache/"
                        + name
                        + ".tmp cache/"
                        + name
                        + "'",
                    )

                def launch():
                    adb(
                        "shell",
                        "am",
                        "start",
                        "-W",
                        "-n",
                        bundle + "/org.beeware.android.MainActivity",
                    )

                launch()
            else:
                app = prepare_ios(binary, workspace / "build")
                (app / "app/logisticsmobile/__main__.py").write_text(ENTRY)
                (
                    app / "app/tests/logisticsmobile/video-privacy-context.txt"
                ).write_text(context)
                (app / "app/tests/logisticsmobile/__main__.py").write_text(ENTRY)
                for p in (app / "app/tests/logisticsmobile/__pycache__").glob(
                    "__main__*.pyc"
                ):
                    p.unlink()
                shutil.copytree(
                    cloud_fixtures(workspace, rclone=rclone),
                    app / "app/tests/logisticsmobile/video-cloud-fixtures",
                )
                for name in ("PlugIns", "Extensions"):
                    shutil.rmtree(app / name, ignore_errors=True)
                info = plistlib.loads((app / "Info.plist").read_bytes())
                info["CFBundleIdentifier"] = bundle
                (app / "Info.plist").write_bytes(plistlib.dumps(info))
                subprocess.run(
                    ["codesign", "--force", "--deep", "--sign", "-", str(app)],
                    check=True,
                    capture_output=True,
                )
                client = AppleSimulators()
                runtime, model = next(
                    (runtime, row["deviceTypeIdentifier"])
                    for runtime, rows in client.devices()["devices"].items()
                    for row in rows
                    if row.get("isAvailable") and platform in row["name"]
                )
                device = client.create(label, model, runtime)
                (output / "lease.json").write_text(
                    json.dumps(dict(device=device, name=label, model=model))
                )
                client.boot(device)
                client.invoke(
                    "keychain",
                    device,
                    "add-root-cert",
                    str(workspace / "video-cloud-fixtures/tls/ca.pem"),
                )
                client.invoke("install", device, str(app))
                cache = (
                    Path(client.invoke("get_app_container", device, bundle, "data"))
                    / "Library/Caches"
                )

                def locate(name):
                    paths = list(cache.rglob(name))
                    return paths[0] if paths else cache / name

                def read(name):
                    return json.loads(locate(name).read_text())

                def write(name, value):
                    target = locate("video-privacy-action.json").with_name(name)
                    temp = target.with_suffix(".tmp")
                    temp.write_text(json.dumps(value))
                    temp.replace(target)

                def launch():
                    for attempt in range(3):
                        try:
                            client.invoke("launch", device, bundle)
                            return
                        except RuntimeError as error:
                            # A shell crash may restart the app and reset the probe.
                            # Never continue and mistake a second run for a valid transition.
                            if "probably crashed" in str(error):
                                events.append(dict(action="simulator_shell_crash", error=str(error)))
                                raise
                            events.append(
                                dict(
                                    action="launch_retry",
                                    attempt=attempt + 1,
                                    error=str(error),
                                )
                            )
                            if attempt == 2:
                                raise
                            time.sleep(1)

                # The simulator recording covers real app-switch transitions; it has no device audio track.
                recording = subprocess.Popen(
                    [
                        "xcrun",
                        "simctl",
                        "io",
                        device,
                        "recordVideo",
                        "--codec=h264",
                        str(output / "transitions.mov"),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=(output / "recording.log").open("w"),
                )
                launch()
            deadline = time.monotonic() + 900
            last = 0
            while time.monotonic() < deadline:
                try:
                    report = read("video-probe-result.json")
                except (OSError, RuntimeError, ValueError):
                    report = None
                if report is not None:
                    report["external_actions"] = events
                    (output / "result.json").write_text(json.dumps(report, indent=2))
                    if not report["success"]:
                        raise RuntimeError(
                            report.get("error", "Native privacy probe failed")
                        )
                    print(
                        json.dumps(
                            dict(
                                platform=platform,
                                success=True,
                                cases=len(report["cases"]),
                            )
                        ),
                        flush=True,
                    )
                    return
                try:
                    request = read("video-privacy-action.json")
                except (OSError, RuntimeError, ValueError):
                    time.sleep(0.1)
                    continue
                if request["sequence"] == last:
                    time.sleep(0.1)
                    continue
                last = request["sequence"]
                action = request["action"]
                result = dict(request, platform=platform)
                if platform == "android":
                    if action == "switch":
                        adb("shell", "input", "keyevent", "KEYCODE_HOME")
                        time.sleep(0.7)
                        launch()
                    elif action == "sleep":
                        adb("shell", "input", "keyevent", "KEYCODE_SLEEP")
                        time.sleep(0.7)
                        result["power_off"] = adb("shell", "dumpsys", "power")[-3000:]
                        adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
                        adb("shell", "wm", "dismiss-keyguard")
                        launch()
                    elif action == "call_begin":
                        adb("emu", "gsm", "call", "5550100")
                    elif action == "call_end":
                        adb("emu", "gsm", "cancel", "5550100")
                        launch()
                    elif action == "call_answer":
                        adb("emu", "gsm", "accept", "5550100")
                else:
                    if action == "switch":
                        client.invoke("launch", device, "com.apple.Preferences")
                        time.sleep(0.7)
                        launch()
                    elif action == "sleep":
                        client.invoke("launch", device, "com.apple.Preferences")
                        time.sleep(0.7)
                        launch()
                        result["scope"] = (
                            "Injected protected-data lock notification plus real app background/resume; not physical sleep"
                        )
                result["completed"] = True
                events.append(result)
                (output / "live-actions.json").write_text(json.dumps(events, indent=2))
                write("video-privacy-action-done.json", result)
            raise TimeoutError("Native privacy probe timed out")
        finally:
            provenance = workspace / "video-cloud-fixtures/fixture-tool.json"
            if provenance.is_file():
                shutil.copy2(provenance, output / "fixture-tool.json")
            (output / "external-actions.json").write_text(json.dumps(events, indent=2))
            if recording is not None:
                recording.send_signal(signal.SIGINT)
                try:
                    recording.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    recording.terminate()
                    recording.wait(timeout=10)
            if emulator is not None:
                try:
                    startup_log = emulator.workspace / "emulator.log"
                    if startup_log.is_file():
                        shutil.copy2(startup_log, output / "emulator.log")
                    if device is not None:
                        (output / "logcat.txt").write_text(
                            emulator.invoke("-s", device, "logcat", "-d", timeout=30)
                        )
                finally:
                    emulator.cleanup()
                    (output / "cleanup.json").write_text(
                        json.dumps(dict(device=device, emulator_removed=True))
                    )
            if client is not None and device is not None:
                try:
                    (output / "springboard.log").write_text(
                        client.invoke(
                            "spawn",
                            device,
                            "log",
                            "show",
                            "--last",
                            "2m",
                            "--style",
                            "compact",
                            "--predicate",
                            'process == "SpringBoard"',
                            timeout=30,
                        )
                    )
                except RuntimeError as error:
                    (output / "diagnostics-error.txt").write_text(str(error))
                finally:
                    client.remove(device, label)
                    (output / "cleanup.json").write_text(
                        json.dumps(dict(device=device, simulator_removed=True))
                    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("android", "iPhone", "iPad"))
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rclone", type=Path, help="Pinned host rclone for synthetic fixtures when absent from a frozen source snapshot")
    parser.add_argument(
        "--context", choices=("all", "remote", "crypt", "localcrypt", "scope"), default="all"
    )
    args = parser.parse_args()
    run(
        args.platform,
        args.binary.resolve(),
        args.output.resolve(),
        context=args.context,
        rclone=args.rclone,
    )
