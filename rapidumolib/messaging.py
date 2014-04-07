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

try:
    import fedmsg
except ImportError:
    fedmsg = None

from rapidumolib.config import RapidumoConfig


if fedmsg:
    config = RapidumoConfig()
    fmcfg = config.fedmsg_config

    fedmsg.init(
        topic_prefix=fmcfg.get("prefix", "org.tanglu"),
        environment=fmcfg.get("environment", "dev"),
        sign_messages=fmcfg.get("sign", False),
        endpoints=fmcfg.get("endpoints", {}),
    )


def emit_raw(component, modname, topic, message):
    modname = "%s.%s" % (component, modname)
    if fedmsg:
        return fedmsg.publish(topic=topic, modname=modname, msg=message)
