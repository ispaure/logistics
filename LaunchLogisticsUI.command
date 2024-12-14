#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SCRIPT_SUBPATH="/Python/launch.py"
FULL_PATH="$SCRIPT_DIR$SCRIPT_SUBPATH"
echo $FULL_PATH
python3 $FULL_PATH