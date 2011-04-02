#!/bin/env python2
# Copyright (C) 2011 Alex Ermakov
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

# import section
import argparse
import os
import re
from xml.dom.minidom import parse, parseString, getDOMImplementation


# prints xml, formats it if needed
def printXml(dom, pretty):
  if pretty:
    # format ouput with xmllint
    (xmllint_stdin, xmllint_stdout) = os.popen2('xmllint --format -')
    xmllint_stdin.write(dom.toxml(encoding='UTF-8'))
    xmllint_stdin.close()
    print(xmllint_stdout.read())
  else:
    print(dom.toxml(encoding='UTF-8'))

# creates new tag with text node inside
def createTagWithText(dom, tagName, content):
  tag = dom.createElement(tagName)
  tag.appendChild(dom.createTextNode(content))
  return tag

# create argument parser
parser = argparse.ArgumentParser(description='Generates skeleton of some Alfresco configuration files basing on process definition XML.')

positionalArgs = parser.add_argument_group('positional arguments')
positionalArgs.add_argument('file', metavar='procdef', help='XML file, containing process definition in jPDL')

configTypeArgs = parser.add_argument_group('config type arguments')
configTypeArgs.add_argument('-s', '--swimlanes', action='store_true', help='generate swimlane tags for process definition')
configTypeArgs.add_argument('-m', '--model', action='store_true', help='generate skeleton of workflow model XML')
configTypeArgs.add_argument('-S', '--share', action='store_true', help='generate skeleton of share-config-custom.xml for UI elements rendering')


modelArgs = parser.add_argument_group('model generation options')
modelArgs.add_argument('-M', '--mandatory-aspects', action='store_true', help='add mandatory-aspects section to each workflow model type')
modelArgs.add_argument('-i', '--item-actions', action='store_true', help='add item-actions section to each workflow model type')
modelArgs.add_argument('-a', '--aspects', action='store_true', help='add dummy aspect definition section')


outputArgs = parser.add_argument_group('output arguments')
outputArgs.add_argument('-f', '--format', action='store_true', help='format output using xmllint')
outputArgs.add_argument('-c', '--comments', action='store_true', help='add comments to result XML')


# parse arguments
args = parser.parse_args()


# standard namespaces to import 
imports = {'d' : 'http://www.alfresco.org/model/dictionary/1.0', 'bpm' : 'http://www.alfresco.org/model/bpm/1.0', 'cm' : 'http://www.alfresco.org/model/content/1.0'}

# load xml
procdef = parse(args.file)

# get implementation
impl = getDOMImplementation()

if args.swimlanes:
  # generate swimlane tags
  swimlanes = [] 
  # get all tasks
  tasks = procdef.getElementsByTagName('task')
  # iterate through all tasks and create list of swimlanes
  for task in tasks:
    # check if swimlane tag is specified
    if 'swimlane' in task.attributes.keys():
      swimlane = task.attributes['swimlane'].value
      if not (swimlane in swimlanes):
        swimlanes.append(swimlane)
  # iterate throught list of swimlanes and build corresponding tags
  for swimlane in swimlanes:
    swimlaneTag = procdef.createElement('swimlane')
    swimlaneTag.attributes['name'] = swimlane
    if swimlane != 'initiator':
      assignmentTag = procdef.createElement('assignment')
      assignmentTag.attributes['class'] = 'org.alfresco.repo.workflow.jbpm.AlfrescoAssignment'
      assignmentTag.appendChild(createTagWithText(procdef, 'actor', '#{'+swimlane+'}'))
      swimlaneTag.appendChild(assignmentTag)
    procdef.childNodes[0].insertBefore(swimlaneTag, procdef.childNodes[0].childNodes[0])
  # print result
  printXml(procdef, args.format)

if args.model:
  # generate workflow model
  model = impl.createDocument(None, 'model', None)
  modelTag = model.childNodes[0]
  modelTag.attributes['xmlns'] = 'http://www.alfresco.org/model/dictionary/1.0'
  # metadata
  if args.comments:
    modelTag.appendChild(model.createComment('Model metadata'))
  modelTag.appendChild(createTagWithText(model, 'description', 'Generated workflow model skeleton'))
  modelTag.appendChild(createTagWithText(model, 'author', os.getenv('USER')))
  modelTag.appendChild(createTagWithText(model, 'version', '0.1'))
  if args.comments:
    modelTag.appendChild(model.createComment('Standard import section'))
  # imports section
  importsTag = model.createElement('imports')
  for imp in imports:
    importTag = model.createElement('import')
    importTag.attributes['uri'] = imports[imp]
    importTag.attributes['prefix'] = imp
    importsTag.appendChild(importTag)
  modelTag.appendChild(importsTag)
  # iterate throught tasks and build namespaces and type tags
  namespaces = []
  tasks = procdef.getElementsByTagName("task")
  typesTag = model.createElement('types')
  for task in tasks:
    taskName = task.attributes["name"].value
    # add namespace to list
    namespace = re.search('^(.+):(.*)$', taskName).group(1)
    if not namespace in namespaces:
      namespaces.append(namespace)
    # build type tag
    typeTag = model.createElement('type')
    typeTag.attributes['name'] = taskName
    # add parent tag
    if args.comments:
      typesTag.appendChild(model.createComment('Type for '+taskName))
    typesTag.appendChild(typeTag)
    if task.parentNode.tagName == 'start-state':
      parentText = 'bpm:startTask'
    else:
      parentText = 'bpm:workflowTask'
    if args.comments:
      typeTag.appendChild(model.createComment('Type parent'))
    typeTag.appendChild(createTagWithText(model, 'parent', parentText))
    # add override section
    if args.item_actions:
      if args.comments:
        typeTag.appendChild(model.createComment('Override default package item actions'))
      overridesTag = model.createElement('override')
      propertyTag = model.createElement('property')
      propertyTag.attributes['name'] = 'bpm:packageItemActionGroup'
      propertyTag.appendChild(createTagWithText(model, 'default', 'edit_package_item_actions'))
      overridesTag.appendChild(propertyTag)
      typeTag.appendChild(overridesTag)
    # add mandatory aspects section
    if args.mandatory_aspects:
      if args.comments:
        typeTag.appendChild(model.createComment('Add mandatory ascpects'))
      mandatoryAspectsTag = model.createElement('mandatory-aspects')
      mandatoryAspectsTag.appendChild(createTagWithText(model, 'aspect', namespaces[0]+':customAspect'))
      typeTag.appendChild(mandatoryAspectsTag)

  # update model name
  modelTag.attributes['name'] = namespaces[0]+':'+procdef.childNodes[0].attributes['name'].value+'Model'
  # generate namespaces tag
  namespacesTag = model.createElement("namespaces")
  for namespace in namespaces:
    namespaceTag = model.createElement("namespace")
    namespaceTag.attributes["prefix"] = namespace
    namespaceTag.attributes["uri"] = 'http://some.uri/namespaces/'+namespace
    namespacesTag.appendChild(namespaceTag)
  # generate aspects tag
  if args.aspects:
    aspectsTag = model.createElement('aspects')
    aspectsTag.appendChild(model.createComment('Custom aspect'))
    aspectTag = model.createElement('aspect')
    aspectTag.attributes['name'] = namespaces[0]+':customAspect'
    aspectTag.appendChild(createTagWithText(model, 'title', 'Custom Aspect'))
    propertiesTag = model.createElement('properties')
    propertyTag = model.createElement('property')
    propertyTag.attributes['name'] = namespaces[0]+':customProperty'
    propertyTag.appendChild(createTagWithText(model, 'type', 'd:string'))
    propertyTag.appendChild(createTagWithText(model, 'mandatory', 'false'))
    propertyTag.appendChild(createTagWithText(model, 'multiple', 'false'))
    propertiesTag.appendChild(propertyTag)
    aspectTag.appendChild(propertiesTag)
    aspectsTag.appendChild(aspectTag)

  # add tags
  if args.comments:
    modelTag.appendChild(model.createComment('Generated list of found namespaces'))
  modelTag.appendChild(namespacesTag)
  if args.comments:
    modelTag.appendChild(model.createComment('Generated list of types'))
  modelTag.appendChild(typesTag)
  if args.aspects:
   if args.comments:
     modelTag.appendChild(model.createComment('Generated list of aspects'))
   modelTag.appendChild(aspectsTag)
  # print result
  printXml(model, args.format)
