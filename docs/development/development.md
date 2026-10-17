# Developing Logistics

Logistics owns application workflows and their presentation. commonUtils supplies
reusable filesystem, format, configuration and UI machinery. Start with the
user guide for the workflow you are changing, then follow this map.

## Start here

1. [Set up and validate a checkout](testing.md).
2. [Find the code owner, entry point and tests](code-map.md).
3. Read [architecture](architecture.md) for host/lifecycle contracts and
   [feature organization](features.md) before adding a feature.

For planned cleanup, see the [restructuring assessment](restructuring.md), which
separates the current layout from proposed migrations.

## Specialist guides

| Task | Guide |
| --- | --- |
| Set up mobile development without prior iOS/Android experience | [Build and release handbook](mobile-handbook.md) |
| Develop the project IDE | [IDE architecture](../../Python/features/ide/docs/development/ide.md) |
| Develop the LM chat client | [LM integration](../../Python/features/lm/docs/development/lm.md) |
| Review tab, docking and compact layout changes | [UI refinement validation](ui-refinement.md) |
| Understand startup, windows, workers and cleanup | [Architecture](architecture.md) |
| Locate a feature, dependencies or enable/disable behavior | [Feature organization](features.md) |
| Add settings, a page, folder integration or a document launcher | [Extension points](extension-points.md) |
| Register a format, preview, action or activation | [Browser extensions](file-browser.md) |
| Decide whether behavior belongs in Logistics or commonUtils | [Shared ownership](commonutils-integration.md) |
| Develop PDF readers and vertical page navigation | [PDF Reader](../../Python/features/pdf/docs/development/development.md) |
| Develop encrypted local copies and private readers | [LocalCrypt](../../Python/features/rclone/docs/development/localcrypt.md) |
| Develop read-only remote browser tabs and direct readers | [Remote browsing](../../Python/features/rclone/docs/development/remote-browsing.md) |
| Consolidate desktop/mobile rclone behavior and ownership | [rclone parity plan](../../Python/features/rclone/docs/development/rclone-parity.md) |
| Change paths, stored state or configuration | [Configuration and data](configuration-and-data.md) |
| Prepare the document core for mobile runtimes | [Mobile preparation](mobile-preparation.md) |
| Review the three-pass alpha audit and its local verification scope | [Alpha verification](mobile-alpha-verification.md) |
| Review the local mobile presentation changes and actual screen evidence | [Mobile UI refresh](mobile-ui-refresh.md) |
| Develop mobile file/conversation drawers and paired document panes | [Workspace navigation](mobile-workspace-navigation.md) |
| Assess Books/Comics desktop and mobile gaps and reader-first delivery | [Books and Comics parity](../../Python/features/books/docs/development/books-comics-parity.md) |
| Plan mobile reader ownership, feature organization and reusable native UI cleanup | [Mobile architecture roadmap](mobile-architecture-roadmap.md) |
| Assess existing Qt browser/editor/reader reuse on iOS | [PySide6 iOS proof](mobile-qt-proof.md) |
| Build, sign and deploy to a paired iPhone or iPad over Wi-Fi | [Local device deployment](mobile-device-deployment.md) |
| Prepare an identity-preserving TestFlight archive and upload | [TestFlight workflow](mobile-testflight.md) |
| Plan native mobile navigation and open documents across Apple and Android | [Mobile navigation plan](mobile-navigation-plan.md) |
| Inspect native mobile foundation evidence and remaining device limits | [Native navigation proof](mobile-navigation-proof.md) |
| Set up, test and contribute | [Development and validation](testing.md) |
| Understand the optional external feature host boundary | [Optional integration](optional-integration.md) |
| Review documentation findings and unresolved concerns | [Documentation audit](documentation-audit.md) |

Feature implementation details live in `Python/features/<feature>/docs/development/`.
Canonical user guides live beside their owners under `docs/user/user.md`;
[the root feature catalog](../../README.md#what-can-it-do) links them all, and
[the application user guide](../user/user.md) explains how to open them in
Settings. Core browser and Markdown hosting live in `Python/ui_new`, and bulk rename keeps its existing
package there. Do not create duplicate feature packages to document them.

## Documentation maintenance

Update feature user guides when behavior, defaults, persistence, dependencies or
recovery change. Update developer guides for contracts and ownership changes;
update the root README for setup or major capability changes. New features need
a `docs/docs.md` wiki, desktop/mobile user guides where supported, and a small
`user_docs/index.md` compatibility entry for
in-app help. Keep compatibility entry pages as links, not copies of whole manuals.

Check statements against implementation and relevant tests. Mark historical
assessments as historical; do not treat proposals as implemented behavior.
Keep shared component documentation in commonUtils and project-specific external
feature documentation in its owning repository. No generated documentation
framework is needed.

## Further reading

- [File browser development](browser-ownership.md)
- [Feature and application infrastructure ownership](feature-infrastructure.md)
- [Developing Logistics](getting-started.md)
- [Maintenance priorities](maintenance.md)
- [Logistics mobile prototype](mobile-launchers.md)
- [Repository and mobile recovery audit — 2026-10-15](mobile-repository-audit.md)
- [Mobile host code](mobile-runtime.md)
- [Cross-platform archive checks](platform-checks.md)
- [PySide6 iOS reuse proof](qt-proof-launchers.md)
- [Publishing a release](releasing.md)
- [Logistics host services](services.md)
- [Feature UI ownership](ui-architecture.md)

## Related pages

- [Documentation ownership and hierarchy](documentation-hierarchy.md)

- [Mobile verification evidence](mobile-evidence/mobile-evidence.md)

- [Documentation viewer verification](documentation-viewer-verification.md)
