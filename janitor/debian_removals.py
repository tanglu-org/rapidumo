#!/usr/bin/python
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

import os
from apt_pkg import TagFile, TagSection
import urllib2

class PackageRemovalItem():
    def __init__(self, suite, pkgname, version, reason):
        self.pkgname = pkgname
        self.version = version
        self.suite = suite
        self.reason = reason

class DebianRemovals:
    def __init__(self):
        # fetch a list of removed packages from Debian
        response = urllib2.urlopen('http://ftp-master.debian.org/removals.822')
        self._removalsRFC822 = response

    def _get_version_from_pkid(self, pkid):
        s = pkid[::-1]
        s = s[:s.index("_")]

        return s[::-1]

    def _get_pkgname_from_pkid(self, pkid):
        s = pkid[:pkid.index("_")]

        return s

    def get_removed_sources(self):
        tagf = TagFile (self._removalsRFC822)
        resultsList = []
        for section in tagf:
            suite = section.get('Suite', '').strip()
            sources_raw = section.get('Sources', '')
            # check if we have a source removal - the only thing of interest for us, at time
            if sources_raw == '' or suite == '':
                continue
            source_ids = [x.strip() for x in sources_raw.split('\n')]
            reason = section['Reason']
            for source_id in source_ids:
                if not "_" in source_id:
                    continue
                version = self._get_version_from_pkid(source_id)
                source = self._get_pkgname_from_pkid(source_id)
                pkgrm = PackageRemovalItem(suite, source, version, reason)
                resultsList.append(pkgrm)
        return resultsList
