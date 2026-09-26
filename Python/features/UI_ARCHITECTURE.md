# Feature UI Ownership

Feature-specific UI belongs to the feature that owns the behavior.

Typical structure:

```text
features/<feature>/
├── backend modules
├── ui_contributions.py
└── ui/
    ├── page.py
    └── dialogs.py
```

The generic `ui_new` package owns only application-level presentation:

- Main window / tab host.
- Generic Folders page.
- Generic Servers page.
- Generic Debug page.
- Generic workflow dispatch.
- Shared UI primitives that are not feature-specific.

## Workflows

A feature registers a `WorkflowContribution` with a stable workflow ID and a
lazy handler. The handler imports the feature-owned dialog only when the user
invokes the workflow.

This prevents unrelated feature UI modules from being imported together.

## Standalone pages

A feature registers a `PageContribution` containing a lazy `create_page`
factory. The main window does not know which feature owns the page or where
its implementation lives.

## Debug

The Debug page only renders `DebugActionContribution` objects from the feature
registry. If a Debug action references a workflow, the generic workflow
dispatcher resolves the corresponding feature-contributed workflow.

The Debug page never imports feature implementations directly.
