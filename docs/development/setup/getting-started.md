# Run a checkout and open your first document

Start with a plain text file on your own computer. You will see how File Browser
opens an editor, how to return to that editor while browsing, and how to tell
when the changes have been saved. No cloud account or server is needed.

## 1. Prepare your environment

For a fresh development checkout, clone the `alpha` branch with its pinned
commonUtils submodule. If you already have a checkout, start in its root and
see [desktop setup](setup.md#desktop-interpreter-and-lockfile) if the
submodule is missing.

```sh
git clone --branch alpha --recurse-submodules https://github.com/ispaure/logistics.git
cd logistics
python3 dev.py setup desktop --dry-run
python3 dev.py setup desktop
python3 dev.py doctor
```

On Windows use `py` instead of `python3`. If uv is missing, run the launcher
for your platform (below) to install it, then return to these commands. The
dry run prints the sync command; setup creates the checkout's `.venv`. Look
for `OK desktop`, `OK commonUtils` and `OK uv` in doctor output. A missing
mobile environment does not prevent the desktop walkthrough.

## 2. Launch the desktop app

From this checkout, open **LaunchLogistics_MAC.command** on macOS or
**LaunchLogistics_WIN.bat** on Windows. On Linux run
`bash LaunchLogistics_LINUX_UV.sh`. Choose **File Browser** from the landing
page. If the sidebar is hidden, open the floating Settings menu and choose
**Open full hub with sidebar** so you can switch between File Browser and
open documents.

## 3. Open, switch, save and reopen

1. Outside the checkout, create a disposable file named `first-document.txt`
   containing a line of plain text. Find it in **File Browser** and
   double-click it. It should open in Text Editor. If it opens outside
   Logistics, enable **Text Editor** under **Settings → Features**, save the
   setting and try again.
2. Add a line in the editor. Switch back to **File Browser**, then choose the
   file from **Open documents** in the sidebar. Your unsaved line should
   still be there.
3. Save the file, close its editor tab, and open it again from **File Browser**.
   Your new line should still be there after reopening.

The second step shows that switching views leaves a document open. The last
step checks that saving changed the file itself. The
[Text Editor user guide](../../features/text_editor/user/user.md) explains what
to do when a file has changed outside the app. Next, see
[how the application fits together](../architecture/architecture.md) to follow
the same workflow through the host, editor and shared library.
