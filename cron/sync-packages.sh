#!/bin/bash
set -e

# import the global variable set.
. /var/archive-kit/rapidumo/cron/vars

########################################################################
# Functions                                                            #
########################################################################
# common functions are "outsourced"
. "${configdir}/common"

# source the dinstall functions
. "${configdir}/dinstall.functions"

########################################################################
########################################################################

DAK_LOCKDIR=/srv/dak/lock
DAK_LOCK=$DAK_LOCKDIR/daily.lock
LOCKFILE="$DAK_LOCKDIR/synchrotron.lock"

OPTIONS="$@"
qoption () {
    for a in $OPTIONS; do if [ "$a" = "$1" ]; then return 0; fi; done
    return 1
}

cleanup() {
    rm -f "$LOCKFILE"
}

# only run one cron.daily
if ! lockfile -r8 $LOCKFILE; then
    echo "aborting Synchrotron cron.daily because $LOCKFILE has already been locked"
    exit 0
fi
trap cleanup 0

if ! qoption allowdaklock; then
	while [ -f $DAK_LOCK ]; do
		echo `date` $DAK_LOCK exists. Sleeping for 10 more minutes.
		sleep 600
	done
fi

# sync packages
sync-debian-package --import-all testing staging main
sync-debian-package --import-all testing staging contrib
sync-debian-package --import-all testing staging non-free

# update archive
dak generate-packages-sources2 -s staging
dak generate-releases -s staging
# sync the public local ftp mirror
mirror

# tell Debile that we have new stuff
debile_unblock_trigger
