# Readability and maintainability implementation status

Updated October 23, 2026. The original assessment covered eight shared-library,
ten Logistics and five cross-cutting priorities. Their host-implementable stages
are complete. **C7's native factory extraction remains gated on native acceptance**;
its lifecycle contract stage is complete. This page is the current status, not a
claim that every future maintainability opportunity has been exhausted.

The [assessment snapshot](history/assessment-20261023.md) retains the original
source revisions, measurements, proposals and test scope. The
[sequential implementation record](history/audit-implementation-20261023.md)
records each checked unit, including caught errors and validation limits; the
[history index](history/history.md) retains earlier work.

## Verified implementation status

| Item | Completed change | Local commit |
| --- | --- | --- |
| T1 | Deterministic lint scope | `75395cc0` |
| T2 | Shared matrix, specialist owner selections and GUI-thread fixture cycle retirement | `75395cc0`, `0b08ebb8`; shared `ac1ae89` |
| C1 | Index target/validation/retirement phases; transaction remains centralized | shared `17978f2` |
| C2 | Indexing owns network/watch policy; shared close/idle admission | shared `9ac9121` |
| C3 | Captured dock transfer/rollback and separate header reconciliation | shared `e8ac643` |
| C4 | Named block classification, code/image typography and authored-source conversion phases | shared `c542e92` |
| C5 | Per-field control construction/binding and row/reset/preview assembly | shared `e37da37` |
| C6 | Named INI validation/location/replacement and rename stem/context stages | shared `d1ba7cd` |
| C7 (contract stage) | Paired install/retirement and late-callback contracts; native factories unchanged and platform-gated | shared `016a35d` |
| C8 | Explicit checkout admission/actions; hook and declined-prompt contracts; legacy exports retained | shared `9aaf84d` |
| L1 | Managed-text host workflows grouped over existing store/workspace/view owners; aggregate lifecycle stays in app | `380ab06e` |
| L2 | Retained drawer/listing owner separated from frame layout; import compatibility preserved | `c2d4cc55` |
| L3 | Explicit unpublished-control adoption/retirement; verified failed-build cleanup; named library page preparation/projection | `76a920c3` |
| L4 | Detached copy descriptors, browser construction and retained source-tab/tree projection | `0e5e9699` |
| L5 | Named mobile control/workspace assembly and recycled rows; desktop timer/signal binding and tree projection | `4d0a3820` |
| L6 | Captured IDE opens/recovery; Git snapshot projection; desktop source resolution and guarded action publication | `970ece5d`, `f50eb862`, `aa64a0bb` |
| L7 | Cloud controls/views separated from credential publication; named encrypted push and collection staging/verification | `f44a57fd`, `17ead7d7` |
| L8 | Named editor command groups, retained settings projection and Bulk Rename action/plan-row presentation | `f5e573c0`, `cf96c413`, `8c20e92e` |
| L9 | Named add-on resolution, managed destination admission, verified ZIP staging and page projection; one rollback owner | `39a6407d` |
| L10 | Reviewed smaller owners; named Hue validation-before-I/O boundary; cohesive backends and legacy APIs retained | `89c10808` |
| T3 | 81 reviewed portable modules, recursive package policy, fresh-owner import blockers and static CI regressions | `7631484c` |
| T4 | Reviewed duplicate imports and compatibility exports; F811 now enforced; F401/F841 remain deliberate owner-review diagnostics | `fc2aacb7` |
| T5 | Current status separated from dated assessments/chronology; native timing evidence consolidated | This documentation unit |

Each unit was checked before its local commit. Source-preserving extractions use
ordered syntax-tree comparisons plus the owning regressions; tests added for real
ownership/rollback gaps also run against original source where applicable.
A passing host suite does not certify native widgets, Blender or live services.

## Remaining acceptance gate

C7's native adapter factories remain unchanged. Before moving them, exercise the
relevant Android/iOS install/dispose/reinstall paths on a supported native runtime:
reader chrome, pinch/scroll/menu callbacks, rendering-canvas retirement, queued
speech completions, background/resume and repeated window closure. Dummy/fake
bridge cases establish contracts but cannot prove native peer/delegate lifetimes.
No connected Android device or booted iOS simulator was available for this pass;
no temporary apps were installed. Keep the main Logistics app and its data.

Existing platform/service acceptance for Blender activation, FUSE drivers, real
remote/collection operations and desktop integrations remains separate from this
readability pass. See [platform checks](../platform-checks.md) and owner guides.
Optional F401/F841 diagnostics remain owner-review aids; T4 completes the reviewed
F811 gate and compatibility-export decision, not a repository-wide unused-code sweep.

## Find the current contract

| Area | Guide |
| --- | --- |
| Shared mechanisms and APIs | [commonUtils integration boundary](../commonutils-integration.md); shared APIs stay in commonUtils' own wiki |
| Mobile host, documents, startup and shutdown | [Mobile owner map and lifecycle contracts](../mobile-runtime.md) |
| Desktop folders and generic services | [Browser ownership](../browser-ownership.md), [host services](../services.md) |
| IDE and Git | [IDE owners](../../features/ide/development/development.md), [Git owners](../../features/git/development/development.md) |
| Chat | [LM owners](../../features/lm/development/development.md) |
| Cloud/collection operations | [rclone owners](../../features/rclone/development/development.md) |
| Editors, settings and rename | [Text Editor](../../features/text_editor/development/development.md), [Bulk Rename](../../features/bulk_rename/development/development.md), [settings contracts](../configuration-and-data.md) |
| Add-on installation | [Blender preparation/publication](../../features/blender/development/development.md#apply-preparation-and-publication) |
| Lint, regression selection and import safety | [Testing](../testing.md), [portable owner policy](../architecture.md#portable-owner-policy) |

## External consumer and Git boundary

Ally Tools and Blue Hole are compatibility consumers. Change them only when an
actual shared migration requires import, signature, binding or resource references;
unrelated readability work and unsolicited vendor refreshes are excluded. This
sequential pass required no changes to either repository. Work stays on the current
development branches. Commits are local; do not push.
