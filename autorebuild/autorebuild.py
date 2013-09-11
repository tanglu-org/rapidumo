#!/usr/bin/python3
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
from update_source import bump_source_version
from optparse import OptionParser
from pkginfo import *
from configparser import SafeConfigParser

#REPO_POOL ="http://archive.tanglu.org/tanglu/pool"
REPO_POOL = "file:///srv/dak/ftp/pool"

def get_package_lists():
    parser = SafeConfigParser()
    parser.read(['/srv/dak/sync-debian.conf', 'sync-debian.conf'])
    _momArchivePath = parser.get('MOM', 'path')
    _dest_distro = parser.get('SyncTarget', 'distro_name')
    _extra_suite = parser.get('SyncTarget', 'devel_suite')

    pkginfo_tgl = PackageInfoRetriever(_momArchivePath, _dest_distro, "staging")
    pkginfo_tgl.extra_suite = _extra_suite
    # we only care about packages in main right now
    pkgs_tanglu = pkginfo_tgl.get_packages_dict("main")

    return pkgs_tanglu

def download_pkg_to_workspace(workspace, suite, component, pkgname, version):
    os.chdir(workspace)

    if pkgname.startswith("lib"):
        short_sec = pkgname[0:4]
    else:
        short_sec = pkgname[0:1]
    url = "%s/%s/%s/%s/%s_%s.dsc" % (REPO_POOL, component, short_sec, pkgname, pkgname, version)
    dget_cmd = ["dget", "-duq", url]
    proc = subprocess.Popen(dget_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    output = ("%s\n%s") % (stdout, stderr)
    if (proc.returncode != 0):
        print(output)
        return False
    return True

def trigger_package_rebuild(suite, component, pkgname, build_note):
    workspace = os.path.abspath("/tmp/arb-workspace/%s" % (pkgname))
    if not os.path.exists(workspace):
        os.makedirs(workspace)
    packages = get_package_lists()
    ret = download_pkg_to_workspace(workspace, suite, component, pkgname, packages[pkgname].version)
    if not ret:
        print("Download of package '%s' failed." % (pkgname))
        return False
    ret = bump_source_version(workspace, pkgname, build_note)
    if not ret:
        print("Unable to bump version of source package '%s'. It might need a manual upload." % (pkgname))
        return False
    return True

def main():
    # init Apt, we need it later
    apt_pkg.init()

    parser = OptionParser()
    parser.add_option("-r",
                  action="store_true", dest="rebuild", default=False,
                  help="rebuild package")
    parser.add_option("-n",
                  type="string", dest="build_note", default="",
                  help="set note for this rebuild")

    (options, args) = parser.parse_args()

    if options.rebuild:
        if len(args) != 3:
            print("Invalid number of arguments (need source-suite, component, package-name)")
            sys.exit(1)
        suite = args[0]
        component = args[1]
        package_name = args[2]
        build_note = options.build_note
        if build_note == "":
            print("No build-note set! Please specify a rebuild reason (e.g. 'perl-5.18')")
            sys.exit(1)
        ret = trigger_package_rebuild(suite, component, package_name, build_note, version)
        if not ret:
            sys.exit(2)
    else:
        print("Run with -h for a list of available command-line options!")

if __name__ == "__main__":
    os.environ['LANG'] = 'C'
    os.environ['LC_ALL'] = 'C'
    main()
