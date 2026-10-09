# Links Feature

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

Provides configured web-link launching for Logistics.

## Responsibilities

- Read URL entries from the feature-owned `features/links/config.ini`.
- Resolve configured machine placeholders in URLs.
- Open configured URLs in the user's default web browser.

## Structure

- `actions.py` contains configured URL-launching behavior.

## URL Resolution

Configured URLs may contain placeholders such as:

- `<goat-pc>`
- `<yagi-mac>`

The feature replaces these placeholders using values from the `ResolveIP` section of `features/links/config.ini` before opening the URL.

Feature configuration keys now use `_str`; existing unsuffixed URL and ResolveIP keys remain readable. Settings displays each section as a tab with one row per entry.
