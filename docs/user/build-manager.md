# Using the Logistics build manager

Use the standalone Build Deployment Manager to run Logistics checks, prepare
artifacts and deliver reviewed builds. Logistics owns its suites and release
policy; the manager owns execution and retained evidence.

Open the manager's platform launcher, add or select the trusted Logistics checkout,
then follow [validating and delivering Logistics](build-manager-journeys.md).
Adding a checkout authorizes its adapter; there is no separate trust step.
Start with local checks and no delivery destination while learning the workflow.

For a fresh GUI plan, Start authorizes its selected Firebase/TestFlight uploads
and GitHub actions to run after the required checks and preparation succeed.
Device installs still require review of the prepared package and recipient.
CLI and retained plans use their declared approval requirements. Inspect the
actual plan before starting; a passing test alone is not authorization.

The six legacy `mobile_build/deploy_*.command` shortcuts and their dedicated deployment window/sequencer have been retired. Device, signing and provider helpers remain in Logistics because the manager adapter uses them.

## Combined validation and delivery

The guided flow supports selecting several platforms together and choosing
GitHub, Firebase and TestFlight destinations independently. See
[combined validation and delivery](build-manager-journeys.md) for source
requirements, explicit approvals, local manager setup and validation scope.
Mobile tester and Release-device builds can capture uncommitted Logistics and
commonUtils files using **Current files**. They retain full release gates and exact
source fingerprints; GitHub source publication still requires a clean committed
checkout. Exclude the GitHub destination for a local mobile release.
Development-device installs are also available in combined journeys; the
[CLI Boox workflow](build-manager-journeys.md#cli-local-android-validation-and-boox-deployment)
shows local emulator validation followed by reviewed installation.

The local **Build** action on Android and iOS compiles a development artifact
without installing or delivering it. Turning testing off in a delivery workflow
skips checks while retaining the selected build and delivery steps.

## Settings and identity

Settings use a category menu on the left and retained forms on the right, sharing
`commonUtils.ui.settings.navigation.SettingsNavigation` with Logistics settings.
Hover a field or its label for its purpose; timing integers have bounded stepper
controls in seconds. The main plan's optional build number also has a stepper,
with **Automatic** representing no override.

Settings show each effective value's origin: repository defaults, ignored local
profile, environment or one-run override. Save changes the local profile;
changing the app version explicitly edits tracked `mobile_build/pyproject.toml`.
That tracked edit is separate from saving a local profile. A historical source selection reads its version from that selected commit,
not from the current checkout. Build numbers are separate from app version and release tags.

| Section | Supported fields |
| --- | --- |
| TestFlight | Guarded app/bundle ID; selected external group; enabled state; What to Test; locale; polling interval and processing timeout |
| Firebase | App ID (verified against the guarded package); tester group; release notes |
| Tools | Desktop/mobile interpreter, Xcode developer directory, Android SDK and JDK directories |
| Local targets | iPhone/Duo/iPad template selectors, disposable Android image/model, Linux/Fedora/Windows guest selectors, Linux distro scope/Fedora mode and shutdown preference; availability is validated before execution |
| Legacy reserved targets | `vm.shared_host` and `vm.shared_guest` are shown read-only for compatibility; `android.avd` remains editable to clear a legacy value, and must be empty. Local backends do not attach existing AVDs or mount shared folders |
| Authentication | Existing TestFlight credential JSON and `.p8` references, with Browse/Locate; GitHub repository, credential-helper strategy and token environment name; existing Firebase CLI account storage |
| Signing | Optional manual app, Inbox, widget and widget-action profile references; all extensions are required for manual signing. Leave all references empty for automatic signing with the pinned team |
| Versions | Read-only app version and next iOS/Android build previews; one-run explicit build override; intentional tracked app-version edit; explicit independent release tag |

The local profile is `mobile_build/.tools/build-manager/profile.json` (schema 1,
`values` mapping), overridable with `LOGISTICS_MANAGER_PROFILE`. Existing provider
JSON remains the tracked default. `LOGISTICS_TESTFLIGHT_GROUP`,
`LOGISTICS_FIREBASE_GROUP`, `ANDROID_HOME`, `JAVA_HOME` and `DEVELOPER_DIR` have
visible precedence. Existing `ASC_KEY_PATH`, `ASC_KEY_ID` and `ASC_ISSUER_ID`
override the protected authentication reference; secret values are never shown.
API authentication, signing and destination verification are separate checks.
Hosted workflows use their own repository secret/variable references; Mac-local
key paths are not synchronized, and stored secret values cannot be retrieved.

Connection verification performs read-only app/group/repository checks. It does
not upload, notify, install or dispatch workflows, and it does not claim workflow
write permission from repository read access. Missing configuration is reported.
Automatic build numbers are previewed without allocation and reserved under a
local lock at build start. Explicit values must increase and satisfy platform
limits. Other machines can reserve independently: local locking does not prove
global uniqueness, and provider verification remains authoritative.

Prepared reports capture actual verified embedded version/build, source,
signature identity and the selected destination at preparation. They are copied
into the run result; editing a profile later does not relabel those reports.
Rebuild for a changed identity, or use the existing explicit build-specific
provider retry/resume command after reviewing that immutable build.

## Reviewing and deleting local builds

Choose **Clean up builds…** in the manager. Filter by iOS/TestFlight,
Android/Firebase, reviewed build outputs, source snapshots or disposable scratch; select individual rows
or choose **Delete all unprotected…** for the displayed category. The confirmation
includes the exact paths. This manual action can remove even the newest local
artifacts; automatic retention still keeps its normal recent-build allowance.

The list covers only the existing retention owners. Native test build caches
inside owned source snapshots are removed with those snapshots. SDKs, toolchains,
physical-device deployment workspaces, personal VM/simulator state, credentials,
signing inputs, build counters and unclassified evidence are not cleanup targets.
Published releases are unaffected. A `.keep` anywhere in a tree or an active build
lease protects it. Deletion checks ownership, links, pins and locks again after
confirmation, reports skipped entries and refreshes the list. Listing and deleting
run off the UI thread; cleanup is unavailable while this manager runs an operation.

The generic UI consumes optional `storage_inventory()` and
`delete_storage(selections)` adapter methods. Logistics defines owned roots in
`logistics_build.build_retention`; reusable manual deletion and lease protection remain
in `build_manager.retention`. The settings navigation factory is optional for
other projects; field metadata supports section, label, description, kind and
integer minimum/maximum/suffix without importing Logistics into the generic UI.

## External manager installation (adapter API 1)

Generic execution, transports, profiles and retention mechanisms now belong to
`build-deployment-manager`. Logistics retains `logistics_build/build_project.py`, snapshots,
suite declarations, distribution helpers and storage policy. No sibling checkout
is discovered automatically. Install a reviewed Git checkout explicitly in each
interpreter used for Logistics tooling:

```sh
.venv/bin/python -m logistics_build.install_build_manager /path/to/build-deployment-manager
mobile_build/.venv/bin/python -m logistics_build.install_build_manager /path/to/build-deployment-manager
```

The manager requires adapter API 1. Missing/incompatible installations stop with a
setup error. Generic contracts run via `python -m build_manager.contracts` from
the installed manager checkout; project contracts remain here. Existing plans
and result schema 1 remain readable; results are never rewritten. Counters, keys,
profiles, snapshots and retention policy keep their existing locations.

Hosted runners and newly provisioned guests also need an explicit installation
of the reviewed manager revision. The extraction is local until that revision
is made available to those hosts; this task does not push or dispatch it.
Local source archives carry the installer and integration, not a stale second
copy of the engine. Re-run the explicit install after recreating an environment.

Hosted setup reads `build-manager-dependency.json` and explicitly installs that
immutable revision using `logistics_build/install_build_manager.py --from-pin DESTINATION`.
It refuses an existing destination rather than pulling or resetting it. The owner
must make both manager and commonUtils commits remotely available before hosted
setup can succeed. No publication of those commits was performed here.

## Registered workflows and fixed settings

The standalone manager registers the tracked `build-project.json` and invokes
`logistics_build/manager_bridge.py` in Logistics' own interpreter after explicit trust.
Named TestFlight/Firebase workflows prepare a signed artifact and pause for exact
artifact/destination review before reusing the existing distribution helpers.
`logistics_build/distribute_prepared.py` never rebuilds for upload. It records intent before
the provider request and refuses to repeat an interrupted attempt without
reconciliation. Passing tests never approves distribution automatically.

Shared GitHub account references can select an environment-name or the existing
Git credential helper; TestFlight can select an existing protected auth JSON.
Destinations, app identities and signing remain explicit project values. An explicit
missing environment reference does not fall back to another account. Firebase
continues to use its existing CLI authentication. No local credentials are copied
to hosted secrets. Each run retains effective values/origins and a private fixed
profile; later account/profile edits cannot redirect that plan's destination.

Native resource declarations bound mobile builds, SDK/cache mutation, signing and
device sessions. iOS devices depend on the prior device's cleanup even if a plan's
worker count increases. POSIX mobile helpers receive a bounded five-second cleanup
grace. The generic Android transport is portable, while Logistics' CPython Android
runtime compiler remains explicitly macOS ARM until its own toolchain is ported.
Native Linux/Windows acceptance and all existing VM holds remain separate.

App Store/Google Play publication are visible as Not implemented. Existing TestFlight
and Firebase functionality retain their own provider identity and review gates.

## Execution locations and inputs for one run

Guided validation offers an execution location beside each platform. Hosted checks
use a reviewed dispatch effect, independently of release publication; no release
tag is needed for checks. Committed source is required for GitHub. Native tester
delivery still requires the owning local validation receipts; a hosted check is
not substituted for those gates.

Project settings retains tool paths, signing/account references and reusable
recipient/note defaults. TestFlight “what to test” and group, and Firebase notes
and group are editable on the run configuration page. The adapter captures these
values in immutable per-run effective settings and review evidence, without writing
them back to the saved profile. Unknown overrides and credential material fail.

A blank GitHub release identifier uses the source project version from the selected
commit and the next available local alpha suffix. Mobile marketing versions and
build numbers remain independent. It creates no tag; publication checks remote availability again.
Custom identifiers remain available under Advanced options.

Cached source snapshots exclude only the known private mobile runtime references
through owned Git exclude metadata. These references are not source and cannot
enter transferred source archives. Snapshot reuse still checks source fingerprints
and rejects unrelated escaping links; linked Git metadata cannot be rewritten.
Native Cocoa verification covered short-window navigation, actual hosted plan
review, captured TestFlight notes, automatic naming and seven passing local checks.
No live dispatch, upload or publication formed part of that verification.

See the [adapter and validation guide](../development/build-manager.md) for developer contracts and platform acceptance.


## Android and iOS can progress independently

Selecting both platforms no longer makes one entire validation branch wait for
the other. Steps can overlap within the run's worker limit. Shared build tools,
workspaces, signing and SDK access still use declared resource locks: only steps
competing for those resources wait. Existing sequences within a platform remain,
including cleanup between successive iOS simulator tests.

A waiting platform card names the shared resource. Open the card and select its
subtask to inspect the resource capacity and other steps using the same resource.
A resource wait is different from a failed prerequisite; unrelated work continues.
After updating the manager and Logistics adapter, restart the app and inspect a
fresh plan. Previously inspected or saved plans preserve their original order.

## Reuse verified tests per preset

In the workflow's **Tests** settings, use **Reuse verified test results**:

- **On** (default): run identical host suites once and reuse verified exact matches.
- **Off · fresh executions (debug)**: execute selected tests afresh locally, in guests and in the hosted release. Neither local receipts nor previous GitHub passes can skip them.

Save the preset to keep that choice. Older presets default to On; loading another
preset does not inherit a previous preset's debug Off setting. The selected test
coverage, separate OS/native checks and rotation checks stay unchanged.
For an explicit CLI journey, the corresponding run choice is
`--run-value testing.reuse_verified_results=off`.

## Build without tests or delivery

In a manager checkout with the Build only goal, choose **Build only**, select
**iOS → This Mac** or **Android → the local host**, review the plan and choose
**Start build**. This produces the existing iOS simulator app or Android test APK.
It captures the selected source, retains its build report and stops before tests
or installation. Desktop Build is not implemented. Store/tester preparation
continues to use its existing project operation.
