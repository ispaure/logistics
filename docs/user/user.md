# Using Logistics

- [Reader history and saved positions](reader-history.md)

Start in **File Browser** to work with any folder, or **Workspaces** for configured
libraries, servers and remote storage. **Documents** lists open readers/editors;
**Settings → Features** saves which tools are enabled. Required features are enabled
together, and disabling a dependency with active dependents is refused.

- [Files, search, storage, panes and Markdown](files-and-documents.md)
- [Choose storage, save confidently and recover](working-safely.md)
- [Bulk Rename: preview, apply and recover](../features/bulk_rename/user/user.md)
- [Configuration: paths, credentials and saved settings](configuration.md)

Save settings explicitly; some changes apply to new windows or after a restart.
A cancelled batch may already have changed some files;
check the feature's recovery guidance before retrying.

## Try a local file first

1. Open File Browser and choose a folder containing a disposable text or Markdown
   file. No cloud account or server configuration is needed.
2. Open it in its reader/editor. Go to Documents to find the retained tab and
   return to it after browsing another folder.
3. If you edit the file, save and reopen it to check the result. Closing a document
   can prompt to save or discard; cancelling keeps it open.

You should now be able to find both the file's folder and its open document view.
Use [working safely](working-safely.md) before exploring private copies, transfers
or batch changes. Closing a document and deleting its file are different actions.

## Feature guides

Open **Settings**, select a feature in the sidebar, then click **User Guide**.
Each guide explains that feature's setup, workflows, limits and recovery options.
The button is unavailable if the guide is not installed.

When browsing outside the app, use the [feature catalog](features.md)
to find the same guides.

## If a tool does not work

Check feature enablement, the selected source/credential, required software and
folder detection rules in its guide. Refresh Workspaces after changing its folders
or loaded configs. Missing credentials do not prevent ordinary local browsing.

Several Logistics instances can run at once and share file indexing work.
Initial dependency setup needs internet. A missing shared launcher usually means
the commonUtils submodule was not included; see
[installation](../../README.md#get-started).

- [Browse all feature guides](features.md)

## Further reading

- [Using the Logistics build manager](build-manager.md)
- [Validating and delivering Logistics](build-manager-journeys.md)
