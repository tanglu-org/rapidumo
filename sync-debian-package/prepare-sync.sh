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
if [ ! -d /srv/patches.tanglu.org/blacklist ]; then
  git clone git://gitorious.org/tanglu/import-blacklist.git /srv/patches.tanglu.org/blacklist
else
  cd /srv/patches.tanglu.org/blacklist/
  git pull
fi
rm /srv/patches.tanglu.org/sync-blacklist.txt
cp /srv/patches.tanglu.org/blacklist/sync-blacklist.txt /srv/patches.tanglu.org/sync-blacklist.txt

cd $MOMDIR

# Download new packages
./update-pool.py $QUIET debian tanglu

# Update the Sources files against new packages that have been downloaded.
./update-sources.py $QUIET
