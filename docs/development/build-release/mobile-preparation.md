# Mobile payload preparation and validation

The Toga entry point is `Python/mobile/app.py:main`. `mobile_build/pyproject.toml` declares the Briefcase app, platform dependencies and separate native test entry. For controller and adapter ownership, use the [mobile runtime map](../architecture/mobile-runtime.md), [workspace navigation](../architecture/mobile-workspace-navigation.md) and [feature catalog](../../features/features.md).

## Owner-declared source selection

Add a new dependency to the host, service or feature's schema 1 `mobile_sources.json`. `SOURCE_OWNERS` in `mobile_build/tools.py` selects the manifests. Preflight verifies the generated `mobile.app` entry and selected module imports, including existing child packages referenced by `from` imports. Type-only imports and uncalled registration factories stay outside the runtime closure. The digest includes selected HTML, CSS and JavaScript paths and bytes.

Staging adds portable commonUtils and declared package data. It rejects linked source paths and excludes private files, Git data and the external feature checkout. Clean staging requires tracked shared sources. Local builds may use `--allow-dirty`; their evidence must bind the exact staged fingerprint. Edit sources and manifests to change generated payloads. See [mobile feature selection](../architecture/mobile-runtime.md#mobile-feature-selection) for runtime boundaries.

## Updating mobile host dependencies

Edit `mobile_build/requirements-host.in`, then regenerate and commit the lock:

```sh
uv pip compile mobile_build/requirements-host.in --python-version 3.12 --universal --generate-hashes --output-file mobile_build/requirements-host.txt
python3 dev.py toolchain
```

Native dependencies stay in `mobile_build/pyproject.toml`. Prepare pinned Go and
the langdetect wheel via **Update project tooling…**, or
`python -m build_manager.cli tooling --project NAME --update --confirm`. See
[native prerequisites](build-manager.md#project-owned-native-prerequisite-setup).

## Validation gates

Run `python3 dev.py test desktop test_mobile_packaging.py` from the root for payload omissions and digests. Use [host commands](mobile-launchers.md#host-validation) for controller checks and [platform gates](../testing/platform-checks.md) for full native app and separate embedded CPython acceptance. The native job retains the normal APK/simulator build before the test-mode build. The native and runtime verifiers require exact source, platform and case inventories. Use real OS fixtures for pickers and independent iPad scenes. Use [Duo checks](mobile-handbook.md#duo-rotation-and-fold-verification) for measured fold geometry.

## Offline component notices

Staging copies `services/licenses/` and writes platform requirements to `mobile/open-source-dependencies.json`. The offline viewer combines installed Python metadata, rclone's native Go manifest and Android's resolved runtime/Chaquopy asset. Update native provenance with dependency pins and verify notices inside the final artifact. See [collectors and refresh commands](open-source-notices.md).

## Launcher artwork

`mobile_build/resources/icons` owns the iOS light, dark and tinted slots and Android adaptive/night/themed artwork. `cloud_build.py` invokes the standard-library installer after Briefcase create/update. Use Pillow only to regenerate from the source PNGs:

```sh
mobile_build/.venv/bin/python mobile_build/build_support/icon_build.py /path/to/light.png /path/to/dark.png /path/to/monochrome.png
python3 dev.py test mobile test_icon_build.py
```

Preserve the full source tile, opaque iOS variants and Android monochrome alpha mask.
The iOS launch storyboard uses an appearance-aware image and color asset.
Android uses a launcher theme and night resources for the system splash, with a
drawable fallback before Android 12. Their background colors match the mobile
startup screen's light and dark window colors. Compile the iOS catalog after
slot changes and verify both cold-launch themes on devices.

## Runtime and native integration owners

- [Mobile workspace navigation](../architecture/mobile-workspace-navigation.md)
  covers native route stacks, Back handling and independent UIKit scenes.
- [Document storage sessions](../architecture/document-storage.md)
  covers the ordinary manifest, private readers and close decisions.
- [Mobile file storage](../architecture/mobile-file-storage.md)
  covers collection locations, iOS migration and the incoming-file extension.
- [Rclone development](../../features/rclone/development/development.md)
  covers the embedded bridge, credentials and transfers.
