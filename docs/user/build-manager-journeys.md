# Validating and delivering Logistics

Use the build manager to review validation, tester delivery and device installation.
For setup and saved settings, see the [build manager user guide](../development/build-manager.md).

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

## Shared builds and device variants

The manager overview reads left to right under Source, Testing and Delivery.
Delivery includes build and export/signing cards as well as destinations. The
project descriptor declares package dependencies; the overview displays each
shared package once. Review and execution show the actual project phases.

Device delivery defaults to Debug. Choose Release in the device destination to
reuse the tester build: Android copies the exact signed Firebase Release APK;
iOS exports a separately provisioned device app from the same Release archive
used for TestFlight. An iOS Release device-only run omits the TestFlight export
and upload. Debug and Release remain separate builds, and simulator validation
remains distinct from physical-device packaging.

Release devices require committed source, full native/runtime release gates and
the existing tester build/signing configuration. iOS device exports use already
available signing assets and validate every selected UDID, including extension
profiles; they do not register devices or enable provisioning updates. All
installs still require review of exact bytes and recipients. Signing/version
conflicts stop the install without clearing data or changing identity.

GitHub publication, Firebase, TestFlight and Release device packages require
committed source. Debug device delivery and local validation can capture current
files. Latest commit excludes local edits without committing them; GitHub
publication additionally requires the current checkout to be clean and to match
the selected commit. Requirements appear in the overview before preparation.

Portable contracts cover sharing, stage dependencies, checksums and mocked
export/install commands. They do not establish successful native signing,
TestFlight processing, Firebase distribution or personal-device installation.
