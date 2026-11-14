# Logistics TestFlight workflow

Use TestFlight in the standalone [manager](../../user/build-manager.md). It runs source-bound native/runtime gates, archives and verifies the IPA, then pauses for artifact and destination review. The local and GitHub workflows use the same deployment helpers. Upload defaults off.

## Identity and prerequisites

Keep `io.github.ispaure.logisticsmobile`, the existing team, application identifier prefix and effective Keychain groups. `mobile_build/.device.json` supplies the local baseline. Refresh Xcode account access and accept pending agreements. Use an Apple Distribution identity and matching App Store profiles. Complete App Store Connect metadata and encryption answers for the selected artifact. The app uses HTTPS and Go AES for credentials and LocalCrypt. See [Apple beta export compliance](https://developer.apple.com/help/app-store-connect/test-a-beta-version/provide-export-compliance-information-for-beta-builds).

Use a unique increasing positive build number up to nine digits. Local manager plans can capture current Logistics/commonUtils files with matching validation. GitHub uses committed source. Check App Store Connect's accepted Xcode and SDK before uploading.

## Local commands

From the repository root, activate the mobile environment and expose the tools as in the [handbook](mobile-handbook.md#set-up-a-mac). Set `MOBILE_RELEASE_NUMBER` to an unused value:

```sh
python -m mobile_build.deployment.testflight_tools plan --build-number "$MOBILE_RELEASE_NUMBER"
python -m mobile_build.deployment.testflight_tools archive --build-number "$MOBILE_RELEASE_NUMBER"
python -m mobile_build.deployment.testflight_tools export --build-number "$MOBILE_RELEASE_NUMBER"
# After reviewing the verified IPA and destination:
TESTFLIGHT_UPLOAD=1 python -m mobile_build.deployment.testflight_tools upload --build-number "$MOBILE_RELEASE_NUMBER"
```

`plan` inspects locally. `archive` creates isolated `mobile_build/build/testflight/<number>/`; use a new number for a new archive. `export` verifies recursive signatures, profile, launcher, entitlements, identity and version, and records archive/IPA hashes. Upload requires those unchanged hashes. `archive --unsigned-check` exercises packaging without producing an exportable archive.

### App and Inbox profiles must match

Enable `group.io.github.ispaure.logisticsmobile` on the app and Inbox extension under the existing team. Refresh both profiles. Manual signing requires that App Group on every included extension profile. If automatic export lacks certificate permission, use the existing distribution identity and one profile per target:

```sh
python -m mobile_build.deployment.testflight_deploy --prepare-only \
  --profile /private/App.mobileprovision \
  --inbox-profile /private/Inbox.mobileprovision \
  --widget-profile /private/Widgets.mobileprovision \
  --widget-actions-profile /private/WidgetActions.mobileprovision
```

For optional Watch targets supply both `--watch-profile` and `--watch-widget-profile`. Keep profiles private.

## Automatic distribution to Friends

`mobile_build/testflight-distribution.json` selects the existing app and exact external **Friends** group. Set `enabled: false` for an unassigned upload. Distribution waits for the exact processed version/build, preserves existing test notes, enables notifications, verifies additive membership and submits review when ready. A competing review can leave confirmed membership with `blocked_by_existing_review`. Check the selected build in App Store Connect for actual tester availability. Historical build `202610145` reached Friends with review submitted.

### Python/OpenSSL privacy manifests

`privacy_build.py` installs the pinned [Python Apple Support declaration](https://github.com/beeware/Python-Apple-support/pull/285) in `_hashlib` and `_ssl` before signing. Archive and IPA inspection require both declarations. An ITMS-91061 rejection needs a corrected build with a new number.

### API setup and distribution

Create a team App Store Connect API key with App Manager access. Back up the `.p8` privately. From the root with the mobile environment:

```sh
python -m pip install -r mobile_build/requirements-testflight.txt
python -m mobile_build.deployment.testflight_external configure \
  --key-path /absolute/private/AuthKey_KEYID.p8 --key-id KEY_ID --issuer-id ISSUER_ID
python -m mobile_build.deployment.testflight_external check
```

The ignored `.testflight-auth.json` stores a reference with mode `0600`. A complete `ASC_KEY_PATH`, `ASC_KEY_ID`, `ASC_ISSUER_ID` override takes precedence. External distribution checks access before upload. Processing/metadata delays are bounded. For compliance, review or processing recovery, resolve the issue and resume the uploaded build:

```sh
python -m mobile_build.deployment.testflight_tools distribute --build-number "$MOBILE_RELEASE_NUMBER"
```

For a retained build add `--workspace /absolute/path/to/build/testflight/NUMBER`. It must match the uploaded app/team/build. Check `upload-result.json` and `external-distribution.json`; reconcile ambiguous upload attempts against Apple before further writes. `distribute` resumes group/review work on the existing upload.

## GitHub configuration after approval

Expose the manual workflow from the default branch. Configure the protected `testflight` environment:

| Kind | Values |
| --- | --- |
| Variables | `IOS_TEAM_ID`, `IOS_APP_IDENTIFIER`, `ASC_KEY_ID`, `ASC_ISSUER_ID` |
| Secrets | `IOS_DISTRIBUTION_P12_BASE64`, `IOS_DISTRIBUTION_P12_PASSWORD`, `IOS_APP_STORE_PROFILE_BASE64`, `ASC_PRIVATE_KEY` |

Use the existing identifier and the certificate export containing its private key. The checked-in workflow passes only the main app profile. Before running hosted signed preparation with the current extension targets, configure and pass their protected profiles too. Use the local manager workflow with matching target profiles in the meantime. The signing helper installs credentials temporarily and cleans up after the run. Run **Logistics TestFlight preparation** with upload off for the signed rehearsal. Review IPA and logs. A later upload run validates and builds with a fresh number. See [the workflow](../../../.github/workflows/testflight.yml) for current signing inputs.

## Beta information prepared for App Store Connect

**Description:** Edit private text and Markdown, read EPUB and comics, browse local or configured remote storage and recover drafts in a native iPhone/iPad workspace. Optional LocalCrypt and chat use your configured storage and server.

**What to test:** Create, save, import and export disposable documents. Check draft recovery, reading position, Files navigation, iPad windows and duplicate-writer prevention. Use test folders and servers for pull/push and chat. Report device, OS, build, steps and observed result through TestFlight without private content.

**Review notes:** Start at Home → New document, save, reopen from Documents and preview Markdown. Local work requires no account. Supply sample books/comics and review-only credentials for any remote features reviewers need. Owner fields include feedback email, review contact, privacy URL, age rating, privacy and encryption answers.

### Notes Library data-view disclosure and review demonstration

Include this disclosure in Beta App Review and App Review notes. Generate and attach the synthetic sample, or provide a reviewer-accessible download link. Choose a fresh output filename:

```sh
python3 -m mobile_build.validation.dataview_review --output test-results/app-review/dataview-review.zip
```

> Notes Library supports limited Dataview-compatible JavaScript. Complete `dataviewjs` blocks run automatically in reading mode, and `dv.view` can execute a library-local script. There is no separate trust prompt. The disposable WebView worker blocks network access and exposes bounded in-library reads. It has no general native or file-write API. The app offers no script marketplace or native executable downloads. Imported or synced local libraries can contain scripts. The app displays generated output alongside the original editable source.
>
> Launch once. In Files, extract the sample under **On My iPhone/iPad → Logisticks** and keep its `.obsidian` folder. Enable Notes Library in Settings if needed, then open Documents → Notes Library → Refresh libraries → Data view review. In `Home.md`, expect “Inline script complete”, “Review pencils” quantity 7 and “Reusable view complete”. Inspect `views/inventory.js`, change quantity to 9 in `data/items.json`, and reopen the note. Expect quantity 9 with the original Markdown script intact. `Blocked read.md` shows the rejected out-of-library read. Settings → About → Open-source licenses retains the upstream MIT acknowledgement.

Confirm these steps on the exact signed build. Supply the sample or a review-accessible demonstration through Apple. The prepared notes and host checks provide local evidence; submit the disclosure with the chosen build.
