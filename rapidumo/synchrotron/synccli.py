#!/usr/bin/python
# Copyright (C) 2013-2015 Matthias Klumpp <mak@debian.org>
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
import time
import yaml
import glob
from optparse import OptionParser

from .. import RapidumoConfig
from ..pkginfo import *
from ..utils import render_template, read_commented_listfile
from ..messaging import *
from .debian_mirror import DebianMirror
from .cruft_report import CruftReport

def emit(modname, topic, message):
    emit_raw("synchrotron", modname, topic, message)

class SyncPackage:
    def __init__(self):
        self.dry_run = False

        self._conf = RapidumoConfig()
        self._debian_mirror = self._conf.synchrotron_config['debian_mirror']
        self._pkgs_mirror = self._conf.general_config['packages_mirror']
        self._dest_distro = self._conf.distro_name

        staging_suite = self._conf.archive_config['staging_suite']
        self._supported_archs = self._conf.get_supported_archs(staging_suite).split (" ")
        self._unsupported_archs = self._conf.syncsource_config['archs'].split (" ")
        self._sync_enabled = self._conf.synchrotron_config['sync_enabled']
        self._synchints_root = self._conf.synchrotron_config.get('synchints_root')
        self._debcheck_before_sync = self._conf.synchrotron_config.get('debcheck_before_sync')

        for arch in self._supported_archs:
            self._unsupported_archs.remove(arch)

    def initialize(self, source_suite, target_suite, component):
        self._sourceSuite = source_suite
        self._component = component
        self._target_suite = target_suite

        pkginfo_dest = SourcePackageInfoRetriever(self._pkgs_mirror, self._dest_distro, target_suite)
        self._pkgs_dest = pkginfo_dest.get_packages_dict(component)
        self._pkg_blacklist = read_commented_listfile("%s/sync-blacklist.txt" % self._synchints_root)
        self._pkg_autosync_overrides = dict()
        self._pkg_sets_dir = None
        if self._synchints_root:
            autosync_dir = os.path.join(self._synchints_root, "autosync")
            self._pkg_sets_dir = os.path.join(self._synchints_root, "sets")
            self._pkg_autosync_overrides = self._load_syncset_data(autosync_dir)

        # load Debian suite data
        self._pkgs_src = dict()
        self.bcheck_data = dict()
        suites = ["experimental", "unstable", "testing"]
        if source_suite not in suites:
            suites.append(source_suite)
        for suite in suites:
            pkginfo_src = SourcePackageInfoRetriever(self._debian_mirror, "", source_suite)
            self._pkgs_src[suite] = pkginfo_src.get_packages_dict(component)

            # don't load debcheck data if we are not supposed to use it later
            if not self._debcheck_before_sync:
                self.bcheck_data[suite] = None
                continue

            # determine if the to-be-synced packages are buildable
            bcheck = BuildCheck(self._conf)
            ydata = bcheck.get_package_states_yaml_sources(target_suite, component, "amd64",
                            self._debian_mirror + "/dists/%s/%s/source/Sources.gz" % (suite, component))
            self.bcheck_data[suite] = yaml.safe_load(ydata)['report']

    def _load_pkgset_file(self, fname):
        hints = dict()
        with open(fname) as slist:
            for line in slist:
                try:
                    line = line[:line.index("#")]
                except ValueError:
                    pass

                line = line.strip()
                if not line:
                    continue
                # sync lines are in the format <suite>/<srcpkg>, for
                # example "experimental/packagekit"
                parts = line.split('/', 1);
                hints[parts[1]] = parts[0]
        return hints

    def _load_syncset_data(self, directory):
        hints = dict()
        for fname in os.listdir(directory):
            fname = os.path.join(directory, fname)
            if fname.endswith(".list"):
                h = self._load_pkgset_file(fname)
                hints.update(h)

        return hints


    def _get_package_depwait_report(self, pkg):
        if not self.bcheck_data[self._sourceSuite]:
            return None

        for nbpkg in self.bcheck_data[self._sourceSuite]:
            if (nbpkg['package'] == ("src:" + pkg.pkgname) and (nbpkg['version'] == pkg.version)):
                return nbpkg
        return None

    def _import_debian_package(self, pkg):
        print("Attempt to import package: %s (%s)" % (pkg, pkg.getVersionNoEpoch()))
        # make 100% sure that we never import any package by accident in dry-run mode
        if self.dry_run:
            return
        # adjust the pkg-dir (we need to remove pool/main, pool/non-free etc. from the string)
        pkg_dir = pkg.directory
        if pkg_dir.startswith("pool"):
            pkg_dir = pkg_dir[pkg_dir.index("/")+1:]
            pkg_dir = pkg_dir[pkg_dir.index("/")+1:]
        pkg_path = self._debian_mirror + "/pool/%s/%s/%s_%s.dsc" % (pkg.component, pkg_dir, pkg.pkgname, pkg.getVersionNoEpoch())

        cmd = ["dak", "import", "-s", "-a", self._target_suite, self._component, pkg_path]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        if p.returncode is not 0:
            stdout, stderr = p.communicate()
            print("ERR: %s\n%s %s" % (cmd, stdout, stderr))
            emit("import", "error", "Import of package %s-%s failed!" % (pkg.pkgname, pkg.version))
            raise Exception("Error while running dak!")
            return False
        emit("import", "done", "Synced package %s-%s from Debian." % (pkg.pkgname, pkg.version))

        return True

    def _can_sync_package(self, src_pkg, dest_pkg, quiet=False, forceSync=False):
        if src_pkg.pkgname in self._pkg_blacklist:
            if not quiet:
                print("Package %s is on package-blacklist and cannot be synced!" % (src_pkg.pkgname))
            return False, None
        # check if the package is arch-only for an unsupported arch
        if " " in src_pkg.archs:
            archs = src_pkg.archs.split(" ")
        else:
            archs = [src_pkg.archs]
        supported = False
        for arch in self._supported_archs:
                if ('any' in archs) or ('linux-any' in archs) or (("any-"+arch) in archs) or (arch in archs):
                    supported = True
        if ("all" in archs):
                supported = True
        if not supported:
                if not quiet:
                    print("Package %s is designed for unsupported architectures and cannot be synced (only for %s).!" % (src_pkg.pkgname, archs))
                return False, None
        if dest_pkg == None:
            return True, None

        compare = version_compare(dest_pkg.version, src_pkg.version)
        if compare >= 0:
            if not quiet:
                print("Package %s has a newer/equal version in the target distro. (Version in target: %s, source is %s)" % (dest_pkg.pkgname, dest_pkg.version, src_pkg.version))
            return False, None

        if (self._dest_distro in dest_pkg.version) and (not forceSync):
            print("Package %s contains Tanglu-specific modifications. Please merge the package instead of syncing it. (Version in target: %s, source is %s)" % (dest_pkg.pkgname, dest_pkg.version, src_pkg.version))
            info = dict()
            info['name'] = dest_pkg.pkgname
            info['dest_version'] = dest_pkg.version
            info['src_version'] = src_pkg.version
            info['fail_type'] = "merge-required"
            info['details'] = "Package contains Tanglu-specific modifications. It needs a manual merge."
            return False, info

        report = self._get_package_depwait_report(src_pkg)
        dose_report = None
        if report and report['status'] != "ok":
            dose_report = "Unknown problem"
            for reason in report["reasons"]:
                if "missing" in reason:
                    dose_report = ("Unsat dependency %s" %
                        (reason["missing"]["pkg"]["unsat-dependency"]))
                    break
                elif "conflict" in reason:
                    if reason["conflict"].get("pkg2"):
                        dose_report = ("Conflict between %s and %s" %
                               (reason["conflict"]["pkg1"]["package"],
                               reason["conflict"]["pkg2"]["package"]))
                    else:
                        dose_report = ("Conflict involving %s (%s)" %
                                (reason["conflict"]["pkg1"]["package"],
                                reason["conflict"]["pkg1"]["version"]))
                    break
            dose_report = dose_report.replace("%3a", ":") # compatibility with older dose3 releases

        if dose_report and not forceSync:
            print("Package %s can not be built in Tanglu, it will not be synced: %s" % (dest_pkg.pkgname, dose_report))
            info = dict()
            info['name'] = dest_pkg.pkgname
            info['dest_version'] = dest_pkg.version
            info['src_version'] = src_pkg.version
            info['fail_type'] = "unbuildable"
            info['details'] = dose_report
            return False, info

        return True, None

    def _can_sync_package_simple(self, src_pkg, dest_pkg, quiet=False, forceSync=False):
        ret, sinfo = self._can_sync_package(src_pkg, dest_pkg, quiet, forceSync)
        return ret

    def sync_package(self, package_name, force=False):
        if not package_name in self._pkgs_src[self._sourceSuite]:
            print("Cannot sync %s, package doesn't exist in Debian (%s/%s)!" % (package_name, self._sourceSuite, self._component))
            return False
        src_pkg = self._pkgs_src[self._sourceSuite][package_name]

        if not package_name in self._pkgs_dest:
            ret = False
            if self._can_sync_package_simple(src_pkg, None):
                if self.dry_run:
                    print("Import: %s (%s) [new!]" % (src_pkg.pkgname, src_pkg.version))
                    ret = True
                else:
                    ret = self._import_debian_package(src_pkg)
            return ret

        dest_pkg = self._pkgs_dest[package_name]

        if not self._can_sync_package_simple(src_pkg, dest_pkg, forceSync=force):
            return False

        # we can now sync the package
        dest_pkg = self._pkgs_dest[src_pkg.pkgname]
        if self._can_sync_package_simple(src_pkg, dest_pkg, quiet=True, forceSync=force):
            if self.dry_run:
                print("Import: %s (%s -> %s)" % (src_pkg.pkgname, dest_pkg.version, src_pkg.version))
                ret = True
            else:
                ret = self._import_debian_package(src_pkg)
        return ret

    def sync_packages(self, package_names, force=False):
        success = True
        for pkgname in package_names:
            ret = self.sync_package(pkgname, force)
            if not ret:
                success = False
        return success

    def sync_package_regex(self, package_regex, force=False):
        for src_pkg in self._pkgs_src[self._sourceSuite].values():
            # check if source-package matches regex, if yes, sync package
            if re.match(package_regex, src_pkg.pkgname):
                if not src_pkg.pkgname in self._pkgs_dest:
                    if self._can_sync_package_simple(src_pkg, None, True):
                        if self.dry_run:
                            print("Import: %s (%s) [new!]" % (src_pkg.pkgname, src_pkg.version))
                            ret = True
                        else:
                            self._import_debian_package(src_pkg)
                    continue
                dest_pkg = self._pkgs_dest[src_pkg.pkgname]
                if self._can_sync_package_simple(src_pkg, dest_pkg, quiet=True, forceSync=force):
                    if self.dry_run:
                        print("Import: %s (%s -> %s)" % (src_pkg.pkgname, dest_pkg.version, src_pkg.version))
                        ret = True
                    else:
                        self._import_debian_package(src_pkg)

    def _sync_allowed(self, src_pkg):
        """
        Return true if the package is freeze-exempt
        """
        if src_pkg.pkgname in self._pkg_autosync_overrides:
            return True
        return self._sync_enabled

    def sync_by_set(self, set_name):
        if not self._pkg_sets_dir:
            print("No sets directory defined!")
            return False
        fname = os.path.join(self._pkg_sets_dir, set_name + ".list")
        if not os.path.isfile(fname):
            print("Found no setfile for set '%s'!" % (set_name))
            return False

        hints = self._load_pkgset_file(fname)

        return self.sync_packages(hints.keys())

    def sync_all_packages(self):
        sync_fails = list()

        if not self._sync_enabled:
            print("INFO: Package syncs are currently disabled. Will only sync packages with permanent freeze exceptions.")

        def perform_sync(src_pkg):
            if not src_pkg.pkgname in self._pkgs_dest:
                ret, sinfo = self._can_sync_package(src_pkg, None, True)
                if not ret and sinfo != None:
                    sync_fails.append(sinfo)
                if ret:
                    if self.dry_run:
                        print("Sync: %s" % (src_pkg))
                    elif self._sync_allowed(src_pkg):
                        self._import_debian_package(src_pkg)
                return
            ret, sinfo = self._can_sync_package(src_pkg, self._pkgs_dest[src_pkg.pkgname], True)
            if not ret and sinfo != None:
                    sync_fails.append(sinfo)
            if ret:
                if self.dry_run:
                    print("Sync: %s" % (src_pkg))
                elif self._sync_allowed(src_pkg):
                    self._import_debian_package(src_pkg)

        # sync all packages where no rule exists
        for src_pkg in self._pkgs_src[self._sourceSuite].values():
            perform_sync(src_pkg)

        # now sync the stuff which has explicit auto-sync hints
        for pkgname, suite in self._pkg_autosync_overrides.items():
            if suite == self._sourceSuite:
                # we already synced this (if possible) in the previous step
                continue
            src_pkg = self._pkgs_src[suite].get(pkgname)
            if src_pkg:
                perform_sync(src_pkg)

        render_template("synchrotron/synchrotron-issues.html", "synchrotron/sync-issues_%s.html" % (self._component),
                page_name="synchrotron", sync_failures=sync_fails, time=time.strftime("%c"), component=self._component,
                import_freeze=not self._sync_enabled)


def main():
    # init Apt, we need it later
    apt_pkg.init()

    parser = OptionParser()
    parser.add_option("-i",
                  action="store_true", dest="import_pkg", default=False,
                  help="import a package")
    parser.add_option("-r",
                  action="store_true", dest="import_pkg_regex", default=False,
                  help="import package(s) by regular expression")
    parser.add_option("--force",
                  action="store_true", dest="force_import", default=False,
                  help="enforce the import of a package")
    parser.add_option("--import-all",
                  action="store_true", dest="sync_everything", default=False,
                  help="sync all packages with newer versions")
    parser.add_option("--import-set",
                  action="store_true", dest="import_set", default=False,
                  help="import a set of packages")
    parser.add_option("--update-data",
                  action="store_true", dest="update_data", default=False,
                  help="update information about Debian sources")
    parser.add_option("--dry",
                  action="store_true", dest="dry_run", default=False,
                  help="don't do anything, just simulate what would happen (some meta-information will still be written to disk)")
    parser.add_option("--update-cruft-report",
                  action="store_true", dest="cruft_report", default=False,
                  help="update cruft report of packages which are not in Debian")
    parser.add_option("--quiet",
                  action="store_true", dest="quiet", default=False,
                  help="don't show output (except for errors)")

    (options, args) = parser.parse_args()

    if options.import_pkg:
        sync = SyncPackage()
        if len(args) < 4:
            print("Invalid number of arguments (need source-suite, target-suite, component, package-name(s))")
            sys.exit(1)
        if options.import_pkg_regex:
            if len(args) != 4:
                print("Invalid number of arguments for regex query (need source-suite, target-suite, component, package-regex)")
                sys.exit(1)

        source_suite = args[0]
        target_suite = args[1]
        component = args[2]
        package_names = list()
        if len(args) > 4:
            for pkg in args[3:]:
                package_names.append(pkg)
        else:
            package_names.append(args[3])
        sync.initialize(source_suite, target_suite, component)
        sync.dry_run = options.dry_run
        ret = False
        if options.import_pkg_regex:
            ret = sync.sync_package_regex(package_name, force=options.force_import)
        else:
            ret = sync.sync_packages(package_names, force=options.force_import)
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
        sync.dry_run = options.dry_run
        sync.sync_all_packages()
    elif options.import_set:
        if len(args) != 4:
            print("Invalid number of arguments (need source-suite, target-suite, component, set-name)")
            sys.exit(1)
        sync = SyncPackage()
        source_suite = args[0]
        target_suite = args[1]
        component = args[2]
        set_name = args[3]
        sync.initialize(source_suite, target_suite, component)
        sync.dry_run = options.dry_run
        ret = sync.sync_by_set(set_name)
        if not ret:
            sys.exit(2)
    elif options.cruft_report:
        cr = CruftReport()
        cr.update(options.quiet)
    elif options.update_data:
        mirror = DebianMirror()
        ret = mirror.update()
        if not ret:
            sys.exit(2)
    else:
        print("Run with -h for a list of available command-line options!")
