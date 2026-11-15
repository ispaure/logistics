# Developing Logistics

Logistics brings file browsing, readers, editors and other tools into one
application. A file can stay open in an editor while you return to browsing.
That simple workflow shows how the app fits together: the host keeps the
browser and the open document available, while the editor owns what happens to
the text.

If you are new to the project, [set up and run a checkout](setup/setup.md) and
try the local text file walkthrough. Then read
[how the application fits together](architecture/architecture.md) to see what
the desktop and mobile hosts share, and where features and services fit. Then
use the steps below to find the right place for a change.

## Make your first contribution

Start with a behavior you can describe from the user's point of view. For a
bug, reproduce it with a small file or other input you can share, and note
what should have happened. For an improvement, identify the step that should
work differently. This gives you something concrete to check after editing.

Use the [feature catalog](../features/features.md) when the behavior belongs
to a particular tool. Its Development guide explains what that tool owns and
where its tests live. If the behavior involves navigation, file access, or
another part shared across tools, use the [code map](architecture/code-map.md)
to follow it to the relevant host or service.

Before editing, find an existing check that covers your example. The
[testing guide](testing/testing.md) shows how to preview a test selection and
run the tests for an owner. If the behavior needs new coverage,
[add and diagnose a test](testing/adding-tests.md) walks through checking WebP
input with two small generated images. After making the change, repeat the
original workflow and run the focused tests. If a workflow or a contract has
changed, update the [guide for the people it affects](documentation/documentation.md).

## Build and release work

Use [Build and release](build-release/build-release.md) when you need to stage
a mobile app, review a validation plan, or prepare a release. The desktop
walkthrough above does not require a mobile SDK or signing setup.
For reports from an existing run, see [validation artifacts](testing/validation-artifacts.md).
