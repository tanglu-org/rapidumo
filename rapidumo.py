#!/usr/bin/python
# Copyright (C) 2014 Matthias Klumpp <mak@debian.org>
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
import codecs
import re
from optparse import OptionParser

from rapidumo.pkginfo import *
from rapidumo.utils import *
from rapidumo.config import *

class RapidumoPageRenderer:
    def __init__(self, suite = ""):
        self._conf = RapidumoConfig()

    def _render_britney_output(self):
        britney_out = self._conf.general_config['britney_output_dir']
        britney_out = os.path.join(britney_out, "update_output.txt")
        f = open(britney_out, "r")
        styled_text = ""
        for line in f:
            s = line.replace("accepted: ", "<font color=\"green\">accepted</font>: ")
            s = s.replace("skipped: ", "<font color=\"orange\">skipped</font>: ")
            s = s.replace("SUCCESS", "<font color=\"lime\">SUCCESS</font>")
            s = s.replace("FAILED", "<font color=\"red\">FAILED</font>")
            s = s.replace("success: ", "<font color=\"lime\">success</font>: ")
            s = s.replace("failed: ", "<font color=\"red\">failed</font>: ")
            s = s.replace("Trying force-hint", "Trying <font color=\"indianred\">force-hint</font>")

            styled_text += "%s<br/>" % (s)

        render_template("migrations/britney_output.html", page_name="migrations", britney_result="output",
                    britney_output=styled_text)

    def _render_britney_excuses(self):
        britney_exc = self._conf.general_config['britney_output_dir']
        britney_exc = os.path.join(britney_exc, "update_excuses.html")
        f = codecs.open(britney_exc, 'r', encoding='utf-8')
        exc_html = f.read()
        m = re.findall('<body>(.*?)</body>', exc_html, re.DOTALL)
        exc_html = m[0]

        render_template("migrations/britney_excuses.html", page_name="migrations", britney_result="excuses",
                    britney_excuses=exc_html)

    def refresh_page(self, page_name):
        if page_name == "static":
            render_template("index.html", page_name="start")
            render_template("pkg-watch.html", page_name="pkg-watch")
            render_template("synchrotron/index.html", page_name="sync-report")
        elif page_name == "migrations":
            self._render_britney_output()
            self._render_britney_excuses()
        else:
            print("Unknown page name: %s" % (page_name))

def main():
    parser = OptionParser()
    parser.add_option("-r", "--refresh-page",
                  type="string", dest="refresh_page", default=None,
                  help="refresh a GUI page")

    (options, args) = parser.parse_args()

    if options.refresh_page:
        helper = RapidumoPageRenderer()
        helper.refresh_page(options.refresh_page)
    else:
        print("Run with --help for a list of available command-line options!")

if __name__ == "__main__":
    os.environ['LANG'] = 'C'
    os.environ['LC_ALL'] = 'C'
    main()
