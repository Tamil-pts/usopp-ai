"""Read project identity details used by the Validation summary."""
from pathlib import Path
import re
from xml.etree import ElementTree

MAX_SETTINGS_BYTES=1024*1024

def _directory(parent:Path,name:str)->Path|None:
    return next((p for p in parent.iterdir() if p.is_dir() and p.name.casefold()==name.casefold()),None) if parent.is_dir() else None

def _legacy_configurations(root:Path)->list[Path]:
    physical=_directory(root,'Physical')
    # These are AS support folders, not user configurations.
    reserved={'system','visualcomponents','temp'}
    return sorted((p for p in physical.iterdir() if p.is_dir() and p.name.casefold() not in reserved),key=lambda p:p.name.casefold()) if physical else []

def _legacy_cpu_roots(root:Path)->list[Path]:
    pgm=_directory(root,'pgm')
    return sorted((cpu for config in pgm.iterdir() if config.is_dir()
                   for cpu in config.iterdir() if cpu.is_dir() and cpu.name.casefold()=='cpu'),key=lambda p:str(p).casefold()) if pgm else []

def read_automation_studio_version(content:bytes,source:str)->str|None:
    """Return the user-facing major/minor Automation Studio version."""
    text=content.decode('utf-8',errors='ignore').replace('\x00','')
    suffix=Path(source).suffix.casefold()
    patterns=(
        r'AutomationStudio\s+Version\s*=\s*["\']\s*(\d+)\.(\d+)',
        r'Version\s+V\s*(\d+)\.(\d+)',
        r'Automation\s+Studio.{0,80}?(\d+)\.(\d+)',
    )
    for pattern in patterns:
        match=re.search(pattern,text,re.I|re.S)
        if match:
            return f'{int(match.group(1))}.{match.group(2)}'
    # A .GDM is the legacy AS 2.x project descriptor. Keep this fallback for
    # valid descriptors whose binary header does not expose the build string.
    return '2.7' if suffix=='.gdm' and content.startswith(b'B&R') else None

def read_active_configuration(content:bytes,source:str)->dict:
    result={'activeConfiguration':None,'settingsFile':source,'configurationStatus':'unavailable'}
    if len(content)>MAX_SETTINGS_BYTES:
        return {**result,'configurationMessage':'LastUser.set is too large to read as project settings.'}
    try:
        root=ElementTree.fromstring(content)
    except (ElementTree.ParseError,ValueError):
        return {**result,'configurationMessage':'LastUser.set could not be read as XML.'}
    names={node.attrib.get('ActiveConfigurationName','').strip() for node in root.iter()
           if node.tag.rsplit('}',1)[-1]=='ConfigurationManager'}-{''}
    if len(names)!=1:
        message='No active configuration is recorded in LastUser.set.' if not names else 'LastUser.set contains conflicting active configurations.'
        return {**result,'configurationMessage':message}
    return {**result,'activeConfiguration':names.pop(),'configurationStatus':'available','configurationMessage':''}

def read_active_project_hardware(root:Path,active_configuration:str|None)->dict:
    """Read the PLC type and visualization target from the active physical configuration."""
    result={'plcType':None,'screenFolder':None,'screenFolders':[],
            'screenType':None,'screenHardwareFile':None,'configuredHmiObjects':[]}
    logical=_directory(root,'Logical')
    if logical:
        result['screenFolders']=sorted(
            (child.name for child in logical.iterdir() if child.is_dir() and _directory(child,'Pages')),
            key=str.casefold,
        )
    if not active_configuration:
        return result
    if active_configuration in {'.','..'} or any(char in active_configuration for char in '/\\:'):
        return result
    physical_parent=_directory(root,'Physical')
    physical=_directory(physical_parent,active_configuration) if physical_parent else None
    if physical is None:
        return result
    hardware=next((path for path in physical.rglob('*') if path.is_file() and path.name.casefold() in {'hardware.hwl','hardware.hw'}),None)
    if hardware:
        try:
            tree=ElementTree.fromstring(hardware.read_bytes())
            modules=[node for node in tree.iter() if node.tag.rsplit('}',1)[-1].casefold()=='module']
            controller=next((node for node in modules if node.attrib.get('Name','').casefold()=='plc1'),None)
            if controller is None:
                controller=next((node for node in modules if re.match(r'^(?:X20CP|X20C|4PP|PP)',node.attrib.get('Type',''),re.I)),None)
            result['plcType']=controller.attrib.get('Type') if controller is not None else None
        except (ElementTree.ParseError,OSError,ValueError):
            pass
    cpu_sw=next((path for path in physical.rglob('*') if path.is_file() and path.name.casefold()=='cpu.sw'),None)
    if cpu_sw:
        try:
            text=cpu_sw.read_text(encoding='utf-8',errors='replace')
            configured=re.findall(r'<VcDataObject\b[^>]*\bName\s*=\s*["\']([^"\']+)',text,re.I)
            result['configuredHmiObjects']=configured
            available={name.casefold():name for name in result['screenFolders']}
            result['screenFolder']=next((available[name.casefold()] for name in configured if name.casefold() in available),None)
        except OSError:
            pass
    # AS 2.7 records the panel in Physical/<config>/<controller>/<HMI>/hw.cfg.
    # MasterPanel describes the HMI; it is not evidence of the PLC CPU type.
    available={name.casefold():name for name in result['screenFolders']}
    panels=[]
    for path in sorted(physical.rglob('*'),key=lambda p:str(p).casefold()):
        if not path.is_file() or path.name.casefold()!='hw.cfg':
            continue
        target=available.get(path.parent.name.casefold())
        if not target:
            continue
        try:
            tree=ElementTree.fromstring(path.read_bytes())
            masters=[node for node in tree.iter() if node.tag.rsplit('}',1)[-1].casefold()=='masterpanel']
            for master in masters:
                panel_type=next((node.get('Value') for node in master
                                 if node.tag.rsplit('}',1)[-1].casefold()=='property' and node.get('Name','').casefold()=='type'),None) or master.get('Name')
                panels.append((target,panel_type,path.relative_to(root).as_posix()))
        except (ElementTree.ParseError,OSError,ValueError):
            continue
    if result['screenFolder'] is None and len({panel[0] for panel in panels})==1:
        result['screenFolder']=panels[0][0]
    if result['screenFolder'] is None and len(result['screenFolders'])==1:
        result['screenFolder']=result['screenFolders'][0]
    selected=[panel for panel in panels if panel[0]==result['screenFolder']]
    if len(selected)==1:
        _,result['screenType'],result['screenHardwareFile']=selected[0]
    if not result['configuredHmiObjects'] and len({panel[0] for panel in panels})==1:
        result['configuredHmiObjects']=sorted({panel[0] for panel in panels},key=str.casefold)
    return result

def local_project_details(root:Path)->dict:
    children=list(root.iterdir())
    settings=next((p for p in children if p.is_file() and p.name.casefold()=='lastuser.set'),None)
    descriptors=sorted((p for p in children if p.is_file() and p.suffix.casefold() in {'.apj','.gdm'}),key=lambda p:p.name.casefold())
    studio_version=None
    for descriptor in descriptors:
        try:
            studio_version=read_automation_studio_version(descriptor.read_bytes(),descriptor.name)
        except OSError:
            continue
        if studio_version:
            break
    result={'projectName':root.name,'projectPath':str(root),
            'projectFiles':[p.name for p in descriptors],
            'automationStudioVersion':studio_version,
            'plcType':None,'screenFolder':None,'screenFolders':[]}
    configuration={'activeConfiguration':None,'settingsFile':None,'configurationStatus':'missing',
                   'configurationMessage':'LastUser.set was not found in the project root.'}
    if settings is not None:
        try:
            with settings.open('rb') as stream: content=stream.read(MAX_SETTINGS_BYTES+1)
            configuration=read_active_configuration(content,str(settings))
            if studio_version is None:
                studio_version=read_automation_studio_version(content,settings.name)
                result['automationStudioVersion']=studio_version
        except OSError:
            configuration={**configuration,'settingsFile':str(settings),'configurationStatus':'unavailable',
                           'configurationMessage':'LastUser.set is not readable. Check file access permissions.'}
    legacy=str(studio_version or '').startswith('2.')
    configs=_legacy_configurations(root) if legacy else []
    if legacy and settings is None:
        if len(configs)==1:
            configuration.update(activeConfiguration=configs[0].name,configurationStatus='available',
                                 configurationMessage='Selected the single AS 2.7 physical configuration; LastUser.set is not required.')
        else:
            configuration.update(configurationStatus='unavailable',configurationMessage='AS 2.7 requires one physical configuration; selection is unresolved.')
    cpus=_legacy_cpu_roots(root) if legacy else []
    legacy_cpu=None
    scope_message=''
    if legacy:
        if len(configs)==1 and len(cpus)==1 and configuration.get('activeConfiguration','') and configs[0].name.casefold()==configuration['activeConfiguration'].casefold():
            legacy_cpu=cpus[0].relative_to(root).as_posix()
        else:
            scope_message='AS 2.7 CPU ownership is unresolved. Expected one physical configuration and one pgm/<project>/CPU folder; CPU sources were not selected.'
    return {**result,**configuration,**read_active_project_hardware(root,configuration.get('activeConfiguration')),
            'legacyCpuRoot':legacy_cpu,'logicScopeMessage':scope_message}
