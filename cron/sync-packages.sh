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

# Update the local Debian package mirror
synchrotron --update-data

# sync packages
synchrotron --import-all $DEBIAN_SOURCE_SUITE staging main
synchrotron --import-all $DEBIAN_SOURCE_SUITE staging contrib
synchrotron --import-all $DEBIAN_SOURCE_SUITE staging non-free

# update cruft information
synchrotron --update-cruft-report --quiet

# update archive
dak generate-packages-sources2 -s staging
dak generate-releases -s staging
# sync the public local ftp mirror
mirror

# tell Debile that we have new stuff
debile_unblock_trigger
