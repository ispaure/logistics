# Publishing a release

The [Source release workflow](.github/workflows/release.yml) builds a source ZIP
on GitHub when a `v*` tag is pushed. Normal branch pushes do not trigger it.
The ZIP has one `Logistics/` folder, with the tagged project's tracked files and
all recursively checked-out public submodules at the commits recorded by that tag.
Existing launchers, dependencies and installation steps stay unchanged.

Maintainers: commit and push submodule changes first, then commit and push the
updated submodule reference, project changes and release workflow. Tag that
published commit to create a release with automatic notes:

```sh
git tag v1.0.0
git push origin v1.0.0
```

Only pushed `v*` tags publish releases. Running **Source release** manually in
Actions builds a downloadable `release-zip` test artifact without publishing.
Packaging uses tracked files, excludes Git metadata and development caches, and
preserves script permissions. Existing releases can receive a missing
`release.zip`; an existing asset is never overwritten. Existing notes and draft
state are preserved, so a draft left by a failed publish may need manual
publication after a successful retry. Use a new version tag for corrected assets.


## Before the first release

1. Review and commit the intended commonUtils changes, then push them to its repository.
2. In Logistics, commit the updated submodule reference, intended application
   changes, release workflow, packaging tools and documentation.
3. Push that Logistics commit and make sure it is the commit you intend to tag.
4. Run the tag commands above, then check **Actions → Source release**.
5. Open the release and confirm that **release.zip** is attached.

The workflow uses GitHub's built-in token. Only the publishing job has
`contents: write`; packaging has read access. Manual runs never publish a release,
even when a tag is selected. Workflow concurrency serializes runs for the same ref.

The packaging tool validates pinned submodule checkouts and archive integrity.
It excludes Git metadata, workflow files, virtual environments, caches and build
outputs. It preserves executable permissions for macOS/Linux launchers. Local
credentials, optional software and other untracked/ignored files are not bundled.

Local validation covers packaging layout, submodule contents and publishing
failure cases. A hosted run must succeed before claiming GitHub execution is tested.

## Testing the package locally

This is optional; users and maintainers do not need to generate ZIPs locally.
From a checkout with initialized submodules, run:

```sh
python .github/scripts/package_release.py --output /tmp/logistics-release/release.zip
python -m unittest discover -s .github/scripts -p 'test_*.py' -v
```

A local dry run reads tracked working-tree files, so it may contain your unstaged
edits. New untracked application files are omitted. CI uses the clean tagged
checkout. Generated ZIPs belong outside the checkout and are never committed.
