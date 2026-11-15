# Documentation ownership and writing

## Preserve the reader's journey

The [wiki home](../../docs.md) introduces three paths: using desktop, using mobile
and developing Logistics. Each path should let a newcomer do one small useful
thing before asking them to understand advanced settings or implementation
details. Readers who already know the basics can use task tables and references
to jump directly to their work.

For developers, the progression is: run a checkout, understand the application's
main parts, choose a change, find its owner, and validate it. A screen-to-code map
is useful at the owner lookup step; it does not replace an introduction to how
the application works.

## Give each page a purpose

| Page purpose | What the reader should get |
| --- | --- |
| Introduction or landing | What this area does, the concepts needed to enter it, and an explained route to each child guide |
| First-use walkthrough | Prerequisites, a small complete task, expected results and the next useful step |
| Task guide | A specific goal, the choices that affect its result, steps, limits and recovery |
| Explanation | How the parts fit together and why a boundary or contract exists |
| Reference | Precise controls, owners, options, contracts or troubleshooting facts that readers can look up |

Keep a page focused on its purpose. Put low-level ownership tables in references,
build procedures in Build and Release, and detailed feature behavior in the
feature's own guide. Explain why a linked page is useful instead of ending with
an unlabelled list of related facts. A landing may be short, but it should orient
the reader before offering links.

## Choose the owning guide

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

## Make instructions concrete

Start a user guide with the visible action and the choices that affect its
result. Include prerequisites, limits and recovery where they affect the task.
Give shared workflows one detailed home and link to it from feature guides.

Introduce a developer guide's responsibility and the relevant data or control
flow before giving a change example. In that example, connect a visible action
to its code owner and a focused check with an expected result. Explain why those
pieces belong together. Keep specialized contracts available as references
without making them prerequisites for a first run.

Describe implemented behavior and verify consequential claims against source or
tests. Distinguish a runnable host check from native or hardware acceptance.
Avoid adding benchmark history, dated audits or implementation logs to ordinary
guides; Git history and ignored test evidence retain that detail. Review the
surrounding section when adding a fact so it belongs in the explanation.

## Validation

From the repository root run:

```sh
python3 dev.py test desktop test_documentation_layout.py
```

Check the [desktop viewer and packaged mobile Help](documentation-viewer-verification.md)
when changing the tree, links or entry points.
