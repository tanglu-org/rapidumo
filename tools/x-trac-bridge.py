#!/usr/bin/python
# Copyright (C) 2013 Matthias Klumpp <mak@debian.org>
#
# Licensed under the GNU Lesser General Public License Version 3
#
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import subprocess
from rapidumolib import pkginfo

# settings
TRAC_DIR = "/srv/bugs.tanglu.org"

class ArchiveTracBridge:
    def __init__(self):
        self.tracComponents = self._getTracComponents ()

    def getArchiveSourcePackageInfo (self):
        spkgs = SourcePackageInfoRetriever("/srv/de.archive.tanglu.org/tanglu", "bartholomea")
        pkgs = pkginfo_tgl.get_packages_dict("non-free")
        pkgs.update(pkginfo_tgl.get_packages_dict("contrib"))
        pkgs.update(pkginfo_tgl.get_packages_dict("main"))

        return pkgs

    def _getTracComponents (self):
        p = subprocess.Popen( ["trac-admin", TRAC_DIR, "component", "list"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        resLines = ""
        while (True):
          retcode = p.poll ()
          line = p.stdout.readline ()
          resLines += line
          if (retcode is not None):
              break
        if p.returncode is not 0:
            raise Exception(resLines)

        rawTracCmp = resLines.splitlines ()
        tracCmps = {}
        # NOTE: we keep the beginning comment and garbage in the components dict, as they are not harmful
        # for later processing
        for cmpln in rawTracCmp:
           tcomp = cmpln.strip ().split (" ", 1)
           if len (tcomp) > 1:
               tracCmps[tcomp[0].strip ()] = tcomp[1].strip ()

        return tracCmps

    def addTracComponent (self, name, user):
        print "[add] Adding new component '%s' and assigning to %s" % (name, user)
        try:
            output = subprocess.check_output (["trac-admin", TRAC_DIR, "component", "add", name, user.replace("'", "'\\''")])
        except subprocess.CalledProcessError as e:
            print("%s\n%s" % (e, output))
            return False

        self.tracComponents[name] = user
        return True

    def chownTracComponent (self, name, user):
        print "[modify] Assigning component '%s' to %s" % (name, user)
        try:
            output = subprocess.check_output (["trac-admin", TRAC_DIR, "component", "chown", name, user.replace("'", "'\\''")])
        except subprocess.CalledProcessError as e:
            print("%s\n%s" % (e, output))
            return False

        self.tracComponents[name] = user
        return True

    def refreshTracComponentList (self):
        # get some fresh data
        debSourceInfo = self.getArchiveSourcePackageInfo ()
        for spkg in debSourceInfo:
            pkg_name = spkg.pkgname
            pkg_maint = spkg.maintainer
            if not pkg_name in self.tracComponents:
                self.addTracComponent (pkg_name, pkg_maint)
            elif not self.tracComponents[pkg_name] == pkg_maint:
                self.chownTracComponent (pkg_name, pkg_maint)
        # TODO: Maybe remove components as soon as they leave the maintained distribution?
        # (or better keep them for historic reasons?))

if __name__ == '__main__':
    daktrac = ArchiveTracBridge ()
    daktrac.refreshTracComponentList ()

    print("Done.")

