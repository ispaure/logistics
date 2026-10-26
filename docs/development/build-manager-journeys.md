# Combined validation and delivery

Logistics now declares the manager's journey schema 1 in `build-project.json`.
The standalone manager and the plan panel in the existing deployment window use
`Scripts.manager_journeys` through `LogisticsProject.make_journey`. The isolated
`Scripts.manager_bridge.py` exposes the same `journey_plan` action.

## Use the guided flow

Restart the manager to load the changed code. In the standalone manager, select
Logistics and use Project → Review and trust adapter when prompted: changing the
descriptor intentionally invalidates its previous trust. The code does not grant
itself trust or change registrations.

1. Choose Validate, then select any supported combination of macOS, Linux,
   Windows, iOS and Android. This runs complete project suites with no hosted
   dispatch, release, tester upload or physical-device installation.
2. For delivery, choose Validate and deliver and select destinations independently:
   GitHub source release, Firebase Android testers and/or TestFlight iOS testers.
   Firebase requires Android; TestFlight requires iOS. The GitHub source release
   requires all three desktop platforms before the existing full hosted gates.
3. Choose the source under Advanced options. Working-tree validation follows
   existing snapshot policy, including refusing uncommitted commonUtils edits.
   Delivery requires committed source. GitHub publication additionally requires
   the current clean checkout at that exact commit and an explicit unused channel
   tag such as `v1.2.3-alpha.1`. Existing edits are never committed or discarded
   by planning. Use a committed revision for validation when that is your intent.
4. Check readiness and review plan. Inspect exact source, native hosts, required
   gates, recipient app/group identities, release tag and the dependency board.
5. Start validation and preparation only when ready. Each destination waits for its own declared platforms:
   Firebase waits for Android, TestFlight for iOS, and GitHub for the three desktop
   platforms. A failed unrelated platform does not block successful delivery branches.
   Native/runtime evidence and owned cleanup remain required; iOS delivery also
   requires the complete iPhone, Duo and iPad inventory. Linux delivery from the
   configured Mac VM backend requires both declared distributions.
6. When preparation finishes, Review and continue delivery presents retained
   artifact evidence. Select each ready action to approve. Eligible GitHub,
   Firebase and TestFlight branches can overlap within the declared resource
   limits. Declining keeps the prepared run; successful preparation is reused
   only after checksum verification. Unknown external outcomes require provider
   reconciliation and are never blindly repeated.

The GitHub branch uses the existing publication policy: it publishes shared and
application source/channel/tag, waits for hosted release gates, and verifies the
source ZIP. This is a separate artifact from the locally prepared tester packages;
those packages are not silently attached to the GitHub release.

Physical-device installs remain in the existing device deployment tab. Its
commands discover devices and build/install together; they are not misrepresented
as artifact-only effects in this reviewed tester workflow. Combined planning never
scans, reconnects, installs on or otherwise touches personal devices.

## Source, settings and resource integrity

Capture source identity, app version and effective settings once in an immutable
internal PlanningContext. Every platform/preparation branch consumes this context,
with unique step IDs, captured settings profiles and explicit dependencies. Snapshot
creation checks its identity against the capture before writing, and final source/
settings verification refuses changes made during preparation. Plans are combined
under this shared context, not by assuming independently captured sources match.

Existing workspace operation locks, snapshot holds, resource requirements and
project retention remain authoritative. Mobile validation branches run in sequence
so their disposable device lifecycles do not overlap. An always-run admission step
lets later platform validation proceed after an earlier platform fails, without making one platform’s success a validation prerequisite for the other.
The admission step uses a completion-only scheduling edge. Artifact review follows
only success-required dependencies, so an unrelated failure cannot veto delivery. Owned cleanup is scoped to its
branch so it cannot wait forever on delivery steps that depend on it.

Credentials remain protected references or inherited environment variables.
Profiles and plans never contain private-key/token contents. Changing a credential
file reference in Settings requires a location outside Git checkouts; existing
references are preserved while editing unrelated values, without copying or moving
credential files. Runtime executable paths are not credential files.

## Local manager dependency and verification

This integration needs the manager with journey schema 1 and explicit host
backend mappings. The current local project environment uses the existing editable
manager installation. Its published manager pin is not advanced to an unpublished
revision, and `build-manager-dependency.json` is preserved. For another environment,
install the reviewed local manager explicitly or advance the project pin only after
an authorized publication. Do not silently substitute a different checkout or pin.

Portable acceptance uses the real project adapter and JSON bridge, temporary
local repositories, mocked native/provider entry points and harmless subprocesses.
It covers shared capture, complete release gates, source changes, cleanup order,
partial failure, approval pause/resume, retained preparation, and overlapping
independent uploads. No native VM/device checks, signing/build acceptance, hosted
dispatch, uploads or publication were run for this integration. Prior native
acceptance does not certify the new combined journey. Native acceptance remains
separate, explicitly authorized work at exact source/artifact identities.

- [Build manager](build-manager.md)
- [Developer home](development.md)

## Shared tests and suite discovery

The project-owned `build-tests.json` is resolved by the headless manager
`build_manager.test_manifest` API against the selected source snapshot.
Desktop validation and full mobile host gates run the pinned
`Python/commonUtils/tests` suite first; project tests depend on its success.
Mobile tooling, desktop UI and mobile host tests may run together after that
shared gate, before native acceptance. A shared failure blocks those consumers.
Focused advanced suites intentionally run only their requested scope and cannot
stand in for complete release acceptance. CI/local desktop checks consume the
same desktop inventory. Native/runtime acceptance remains project-owned.

Suites use stable IDs, `test_*.py` files (existing isolated runner also supports
`test*.py`), explicit `after` prerequisites and named interpreter environments.
Dependency suites must name an in-checkout Git submodule owner at its pinned
commit; no sibling checkout or dependency installation is inferred.
The manager wiki’s test-manifest contract documents the complete schema.
New checkouts must contain this manifest in the source revision selected for a
run; old revisions that predate it must use their matching adapter version.

## Tester messages and development devices

Delivery configuration offers one per-run tester message for Firebase and
TestFlight. The adapter maps it to each service’s existing notes field. Leaving
it untouched preserves different saved defaults; editing it applies the same
text to both selected tester services. Recipient groups remain service-specific.
These overrides are captured for review and do not update saved settings.

Development-device delivery is now integrated under Delivery → Dev devices.
Choose explicit Android devices or iPhone/iPad UDIDs from saved metadata, or enter
an already connected paired ID. Reload only reads `.tools/test-devices.json` and
`.device.json`; it performs no discovery, connection or device mutation. No target
is selected by default. The project captures IDs, labels and connection mappings
in a hash-bound preparation recipe. Per-device review names the actual recipient.

`Scripts.manager_devices` builds from the same isolated captured source as the
validation branch, prepares an APK or zipped development-signed iOS app, then
requires manager approval of the exact retained report and package before each
installation. The iOS development profile must already cover all selected UDIDs;
preparation never registers devices or updates provisioning automatically.
Android preparation disables wireless discovery and device version queries.
Installation validates exact bytes and recipient identity, updates in place and
never uninstalls, clears storage, downgrades or re-signs on failure. Build/version
or signing conflicts stop the target with an error. Installing does not launch or
force-stop the app. Offline targets never cause another device to be substituted.

Each installation records an attempt before its first mutating command and a
receipt after confirmed success. Interrupted/uncertain outcomes require explicit
reconciliation before retry; other successful recipients remain recorded. Owned
build workspaces and the existing device deployment lock prevent competing writers.
Runtime credential/signing inputs remain protected references outside source.
Device-only runs may use captured current files; selecting tester services or
GitHub retains committed-source/release-acceptance policy. Device preparation and
local native validation currently require the configured Mac environment.

Portable coverage uses mocked ADB/Xcode commands and harmless process graphs.
No physical device was queried, installed, launched or otherwise changed, and no
native signing/build or provider acceptance was performed for this implementation.
