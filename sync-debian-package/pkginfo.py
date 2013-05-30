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

import gzip
import os.path
from ConfigParser import SafeConfigParser
from apt_pkg import TagFile, TagSection
from apt_pkg import version_compare

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
        self.installedArchs = []
        self.directory = directory

    def getVersionNoEpoch(self):
        return noEpoch(self.version)

    def __str__(self):
        return "Package: name: %s | version: %s | suite: %s | comp.: %s" % (self.pkgname, self.version, self.suite, self.component)

class PackageInfoRetriever():
    def __init__(self, path, distro, suite):
        self._archivePath = path
        self._distroName = distro
        self._suiteName = suite

    def _get_packages_for(self, component):
        source_path = self._archivePath + "/dists/%s-%s/%s/source/Sources.gz" % (self._distroName, self._suiteName, component)
        f = gzip.open(source_path, 'rb')
        tagf = TagFile (f)
        packageList = []
        for section in tagf:
            archs = section['Architecture']
            binaries = section['Binary']
            pkgversion = section['Version']
            pkgname = section['Package']
            directory = section['Directory']
            pkg = PackageInfo(pkgname, pkgversion, self._suiteName, component, archs, directory)

            packageList.append(pkg)

        return packageList

    def get_packages_dict(self, component):
        packageList = self._get_packages_for(component)
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
