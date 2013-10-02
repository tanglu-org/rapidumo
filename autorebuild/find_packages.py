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
import gzip
import apt_pkg

def find_packages_with_dependency (source_path):
    f = gzip.open(source_path, 'rb')
    tagf = TagFile (f)
    rebuildSources = []
    bad_depends = bad_depends.strip()
    for section in tagf:
        pkgname = section['Package']
        source_pkg = section.get('Source', '')
        if source_pkg == '':
            source_pkg = pkgname
        if source_pkg in rebuildSources:
            continue # we already handled a rebuild for that

        depends = section.get('Depends', '')
        if depends == '':
            continue
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
    return rebuildSources
