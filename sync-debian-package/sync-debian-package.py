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
from optparse import OptionParser

from pkginfo import *

class SyncPackage:
    def __init__(self):
        self.debugMode = False

        parser = SafeConfigParser()
        parser.read(['/srv/dak/sync-debian.conf', 'sync-debian.conf'])
        self._momArchivePath = parser.get('MOM', 'path')
        self._destDistro = parser.get('SyncTarget', 'distro_name')

        self._supportedArchs = parser.get('SyncTarget', 'archs').split (" ")
        self._unsupportedArchs = parser.get('SyncSource', 'archs').split (" ")
        for arch in self._supportedArchs:
            self._unsupportedArchs.remove(arch)

    def initialize(self, source_suite, target_suite, component):
        self._sourceSuite = source_suite
        self._component = component
        self._target_suite = target_suite
        pkginfo_src = PackageInfoRetriever(self._momArchivePath, "debian", source_suite)
        pkginfo_dest = PackageInfoRetriever(self._momArchivePath, self._destDistro, target_suite)
        self._pkgs_src = pkginfo_src.get_packages_dict(component)
        self._pkgs_dest = pkginfo_dest.get_packages_dict(component)
        self._pkg_blacklist = self._read_blacklist()

    def _read_blacklist(self):
        filename = "%s/sync-blacklist.txt" % self._momArchivePath
        if not os.path.isfile(filename):
            return []

        bl = []
        with open(filename) as blacklist:
            for line in blacklist:
                try:
                    line = line[:line.index("#")]
                except ValueError:
                    pass

                line = line.strip()
                if not line:
                    continue

                bl.append(line)
        return bl

    def _import_debian_package(self, pkg):
        print("Attempt to import package: %s" % (pkg))
        # adjust the pkg-dir (we need to remove pool/main, pool/non-free etc. from the string)
        pkg_dir = pkg.directory
        if pkg_dir.startswith("pool"):
            pkg_dir = pkg_dir[pkg_dir.index("/")+1:]
            pkg_dir = pkg_dir[pkg_dir.index("/")+1:]
        pkg_path = self._momArchivePath + "/pool/debian/" + pkg_dir + "/%s_%s.dsc" % (pkg.pkgname, pkg.getVersionNoEpoch())
        print("(Import path: %s)" % (pkg_path))

        cmd = ["dak", "import", "-s", "-a", self._target_suite, self._component, pkg_path]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        if p.returncode is not 0:
            stdout, stderr = p.communicate()
            print("ERR: %s\n%s %s" % (cmd, stdout, stderr))
            raise Exception("Error while running dak!")
            return False

        return True

    def _can_sync_package(self, src_pkg, dest_pkg, quiet=False, forceSync=False):
        if src_pkg.pkgname in self._pkg_blacklist:
            if not quiet:
                print("Package %s is on package-blacklist and cannot be synced!" % (src_pkg.pkgname))
            return False
        # check if the package is arch-only for an unsupported arch
        if " " in src_pkg.archs:
            archs = src_pkg.archs.split(" ")
        else:
            archs = [src_pkg.archs]
        supported = False
        for arch in self._supportedArchs:
                if ('any' in archs) or ('linux-any' in archs) or (("any-"+arch) in archs) or (arch in archs):
                    supported = True
        if ("all" in archs):
                supported = True
        if not supported:
                if not quiet:
                    print("Package %s is designed for unsupported architectures and cannot be synced (only for %s).!" % (src_pkg.pkgname, archs))
                return False
        if dest_pkg == None:
            return True

        compare = version_compare(dest_pkg.version, src_pkg.version)
        if compare >= 0:
            if not quiet:
                print("Package %s has a newer/equal version in the target distro. (Version in target: %s, source is %s)" % (dest_pkg.pkgname, dest_pkg.version, src_pkg.version))
            return False

        if (self._destDistro in dest_pkg.version) and (not forceSync):
            print("Package %s contains Tanglu-specific modifications. Please merge the package instead of syncing it. (Version in target: %s, source is %s)" % (dest_pkg.pkgname, dest_pkg.version, src_pkg.version))
            return False

        return True

    def sync_package(self, package_name, force=False):
        if not package_name in self._pkgs_src:
            print("Cannot sync %s, package doesn't exist in Debian (%s/%s)!" % (package_name, self._sourceSuite, self._component))
            return False
        src_pkg = self._pkgs_src[package_name]

        if not package_name in self._pkgs_dest:
            ret = False
            if self._can_sync_package(src_pkg, None):
                ret = self._import_debian_package(src_pkg)
            return ret

        dest_pkg = self._pkgs_dest[package_name]

        if not self._can_sync_package(src_pkg, dest_pkg, forceSync=force):
            return False

        # we can now sync the package
        ret = self._import_debian_package(src_pkg)
        return ret

    def sync_all_packages(self):
        for src_pkg in self._pkgs_src.values():
            if not src_pkg.pkgname in self._pkgs_dest:
                if self._can_sync_package(src_pkg, None, True):
                    self._import_debian_package(src_pkg)
                continue
            if self._can_sync_package(src_pkg, self._pkgs_dest[src_pkg.pkgname], True):
                self._import_debian_package(src_pkg)

    def list_all_syncs(self):
        for src_pkg in self._pkgs_src.values():
            if not src_pkg.pkgname in self._pkgs_dest:
                if self._can_sync_package(src_pkg, None, True):
                    print("Sync: %s" % (src_pkg))
                continue
            if self._can_sync_package(src_pkg, self._pkgs_dest[src_pkg.pkgname], True):
                print("Sync: %s" % (src_pkg))

    def list_not_in_debian(self):
        debian_pkg_list = self._pkgs_src.values()
        dest_pkg_list = self._pkgs_dest.keys()
        for src_pkg in debian_pkg_list:
            pkgname = src_pkg.pkgname
            if pkgname in dest_pkg_list:
                dest_pkg_list.remove(pkgname)
                continue
        for pkgname in dest_pkg_list:
            print(pkgname)

def main():
    # init Apt, we need it later
    apt_pkg.init()

    parser = OptionParser()
    parser.add_option("-i",
                  action="store_true", dest="import_pkg", default=False,
                  help="import a package")
    parser.add_option("--force",
                  action="store_true", dest="force_import", default=False,
                  help="enforce the import of a package")
    parser.add_option("-a", "--import-all",
                  action="store_true", dest="sync_everything", default=False,
                  help="sync all packages with newer versions")
    parser.add_option("-l", "--list-syncs",
                  action="store_true", dest="list_syncs", default=False,
                  help="list all packages which would be synced")
    parser.add_option("--list-not-in-debian",
                  action="store_true", dest="list_nodebian", default=False,
                  help="show a list of packages which are not in Debian")

    (options, args) = parser.parse_args()

    if options.import_pkg:
        sync = SyncPackage()
        if len(args) != 4:
            print("Invalid number of arguments (need source-suite, target-suite, component, package-name)")
            sys.exit(1)
        source_suite = args[0]
        target_suite = args[1]
        component = args[2]
        package_name = args[3]
        sync.initialize(source_suite, target_suite, component)
        ret = sync.sync_package(package_name, force=options.force_import)
        if not ret:
            sys.exit(2)
    elif options.sync_everything:
        sync = SyncPackage()
        if len(args) != 3:
            print("Invalid number of arguments (need source-suite, target-suite, component)")
            sys.exit(1)
        source_suite = args[0]
        target_suite = args[1]
        component = args[2]
        sync.initialize(source_suite, target_suite, component)
        sync.sync_all_packages()
    elif options.list_syncs:
        sync = SyncPackage()
        if len(args) != 3:
            print("Invalid number of arguments (need source-suite, target-suite, component)")
            sys.exit(1)
        source_suite = args[0]
        target_suite = args[1]
        component = args[2]
        sync.initialize(source_suite, target_suite, component)
        sync.list_all_syncs()
    elif options.list_nodebian:
        sync = SyncPackage()
        if len(args) != 3:
            print("Invalid number of arguments (need debian-suite, distro-suite, component)")
            sys.exit(1)
        source_suite = args[0]
        target_suite = args[1]
        component = args[2]
        sync.initialize(source_suite, target_suite, component)
        sync.list_not_in_debian()
    else:
        print("Run with -h for a list of available command-line options!")

if __name__ == "__main__":
    os.environ['LANG'] = 'C'
    os.environ['LC_ALL'] = 'C'
    main()
