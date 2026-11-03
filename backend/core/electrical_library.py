"""Native circuit symbols, pin geometry and explicit generic simulation models."""
import math


def part(kind,title,prefix,paths,ports,defaults=None,fields=None):
    return {'kind':kind,'title':title,'prefix':prefix,'paths':paths,'ports':[{'id':n,'x':x,'y':y} for n,x,y in ports],
            'defaults':defaults or {},'fields':fields or [],'model':'Generic idealized simulation model; match values to the intended circuit.'}


def number(key,label,unit,minimum=0,maximum=1e12):
    return {'key':key,'label':label,'unit':unit,'type':'number','min':minimum,'max':maximum}


TWO=[('p',-40,0),('n',40,0)]
LIBRARY=[
 part('resistor','Resistor','R',['M-40 0H-24L-20 -10L-12 10L-4 -10L4 10L12 -10L20 10L24 0H40'],TWO,{'value':1000},[number('value','Resistance','Ω',1e-6)]),
 part('capacitor','Capacitor','C',['M-40 0H-6M-6 -20V20M6 -20V20M6 0H40'],TWO,{'value':1e-6},[number('value','Capacitance','F',1e-15,1000)]),
 part('inductor','Inductor','L',['M-40 0H-24C-24 -22 -12 -22 -12 0C-12 -22 0 -22 0 0C0 -22 12 -22 12 0C12 -22 24 -22 24 0H40'],TWO,{'value':.01},[number('value','Inductance','H',1e-12,1000)]),
 part('voltage','Voltage source','V',['M-40 0H-18M18 0H40','M18 0A18 18 0 1 1 -18 0A18 18 0 1 1 18 0','M-12 0H-4M-8 -4V4M5 0H13'],TWO,
      {'value':9,'waveform':'dc','frequency':50,'period':.02,'width':.01},[number('value','Voltage / pulse high','V',-1e6,1e6),{'key':'waveform','label':'Waveform','type':'enum','options':['dc','sine','pulse']},number('frequency','Sine frequency','Hz',.001,1e9),number('period','Pulse period','s',1e-9,1000),number('width','Pulse width','s',1e-9,1000)]),
 part('ground','Ground / reference','G',['M0 -20V0M-20 0H20M-12 7H12M-5 14H5'],[('g',0,-20)]),
 part('terminal','Junction / terminal','X',['M5 0A5 5 0 1 1 -5 0A5 5 0 1 1 5 0'],[('p',0,0)]),
 part('switch','Interactive switch','S',['M-40 0H-20M-20 0L17 -15M20 0H40'],TWO,{'closed':False},[{'key':'closed','label':'Closed','type':'boolean'}]),
 part('contact_no','Relay contact NO','NO',['M-40 0H-8M-8 -15V15M8 -15V15M8 0H40'],TWO,{'control':'','threshold':12},[{'key':'control','label':'Coil label','type':'text'},number('threshold','Coil pickup voltage','V',.001,1e6)]),
 part('contact_nc','Relay contact NC','NC',['M-40 0H-8M-8 -15V15M8 -15V15M8 0H40M-15 22L15 -22'],TWO,{'control':'','threshold':12},[{'key':'control','label':'Coil label','type':'text'},number('threshold','Coil pickup voltage','V',.001,1e6)]),
 part('coil','Relay coil (resistive)','K',['M-40 0H-20V-15H20V15H-20V0M20 0H40M-18 13L18 -13'],TWO,{'value':1000},[number('value','Coil resistance','Ω',1e-6)]),
 part('lamp','Lamp (resistive)','H',['M-40 0H-18M18 0H40','M18 0A18 18 0 1 1 -18 0A18 18 0 1 1 18 0','M-12 -12L12 12M-12 12L12 -12'],TWO,{'value':240},[number('value','Equivalent resistance','Ω',1e-6)]),
 part('diode','Diode','D',['M-40 0H-15M-15 -15L15 0L-15 15ZM15 -15V15M15 0H40'],TWO,{'model':'silicon'},[{'key':'model','label':'Generic model','type':'enum','options':['silicon','led']}]),
 part('npn','NPN transistor','Q',['M-40 0H-10M-10 -18V18M-10 -10L20 -25V-40M-10 10L20 25V40M9 24L20 25L15 15'],[('c',20,-40),('b',-40,0),('e',20,40)],{'beta':100},[number('beta','Generic forward gain','',1,10000)]),
 part('pnp','PNP transistor','Q',['M-40 0H-10M-10 -18V18M-10 -10L20 -25V-40M-10 10L20 25V40M-3 6L-10 10L-2 18'],[('c',20,-40),('b',-40,0),('e',20,40)],{'beta':100},[number('beta','Generic forward gain','',1,10000)]),
 part('motor','Motor — model unresolved','M',['M24 0A24 24 0 1 1 -24 0A24 24 0 1 1 24 0','M-12 12V-12L0 5L12 -12V12','M-40 0H-24M24 0H40'],TWO),
]
BY_KIND={p['kind']:p for p in LIBRARY}


def pin(element,port):
    spec=next(p for p in BY_KIND[element['kind']]['ports'] if p['id']==port)
    angle=math.radians(element.get('rotation',0));x,y=spec['x']*element.get('scale',1),spec['y']*element.get('scale',1)
    return [element['x']+x*math.cos(angle)-y*math.sin(angle),element['y']+x*math.sin(angle)+y*math.cos(angle)]


def example(name='divider'):
    elements=[]
    def symbol(identity,kind,x,y,label,params=None,rotation=0):
        e={'id':identity,'kind':kind,'x':x,'y':y,'label':label,'rotation':rotation,'params':{**BY_KIND[kind]['defaults'],**(params or {})},'reviewed':True}
        elements.append(e);return e
    def wire(identity,a,ap,b,bp,via=None):
        elements.append({'id':identity,'kind':'wire','x':0,'y':0,'points':[pin(a,ap),*(via or []),pin(b,bp)],'from':{'id':a['id'],'port':ap},'to':{'id':b['id'],'port':bp},'reviewed':True})
    if name=='starter':
        v=symbol('v','voltage',120,300,'V1',{'value':24},90)
        stop=symbol('stop','switch',260,170,'STOP',{'closed':True});start=symbol('start','switch',420,170,'START',{'closed':False})
        hold=symbol('hold','contact_no',420,310,'K1 hold',{'control':'K1'});coil=symbol('coil','coil',600,170,'K1')
        g=symbol('g','ground',120,460,'0')
        wire('w1',v,'p',stop,'p',[[120,170]])
        wire('w2',stop,'n',start,'p');wire('w3',start,'n',coil,'p')
        wire('w4',coil,'n',v,'n',[[680,170],[680,400],[120,400]])
        wire('w5',v,'n',g,'g',[[120,400]])
        wire('w6',stop,'n',hold,'p',[[330,170],[330,310]])
        wire('w7',hold,'n',coil,'p',[[520,310],[520,170]])
        title='24 V relay starter — generic coil/contact model'
    else:
        v=symbol('v','voltage',120,240,'V1',{'value':9},90)
        a=symbol('r1','resistor',280,160,'R1',{'value':1000});b=symbol('r2','capacitor' if name=='rc' else 'resistor',440,280,'C1' if name=='rc' else 'R2',{'value':1e-6 if name=='rc' else 2000},90)
        g=symbol('g','ground',120,410,'0')
        if name=='rc':v['params'].update(waveform='pulse',period=.02,width=.01)
        wire('w1',v,'p',a,'p',[[120,160]])
        wire('w2',a,'n',b,'p',[[440,160]])
        wire('w3',b,'n',v,'n',[[440,360],[120,360]])
        wire('w4',v,'n',g,'g',[[120,360]])
        title='RC pulse response' if name=='rc' else '9 V voltage divider'
    return {'schemaVersion':2,'version':1,'name':title,'elements':elements,'sources':[],'issues':[],
            'imported':False,'sourceSha256':None,'modelNotice':'Generic component models; simulated electrical behavior is not physical machine feedback.'}
