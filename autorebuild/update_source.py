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
import contextlib
import lzma
import apt_pkg
import glob
import subprocess
import re
import tempfile
from itertools import islice
import shutil
import hashlib
from rapidumolib.pkginfo import noEpoch

class Checksum:
    Unknown, Sha1, Sha256, MD5 = range(4)

def rreplace(s, old, new):
    li = s.rsplit(old, 1)
    return new.join(li)

def get_file_hash(fname, checksum):
    if checksum == Checksum.Unknown:
        print("Error while assembling new dsc file: Attempt to create checksum, bot no checksum was set")
        return False
    if checksum == Checksum.Sha1:
        return hashlib.sha1(open(fname, 'rb').read()).hexdigest()
    elif checksum == Checksum.Sha256:
        return hashlib.sha256(open(fname, 'rb').read()).hexdigest()
    elif checksum == Checksum.MD5:
        return hashlib.md5(open(fname, 'rb').read()).hexdigest()

def find_changelog(tmp_workspace, pkg_name):
    changelog_fname = None
    for r,d,f in os.walk(tmp_workspace):
        for fname in f:
            path = os.path.join(r,fname)
            if path.endswith("debian/changelog"):
                 changelog_fname = path
    if changelog_fname == None:
        print("Unable to find changelog for package '%s'. It might be an old package which needs a manual upload." % (pkg_name))
        return None
    return changelog_fname

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
        return False, None
    if debian_src == None:
        print("Unable to find debian source for package '%s'. It might be an old package which needs a manual upload." % (pkg_name))
        return False, None

    os.chdir("/tmp")
    debian_src = ("%s/%s") % (src_pkg_dir, debian_src)
    debian_dsc = ("%s/%s") % (src_pkg_dir, debian_dsc)

    tmp_workspace = tempfile.mkdtemp()

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
        return False, None

    try:
        if archive_compression == "xz":
            with contextlib.closing(lzma.LZMAFile(debian_src)) as xz:
                with tarfile.open(fileobj=xz) as tar:
                    tar.extractall(path=tmp_workspace)
        else:
            tar = tarfile.open(debian_src)
            tar.extractall(path=tmp_workspace)
            tar.close()
    except Exception as e:
        print("Failed to open Tar file %s (%s)" % (debian_src, str(e)))
        print("Package %s needs a manual upload." % (pkg_name))
        return False, None

    changelog_fname = find_changelog(tmp_workspace, pkg_name)
    if changelog_fname == None:
        return False, None

    # get version number (and possible other values later)
    with open(changelog_fname) as f:
        head = list(islice(f,2))
    m = re.search('\((.*?)\)', head[0])
    pkg_version_old = m.group(1)

    # change dir to pkg basedir
    os.chdir(os.path.abspath("%s/../.." % (changelog_fname)))

    # we need ubuntu as vendor to get the rebuild action
    dch_cmd = ["dch", "--rebuild", "--vendor=Tanglu", "-Dstaging", "%s" % (rebuild_info)]
    proc = subprocess.Popen(dch_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    output = ("%s\n%s") % (stdout, stderr)
    if (proc.returncode != 0):
        print(output)
        return False, None

    # update changelog - we want the new location, since dch might have changed it
    changelog_fname = find_changelog(tmp_workspace, pkg_name)
    if changelog_fname == None:
        return False, None

    # get version number (and possible other values later)
    with open(changelog_fname) as f:
        head = list(islice(f,6))
    m = re.search('\((.*?)\)', head[0])
    pkg_version_new = m.group(1)

    # recreate source file as original file
    os.chdir(tmp_workspace)
    os.remove(debian_src)
    debian_src_new = rreplace(debian_src, noEpoch(pkg_version_old), noEpoch(pkg_version_new))
    if archive_compression == "xz":
        with tarfile.open("%s.tmp" % (debian_src_new), 'w') as tar:
            tar.add(".", recursive=True)
        with open("%s.tmp" % (debian_src_new), 'rb') as f, open(debian_src_new, 'wb') as out:
            out.write(lzma.compress(bytes(f.read())))
    else:
        with tarfile.open(debian_src_new, "w:%s" % (archive_compression)) as tar:
            tar.add(".", recursive=True)

    os.chdir("/tmp")
    # cleanup workspace
    shutil.rmtree(tmp_workspace)

    # now update the dsc file
    new_dsc_content = []
    checksum = Checksum.Unknown
    debian_src_basename = os.path.basename(debian_src)
    dsc_lines = [line.rstrip("\n") for line in open(debian_dsc)]
    for line in dsc_lines:
        if line.startswith("Version: %s" % (pkg_version_old)):
            new_dsc_content.append("Version: %s" % (pkg_version_new))
            continue

        if line.startswith("Checksums-Sha1"):
            checksum = Checksum.Sha1
        if line.startswith("Checksums-Sha256"):
            checksum = Checksum.Sha256
        if line.startswith("Files"):
            checksum = Checksum.MD5

        # update the checksums & filenames
        if line.endswith(debian_src_basename):
            hash_str = get_file_hash(debian_src_new, checksum)
            size = os.path.getsize(debian_src_new)
            cs_line = " %s %s %s" % (hash_str, size, os.path.basename(debian_src_new))
            new_dsc_content.append(cs_line)
            continue

        new_dsc_content.append(line)

    debian_dsc_new = rreplace(debian_dsc, noEpoch(pkg_version_old), noEpoch(pkg_version_new))

    f = open(debian_dsc_new, 'w')
    f.write("\n".join(new_dsc_content))
    f.close()
    os.remove(debian_dsc)

    # now fix the signature
    debsign_cmd = ["debsign", "-k35DAD38D", "--re-sign", debian_dsc_new]
    proc = subprocess.Popen(debsign_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    output = ("%s\n%s") % (stdout, stderr)
    if (proc.returncode != 0):
        print(output)
        return False, None
    return True, debian_dsc_new
