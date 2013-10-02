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
import shutil
from update_source import bump_source_version
from apt_pkg import TagFile, TagSection
from optparse import OptionParser
from synctool.pkginfo import *
from ConfigParser import SafeConfigParser

#REPO_POOL ="http://archive.tanglu.org/tanglu/pool"
REPO_POOL = "file:///srv/dak/ftp/pool"

class Autorebuild():
    def __init__(suite):
        parser = SafeConfigParser()
        parser.read(['/srv/dak/sync-debian.conf', 'sync-debian.conf'])
        self._ArchivePath = parser.get('Archive', 'path')
        _dest_distro = parser.get('SyncTarget', 'distro_name')
        extra_suite = parser.get('SyncTarget', 'devel_suite')
        if suite == extra_suite:
            suite = "staging"
        else:
            extra_suite = ""

        pkginfo_tgl = PackageInfoRetriever(self._ArchivePath, _dest_distro, suite)
        pkginfo_tgl.extra_suite = extra_suite
        # we only care about packages in main right now
        self._pkgs_tanglu = pkginfo_tgl.get_packages_dict("main")
        self._suite = suite

        # make sure workspace is empty...
        if os.path.exists("/tmp/arb-workspace"):
            shutil.rmtree("/tmp/arb-workspace")

    def _download_pkg_to_workspace(self, workspace, suite, component, pkgname, version):
        os.chdir(workspace)

        if pkgname.startswith("lib"):
            short_sec = pkgname[0:4]
        else:
            short_sec = pkgname[0:1]
        url = "%s/%s/%s/%s/%s_%s.dsc" % (REPO_POOL, component, short_sec, pkgname, pkgname, noEpoch(version))
        dget_cmd = ["dget", "-duq", url]
        proc = subprocess.Popen(dget_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        output = ("%s\n%s") % (stdout, stderr)
        if (proc.returncode != 0):
            print(output)
            return False
        return True

    def trigger_package_rebuild(self, component, pkgname, build_note):
        workspace = os.path.abspath("/tmp/arb-workspace/%s" % (pkgname))
        if not os.path.exists(workspace):
            os.makedirs(workspace)
        packages = self._pkgs_tanglu
        ret = self._download_pkg_to_workspace(workspace, self._suite, component, pkgname, packages[pkgname].version)
        if not ret:
            print("Download of package '%s' failed." % (pkgname))
            return False
        ret, dsc_path = bump_source_version(workspace, pkgname, build_note)
        if not ret:
            print("Unable to bump version of source package '%s'. It might need a manual upload." % (pkgname))
            return False

        # now make the package known to dak
        cmd = ["dak", "import", "-s", "-a", "staging", component, dsc_path]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        if p.returncode is not 0:
            stdout, stderr = p.communicate()
            print("ERR: %s\n%s %s" % (cmd, stdout, stderr))
            raise Exception("Error while running dak!")
            return False

        shutil.rmtree(workspace)
        print("Triggered rebuild for '%s'." % (pkgname))

        return True

    def batch_rebuild_packages(self, component, bad_depends, build_note, dry_run=True):
        source_path = self._ArchivePath + "%s/dists/%s/%s/binary-i386/Packages.gz" % ("tanglu", self._suite, component)
        f = gzip.open(source_path, 'rb')
        tagf = TagFile (f)
        rebuildSources = []
        bad_depends = bad_depends.strip()
        for section in tagf:
            pkgname = section['Package']
            source_pkg = section.get('Source', '')
            if source_pkg == '':
                source_pkg = pkgname
            if source_pkg in processedSources:
                continue # we already handled a rebuild for that

            depends = section.get('Depends', '')
            # we ignore pre-depends: Pre-depending stuff is much safer with a manual rebuild
            dep_chunks = depends.split(',')
            for dep in dep_chunks:
                dep = dep.strip()
                if dep.startswith(bad_depends):
                    if dep == bad_depends:
                        rebuildSources.append(source_pkg)
                        continue
                    if '(' not in dep:
                        continue
                    depid_parts = dep.split('(')
                    if bad_depends == depid_parts[0].strip():
                        rebuildSources.append(source_pkg)
                        continue

            print("Packages planned for rebuild:")
            if len(rebuildSources) == 0:
                print("No matching packages found.")
                return
            print(rebuildSources.join('\n'))

            if dry_run:
                return # dry-run - nothing to do

def main():
    # init Apt, we need it later
    apt_pkg.init()

    parser = OptionParser()
    parser.add_option("-r",
                  action="store_true", dest="rebuild", default=False,
                  help="rebuild package")
    parser.add_option("-b",
                  action="store_true", dest="rebuild_batch", default=False,
                  help="batch-rebuild multiple packages")
    parser.add_option("-n",
                  type="string", dest="build_note", default="",
                  help="set note for this rebuild")

    (options, args) = parser.parse_args()

    if options.rebuild:
        if len(args) != 3:
            print("Invalid number of arguments (need source-suite, component, (bad) package-name)")
            sys.exit(1)
        suite = args[0]
        component = args[1]
        package_name = args[2]

        build_note = options.build_note
        if build_note == "":
            print("No build-note set! Please specify a rebuild reason (e.g. 'perl-5.18')")
            sys.exit(1)
        rebuilder = Autorebuild(suite)

        ret = False
        if options.rebuild_batch:
            ret = rebuilder.batch_rebuild_packages(component, package_name, build_note)
        else:
            ret = rebuilder.trigger_package_rebuild(component, package_name, build_note)
        if not ret:
            sys.exit(2)
    else:
        print("Run with -h for a list of available command-line options!")

if __name__ == "__main__":
    os.environ['LANG'] = 'C'
    os.environ['LC_ALL'] = 'C'
    main()
