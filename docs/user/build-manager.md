# Using the Logistics build manager

Open Build Deployment Manager, then add or select the trusted Logistics
checkout. Adding a checkout authorizes its adapter. Start by running local
checks with no delivery destination. See [Validating and delivering Logistics](build-manager-journeys.md).

## Combined validation and delivery

Choose platforms and execution hosts, then choose destinations separately.
**Review plan** shows the captured source, required checks and actions.
A fresh GUI **Start** authorizes selected tester uploads and GitHub actions
after their gates pass. Device installs pause for a separate review. For the
CLI, follow the [Boox example](build-manager-journeys.md#cli-local-android-validation-and-boox-deployment).

## Publish GitHub without testing

Advanced **Release → GitHub** prepares a source release without local gates.
Keep **Run GitHub validation** on for normal hosted checks. When explicitly
publishing without those checks, turn it off and review the new plan. The
release records the opt-out. Independent push-triggered CI can still run.
Use the full preset with the appropriate validation settings for a tested
release. GitHub publication requires a clean committed checkout.

## Settings and identity

Settings shows where each effective value comes from. Saving writes the local
profile. App version edits update the tracked desktop and mobile version files.
Build numbers and release tags are separate. **Automatic** previews the next
local number until the build reserves it. Provider checks still govern acceptance.

Choose platform tools, VM or simulator targets, signing references and tester
groups in Settings. **Verify connection** reads service identity without
uploading, installing or dispatching. A prepared artifact keeps its source,
embedded version, signing identity and reviewed destination even if you edit
Settings later.

## Reviewing and deleting local builds

Use **Clean up builds…** to review categories, sizes and exact paths. Manual
deletion can remove recent outputs. The confirmation checks ownership, active
locks and pins. **Retained workflows** lets you retire a run, releasing its
holds and disabling continuation while keeping the outcome and logs. Reconcile
an uncertain delivery with its provider before starting a replacement.

Only adopt build folders or exact simulator IDs you can confirm are disposable.
Copy out needed evidence first. A name alone does not establish ownership.
See [storage retention](../development/build-release/build-manager.md#automatic-storage-retention)
for what automatic cleanup keeps.

## External manager installation (adapter API 1)

Set up the desktop and mobile environments first. Use the project tooling
repair action for the pinned Manager. For an explicit reviewed checkout, use
the Logistics installer once per environment:

```sh
.venv/bin/python -m logistics_build.install_build_manager /path/to/build-deployment-manager
mobile_build/.venv/bin/python -m logistics_build.install_build_manager /path/to/build-deployment-manager
```

On Windows, use each environment's **Scripts/python.exe**. For an offline
install, initialize the Manager checkout's pinned submodules and use uv with
a cached build backend. Repeat for each interpreter.

```sh
uv pip install --offline --python .venv/bin/python --no-deps -e /path/to/build-deployment-manager/Python
```

### Project tooling readiness and repair

Choose **Project tooling → Update project tooling** to verify and install the
declared pin in both project environments. Active workflows block repair. From
the Logistics root, the equivalent is:

```sh
python3 logistics_build/tooling_bootstrap.py status
python3 logistics_build/tooling_bootstrap.py update --confirmed
```

On Windows use **py**. If status reports an unfinished mutation without verified
cleanup, restart the host, then run the update again. Keep the recovery record
in place. See [manager integration](../development/build-release/build-manager.md)
for pinned native prerequisites, offline setup and guest requirements.

## Registered workflows and fixed settings

The trusted project descriptor supplies Logistics tests and destinations.
Each run captures the effective settings and account references, so a later
profile edit cannot redirect it. Uncertain external actions require
reconciliation before retry.

## Execution locations and inputs for one run

Select a local host for a local-only check. A GitHub execution choice dispatches
hosted checks for committed source. A hosted pass does not replace native local
tester gates. Review one-run notes, groups, signing and recipients before starting.

## Android and iOS can progress independently

Independent steps can overlap. A waiting card names the resource it needs.
Sharing build tools or signing can serialize steps. iPhone, Duo and iPad checks
retain their order and cleanup.

## Reuse verified tests per preset

**Reuse verified test results** uses matching retained evidence. Select the
fresh option to execute again when diagnosing failures or measuring performance.
Review the active preset's choice. The CLI setting is
`--run-value testing.reuse_verified_results=off`.

## Build without tests or delivery

Choose **Build only**, then a supported local iOS or Android host. This creates
a simulator app or test APK. Use a delivery flow for installing or submitting it.
