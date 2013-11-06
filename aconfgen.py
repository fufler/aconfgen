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

# default namespaces for definition files
defNS = {'jpdl-3.1': 'urn:jbpm.org:jpdl-3.1',
         'jpdl-3.2': 'urn:jbpm.org:jpdl-3.2',
         'bpmn-2.0': 'http://www.omg.org/spec/BPMN/20100524/MODEL'}
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

class InvalidActionException(ValidationException):
	'''Exception to raise when invalid action was invoked.'''
	pass

# config generator class
class ConfigGenerator:
	'''ConfigGenerator class. Generates skeleton of Alfresco configuration files'''

	def noErr(self, ctx, str):
		'''Dummy function to suppress error messages.'''
		pass

	def __init__(self, xmlFile, addComments=False):
		'''Class constructor. Collects some information needed for config generation, loads XML.

		Keyword arguments:
			addComments -- add comments to result XML (default False)
			xmlFile -- file that contains XML to parse

		'''
		# get path to script
		self.scriptPath = os.path.dirname(os.path.realpath(sys.argv[0]))
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
		'''Validates document and returns it's language id on success.
		Exception is raised in any other case'''

		schemas = {'jpdl-3.1': 'jpdl-3.1.xsd', 'jpdl-3.2': 'jpdl-3.2.xsd', 'bpmn-2.0' : 'BPMN20.xsd'};
		# iterate through all schemas and try to validate XML
		definitionLang = None;
		for lang in schemas:
			try:
				# load schema
				schema_parser_ctx = libxml2.schemaNewParserCtxt(os.path.join(self.scriptPath, 'schemas', schemas[lang]))
				schema = schema_parser_ctx.schemaParse()
				valid_schema = schema.schemaNewValidCtxt()
			except libxml2.libxmlError, e:
				raise InvalidSchemaException('Schema for '+lang + ' is invalid.')

			# validate
			if not self.xml.schemaValidateDoc(valid_schema):
				# xml validate, store result
				definitionLang = lang;

		if not definitionLang:
			# language not found, raise exception
			raise InvalidProcDefException("Process definition is invalid.")

		return definitionLang;

	def validateContentModel(self):
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


	def buildNamespace(self, prefix):
		'''Helper to construct namespace by prefix'''
		return 'https://github.com/fufler/aconfgen/prefix/' + prefix

	def addSwimlanes(self):
		'''Parses process definition and adds swimlane tags to the top of it.'''

		# set result type
		self.xmlResult = True
		# validate process definition XML
		lang = self.validateProcessDefinition()
		if lang in defNS:
			ns = defNS[lang]
		else:
			raise InvalidActionException('Swimlanes adding supported only for jpdl process definitions.');

		# clone xml
		self.result = copy.copy(self.xml)
		# get new xpath context
		ctx = self.result.xpathNewContext()
		# register default namespace
		ctx.xpathRegisterNs('defaultns', ns)

		# populate swimlane list
		swimlanes = set([x.prop('swimlane') for x in ctx.xpathEval('/defaultns:process-definition/defaultns:task-node/defaultns:task[@swimlane != \'\']')])
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
				assignmentNode.addChild(self.result.newDocNode(None, 'actor', '#{' + swimlane + '}'))
			# add comment if needed
			if self.addComments:
				self.result.getRootElement().addChild(self.result.newDocComment("'" + swimlane + "' swimlane"))
			# add swimlane to tree
			self.result.getRootElement().addChild(swimlaneNode)

	def generateTaskModel(self, addMetaData=False, addMandatoryAspects=False, addItemActions=False, addAspectDef=False):
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
		lang = self.validateProcessDefinition()
		# create model skeleton
		modelTemplate = '''<?xml version='1.0'?><model xmlns='http://www.alfresco.org/model/dictionary/1.0'></model>'''
		importTemplate = '''<imports><import uri="http://www.alfresco.org/model/dictionary/1.0" prefix="d" /><import uri="http://www.alfresco.org/model/bpm/1.0" prefix="bpm" /></imports>'''
		customAspectTemplate = '''<aspects><aspect name='ns:customAspect'><title>Custom aspect sample</title><properties><property name='ns:customProperty'><type>d:string</type><mandatory>false</mandatory><multiple>false</multiple></property></properties></aspect></aspects>'''
		overridesTemplate = '''<overrides><property name='bpm:packageItemActionGroup'><default>edit_package_item_actions</default></property></overrides>'''

		self.result = libxml2.parseMemory(modelTemplate, len(modelTemplate))
		root = self.result.getRootElement()
		# add metadata
		if addMetaData:
			if self.addComments:
				root.addChild(self.result.newDocComment('Model metadata'))
			root.addChild(self.result.newDocNode(None, 'description', 'Task model for '+self.xmlFile))
			root.addChild(self.result.newDocNode(None, 'author', os.getenv('USER')))
			root.addChild(self.result.newDocNode(None, 'version', '1.0'))
		# add import section
		if self.addComments:
			root.addChild(self.result.newDocComment('Import necessary namespaces'))
		root.addChild(libxml2.parseMemory(importTemplate, len(importTemplate)).getRootElement())
		# build array containing information about tasks
		ctx = self.xml.xpathNewContext()
		ns = defNS[lang]
		# register default namespace
		ctx.xpathRegisterNs('defaultns', ns)
		if lang == 'bpmn-2.0':
			# it's an activiti file
			# register activiti namespace
			ctx.xpathRegisterNs('activiti', 'http://activiti.org/bpmn')
			tasks = {
                      x.prop('formKey'):
                      {
                        'id': x.prop('id'),
                        'parent': x.name,
                        'transitions':[]
                      }
                      for x in ctx.xpathEval('/defaultns:definitions/defaultns:process/*[@activiti:formKey!=""]')
                    }
			# find all transitions
			for task in tasks:
				trans = ctx.xpathEval('/defaultns:definitions/defaultns:process/defaultns:sequenceFlow[@sourceRef="'+tasks[task]["id"]+'"]')
				if len(trans) != 1:
					raise InvalidProcDefException('Task has no/invalid outcome.')
				gateway = trans[0].prop('targetRef')
				trans = [x.prop('targetRef') for x in ctx.xpathEval('/defaultns:definitions/defaultns:process/defaultns:sequenceFlow[@sourceRef="'+gateway+'"]')]
				if len(trans) == 0:
					trans = ['done']
				tasks[task]["transitions"] = trans
		else:
			# it's a jpdl file
			# populate task list
			tasks = {
                      x.prop('name'):
                      {
                        'parent': x.parent.name,
                        'transitions':[]
                      }
                      for x in ctx.xpathEval('/defaultns:process-definition/defaultns:*/defaultns:task')
                    }

		# iterate through all task and build task model and collect namespaces
		namespaces = set()
		parentNode = {
                       'start-state': 'bpm:startTask',
                       'task-node': 'bpm:workflowTask',
                       'startEvent': 'bpm:startTask',
                       'userTask': 'bpm:workflowTask'
                     }
		typesNode = self.result.newDocNode(None, 'types', None)
		ns = ''
		for taskName in tasks:
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
			task = tasks[taskName]
			parentNodeType = task["parent"]
			activitiOutcome = False
			if parentNodeType in ['start-state', 'startEvent']:
				typeNode.addChild(self.result.newDocNode(None, 'parent', 'bpm:startTask'))
			elif len(task['transitions']) > 0:
				typeNode.addChild(self.result.newDocNode(None, 'parent', 'bpm:activitiOutcomeTask'))
				activitiOutcome = True
			else:
				typeNode.addChild(self.result.newDocNode(None, 'parent', 'bpm:workflowTask'))
			# add outcome for activiti tasks
			if activitiOutcome:
				if self.addComments:
					typeNode.addChild(self.result.newDocComment('Add outcome property for activiti tasks'))
				propertiesNode = self.result.newDocNode(None, 'properties', None)
				propertyNode =  self.result.newDocNode(None, 'property', None)
				propertiesNode.addChild(propertyNode)
				propertyNode.setProp('name', taskName+'Outcome')
				propertyNode.addChild(self.result.newDocNode(None, 'type', 'd:text'))
				propertyNode.addChild(self.result.newDocNode(None, 'default', task['transitions'][0]))
				constraintsNode =  self.result.newDocNode(None, 'constraints', None)
				propertyNode.addChild(constraintsNode)
				constraintNode =  self.result.newDocNode(None, 'constraint', None)
				constraintNode.setProp('type', 'LIST')
				constraintNode.setProp('name', taskName+'OutcomeConstraint')
				constraintsNode.addChild(constraintNode)
				parameterNode = self.result.newDocNode(None, 'parameter', None)
				parameterNode.setProp('name', 'allowedValues')
				constraintNode.addChild(parameterNode)
				listNode = self.result.newDocNode(None, 'list', None)
				parameterNode.addChild(listNode)
				for x in task['transitions']:
					listNode.addChild(self.result.newDocNode(None, 'value', x))
				typeNode.addChild(propertiesNode)


			# add overrides section
			if addItemActions:
				if self.addComments:
					typeNode.addChild(self.result.newDocComment('overrides default properties values'))
				overridesNode = libxml2.parseMemory(overridesTemplate, len(overridesTemplate)).getRootElement()
				if activitiOutcome:
					# add property name of activiti outcome
					propertyNode = self.result.newDocNode(None, 'property', None)
					overridesNode.addChild(propertyNode)
					propertyNode.setProp('name', 'bpm:outcomePropertyName')
					propertyNode.addChild(self.result.newDocNode(None, 'default', taskName.replace(ns+':', '{'+self.buildNamespace(ns)+'}')+'Outcome'))
				typeNode.addChild(overridesNode)
			# add mandatory aspects
			if addMandatoryAspects:
				aspectsNode = self.result.newDocNode(None, 'mandatory-aspects', None)
				# add bpm:assignee for start task
				if parentNodeType == 'start-state':
					aspectsNode.addChild(self.result.newDocNode(None, 'aspect', 'bpm:assignee'))
				# add custom aspect
				aspectsNode.addChild(self.result.newDocNode(None, 'aspect', ns + ':customAspect'))
				# add aspects to tree
				if self.addComments:
					typeNode.addChild(self.result.newDocComment('Task mandatory aspects'))
				typeNode.addChild(aspectsNode)

			# add node to tree
			if self.addComments:
				typesNode.addChild(self.result.newDocComment('Type for ' + taskName + ' task'))
			typesNode.addChild(typeNode)


		# add found namespaces to task model
		namespacesNode = self.result.newDocNode(None, 'namespaces', None)
		for ns in namespaces:
			# create new node
			namespaceNode = self.result.newDocNode(None, 'namespace', None)
			namespaceNode.setProp('prefix', ns)
			namespaceNode.setProp('uri', self.buildNamespace(ns))
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
			customAspectTemplate = customAspectTemplate.replace('ns:', ns + ':')
			root.addChild(libxml2.parseMemory(customAspectTemplate, len(customAspectTemplate)).getRootElement())
		# set models name using last found namespace
		self.result.getRootElement().setProp('name', ns + ':samplemodel')



	def generateUIConfig(self, workflowModel, processName='', addLabelId=False, addSets=False):
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
		ns = self.validateContentModel()
		# get new xpath context
		ctx = self.xml.xpathNewContext()
		# register default namespace
		ctx.xpathRegisterNs('defaultns', ns)
		# build config for UI rendering
		# create new document and root node
		self.result = libxml2.newDoc('1.0')
		root = self.result.newDocNode(None, 'alfresco-config', None)
		self.result.setRootElement(root)
		# populate task type list
		types = ctx.xpathEval('/defaultns:model/defaultns:types/defaultns:type')
		# iterate throught all types and build config
		for typeNode in types:
			ctx.setContextNode(typeNode)
			# create config node
			configNode = self.result.newDocNode(None, 'config', None)
			# choose evaluator based on model type
			if workflowModel:
				# if this is startTask then we should use another condition
				if 'bpm:startTask' in [x.content for x in ctx.xpathEval('defaultns:parent')]:
					configNode.setProp('evaluator', 'string-compare')
					configNode.setProp('condition', processName)
				else:
					configNode.setProp('evaluator', 'task-type')
					configNode.setProp('condition', typeNode.prop('name'))
			else:
				configNode.setProp('evaluator', 'node-type')
				configNode.setProp('condition', typeNode.prop('name'))
			if self.addComments:
				root.addChild(self.result.newDocComment('Form config for ' + typeNode.prop('name') + ' rendering'))
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
					if 'bpm:startTask' not in [x.content for x in ctx.xpathEval('defaultns:parent')]:
						setNode = self.result.newDocNode(None, 'set', None)
						setNode.setProp('id', 'response')
						setNode.setProp('appearance', 'title')
						if addLabelId:
							setNode.setProp('label-id', 'workflow.set.response')
						appearanceNode.addChild(setNode)

			# for each property ans association generate field elements
			if self.addComments:
				appearanceNode.addChild(self.result.newDocComment('Fields'))
			properties = [x.prop('name') for x in ctx.xpathEval('defaultns:properties/defaultns:property') + ctx.xpathEval('defaultns:associations/defaultns:association')]
			for property in properties:
				# create show and field nodes
				showNode = self.result.newDocNode(None, 'show', None)
				showNode.setProp('id', property)
				fieldVisNode.addChild(showNode)
				fieldNode = self.result.newDocNode(None, 'field', None)
				fieldNode.setProp('id', property)
				if addLabelId:
					# activity: don't add label-id if property name ends with Outcome
					if not property.endswith('Outcome'):
						fieldNode.setProp('label-id', 'label.' + property.replace(':', '_'))
				if addSets:
					# activiti : add to response set if property name ends with Outcome
					if property.endswith('Outcome'):
						fieldNode.setProp('set', 'response')
					else:
						fieldNode.setProp('set', 'other')
				appearanceNode.addChild(fieldNode)

			# populate all aspects for type
			aspects = [x.content for x in ctx.xpathEval('defaultns:mandatory-aspects/defaultns:aspect')]
			# for each aspect try to find its definition to extract all properties and associations
			for aspect in aspects:
				aspectDefNode = ctx.xpathEval('/defaultns:model/defaultns:aspects/defaultns:aspect[@name=\'' + aspect + '\']')
				# if list is not empty then choose first element (because we expect at most one aspect definition)
				if len(aspectDefNode):
					aspectDefNode = aspectDefNode[0]
					# find all properties and associations
					ctx.setContextNode(aspectDefNode)
					fields = [x.prop('name') for x in ctx.xpathEval('defaultns:properties/defaultns:property') + ctx.xpathEval('defaultns:associations/defaultns:association')]
					# add them to tree
					for field in fields:
						# create show and field nodes
						showNode = self.result.newDocNode(None, 'show', None)
						showNode.setProp('id', field)
						fieldVisNode.addChild(showNode)
						fieldNode = self.result.newDocNode(None, 'field', None)
						fieldNode.setProp('id', field)
						if addLabelId:
							fieldNode.setProp('label-id', 'label.' + field.replace(':', '_'))
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
						fieldNode.setProp('label-id', 'label.' + aspect.replace(':', '_'))
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
				if 'bpm:startTask' not in [x.content for x in ctx.xpathEval('defaultns:parent')]:
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
		'''Generates workflow internationalization bundle (tasks and transitions)'''

		# set result type
		self.xmlResult = False
		# validate process definition XML
		lang = self.validateProcessDefinition()
		ns = defNS[lang]
		# get new xpath context
		ctx = self.xml.xpathNewContext()
		# register default namespace
		ctx.xpathRegisterNs('defaultns', ns)
		if lang in ['jpdl-3.1', 'jpdl-3.2']:
			# get process name
			procName = self.xml.getRootElement().prop('name').replace(':', '_')
			# add process string
			tmp = [procName + '.workflow']
			# get tasks with non-empty name replacing : by _ and add them to temporary list
#			tmp.extend([procName + '.task.' + x.prop('name').replace(':', '_') for x in ctx.xpathEval('/defaultns:process-definition/defaultns:task-node/defaultns:task[@name!=\'\']')])
			# get all transitions and add them to temporary list
			tmp.extend([procName + '.node.' + x.parent.prop('name') + '.transition.' + x.prop('name') for x in ctx.xpathEval('/defaultns:process-definition/defaultns:task-node[@name!=\'\']/defaultns:transition[@name!=\'\']')])
			# create result list
			self.result = []
			for x in tmp:
				self.result.extend([x + '.title=', x + '.description='])
		elif lang ==  'bpmn-2.0':
			# get process name
			procName = ctx.xpathEval('/defaultns:definitions/defaultns:process')[0].prop('id')
			self.result = [procName + '.workflow.title=', procName + '.workflow.description=']


	def generateShareBundle(self):
		'''Generates share internationalization bundle for found label-id attributes'''
		# set result type
		self.xmlResult = False
		# get new xpath context
		ctx = self.xml.xpathNewContext()
		self.result = [x.prop('label-id') + '=' for x in ctx.xpathEval('/alfresco-config/config/forms/form/appearance/field[@label-id!=\'\']')]
		# remove dplicates
		self.result = list(set(self.result))

	def generateModelBundle(self):
		'''Generates model internationalization bundle'''
		# set result type
		self.xmlResult = False
		# validate task model
		ns = self.validateContentModel()
		# get new xpath context
		ctx = self.xml.xpathNewContext()
		ctx.xpathRegisterNs('defaultns', ns)
		# get content model name
		modelName = self.xml.getRootElement().prop('name').replace(':', '_')
		tmp = ['']
		# extract all types
		tmp.extend(['.type.'+x.prop('name').replace(':', '_') for x in ctx.xpathEval("/defaultns:model/defaultns:types/defaultns:type[@name!='']")])
		# extract all aspects
		tmp.extend(['.aspect.'+x.prop('name').replace(':', '_') for x in ctx.xpathEval("/defaultns:model/defaultns:aspects/defaultns:aspect[@name!='']")])
		# extract all associations
		tmp.extend(['.association.'+x.prop('name').replace(':', '_') for x in ctx.xpathEval("/defaultns:model//defaultns:associations/defaultns:association[@name!='']")])
		# extract all properties
		tmp.extend(['.property.'+x.prop('name').replace(':', '_') for x in ctx.xpathEval("/defaultns:model//defaultns:properties/defaultns:property[@name!='']")])
		# result
		self.result = []
		for item in tmp:
			self.result.extend([modelName+item+'.title=', modelName+item+'.description='])
		# add list constraints items
		for constraintNode in ctx.xpathEval("/defaultns:model//defaultns:constraints/defaultns:constraint[@name!='' and @type='LIST']"):
			ctx.setContextNode(constraintNode)
			self.result.extend(['listconstraint.'+constraintNode.prop('name').replace(':', '_')+'.'+x.content+'=' for x in ctx.xpathEval("defaultns:parameter[@name='allowedValues']/defaultns:list/defaultns:value/text()")])

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
	actionArgs = parser.add_mutually_exclusive_group(required=True)
	actionArgs.add_argument('-s', '--swimlanes', action='store_true', help='generate swimlane tags for process definition')
	actionArgs.add_argument('-m', '--model', action='store_true', help='generate skeleton of workflow model XML')
	actionArgs.add_argument('-w', '--workflow-ui', action='store_true', help='generate skeleton of share-config-custom.xml for workflow UI rendering')
	actionArgs.add_argument('-L', '--model-ui', action='store_true', help='generate skeleton of share-config-custom.xml for model UI rendering')
	actionArgs.add_argument('-W', '--workflow-i18n', action='store_true', help='generate workflow internationalization bundle')
	actionArgs.add_argument('-e', '--share-i18n', action='store_true', help='generate share internationalization bundle')
	actionArgs.add_argument('-Z', '--model-i18n', action='store_true', help='generate model internationalization bundle')

	# add arguments related to model generation
	modelArgs = parser.add_argument_group('Model generation options')
	modelArgs.add_argument('-M', '--mandatory-aspects', action='store_true', help='add mandatory-aspects section to each workflow model type')
	modelArgs.add_argument('-d', '--metadata', action='store_true', help='add metadata to model')
	modelArgs.add_argument('-i', '--item-actions', action='store_true', help='add item-actions section to each workflow model type')
	modelArgs.add_argument('-a', '--aspect', action='store_true', help='add dummy aspect definition section')

	# add arguments related to share config generation
	workflowUIArgs = parser.add_argument_group('Workflow UI config generation options')
	workflowUIArgs.add_argument('-n', '--process-name', default='', action='store', help='workflow process name to be used in generated config (with prefix)')
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
			confgen.generateUIConfig(True, args.process_name, args.label_id, args.sets)
		elif args.model_ui:
			# generate model UI config
			confgen.generateUIConfig('', False, args.label_id, args.sets)
		elif args.workflow_i18n:
			# generate workflow internationalization bundle
			confgen.generateWorkflowBundle()
		elif args.share_i18n:
			# generate share internationalization bundle
			confgen.generateShareBundle()
		elif args.model_i18n:
			# generate model internationalization bundle
			confgen.generateModelBundle()
	except ValidationException, e:
		print('XML validation failed: ' + e.message)
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
