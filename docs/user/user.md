# Using Logistics

Start in **File Browser** to work with any folder, or **Workspaces** for configured
libraries, servers and remote storage. **Documents** lists open readers/editors;
**Settings → Features** saves which tools are enabled. Required features are enabled
together, and disabling a dependency with active dependents is refused.

- [Files, search, storage, panes and Markdown](files-and-documents.md)
- [Bulk Rename: preview, apply and recover](../features/bulk_rename/user/user.md)
- [Configuration: paths, credentials and saved settings](configuration.md)

Save settings explicitly; some changes apply to new windows or after a restart.
A cancelled batch may already have changed some files;
check the feature's recovery guidance before retrying.

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
