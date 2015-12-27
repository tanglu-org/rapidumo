#!/usr/bin/python3
# Copyright (C) 2015 Matthias Klumpp <mak@debian.org>
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

import sys
import time
from .. import RapidumoConfig, SourcePackageInfoRetriever
from ..utils import render_template


class CruftReport:

    def __init__(self):
        self._conf = RapidumoConfig()
        self._debian_mirror = self._conf.synchrotron_config['debian_mirror']
        self._pkgs_mirror = self._conf.general_config['packages_mirror']
        self._devel_suite = self._conf.archive_config['devel_suite']
        self._staging_suite = self._conf.archive_config['staging_suite']
        self._sync_enabled = self._conf.synchrotron_config['sync_enabled']

        debian_suite = self._conf.syncsource_config['suite']
        pkginfo_src = SourcePackageInfoRetriever(self._debian_mirror, "", debian_suite)
        self._pkgs_src = dict()
        for component in ['main', 'contrib', 'non-free']:
            self._pkgs_src.update(pkginfo_src.get_packages_dict(component))

    def _get_packages_not_in_debian(self, target_suite):
        pkginfo_dest = SourcePackageInfoRetriever(self._pkgs_mirror, self._conf.distro_name, target_suite)
        pkgs_dest = dict()
        for component in self._conf.get_supported_components(target_suite).split(' '):
            pkgs_dest.update(pkginfo_dest.get_packages_dict(component))

        debian_pkg_list = list(self._pkgs_src.keys())
        removed_pkgs = list()

        for pkgname in pkgs_dest.keys():
            if pkgname in debian_pkg_list:
                continue
            else:
                removed_pkgs.append(pkgs_dest[pkgname])

        # we don't want Tanglu-only packages to be listed here
        for pkg in removed_pkgs[:]:
            if ("-0tanglu" in pkg.version) or ("tanglu" in pkg.pkgname):
                removed_pkgs.remove(pkg)
                continue

        return removed_pkgs

    def update(self, quiet=False):
        def pkg_rmlist_to_templatelist(rmlist, dak_cmds=True):
            rm_items = list()
            for pkg in rmlist:
                item = dict()
                item['name'] = pkg.pkgname
                item['debian_pts'] = "https://tracker.debian.org/pkg/%s" % (pkg.pkgname)
                item['tanglu_tracker'] = "http://packages.tanglu.org/%s" % (pkg.pkgname)

                item['tanglu_changes'] = False
                if "tanglu" in pkg.version:
                    item['tanglu_changes'] = True
                if dak_cmds:
                    item['remove_hint'] = "dak rm -m \"[auto-cruft] RID (removed in Debian and unmaintained)\" -s %s -R %s" % (self._staging_suite, pkg.pkgname)
                else:
                    item['remove_hint'] = "remove %s/%s" % (pkg.pkgname, pkg.version)
                rm_items.append(item)
                if not quiet:
                    print(item['remove_hint'])
            return rm_items


        rmlist_devel = self._get_packages_not_in_debian(self._devel_suite)
        rm_items_devel = pkg_rmlist_to_templatelist(rmlist_devel, False)

        rmlist_staging = self._get_packages_not_in_debian(self._staging_suite)
        rm_items_staging = pkg_rmlist_to_templatelist(rmlist_devel)


        render_template("synchrotron/cruft-report.html", "synchrotron/cruft-report.html",
                section_label="synchrotron-cruft", rmitems_devel=rm_items_devel, rmitems_staging=rm_items_staging,
                devel_suite=self._devel_suite, staging_suite=self._staging_suite, time=time.strftime("%c"),
                import_freeze=not self._sync_enabled)
