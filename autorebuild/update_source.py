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
import tarfile
import apt_pkg
import glob
import subprocess
import re
import tempfile
from itertools import islice
import shutil

def rreplace(s, old, new):
    li = s.rsplit(old, 1)
    return new.join(li)

def bump_source_version (src_pkg_dir, pkg_name, rebuild_info):
    src_pkg_dir = os.path.abspath(src_pkg_dir)
    debian_src = None
    debian_dsc = None
    os.chdir(src_pkg_dir)
    for fname in glob.glob("*.dsc"):
        debian_dsc = fname
        break
    for fname in glob.glob("*.debian.*"):
        debian_src = fname
        break
    if debian_src == None:
        # we might have a native package
        for fname in glob.glob("*.tar.*"):
            debian_src = fname
            break

    if debian_dsc == None:
        print("Unable to find dsc file for '%s'. This is a bug." % (pkg_name))
        return False
    if debian_src == None:
        print("Unable to find debian source for package '%s'. It might be an old package which needs a manual upload." % (pkg_name))
        return False

    os.chdir("/tmp")
    debian_src = ("%s/%s") % (src_pkg_dir, debian_src)
    debian_dsc = ("%s/%s") % (src_pkg_dir, debian_dsc)

    tmp_workspace = tempfile.mkdtemp()
    tar = tarfile.open(debian_src)
    tar.extractall(path=tmp_workspace)
    tar.close()

    # determine archive type
    archive_compression = None
    if debian_src.endswith("gz"):
        archive_compression = "gz"
    elif debian_src.endswith("xz"):
        archive_compression = "xz"
    elif debian_src.endswith("bz2"):
        archive_compression = "bz2"
    else:
        print("Could not determine archive compression type for '%s'!" % (debian_src))
        return False

    changelog_fname = None
    for r,d,f in os.walk(tmp_workspace):
        for fname in f:
            path = os.path.join(r,fname)
            if path.endswith("debian/changelog"):
                 changelog_fname = path
    if changelog_fname == None:
        print("Unable to find changelog for package '%s'. It might be an old package which needs a manual upload." % (pkg_name))

    # get version number (and possible other values later)
    with open(changelog_fname) as f:
        head = list(islice(f,2))
    m = re.search('\((.*?)\)', head[0])
    pkg_version_old = m.group(1)

    # change dir to pkg basedir
    os.chdir(os.path.abspath("%s/../.." % (changelog_fname)))

    # we need ubuntu as vendor to get the rebuild action
    dch_cmd = ["dch", "--rebuild", "--vendor=ubuntu", "-Dstaging", "No-change rebuild against %s" % (rebuild_info)]
    proc = subprocess.Popen(dch_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    output = ("%s\n%s") % (stdout, stderr)
    if (proc.returncode != 0):
        print(output)
        return False

    # get version number (and possible other values later)
    with open(changelog_fname) as f:
        head = list(islice(f,6))
    m = re.search('\((.*?)\)', head[0])
    pkg_version_new = m.group(1)

    # recreate source file as original file
    os.chdir(tmp_workspace)
    os.remove(debian_src)
    debian_src_new = rreplace(debian_src, pkg_version_old, pkg_version_new)
    with tarfile.open(debian_src_new, "w:%s" % (archive_compression)) as tar:
        tar.add(".", recursive=True)

    os.chdir("/tmp")
    # cleanup workspace
    shutil.rmtree(tmp_workspace)

    # now update the dsc file
    new_dsc_content = []
    for line in open(debian_dsc):
        if line.startswith("Version: %s" % (pkg_version_old)):
            new_dsc_content.append("Version: %s\n" % (pkg_version_new))
        else:
            new_dsc_content.append(line)
    debian_dsc_new = rreplace(debian_dsc, pkg_version_old, pkg_version_new)
    print(debian_dsc_new)
    f = open(debian_dsc_new, 'w')
    f.write("".join(new_dsc_content))
    f.close()
    os.remove(debian_dsc)

    # now fix the signature
    debsign_cmd = ["debsign", "--re-sign", debian_dsc_new]
    proc = subprocess.Popen(debsign_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    output = ("%s\n%s") % (stdout, stderr)
    if (proc.returncode != 0):
        print(output)
        return False
    return True
