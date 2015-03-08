#!/bin/sh
# Copyright (C) 2013 Matthias Klumpp <mak@debian.org>
#
# Licensed under the GNU General Public License Version 3
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# This is a small helper tool to syncronize the archive-hints

# Update the blacklist
if [ ! -d /srv/dak/archive-hints ]; then
  git clone https://gitlab.com/tanglu/archive-hints.git /srv/dak/archive-hints
else
  cd /srv/dak/archive-hints/
  git pull --quiet
fi
