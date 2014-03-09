# Copyright (C) 2014 Matthias Klumpp <mak@debian.org>
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

import yaml
from rapidumolib.utils import *

class RapidumoConfig():
    def __init__(self):
        self._conf = yaml.safe_load(open('/srv/dak/tanglu-archive.yml', 'r'))

    @property
    def distro_name(self):
        return self._conf["General"]["distro_name"]

    @property
    def mom_config(self):
        return self._conf["MOM"]

    @property
    def archive_config(self):
        return self._conf["Archive"]

    @property
    def syncsource_config(self):
        return self._conf["SyncSource"]

    @property
    def janitor_config(self):
        return self._conf["Janitor"]

    @property
    def templates_config(self):
        return self._conf["Templates"]

    @property
    def suites_config(self):
        return self._conf["Suites"]

    @property
    def fedmsg_config(self):
        return self._conf["Fedmsg"]

    def get_supported_archs(self, suite):
        for s in self.suites_config:
            if s['name'] == suite:
                return s['archs']
        return None

    def get_supported_components(self, suite):
        for s in self.suites_config:
            if s['name'] == suite:
                return s['components']
        return None
