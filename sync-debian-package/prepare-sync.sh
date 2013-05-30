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

cd $MOMDIR
#bzr update

cp addcomment.py /srv/patches.tanglu.org/merges

# Update the blacklist
wget -q -O/srv/patches.tanglu.org/sync-blacklist.txt http://gitorious.org/tanglu/import-blacklist/blobs/raw/master/sync-blacklist.txt

# Download new packages
./update-pool.py $QUIET debian tanglu

# Update the Sources files against new packages that have been downloaded.
./update-sources.py $QUIET
