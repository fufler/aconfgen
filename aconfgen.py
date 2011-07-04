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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.	If not, see <http://www.gnu.org/licenses/>.

# import section
import argparse
import os
import subprocess
import sys
import re
from xml.dom.minidom import parse, parseString, getDOMImplementation


# prints xml, formats it if needed
def printXml(dom, pretty):
	if pretty:
		# format ouput with xmllint
		xmllint = subprocess.Popen(['xmllint', '--format', '-'], stdin=subprocess.PIPE, stdout=sys.stdout);
		xmllint.stdin.write(dom.toxml(encoding='UTF-8'))
		xmllint.stdin.close()
	else:
		print(dom.toxml(encoding='UTF-8'))

# validates XML using schema
def isValid(xmlString, schemaFile):
	# open /dev/null
	devNull = open('/dev/null', 'w')
	xmllint = subprocess.Popen(['xmllint', '--schema', schemaFile, '--noout', '-'], stdin=subprocess.PIPE, stdout=devNull, stderr=devNull)
	xmllint.stdin.write(xmlString);
	xmllint.stdin.close()
	return not xmllint.wait()

def generateSwimlaneTags():
	# load xml
	try:
		procdef = parse(args.file)
	except Exception, e:
		print('can\'t parse XML, terminating.');
		sys.exit(1)

	# validate XML
	schema1 = os.path.join(scriptPath, 'schemas','jpdl-3.1.xsd')
	schema2 = os.path.join(scriptPath, 'schemas','jpdl-3.2.xsd')
	if not isValid(procdef.toxml(encoding='UTF-8'), schema1) and not isValid(procdef.toxml(encoding='UTF-8'), schema2):
		print('XML validation failed, terminating.')
		sys.exit(1)

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
		deftag = procdef.getElementsByTagName('process-definition')[0]
		if len(deftag.childNodes):
			reftag = deftag.childNodes[0]
		else:
			reftag = None
		deftag.insertBefore(swimlaneTag, reftag)
		# add comment
		if args.comments:
			deftag.insertBefore(procdef.createComment(swimlane+' swimlane'), swimlaneTag)
	# return result
	return procdef

# generates workflow model
def generateModel():
	# load xml
	try:
		procdef = parse(args.file)
	except Exception, e:
		print('can\'t parse XML, terminating.');
		sys.exit(1)

	# validate XML
	schema1 = os.path.join(scriptPath, 'schemas','jpdl-3.1.xsd')
	schema2 = os.path.join(scriptPath, 'schemas','jpdl-3.2.xsd')
	if not isValid(procdef.toxml(encoding='UTF-8'), schema1) and not isValid(procdef.toxml(encoding='UTF-8'), schema2):
		print('XML validation failed, terminating.')
		sys.exit(1)

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
	modelTag.attributes['name'] = namespaces[0]+':'+procdef.getElementsByTagName('process-definition')[0].attributes['name'].value+'Model'
	# generate namespaces tag
	namespacesTag = model.createElement("namespaces")
	for namespace in namespaces:
		namespaceTag = model.createElement("namespace")
		namespaceTag.attributes["prefix"] = namespace
		namespaceTag.attributes["uri"] = 'https://github.com/fufler/aconfgen/namespaces/'+namespace
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
	# return result
	return model

# generates share-config-custom XML
def generateShareConfig():
	# load xml
	try:
		model = parse(args.file)
	except Exception,e:
		print('can\'t parse XML, terminating.');
		sys.exit(1)

	# validate XML
	schema = os.path.join(scriptPath, 'schemas','modelSchema.xsd')
	if not isValid(model.toxml(encoding='UTF-8'), schema):
		print('XML validation failed, terminating.')
		sys.exit(1)

	# generate share config
	config = impl.createDocument(None, 'alfresco-config', None)
	alfConfigTag = config.childNodes[0]
	typesTag = model.getElementsByTagName('types')[0]
	types = typesTag.getElementsByTagName('type')
	# generate interface elements for tasks
	for typeItem in types:
		configTag = config.createElement('config')
		configTag.attributes['evalutor'] = 'task-type'
		configTag.attributes['condition'] = typeItem.attributes['name'].value
		formsTag = config.createElement('forms')
		formTag = config.createElement('form')
		fieldVisibilityTag = config.createElement('field-visibility')
		appearanceTag = config.createElement('appearance')
		# iterate throught all aspects
		mandatoryAspects = typeItem.getElementsByTagName('mandatory-aspects')
		if len(mandatoryAspects) == 1:
			mandatoryAspects = mandatoryAspects[0]
			for aspectItem in mandatoryAspects.getElementsByTagName('aspect'):
				showTag = config.createElement('show')
				print(aspectItem)
				showTag.attributes['id'] = aspectItem.childNodes[0].nodeValue
				fieldVisibilityTag.appendChild(showTag)
	   
		formTag.appendChild(fieldVisibilityTag)
		formTag.appendChild(appearanceTag)
		formsTag.appendChild(formTag)
		configTag.appendChild(formsTag)
		if args.comments:
			alfConfigTag.appendChild(config.createComment('config for '+configTag.attributes['condition'].value))
		alfConfigTag.appendChild(configTag)
	# return result
	return config

# creates new tag with text node inside
def createTagWithText(dom, tagName, content):
	tag = dom.createElement(tagName)
	tag.appendChild(dom.createTextNode(content))
	return tag

# create argument parser
parser = argparse.ArgumentParser(description='Generates skeleton of some Alfresco configuration files basing on process definition XML.')

positionalArgs = parser.add_argument_group('positional arguments')
positionalArgs.add_argument('file', metavar='XML', default=sys.stdin, nargs='?', help='XML file, containing process definition in jPDL or workflow model')

exclusiveTypeArgs = parser.add_mutually_exclusive_group(required=True)
exclusiveTypeArgs.add_argument('-s', '--swimlanes', action='store_true', help='generate swimlane tags for process definition')
exclusiveTypeArgs.add_argument('-m', '--model', action='store_true', help='generate skeleton of workflow model XML')
exclusiveTypeArgs.add_argument('-S', '--share', action='store_true', help='generate skeleton of share-exclusive-custom.xml for UI elements rendering')

modelArgs = parser.add_argument_group('model generation options')
modelArgs.add_argument('-M', '--mandatory-aspects', action='store_true', help='add mandatory-aspects section to each workflow model type')
modelArgs.add_argument('-i', '--item-actions', action='store_true', help='add item-actions section to each workflow model type')
modelArgs.add_argument('-a', '--aspects', action='store_true', help='add dummy aspect definition section')

configArgs = parser.add_argument_group('share config generation options')
configArgs.add_argument('-n', '--process-name', action='store_true', help='workflow process name to use in generated config')

outputArgs = parser.add_argument_group('output arguments')
outputArgs.add_argument('-f', '--format', action='store_true', help='format output using xmllint')
outputArgs.add_argument('-c', '--comments', action='store_true', help='add comments to result XML')

# parse arguments
args = parser.parse_args()

# get path to script
scriptPath = os.path.dirname(sys.argv[0])

# standard namespaces to import 
imports = {'d' : 'http://www.alfresco.org/model/dictionary/1.0', 'bpm' : 'http://www.alfresco.org/model/bpm/1.0', 'cm' : 'http://www.alfresco.org/model/content/1.0'}

# get implementation
impl = getDOMImplementation()

if args.swimlanes:
	# generate swinlane tags
	procdef = generateSwimlaneTags()
	# print result
	printXml(procdef, args.format)

if args.model:
	model = generateModel()
	# print result
	printXml(model, args.format)

if args.share:
	# generate share config
	config = generateShareConfig()
	# print result
	printXml(config, args.format)
