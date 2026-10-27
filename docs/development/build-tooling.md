# Mobile build tooling owners

The Briefcase project, generated output paths, native bridge and installed app
identities remain unchanged. Organize tooling by the work a contributor needs
to do; application features stay in `Python/`.

| Work | Owner |
| --- | --- |
| Curate the public Python payload and verify its source identity | `mobile_build/tools.py` |
| Validate collected guest evidence, report outcomes and clean only after collection | `Scripts/guest_results.py`; platform setup/transport stays in the Linux/Windows backends |
| Build and link the native bridge; compose generated-project adapters | `mobile_build/cloud_build.py` |
| Configure camera, scenes, privacy manifests and app artwork | `mobile_build/build_support/` |
| Regenerate canonical navigation and folder artwork | `mobile_build/build_support/generate_navigation_icons.py`, `generate_folder_icons.py` |
| Device install, deployment policy, Firebase and TestFlight | `mobile_build/deployment/`; reusable command controls and sequencing in external `build_manager.deployment_commands*` |
| App Store Connect signing/HTTP/polling and Firebase CLI transport | External `build_manager.app_store_connect` and `build_manager.firebase`; app/destination policy remains in `mobile_build/deployment/` |
| Operator builds and delivery | Standalone Build Deployment Manager with the Logistics adapter |
| Native report verification, lifecycle drivers and synthetic fixture generators | `mobile_build/validation/` |
| Host regression contracts | `mobile_build/tests/` |
| On-device checks and synthetic fixtures | `mobile_build/native_tests/` |

Linux bootstrap and Windows portable-tool preparation execute the external
manager's `build_manager.guest_tools` programs. `Scripts/build_manager_tools.json`
retains Logistics' uv/Git archives, interpreter selectors and architecture choices.
`Scripts/vm_backend.py` and `Scripts/windows_backend.py` keep their entry points,
suite routing, selected-guest policy and preparation/evidence receipts. Tool
preparation does not imply a passed suite. The extraction preserves existing
workspace ownership, interactive Windows account checks, archive hashes and
collect-before-cleanup behavior; it does not replace dedicated-machine creation
or silently select a different Python architecture.

Operator builds and delivery start in the standalone manager. The six legacy mobile deployment shortcuts, `deploy_ui.py` and `deploy_all.py` have been removed. Logistics retains the device, signing, Firebase and TestFlight helpers consumed by its adapter. `deployment_confirmation.py` retains the low-level interactive upload protocol; it does not establish manager release acceptance. See the [operator guide](../user/build-manager.md).

`testflight_external.py` retains credential-reference selection, the Logistics
bundle/app and external-group checks, audience/expiry restrictions, localization
and review-state decisions, additive group assignment and its project report.
It delegates JWT signing, authenticated same-origin HTTP, pagination and exact
processing waits to the external App Store Connect client. Cryptography remains
an optional host dependency pinned by `requirements-testflight.txt`; importing
the manager does not load it or read project credentials.

Firebase CLI installation/location, authentication permission, app/package/group
checks, signing, counters and explicit upload approval remain here. The external
Firebase client owns CLI invocation and response parsing, including direct
console delivery and captured operation receipts. `Scripts/distribute_prepared.py`
still checks the reviewed artifact/destination and writes its attempt marker
before a provider write. Missing/ambiguous receipts keep that marker and prevent
blind replay. Neither reusable client automatically retries writes or signs in.

`build_support` edits only generated projects or explicitly requested canonical
artwork. Its imports have no build or deployment side effects. `cloud_build.py`
shows adapter composition explicitly before compiling the bridge. It uses the
same generated workspaces and native resource sources as before.

For normal build commands and platform prerequisites, see the
[mobile handbook](mobile-handbook.md). For signing and distribution, see
[TestFlight](mobile-testflight.md) and [device deployment](mobile-device-deployment.md).

## Deployment commands and paths

Run deployment modules from the repository root, for example:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools --help
mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_tools --help
```

Run diagnostic module commands from the repository root. Manager adapter phases
set their working directory and interpreter explicitly. No deployment module
catches an arbitrary ImportError to guess whether it was loaded as a script.

`deployment_paths` still separates canonical settings/signing files from generated
platform workspaces. Moving Python owners does not move `.device.json`,
`.android-beta`, `.tools`, `.testflight-auth.json`, `build/` or `.deploy-workspaces/`.
The manager reviews prepared artifacts and destinations before tester uploads.

## Validation commands

The device workflow keeps `mobile_build` as its working directory and runs
`python validation/ui_tools.py ...`. Report contracts still validate the exact
source revisions, selected device and required case set. Native test application
sources remain in `native_tests/tests/`; host regression sources stay in `tests/`.
Run the standalone Duo pose audit from the repository root as
`python -m mobile_build.validation.duo_pose_tools --help`.

The build root now has three Python entry points: `tools.py` for payloads,
`cloud_build.py` for native project composition and `select_ios_sdk.py` for SDK
selection. Credentials, manifests, native bridge sources and build products keep
their existing paths.

## Find mobile regression contracts

`mobile_build/tests/` groups contracts by responsibility. Test filenames remain
unique, so the developer command still accepts a single filename and discovers it
recursively:

```sh
python dev.py test mobile test_native_report.py
python dev.py test mobile 'test_reader_*.py'
```

| Folder | Contracts and reusable test fixtures |
| --- | --- |
| `tooling/` | Payload/build identity, native reports, signing, distribution and worker launchers |
| `reading/` | EPUB/PDF/comic readers, library, progress and lifecycle |
| `documents/` | Open/save, drafts, document menus, imports and offline help |
| `storage/` | Browser/folder navigation, local search and file operations |
| `transfers/` | Cloud credentials, LocalCrypt, mirror jobs and reviewed transfers |
| `workspace/` | Host composition, navigation, settings and retained window/session owners |
| `native/` | Platform controls, sizing, rotation, keyboard and native adapters |
| `editing/` | Source/Markdown editing, search and speech presentation |
| `chat/` | Conversations, inventory, deferred chat and transcript DOM contracts |

Cross-group fixtures use explicit `mobile_build.tests.<group>.<module>` imports,
so moving a file does not rely on another test directory being on sys.path. The
EPUB and transcript DOM drivers stay beside their Python contracts. Use the
existing isolated-module runner for a full suite; no compatibility forwarding
test modules or generated test registries are needed.


## Signed local coverage in hosted releases

Combined journeys with GitHub publication capture an immutable export request
for eligible input-bound host test phases. The reviewed publication command
checks the clean exact source and authenticated local receipts, signs only recent
passed coverage and publishes a Git note at `refs/notes/build-manager-tests`
before pushing the release tag. Existing notes are never replaced. If exporting
or publishing proof fails, ordinary release gates remain enabled; no failed or
missing test becomes a pass. A standalone release without local tests exports no
proof. Packaging and publication checks still run.

The private Ed25519 signing key lives in the manager's Application Support
configuration, keyed by repository. One-time enrollment is explicit:

```sh
.venv/bin/python -m Scripts.release_test_evidence enroll --repository ispaure/logistics
```

Review and commit only `.github/local-test-signers`. It contains a public key
restricted to the manager test-evidence signing namespace, without machine/user
comments. Keep the private key outside Git and CI. Removing a public signer from
the selected source revokes trust for that source's releases.

Hosted desktop platform checks fetch optional notes read-only. Each host suite
recomputes its actual source, command, environment and toolchain fingerprint.
It may reuse only a signed matching suite from the exact source/repository and
pinned dependencies, using the allowlist read from that Git commit. Both signing
and original test completion must be less than 24 hours old. A changed working
allowlist cannot enroll another signer. The report labels the result `reused`
and retains signer, source and input identity; it does not pretend to execute
those tests again. Invalid/unavailable proof or any input mismatch runs fresh.

This integration currently covers the input-bound portable host suites executed
through `Scripts.platform_checks.run_check`. It does not infer equivalence for
native simulator/emulator/runtime tests, static workflow checks, different
architectures or different Python/toolchain installations. Such coverage stays
fresh. In particular, a local Mac and GitHub's Mac image can legitimately have
different keys. Earlier successful GitHub workflow reuse is a separate check.


Guest setup and checks now emit a throttled host-side elapsed waiting message,
including receipt reconciliation on a lost Windows transport result. These
messages identify a headless wait; they do not assert guest activity, test counts
or a successful result. They add no VM polling. Collected reports and bound
worker receipts remain authoritative.
