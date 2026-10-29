# Your first Logistics contribution

This guide takes you from a checkout to a focused, locally verified change.
You need basic Python and Git knowledge. Start with desktop or portable behavior;
you do not need mobile SDKs, a provider account or a personal device for this loop.

## 1. Prepare your environment

Clone with the pinned shared library included:

```sh
git clone --recurse-submodules https://github.com/ispaure/logistics.git
cd logistics
python3 dev.py setup desktop --dry-run
python3 dev.py setup desktop
python3 dev.py doctor
```

On Windows use `py` in place of `python3`. The setup preview prints its intended
command; setup then installs the locked desktop environment at root `.venv`.
Doctor reads interpreter, package, submodule and optional-tool status without
changing the environment or reading credentials. A missing optional native tool
can keep doctor nonzero even when a portable change is ready to test; read the
specific diagnostic. See [setup details](testing.md#set-up-a-checkout).

For an existing checkout, keep your current branch and preserve local edits.
Initialize missing submodules only after checking for changes inside them.
Use the consumer's pinned `Python/commonUtils`, never another checkout found
elsewhere on your computer.

## 2. Try the behavior before editing it

Open the platform launcher from the [README](../../README.md#get-started).
For a harmless first exploration, use File Browser on a disposable folder with a
text file. Open the file in a reader/editor, switch to Documents and return to it.
This introduces the separation between folder browsing and retained document tabs.
Use copied fixtures when exploring rename, delete, transfer or encryption actions.

Read the matching [user guide](../user/user.md) and feature guide so you know the
intended result before tracing callbacks. Missing remote accounts do not prevent
ordinary local browsing.

## 3. Find one owner and its tests

Use the [code map](code-map.md) to choose an owner. For example, a feature's
`__init__.py` declares its capabilities; its `ui/` package implements desktop
presentation, and portable modules hold behavior reusable by mobile. The desktop
shell composes those features rather than owning all their logic.

A useful existing example is [LM attachments](testing.md#worked-contribution-desktop-lm-attachments):
registration → page → controller → portable file policy → regression tests.
You can follow this path without an API key; endpoint tests use synthetic fixtures.
Read [architecture](architecture.md) before moving behavior across owners.

The three repositories have distinct jobs:

| Repository | Change here when… |
| --- | --- |
| Logistics | The change concerns app navigation, features, document policy, project builds or release rules |
| commonUtils | The change is a reusable mechanism or shared component contract; update its own docs and affected consumer tests |
| Build Deployment Manager | The change concerns generic plan execution, review, scheduling, transports or retention mechanics |

A shared-library edit is a separate repository change, even though its files are
under `Python/commonUtils`. It does not update another consumer's pin.

## 4. Make a small change and check it

Start with an existing test file for the behavior. Inspect the command before
running it if you are unsure which interpreter it uses:

```sh
python3 dev.py test desktop test_feature_registry.py --dry-run
python3 dev.py test desktop test_feature_registry.py
python3 dev.py architecture
python3 dev.py lint
```

The regression runner executes each selected file in a fresh process with isolated
storage. A passing command exits zero; no matching files is an error. Replace the
example filename with the tests for your change. [Test selection](testing.md#find-the-tests-for-your-change)
explains desktop, mobile-host and shared-library owners.

Portable/offscreen checks verify logic and lifecycle, not native appearance or
actual provider/device behavior. A mobile presentation change also needs its
[own native validation](mobile-handbook.md). Do not weaken a native gate because
its SDK, host or device is unavailable; report the unverified scope.

To add coverage rather than only run existing tests, follow
[adding and diagnosing tests](adding-tests.md) for a complete example, fixture
choices and the configuration files required at each step.

## 5. Update the guide a reader needs

Describe visible behavior in the feature's `user/` or `user_mobile/` guide and
contracts in its `development/` guide. Cross-cutting docs stay in the corresponding
root audience branch. Include prerequisites, a short sequence, expected results
and recovery for likely failures. Keep shared API reference in commonUtils.

Check your diff for unrelated edits and generated/private files. Raw test evidence
belongs under ignored `test-results/`, not the wiki. Documentation layout is checked
with `python3 dev.py test desktop test_documentation_layout.py`. Follow the
[documentation hierarchy](documentation-hierarchy.md) for new pages. Commit or
publish only when that work is authorized.

[Developer index](development.md) · [Full development and validation reference](testing.md)
