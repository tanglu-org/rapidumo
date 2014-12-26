#!/bin/bash
set -e

# import the global variable set.
. /var/archive-kit/rapidumo/cron/vars

# update the package-watch pages
cd /srv/dak/export/
python $RAPIDUMO_PATH/pkgwatch/versions.py
cd $TMP_DATA_DIR
