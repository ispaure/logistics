# Application architecture

The easiest way to see who owns what in Logistics is to follow a file. In the
[desktop walkthrough](../setup/getting-started.md), you opened a text file
from File Browser, returned to it through Open documents, and saved it. Those
steps involve different parts of the application.

## Shell, features and services

On desktop, the Qt shell provides File Browser and the tab workspace. Logistics
connects the shared commonUtils browser to the enabled features. When you
double-click a plain text file, Text Editor's declared file action opens it.
The application keeps the editor available after you leave File Browser and
the Documents workspace lets you return to it. The editor handles the text,
decides whether there is anything to save, and deals with a file that has
changed on disk. It uses commonUtils to preserve encoding and line endings and
to publish file changes safely.

Mobile has its own host, built with Toga and native controls. It opens supported
formats into a mobile document workspace and owns navigation, open views and
their lifetimes. A feature can provide mobile controls or reuse portable code
without sharing its desktop widgets. The same visible task can therefore have
a different entry point or implementation on each platform.

Features own behavior specific to a tool or format, such as editing text or
reading a comic. The host decides where those tools can appear. Logistics
services hold rules that apply across screens or tools, such as which folders
are offered as workspaces or which document sources may be written to. A
storage provider supplies access to the bytes. A document session holds the
state and access needed to keep a file open until the host retires it.

Use commonUtils for mechanisms that another application could call, like
writing a file safely or mounting a browser control. Keep the app's decisions
with Logistics: which paths are allowed, what commands are offered, and when
to prompt the user. Build tooling has a similar boundary. Logistics declares
the project, tests and release rules in `logistics_build/`; the standalone
Build Deployment Manager executes the project's plans.

If you are ready to change something, return to [make your first contribution](../development.md#make-your-first-contribution).
Use the [code map](code-map.md) when you know what behavior you want to find.

## Follow the host

For desktop navigation and open windows, start with [desktop startup and lifecycle](desktop-lifecycle.md).
The [screen and panel map](ui-architecture.md) locates named controls, and
[File Browser development](file-browser.md) explains how the browser wires up
actions and works with different sources.

For mobile, use [the host runtime](mobile-runtime.md) for app and document
lifetime, including [native startup progress](mobile-runtime.md#native-startup-progress).
See [workspaces and navigation](mobile-workspace-navigation.md) for
routes, panes and scenes. Platform guides cover [mobile accent controls](mobile-accent.md)
and [iOS Shortcut value widgets](shortcut-widgets.md).
[Mobile preparation](../build-release/mobile-preparation.md) explains how
source declarations become a packaged app.

## Follow the data

Start with [Logistics host services](services.md) for shared app rules. If
your change follows a document, see [document storage sessions](document-storage.md)
for the boundary among hosts, formats and providers, including the
[mobile provider-to-reader trace](document-storage.md#trace-a-mobile-provider-reader).
[Mobile file storage and incoming shares](mobile-file-storage.md) covers local
files and handoffs from the OS; [reader progress and history](reader-state.md)
covers what is saved after a read.

For shared rules, see [configuration and compatibility](configuration-and-data.md)
for defaults and migrations, [access and privacy](access-privacy.md) for
credential and protection decisions, and [audio and capture privacy](audio-playback.md)
for playback and screen capture. See [Siri access to onscreen content](siri-screen-access.md)
for the Apple platform feasibility decision.

## Add or extend a feature

Use [feature organization and lifecycle](features.md) to decide which
parts belong to a feature, then [application extension points](extension-points.md)
to choose how the app will expose them. The [feature registry and infrastructure](feature-infrastructure.md)
explains how declarations become available and how dependencies and enablement
work. See [commonUtils integration](commonutils-integration.md) for changes
at the shared-library boundary and [optional external feature integration](optional-integration.md)
for the app's external discovery and loading contract.
