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
import sys
import apt_pkg
import subprocess
import re
from optparse import OptionParser

from rapidumolib.pkginfo import *
from rapidumolib.utils import *
from debian_removals import DebianRemovals, PackageRemovalItem

class Janitor:
    def __init__(self, suite = ""):
        parser = SafeConfigParser()
        parser.read(['/srv/dak/tanglu-archive.conf', 'tanglu-archive.conf'])
        self._devel_suite = suite
        if self._devel_suite == "":
            self._devel_suite = parser.get('Archive', 'devel_suite')
        self._distro_name = parser.get('General', 'distro_name')
        self._staging_suite = parser.get('Archive', 'staging_suite')
        self._archive_path = parser.get('Archive', 'path')

        self._supportedArchs = parser.get('Archive', 'archs').split (" ")
        self._unsupportedArchs = parser.get('SyncSource', 'archs').split (" ")
        for arch in self._supportedArchs:
            self._unsupportedArchs.remove(arch)
        pkginfo = PackageInfoRetriever(self._archive_path, self._distro_name, self._devel_suite)
        pkginfo.extra_suite = self._staging_suite
        self._source_pkgs_full = pkginfo.get_packages_dict("non-free")
        self._source_pkgs_full.update(pkginfo.get_packages_dict("contrib"))
        self._source_pkgs_full.update(pkginfo.get_packages_dict("main"))

    def _get_debcruft(self):
        debrm = DebianRemovals()
        debrm_list = debrm.get_removed_sources()
        cruftList = list()
        for rmitem in debrm_list:
            # we don't care about experimental
            if rmitem.suite == "experimental":
                continue
            if rmitem.pkgname in self._source_pkgs_full:
                pkg_item = self._source_pkgs_full[rmitem.pkgname]
                # the package is in Tanglu, check if it contains Tanglu changes.
                # if it does, we skip it here, else it apparently is cruft
                if not self._distro_name in pkg_item.version:
                    tglpkgrm = PackageRemovalItem(self._devel_suite, pkg_item.pkgname, pkg_item.version, rmitem.reason)
                    cruftList.append(tglpkgrm)
        return cruftList

    def remove_cruft(self):
        removals_list = self._get_debcruft()
        for rmitem in removals_list:
            print("----")
            print(rmitem.suite)
            print(rmitem.pkgnames)
            print(rmitem.reason)
        return True

def main():
    # init Apt, we need it later
    apt_pkg.init()

    parser = OptionParser()
    parser.add_option("-r", "--cruft-remove",
                  action="store_true", dest="cruft_remove", default=False,
                  help="remove cruft from the archive")
    parser.add_option("-s",
                  type="string", dest="suite", default="",
                  help="suite to operate on")
    parser.add_option("--dry",
                  action="store_true", dest="dry_run", default=False,
                  help="list all packages which would be synced")
    parser.add_option("--quiet",
                  action="store_true", dest="quiet", default=False,
                  help="don't show output (except for errors)")

    (options, args) = parser.parse_args()

    if options.cruft_remove:
        janitor = Janitor(options.suite)
        ret = False
        ret = janitor.remove_cruft()
        if not ret:
            sys.exit(2)
    else:
        print("Run with --help for a list of available command-line options!")

if __name__ == "__main__":
    os.environ['LANG'] = 'C'
    os.environ['LC_ALL'] = 'C'
    main()
