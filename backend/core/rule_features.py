"""Feature organisation for the existing rule library; check definitions remain intact."""
from __future__ import annotations
import json
import os
import re
import tempfile
from threading import RLock
from backend.core.runtime import BASE, DEFAULT_RULES

LOCK = RLock()
NAMES = {'spin_connect':'Spin Connect','logic_checks':'Logic checks','library_checks':'Library checks','hmi_screens':'HMI screens','hardware_io':'Hardware / I/O','declarations':'Variable declarations','project_configuration':'Project configuration','text_groups':'Text groups','touch_pads':'Touch pads','alarms':'Alarms','traceability':'Cross-domain traceability'}

def safe_id(value):
    return re.sub(r'[^a-z0-9_-]+', '_', str(value).strip().lower()).strip('_')[:100]

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            name = stream.name
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name): os.unlink(name)

def rule_library():
    merged = {}
    if DEFAULT_RULES.exists():
        for rule in json.loads(DEFAULT_RULES.read_text(encoding='utf-8')).get('rules', []):
            merged[rule['id']] = {**rule, 'machineScope':rule.get('machineScope') or ['All']}
    latest = {}
    for path in sorted((BASE/'rules'/'modules').glob('*.json'), key=lambda p:p.stat().st_mtime_ns):
        module = json.loads(path.read_text(encoding='utf-8'))
        latest[module.get('id',path.stem)] = module
    for module in sorted(latest.values(), key=lambda m:0 if isinstance(m.get('rules'),list) else 1):
        for rule in module.get('rules', [module]):
            scope = [rule['machineDepartment']] if rule.get('machineDepartment') else rule.get('machineScope') or module.get('machineScope') or ['All']
            merged[rule['id']] = {**rule, 'moduleId':module.get('id'), 'machineScope':scope}
    from python_engine.module_serial_mapping import normalize_configuration
    from backend.core.identifiers import rule_id
    return [{**(normalize_configuration(rule) if rule.get('kind')=='module_serial_mapping' or rule.get('id')=='BR_MODULE_SERIAL_420' else rule),'standardId':rule_id(rule['id'])} for rule in merged.values()]

def classify(rule):
    text = ' '.join(str(rule.get(k,'')) for k in ('id','name','subroutine','sourceFile')).casefold().replace('_',' ')
    for words in (('lot name','lotname'),('password','login level'),('ip add','ip address','gateway','ip setting'),('stoppage','stop reason')):
        if any(word in text for word in words): return 'spin_connect'
    category = str(rule.get('category') or '').strip().casefold()
    category_features = {
        'plc logic + hmi':'traceability',
        'logic traceability in various subroutines':'traceability',
        'cross-domain traceability':'traceability',
        'logic / declaration':'declarations',
        'declaration':'declarations',
        'hmi screen + datapoint mapped':'hmi_screens',
        'hmi screen / datapoint':'hmi_screens',
        'hmi text groups':'text_groups',
        'text group':'text_groups',
        'hmi touch pad':'touch_pads',
        'touch pad':'touch_pads',
        'hmi alarm declaration':'alarms',
        'alarm':'alarms',
        'plc configuration':'project_configuration',
        'hardware / i/o':'hardware_io',
        'library check':'library_checks',
    }
    if category in category_features: return category_features[category]
    if str(rule.get('id','')).startswith(('SC-','CP-')) or 'mms' in text: return 'spin_connect'
    if category in {'group code wise parameter check','logic','logic with condition'}: return 'spin_connect'
    return 'logic_checks'

def catalog():
    with LOCK:
        rules = rule_library()
        known_rule_ids = {rule['id'] for rule in rules}
        folder = BASE/'rules'/'features'
        features = {'spin_connect':{'id':'spin_connect','name':'Spin Connect','description':'','ruleIds':[]}}
        for path in sorted(folder.glob('*.json')):
            if path.name == 'pipeline.json': continue
            feature = json.loads(path.read_text(encoding='utf-8'))
            features[feature['id']] = feature
        for rule in rules:
            explicit = safe_id(rule.get('featureId') or rule.get('featureName',''))
            assigned = [f['id'] for f in features.values() if rule['id'] in f.get('ruleIds',[])]
            if explicit and explicit not in assigned:
                # A rule can be shared by several features. Refresh must never
                # remove a manual link when the rule names another default feature.
                features.setdefault(explicit, {'id':explicit,'name':rule.get('featureName') or NAMES.get(explicit,explicit.replace('_',' ').title()),'description':'','ruleIds':[]})
                features[explicit].setdefault('ruleIds',[]).append(rule['id'])
                assigned.append(explicit)
            if not assigned:
                fid = explicit or classify(rule)
                features.setdefault(fid, {'id':fid,'name':rule.get('featureName') or NAMES.get(fid,fid.replace('_',' ').title()),'description':'','ruleIds':[]})
                features[fid].setdefault('ruleIds',[]).append(rule['id'])
                assigned = [fid]
            rule['featureIds'] = assigned
        for feature in features.values():
            path = folder/(safe_id(feature['id'])+'.json')
            # Older feature records may outlive rules that were removed from
            # the library. Do not expose those dangling IDs as linkable checks.
            feature['ruleIds'] = list(dict.fromkeys(
                rule_id for rule_id in feature.get('ruleIds', [])
                if rule_id in known_rule_ids
            ))
            if not path.exists() or json.loads(path.read_text(encoding='utf-8')) != feature: write_json(path,feature)
        return {'rules':rules,'features':list(features.values())}
