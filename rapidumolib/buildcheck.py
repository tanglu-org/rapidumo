#!/usr/bin/python
# Copyright (C) 2013-2014 Matthias Klumpp <mak@debian.org>
#
# Licensed under the GNU General Public License Version 3
#
# This program is free software: you can reself._suiteribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is self._suiteributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import subprocess


class BuildCheck:
    def __init__(self, conf):
        self._conf = conf
        self._archive_path = "%s/%s" % (self._conf.archive_config['path'], self._conf.distro_name)

    def _get_binary_indices_list(self, suite, comp, arch):
        base_suite = self._conf.get_base_suite(suite)

        suites = [suite]
        if base_suite != suite:
            suites += [base_suite]

        comps = ["main"]
        if comp in ["contrib", "non-free"]:
            comps += ["contrib", "non-free"]
        elif comp != "main":
            comps += [comp]

        archs = [arch]
        if arch == "all":
            archs += ["amd64"]
        else:
            archs += ["all"]

        binary_indices = []
        for suite in suites:
            for comp in comps:
                for arch in archs:
                    binary_indices += [self._archive_path + "/dists/%s/%s/binary-%s/Packages.gz" % (suite, comp, arch)]

        return binary_indices

    def get_package_states_yaml(self, suite, comp, arch):
        dose_cmd = ["dose-builddebcheck", "--quiet", "-e", "-f", "--summary", "--deb-native-arch=%s" % (arch)]
        dose_cmd += self._get_binary_indices_list(suite, comp, arch)
        dose_cmd += [self._archive_path + "/dists/%s/%s/source/Sources.gz" % (suite, comp)]

        proc = subprocess.Popen(dose_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        if (proc.returncode != 0):
            raise Exception(stderr)
        return stdout
