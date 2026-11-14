# Logistics build tooling owners

| Work | Owner |
| --- | --- |
| Select payload and verify source | `mobile_build/tools.py` |
| Compose Briefcase project and build bridge | `mobile_build/cloud_build.py`, `build_support/` |
| Device, Firebase and TestFlight policy | `mobile_build/deployment/` |
| Verify prepared artifacts and journal writes | `logistics_build/distribute_prepared.py` |
| Guest workload and recovery | `vm_backend.py`, `windows_backend.py`, `guest_results.py` |
| Reusable transport/signing | SDK `guest_tools`, `app_store_connect`, `firebase` |
| Native validation and reports | `mobile_build/validation/`, `native_tests/` |
| Host regressions | `mobile_build/tests/` grouped by responsibility |

The [manager](../../user/build-manager.md) owns operator review. Reconcile ambiguous attempt receipts before another provider write.

## Deployment commands and paths

Run module diagnostics from the root:

```sh
mobile_build/.venv/bin/python -m mobile_build.deployment.device_tools --help
mobile_build/.venv/bin/python -m mobile_build.deployment.testflight_tools --help
python3 dev.py test mobile test_native_report.py
python3 dev.py test mobile 'test_reader_*.py'
```

Run native `validation/ui_tools.py` from `mobile_build` with the prepared mobile interpreter. `deployment_paths` separates private settings and signing from generated workspaces.

## Signed local coverage in hosted releases

Enroll the local Ed25519 signer once:

```sh
.venv/bin/python -m logistics_build.release_test_evidence enroll --repository ispaure/logistics
```

Review and commit only `.github/local-test-signers`. The private key stays in the manager's private configuration. The reviewed combined release can publish recent passing exact-source host receipts under `refs/notes/build-manager-tests` before the tag. Hosted checks validate the signature, committed allowlist, source, interpreter/toolchain inputs and 24-hour limits. Missing or mismatched proof runs fresh. Native coverage uses its platform gates.

`testing.reuse_verified_results=local-off` forces fresh local execution; `off` also suppresses signed export and hosted reuse. A new release records the latter as immutable `Build-Manager-Reuse: off` tag metadata.

## Android runtime evidence transport

`logistics_build/android_runtime_hosted.py` collects the bounded private `mobile.smoke` receipt from its owned emulator before teardown. The full gate requires the exact source manifest, runtime identity, every declared case, zero skips, and successful cleanup before publishing canonical results. Retain raw receipts and best-effort logs for failed attempts. Portable tests cover receipt transport; hosted acceptance requires the actual testbed.
