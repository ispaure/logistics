# Validating and delivering Logistics

Use the standalone manager to run checks, build an artifact or deliver it.
A **preset** saves choices. A **plan** captures source and actions. A **run**
records the work and evidence.

## Use the guided flow

1. Add or select the trusted Logistics checkout. For setup and repair, see
   [Using the Logistics build manager](build-manager.md).
2. Choose **Run checks**, **Build only**, or **Prepare and deliver**. Choose
   platforms and hosts. A GitHub host dispatches hosted checks even without
   a GitHub release destination.
3. For delivery, choose the destinations explicitly. Firebase needs the
   Android gate. TestFlight needs the iOS gate, including iPhone, Duo and iPad.
   GitHub source publication needs the desktop gates and its hosted release
   policy. It publishes a source ZIP separately from tester artifacts.
4. Choose **Current files** for a captured local snapshot, including local
   Logistics and commonUtils edits. Choose **Latest commit** to exclude edits.
   Hosted checks require committed source. GitHub publication also requires a
   clean matching checkout and an unused release tag.
5. In **Review plan**, inspect the exact source, gates, recipients, signing and
   destinations. Fresh GUI **Start** authorizes selected tester uploads and GitHub
   actions after their gates pass. Device installs still pause for review.
   CLI and retained plans use their own declared review requirements.

A failed branch only blocks work that depends on it. Resume verifies retained
artifacts before reuse. Reconcile an uncertain upload or install before trying
again.

## Tester messages and development devices

A nonempty tester message applies to both selected tester services. Leaving it
blank uses each service's saved notes. Groups stay separate.

In **Delivery → Development**, choose exact Android recipients or paired iPhone
or iPad IDs. No target is selected by default. For an offline device choose
whether to try once or wait for reconnection. The manager never substitutes a
recipient. Verify the package and recipient before approving an install.
Signing and version conflicts stop the install without removing the installed
app or clearing data.

iOS profiles must cover the selected devices. The default uses existing
profiles. For explicit Debug provisioning repair, the per-run
`devices.ios_provisioning=update` setting lets Xcode update profiles without
registering a device. Release exports use existing profiles.

## Mobile release preset without GitHub

If saved, open **Full Testing, Release & Build (Mobile, excl. GitHub)**.
Confirm local iOS and Android hosts, the intended source and recipients, and
your test reuse choice. The preset carries choices. Review the new plan before
starting.

## CLI: local Android validation and Boox deployment

From the manager checkout, use `list` to find the Logistics registration ID
and `inputs --project REGISTRATION_ID` to confirm the hardware ID. Substitute
the exact plan and step identities returned by the commands. Use a fresh output
directory for each run.

```sh
.venv/bin/python -m build_manager.cli journey --project REGISTRATION_ID \
  --goal deliver --platform android --destination android-devices \
  --execution 'android=This Mac — Android Emulator' --revision working-tree \
  --run-value 'devices.android=["HARDWARE_ID"]' \
  --run-value 'devices.android_connections={"HARDWARE_ID":"ADB_SERIAL"}' \
  --run-value devices.android_signing=beta \
  --run-value devices.android_variant=debug --output test-results/build-manager/boox-plan.json
.venv/bin/python -m build_manager.cli show-plan test-results/build-manager/boox-plan.json
.venv/bin/python -m build_manager.cli run test-results/build-manager/boox-plan.json \
  --output test-results/build-manager/boox-run --expect-identity PLAN_SHA256 --events
.venv/bin/python -m build_manager.cli review test-results/build-manager/boox-run
.venv/bin/python -m build_manager.cli resume test-results/build-manager/boox-run \
  --confirm --expect-identity PLAN_SHA256 --approval-identity STEP=REVIEW_SHA256
```

Exit 3 means a prepared action awaits review. Use `status RUN_DIRECTORY` and
`logs RUN_DIRECTORY --step STEP` for evidence. Use `devices.android_connections`
only for a specific selected device and transport. Wi-Fi installs verify the
same hardware identity. Use the signing mode and certificate for the package
already installed on that recipient. After Boox testing, remove temporary QA
packages while keeping the main Logistics app and data.

## Shared builds and device variants

**Debug** uses a development package. **Release** can reuse the Android
Firebase APK or export a device app from the iOS Release archive. A
device-only iOS run omits TestFlight export and upload. Release devices keep
the local native and runtime gates. Installation always requires approval of
the exact package and recipient.
