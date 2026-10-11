#!/usr/bin/env bash

PROJECT_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
CONFIG_FILE="$PROJECT_ROOT/launch_config.ini"
LOGISTICS_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
case "$LOGISTICS_CONFIG_HOME" in /*) ;; *) LOGISTICS_CONFIG_HOME="${HOME}/.config" ;; esac
export COMMONUTILS_PERSONAL_CONFIG_FILE="${LOGISTICS_CONFIG_HOME}/logistics/configuration/launch_config.ini"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: launch_config.ini was not found:"
    echo "  $CONFIG_FILE"
    exit 1
fi

read_config_value() {
    local inputs=("$CONFIG_FILE")
    [[ ! -f "$COMMONUTILS_PERSONAL_CONFIG_FILE" ]] || inputs+=("$COMMONUTILS_PERSONAL_CONFIG_FILE")
    awk -v key="$1" '
        FNR == 1 { in_launch=0; matches=0 }
        /^[[:space:]]*\[Launch\][[:space:]]*$/ { in_launch=1; next }
        /^[[:space:]]*\[/ { in_launch=0 }
        in_launch {
            pos=index($0,"="); if(!pos) next
            name=substr($0,1,pos-1); gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
            if(name==key) {
                value=substr($0,pos+1); gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                found=1
            }
        }
        END { if(found) print value }
    ' "${inputs[@]}"
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
