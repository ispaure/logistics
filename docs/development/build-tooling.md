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
| User-facing deployment commands | Existing `mobile_build/*.command` launchers |
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

The legacy `deploy_ui.py` entry point now composes `ManagerPanel` and the external
manager's `CommandPanel`. `LogisticsDeployment` supplies device inventory parsing,
module arguments, destination labels, interpreter/profile/toolchain settings and
log locations. The manager owns target retention, asynchronous process output,
explicit GUI confirmation and busy controls. The shell prevents closing during
either a manager run or a direct deployment; the two paths cannot start together.

`deploy_all.py` retains the ordered iOS-device, Android-device, TestFlight and
Firebase launcher policy and its failure prompt. It delegates ordered execution
to `build_manager.deployment_commands.run_sequence`. These interactive commands
inherit terminal input; they do not produce release-acceptance evidence or retry
effects. An earlier failure remains a failure after continuing. The existing
`deployment_confirmation.py` wrapper preserves `LOGISTICS_UPLOAD_CONFIRM:` while
delegating framing/input to the manager. All six `.command` paths remain intact.

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

The existing `.command` files work from any directory and select that import
context themselves. Deployment child workers and the Qt deployment window use
the same module commands. No deployment module catches an arbitrary ImportError
to guess whether it was loaded as a script.

`deployment_paths` still separates canonical settings/signing files from generated
platform workspaces. Moving Python owners does not move `.device.json`,
`.android-beta`, `.tools`, `.testflight-auth.json`, `build/` or `.deploy-workspaces/`.
The launcher UI keeps its existing confirmation protocol before tester uploads.

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
