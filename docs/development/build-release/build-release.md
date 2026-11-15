# Build and release

Use this section when you need platform validation, an installable app or a
release. For an ordinary code change, begin with the focused checks in
[Testing Logistics](../testing/testing.md).

The standalone Build Deployment Manager runs Logistics' build and delivery
plans. This repository supplies the project policy and adapters. A build creates
an artifact; installing it on a device and publishing it to testers are separate
choices in the reviewed workflow.

## Run a build or release

1. Follow [operator setup](operator/setup.md) to connect the manager to your
   checkout and prepare its tools.
2. Use [operator workflows](operator/workflows.md) to choose checks, a build or
   delivery, review the source and target, and run the plan.
3. Consult the platform guide below when you need native prerequisites,
   device installation or distribution details.

The [operator guide](operator/operator.md) is the entry point for these tasks.

## Understand or change the build system

Read [build and deployment ownership](build-tooling.md) first to distinguish
project policy from the external manager and platform helpers. Then
[trace a validation plan](build-manager-journeys.md#trace-a-validation-plan)
from the manager's review screen to the Logistics adapter and its fixture tests.

## Procedure and reference guides

| Task | Guide |
| --- | --- |
| Change plan, backend or retention policy | [Build Manager adapter](build-manager.md) |
| Set up or diagnose native builds | [Mobile handbook](mobile-handbook.md), [launcher commands](mobile-launchers.md) |
| Change staged source or notices | [Mobile preparation](mobile-preparation.md), [open-source notices](open-source-notices.md) |
| Install on devices or distribute betas | [Device deployment](mobile-device-deployment.md), [TestFlight](mobile-testflight.md) |
| Publish a source release | [Release gates](releasing.md) |
| Reproduce the experimental Qt app | [iOS Qt proof](qt-proof-launchers.md) |
