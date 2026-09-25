# Comics Feature

Provides comic-related integration for Logistics.

## Responsibilities

- Detect and configure comic-reader integrations.
- Work with CBZ and CBR comic archives.
- Edit ComicInfo.xml metadata.
- Support comic-specific conversion, compression, and organization workflows.
- Keep comic-specific behavior isolated from Logistics core and UI code.

## Structure

- `actions.py` contains user-facing comic actions such as reader launching and CBZ organization.
- `detection.py` contains ComicRack and YACReader detection/configuration helpers.
- `cbz.py` contains CBZ compression and processing behavior.
- `conversion.py` contains CBR to CBZ conversion behavior.
- `metadata.py` contains ComicInfo.xml metadata editing behavior.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Initialization

This feature does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until comic functionality is used.

## Safety Notes

Several Comics operations modify or replace files.

CBR to CBZ conversion deletes the original CBR after a successful conversion.
ComicInfo metadata operations unpack and rebuild CBZ archives.
CBZ organization copies each archive into a new folder and then deletes the original after the copy succeeds.
CBZ compression may replace existing archives.

These operations should be tested against disposable data when behavioral changes are made.

## Future Work

`logisticsUtils/epubUtils.py` is intentionally retained for future EPUB development.

Image utilities remain separate because they are also used outside the Comics feature.
