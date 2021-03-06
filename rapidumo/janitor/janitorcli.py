#!/usr/bin/python
# Copyright (C) 2013-2014 Matthias Klumpp <mak@debian.org>
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

from ..pkginfo import *
from ..utils import *
from ..config import *
from .janitor_utils import *
from .debian_removals import DebianRemovals
from .installability_test import JanitorDebcheck


class Janitor:
    def __init__(self, suite = ""):
        conf = RapidumoConfig()
        self._current_suite = suite
        if not self._current_suite:
            self._current_suite = conf.archive_config['devel_suite']
        self._distro_name = conf.distro_name
        self._staging_suite = conf.archive_config['staging_suite']
        self._archive_path = conf.archive_config['path']
        base_suite = conf.get_base_suite(self._current_suite)
        self._supportedArchs = conf.get_supported_archs(base_suite).split(" ")

        self._hints_file = conf.janitor_config['hints_file']

        pkginfo = SourcePackageInfoRetriever(self._archive_path, self._distro_name, self._current_suite)
        self._source_pkgs_full = pkginfo.get_packages_dict("non-free")
        self._source_pkgs_full.update(pkginfo.get_packages_dict("contrib"))
        self._source_pkgs_full.update(pkginfo.get_packages_dict("main"))

        self.dryrun = False
        self.quiet = False
        self.rmuninstallable = False

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
                    # check for Tanglu autorebuilds (and don't count them when comparing versions)
                    p = re.compile(r"(.*)b\d$")
                    m = p.match(pkg_item.version)
                    if m == None:
                        version_norebuild = pkg_item.version
                    else:
                        version_norebuild = m.group(1)
                    if apt_pkg.version_compare(version_norebuild, rmitem.version) > 0:
                        # the version in Tanglu is newer, we don't want to delete the package
                        continue
                    tglpkgrm = PackageRemovalItem(self._current_suite, pkg_item.pkgname, pkg_item.version, rmitem.reason)
                    cruftList.append(tglpkgrm)
        return cruftList

    def _get_uninstallable_cruft(self):
        dcheck = JanitorDebcheck()
        return dcheck.get_uninstallable_removals(self._current_suite, self._supportedArchs)

    def _print_removals_list(self, removals_list):
        for rmitem in removals_list:
            print("----")
            print(rmitem.suite)
            print(rmitem.pkgname + " - " + rmitem.version)
            print("-")
            print(rmitem.reason)

    def remove_cruft(self, dak_mode=False):
        removals_list = self._get_debcruft()
        if self.rmuninstallable:
            removals_list.extend(self._get_uninstallable_cruft())
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
                    f.write("\n# %s\n" % (rmitem.reason.replace('\n', "\n#")))
                # create a Britney remove-hint
                f.write("remove %s/%s\n" % (rmitem.pkgname, rmitem.version))
                if rmitem.suite == self._staging_suite:
                    print("Attention! Wrote a britney-hint on the staging suite (package: %s/%s). That might not be what you wanted." % (rmitem.pkgname, rmitem.version))
            f.close()
        else:
            for rmitem in removals_list:
                cmd = ["dak", "rm", "-s", rmitem.suite, "-m", rmitem.reason, "-C", "ftpmaster@ftp-master.tanglu.org", rmitem.pkgname]
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                p.communicate(input=b'y\n')
                p.wait()
                if p.returncode is not 0:
                    stdout, stderr = p.communicate()
                    raise Exception("Error while running dak!\n----\n%s\n%s %s" % (cmd, stdout, stderr))
                    return False
                if not self.quiet:
                    print("Removed: %s/%s" % (rmitem.pkgname, rmitem.version))
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
    parser.add_option("--rm-uninstallable",
                  action="store_true", dest="rm_uninst", default=False,
                  help="remove source-packages which have binary packages with broken dependencies (use with care!)")
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
        janitor.quiet = options.quiet
        janitor.rmuninstallable = options.rm_uninst
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
