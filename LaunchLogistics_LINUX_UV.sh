#!/usr/bin/env bash
set -u
set -o pipefail

SCRIPT_NAME="$(basename -- "$0")"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)" || {
    echo "ERROR: $SCRIPT_NAME could not determine its own directory." >&2
    exit 1
}
CONFIG_FILE="$SCRIPT_DIR/launch_config.ini"

pause_if_interactive() {
    if [[ -t 0 ]]; then
        echo
        read -r -p "Press Enter to close..." _ || true
    fi
}

fail() {
    echo "ERROR: $*" >&2
    pause_if_interactive
    exit 1
}

read_launch_value() {
    local key="$1"
    local output_variable="$2"
    local value
    local status

    command -v awk >/dev/null 2>&1 || fail "awk is required to read launch_config.ini but was not found."

    value="$(awk -v wanted="$key" '
        function trim(s) {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
            return s
        }
        {
            sub(/\r$/, "")
        }
        /^[[:space:]]*[#;]/ { next }
        /^[[:space:]]*\[Launch\][[:space:]]*$/ {
            in_launch = 1
            next
        }
        /^[[:space:]]*\[/ {
            in_launch = 0
        }
        in_launch {
            line = $0
            pos = index(line, "=")
            if (!pos) {
                next
            }
            found_key = trim(substr(line, 1, pos - 1))
            if (found_key == wanted) {
                matches++
                found_value = trim(substr(line, pos + 1))
                if ((found_value ~ /^".*"$/) || (found_value ~ /^\047.*\047$/)) {
                    found_value = substr(found_value, 2, length(found_value) - 2)
                }
                value = found_value
            }
        }
        END {
            if (matches > 1) {
                exit 2
            }
            if (matches == 1) {
                print value
            }
        }
    ' "$CONFIG_FILE")"
    status=$?

    case $status in
        0) printf -v "$output_variable" '%s' "$value" ;;
        2) fail "Duplicate '$key' entries were found in [Launch] in $CONFIG_FILE." ;;
        *) fail "Failed to read '$key' from $CONFIG_FILE." ;;
    esac
}

[[ -f "$CONFIG_FILE" ]] || fail "launch_config.ini was not found next to this launcher: $CONFIG_FILE"
[[ -r "$CONFIG_FILE" ]] || fail "launch_config.ini exists but is not readable: $CONFIG_FILE"

COMMONUTILS_ROOT_VALUE=""
read_launch_value commonutils_root COMMONUTILS_ROOT_VALUE
[[ -n "$COMMONUTILS_ROOT_VALUE" ]] || fail "commonutils_root is missing or empty in [Launch] in $CONFIG_FILE."
[[ "$COMMONUTILS_ROOT_VALUE" != /* ]] || fail "commonutils_root must be relative to the project launcher directory, not absolute: $COMMONUTILS_ROOT_VALUE"

COMMONUTILS_ROOT="$SCRIPT_DIR/$COMMONUTILS_ROOT_VALUE"
[[ -d "$COMMONUTILS_ROOT" ]] || fail "commonUtils root was not found: $COMMONUTILS_ROOT"

COMMON_LAUNCHER="$COMMONUTILS_ROOT/launchers/LaunchPythonProject_LINUX_UV.sh"
[[ -f "$COMMON_LAUNCHER" ]] || fail "Shared Linux launcher was not found: $COMMON_LAUNCHER"
[[ -r "$COMMON_LAUNCHER" ]] || fail "Shared Linux launcher exists but is not readable: $COMMON_LAUNCHER"

# Invoke through Bash so the shared launcher does not need its executable bit set.
# This also works cleanly when commonUtils lives in a read-only/shared checkout.
bash "$COMMON_LAUNCHER" "$SCRIPT_DIR" "$CONFIG_FILE"
status=$?

if [[ $status -ne 0 ]]; then
    echo "ERROR: Shared Linux launcher exited with code $status." >&2
fi
exit "$status"
