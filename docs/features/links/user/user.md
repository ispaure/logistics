# Open configured service shortcuts

Enable **Personal Links** under **Settings → Features**, then open **Links** in
the desktop navigation. Buttons are grouped under Self-Improvement, Quick Links
and Entertainment. Selecting one asks your default browser to open its URL.

## Configure shortcuts

Open the Personal Links configuration in Settings. Its **URLs** and **ResolveIP**
sections contain the shortcut targets and machine-address replacements. Choose
personal settings for private overrides, then explicitly **Save Settings**.
Software defaults edit `Python/features/links/config.ini`; use personal settings
for your own addresses and account-specific URLs.

The catalog is fixed: changing a known **URLs** entry changes its button's target;
adding an arbitrary INI key does not create a button. Prefer the supplied `_str`
keys, for example `plex_common_web_str`. Legacy unsuffixed keys remain readable.
When both forms exist, the typed `_str` entry takes precedence.

Only HTTP and HTTPS targets with a hostname are accepted. For example,
`sonarr_common_local_str = http://<goat-pc>:8989` uses the value of
`goat-pc_str` in **ResolveIP**. The supported placeholders are `<goat-pc>` and
`<yagi-mac>`; other placeholder names are not expanded. These are literal
replacements, so enter a hostname or address rather than a complete URL in
**ResolveIP**. This substitution does not discover machines on the network.

## Open a link and troubleshoot

Select a shortcut. The page reports **Opened in your browser.** when the browser
launcher accepts it, or **The browser could not open this link.** when it declines.
Missing or invalid configuration is shown on the page instead of opening a URL.
Unresolved placeholders and whitespace in the resulting URL are rejected.

If the browser opens but the service does not load, check the target URL,
replacement address, network connection and service itself. Browser acceptance
is not a service-health check. Logistics does not start the linked server or
sign in for you; the browser handles authentication.

## Platform scope

This launcher is desktop-only. See [mobile availability](../user_mobile/user_mobile.md)
for the distinction from Notes Library's Links drawer, and
[Using Logistics](../../../user/user.md) for general navigation and settings.
