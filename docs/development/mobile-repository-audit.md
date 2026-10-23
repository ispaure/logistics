# Repository and mobile recovery audit — 2026-10-15

This is a historical snapshot before approval/commit of the local changes listed below.
The user subsequently authorized committing all pending files on 2026-10-15;
the artwork and documentation groups described here have now been committed
locally. The remote-ref and pending-file statements below describe the original
audit checkpoint, not the current working tree.
It is not a promise that future working trees or Apple account state remain the
same. Start with the [mobile handbook](mobile-handbook.md) for operating steps.
No files were staged, committed or pushed during this audit. No app was built,
installed or uploaded; focused automated checks used temporary fixtures/mocks.

## Source already on GitHub

Read-only checks against GitHub's current branch tips confirmed:

| Repository | Local branch / commit | GitHub result |
| --- | --- | --- |
| Logistics | `alpha` / `be3665c2eac7cd43874448a3d2027e52f2a9ea04` | Matches `origin/alpha` |
| Logistics | `main` and `beta` / `29715f92c76c75ebc7b88cfe0b09d317f302778d` | Both match their remote branches; earlier than alpha |
| commonUtils | `alpha` / `fd1df652774c6da76e6676c4a51f9e0e941022a3` | Matches remote alpha and Logistics' pinned submodule revision |
| commonUtils | `main` / `615a70d6ea4b75b5ed2d077d7542fa99d151991b` | Matches remote main |

commonUtils has no modified or untracked source files. No local branch commits
were absent from the repositories' cached remote refs; all local branch tips were
also checked against live GitHub heads. All 114 local Logistics tags and the one
local commonUtils tag exist remotely with matching object IDs. These checks did
not change branches or update dependency revisions.

Tracked mobile source, native bridge, build/deployment/TestFlight scripts,
workflow definitions and privacy resources are already in Logistics. The
exception is the pending icon change below. A fresh clone must include submodules
and select the intended branch; checking out `main` does not select alpha's work.

## Group A: mobile icons — approve together

The following code/artwork is local only and not backed up by a commit/push:

| Path | Status / purpose |
| --- | --- |
| `mobile_build/cloud_build.py` | Modified: imports the new helper and installs icons in generated projects |
| `mobile_build/build_support/icon_build.py` | Untracked: icon installation and optional artwork resizing |
| `mobile_build/resources/icons/ios/` | Untracked: iOS PNG artwork and asset catalog |
| `mobile_build/resources/icons/android/` | Untracked: Android PNG artwork and XML resources |
| `mobile_build/tests/test_icon_build.py` | Untracked: artwork/catalog and repeated-installation checks |

There are **67 artwork/resource files**: 60 PNGs, six XML files and one JSON
catalog. Including the build helper, test and changed build entry point, group A
contains **70 files**. Although their sizes are generated from supplied artwork,
these committed-ready resources are inputs to builds and belong in source control.
A fresh clone of today's pushed code still has its previous icon behavior; the
local `cloud_build.py` change must not be committed without its helper/assets.

## Group B: documentation — separate approval

These **eight files** include the existing icon documentation changes plus the
new handbook, navigation links, corrected historical release status and this audit:

- `README.md`
- `docs/development/mobile-launchers.md`
- `docs/user_mobile/user_mobile.md`
- `docs/development/development.md`
- `docs/development/mobile-preparation.md`
- `docs/development/mobile-testflight.md`
- `docs/development/mobile-handbook.md` (new)
- `docs/development/mobile-repository-audit.md` (new)

The existing icon documentation describes group A. If approving only documentation,
leave its icon-specific additions out until the corresponding code is approved.
Other handbook/status/navigation changes can be committed independently.
`Python/mobile/user_docs/index.md` remains the compatibility link.
The root README's optional Ally Tools sentence is preserved unchanged.

For individual review, `git diff` shows tracked modifications and
`git ls-files --others --exclude-standard` lists every new file, including each
artwork path. Approve selected paths or either complete group before staging,
committing and pushing; this audit itself grants no commit/push approval.

## Local items that should stay out of Git

The ignored-file inventory found generated build/payload/tool/environment files,
caches, logs/test evidence and private configuration/resources. Outside those
expected categories, the ignored-source candidate check found only the two known
mobile configuration JSON files below. It did not find an additional ignored
application source folder. The commonUtils ignored inventory contains cache/OS
files. No tracked non-test Python files larger than 100 bytes were exact content
duplicates; this is not a full assessment of overlapping implementations.

| Local item | Action |
| --- | --- |
| `mobile_build/.device.json` | Private backup: preserves device/team and established signing/Keychain baseline |
| `mobile_build/.testflight-auth.json` | Private backup: key reference; paths may need reconfiguration on another Mac |
| `mobile_build/.testflight-keys/` and any externally stored `.p8` | Encrypted private backup; never commit |
| Certificates/private keys in macOS Keychain | Private export/account recovery plan; not stored in this checkout |
| `mobile_build/build/testflight/` archives, IPA, debug symbols and release records | Separate release backup if historical artifacts are needed |
| `mobile_build/payload/`, other generated build projects, `.venv`, `.tools`, `.briefcase` | Rebuild/download using the handbook |
| `mobile_build/logs/`, `test-results/`, caches | Optional diagnostic backup, not source |
| Private software/resources/configuration and external feature link | Keep separate; not public mobile source or a Logistics Git backup |

Private key contents were not printed. The audit did not inspect Apple account
agreements, validate exported signing-key backups, read GitHub secret values, or
confirm that any private backup already exists. Source sync therefore does not
establish complete disaster recovery. The handbook explains these boundaries.

## Documentation and checks completed

The handbook covers terminology, source/build ownership, cloning alpha with the
pinned submodule, fresh-Mac tools, simulator/Xcode steps, paired-device builds,
TestFlight archive/export/upload/distribution recovery, Android debug builds,
troubleshooting and private backup requirements. Commands were compared with the
repository helpers and workflows, with primary Apple/BeeWare guidance linked.
The repository does not currently supply Google Play release/upload automation.

The retained record for build `202610145` says `status=assigned` and
`review_submitted=true`; older statements that assignment/upload were still
unverified were corrected. This is historical local evidence, not a live Apple
review result. A `202610146` release archive record also exists locally; its
presence alone is not evidence that it uploaded.

All **33 focused tests** passed for icons, device deployment, SDK selection,
TestFlight release/distribution safeguards and privacy manifests. Whitespace and
local documentation links were checked. A fresh native build, fresh-Mac setup,
physical-device run and actual upload were not performed for this documentation
audit, and remain separate validation activities.
