# perform some janitor tasks automatically
#!/bin/bash
set -e

# import the global variable set.
. /var/archive-kit/rapidumo/cron/vars

JANITOR=$RAPIDUMO_PATH/scripts/janitor

$JANITOR -r -s staging --use-dak

# automatically delete packages which are removed in Debian (and don't carry Tanglu changes)
if test "x$CLEANUP_DEVEL" = xyes; then
  $JANITOR -r -s $CURRENT_DEV_SUITE
fi
