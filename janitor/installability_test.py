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

from rapidumolib.utils import *
import subprocess
import yaml

class JanitorDebcheck:
    def __init__(self):
        parser = get_archive_config_parser()
        path = parser.get('Archive', 'path')
        self._archive_path = path
        self._distro = parser.get('General', 'distro_name').lower()

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
            # staging needs the aequorea data (it is no complete suite)
            archive_indices.extend(self._get_binary_indices_list("aequorea", comp, arch))

        return archive_indices

    def _run_dose_debcheck(self, suite, comp, arch):
        # we always need main components
        archive_indices = self._get_binary_indices_list(suite, "main", arch)
        if comp != "main":
            # if the component is not main, add it to the list
            comp_indices = self._get_binary_indices_list(suite, comp, arch)
            archive_indices.extend(comp_indices)
            if comp == "non-free":
                # non-free might need contrib
                comp_indices = self._get_binary_indices_list(suite, "contrib", arch)
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

    def get_debcheck_yaml(self, suite, component, architecture):
        ret, output = self._run_dose_debcheck(suite, component, architecture)
        return output

    def get_uninstallable_packages(self, suite, component, architecture):
        # we return a package=>reason dictionary
        res = {}
        info = self.get_debcheck_yaml(suite, component, architecture)
        doc = yaml.load(info)
        if doc['report'] is not None:
            for p in doc['report']:
                pkg = p['package']
                if pkg.startswith('src%3a'):
                    pkg = pkg.replace('src%3a',"",1)
                if ":" in pkg:
                    parts = pkg.split (':')
                    pkg = parts[1]
                res[pkg] = p['reasons']
        return res
