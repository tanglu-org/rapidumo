#!/usr/bin/env python3
#
# Copyright (C) 2013-2014 Matthias Klumpp <mak@debian.org>
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
import glob
import gzip
import re
import subprocess
from apt_pkg import TagFile, version_compare


def package_list_to_dict(pkg_list):
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

        self.homepage = None
        self.extra_source_only = False

        self.queue_name = None

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
        self._archive_path = path
        self._distroName = distro
        self._suiteName = suite
        self.extra_suite = ""
        self.useMOMCache = momCache

    def _get_packages_for(self, suite, component):
        if self.useMOMCache:
            source_path = self._archive_path + "/dists/%s-%s/%s/source/Sources" % (self._distroName, suite, component)
        else:
            aroot = self._archive_path
            if suite.startswith("buildq"):
                aroot = self._bqueue_path
            source_path = aroot + "/%s/dists/%s/%s/source/Sources.gz" % (self._distroName, suite, component)
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
            pkg.maintainer = section['Maintainer']
            pkg.comaintainers = section.get('Uploaders', '')
            pkg.homepage = section.get('Homepage', None)

            if section.get('Extra-Source-Only', 'no') == 'yes':
                pkg.extra_source_only = True

            packageList.append(pkg)

        if self.extra_suite:
            packageList.extend(self._get_packages_for(self.extra_suite, component))

        return packageList

    def get_packages_dict(self, component):
        packageList = self._get_packages_for(self._suiteName, component)

        packages_dict = package_list_to_dict(packageList)

        return packages_dict


class PackageBuildInfoRetriever():
    """
     Retrieve information about source packages and their build status.
     Useful for our build infrastructure.
    """

    def __init__(self, conf):
        self._conf = conf
        self._archive_path = "%s/%s" % (self._conf.archive_config['path'], self._conf.distro_name)
        self._bqueue_path = self._conf.archive_config['build_queues_path']

    def _get_package_list(self, suite, component, is_build_queue=False):
        source_path = None
        if is_build_queue:
            source_path = self._bqueue_path + "/dists/%s/%s/source/Sources.gz" % (suite, component)
        else:
            source_path = self._archive_path + "/dists/%s/%s/source/Sources.gz" % (suite, component)
        f = gzip.open(source_path, 'rb')
        tagf = TagFile(f)
        packageList = []
        for section in tagf:
            # don't even try to build source-only packages
            if section.get('Extra-Source-Only', 'no') == 'yes':
                continue

            pkgname = section['Package']
            pkgversion = section['Version']
            archs = list(set(section['Architecture'].split(None)))
            directory = section['Directory']
            dsc = find_dsc(section['Files'])

            pkg = PackageInfo(pkgname, pkgversion, suite, component, archs, directory, dsc)

            if section.get('Extra-Source-Only', 'no') == 'yes':
                pkg.extra_source_only = True

            # values needed for build-dependency solving
            pkg.build_depends = section.get('Build-Depends', '')
            pkg.build_conflicts = section.get('Build-Conflicts', '')

            pkg.maintainer = section['Maintainer']
            pkg.comaintainers = section.get('Uploaders', '')

            packageList += [pkg]

        bqueue = self._conf.get_build_queue(suite)
        if bqueue:
            packageList.extend(self._get_package_list(bqueue, component, is_build_queue=True))

        return packageList

    def _add_binaries_to_dict(self, pkg_dict, suite, component, arch, udeb=False):
        aroot = self._archive_path
        if suite.startswith("buildq"):
            aroot = self._bqueue_path
        if udeb:
            source_path = aroot + "/dists/%s/%s/debian-installer/binary-%s/Packages.gz" % (suite, component, arch)
        else:
            source_path = aroot + "/dists/%s/%s/binary-%s/Packages.gz" % (suite, component, arch)
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

            if pkg is not None and pkg.version == pkgversion:
                if arch not in pkg.installed_archs:
                    pkg.installed_archs += [arch]
                pkg.binaries += [(pkgname, arch, section['Filename'])]
                pkg_dict[pkgsource] = pkg

        return pkg_dict

    def get_packages_dict(self, suite):
        base_suite = self._conf.get_base_suite(suite)
        suites = [suite, base_suite] if suite != base_suite else [suite]
        components = self._conf.get_supported_components(base_suite).split(" ")
        archs = self._conf.get_supported_archs(base_suite).split(" ") + ["all"]

        pkg_list = []
        for component in components:
            pkg_list += self._get_package_list(suite, component)
        pkg_dict = package_list_to_dict(pkg_list)

        for suite in suites:
            for component in components:
                for arch in archs:
                    pkg_dict = self._add_binaries_to_dict(pkg_dict, suite, component, arch)
                    pkg_dict = self._add_binaries_to_dict(pkg_dict, suite, component, arch, udeb=True)

        for name, pkg in pkg_dict.items():
            for arch in archs:
                if (arch not in pkg.installed_archs and
                        glob.glob(self._archive_path + "/%s/*_%s_%s.deb" %
                                  (pkg.directory, noEpoch(pkg.version), arch))):
                    # There are *.deb files in the pool, but no entries in Packages.gz
                    # We don't want spurious build jobs if this is a temporary error,
                    # but without info on the binary packages we can't use them either,
                    # so skip this package for now.
                    print("Skipping %s (%s) in %s due to repository inconsistencies" %
                          (pkg.pkgname, pkg.version, pkg.suite))
                    del pkg_dict[name]
                    break

        return pkg_dict

class BuildCheck:
    def __init__(self, conf):
        self._conf = conf
        self._archive_path = "%s/%s" % (self._conf.archive_config['path'], self._conf.distro_name)
        self._bqueue_path = self._conf.archive_config['build_queues_path']

    def _get_pkg_indices_list(self, suite_name, comp, arch, add_sources=False, is_build_queue=False):
        build_queue = self._conf.get_build_queue(suite_name)
        suites = [{'name': suite_name, 'apath': self._archive_path}]
        if build_queue:
            suites += [{'name': build_queue, 'apath': self._bqueue_path}]
        else:
            base_suite = self._conf.get_base_suite(suite_name)
            if base_suite != suite_name:
                suites += [{'name': base_suite, 'apath': self._archive_path}]

        comps = ["main"]
        if comp in ["contrib", "non-free"]:
            comps += ["contrib", "non-free"]
        elif comp != "main":
            comps += [comp]

        if arch == "all":
            arch = "amd64"

        pkg_indices = list()
        for suite in suites:
            for comp in comps:
                pkg_indices.append(suite['apath'] + "/dists/%s/%s/binary-%s/Packages.gz" % (suite['name'], comp, arch))
                if add_sources:
                    pkg_indices.append(suite['apath'] + "/dists/%s/%s/source/Sources.gz" % (suite['name'], comp))

        return pkg_indices

    def get_package_states_yaml_sources(self, suite, comp, arch, source_gz_path=None):
        add_sources = not source_gz_path
        dose_cmd = ["dose-builddebcheck", "--quiet", "--latest", "-e", "-f", "--summary", "--deb-native-arch=%s" % (arch)]
        dose_cmd += self._get_pkg_indices_list(suite, comp, arch, add_sources)
        if source_gz_path:
            dose_cmd += [source_gz_path]

        proc = subprocess.Popen(dose_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        if stderr:
            # FIXME: hack to ignore this particular error...
            if not "Unable to get real version for mplayer2" in stderr:
                raise Exception(stderr)

        # make this work on Python2 as well
        if sys.version_info >= (3,):
            stdout = str(stdout, 'utf-8')

        ydata = stdout.replace("%3a", ":")  # Support for wheezy version of dose-builddebcheck
        return ydata

    def get_package_states_yaml(self, suite, comp, arch):
        return self.get_package_states_yaml_sources(suite, comp, arch)
