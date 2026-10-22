# Documentation ownership and hierarchy

The [Logistics wiki](../docs.md) contains systemic desktop usage, mobile usage
and development guides. [Feature infrastructure](feature-infrastructure.md)
explains feature ownership; each feature keeps its own `docs/` wiki. Common UI
and Workspaces help belong to Logistics; Bulk Rename remains under `desktop`.
Shared commonUtils API guides and optional external feature internals stay in
their own repositories. Compatibility entries contain links rather than copied guides.
Historical migration reports do not override these current ownership rules.

Screenshots, recordings and raw test results stay in ignored local artifact
directories, outside the documentation wiki. See [local validation artifacts](validation-artifacts.md)
for locations and packaging rules. Public guides must not link to local-only files.

## Pages and scopes

Each wiki starts at `docs/docs.md`. Audience branches use `user/user.md`,
`development/development.md`, and `user_mobile/user_mobile.md` when applicable.
Every nested folder has a same-named landing, and its parent links to it.
Every Markdown file starts with an H1, following optional YAML frontmatter.
The H1 supplies the visible navigation title. Parent pages explicitly mention
all immediate children in context or Further reading.

Desktop help entry points use `services.documentation`: feature Settings opens
the feature guide with its feature docs directory; browser and general help use
the root Logistics docs directory. Legacy external help remains supported.
The shared viewer updates the sidebar when a link enters another wiki scope,
including when returning through history. Rendering and navigation contracts are
maintained in commonUtils rather than duplicated here.

## Mobile packaging

`mobile_build/tools.py` copies root and owned feature wiki Markdown into
`mobile/help/`, preserving repository-relative paths. It excludes linked
features and never traverses the external emulation repository. The Settings
entry opens `docs/user_mobile/user_mobile.md` with the Logistics tree. Cross-wiki
links resolve within the mirrored payload, so users can read the scoped feature
guides offline. Source files mentioned by developer pages are not included in
this documentation mirror.

## Validation

Run `Python/tests/test_documentation_layout.py` for H1s, landing-page ownership,
parent-child links, migrated Markdown links and the repository boundary.
Desktop Settings and shared wiki tests cover guide entry points and scope changes;
mobile documentation tests cover offline rendering and scope/history navigation.
Native appearance still requires device validation.
