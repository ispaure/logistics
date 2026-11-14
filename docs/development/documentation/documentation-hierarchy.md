# Documentation ownership and hierarchy

Start at [the Logistics wiki](../../docs.md). Systemic guides live under
`docs/user/`, `docs/user_mobile/` and `docs/development/`. Feature guides use
the corresponding folders under `docs/features/<owner>/`, including
`bulk_rename`. Give source-local README and `user_docs/index.md` files short
links to their owning guides. Shared APIs belong in commonUtils' wiki.
Optional external features keep their internals in their own repositories.

## Pages and scopes

Every folder has a same-named landing and links to all its immediate children.
Every page starts with an H1 after optional YAML. The viewer uses the H1 as
the sidebar title. Desktop feature and general Help use
`services.documentation` with the Logistics wiki root. The shared viewer
handles scope switching and history.

## Mobile packaging

`mobile_build/tools.py` mirrors the root wiki into `mobile/help/`.
Settings opens `docs/user_mobile/user_mobile.md`. Relative wiki links stay
in the bundled tree. Links to source and the commonUtils wiki require a checkout.
The mirror excludes `mobile-evidence/`. Keep raw evidence outside the wiki and
linked feature sources outside the payload. See
[local artifacts](../testing/validation-artifacts.md).

## Writing for a first-time reader

Start with a visible action, its code owner, an exact focused command and the
expected result. Include prerequisites, compatibility limits and recovery where
they affect that task. Link to the owning contract for details used elsewhere.
Keep dated audits, plans and implementation logs in Git history.

## Validation

From the repository root run:

```sh
python3 dev.py test desktop test_documentation_layout.py
```

Check the [desktop viewer and packaged mobile Help](documentation-viewer-verification.md)
when changing the tree, links or entry points.
