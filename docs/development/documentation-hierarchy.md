# Documentation ownership and hierarchy

The [Logistics wiki](../docs.md) contains systemic desktop, mobile and developer
guides plus feature-owned sections under `docs/features/<owner>/`. Source code
stays with its feature; documentation stays in this root wiki so the Markdown
viewer exposes one complete sidebar. Bulk Rename uses `docs/features/bulk_rename/`.
Shared APIs live in commonUtils' own root wiki. Optional external feature internals
stay in their separate repositories. Source-local README and user_docs entries
remain short compatibility links rather than duplicate guides.

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
the feature guide with the root Logistics docs directory; browser and general help use
the root Logistics docs directory. Legacy external help remains supported.
The shared viewer updates the sidebar when a link enters another wiki scope,
including when returning through history. Rendering and navigation contracts are
maintained in commonUtils rather than duplicated here.

## Mobile packaging

`mobile_build/tools.py` copies the single root wiki into
`mobile/help/`, preserving repository-relative paths. It excludes linked
features and never traverses the external emulation repository. The Settings
entry opens `docs/user_mobile/user_mobile.md` with the Logistics tree. Feature links stay inside the same mirrored wiki, so users can read every
feature guide offline without changing the sidebar scope. Source files mentioned by developer pages are not included in
this documentation mirror.

## Validation

Run `Python/tests/test_documentation_layout.py` for H1s, landing-page ownership,
parent-child links, migrated Markdown links and the repository boundary.
Desktop Settings and shared wiki tests cover guide entry points and scope changes;
mobile documentation tests cover offline rendering and scope/history navigation.
Native appearance still requires device validation.
