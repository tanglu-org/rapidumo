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

import os
from rapidumo.config import RapidumoConfig
from jinja2 import Environment, FileSystemLoader

# set up templates
template_dir = os.path.dirname(os.path.realpath(__file__))
template_dir = os.path.realpath(os.path.join(template_dir, "..", "templates"))
j2_env = Environment(loader=FileSystemLoader(template_dir))

# check if we are in debug mode
debug_enabled = False
if 'DEBUG' in os.environ:
    debug_enabled = True

def render_template(name, out_name = None, *args, **kwargs):
    config = RapidumoConfig()
    gcfg = config.general_config
    out_dir = gcfg['html_output']

    if not out_name:
        out_path = os.path.join(out_dir, name)
    else:
        out_path = os.path.join(out_dir, out_name)
    # create subdirectories if necessary
    out_dir = os.path.dirname(os.path.realpath(out_path))
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    template = j2_env.get_template(name)
    content = template.render(*args, **kwargs)
    f = open(out_path, 'w')
    f.write(content)
    f.close()

def debug(text):
    if debug_enabled:
        print(text)
