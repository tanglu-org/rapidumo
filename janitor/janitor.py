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
        self._current_suite = suite
        if self._current_suite == "":
            self._current_suite = parser.get('Archive', 'devel_suite')
        self._distro_name = parser.get('General', 'distro_name')
        self._staging_suite = parser.get('Archive', 'staging_suite')
        self._archive_path = parser.get('Archive', 'path')

        self._hints_file = parser.get('Janitor', 'hints_file')

        pkginfo = PackageInfoRetriever(self._archive_path, self._distro_name, self._current_suite)
        self._source_pkgs_full = pkginfo.get_packages_dict("non-free")
        self._source_pkgs_full.update(pkginfo.get_packages_dict("contrib"))
        self._source_pkgs_full.update(pkginfo.get_packages_dict("main"))
        self.dryrun = False

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
                    tglpkgrm = PackageRemovalItem(self._current_suite, pkg_item.pkgname, pkg_item.version, rmitem.reason)
                    cruftList.append(tglpkgrm)
        return cruftList

    def _print_removals_list(self, removals_list):
        for rmitem in removals_list:
            print("----")
            print(rmitem.suite)
            print(rmitem.pkgname + " - " + rmitem.version)
            print(rmitem.reason)

    def remove_cruft(self, dak_mode=False):
        removals_list = self._get_debcruft()
        if self.dryrun:
            self._print_removals_list(removals_list)
            print("#")
            print("End of dry-run. Packages flagged for removal are shown above.")
            return True
        if not dak_mode:
            f = open(self._hints_file, 'w')
            f.write('##\n# Hints file for the Tanglu Archive Janitor\n##\n')
            last_reason = ""
            for rmitem in removals_list:
                if rmitem.reason != last_reason:
                    last_reason = rmitem.reason
                    f.write("\n# %s\n" % (rmitem.reason))
                # create a Britney remove-hint
                f.write("remove %s/%s\n" % (rmitem.pkgname, rmitem.version))
                if rmitem.suite == self._staging_suite:
                    print("Attention! Wrote a britney-hint on the staging suite (package: %s/%s). That might not be what you wanted." % (rmitem.pkgname, rmitem.version))
            f.close()
        else:
            for rmitem in removals_list:
                cmd = ["dak", "rm", "-s", rmitem.suite, "-m", rmitem.reason, "-C", "ftpmaster@ftp-master.tanglu.org", rmitem.pkgname]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                p.wait()
                if p.returncode is not 0:
                    stdout, stderr = p.communicate()
                    raise Exception("Error while running dak!\n----\n%s\n%s %s" % (cmd, stdout, stderr))
                    return False
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
    parser.add_option("--use-dak",
                  action="store_true", dest="use_dak", default=False,
                  help="call dak to remove packages, instead of writing a britney hints file")
    parser.add_option("--dry",
                  action="store_true", dest="dry_run", default=False,
                  help="list all packages which would be synced")
    parser.add_option("--quiet",
                  action="store_true", dest="quiet", default=False,
                  help="don't show output (except for errors)")

    (options, args) = parser.parse_args()

    if options.cruft_remove:
        janitor = Janitor(options.suite)
        janitor.dryrun = options.dry_run
        ret = False
        ret = janitor.remove_cruft(options.use_dak)
        if not ret:
            sys.exit(2)
    else:
        print("Run with --help for a list of available command-line options!")

if __name__ == "__main__":
    os.environ['LANG'] = 'C'
    os.environ['LC_ALL'] = 'C'
    main()
