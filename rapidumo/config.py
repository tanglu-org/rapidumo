#!/usr/bin/env python3
#
# Copyright (C) 2014 Matthias Klumpp <mak@debian.org>
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
import os


class RapidumoConfig():
    def __init__(self):
        self._conf = yaml.safe_load(open('/srv/dak/tanglu-archive.yml', 'r'))

        self.debug_enabled = False
        if 'DEBUG' in os.environ:
            self.debug_enabled = True

    @property
    def distro_name(self):
        return self._conf["General"]["distro_name"]

    @property
    def general_config(self):
        return self._conf["General"]

    @property
    def archive_config(self):
        return self._conf["Archive"]

    @property
    def synchrotron_config(self):
        return self._conf["Synchrotron"]

    @property
    def syncsource_config(self):
        return self.synchrotron_config["sync_source"]

    @property
    def janitor_config(self):
        return self._conf["Janitor"]

    @property
    def suites_config(self):
        return self._conf["Suites"]

    @property
    def fedmsg_config(self):
        return self._conf["Fedmsg"]

    def get_base_suite(self, suite_name):
        base_suite, _, apnd = suite_name.partition('-')
        if base_suite == 'buildq':
            base_suite = apnd
        return base_suite

    def get_build_queue(self, suite_name):
        sdict = None
        for s in self.suites_config:
            if s['name'] == suite_name:
                sdict = s
        if not sdict:
            return None

        bqueue = sdict.get('incoming_queue')
        return bqueue

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
