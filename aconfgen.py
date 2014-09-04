#!/usr/bin/python3
# Copyright (C) 2014 Alexey Ermakov
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

import sys
import os
import argparse
import imp
import inspect

# FIXME
ACONFGEN_HOME = os.path.dirname(os.path.realpath(__file__))
sys.path.append(ACONFGEN_HOME)

PLUGIN_PATHS = [os.path.join(ACONFGEN_HOME, 'plugins')]

from plugin import AconfgenPlugin


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates Alfresco configuration files')
    subparsers = parser.add_subparsers(help='List of available sub-commands')

    for plugin_path in PLUGIN_PATHS:
        for root, _, files in os.walk(plugin_path):
            for name in files:
                if name.lower().endswith('.py'):
                    mpath = os.path.join(root, name)
                    m = imp.load_source(mpath[:-3], mpath)
                    for name, obj in inspect.getmembers(m):
                        if inspect.isclass(obj) and issubclass(obj, AconfgenPlugin) and obj != AconfgenPlugin:
                            pl = obj()
                            pl.create_argument_parsers(subparsers)

    args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_usage()
    else:
        args.func(args)
