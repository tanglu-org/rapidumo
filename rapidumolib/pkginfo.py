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

import gzip
import os.path
import re
from ConfigParser import SafeConfigParser
from apt_pkg import TagFile, TagSection
from apt_pkg import version_compare
from rapidumolib.utils import *

def noEpoch(version):
    v = version
    if ":" in v:
        return v[v.index(":")+1:]
    else:
        return v

class PackageInfo():
    def __init__(self, pkgname, pkgversion, suite, component, archs, directory):
        self.pkgname = pkgname
        self.version = pkgversion
        self.suite = suite
        self.component = component
        self.archs = archs
        self.info = ""
        self.installed_archs = []
        self.directory = directory

        self.build_depends = ""
        self.build_conflicts = ""

        self.extra_source_only = False

    def getVersionNoEpoch(self):
        return noEpoch(self.version)

    def __str__(self):
        return "Package: name: %s | version: %s | suite: %s | comp.: %s" % (self.pkgname, self.version, self.suite, self.component)

"""
 Retrieve information about source packages available
 in the distribution.
"""
class SourcePackageInfoRetriever():
    def __init__(self, path, distro, suite, momCache=False):
        self._archivePath = path
        self._distroName = distro
        self._suiteName = suite
        self.extra_suite = ""
        self.useMOMCache = momCache

    def _get_packages_for(self, suite, component):
        if self.useMOMCache:
            source_path = self._archivePath + "/dists/%s-%s/%s/source/Sources.gz" % (self._distroName, suite, component)
        else:
            source_path = self._archivePath + "/%s/dists/%s/%s/source/Sources.gz" % (self._distroName, suite, component)
        f = gzip.open(source_path, 'rb')
        tagf = TagFile (f)
        packageList = []
        for section in tagf:
            archs = section['Architecture']
            binaries = section['Binary']
            pkgversion = section['Version']
            pkgname = section['Package']
            directory = section['Directory']
            pkg = PackageInfo(pkgname, pkgversion, suite, component, archs, directory)

            if section.get('Extra-Source-Only', 'no') == 'yes':
                pkg.extra_source_only = True

            packageList.append(pkg)

        if self.extra_suite != "":
            packageList.extend(self._get_packages_for(self.extra_suite, component))

        return packageList

    def get_packages_dict(self, component):
        packageList = self._get_packages_for(self._suiteName, component)
        packages_dict = {}
        for pkg in packageList:
            pkgname = pkg.pkgname
            # replace it only if the version of the new item is higher (required to handle epoch bumps and new uploads)
            if pkgname in packages_dict:
                regVersion = packages_dict[pkgname].version
                compare = version_compare(regVersion, pkg.version)
                if compare >= 0:
                    continue
            packages_dict[pkgname] = pkg

        return packages_dict

"""
 Retrieve information about source packages and their build status.
 Useful for our build infrastructure.
"""
class PackageBuildInfoRetriever():
    def __init__(self):
        parser = get_archive_config_parser()
        path = parser.get('Archive', 'path')
        path = "%s/%s" % (path, parser.get('General', 'distro_name'))
        self._archivePath = path
        export_path = parser.get('Archive', 'export_dir')
        self._archiveComponents = parser.get('Archive', 'components').split (" ")
        self._supportedArchs = parser.get('Archive', 'archs').split (" ")
        self._supportedArchs.append("all")
        self._installedPkgs = {}

        # to speed up source-fetching and to kill packages without maintainer immediately, we include the pkg-maintainer
        # mapping, to find out active source/binary packages (currently, only source packages are filtered)
        self._activePackages = []
        for line in open(export_path + "/SourceMaintainers"):
           pkg_m = line.strip ().split (" ", 1)
           if len (pkg_m) > 1:
               self._activePackages.append(pkg_m[0].strip())

    def _set_pkg_installed_for_arch(self, dirname, pkg, binaryName):
        for arch in self._supportedArchs:
            if arch in pkg.installedArchs:
                continue

            # check caches for installed package
            pkg_id = "%s_%s" % (binaryName, arch)
            if pkg_id in self._installedPkgs:
                existing_pkgversion = self._installedPkgs[pkg_id]
                if pkg.version == existing_pkgversion:
                    pkg.installedArchs.append(arch)
                    continue

            # we also check if the package file is still installed in pool.
            # this reduces the amount of useless rebuild requests, because if there is still
            # a binary package in pool, the newly built package with the same version will be rejected
            # anyway.
            # This doesn't catch all corner-cases (e.g. different binary-versions), but it's better than nothing.
            binaryExists = False
            for fileExt in ["deb", "udeb"]:
                binaryPkgName = "%s_%s_%s.%s" % (binaryName, pkg.getVersionNoEpoch(), arch, fileExt)
                expectedPackagePath = self._archivePath + "/%s/%s" % (dirname, binaryPkgName)

                if os.path.isfile(expectedPackagePath):
                    binaryExists = True
                    break

            if binaryExists:
                pkg.installedArchs.append(arch)
                continue

    def get_packages_for(self, suite, component):
        # create a cache of all installed packages on the different architectures
        self._build_installed_pkgs_cache(suite, component)
        source_path = self._archivePath + "/dists/%s/%s/source/Sources.gz" % (suite, component)
        f = gzip.open(source_path, 'rb')
        tagf = TagFile (f)
        packageList = []
        for section in tagf:
            # don't even try to build source-only packages
            if section.get('Extra-Source-Only', 'no') == 'yes':
                continue

            pkgname = section['Package']
            if not pkgname in self._activePackages:
                continue
            archs_str = section['Architecture']
            binaries = section['Binary']
            pkgversion = section['Version']
            directory = section['Directory']

            if ' ' in archs_str:
                archs = archs_str.split(' ')
            else:
                archs = [archs_str]
            # remove duplicate archs from list
            # this is very important, because we otherwise will add duplicate build requests in Jenkins
            archs = list(set(archs))

            pkg = PackageInfo(pkgname, pkgversion, suite, component, archs, directory)

            # values needed for build-dependency solving
            pkg.build_depends = section.get('Build-Depends', '')
            pkg.build_conflicts = section.get('Build-Conflicts', '')

            # we check if one of the arch-binaries exists. if it does, we consider the package built for this architecture
            # FIXME: This does not work well for binNMUed packages! Implement a possible solution later.
            # (at time, a version-check prevents packages from being built twice)
            if "," in binaries:
                binaryPkgs = binaries.split(', ')
            else:
                binaryPkgs = [binaries]
            for binaryName in binaryPkgs:
                self._set_pkg_installed_for_arch(directory, pkg, binaryName)
                #if (pkg.installedArchs != ["all"]) or (len(binaryPkgs) <= 0:

            packageList += [pkg]

        return packageList

    def _build_installed_pkgs_cache(self, suite, component):
        for arch in self._supportedArchs:
            source_path = self._archivePath + "/dists/%s/%s/binary-%s/Packages.gz" % (suite, component, arch)
            f = gzip.open(source_path, 'rb')
            tagf = TagFile (f)
            for section in tagf:
                # make sure we have the right arch (closes bug in installed-detection)
                if section['Architecture'] != arch:
                    continue

                pkgversion = section['Version']
                pkgname = section['Package']
                pkgsource = section.get('Source', '')
                # if source has different version, we cheat and set the binary pkg version
                # to the source package version
                if "(" in pkgsource:
                    m = re.search(r"\((.*)\)", pkgsource)
                    s = m.group(1).strip()
                    if s != "":
                        pkgversion = s
                pkid = "%s_%s" % (pkgname, arch)
                if pkid in self._installedPkgs:
                   regVersion = self._installedPkgs[pkid]
                   compare = version_compare(regVersion, pkgversion)
                   if compare >= 0:
                       continue
                self._installedPkgs[pkid] = pkgversion

    def package_list_to_dict(self, pkg_list):
        pkg_dict = {}
        for pkg in pkg_list:
            # replace it only if the version of the new item is higher (required to handle epoch bumps and new uploads)
            if pkg.pkgname in pkg_dict:
                regVersion = pkg_dict[pkg.pkgname].version
                compare = version_compare(regVersion, pkg.version)
                if compare >= 0:
                    continue
            pkg_dict[pkg.pkgname] = pkg
        return pkg_dict
