# Blue Hole consumer maintenance

Blue Hole is a separate consumable Blender add-on. Its existing vendored
commonUtils copy, packaging, environment mapping and Perforce build design stay
intact. Logistics hosts configuration and launch workflows; Blue Hole owns add-on
operation policy. Shared APIs remain documented in commonUtils' root wiki.

## Ordered operation checks

`blenderUtils/filterUtils.py` keeps `check_tests` as the established entry point.
Its keyword switches still select lazy checks in this order: saved scene, scene
layout, selection, source-control enablement/connection, source content, Unity
Assets and Godot root. It exits at the first failed gate and shares one source-path
lookup across the two source-content checks. No filesystem mutation or server
submission is introduced.

Private diagnostic functions in the same module receive the operation title,
silent flag and relevant paths explicitly. They no longer obscure the gate flow
as nine nested closures. Popup flags and diagnostic text retain existing behavior;
in particular silent scene failures and silent missing-path failures have different
logging contracts. Exceptions raised by the configured diagnostic logger propagate.

The initial regression tests exposed an existing undefined variable in the
outside-source diagnostic. That repair is separate from the readability change:
the branch now reports its intended message instead of raising `NameError`.
Windows source membership remains case-insensitive; Unix comparisons retain their
previous case-sensitive lexical path policy.

## Validation scope

Eight preflight contracts run without Blender using the actual implementation and
substituted Blender/preference dependencies. An old/new comparison covers 1,078
profiles: every flag combination, silent modes and platform-specific failures.
Outcomes, dependency order, diagnostic bytes and popup flags match the corrected
baseline. All 41 Blue Hole adapter tests pass. No Perforce server is contacted.

Exact vendor membership and bytes are checked with the existing copy verifier.
The image encoding update additionally runs its eight public contracts against
the actual vendor copy. These host checks do not establish Blender 5.2.2 add-on
registration, operator UI or export behavior; those need the matching runtime.
