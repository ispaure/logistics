# Publishing a release

[Source release](../../../.github/workflows/release.yml) publishes on pushed `v*` tags. A manual run exercises packaging without publishing. Push commonUtils first, then the Logistics commit containing its pin and reviewed release notes. Verify the published commit before tagging. Example:

```sh
git tag v1.0.0
git push origin v1.0.0
```

Open the workflow and confirm the exact published release and SHA-256-labelled `release.zip`. A manager release can select a full already-published commit without advancing development branches. See [retained publication recovery](build-manager.md#retained-source-publication-recovery). Preserve existing tags/assets. Correct binary content with a new tag.

Three-part versions require reviewed `.github/release-notes/` Markdown. Exact notes win, then the closest lower numbered notes in the same version/channel. Main can fall back to that version's stable notes. Missing or invalid notes stop publication.

## Testing the package locally

From the checkout root with initialized submodules:

```sh
python -m logistics_build.build_retention --scratch python "$PWD/.github/scripts/package_release.py" --root "$PWD" --output "{workspace}/release.zip"
python -m unittest discover -s .github/scripts -p 'test_*.py' -v
```

The ZIP contains tracked public source plus pinned submodules under `Logistics/`, preserves executable modes and normalizes Windows launchers to CRLF. Local dry runs read tracked working edits. CI reads the clean tag. Exclude credentials, build/cache trees, root `tmp/` and local evidence. Save needed evidence before scratch exits.

### Export a manual source snapshot

On macOS run `bash PackageSnapshot.command` from the root. It includes nonignored untracked files and current edits along with initialized submodules. Review the ZIP member list before sharing.

## In-app update channels

Use `v0.1.0-main.01`, `v1.0.0-beta.1` or `v1.0.0-alpha.1`. Legacy stable tags remain recognized. Releases require desktop and both mobile native/runtime gates, including [iPhone, Duo and iPad](../testing/platform-checks.md#parallel-native-ios-validation). Preserve `.app-install.json` for hash-checked archive updates. Old ZIPs without it require fresh extraction. Git updates check out the release commit and pinned submodules. Older clients need an updater containing `-main.N` support or a new extraction.
