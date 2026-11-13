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
Keep user workflows under `user/` and technical contracts under `development/`
in Logistics, Build Deployment Manager and commonUtils. commonUtils API references
use `development/reference/`; Logistics retains its feature and mobile branches.
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
features and never traverses the external emulation repository. The mirror
excludes every `mobile-evidence/` directory under `docs/`, including
feature wikis, while preserving the local files. The Settings
entry opens `docs/user_mobile/user_mobile.md` with the Logistics tree. Feature links stay inside the same mirrored wiki, so users can read every
feature guide offline without changing the sidebar scope. Links within the
Logistics wiki use that packaged tree. Checkout-relative links to source files
or the separate commonUtils wiki require those files in a source checkout;
they are not included in this documentation mirror. Shared API documentation
remains in commonUtils rather than being copied into the mobile help payload.

## Writing for a first-time reader

Give each page a clear audience and purpose. A task guide should state what the
reader needs, where to run commands, what to do, what success looks like and how
to recover from likely failures. Define project terms before using them. Keep
short learning examples separate from exhaustive API and validation reference;
link to the owning contract instead of copying it.

Use concrete subjects and verbs, and prefer a disposable worked example over a
list of internal module names without context. Keep current behavior, supported commands and concise validation scope in the wiki.
Use Git history for superseded plans, dated audits and implementation logs. This
approach follows [Diátaxis](https://www.diataxis.fr/start-here/),
[Write the Docs](https://www.writethedocs.org/guide/writing/beginners-guide-to-docs/)
and [Google's clear-sentence guidance](https://developers.google.com/tech-writing/one/clear-sentences).

## Validation

Run the existing layout check from the repository root:

```sh
python3 dev.py test desktop test_documentation_layout.py
```

It checks H1s, landing-page ownership, parent-child links, migrated Markdown links
and the repository boundary. Its source is `Python/tests/tooling/test_documentation_layout.py`.
Desktop Settings and shared wiki tests cover guide entry points and scope changes;
mobile documentation tests cover offline rendering and scope/history navigation.
Native appearance still requires device validation.
