# Open configured service shortcuts

Enable **Personal Links** under **Settings → Features** to use these tools.

The **Links** page opens configured websites in your default browser.

## Configure shortcuts

Edit `Python/features/links/config.ini` to match your services. URL placeholders
such as `<goat-pc>` or `<yagi-mac>` are resolved using the file's `[ResolveIP]`
settings. Use your own machine addresses and URLs.

## Open a link

Select the desired shortcut on the Links page. If it does not open, check the
configured URL, hostname substitution, network access and default browser.
This feature opens links; it does not start the linked server or check its health.

## More help

See [Using Logistics](../../../../../docs/user/user.md) for navigation and settings.

Use **Settings → Links** to save URL changes explicitly. The shipped catalog is
a fixed set of shortcuts: editing known `[URLs]` keys changes their targets;
adding arbitrary INI keys does not create new buttons. Prefer the supplied `_str`
keys (for example `plex_common_web_str`); legacy unsuffixed keys remain readable.
Changes configure the links, not the services they point to.
