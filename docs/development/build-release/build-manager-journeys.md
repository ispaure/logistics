# Combined validation and delivery

See [operator journeys](../../user/build-manager-journeys.md) for starting checks and delivery.

## Trace a validation plan

1. From the checkout root run `python3 logistics_build/tooling_bootstrap.py status` (`py` on Windows). If either environment needs repair, follow [tooling readiness](../../user/build-manager.md#project-tooling-readiness-and-repair).
2. In the manager choose the trusted checkout, **Run checks**, a platform and local host, then **Next: review plan**. Inspect source, host, phases and prerequisites.
3. Trace `build-project.json` → `LogisticsProject.make_journey` → `logistics_build/manager_journeys.py` (bridge action `journey_plan`). Match its [suite IDs](#shared-tests-and-suite-discovery) to `build-tests.json`.
4. From the root run `python3 dev.py test desktop --exact-file Python/tests/tooling/test_manager_journeys.py`. Expect fixture plans to pass source binding, gate and cleanup checks using mocked native/provider work. For import errors, see [local SDK verification](#local-manager-dependency-and-verification).

## Source, settings and resource integrity

One immutable PlanningContext binds source, version and effective settings. Each branch uses unique IDs, scoped resources and explicit dependencies. Source/settings drift stops preparation. Credentials remain protected references. Independent platform branches can overlap. See [storage policy](build-manager.md#automatic-storage-retention) and [manager installation](../../user/build-manager.md#external-manager-installation-adapter-api-1).

## Local manager dependency and verification

Use the exact revision in `build-manager-dependency.json`. See [manager installation](../../user/build-manager.md#external-manager-installation-adapter-api-1) for the pinned SDK and explicit local override. Run the [fixture check](#trace-a-validation-plan) before native or provider work.

## Shared tests and suite discovery

The manager resolves `build-tests.json` against the selected capture. Full desktop/mobile host gates run pinned commonUtils before their dependents. Use stable suite IDs, explicit `after` edges and named interpreter environments. Dependency suites must name their pinned in-tree submodule. Focused diagnostics cover their selected scope. Revisions predating the manifest need their matching adapter.

## Retried guest validation

Each attempt retains its logs. Retry a matching finished source/backend only after owned cleanup. Focused `manager:test_ui.py` selects pinned SDK diagnostics; `shared:` selects commonUtils. For incomplete Windows setup or retained diagnostics, run these from the root with the matching manager:

```sh
python -m logistics_build.guest_attempts reconcile-windows-setup --directory RESULT_ROOT --manager-checkout PINNED_CHECKOUT
python -m logistics_build.guest_results --directory ATTEMPT --source-plan PLAN --backend BACKEND --manager-commit PIN
python -m logistics_build.continuation_inputs --root . --previous OLD_COMMIT --current HEAD_COMMIT
```

Reconciliation requires an absent exact guest namespace. Source review can enforce `--require-current-equivalent` and `--expect-identity`. Add `--native-output RUN --native-plan-identity SHA` to verify original native coverage and toolchains. Keep original results and validate changed desktop fixtures. Review identities establish applicability; delivery still requires verified original checks, cleanup and available artifacts.
