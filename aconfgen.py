#!/usr/bin/python2
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
import copy
import os
import sys
import re
import libxml2

# exception classes
class ValidationException(Exception):
	'''Super class for validation exceptions.'''
	pass

class InvalidSchemaException(ValidationException):
	'''Exception to raise when schema is invalid.'''
	pass


class InvalidProcDefException(ValidationException):
	'''Exception to raise when process definition is invalid.'''
	pass

class InvalidTaskModelException(ValidationException):
	'''Exception to raise when task model is invalid.'''
	pass

# config generator class
class ConfigGenerator:
	'''ConfigGenerator class. Generates skeleton of Alfresco configuration files'''

	def noErr(self, ctx, str):
		'''Dummy function to suppress error messages.'''
		pass

	def __init__(self, xmlFile, addComments = False):
		'''Class constructor. Collects some information needed for config generation, loads XML.

		Keyword arguments:
			addComments -- add comments to result XML (default False)
			xmlFile -- file that contains XML to parse

		'''
		# get path to script
		self.scriptPath = os.path.dirname(sys.argv[0])
		# default options
		self.addComments = addComments
		self.xmlFile = xmlFile
		# suppress all error messages from libxml2
		libxml2.registerErrorHandler(self.noErr, None)
		# load xml
		self.xml = libxml2.readFile(xmlFile, None, 0)

	def removeBlankNodes(self, node):
		'''Removes all blank nodes from result xml'''

		# iterate through node children and remove blank nodes
		item = node.children
		while item:
			if item.isBlankNode():
				# remove node
				t = item.next
				item.unlinkNode()
				# get next node
				item = t
			else:
				# call recursively
				self.removeBlankNodes(item)
				# get next node
				item = item.next


	def validateProcessDefinition(self):
		'''Validates process definition and return default namespace on success.'''
		# try to validate XML as jpdl-3.1
		ns = 'urn:jbpm.org:jpdl-3.1'
		try:
			# load 3.1 schema
			schema_parser_ctx = libxml2.schemaNewParserCtxt(os.path.join(self.scriptPath, 'schemas', 'jpdl-3.1.xsd'))
			schema = schema_parser_ctx.schemaParse()
			valid_schema = schema.schemaNewValidCtxt()
		except libxml2.libxmlError, e:
			raise InvalidSchemaException('jpdl-3.1 schema is invalid')
		# validate
		if self.xml.schemaValidateDoc(valid_schema):
			# it's not jpdl-3.1, try to validate as jpdl-3.2
			ns = 'urn:jbpm.org:jpdl-3.2'
			try:
				# load 3.2 schema
				schema_parser_ctx = libxml2.schemaNewParserCtxt(os.path.join(self.scriptPath, 'schemas', 'jpdl-3.2.xsd'))
				schema = schema_parser_ctx.schemaParse()
				valid_schema = schema.schemaNewValidCtxt()
			except libxml2.libxmlError, e:
				raise InvalidSchemaException('jpdl-3.2 schema is invalid')
			# validate
			if self.xml.schemaValidateDoc(valid_schema):
				# throw exception, because document is not valid
				raise InvalidProcDefException('This is not valid jpdl-3.1 or jpdl-3.2 XML.');

		# return default namespace
		return ns

	def validateTaskModel(self):
		'''Validates task model XML and returns default namespace on success'''
		try:
			# load schema
			schema_parser_ctx = libxml2.schemaNewParserCtxt(os.path.join(self.scriptPath, 'schemas', 'modelSchema.xsd'))
			schema = schema_parser_ctx.schemaParse()
			valid_schema = schema.schemaNewValidCtxt()
		except libxml2.libxmlError, e:
			raise InvalidSchemaException('Task model schema is invalid')

		# validate
		if self.xml.schemaValidateDoc(valid_schema):
			# throw exception, because document is not valid
			raise InvalidTaskModelException('Task model XML is invalid.')

		return 'http://www.alfresco.org/model/dictionary/1.0'


	def addSwimlanes(self):
		'''Parses process definition and adds swimlane tags to the top of it.'''

		# set result type
		self.xmlResult = True
		# validate process definition XML
		ns = self.validateProcessDefinition()
		# clone xml
		self.result = copy.copy(self.xml)
		# get new xpath context
		ctx = self.result.xpathNewContext()
		# register default namespace
		ctx.xpathRegisterNs('dd', ns)

		# populate swimlane list
		swimlanes = [x.prop('swimlane') for x in ctx.xpathEval('/dd:process-definition/dd:task-node/dd:task[@swimlane != \'\']')]
		# iterate through swimlane list and generate nodes
		for swimlane in swimlanes:
			# create new node
			swimlaneNode = self.result.newDocNode(None, 'swimlane', None)
			swimlaneNode.setProp('name', swimlane)
			# create assignment if swimlane != initiator
			if swimlane != 'initiator':
				# set assignment
				assignmentNode = self.result.newDocNode(None, 'assignment', None)
				assignmentNode.setProp('class', 'org.alfresco.repo.workflow.jbpm.AlfrescoAssignment')
				swimlaneNode.addChild(assignmentNode)
				# set actor
				assignmentNode.addChild(self.result.newDocNode(None, 'actor', '#{'+swimlane+'}'))
			# add comment if needed
			if self.addComments:
				self.result.getRootElement().addChild(self.result.newDocComment("'"+swimlane+"' swimlane"))
			# add swimlane to tree
			self.result.getRootElement().addChild(swimlaneNode)

	def generateTaskModel(self, addMetaData = False, addMandatoryAspects = False, addItemActions = False, addAspectDef = False):
		'''Parses process definition and generates task model for it.

		Keyword arguments:
			addMetadata -- add metadata to result XML (default False)
			addMandatoryAspects -- add <mandatory-aspects> tag to each type item (default False)
			addItemActions -- add overrides section for bpm:packageItemActionGroup property to each type item (default False)
			addAspectDef -- add custom aspect definition section to the end of task model XML (default False)

		'''

		# set result type
		self.xmlResult = True
		# validate process definition XML
		ns = self.validateProcessDefinition()
		# get new xpath context
		ctx = self.xml.xpathNewContext()
		# register default namespace
		ctx.xpathRegisterNs('dd', ns)
		# create model skeleton
		modelTemplate = '''<?xml version='1.0'?><model xmlns='http://www.alfresco.org/model/dictionary/1.0'></model>'''
		importTemplate = '''<imports><import uri="http://www.alfresco.org/model/dictionary/1.0" prefix="d" /><import uri="http://www.alfresco.org/model/bpm/1.0" prefix="bpm" /></imports>'''
		customAspectTemplate = '''<aspects><aspect name='ns:customAspect'><title>Custom aspect sample</title><properties><property name='ns:customProperty'><type>d:string</type><mandatory>false</mandatory><multiple>false</multiple></property></properties></aspect></aspects>'''
		overridesTemplate = '''<overrides><property name='bpm:packageItemActionGroup'><default>edit_package_item_actions</default></property></overrides>'''

		self.result = libxml2.parseMemory(modelTemplate, len(modelTemplate))
		root = self.result.getRootElement()
		# add metadata
		if self.addComments:
			root.addChild(self.result.newDocComment('Model metadata'))
		root.addChild(self.result.newDocNode(None, 'description', 'Task model for '+self.xmlFile))
		root.addChild(self.result.newDocNode(None, 'author', os.getenv('USER')))
		root.addChild(self.result.newDocNode(None, 'version', '1.0'))
		# add import section
		if self.addComments:
			root.addChild(self.result.newDocComment('Import necessary namespaces'))
		root.addChild(libxml2.parseMemory(importTemplate, len(importTemplate)).getRootElement())
		# populate task list
		tasks = ctx.xpathEval('/dd:process-definition/dd:*/dd:task')
		# iterate through all task and build task model and collect namespaces
		namespaces = set()
		parentNode = {'start-state': 'bpm:startTask', 'task-node': 'bpm:workflowTask'}
		typesNode = self.result.newDocNode(None, 'types', None)
		ns = ''
		for task in tasks:
			taskName = task.prop('name')
			# extract namespace
			gr = re.search('^(.+):(.*)$', taskName)
			if gr:
				ns = gr.group(1)
			else:
				ns = ''
			namespaces.add(ns)
			# add new type element
			typeNode = self.result.newDocNode(None, 'type', None)
			typeNode.setProp('name', taskName)
			# add parent node
			typeNode.addChild(self.result.newDocNode(None, 'parent', parentNode[task.parent.name]))
			# add overrides section
			if addItemActions:
				if self.addComments:
					typeNode.addChild(self.result.newDocComment('overrides default properties values'))
				typeNode.addChild(libxml2.parseMemory(overridesTemplate, len(overridesTemplate)).getRootElement())
			# add mandatory aspects
			if addMandatoryAspects:
				aspectsNode = self.result.newDocNode(None, 'mandatory-aspects', None)
				# add bpm:assignee for start task
				if task.parent.name == 'start-state':
					aspectsNode.addChild(self.result.newDocNode(None, 'aspect', 'bpm:assignee'))
				# add custom aspect
				aspectsNode.addChild(self.result.newDocNode(None, 'aspect', ns+':customAspect'))
				# add aspects to tree
				if self.addComments:
					typeNode.addChild(self.result.newDocComment('Task mandatory aspects'))
				typeNode.addChild(aspectsNode)

			# add node to tree
			if self.addComments:
				typesNode.addChild(self.result.newDocComment('Type for '+taskName+' task'))
			typesNode.addChild(typeNode)

		# add found namespaces to task model
		namespacesNode = self.result.newDocNode(None, 'namespaces', None)
		for ns in namespaces:
			# create new node
			namespaceNode = self.result.newDocNode(None, 'namespace', None)
			namespaceNode.setProp('prefix', ns)
			namespaceNode.setProp('uri', 'https://github.com/fufler/aconfgen/prefix/'+ns)
			# add node to tree
			namespacesNode.addChild(namespaceNode)

		# add namespaces and types node to tree
		if self.addComments:
			root.addChild(self.result.newDocComment('List of found namespaces in process definition'))
		root.addChild(namespacesNode)
		if self.addComments:
			root.addChild(self.result.newDocComment('List of types'))
		root.addChild(typesNode)
		# add custom aspect definition
		if addAspectDef:
			if self.addComments:
				root.addChild(self.result.newDocComment('Custom aspect definition sample'))
			# replace ns: with last found namespace (we expect exact one)
			customAspectTemplate = customAspectTemplate.replace('ns:', ns+':')
			root.addChild(libxml2.parseMemory(customAspectTemplate, len(customAspectTemplate)).getRootElement())
		# set models name using last found namespace
		self.result.getRootElement().setProp('name', ns+':samplemodel')



	def generateUIConfig(self, workflowModel, processName = '', addLabelId = False, addSets = False):
		'''Generates skeleton of share-custom-config.xml for workflow/documentLibrary UI rendering.

		Keyword arguments:
			workflowModel -- treat model as workflow model			
			processName -- process name to use in generated config (default '')
			addLabelId -- insert label-id attribute into each filed tag (default False)
			addSets -- add sets definitions to each form (default False)

		'''

		# set result type
		self.xmlResult = True
		# validate xml
		ns = self.validateTaskModel()
		# get new xpath context
		ctx = self.xml.xpathNewContext()
		# register default namespace
		ctx.xpathRegisterNs('dd', ns)
		# build config for UI rendering
		# create new document and root node
		self.result = libxml2.newDoc('1.0')
		root = self.result.newDocNode(None, 'alfresco-config', None)
		self.result.setRootElement(root)
		# populate task type list
		types = ctx.xpathEval('/dd:model/dd:types/dd:type')
		# iterate throught all types and build config
		for typeNode in types:
			ctx.setContextNode(typeNode)
			# create config node
			configNode = self.result.newDocNode(None, 'config', None)
			# choose evaluator based on model type
			if workflowModel: 
				# if this is startTask then we should use another condition
				if 'bpm:startTask' in [x.content for x in ctx.xpathEval('dd:parent')]:
					configNode.setProp('evaluator', 'string-compare')
					configNode.setProp('condition', 'jbpm$'+processName)
				else:
					configNode.setProp('evaluator', 'task-type')
					configNode.setProp('condition', typeNode.prop('name'))
			else:
				configNode.setProp('evaluator', 'node-type')
				configNode.setProp('condition', typeNode.prop('name'))				
			if self.addComments:
				root.addChild(self.result.newDocComment('Form config for '+typeNode.prop('name')+' rendering'))
			root.addChild(configNode)
			# create forms and form nodes
			formsNode = self.result.newDocNode(None, 'forms', None)
			formNode = self.result.newDocNode(None, 'form', None)
			configNode.addChild(formsNode)
			formsNode.addChild(formNode)
			# create field-visibility and appearance nodes
			fieldVisNode = self.result.newDocNode(None, 'field-visibility', None)
			if self.addComments:
				formNode.addChild(self.result.newDocComment('List of fields to render'))
			formNode.addChild(fieldVisNode)
			appearanceNode = self.result.newDocNode(None, 'appearance', None)
			if self.addComments:
				formNode.addChild(self.result.newDocComment('Fields appearance configuration'))
			formNode.addChild(appearanceNode)
			# add sets definitions
			if addSets:
				if self.addComments:
					appearanceNode.addChild(self.result.newDocComment('Sets definition'))
				# top set
				if workflowModel:
					setNode = self.result.newDocNode(None, 'set', None)
					setNode.setProp('id', 'info')
					setNode.setProp('appearance', '')
					if addLabelId:
						setNode.setProp('label-id', 'workflow.set.task.info')
					appearanceNode.addChild(setNode)
				# other set
				setNode = self.result.newDocNode(None, 'set', None)
				setNode.setProp('id', 'other')
				setNode.setProp('appearance', 'title')
				if addLabelId:
					setNode.setProp('label-id', 'workflow.set.other')
				appearanceNode.addChild(setNode)
				# items set
				if workflowModel:
					setNode = self.result.newDocNode(None, 'set', None)
					setNode.setProp('id', 'items')
					setNode.setProp('appearance', 'title')
					if addLabelId:
						setNode.setProp('label-id', 'workflow.set.items')
					appearanceNode.addChild(setNode)
				# response set
				if workflowModel:
					if 'bpm:startTask' not in [x.content for x in ctx.xpathEval('dd:parent')]:
						setNode = self.result.newDocNode(None, 'set', None)
						setNode.setProp('id', 'response')
						setNode.setProp('appearance', 'title')
						if addLabelId:
							setNode.setProp('label-id', 'workflow.set.response')
						appearanceNode.addChild(setNode)

			# for each property ans association generate field elements
			if self.addComments:
				appearanceNode.addChild(self.result.newDocComment('Fields'))			
			properties = [x.prop('name') for x in ctx.xpathEval('dd:properties/dd:property')+ctx.xpathEval('dd:associations/dd:association')]
			for property in properties:
				# create show and field nodes
				showNode = self.result.newDocNode(None, 'show', None)
				showNode.setProp('id', property)
				fieldVisNode.addChild(showNode)
				fieldNode = self.result.newDocNode(None, 'field', None)
				fieldNode.setProp('id', property)
				if addLabelId:
					fieldNode.setProp('label-id', 'label.'+property.replace(':','_'))
				if addSets:
					fieldNode.setProp('set', 'other')
				appearanceNode.addChild(fieldNode)
					
			# populate all aspects for type
			aspects = [x.content for x in ctx.xpathEval('dd:mandatory-aspects/dd:aspect')]
			# for each aspect try to find its definition to extract all properties and associations
			for aspect in aspects:
				aspectDefNode = ctx.xpathEval('/dd:model/dd:aspects/dd:aspect[@name=\''+aspect+'\']')
				# if list is not empty then choose first element (because we expect at most one aspect definition)
				if len(aspectDefNode):
					aspectDefNode = aspectDefNode[0]
					# find all properties and associations
					ctx.setContextNode(aspectDefNode)
					fields = [x.prop('name') for x in ctx.xpathEval('dd:properties/dd:property') + ctx.xpathEval('dd:associations/dd:association')]
					# add them to tree
					for field in fields:
						# create show and field nodes
						showNode = self.result.newDocNode(None, 'show', None)
						showNode.setProp('id', field)
						fieldVisNode.addChild(showNode)
						fieldNode = self.result.newDocNode(None, 'field', None)
						fieldNode.setProp('id', field)
						if addLabelId:
							fieldNode.setProp('label-id', 'label.'+field.replace(':','_'))
						if addSets:
							fieldNode.setProp('set', 'other')
						appearanceNode.addChild(fieldNode)
				else:
					# aspect definition not found, add field with the same name as aspect
					# create show and field nodes
					showNode = self.result.newDocNode(None, 'show', None)
					showNode.setProp('id', aspect)
					fieldVisNode.addChild(showNode)
					fieldNode = self.result.newDocNode(None, 'field', None)
					fieldNode.setProp('id', aspect)
					if addLabelId:
						fieldNode.setProp('label-id', 'label.'+aspect.replace(':','_'))
					if addSets:
						fieldNode.setProp('set', 'other')
					appearanceNode.addChild(fieldNode)
			# add items field
			if workflowModel:
				showNode = self.result.newDocNode(None, 'show', None)
				showNode.setProp('id', 'packageItems')
				fieldVisNode.addChild(showNode)
				fieldNode = self.result.newDocNode(None, 'field', None)
				fieldNode.setProp('id', 'packageItems')
				if addSets:
					fieldNode.setProp('set', 'items')
				appearanceNode.addChild(fieldNode)
				# add transitions field
				ctx.setContextNode(typeNode)
				if 'bpm:startTask' not in [x.content for x in ctx.xpathEval('dd:parent')]:
					showNode = self.result.newDocNode(None, 'show', None)
					showNode.setProp('id', 'transitions')
					fieldVisNode.addChild(showNode)
					fieldNode = self.result.newDocNode(None, 'field', None)
					fieldNode.setProp('id', 'transitions')
					if addSets:
						fieldNode.setProp('set', 'response')
					appearanceNode.addChild(fieldNode)
				else:
					# create form for workflow details rendering
					configNode = configNode.copyNodeList()
					# replace condition
					configNode.setProp('evaluator', 'task-type')
					configNode.setProp('condition', typeNode.prop('name'))
					if self.addComments:
						root.addChild(self.result.newDocComment('Form config to display workflow info'))
					# remove info set
					if addSets:
						resctx = self.result.xpathNewContext()
						resctx.setContextNode(configNode)
						resctx.xpathEval('forms/form/appearance/set[@id=\'info\']')[0].unlinkNode()
					# add to tree
					root.addChild(configNode)

	def generateWorkflowBundle(self):
		'''Generates workflow internationalization bundle'''

		# set result type
		self.xmlResult = False

	def generateWorkflowBundle(self):
		'''Generates workflow internationalization bundle (tasks and transitions)'''

		# set result type
		self.xmlResult = False
		# validate process definition XML
		ns = self.validateProcessDefinition()
		# get new xpath context
		ctx = self.xml.xpathNewContext()
		# register default namespace
		ctx.xpathRegisterNs('dd', ns)
		# get process name
		procName = self.xml.getRootElement().prop('name').replace(':', '_')
		# add process string
		tmp = [procName+'.workflow']
		# get tasks with non-empty name replacing : by _ and add them to temporary list
		tmp.extend([procName+'.task.'+x.prop('name').replace(':', '_') for x in ctx.xpathEval('/dd:process-definition/dd:task-node/dd:task[@name!=\'\']')])
		# get all transitions and add them to temporary list
		tmp.extend([procName+'.node.'+x.parent.prop('name')+'.transition.'+x.prop('name') for x in ctx.xpathEval('/dd:process-definition/dd:task-node[@name!=\'\']/dd:transition[@name!=\'\']')])
		# create result list
		self.result = []
		for x in tmp:
			self.result.extend([x+'.title=', x+'.description='])


	def generateShareBundle(self):
		'''Generates share internationalization bundle for found label-id attributes'''
		# set result type
		self.xmlResult = False
		# get new xpath context
		ctx = self.xml.xpathNewContext()
		self.result = [x.prop('label-id')+'=' for x in ctx.xpathEval('/alfresco-config/config/forms/form/appearance/field[@label-id!=\'\']')]
		# remove dplicates
		self.result = list(set(self.result))

	def printListResult(self):
		'''Prints result list'''

		for x in self.result:
			print(x)

# run script
if __name__ == '__main__':
	# parse command line arguments

	# create argument parser
	parser = argparse.ArgumentParser(description='Generates skeleton of some Alfresco configuration files using process definition XML, task model, share custom config.')

	# add file argument
	parser.add_argument('file', metavar='XML', help='XML file, containing process definition in jPDL/workflow model/share config (use \'-\' to read from stdin)')

	# add group of arguments for specifying action to perform
	actionArgs = parser.add_mutually_exclusive_group( required=True)
	actionArgs.add_argument('-s', '--swimlanes', action='store_true', help='generate swimlane tags for process definition')
	actionArgs.add_argument('-m', '--model', action='store_true', help='generate skeleton of workflow model XML')
	actionArgs.add_argument('-w', '--workflow-ui', action='store_true', help='generate skeleton of share-config-custom.xml for workflow UI rendering')
	actionArgs.add_argument('-L', '--model-ui', action='store_true', help='generate skeleton of share-config-custom.xml for model UI rendering')	
	actionArgs.add_argument('-W', '--workflow-i18n', action='store_true', help='generate workflow internationalization bundle')
	actionArgs.add_argument('-e', '--share-i18n', action='store_true', help='generate share internationalization bundle')

	# add arguments related to model generation
	modelArgs = parser.add_argument_group('Model generation options')
	modelArgs.add_argument('-M', '--mandatory-aspects', action='store_true', help='add mandatory-aspects section to each workflow model type')
	modelArgs.add_argument('-d', '--metadata', action='store_true', help='add metadata to model')
	modelArgs.add_argument('-i', '--item-actions', action='store_true', help='add item-actions section to each workflow model type')
	modelArgs.add_argument('-a', '--aspect', action='store_true', help='add dummy aspect definition section')

	# add arguments related to share config generation
	workflowUIArgs = parser.add_argument_group('Workflow UI config generation options')
	workflowUIArgs.add_argument('-n', '--process-name', default='', action='store', help='workflow process name to be used in generated config (adds $jbpm prefix automatically)')
	workflowUIArgs.add_argument('-l', '--label-id', action='store_true', help='insert label-id attribute into each field tag')
	workflowUIArgs.add_argument('-S', '--sets', action='store_true', help='add sets definitions and set correspoding field attribute')

	# add arguments related to XML output
	outputArgs = parser.add_argument_group('Output arguments')
	outputArgs.add_argument('-f', '--format', action='store_true', help='format output with blanks (works only if -r specified)')
	outputArgs.add_argument('-c', '--comments', action='store_true', help='add comments to resulting XML')
	outputArgs.add_argument('-r', '--remove-blanks', action='store_true', help='remove all blank nodes from resulting XML')

	# parse arguments
	args = parser.parse_args()

	# create ConfigGenerator
	try:
		confgen = ConfigGenerator(args.file, args.comments)
	except libxml2.libxmlError, e:
		print('Cannot parse XML. Terminating.')
		sys.exit(1);

	try:
		if args.swimlanes:
			# add swimlane tags
			confgen.addSwimlanes()
		elif args.model:
			# generate task model
			confgen.generateTaskModel(args.metadata, args.mandatory_aspects, args.item_actions, args.aspect)
		elif args.workflow_ui:
			# generate workflow UI config
			confgen.generateUIConfig(args.process_name, True, args.label_id, args.sets)
		elif args.model_ui:
			# generate model UI config
			confgen.generateUIConfig('', False, args.label_id, args.sets)			
		elif args.workflow_i18n:
			# generate workflow internationalization bundle
			confgen.generateWorkflowBundle()
		elif args.share_i18n:
			# generate share internationalization bundle
			confgen.generateShareBundle()
	except ValidationException, e:
		print('XML validation failed: '+e.message)
		sys.exit(1)

	# do diffrent stuff depending on result type
	if confgen.xmlResult:
		# remove blank nodes
		if args.remove_blanks:
			confgen.removeBlankNodes(confgen.result)
		# output XML
		confgen.result.saveFormatFileEnc('-', 'utf-8', args.format)
	else:
		# print strings
		confgen.printListResult()
		
