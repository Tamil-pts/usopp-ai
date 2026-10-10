"""Nami V1.5 simulator payloads, using the reference application's byte layouts."""
import struct
from datetime import datetime

DEFAULT_STATE = dict(
    machineId=0, programVersion=5.296, deliverySpeed=285.5, sliverHank=0.128,
    productionKgHr=84.5, fiveMtrCv=2.15, lickerinSuction=145.0, flatSuction=152.0,
    alValue=100.2, actValue=99.8, dPercent=0.4, currentLength=4250,
    totalCanLength=5000, emptyCanLength=750, machineStatus=8, chutePressure=165,
    feedWeight=520.0, feedThicknessLHS=4.2, cylinderRpm=580, flatsRpm=240.0,
    lickerinRpm=1150.0, activePowerKw=12.4, totalKwh=342.8, voltageAvg=415.2,
    currentAvg=22.8, lotName='CARD-COTTON-T40', doffCount=12,
    alarms=[0, 4, 0, 16] + [0]*13,
)


def frame(machine_id, payload=b'', result=0):
    header = bytes([3, machine_id & 255, result & 255]) + len(payload).to_bytes(2, 'big')
    data = header + payload
    checksum = 0
    for byte in data:
        checksum ^= byte
    return data + bytes([checksum, 2])


def payload(group, state):
    size = {10:4, 20:200, 30:17, 130:172, 140:142, 150:63, 240:20,
            250:50, 410:78, 600:368}.get(group, 202 if group in range(40,111,10)
                                     else 122 if group in (500,510,520,530) else 20)
    data = bytearray(size)
    def put(kind, offset, value):
        struct.pack_into('<'+kind, data, offset, value)
    def floats(offset, values):
        for index, value in enumerate(values): put('f', offset+index*4, value)
    def text(offset):
        value = state['lotName'].encode('utf-8')[:size-offset]
        data[offset:offset+len(value)] = value
    if group == 10:
        put('f',0,state['programVersion'])
    elif group == 20:
        floats(0,[state[k] for k in ('deliverySpeed','sliverHank','productionKgHr','fiveMtrCv',
                                    'lickerinSuction','flatSuction','alValue','actValue','dPercent')])
        for offset,key in ((36,'currentLength'),(38,'totalCanLength'),(40,'emptyCanLength'),(42,'machineStatus')):
            put('H',offset,state[key])
        put('h',44,state['chutePressure']);put('f',46,state['feedWeight'])
        floats(50,[state['feedThicknessLHS'],4.15,4.22,4.18,4.25,4.20,28.4,105.2])
        put('H',82,state['cylinderRpm'])
        floats(84,[state['flatsRpm'],state['lickerinRpm'],850,420,2.35,2.18])
        for i in range(20):
            offset=108+i*4
            if offset+4<=188:put('f',offset,45.5+i*2.1)
        data[188]=1;data[189]=1;put('H',195,1);data[196]=1;data[199]=1
    elif group == 30:
        data[:] = bytes((state['alarms']+[0]*17)[:17])
    elif group in range(40,111,10):
        floats(0,[1 if group==40 else group//10-3,7,9,2026,14,30,0.125,680.5,7.5,25,0.5,12])
        for offset,value in ((56,93.5),(60,91.2),(88,state['voltageAvg']),(92,state['currentAvg']),
                             (96,0.92),(100,50.02),(104,state['activePowerKw']),(116,state['totalKwh'])):
            put('f',offset,value)
        text(152)
    elif group==130:
        data[0]=1
        for kind,offset,value in [('H',6,120),('H',23,250),('f',37,1),('f',41,1.2),('h',116,900),('h',118,750)]:put(kind,offset,value)
    elif group==140:
        for kind,offset,value in [('b',0,1),('B',1,40),('H',2,4500),('H',4,280),('f',14,0.125),
                                 ('f',18,0.126),('f',22,0.010),('B',30,1),('H',51,150),('h',53,148),
                                 ('H',78,550),('H',80,548),('f',82,1150),('f',86,1148.5)]:put(kind,offset,value)
    elif group==150:
        now=datetime.now()
        for kind,offset,value in [('B',0,now.day),('B',1,now.month),('H',2,now.year),('B',4,now.hour),
                                 ('B',5,now.minute),('B',6,now.second),('H',7,101),('H',9,15),('H',11,6),
                                 ('H',13,2024),('f',15,12450.5),('f',19,1580.2),('f',23,128500),('f',27,3)]:put(kind,offset,value)
    elif group==240:data[:]=bytes([1]*20)
    elif group==250:
        for kind,offset,value in [('f',0,1.2),('f',4,0.85),('f',8,2.15),('f',12,2.05),
                                 ('f',28,150),('f',32,515),('h',44,2)]:put(kind,offset,value)
    elif group==410:
        floats(0,[state['sliverHank'],state['deliverySpeed']]);put('H',8,state['currentLength'])
        floats(10,[state['voltageAvg'],state['currentAvg'],0.92,50.05,state['activePowerKw'],13.8,4.2,state['totalKwh']])
    elif group in (500,510,520,530):
        floats(0,[7,9,2026,12,45,0.125,280,24.5,4500,3.5]);put('f',56,15.2);text(72)
    elif group==600:
        floats(0,[state['deliverySpeed'],state['cylinderRpm'],state['flatsRpm'],state['lickerinRpm']])
        floats(28,[42.5+i*2.3 for i in range(8)])
        floats(60,[1.2+(i%3)*0.4 for i in range(8)])
        floats(92,[state['lickerinSuction'],state['flatSuction']])
    return bytes(data)
