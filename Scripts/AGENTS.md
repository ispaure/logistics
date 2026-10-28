# Machine script preservation

Keep the existing `.bat` filenames and paths in this directory. Other machines
invoke them directly. The user explicitly authorized Python tooling to move to
its proper owner; build and release adapters now live in `logistics_build/`.
Contributor inspection/setup tools may remain here. Do not keep duplicate build
implementations or forwarding Python scripts merely to preserve old paths.

Keep substantive tooling documentation in the root `docs/` wiki. Generated
Python/tool caches are disposable; script sources and configuration are not.
