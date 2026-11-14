# Local iPhone and iPad deployment

Use [manager delivery](../../user/build-manager-journeys.md) → Dev devices and select saved recipients. The low-level helper is `mobile_build/deployment/device_tools.py`. Set up [verified native prerequisites](build-manager.md#project-owned-native-prerequisite-setup), then expose the pure langdetect wheel to binary-only child installers:

```sh
export PIP_FIND_LINKS="$PWD/mobile_build/.tools/release-wheels"
```

## Reuse a verified Release archive

The archive's build number remains authoritative. Export verifies captured version, capabilities, recursive signature, team, identity and provisioning membership. In the manager choose delivery from a saved run and select recipients again. The CLI equivalent is `retained-delivery RUN --destination ios-devices --run-value 'devices.ios=["SAVED-UDID"]' --output NEWPLAN.json`.

The selected platform needs passing validation, preparation and cleanup. Verify retained/original artifact hashes and captured source. Missing input requires a fresh build. A new plan keeps original records and binds new recipients with new receipts. Explicit iOS provisioning updates permit profile/capability updates at export. Android recipients require a compatible saved Beta certificate. Availability defaults to **Try once (up to 90 seconds)**; **Wait until reachable** lets other recipients proceed. Review an uncertain install before retrying.

## Recover a retained device app after a failed build process

From the root:

```sh
python -m logistics_build.device_recovery plan --run FAILED_RUN --output RECOVERY_PLAN.json
```

Review and run in a fresh manager output directory. This requires one iOS target and no admitted original install. Recovery restages the captured payload, verifies the completed app, signature, profile and original recipe, then packages and installs the retained bytes. Keep the original build failure.

## Physical development configuration

Follow [pairing and commands](mobile-launchers.md#build-and-deploy-to-a-paired-iphone-over-wi-fi). `--device` selects an exact paired name, identifier or UDID. Preserve `io.github.ispaure.logisticsmobile`, signing team, application identifier and Keychain groups. For direct Debug diagnostics, `--skip-tests` omits Go bridge tests. The helper refreshes requirements, source and canonical plist settings, rebuilds native components and restores `MainModule=mobile` before signing. Simulator and ambiguous selections fail. Read `mobile_build/logs/device-*.log` and deployment JSON. See [artifact locations](../testing/validation-artifacts.md#find-an-output).

## Verify an in-place iOS update

Check a usable window after launch and confirm saved files by relative paths and sizes or exact byte hashes. For file sharing check both plist keys and use House Arrest `VendDocuments` with a disposable file. Verify Finder interaction separately. Preserve the installed app and its data.

## Diagnose startup after installation

Check unified logs for Python exceptions and stale requirements. From the root:

```sh
python3 dev.py test desktop test_mobile_packaging.py
python3 dev.py test mobile test_packaged_startup.py
python3 dev.py test mobile --exact-file mobile_build/tests/workspace/test_appearance.py
```

These exercise the payload and host UI. Verify the affected native window and existing groups on the target OS.

## Wireless Android discovery and recovery

`wireless_adb.py` checks paired TLS advertisements and supplements them with bounded Bonjour resolution on macOS. It prefers reachable IPv4. Pair manually. With no ready devices, a stale daemon can restart once. Preserve serving daemons during delivery. If another server owns USB, set `ADB_SERVER_SOCKET=tcp:localhost:<port>` to that server. See `test_wireless_adb.py` for discovery, changed ports and recovery contracts. **All mobile devices** means configured physical devices; tester destinations use separate delivery.
