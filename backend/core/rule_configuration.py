"""Deterministic conversion of Chopper conversation answers into reviewable rules."""
import hashlib
import json
import re
import uuid
from python_engine.hmi_requirements import parse_requirements, reference_xml
import xml.etree.ElementTree as ET
from backend.core.rule_checklist import _memcpy_signatures


def guided_configuration(answers: dict) -> dict:
    from backend.core.identifiers import rule_id
    config=_guided_configuration(answers)
    for rule in config.get('rules',[]):
        if rule.get('id'):rule['standardId']=rule_id(rule['id'])
    return config


def _guided_configuration(answers: dict) -> dict:
    from backend.core.identifiers import rule_id
    answers=dict(answers)
    if not answers.get('ruleId') and answers.get('configurationFormat')!='serial-mapping-v1': answers['ruleId']=rule_id()
    if answers.get('configurationFormat')=='serial-mapping-v1':
        from python_engine.module_serial_mapping import normalize_configuration, configuration_errors
        from backend.core.rule_features import rule_library
        rule=answers.get('rule')
        if not isinstance(rule,dict): raise ValueError('Enter the serial-number rule configuration.')
        errors=configuration_errors(rule)
        if errors: raise ValueError('; '.join(errors))
        known={str(item.get('id')) for item in rule_library()}
        if rule.get('id') in known and answers.get('editingRuleId')!=rule.get('id'): raise ValueError('This rule already exists. Open the saved rule to edit it.')
        rule=normalize_configuration(rule)
        rule.update({'enabled':False,'reviewStatus':'Needs engineer review'})
        return {'version':'4.60.3','rules':[rule]}
    if answers.get('configurationFormat') == 'grouped-v1':
        from python_engine.structured_requirements import configuration
        from backend.core.rule_features import rule_library
        known={str(rule.get('id')) for rule in rule_library()}
        if answers.get('ruleId') in known and answers.get('editingRuleId')!=answers.get('ruleId'):
            raise ValueError('This Rule ID already exists. Start a new rule to generate another ID, or edit the saved rule.')
        return configuration(answers)
    if answers.get('schemaVersion') == 2:
        from python_engine.structured_rule_checks import configuration_errors
        checks=answers.get('checks') or []
        if not isinstance(checks,list): raise ValueError('Checks must be a list.')
        errors=configuration_errors(checks)
        name=str(answers.get('name') or '').strip()
        if not name: errors.append('Enter a rule name.')
        if not answers.get('category'): errors.append('Choose a category.')
        rule={key:answers.get(key) for key in ['category','description','featureName']}
        rule.update({'id':str(answers.get('ruleId') or 'R-'+uuid.uuid4().hex.upper()),'name':name or 'Untitled draft',
                     'kind':'structured_checks','schemaVersion':2,'version':'1.0','enabled':False,
                     'reviewStatus':'Needs engineer review','checks':checks,
                     'machineScope':[answers.get('machineDepartment') or 'All'],
                     'machineDepartment':answers.get('machineDepartment') or 'All',
                     'machineModels':[answers.get('machineModel') or 'All'],
                     'expected':answers.get('description') or name,'configurationIssues':errors,
                     'featureId':re.sub(r'[^a-z0-9_-]+','_',str(answers.get('featureName') or 'Unassigned').lower()).strip('_')})
        if errors: rule['needsRuleConfiguration']=True
        return {'version':'4.60.3','rules':[rule]}
    supplied_name=str(answers.get('name') or '').strip()
    name=supplied_name or str(answers.get('description') or '').strip() or f"Unconfigured rule {uuid.uuid4().hex[:6].upper()}"
    description=str(answers.get('description') or name).strip()
    source=str(answers.get('subroutine') or '').strip()
    logic=str(answers.get('exactLogic') or '').strip()
    supplied_alternatives=answers.get('logicAlternatives')
    if isinstance(supplied_alternatives,str):
        try: supplied_alternatives=json.loads(supplied_alternatives)
        except (TypeError,ValueError): supplied_alternatives=None
    if isinstance(supplied_alternatives,list):
        alternatives=[str(value).strip() for value in supplied_alternatives if str(value).strip()]
    else:
        # Read legacy conversation answers only; the review form stores blocks separately.
        alternatives=[part.strip() for part in re.split(r'(?im)^\s*or\s*$',logic) if part.strip()]
    needs_logic_configuration=not source or not alternatives
    needs_rule_configuration=(not supplied_name or not str(answers.get('category') or '').strip() or
                              bool(answers.get('categorySkipped')) or bool(answers.get('needsGroupCodeConfiguration')) or
                              (answers.get('category')=='PLC logic + HMI' and not answers.get('template')))
    if answers.get('category') == 'Logic / declaration' and not (answers.get('variable') and answers.get('datatype')):
        needs_rule_configuration=True
    if answers.get('category') == 'PLC logic + HMI' and answers.get('template') == 'Custom PLC + HMI' and not (answers.get('variable') and answers.get('hmiPages')):
        needs_rule_configuration=True
    if isinstance(answers.get('crossFunctionChecks'),str):
        try: cross_checks=json.loads(answers['crossFunctionChecks'])
        except (TypeError,ValueError): cross_checks=[]
    else:
        cross_checks=answers.get('crossFunctionChecks') or []
    if not isinstance(cross_checks,list): raise ValueError('Cross-function checks must be a list.')
    normalized_cross_checks=[]
    for index,check in enumerate(cross_checks):
        if not isinstance(check,dict): raise ValueError(f'Cross-function check {index+1} must be an object.')
        variants=check.get('logicAlternatives') or ([check.get('exactLogic')] if check.get('exactLogic') else [])
        if isinstance(variants,str): variants=[part.strip() for part in re.split(r'(?im)^\s*or\s*$',variants) if part.strip()]
        variants=[str(value).strip() for value in variants if str(value).strip()] if isinstance(variants,list) else []
        if not variants: raise ValueError(f'Add expected logic to cross-function check {check.get("name") or index+1}.')
        files=check.get('sourceFiles') or []
        if isinstance(files,str): files=[value.strip().replace('\\','/') for value in re.split(r'[\r\n,;]+',files) if value.strip()]
        if not isinstance(files,list): raise ValueError(f'Source files for cross-function check {index+1} must be a list.')
        files=[str(value).strip().replace('\\','/') for value in files if str(value).strip()]
        if not files and (check.get('subroutine') or check.get('sourceFile')):
            files=[str(check.get('subroutine') or check.get('sourceFile')).strip().replace('\\','/')]
        if not check.get('searchAllSubroutines') and not files and not (check.get('subroutine') or check.get('sourceFile')):
            raise ValueError(f'Choose all other subroutines or enter a source file for cross-function check {index+1}.')
        normalized={**check,'name':str(check.get('name') or f'Cross-function check {index+1}').strip(),'logicAlternatives':variants,'exactLogic':variants[0],'sourceFiles':files,'searchAllSubroutines':bool(check.get('searchAllSubroutines'))}
        normalized_cross_checks.append(normalized)
    rule={
        'id':str(answers.get('ruleId') or 'R-'+hashlib.sha256((name+source+logic+uuid.uuid4().hex).encode()).hexdigest()[:10].upper()),
        'name':name,'description':description,'version':'1.0','enabled':False,'reviewStatus':'Needs engineer review',
        'machineDepartment':answers.get('machineDepartment') or 'All',
        'machineModels':[answers.get('machineModel') or 'All'],
        'machineScope':[answers.get('machineDepartment') or 'All'],
        'category':answers.get('category') or 'Structured Text logic',
        'featureName':str(answers.get('featureName') or 'Spin Connect').strip(),
        'featureId':re.sub(r'[^a-z0-9_-]+','_',str(answers.get('featureName') or 'Spin Connect').strip().lower()).strip('_'),
        'ruleScope':answers.get('scope') or 'Spin Connect',
        'subroutine':source,'logicAlternatives':alternatives,
        'exactLogic':alternatives[0] if alternatives else '',
        'expected':str(answers.get('expected') or description),
        'variable':str(answers.get('variable') or '').strip(),
        'allowedDatatypes':[x.strip() for x in str(answers.get('datatype') or '').split(',') if x.strip()],
    }
    if needs_logic_configuration: rule['needsLogicConfiguration']=True
    if needs_rule_configuration: rule['needsRuleConfiguration']=True
    if not answers.get('variable') and answers.get('datatype'):
        rule['needsRuleConfiguration']=True
    if normalized_cross_checks: rule['crossFunctionChecks']=normalized_cross_checks
    # Preserve a multi-source traceability request as explicit, reviewable scope.
    # Paths are project-relative and may name task files, local declarations, or HMI pages.
    source_files=[x.strip().replace('\\','/') for x in re.split(r'[\r\n,;]+',str(answers.get('sourceFiles') or source)) if x.strip()]
    if source_files:
        rule['sourceFiles']=list(dict.fromkeys(source_files))
    hmi_pages=[x.strip().replace('\\','/') for x in re.split(r'[\r\n,;]+',str(answers.get('hmiPages') or '')) if x.strip()]
    if hmi_pages:
        rule['crossDomainHmiPages']=list(dict.fromkeys(hmi_pages))
    source_roles=[x.strip() for x in re.split(r'[\r\n,;]+',str(answers.get('sourceRoles') or '')) if x.strip()]
    if source_roles:
        rule['sourceRoles']=list(dict.fromkeys(source_roles))
    group=str(answers.get('groupCode') or '').strip()
    if group.casefold()=='all':rule.update(groupCodeMode='all',groupCodes=[])
    if group and group.casefold() not in {'all','none','skip'}:
        if not re.fullmatch(r'\d+(?:\s*,\s*\d+)*',group): raise ValueError('Enter Group Codes separated by commas, for example 140, 40, 50.')
        codes=list(dict.fromkeys(int(value.strip()) for value in group.split(',')))
        if len(codes)==1:rule['groupCode']=codes[0]
        else:rule.update(groupCodeMode='selected',groupCodes=codes)
    category=str(rule['category']).strip().casefold()
    if answers.get('template')=='Lot Name: PLC + HMI':
        rule['kind']='lot_name_packet_hmi'
        if not rule.get('groupCodeMode'): rule.setdefault('groupCode',140)
        rule['pagePrefix']=str(answers.get('pagePrefix') or 'Process').removesuffix('.pages').removesuffix('.page')
        rule['label']=str(answers.get('label') or 'LOT NAME')
        rule['controlNamePrefix']=str(answers.get('controlPrefix') or 'String')
        rule['inputTouchpad']=str(answers.get('touchpad') or 'Source[local].TouchPad[AlphaPadQVGA]')
        rule['requireSameVariable']=True
        variables=re.findall(r'memcpy\s*\(\s*ADR\s*\(.*?\)\s*,\s*ADR\s*\(\s*(\w+)', '\n'.join(alternatives),re.I|re.S)
        rule['acceptedVariables']=list(dict.fromkeys(variables))
        if alternatives and not variables: raise ValueError('The Lot Name alternatives must contain a memcpy source variable.')
        if not variables: rule['needsLogicConfiguration']=True
        reference=str(answers.get('hmiXml') or '').strip()
        if reference:
            requirements=parse_requirements(reference)
            rule['hmiControlChecks']=requirements
            rule['hmiPropertiesInput']=reference
            rule['hmiReferenceXml']=reference_xml(requirements)
            rule['controlNamePrefix']=requirements[0]['name'] or rule['controlNamePrefix']
            rule['requiredProperties']=requirements[0]['properties']
            rule['explicitHmiProperties']=True
    elif category == 'logic with condition':
        condition_pattern=r'\bIF\s*\(?\s*([A-Za-z_]\w*)\s*(<=|>=|<>|=|<|>)\s*(-?\d+(?:\.\d+)?)\s*\)?\s*THEN\b.*?\b\1\s*:=\s*(-?\d+(?:\.\d+)?)\s*;'
        conditions=[re.search(condition_pattern,alternative,re.I|re.S) for alternative in alternatives]
        if not alternatives:
            rule['kind']='condition_assignment'
            rule['needsLogicConfiguration']=True
            return {'version':'4.52','rules':[rule]}
        if not conditions or any(condition is None for condition in conditions):
            rule['kind']='exact_logic_declaration'
            return {'version':'4.52','rules':[rule]}
        signatures={(condition.group(2),condition.group(3),condition.group(4)) for condition in conditions if condition}
        if len(signatures)!=1:
            rule['kind']='exact_logic_declaration'
            return {'version':'4.52','rules':[rule]}
        condition=conditions[0]
        rule.update({'kind':'condition_assignment','variable':condition.group(1),'acceptedVariables':list(dict.fromkeys(item.group(1) for item in conditions if item)),'comparison':condition.group(2),'threshold':condition.group(3),'assignedValue':condition.group(4)})
    elif category == 'group code wise parameter check':
        mode_text=str(answers.get('groupCodeMode') or 'All group codes').strip().casefold()
        if mode_text == 'all group codes':
            rule['groupCodeMode']='all'
        elif mode_text == 'all group codes except':
            rule['groupCodeMode']='exclude'
        elif mode_text == 'selected group codes':
            rule['groupCodeMode']='selected'
        else:
            raise ValueError('Choose all Group Codes, all except selected codes, or selected Group Codes.')
        codes=[int(x.strip()) for x in re.split(r'[,;\s]+',str(answers.get('groupCodes') or '')) if x.strip()]
        if rule['groupCodeMode'] in {'exclude','selected'} and not codes and not answers.get('needsGroupCodeConfiguration'):
            raise ValueError('Enter at least one Group Code for this scope.')
        if rule['groupCodeMode'] in {'exclude','selected'} and not codes:
            rule['needsRuleConfiguration']=True
        rule['groupCodes']=codes
        inferred_variable=re.search(r'ADR\s*\(\s*(Blow_room_product_code)\s*\)',logic,re.I)
        product_code_variable=str(answers.get('variable') or (inferred_variable.group(1) if inferred_variable else '')).strip().casefold()
        if product_code_variable == 'blow_room_product_code' and rule['groupCodeMode'] == 'exclude' and 11 in codes:
            rule['kind']='group_code_exact_logic'
            rule['excludeGroupCodes']=codes
            rule['sourceFile']=source
            rule['expected']=str(answers.get('expected') or 'Every active Group Code except 11 starts with the two-byte Blow_room_product_code mapping.')
            return {'version':'4.52','rules':[rule]}
        signatures=_memcpy_signatures(logic)
        if not signatures and alternatives:
            raise ValueError('Add expected memcpy packet logic so parameter names and byte sizes can be checked in every selected Group Code.')
        rule['kind']='checklist_packet_signatures'
        rule['sourceFile']=source
        rule['requiredParameters']=signatures
        if not signatures: rule['needsLogicConfiguration']=True
        if answers.get('needsGroupCodeConfiguration'): rule['needsRuleConfiguration']=True
        rule['expected']=str(answers.get('expected') or f"Required packet parameters must be present in {mode_text}.")
    elif category.startswith('hmi') and re.search(r'(?im)^\s*Name\s*=',logic):
        rule['kind']='hmi_control_properties'
        rule['hmiControlChecks']=parse_requirements(logic)
        rule['hmiPropertiesInput']=logic
        rule['hmiReferenceXml']=reference_xml(rule['hmiControlChecks'])
    elif str(rule['category']).casefold() == 'hmi screen + datapoint mapped' and answers.get('pageName'):
        rule['kind']='hmi_page_structure'
        configured_name=str(answers.get('pageName') or 'MMS_CONFIG.page').strip()
        rule['acceptedPageNames']=[configured_name, configured_name.removesuffix('.pages').removesuffix('.page')+'.pages']
        rule['requiredObjects']=['Text','Numeric','Control','HotSpot']
        rule['requiredProperties']=['IndexDatapoint','LockingDatapoint','TextGroup']
        rule['expected']=str(answers.get('expected') or 'The MMS Configure screen shall contain Text, Numeric, Control and HotSpot objects with IndexDatapoint, LockingDatapoint and TextGroup properties.')
    else:
        cross_domain_categories={
            'cross-domain traceability',
            'plc logic + hmi',
            'logic traceability in various subroutines',
            'hmi screen + datapoint mapped',
            'hmi text groups',
            'hmi touch pad',
            'hmi alarm declaration',
        }
        rule['kind']='cross_domain_traceability' if category in cross_domain_categories else 'exact_logic_declaration'
    # New guided group rules evaluate complete alternatives in every branch.
    # Legacy checklist rules retain their parameter-signature validator.
    if category == 'group code wise parameter check':
        rule['kind']='group_code_exact_logic'
    return {'version':'4.52','rules':[rule]}
