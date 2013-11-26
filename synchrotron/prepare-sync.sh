#!/bin/sh

set -e
umask 002

if [ "$DEBUG" = "y" ]; then
        QUIET=""
else
        QUIET="-q"

        if ! mkdir /srv/patches.tanglu.org/.lock 2>/dev/null; then
                echo "LOCKED (another one running?)"
                exit 1
        fi
        trap "rmdir /srv/patches.tanglu.org/.lock" 0
fi

MOMDIR="/var/archive-kit/merge-o-matic"
WORKDIR="/srv/patches.tanglu.org"

# FIXME: Don't hardcode paths anywhere...
BASE=/var/archive-kit/rapidumo

# Update the blacklist
sh $BASE/cron/sync-hints.sh
rm /srv/patches.tanglu.org/sync-blacklist.txt
cp /srv/dak/archive-hints/sync-blacklist/sync-blacklist.txt /srv/patches.tanglu.org/sync-blacklist.txt

cd $MOMDIR

cp addcomment.py /srv/patches.tanglu.org/merges

# Download new packages
./update-pool.py $QUIET debian tanglu

# Update the Sources files against new packages that have been downloaded.
./update-sources.py $QUIET
