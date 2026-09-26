# Links Feature

Provides configured web-link launching for Logistics.

## Responsibilities

- Read URL entries from the feature-owned `features/links/config.ini`.
- Resolve configured machine placeholders in URLs.
- Open configured URLs in the user's default web browser.
- Keep Links-tab behavior out of the global command layer.

## Structure

- `actions.py` contains configured URL-launching behavior.
- `__init__.py` exposes the feature to the Logistics feature registry.

## URL Resolution

Configured URLs may contain placeholders such as:

- `<goat-pc>`
- `<yagi-mac>`

The feature replaces these placeholders using values from the `ResolveIP` section of `features/links/config.ini` before opening the URL.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry but performs no work until a Links action is used.


## Configuration

Links owns its configuration in:

`features/links/config.ini`

The root Logistics configuration does not contain Links-specific URLs or
hostname/IP substitutions.
