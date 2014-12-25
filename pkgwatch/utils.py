#!/usr/bin/python
# coding: utf-8

import apt_pkg
import urllib
from rapidumo.utils import debug

# Strip epoch from version number
def non_epoch_version(version):
    try:
        return version.split(':', 1)[1]
    except IndexError:
        return version

def compare_versions(versionA, versionB):
    if versionA is None or versionA == '':
        return -1
    if versionB is None or versionB == '':
        return 1
    return apt_pkg.version_compare(non_epoch_version(versionA), non_epoch_version(versionB))

url_cache = {}
def get_url(url):
    try:
        return url_cache[url]
    except KeyError:
        pass

    try:
        data = urllib.urlopen(url)
    except IOError, e:
        debug('Unable to open URL: %s, %s' % (url, e.strerror))
        return []

    lines = data.readlines ()
    url_cache[url] = lines
    return lines

def load_germinate(url):
    packages = []
    for (n, line) in enumerate(get_url(url)):
        # Skip headings
        if n == 0:
            continue

        try:
            if not line[0].isalpha():
                continue
            package = line.split('|')[1].strip()
            if not package in packages:
                packages.append(package)
        except IndexError:
            continue
    return packages
