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

import re
import os

from lxml import etree
from jinja2 import Template

from aconfgen import AconfgenPlugin

class AconfgenWorkflowPlugin(AconfgenPlugin):

    def __init__(self):
        self.dir = os.path.dirname(os.path.realpath(__file__))
        self.bpmn_schema = etree.XMLSchema(file=os.path.join(self.dir, 'schemas', 'BPMN20.xsd'))
        self.bpmn_parser = etree.XMLParser(schema=self.bpmn_schema)
        self.model_template = Template(
            open(os.path.join(self.dir, 'templates', 'model.xml')).read(),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def create_argument_parsers(self, subparsers):
        parser = subparsers.add_parser(
            'workflow-generate-model',
            help='Generates task model for specified process definition'
        )
        parser.add_argument(
            '--file',
            required=True,
            help='File name to load process definition from'
        )
        parser.add_argument(
            '--with-metadata',
            action='store_true',
            help='Generate task model metadata'
        )
        parser.add_argument(
            '--with-mandatory-aspects',
            action='store_true',
            help='Generate mandatory aspects section for each type'
        )
        parser.add_argument(
            '--with-aspects',
            action='store_true',
            help='Generate custom aspect definition section'
        )
        parser.set_defaults(func=self.generate_task_model)

        return [parser]

    def generate_task_model(self, args):
        tree = etree.parse(args.file, self.bpmn_parser)
        ns = {
            'dn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
            'activiti': 'http://activiti.org/bpmn'
        }
        xpath = etree.XPathEvaluator(tree, namespaces=ns)
        types = []
        formKey = '{%s}formKey' % ns['activiti']
        startEvent = '{%s}startEvent' % ns['dn']
        for el in xpath('/dn:definitions/dn:process//*[@activiti:formKey]'):
            types.append({
                'name': el.attrib[formKey],
                'start': el.tag == startEvent
            })
        pname = xpath('/dn:definitions/dn:process/@name')[0]
        mname = '%s_task_model' % re.sub(r'\W', '_', pname.lower())
        prefixes = list(set([x['name'].split(':')[0] for x in types]))
        print(self.model_template.render(
            types=types,
            version=1.0,
            author=os.getlogin(),
            prefixes=prefixes,
            prefix=prefixes[0],
            name=mname,
            description='Auto-generated task model for "%s" process' % pname,
            with_aspects=args.with_aspects,
            with_mandatory_aspects=args.with_mandatory_aspects,
            with_metadata=args.with_metadata
        ))
