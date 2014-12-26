#!/usr/bin/python
# coding: utf-8

# TODO:
# - We should warn if the upstream version is less than the Ubuntu/Debian version (implying the download link is broken)
# - We should indicate if an upstream link is Ubuntu or Debian with an icon
# - We should track build dependencies
# - Track all GNOME packages we find
# - Versions like this aren't compared correctly - xfonts-mathml 4ubuntu1 (ubuntu) 6 (debian) 6 (upstream)

'''
 Copyright: Canonical Ltd
            Matthias Klumpp <mak@debian.org>
 Authors:   Sébastien Bacher <seb128@canonical.com>,
            Robert Ancell <robert.ancell@canonical.com>
            Matthias Klumpp <mak@debian.org>

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation; either version 2 of the License, or (at your
option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
the full text of the license.
'''

import time
start_time = time.time ()

import urllib2
import os, math, traceback, tempfile, re, sys
import threading, Queue
import subprocess

import apt_pkg
apt_pkg.init_system()

from packages import package_info, package_sets, DEBIAN, TANGLU, UNTRACKED, germinate_tags
from utils import compare_versions, load_germinate
from rapidumo.utils import debug

if 'PACKAGE_SET' in os.environ:
    PACKAGE_SET = os.environ['PACKAGE_SET']
else:
    PACKAGE_SET = 'all'

# this is a limited list of packages for quicker testing
# PACKAGE_SET = 'dummy'

debug ('Starting')

from rapidumo.pkginfo import *
from rapidumo.config import *
from rapidumo.utils import render_template

class Package:
    def __init__(self, name, stable_url, unstable_url):
        self.source = name
        self.tags = []
        self.on_cd = False
        self.stable_url = stable_url
        self.unstable_url = unstable_url
        self.is_debian_newer = False
        self.is_upstream_newer = False
        self.is_upstream_unstable_newer = False
        self.is_synchronised = False
        self.lp_bugs = []
        self.tanglu_version = None
        self.debian_version = None
        self.upstream_version = None
        self.upstream_version_link = None
        self.upstream_unstable_version = None
        self.upstream_unstable_version_link = None
        self.in_queue = False
        self.merges = []
        self.build_failures = []

debug ('Loading package list...')

pkg_sets = [PACKAGE_SET]
if PACKAGE_SET == "all":
    pkg_sets = package_sets

packages = {}
for pset in pkg_sets:
    for (name, stable_url, unstable_url) in package_info[pset]:
        packages[name] = Package(name, stable_url, unstable_url)

# components which don't have the same source name in debian and ubuntu
debian_naming_translation = {'firefox': 'iceweasel',
                             'thunderbird': 'icedove'}

tanglu_series = "chromodoris"
debian_unstable_series = "unstable"
debian_experimental_series = "experimental"

# Tag latest packages
debug ("Loading germinate output...")
def add_package (name, tag):
    if not packages.has_key (name):
        packages[name] = Package (name, UNTRACKED, None)
    if not tag in packages[name].tags:
        packages[p].tags.append (tag)
    packages[p].on_cd = True

for pset in pkg_sets:
    for tag, url in germinate_tags[pset].iteritems():
        url = url % {'series': tanglu_series}
        for p in load_germinate(url % {'series': tanglu_series}):
            add_package(p, tag)

# get configuration data
conf = RapidumoConfig()
_momArchivePath = conf.mom_config["path"]
_dest_distro = conf.distro_name
_extra_suite = conf.archive_config["devel_suite"]

pkginfo_tgl = SourcePackageInfoRetriever(_momArchivePath, _dest_distro, "staging", momCache=True)
pkginfo_tgl.extra_suite = _extra_suite
pkginfo_deb_unstable = SourcePackageInfoRetriever(_momArchivePath, "debian", "unstable", momCache=True)
pkginfo_deb_experimental = SourcePackageInfoRetriever(_momArchivePath, "debian", "experimental", momCache=True)
# we only care about packages in main here
pkgs_debian_unstable = pkginfo_deb_unstable.get_packages_dict("main")
pkgs_debian_experimental = pkginfo_deb_experimental.get_packages_dict("main")
pkgs_tanglu = pkginfo_tgl.get_packages_dict("main")

debug('Getting versions...')

class PackageThread (threading.Thread):
    def __init__ (self, queue, package):
        threading.Thread.__init__ (self)
        self.queue = queue
        self.package = package

    def run (self):
        # Get Tanglu version
        if self.package.source in pkgs_tanglu:
            self.package.tanglu_version = pkgs_tanglu[self.package.source].version
        else:
            debug ("Package %s not found in Tanglu!" % (self.package.source))

        # Get Debian version
        try:
            debian_source = debian_naming_translation.get (self.package.source, self.package.source)
            if debian_source in pkgs_debian_unstable:
                self.package.debian_version = pkgs_debian_unstable[debian_source].version
            else:
                self.package.debian_version = "0~"
            if debian_source in pkgs_debian_experimental:
                self.package.debian_version = self.max_version (self.package.debian_version, pkgs_debian_experimental[debian_source].version);
            self.package.debian_version = self.max_version (self.package.debian_version, self.get_svn_version ('experimental', debian_source));
            self.package.debian_version = self.max_version (self.package.debian_version, self.get_svn_version ('unstable', debian_source));
        except:
            debug (traceback.format_exc ())

        # Get upstream versions
        try:
            (self.package.upstream_version, self.package.upstream_unstable_version) = self.get_upstream_version ()
        except:
            debug (traceback.format_exc ())

        self.queue.put (self)

    def max_version (self, a, b):
        if self.compare_versions (a, b) > 0:
            return a
        else:
            return b

    def get_upstream_version (self):
        if self.package.stable_url is UNTRACKED:
            return ('UNKNOWN', None)
        elif self.package.stable_url is DEBIAN:
            return (self.package.debian_version, None)
        elif self.package.stable_url is TANGLU:
            return (self.package.tanglu_version, None)
        else:
            stable_version = self.get_url_version (self.package.stable_url)
            unstable_version = self.get_url_version (self.package.unstable_url)
            if unstable_version == stable_version:
                unstable_version = None
            return (stable_version, unstable_version)

    def get_url_version (self, url):
        if url is None:
            return None

        version = ''
        for line in self.get_regex_url (url[0]):
            for m in re.finditer (url[1], line):
                v = m.groups ()[0]

                # Ignore annoying alpha release that doesn't seem to be moving on
                if self.package.source == 'libtheora' and v == '1.2.0~alpha1':
                    continue

                # CD paranoia has an annoying naming scheme
                if self.package.source == 'cdparanoia':
                    v = '3.' + v

                # Sqlite has an annoying naming scheme
                if self.package.source == 'sqlite3':
                    v = '%d.%d.%d' % (int (v[0]), int (v[1:3]), int (v[3:5]))

                # Boost and ICU uses underscores for versioning
                if self.package.source == 'boost1.49' or self.package.source == 'icu':
                    v = v.replace ('_', '.')

                # aalib is stupidly versioned mangled by Debian
                if self.package.source == 'aalib':
                    v = v.replace ('rc', 'p')

                # portaudio has a mental naming scheme
                if self.package.source == 'portaudio19':
                    v = '19+svn' + v

                # ImageMagick has a weird naming scheme
                if self.package.source == 'imagemagick':
                    v = v.replace ('-', '.')

                # ntp has a 'p' naming system
                if self.package.source == 'ntp':
                    v = v.replace ('p', '.p')

                # mozjs naming...
                if self.package.source == 'mozjs':
                    v = v[0] + '.' + v[1] + '.' + v[2:]

                # We are checking glibc for eglibc and eglibc doesn't have the third number for some reason
                if self.package.source == 'eglibc' and v.endswith ('.0'):
                    v = v[:-2]

                if self.compare_versions (v, version) > 0:
                    version = v

        return version

    def get_regex_url (self, url):
        (server, tokens) = self.split_url (url)
        if len (tokens) == 1:
            return self.get_url (url)

        lines = self.get_url (server + tokens[0])
        dirs = []
        for line in lines:
            for m in re.finditer ('<a href=[\'"]([^\'"]*)[\'"]', line):
                href = m.groups()[0]
                if href.startswith (tokens[0] + '/'):
                    href = href[len(tokens[0]) + 1:]
                if href.endswith ('/'):
                    href = href[:-1]
                version = re.findall ('^%s$' % tokens[1], href)
                if len (version) == 0:
                    continue
                dirs.append ((href, version[0]))

        if len (dirs) == 0:
            return self.get_url (url)

        dirs.sort (cmp = self.compare_dirs, reverse = True)
        url = server + tokens[0] + '/' + dirs[0][0]
        if len (tokens) > 2:
            url += '/' + tokens[2]

        return self.get_url (url)

    def is_regex (self, text):
        return text.find ('(') >= 0 and text.find (')') >= 0

    def split_url (self, url):
        (protocol, path) = url.split ('://')
        try:
            (server, path) = path.split ('/', 1)
        except ValueError:
            return (url, [''])
        server = protocol + '://' + server

        if not url.startswith ('http://'):
            return (server, [path])

        dirs = path.split ('/')

        tokens = []
        path = ''
        for d in dirs:
            if not self.is_regex (d):
                path += '/' + d
            else:
                if path != '':
                    tokens.append (path)
                tokens.append (d)
                path = ''
        if path != '':
            tokens.append (path)

        return (server, tokens)

    def get_url (self, url):
        try:
            return urllib2.urlopen (url).readlines ()
        except IOError, e:
            self.error_text = 'Unable to open URL: %s, %s' % (url, e.strerror)
            return []

    def compare_dirs (self, a, b):
        (dirA, versionA) = a
        (dirB, versionB) = b
        return self.compare_versions (versionA, versionB)

    def compare_versions (self, v0, v1):
        if v0 is None:
            v0 = ''
        if v1 is None:
            v1 = ''
        t0 = v0.split ('.')
        t1 = v1.split ('.')
        for i in xrange (min (len (t0), len (t1))):
            try:
                d = cmp (int (t0[i]), int (t1[i]))
            except ValueError:
                d = cmp (t0[i], t1[i])
            if d != 0:
                return d
        return len (t0) - len (t1)

    def get_svn_version (self, series, debian_source):
        data = None
        for tree in ('packages', 'desktop', ):
            url = 'svn://svn.debian.org/svn/pkg-gnome/%s/%s/%s/debian/changelog' % (
                tree, series, debian_source)
        try:
            data = subprocess.check_output(['svn', 'cat', url, ' > /dev/null'], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            pass
        if not data:
            return ''

        versions = re.findall ('.* \\((.*)\\) .*; urgency=.*', data)
        if len (versions) == 0:
            return ''

        return versions[0]

package_names = packages.keys ()
package_names.sort ()

queue = Queue.Queue ()
count = 0
MAX_THREADS = 10
for name in package_names:
    package = packages[name]
    thread = PackageThread (queue, package)
    thread.start ()
    count += 1
    if count == MAX_THREADS:
        thread = queue.get ()
        debug ('  %s tanglu=%s debian=%s upstream=%s' % (thread.package.source, thread.package.tanglu_version, thread.package.debian_version, thread.package.upstream_version))
        count -= 1
for i in xrange (count):
    thread = queue.get ()
    debug ('  %s tanglu=%s debian=%s upstream=%s' % (thread.package.source, thread.package.tanglu_version, thread.package.debian_version, thread.package.upstream_version))

if 'DEBUG' in os.environ and os.environ['DEBUG'] == 'get':
    sys.exit(0)

debug('Comparing versions...')

for name in package_names:
    package = packages[name]
    if package.debian_version == package.tanglu_version:
        package.is_synchronised = True
    if compare_versions(package.debian_version, package.tanglu_version) > 0:
        package.is_debian_newer = True
    if package.upstream_version is None:
        debug ("Upstream version of %s was None!" % (name))
    else:
        if package.tanglu_version is None or compare_versions(apt_pkg.upstream_version(package.upstream_version), apt_pkg.upstream_version(package.tanglu_version)) > 0:
            package.is_upstream_newer = True
    if package.upstream_unstable_version is not None and \
       compare_versions(package.upstream_unstable_version, package.tanglu_version) > 0:
       # HACK? don't list gnome3 ppa version as uptodate, we don't want to overlook things
       # because they are only in the ppa, could be yet another section though
       # and (package.ubuntu_unstable_version is None or compare_versions(package.upstream_unstable_version, package.ubuntu_unstable_version) > 0):
        package.is_upstream_unstable_newer = True

def get_package_class(package):
    if package.stable_url == UNTRACKED or package.upstream_version == '':
        return 6
    elif package.is_upstream_newer and package.is_debian_newer:
        return 0
    elif package.is_upstream_newer and not package.is_synchronised:
        return 1
    elif package.is_upstream_newer and package.is_synchronised:
        return 2
    elif package.is_debian_newer:
        return 3
    elif package.is_upstream_unstable_newer:
        return 4
    else:
        return 5 # (should be fully up-to-date)

def cmp_package_failures(a, b):
    a_has_failures = len(a.build_failures) > 0
    b_has_failures = len(b.build_failures) > 0
    return cmp(b_has_failures, a_has_failures)

def cmp_package_merges(a, b):
    a_has_merges = len(a.merges) > 0
    b_has_merges = len(b.merges) > 0
    return cmp(b_has_merges, a_has_merges)

def cmp_package_class(a, b):
    return get_package_class(a) - get_package_class(b)

def cmp_package_name(a, b):
    return cmp(a.source, b.source)

def sort_by_status(a_name, b_name):
    a = packages[a_name]
    b = packages[b_name]

    if a.stable_url != UNTRACKED and a.upstream_version != '' and b.stable_url != UNTRACKED and b.upstream_version != '':
        # List build failures before successful builds
        z = cmp_package_failures(a, b)
        if z != 0:
            return z

        # List merges before non-merges
        z = cmp_package_merges(a, b)
        if z != 0:
            return z

    # List packages by most out-of-date to least out-of-date
    z = cmp_package_class(a, b)
    if z != 0:
        return z;

    # Finally, list by name
    return cmp_package_name(a, b)

# Categorise update state
sources = packages.keys ()
sources.sort (sort_by_status)
for source in sources:
    package = packages[source]

    if package.stable_url == UNTRACKED or package.upstream_version == '':
        package.style = 'untracked'
    elif package.is_upstream_newer:
        if package.is_synchronised:
            package.style = 'syncnewupstream'
        elif package.is_debian_newer:
            package.style = 'newboth'
        else:
            package.style = 'newupstream'
    else:
        if package.is_debian_newer:
            package.style = 'newdebian'
        elif package.is_upstream_unstable_newer:
            package.style = 'newunstable'
        else:
            package.style = 'uptodate'

end_time = time.time ()
duration = end_time - start_time
n_minutes = duration // 60
n_seconds = int (duration - 60 * n_minutes)

def generate_page (tags = [], invert = False):
    html = '''<table class="table">
<tr>
<th><b>Package</b></th>
<th><b>Tanglu</b></th>
<th><b>Debian</b></th>
<th><b>Upstream version</b></th>
<th><b>Status</b></th>
</tr>
'''

    debug('Building table...')
    style_total = 0
    style_count = {}
    for source in sources:
        package = packages[source]

        have_tag = False
        for tag in tags:
            if tag in package.tags:
                have_tag = True
        if invert:
            have_tag = not have_tag
        if not have_tag:
            continue

        try:
            style_count[package.style] += 1
        except KeyError:
            style_count[package.style] = 1
        style_total += 1

        html += '<tr class="%s">\n' % package.style

        status = ""
        # TODO: Adjust for Tanglu bugs!
        #if len(package.lp_bugs) > 0:
            #bug_text = []
            #for (number, importance, assignee, fix_committed) in package.lp_bugs:
                #img = 'https://launchpad.net/@@/bug-%s' % importance.lower()
                #if fix_committed:
                    #color_link = 'style="color:grey"'
                #else:
                    #color_link = ''

                #text = '<a href="https://launchpad.net/bugs/%s" %s>' % (number, color_link)
                #text += '<img alt="" src="%s" />%s</a>' % (img, number)
                #if assignee is not None:
                    #text += '<br/><a href="https://launchpad.net/~%s" %s>' % (assignee, color_link)
                    #text += '<img alt="" src="https://launchpad.net/@@/person" />%s' % assignee
                    #text += '</a>'
                #bug_text.append(text)
            #status += ', '.join(bug_text)
        #elif package.tanglu_version == '':
            #status += '<a href="https://launchpad.net/ubuntu/+filebug?field.title=[needs-packaging] %s&field.tags=needs-packaging&no-redirect">' % package.source
            #status += 'Open Bug...'
            #status += '</a>'
        #elif package.is_upstream_newer:
            #status += '<a href="https://launchpad.net/ubuntu/+source/%s/+filebug?field.title=Update to %s&field.tags=upgrade-software-version&no-redirect">' % (package.source,package.upstream_version)
            #status += 'Open Bug...'
            #status += '</a>'
        #elif package.is_debian_newer:
            #status += '<a href="https://launchpad.net/ubuntu/+source/%s/+filebug?field.title=Merge with Debian %s&field.tags=upgrade-software-version&no-redirect">' % (package.source,package.debian_version)
            #status += 'Open Bug...'
            #status += '</a>'

        html += '  <td>\n'
        html += '    <img alt="" src="https://launchpad.net/@@/package-source" />\n'
        html += '    <a href="http://packages.tanglu.org/source/%s">%s</a>\n' % (package.source, package.source)
        html += '  </td>\n'
        # version = '<a class="versionlink" href="http://launchpad.net/ubuntu/+source/%s/%s">%s</a>' % (package.source, package.tanglu_version, package.tanglu_version)
        # FIXME: Add Tanglu PTS link instead!
        version = '<a class="versionlink" href="http://buildd.tanglu.org/source/default/%s/%s/">%s</a>' % (package.source, package.tanglu_version, package.tanglu_version)
        if package.in_queue:
            version = '%s Q' % version
        for (arch, url) in package.build_failures:
            version += '<img src="https://launchpad.net/@@/build-failed"/><a href="%s">%s</a>' % (url, arch)
        for merge in package.merges:
            version += '<a href="%s"><img src="https://launchpad.net/@@/branch"/></a>' % merge

        html += '  <td>%s</td>\n' % version
        #FIXME: Doesn't correct things like iceweasel and gdm3
        html += '  <td><a class="versionlink" href="http://ftp-master.metadata.debian.org/changelogs/main/%c/%s/%s_%s_changelog">%s</a>' % (package.source[0], package.source, package.source, package.debian_version, package.debian_version)
        html += '&nbsp;(<a href="https://tracker.debian.org/pkg/%s">PTS</a>)</td>\n' % (package.source)
        version = package.upstream_version
        if package.upstream_version_link is not None:
            version = '<a class="versionlink" href="%s">%s</a>' % (package.upstream_version_link, version)
        if package.upstream_unstable_version is not None:
            unstable_version = package.upstream_unstable_version
            if package.upstream_unstable_version_link is not None:
                unstable_version = '<a class="versionlink" href="%s">%s</a>' % (package.upstream_unstable_version_link, unstable_version)
            version = '%s / %s' % (version, unstable_version)
        html += '  <td>%s</td>\n' % version
        html += '  <td>%s</td>\n' % status

    html += """
<tr class='spacing'><td><br></td>
<tr class='untracked'><td colspan='5'>Untracked packages</td>
<tr class='uptodate'><td colspan='5'>Tanglu package is latest upstream</td>
<tr class='newunstable'><td colspan='5'>New unstable version available</td>
<tr class='newdebian'><td colspan='5'>Newer version available in Debian</td>
<tr class='syncnewupstream'><td colspan='5'>Synchronised with Debian but newer version available upstream</td>
<tr class='newupstream'><td colspan='5'>Unsynchronised and newer version available upstream</td>
<tr class='newboth'><td colspan='5'>Newer upstream and Debian versions available</td>
<tr class='spacing'><td><br></td>
<tr class='newboth' style="color:grey"><td colspan='5'>Associated bug in "Fix Committed" state</td>
<tr class='spacing'><td><br></td>
</table>
"""

    # Pie chart of status
    SIZE = 200
    offset = 0
    styles = [('uptodate', '#bcfc7e'), ('newunstable', '#ddfd7f'), ('newdebian', '#ffff80'), ('syncnewupstream', '#ffd280'), ('newupstream', '#ffb97f'), ('newboth', '#ffa17e'), ('untracked', '#e0e0e0')]
    html += '<svg with="%d" height="%d">\n' % (SIZE, SIZE)
    for (name, color) in styles:
        r = SIZE * 0.5
        if not style_count.has_key (name):
            continue
        step = style_count[name]
        a0 = 2 * math.pi * offset / style_total
        a1 = 2 * math.pi * (offset + step) / style_total
        large_arc = 0
        if a1 - a0 > math.pi:
            large_arc = 1
        x0 = r + r * math.sin (a0)
        y0 = r + r * math.cos (a0)
        x1 = r + r * math.sin (a1)
        y1 = r + r * math.cos (a1)
        html += '<path d="M%f,%f L%f,%f A%f,%f 0 %d,0 %r,%r" fill="%s"/>\n' % (r, r, x0, y0, r, r, large_arc, x1, y1, color)
        offset += step
    html += '</svg>\n'

    # Warn about packages without tags
    untagged_packages = []
    for p in packages:
        if len (packages[p].tags) == 0:
            untagged_packages.append (packages[p].source)
    untagged_packages.sort ()
    if len (untagged_packages) > 0:
        html += '<p>\n'
        html += '<a href="untagged.html">Untagged packages</a> (%d):<br>\n' % len (untagged_packages)
        for (n, p) in enumerate (untagged_packages):
            if n != 0:
                html += ', '
            html += '<a href="http://packages.tanglu.org/source/%s">%s</a>' % (p, p)
        html += '</p>\n'

    foot_html = '<p>\n'
    foot_html += 'Last updated: %s, took %d minutes, %d seconds<br>\n' % (time.strftime('%A %B %d %Y %H:%M:%S %z'), n_minutes, n_seconds)
    foot_html += '</p>\n'
    foot_html += '<p style="font-size: xx-small;">These pages are generated by pkgcheck (part of Rapidumo) (<a href="http://gitorious.org/tanglu/rapidumo">sources</a>). It contains code originally written for Ubuntu.\n'
    foot_html += '</p>\n'

    return html, foot_html

def write_page (name, section_label, tags = [], invert = False):
    html, foot_html = generate_page (tags, invert)
    render_template("package-watch/pkgwatch.html", name,
                page_name="pkg-watch", content=html, extra_footer=foot_html, section_label=section_label)
    debug('Wrote %s' % name)

tags = []
for p in packages:
    for t in packages[p].tags:
        if not t in tags:
            tags.append (t)

write_page ('package-watch/versions.html', "versions", [], True)
write_page ('package-watch/base.html', "base", ['minimal', 'standard'])
write_page ('package-watch/minimal.html', "minimal", ['minimal'])
write_page ('package-watch/standard.html', "standard", ['standard'])
write_page ('package-watch/desktop-common.html', "desktop-common", ['desktop-common', 'desktop-common.build-depends'])
write_page ('package-watch/gnome.html', "gnome", ['gnome'])
write_page ('package-watch/kde.html', "kde", ['kde'])
write_page ('package-watch/untagged.html', "untagged", tags, True)
