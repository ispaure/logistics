# Developing Logistics

Logistics owns application workflows and their presentation. commonUtils supplies
reusable filesystem, format, configuration and UI machinery. Start with the
user guide for the workflow you are changing, then follow this map.

| Task | Guide |
| --- | --- |
| Understand startup, windows, workers and cleanup | [Architecture](architecture.md) |
| Locate a feature, dependencies or enable/disable behavior | [Feature organization](features.md) |
| Add settings, a page, folder integration or a document launcher | [Extension points](extension-points.md) |
| Register a format, preview, action or activation | [Browser extensions](file-browser.md) |
| Decide whether behavior belongs in Logistics or commonUtils | [Shared ownership](commonutils-integration.md) |
| Change paths, stored state or configuration | [Configuration and data](configuration-and-data.md) |
| Set up, test and contribute | [Development and validation](testing.md) |
| Understand the optional external feature host boundary | [Optional integration](optional-integration.md) |
| Review documentation findings and unresolved concerns | [Documentation audit](documentation-audit.md) |

Feature implementation details remain in `Python/features/<feature>/README.md`.
Canonical user guides live beside their owners under `user_docs/README.md`;
[the root feature catalog](../../README.md#what-can-it-do) links them all, and
[the application user guide](../../USER_GUIDE.md) explains how to open them in
Settings. Core browser and Markdown hosting live in `Python/ui_new`, and bulk rename keeps its existing
package there. Do not create duplicate feature packages to document them.

## Documentation maintenance

Update feature user guides when behavior, defaults, persistence, dependencies or
recovery change. Update developer guides for contracts and ownership changes;
update the root README for setup or major capability changes. New features need
both a usable guide and the small `user_docs/index.md` compatibility entry for
in-app help. Keep compatibility entry pages as links, not copies of whole manuals.

Check statements against implementation and relevant tests. Mark historical
assessments as historical; do not treat proposals as implemented behavior.
Keep shared component documentation in commonUtils and project-specific external
feature documentation in its owning repository. No generated documentation
framework is needed.
