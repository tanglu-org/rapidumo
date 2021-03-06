#!/usr/bin/python3
# Copyright (C) 2015 Matthias Klumpp <mak@debian.org>
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
import sys
import subprocess
import select
import gzip
import lzma
from .. import RapidumoConfig


class DebianMirror:

    def __init__(self):
        self._conf = RapidumoConfig()
        self._mirrordir = self._conf.synchrotron_config.get('debian_mirror')

    def update(self):
        targetdir = self._mirrordir
        if not targetdir:
            print("No syncing Debian sources: No mirror target found!")
            return False

        host = 'ftp.de.debian.org'
        method = 'rsync'
        dists = 'testing,unstable,experimental'
        sections = 'main,contrib,non-free'
        debug = self._conf.debug_enabled

        cmd = ['debmirror', '--source', "--section="+sections,
                '--host='+host, '--dist='+dists, '--arch=none',
                '--root=/debian', '--diff=none', '--method='+method,
                '--keyring=/usr/share/keyrings/debian-archive-keyring.gpg']
        if debug:
            cmd.append('--verbose')
        cmd.append(targetdir)

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while True:
            reads = [proc.stdout.fileno(), proc.stderr.fileno()]
            ret = select.select(reads, [], [])

            for fd in ret[0]:
                if fd == proc.stdout.fileno():
                    read = proc.stdout.readline()
                    if debug:
                        sys.stdout.write(str(read, 'utf-8'))
                if fd == proc.stderr.fileno():
                    read = proc.stderr.readline()
                    if debug:
                        sys.stderr.write(str(read, 'utf-8'))

            if proc.poll() != None:
                break

        if proc.returncode == 0:
            # workaround to have GZip files for Debian experimental (until dose3 support XZ natively)
            for section in sections.split(','):
                basepath = os.path.join(targetdir, 'dists', 'experimental', section, 'source')
                sfile = os.path.join(basepath, 'Sources.xz')
                tfile = os.path.join(basepath, 'Sources.gz')
                if not os.path.isfile(sfile):
                    continue
                sf = lzma.open(sfile, 'r')
                tf = gzip.open(tfile, 'wb')
                tf.write(sf.read())
                tf.close()
                sf.close()
            return True
        return False
