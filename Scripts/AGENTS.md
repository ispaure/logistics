# Root scripts preservation

Keep this root `Scripts/` directory and its existing script names and paths.
Some computers invoke these files directly, including the machine-specific
Windows launch and synchronization scripts. Absence of an in-repository caller
does not establish that a script is unused. Do not delete, relocate or rename
them during cleanup unless the user explicitly authorizes that particular change.

Keep substantive tooling documentation in the root `docs/` wiki. Generated
Python/tool caches are disposable; script sources and configuration are not.
