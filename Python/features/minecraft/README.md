# Minecraft Feature

Provides Minecraft server integration for Logistics.

## Responsibilities

- Discover configured Java and Bedrock server roots.
- Represent individual Minecraft servers.
- Launch supported servers.
- Open server folders and documentation.
- Edit `server.properties`.
- Contribute Minecraft servers to the generic Servers page.

## Structure

- `detection.py` resolves the Java and Bedrock server roots.
- `server.py` contains the `MinecraftServer` model and server actions.
- `ui_contributions.py` contributes Minecraft as a server provider.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Detection

Minecraft server roots are resolved from the configured Marc Dropbox location.

Java servers are discovered under:

`Software/Server/Minecraft`

Bedrock servers are discovered under:

`Software/Server/Minecraft (Bedrock)`

Each immediate child directory is represented as a Minecraft server, except
directories whose names end in `Backups`.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry and performs no work until
the Servers page requests Minecraft server information.
