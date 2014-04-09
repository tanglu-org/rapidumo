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
from apt_pkg import TagFile
from apt_pkg import version_compare
from rapidumolib.config import RapidumoConfig


def noEpoch(version):
    v = version
    if ":" in v:
        return v[v.index(":")+1:]
    else:
        return v


def find_dsc(value):
    for text in value.split(None):
        if text.endswith(".dsc"):
            return text
    return None


class PackageInfo():
    def __init__(self, pkgname, pkgversion, suite, component, archs, directory, dsc):
        self.pkgname = pkgname
        self.version = pkgversion
        self.suite = suite
        self.component = component
        self.archs = archs
        self.binaries = []
        self.installed_archs = []
        self.directory = directory
        self.dsc = dsc

        self.build_depends = ""
        self.build_conflicts = ""

        self.maintainer = ""
        self.comaintainers = ""

        self.extra_source_only = False

    def getVersionNoEpoch(self):
        return noEpoch(self.version)

    def __str__(self):
        return "Package: name: %s | version: %s | suite: %s | comp.: %s" % (self.pkgname, self.version, self.suite, self.component)


class SourcePackageInfoRetriever():
    """
     Retrieve information about source packages available
     in the distribution.
    """

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
        tagf = TagFile(f)
        packageList = []
        for section in tagf:
            archs = section['Architecture']
            pkgversion = section['Version']
            pkgname = section['Package']
            directory = section['Directory']
            dsc = find_dsc(section['Files'])
            pkg = PackageInfo(pkgname, pkgversion, suite, component, archs, directory, dsc)

            if section.get('Extra-Source-Only', 'no') == 'yes':
                pkg.extra_source_only = True

            packageList.append(pkg)

        if suite == "staging":
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


class PackageBuildInfoRetriever():
    """
     Retrieve information about source packages and their build status.
     Useful for our build infrastructure.
    """

    def __init__(self):
        self._conf = RapidumoConfig()
        aconf = self._conf.archive_config
        path = aconf['path']
        path = "%s/%s" % (path, self._conf.distro_name)
        self._archivePath = path
        export_path = aconf['export_dir']
        self._installedPkgs = {}

        # to speed up source-fetching and to kill packages without maintainer immediately, we include the pkg-maintainer
        # mapping, to find out active source/binary packages (currently, only source packages are filtered)
        self._activePackages = []
        for line in open(export_path + "/SourceMaintainers"):
            pkg_m = line.strip().split(" ", 1)
            if len(pkg_m) > 1:
                self._activePackages.append(pkg_m[0].strip())

    def _set_suite_info(self, suite):
        devel_suite = self._conf.archive_config['devel_suite']
        staging_suite = self._conf.archive_config['staging_suite']
        a_suite = suite
        if suite == staging_suite:
            a_suite = devel_suite
        self._supportedComponents = self._conf.get_supported_components(a_suite).split(" ")
        self._supportedArchs = self._conf.get_supported_archs(a_suite).split(" ")
        self._supportedArchs.append("all")

    def _get_package_list(self, suite, component):
        source_path = self._archivePath + "/dists/%s/%s/source/Sources.gz" % (suite, component)
        f = gzip.open(source_path, 'rb')
        tagf = TagFile(f)
        packageList = []
        for section in tagf:
            # don't even try to build source-only packages
            if section.get('Extra-Source-Only', 'no') == 'yes':
                continue

            pkgname = section['Package']
            if not pkgname in self._activePackages:
                continue
            archs_str = section['Architecture']
            pkgversion = section['Version']
            directory = section['Directory']
            dsc = find_dsc(section['Files'])

            if ' ' in archs_str:
                archs = archs_str.split(' ')
            else:
                archs = [archs_str]
            # remove duplicate archs from list
            # this is very important, because we otherwise will add duplicate build requests in Jenkins
            archs = list(set(archs))

            pkg = PackageInfo(pkgname, pkgversion, suite, component, archs, directory, dsc)

            # values needed for build-dependency solving
            pkg.build_depends = section.get('Build-Depends', '')
            pkg.build_conflicts = section.get('Build-Conflicts', '')

            pkg.maintainer = section['Maintainer']
            pkg.comaintainers = section.get('Uploaders', '')

            packageList += [pkg]

        return packageList

    def _add_binaries_to_dict(self, pkg_dict, suite, component, arch):
        source_path = self._archivePath + "/dists/%s/%s/binary-%s/Packages.gz" % (suite, component, arch)
        f = gzip.open(source_path, 'rb')
        tagf = TagFile(f)
        for section in tagf:
            # make sure we have the right arch (closes bug in installed-detection)
            if section['Architecture'] != arch:
                continue

            pkgversion = section['Version']
            pkgname = section['Package']
            pkgsource = section.get('Source', pkgname)
            # if source has different version, we cheat and set the binary pkg version
            # to the source package version
            if "(" in pkgsource:
                m = re.search(r"^(.*)\((.*)\)$", pkgsource)
                pkgsource = m.group(1).strip()
                pkgversion = m.group(2).strip()

            pkg = pkg_dict.get(pkgsource, None)

            # we also check if the package file is still installed in pool.
            # this reduces the amount of useless rebuild requests, because if there is still
            # a binary package in pool, the newly built package with the same version will be rejected
            # anyway.
            # This doesn't catch all corner-cases (e.g. different binary-versions), but it's better than nothing.
            if pkg is not None and pkg.version == pkgversion:
                if arch not in pkg.installed_archs and os.path.isfile(self._archivePath + section['Filename']):
                    pkg.installed_archs += [arch]
                pkg.binaries += [(pkgname, arch, section['Filename'])]
                pkg_dict[pkgsource] = pkg

        return pkg_dict

    def _package_list_to_dict(self, pkg_list):
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

    def get_packages(self, suite):
        self._set_suite_info(suite)

        pkg_list = []
        for component in self._supportedComponents:
            pkg_list += self._get_package_list(suite, component)
        pkg_dict = self._package_list_to_dict(pkg_list)

        for component in self._supportedComponents:
            for arch in self._supportedArchs:
                pkg_dict = self._add_binaries_to_dict(pkg_dict, suite, component, arch)

        return pkg_dict
