#!/bin/bash

# import the global variable set.
. /var/archive-kit/rapidumo/cron/vars

##################################
##################################

mkdir -p $TMP_DATA_DIR
cd $TMP_DATA_DIR

# update the tanglu-meta copy
if [ ! -d "$TMP_DATA_DIR/tanglu-meta" ]; then
  git clone --quiet --depth=1 git://gitorious.org/tanglu/tanglu-meta.git tanglu-meta
fi
cd $TMP_DATA_DIR/tanglu-meta
git pull --quiet
# germinate!
mkdir -p /srv/dak/export/germinate/tanglu.$CURRENT_DEV_SUITE
cd /srv/dak/export/germinate/tanglu.$CURRENT_DEV_SUITE
germinate -S file://$TMP_DATA_DIR/tanglu-meta/seed  -s aequorea -d aequorea -m file:///srv/archive.tanglu.org/tanglu/ -c main contrib

cd $TMP_DATA_DIR
