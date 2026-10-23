# Logistics TestFlight workflow

For first-time setup and step-by-step operating instructions, start with the
[mobile handbook](mobile-handbook.md). This page is the detailed release reference.

The release entry point is `mobile_build/deployment/testflight_tools.py`. A manual GitHub workflow
in `.github/workflows/testflight.yml` invokes the same commands after the existing
iOS native UI and CPython runtime workflows pass. Upload is disabled by default.
Explicit uploads now invoke `testflight_external.py` to distribute the resulting
build to the configured external group after Apple processing. This operates on
existing testers and beta groups; App Store publication remains a separate workflow.

## Identity and prerequisites

Use the existing bundle ID **`io.github.ispaure.logisticsmobile`** when registering
the identifier and creating the App Store Connect app record. Keep the existing
application identifier prefix and Keychain access. On the configured Mac,
`mobile_build/.device.json` supplies that baseline. The helper refuses a different
team, bundle ID, application identifier or effective Keychain groups. If the
approved membership exposes another team ID, resolve that mapping before
uploading; do not bypass the check by changing identity or uninstalling the app.
No release command installs anything on the paired iPhone.

Enrollment was confirmed approved by the owner on 2026-10-14. Account refresh,
App Store Connect configuration and distribution signing are separate steps:

1. Refresh Xcode's Apple Account and confirm the existing team is available for
   paid-program signing. Accept any pending agreements in Apple's account UI.
2. Create the App Store Connect iOS app record using the existing bundle ID;
   complete its required metadata, privacy information and beta-test information.
3. Make Apple Distribution signing available. Local commands can use the signed-in
   Xcode account with automatic signing. CI uses an exported distribution
   certificate with its private key and a matching **App Store** provisioning profile.
4. Complete the encryption questions accurately. Logistics includes Go-based
   AES encryption for credential storage and LocalCrypt, in addition to HTTPS;
   this workflow deliberately does not declare `ITSAppUsesNonExemptEncryption=false`.
   Use Apple's [beta export-compliance guide](https://developer.apple.com/help/app-store-connect/test-a-beta-version/provide-export-compliance-information-for-beta-builds)
   to determine the required declaration/documents. This is not an exemption assessment.
5. Commit the intended mobile sources and required commonUtils changes. Signed
   release staging rejects dirty/uncommitted mobile sources. Pick a unique,
   increasing positive build number (at most nine digits) for every uploaded build.

Apple describes [distribution preparation](https://developer.apple.com/documentation/xcode/preparing-your-app-for-distribution)
and [build upload requirements](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/).
Check that the selected Xcode/SDK is currently accepted for App Store Connect
before the first upload. The local selector requires SDK 27.1 or newer.

## Double-click launcher

`mobile_build/deploy_ios_testflight.command` uses the existing local environment and
`testflight_deploy.py` to run plan, archive and export in order. It chooses a build
number above existing local release workspaces, then asks for an explicit `y`
before invoking upload with the existing opt-in flag. Failed steps stop the flow;
an empty answer keeps the verified export. All identity, clean-source, signature
and distribution checks remain owned by `testflight_tools.py`. An explicit build
number can be supplied with `--build-number`. Processing and beta review still
happen through Apple after upload.

## Local commands

Use the persistent Python 3.12/Briefcase 0.4.5 environment prepared for device
deployment and Go 1.26.9. For example, from the repository root:

```sh
export PATH="$PWD/mobile_build/.tools/go/bin:$PATH"
mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_tools plan --build-number 202610132
mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_tools archive --build-number 202610132
mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_tools export --build-number 202610132
# After reviewing the verified IPA and choosing to upload:
TESTFLIGHT_UPLOAD=1 mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_tools upload --build-number 202610132
```

`plan` prints the pinned identity, version, build number and export options without
building or contacting Apple. `archive` generates a new curated payload and
Briefcase project under `mobile_build/build/testflight/<number>`, builds both native
bridge variants, restores the normal app launcher and creates a Release arm64
`.xcarchive`. It does not rewrite the physical-device project or `.device.json`.
Existing release workspaces are preserved; choose another build number after
an incomplete attempt. Build numbers are written only into the isolated plist;
Xcode's automatic upload renumbering is disabled.

`export` uses `app-store-connect` with `destination=export`, creates the IPA,
and verifies the distribution profile, recursive signature, non-debuggable
entitlements, app identity, Keychain groups, normal launcher and build number.
It records archive/IPA fingerprints. `upload` requires a successful export,
unchanged fingerprints and explicit `TESTFLIGHT_UPLOAD=1`; it uploads the archive
through Xcode with `destination=upload`. With external distribution enabled, API
authentication and the destination group are verified before uploading; after a
successful upload the helper waits for processing and distributes that exact
iOS app/version/build to the group. Apple beta review can still be pending.

Optional API authentication uses `ASC_KEY_PATH`, `ASC_KEY_ID` and `ASC_ISSUER_ID`
together. Keep the `.p8` outside tracked sources; never paste it into a command
or commit it. When these variables are absent, the commands use the saved local
API key reference if configured, otherwise Xcode's signed-in account. A partial
environment override is rejected. This also avoids depending on Xcode's login
session once API setup is complete. External group automation requires API
authentication; see the configuration below.
`--profile /path/to/distribution.mobileprovision` selects manual signing for
archiving; install the matching certificate/private key and profile first.

## Automatic distribution to Friends

### Python/OpenSSL privacy manifests

`privacy_build.py` supplies the OpenSSL declaration published by the Python Apple
Support provider in commit `c012e5d4309b3a6767bcc5787f9cd57cfbcd48e9`
([upstream fix](https://github.com/beeware/Python-Apple-support/pull/285)). The exact
file and source fingerprint are retained in `mobile_build/privacy/`. This is a targeted
packaging fix for the pinned Python 3.12 support package b10, whose OpenSSL-backed
`_hashlib` and `_ssl` modules lack their provider privacy manifests.

The helper installs the module manifests in the device and simulator standard-library
folders before compilation. It requires the support package's existing framework
conversion script to embed each manifest as `PrivacyInfo.xcprivacy` before framework
signing; it does not modify a signed artifact. Existing different declarations are
rejected for review rather than overwritten. Release archive and exported IPA
inspection verify both frameworks contain the provider declaration, alongside
recursive signature and identity checks. This declares the provider's OpenSSL
behavior, not the app's full privacy answers or an encryption exemption.

### API setup and distribution

`mobile_build/testflight-distribution.json` enables external distribution to the existing
**Friends** group for App Store Connect app `6822787800`. The helper verifies the
app's bundle ID and requires one exact external group name match. It never creates
a group or enables a public link. Set `enabled` to `false` for an upload that should
remain unassigned. Direct `deploy_ios.command` installs are separate and do not
upload or distribute a TestFlight build.

One-time local setup:

1. In App Store Connect, open **Users and Access → Integrations → App Store Connect
   API**. Create a **team API key** with **App Manager** access for beta distribution.
   Download the `.p8` and keep it outside tracked sources. Note its Key ID and
   Issuer ID. This credential is separate from Xcode's Apple Account login.
2. Install host-side authentication support and save the key reference locally:

   ```sh
   mobile_build/.venv/bin/python -m pip install -r mobile_build/requirements-testflight.txt
   mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_external configure \
     --key-path /absolute/private/path/AuthKey_KEYID.p8 \
     --key-id YOUR_KEY_ID --issuer-id YOUR_ISSUER_ID
   mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_external check
   ```

   The key reference is saved in ignored `mobile_build/.testflight-auth.json` with mode
   `0600`; the configuration command itself does not copy key content. On the
   configured Mac, the downloaded key is retained in ignored
   `mobile_build/.testflight-keys/` (directory `0700`, key `0600`) and the reference
   points there so clearing Downloads does not break uploads. CI instead uses the existing
   `ASC_KEY_PATH`, `ASC_KEY_ID`, and `ASC_ISSUER_ID` variables installed by the
   signing helper. Environment values take precedence over local references.
   The saved local reference also supplies Xcode's authentication arguments for
   archive/export/upload, without exposing private-key contents in commands.
3. Complete the beta app description, feedback email, review contact and encryption
   information in App Store Connect. The automation preserves those owner values.

Every explicit upload now checks API access before contacting Xcode for upload.
After success it writes `upload-result.json`, waits up to 30 minutes for the
specific iOS version/build, preserves existing per-build testing notes (or supplies
the configured defaults), enables `autoNotifyEnabled`, submits beta review only
from `READY_FOR_BETA_SUBMISSION`, and adds the build to Friends without removing
earlier builds. Pending or approved reviews are not resubmitted. The helper verifies
group membership and records `external-distribution.json`; it does not wait for
Apple's human beta review to finish.

Missing encryption information, rejected/expired/internal-only builds, API errors
and processing timeouts stop with an actionable error. There is no guessed encryption
exemption, private session-cookie authentication, or implicit retry of a failed
upload. Once the issue is resolved, retry distribution for the existing upload:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_tools distribute --build-number 202610144
```

This command does not rebuild or re-upload. It finds the exact app/version/build
from the retained `release.json` and can resume partially completed distribution.
Testers still choose automatic installation in the TestFlight app on their devices.
Automatic tester notification is separate from automatic device installation.

API contracts were checked against Apple's public OpenAPI specification and
[beta review API](https://developer.apple.com/documentation/appstoreconnectapi/post-v1-betaappreviewsubmissions),
[group build association API](https://developer.apple.com/documentation/appstoreconnectapi/post-v1-betagroups-_id_-relationships-builds),
and [JWT authentication guidance](https://developer.apple.com/documentation/appstoreconnectapi/generating-tokens-for-api-requests).
Mocked integration tests cover exact build filters, bounded processing waits,
app/group identity, review states, retries, notifications and membership verification;
an ephemeral real P-256 key verifies JWT signing. On 2026-10-14 the owner configured
a team API key and the authenticated `check` confirmed the correct app and existing
Friends external group. The first live distribution attempt correctly stopped
because Apple's processing marked build `202610144` as `INVALID`. Apple's notice
identified missing privacy manifests in the bundled `_hashlib` and `_ssl`
frameworks (ITMS-91061). Upload transport succeeded, but that build is unavailable
for testing until packaging is corrected and a new build is uploaded. Group
assignment and beta-review submission remain unverified against a valid live build.
Replacement build `202610145` includes the provider manifests, passed archive and
IPA signature/manifest verification, and uploaded successfully using the configured
API key on 2026-10-14. During the 2026-10-15 repository audit, its retained
`external-distribution.json` recorded `status=assigned` and `review_submitted=true`.
This confirms the recorded group assignment and review submission, not Apple's
current approval status. Check App Store Connect for live processing/review state.

An unsigned packaging check is available while enrollment is pending:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_tools archive --build-number 202610133 --unsigned-check
```

It allows dirty local sources and ad-hoc signing of Python framework modules
only to exercise packaging. Its archive cannot be exported or uploaded.

## GitHub configuration after approval

Commit/push the workflow when ready. GitHub exposes manual workflow dispatch
after the workflow exists on the default branch. Create a `testflight` environment
and configure its reviewer/branch protection preferences for release access.
The following variables and secrets belong to that environment:

| Kind | Name | Value |
| --- | --- | --- |
| Variable | `IOS_TEAM_ID` | Approved existing development team ID |
| Variable | `IOS_APP_IDENTIFIER` | Exact existing prefix plus `.io.github.ispaure.logisticsmobile` |
| Variable | `ASC_KEY_ID` | App Store Connect team API key ID |
| Variable | `ASC_ISSUER_ID` | API key issuer ID |
| Secret | `IOS_DISTRIBUTION_P12_BASE64` | Base64 Apple Distribution certificate **and private key** export |
| Secret | `IOS_DISTRIBUTION_P12_PASSWORD` | Password protecting that export |
| Secret | `IOS_APP_STORE_PROFILE_BASE64` | Base64 App Store provisioning profile for the existing identifier |
| Secret | `ASC_PRIVATE_KEY` | Complete `.p8` private key contents |

Use an App Store Connect team API key with the roles/access required for the
upload. Do not use a Personal Team profile, an ad-hoc profile or another bundle's
profile. Distribution profile checks run before signing assets are used.
`testflight_signing.py` installs assets into a temporary runner keychain,
preserves its previous keychain search list, and removes the temporary keychain,
profile and API key in an always-run cleanup step. Only IPA, release metadata,
export options and logs become artifacts; signing secrets are excluded.

Run **Logistics TestFlight preparation** manually with a new build number and
leave **upload** off for the first signed rehearsal. Inspect the resulting IPA
and logs. A subsequent run with upload enabled also reruns validation and
produces a new build; choose another increasing build number.

## Beta information prepared for App Store Connect

The following copy describes the current mobile prototype. Review it against the
exact committed build before entering it in App Store Connect. Apple's
[test-information guide](https://developer.apple.com/help/app-store-connect/test-a-beta-version/provide-test-information/)
describes the beta description and feedback email fields.

### Beta app description

Logistics Mobile brings text documents, Markdown, books and comics into a native
workspace for iPhone and iPad. Create and edit private documents, preview Markdown,
read EPUB books and CBZ/ZIP comics, and keep bookmarks and reading progress.

Browse local files and configured rclone storage, keep encrypted LocalCrypt copies
for offline use, and review changes before pushing managed folders. Connect to
your own compatible language-model server for text conversations.

This early beta focuses on document recovery, file operations, reading and native
navigation. Imported ordinary documents are private copies; export a copy to use
changes elsewhere. Optional server and remote-storage features require your own
configuration. No Logistics account is required for local document use.

### What to test

1. Create a text or Markdown document, edit it, switch destinations, then reopen
   it. Check Find, Replace, Preview, Save and draft recovery after relaunch.
2. Import a disposable document through the available picker and export a copy.
   Confirm encoding, line endings and content. Check cancellation and unavailable
   provider permissions on a physical device.
3. Import an EPUB or CBZ/ZIP comic. Change chapters/pages, add a bookmark, close
   and reopen it, and check reading position and appearance.
4. Browse Files in list and tile views. Try search, sorting, folder navigation,
   file details and operations on disposable files.
5. If you already use rclone or LocalCrypt, import a test credential package,
   download a test file and check locking, password retry and offline reopening.
   Exercise Pull and reviewed Push only against a disposable remote folder.
6. If you have a compatible LM server, configure its URL/model, send a short
   message, cancel a streamed response and export the conversation.
7. On iPad, create a second window in Settings and check separate ordinary
   document drafts, rotation, keyboard layout and duplicate-writer prevention.

Report the device model, OS version, build number, steps, expected result and
actual result through TestFlight feedback. Exclude passwords, keys and private
document contents from reports.

### Beta review notes

Local document creation, editing and Markdown preview do not require a login.
Start at Home, choose New document, enter text and save. Open Documents to
revisit it, or use Preview from a Markdown editor. The app has no Logistics
account registration screen.

Books and comics require a user-supplied EPUB or CBZ/ZIP. Remote storage,
LocalCrypt and LM chat require user-supplied configuration and are optional.
Before requesting external beta review, provide a disposable sample book/comic
and, if Apple needs to review connection features, reachable test services with
review-only credentials through App Store Connect. Never supply personal keys.

### Fields that still require the owner's values

| Field | Preparation status |
| --- | --- |
| App name / platform | Logistics Mobile / iOS |
| Bundle ID | `io.github.ispaure.logisticsmobile` |
| Version | `0.1.7` in `mobile_build/pyproject.toml`; confirm against the selected archive |
| Primary language and SKU | Choose when creating the app record; a proposed internal SKU is `logistics-mobile-ios` |
| Feedback email | Owner must choose a monitored address |
| Beta review contact | Owner must supply name, email and phone |
| Privacy policy URL | Owner must supply a published policy URL |
| Privacy and age-rating answers | Review the exact bundled app, configured services and dependencies before submitting |
| Encryption answers | Complete Apple's questionnaire for bundled encryption; do not infer an exemption from HTTPS use |
| Tester groups | Choose initial internal testers; prepare external review separately |

The code keeps ordinary documents, preferences and chat history in app-private
storage. Chat sends messages to the explicitly configured server; rclone connects
to configured storage providers. iOS saved credential keys use the device Keychain
and encrypted credential files are excluded from backup. These source observations
help prepare a privacy policy; they do not establish App Store privacy answers for
all dependencies or third-party services. Review the packaged privacy manifests,
required-reason APIs and app icon during signed distribution validation.

## Verification boundary

On 2026-10-13, a local unsigned Release archive packaged successfully with SDK
27.1 and the normal Logistics launcher. Export of that local archive was rejected
as intended. Focused unit tests cover pinned identity, profile type/expiry,
effective default Keychain access, build-number validation and export defaults.
On 2026-10-14, a fresh unsigned Release archive of the shared working tree packaged
successfully as version `0.1.5`, build `202610143`, using Xcode 27.1. The native Go
bridge tests passed. The archive is retained under `mobile_build/build/testflight/202610143`
with its `release.json`, curated source fingerprint and build logs. It records
dirty source and cannot be exported or uploaded. Attempts `202610141` and
`202610142` stopped at sandbox cache access and remain as diagnostic workspaces.
This rehearsal includes ongoing local mobile changes and is separate from the
frozen [alpha audit](mobile-alpha-verification.md).

The release tests additionally cover rejected profile Keychain groups and verify
that uploading cannot run without a reviewed export, explicit opt-in and unchanged
archive/IPA fingerprints. Profile identity checks run before signing assets are
installed. A local keychain check found two Apple Development identities and no
Apple Distribution identity. Enrollment approval is confirmed, but distribution
signing/export and upload were unverified at that earlier preparation checkpoint.
The later build `202610145` records above supersede that historical limit. New
mobile changes must still be committed before signed release staging. This
documentation audit did not install or upload an app.
