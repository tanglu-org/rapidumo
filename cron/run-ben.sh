#!/bin/sh
set -e

mkdir -p /srv/dak/tmp/ben
cd /srv/dak/tmp/ben

# remove the cache manually - cache invalodation doesn't seem to work
rm -f ben.cache

# just call ben to regenerate the transition tracker data
ben tracker -g /srv/dak/archive-hints/ben/config/global.conf
cd ..
