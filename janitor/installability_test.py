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

from rapidumo.config import *
import subprocess
import yaml
import re
from janitor_utils import PackageRemovalItem

class JanitorDebcheck:
    def __init__(self):
        conf = RapidumoConfig()
        aconf = conf.archive_config
        path = aconf['path']
        self._archive_path = path
        self._devel_suite = aconf['devel_suite']
        self._distro = conf.distro_name.lower()

    def _get_binary_indices_list(self, suite, comp, arch):
        archive_indices = []
        archive_binary_index_path = self._archive_path + "/%s/dists/%s/%s/binary-%s/Packages.gz" % (self._distro, suite, comp, arch)
        archive_indices.append(archive_binary_index_path)
        if arch == "all":
            # if arch is all, we feed the solver with a binary architecture as example, to solve dependencies on arch-specific stuff
            archive_binary_index_path_arch = self._archive_path + "/%s/dists/%s/%s/binary-amd64/Packages.gz" % (self._distro, suite, comp)
            archive_indices.append(archive_binary_index_path_arch)
        else:
            # any architecture canb also depend on arch:all stuff, so we add it to the loop
            archive_binary_index_path_all = self._archive_path + "/%s/dists/%s/%s/binary-all/Packages.gz" % (self._distro, suite, comp)
            archive_indices.append(archive_binary_index_path_all)

        if suite == "staging":
            # staging needs the devel suite data (it is no complete suite)
            archive_indices.extend(self._get_binary_indices_list(self._devel_suite, comp, arch))

        return archive_indices

    def _run_dose_debcheck(self, suite, arch):
        # we always need the main component
        archive_indices = self._get_binary_indices_list(suite, "main", arch)
        # add contrib
        comp_indices = self._get_binary_indices_list(suite, "contrib", arch)
        archive_indices.extend(comp_indices)
        # analyze non-free too
        comp_indices = self._get_binary_indices_list(suite, "non-free", arch)
        archive_indices.extend(comp_indices)

        dose_cmd = ["dose-debcheck", "--quiet", "-e", "-f", "--summary", "--deb-native-arch=%s" % (arch)]
        # add the archive index files
        dose_cmd.extend(archive_indices)

        proc = subprocess.Popen(dose_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        output = stdout
        # we are (currently) not interested in dose errors
        #if (proc.returncode != 0):
        #    return False, stderr
        return True, output

    def get_debcheck_yaml(self, suite, architecture):
        ret, output = self._run_dose_debcheck(suite, architecture)
        return output

    def get_uninstallable_packages(self, suite, architecture):
        # we return a package=>reason dictionary
        res = {}
        info = self.get_debcheck_yaml(suite, architecture)
        doc = yaml.safe_load(info)
        if doc['report'] is not None:
            for p in doc['report']:
                pkg = p['source']
                if pkg.startswith('src%3a'):
                    pkg = pkg.replace('src%3a', "", 1)
                if not "(" in pkg:
                    continue
                parts = pkg.split ('(')
                pkg = parts[0].strip()
                version = parts[1].replace("=", "", 1).strip()
                version = re.sub('\)$', '', version)
                res["%s/%s" % (pkg, version)] = p['reasons']
        return res

    def get_uninstallable_removals(self, suite, archs):
        cruft_dict = {}
        for arch in archs:
            uninst_pkgs = self.get_uninstallable_packages(suite, arch)
            for pkg_id in uninst_pkgs.keys():
                parts = pkg_id.split("/")
                pkg = parts[0]
                version = parts[1]
                if pkg in cruft_dict:
                    # package is uninstallable on another arch (or different version - we don't handle this case at time)
                    rmitem = cruft_dict[pkg]
                    rmitem.reason = "%s, %s" % (rmitem.reason, arch)
                    cruft_dict[pkg] = rmitem
                else:
                    reason_yml = uninst_pkgs[pkg_id]
                    reason = "Binary packages with broken dependencies."
                    # extract some very basic hints on why this package is broken
                    reason_yml = reason_yml[0] # we only want the first reason
                    if 'missing' in reason_yml:
                        reason = "%s\nMissing dependency: %s" % (reason, reason_yml['missing']['pkg']['unsat-dependency'])
                    elif 'conflict' in reason_yml:
                        reason = "%s\nConflicting packages. '%s' is involved." % (reason, reason_yml['conflict']['pkg1']['unsat-conflict'])
                    reason = "%s\nBroken on arch: %s" % (reason, arch)
                    reason = reason.replace("%3a", ":")
                    cruft_dict[pkg] = PackageRemovalItem(suite, pkg, version, reason)
        return cruft_dict.values()
