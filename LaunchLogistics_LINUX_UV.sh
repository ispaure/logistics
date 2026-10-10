#!/usr/bin/env bash

PROJECT_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
CONFIG_FILE="$PROJECT_ROOT/launch_config.ini"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: launch_config.ini was not found:"
    echo "  $CONFIG_FILE"
    exit 1
fi

read_config_value() {
    awk -F= -v key="$1" '
        $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
            value=$2
            sub(/^[[:space:]]*/, "", value)
            sub(/[[:space:]]*$/, "", value)
            print value
            exit
        }
    ' "$CONFIG_FILE"
}

COMMONUTILS_ROOT="$(read_config_value commonutils_root)"
PAUSE_AFTER_COMPLETED="$(read_config_value pause_after_completed)"
PAUSE_AFTER_COMPLETED="${PAUSE_AFTER_COMPLETED:-false}"

if [[ -z "$COMMONUTILS_ROOT" ]]; then
    echo "ERROR: commonutils_root was not found in launch_config.ini."
    exit 1
fi

LAUNCHER="$PROJECT_ROOT/$COMMONUTILS_ROOT/launchers/LaunchPythonProject_LINUX_UV.sh"

if [[ ! -f "$LAUNCHER" ]]; then
    echo "ERROR: Shared Python launcher was not found:"
    echo "  $LAUNCHER"
    exit 1
fi

export LOGISTICS_ROOT="$PROJECT_ROOT"
unset LOGISTICS_ALLY_ROOT
ENVIRONMENT_ROOT="$PROJECT_ROOT"
ALLY_ROOT="$(dirname -- "$PROJECT_ROOT")/ally-tools"
if [[ -d "$ALLY_ROOT" ]]; then
    if [[ ! -f "$ALLY_ROOT/Python/pyproject.toml" || ! -f "$ALLY_ROOT/logistics_launch.ini" || ! -f "$ALLY_ROOT/Python/ally_feature/__init__.py" ]]; then
        echo "ERROR: Sibling ally-tools is missing its dependency manifest, Logistics launch config, or feature package." >&2
        exit 1
    fi
    ENVIRONMENT_ROOT="$ALLY_ROOT"
    CONFIG_FILE="$ALLY_ROOT/logistics_launch.ini"
    echo "Using private Ally environment: $ALLY_ROOT/.venv"
fi
bash "$LAUNCHER" "$ENVIRONMENT_ROOT" "$CONFIG_FILE" "$PAUSE_AFTER_COMPLETED"
exit $?
