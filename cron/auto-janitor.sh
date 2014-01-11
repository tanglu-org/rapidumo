# perform some janitor tasks automatically
#!/bin/bash
set -e

# import the global variable set.
. /var/archive-kit/rapidumo/cron/vars

JANITOR=$RAPIDUMO_PATH/janitor/janitor.py

python $JANITOR -r -s staging --use-dak
