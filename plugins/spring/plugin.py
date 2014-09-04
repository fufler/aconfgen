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

import os

from jinja2 import Template

from aconfgen import AconfgenPlugin

class AconfgenSpringPlugin(AconfgenPlugin):

    def __init__(self):
        self.dir = os.path.dirname(os.path.realpath(__file__))
        self.repo_context_template = Template(
            open(os.path.join(self.dir, 'templates', 'repository_context.xml')).read(),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def _create_model_deployer_parser(self, subparsers):
        parser = subparsers.add_parser(
            'spring-generate-model-deployer-bean',
            help='Generates model deployer Spring bean'
        )
        
        parser.add_argument(
            '--models-path-prefix',
            required=False,
            default=os.path.join('alfresco', 'extension', 'model', ''),
            help='Path in classpath where models are stored'
        )
        
        parser.add_argument(
            '--labels-path-prefix',
            required=False,
            default='alfresco.extension.messages.',
            help='Path in classpath where labels are stored'
        )
        
        parser.add_argument(
            '--model',
            required=False,
            action='append',
            default=[],
            help='Model file name to add to bean'
        )
        
        parser.add_argument(
            '--labels',
            required=False,
            action='append',
            default=[],
            help='Labels file name to add to bean'
        )

        parser.add_argument(
            '--id',
            required=True,
            help='Bean id'
        )
        
        parser.set_defaults(func=self.generate_repo_context)

        return parser

    def create_argument_parsers(self, subparsers):

        return [
            self._create_model_deployer_parser(subparsers)
        ]

    def generate_repo_context(self, args):
        
        labels = [args.labels_path_prefix+l for l in args.labels]
        models = [args.models_path_prefix+m for m in args.model]
        bean_id = args.id

        print(self.repo_context_template.render(
            locals()
        ))
