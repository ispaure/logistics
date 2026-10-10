# Architecture cleanup implementation

The twelve candidates in ARCHITECTURE_REUSE_REPORT.md were implemented in their
suggested order, with review and regression checks before each numbered commit.
The assessment remains a dated snapshot; current contracts live in
Python/features/UI_ARCHITECTURE.md and commonUtils' UI/development guides.

| Item | Implementation | Focused validation |
| --- | --- | --- |
| 1 | Public close outcomes and reader-owned readiness | 70 lifecycle regressions plus standalone contract tests |
| 2 | Shared atomic byte writer used by three editor paths | 53 persistence/editor tests; Markdown failure-injection tests updated to shared writer |
| 3 | Outline entries and list/tree presentation for headings, chapters, bookmarks | 59 navigation/reader tests plus opaque-target outline checks |
| 4 | Notification service, history/deduplication, toast and native delivery | 40 shell/process/archive tests plus acknowledgement checks |
| 5 | Shared worker result contract for Operation, EPUB and Git | 33 Git and 43 worker/reader/archive tests |
| 6 | Reader appearance controls and screen-bounded popup placement | 27 reader/pagination/presentation checks; Qt fixture appearance isolation |
| 7 | Shared Unicode-safe cursor wrapping with explicit policies | 58 code/Markdown regressions including single-step undo |
| 8 | Shared entry selection and typed sorting | 44 filesystem/archive regressions; models and capabilities remain separate |
| 9 | Shared JSON publication below owner-specific schemas | 40 state/history/recovery regressions |
| 10 | All public feature packages expose unified declarations | 64 registry/settings/action/source regressions |
| 11 | Git job orchestration and EPUB bookmark modules | 33 Git and 38 reader/document regressions |
| 12 | Reconciled canonical architecture and component guides | Documentation links and full release validation |

No root README expansion was made. External feature documentation stays with its
owner. Package reorganization follows these twelve commits as a separate phase.
