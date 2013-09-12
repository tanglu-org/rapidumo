#!/bin/sh
# small helper for autorebuild-execution

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
sudo -u dak-rebuild $DIR/autorebuild.py "$@"
