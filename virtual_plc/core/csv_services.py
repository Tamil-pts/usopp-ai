"""Reusable BRSE_CSV model translated from its supplied public C source.

Reference: BRSE_CSV.fun, brse_csv{,_alloc,_new,_open,_save,_structarray}.c
and brse_csv_main.h. Storage is the simulator's FileIO store, never host files.
"""
import csv
import io
import re
import struct
from copy import deepcopy

CALLS={'BRSE_CSV_ALLOC':(5,5),'BRSE_CSV_FREE':(1,1),'BRSE_CSV_GETCELL':(3,3),
       'BRSE_CSV_GETCELLASDINT':(3,3),'BRSE_CSV_GETCELLASREAL':(3,3),
       'BRSE_CSV_SETCELL':(4,4),'BRSE_CSV_SETCELLASDINT':(4,4),'BRSE_CSV_SETCELLASREAL':(4,4),
       'BRSE_CSV_ROWS':(1,1),'BRSE_CSV_COLUMNS':(1,1)}
OUTPUTS={'Busy':'BOOL','Progress':'USINT','Done':'BOOL','Error':'BOOL','ErrorMessage':'STRING[32]','ErrorNumber':'UINT','ErrorInfo':'UINT'}
BLOCKS={
 'BRSE_CSV_New':({'AllocIdent':'UDINT','Rows':'UINT','Columns':'USINT','MaxClearSize':'UDINT'},OUTPUTS),
 'BRSE_CSV_Open':({'AllocIdent':'UDINT','FileDevice':'STRING[32]','FileName':'STRING[32]','MaxCopyRows':'UINT','MaxReadSize':'UDINT'},{**OUTPUTS,'sysRows':'UINT'}),
 'BRSE_CSV_Save':({'AllocIdent':'UDINT','FileDevice':'STRING[32]','FileName':'STRING[32]','MaxCopyRows':'UINT','MaxWriteSize':'UDINT'},OUTPUTS),
 'BRSE_CSV_OpenStructArray':({'AllocIdent':'UDINT','StructSize':'UDINT','NumStructItems':'UINT','StructItems':'ARRAY[0..2500] OF BRSE_CSV_StructItem_typ','StartRow':'UINT','MaxCopyRows':'UINT'},OUTPUTS),
 'BRSE_CSV_SaveStructArray':({'AllocIdent':'UDINT','StructSize':'UDINT','NumStructItems':'UINT','StructItems':'ARRAY[0..255] OF BRSE_CSV_StructItem_typ','StartRow':'UINT','MaxCopyRows':'UINT'},OUTPUTS),
}
FORMATS={1:('BOOL','?'),2:('SINT','b'),3:('INT','h'),4:('DINT','i'),5:('USINT','B'),6:('UINT','H'),7:('UDINT','I'),8:('REAL','f'),252:('LREAL','d')}


class CSVRuntime:
    def __init__(self,services):
        self.services=services;self.runtime=services.runtime;self.sheets={};self.pending={}

    @property
    def vendor(self):return self.runtime.vendor

    def cell(self,sheet,row,col):
        if not 0<=row<sheet['rows'] or not 0<=col<sheet['columns']:return None
        return sheet['address']+16+(row*sheet['maxColumns']+col)*(sheet['entrySize']+1)

    def put(self,sheet,row,col,text):
        address=self.cell(sheet,row,col)
        if address is None:return 0
        raw=str(text).encode('latin-1',errors='replace');limit=sheet['entrySize']
        self.vendor.write(address,raw[:limit]+b'\0');return 255 if len(raw)>limit else 1

    def call(self,name,values):
        if name=='BRSE_CSV_ALLOC':
            rows,columns,entry,rowdelimiter,coldelimiter=values
            size=16+2*rows*columns*(entry+1)
            if not 1<=rows<=65535 or not 1<=columns<=255 or not 1<=entry<=255 or size>4*1024*1024:raise ValueError('CSV allocation exceeds its documented/bounded dimensions')
            key=('csv',self.services.ident());address=self.vendor.allocate(key,size)
            self.vendor.write(address,struct.pack('<I',address))
            self.sheets[address]={'address':address,'key':key,'maxRows':rows,'maxColumns':columns,'entrySize':entry,'rows':0,'columns':0,'rowDelimiter':rowdelimiter or '\r\n','columnDelimiter':coldelimiter or ';'}
            return address
        ident=values[0];sheet=self.sheets.get(ident)
        if name=='BRSE_CSV_FREE':
            if sheet is None:return False
            self.vendor.release(sheet['key']);self.sheets.pop(ident);return True
        if name in {'BRSE_CSV_ROWS','BRSE_CSV_COLUMNS'}:return sheet[name.rsplit('_',1)[1].lower()] if sheet else 0
        address=self.cell(sheet,values[1],values[2]) if sheet else None
        if name.startswith('BRSE_CSV_GETCELL'):
            text=self.vendor.string(address) if address else ''
            if name=='BRSE_CSV_GETCELL':return address or self.vendor.allocate(('csv','empty'),1,b'\0')
            pattern=r'\s*([+-]?\d+)' if name.endswith('DINT') else r'\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)'
            match=re.match(pattern,text)
            return (int if name.endswith('DINT') else float)(match[1]) if match else 0
        if not address:return 0
        text=self.vendor.string(values[3]) if name=='BRSE_CSV_SETCELL' else str(values[3]) if name.endswith('DINT') else format(values[3],'.7g')
        return self.put(sheet,values[1],values[2],text)

    def error(self,b,number,text,info=0):
        b.update(Busy=False,Done=False,Error=True,ErrorNumber=number,ErrorMessage=text[:32],ErrorInfo=info);return b

    def block(self,kind,key,block):
        b=deepcopy(block);b.update(Busy=False,Done=False,Error=False,Progress=0,ErrorNumber=0,ErrorInfo=0,ErrorMessage='')
        sheet=self.sheets.get(b['AllocIdent'])
        if sheet is None:return self.error(b,52002,'Wrong AllocIdent')
        saved=self.pending.get(key)
        if saved is None:self.pending[key]=(self.runtime.scan_count,0);b['Busy']=True;return b
        if saved[0]==self.runtime.scan_count:b['Busy']=True;return b
        if kind=='BRSE_CSV_New':
            if b['Rows']>sheet['maxRows']:return self.error(b,52000,'Rows exceed allocation')
            if b['Columns']>sheet['maxColumns']:return self.error(b,52012,'Columns exceed allocation')
            sheet.update(rows=b['Rows'],columns=b['Columns'])
            for row in range(sheet['rows']):
                for column in range(sheet['columns']):self.put(sheet,row,column,'')
        elif kind in {'BRSE_CSV_Open','BRSE_CSV_Save'}:
            filekey=(b['FileDevice'],b['FileName'].casefold())
            if kind=='BRSE_CSV_Open':
                raw=self.vendor.files.get(filekey)
                if raw is None:return self.error(b,52008,'Error opening file',20708)
                rows=list(csv.reader(io.StringIO(bytes(raw).decode('latin-1')),delimiter=sheet['columnDelimiter']))
                columns=max(map(len,rows),default=0)
                if len(rows)>sheet['maxRows']:return self.error(b,52011,'Rows exceed allocation',len(rows))
                if columns>sheet['maxColumns']:return self.error(b,52012,'Columns exceed allocation',columns)
                if not rows:return self.error(b,52023,'File length is zero')
                sheet.update(rows=len(rows),columns=columns)
                for row,data in enumerate(rows):
                    for col,text in enumerate(data):self.put(sheet,row,col,text)
                b['sysRows']=len(rows)
            else:
                stream=io.StringIO();writer=csv.writer(stream,delimiter=sheet['columnDelimiter'],lineterminator=sheet['rowDelimiter'])
                for row in range(sheet['rows']):writer.writerow([self.vendor.string(self.cell(sheet,row,col)) for col in range(sheet['columns'])])
                raw=stream.getvalue().encode('latin-1')
                if sum(len(v) for k,v in self.vendor.files.items() if k!=filekey)+len(raw)>16*1024*1024:raise ValueError('Virtual FileIO capacity exceeded')
                self.vendor.files[filekey]=bytearray(raw)
        else:
            items=[]
            for item in b['StructItems'][:255]:
                if not item['Address'] or not item['Type']:break
                items.append(item)
            if not items:return self.error(b,52018,'No structure items defined')
            if not sheet['rows'] or not b['NumStructItems']:return self.error(b,52019,'No rows defined')
            if not sheet['columns']:return self.error(b,52020,'No columns defined')
            start=saved[1];end=min(sheet['rows'],b['StartRow']+b['NumStructItems']);batch=b['MaxCopyRows'] or end
            start=max(start,b['StartRow'])
            for row in range(start,min(start+batch,end)):
                for col,item in enumerate(items[:sheet['columns']]):
                    typ=item['Type'];dtype,fmt=FORMATS.get(typ,('STRING',None))
                    width=struct.calcsize('<'+fmt) if fmt else typ-9+1
                    if not 1<=width<=256:raise ValueError('Unsupported CSV structure type code')
                    stride=b['StructSize'] or width;address=item['Address']+(row-b['StartRow'])*stride
                    if kind=='BRSE_CSV_OpenStructArray':
                        text=self.vendor.string(self.cell(sheet,row,col))
                        value=float(text or 0) if dtype in {'REAL','LREAL'} else int(float(text or 0)) if fmt else text
                        spec=self.runtime.memory.spec('STRING['+str(width-1)+']' if not fmt else dtype)
                        self.vendor.write(address,self.vendor.encode(self.runtime.memory.coerce(value,spec),spec))
                    else:
                        value=struct.unpack('<'+fmt,self.vendor.read(address,width))[0] if fmt else self.vendor.string(address)
                        self.put(sheet,row,col,value)
            nextrow=min(start+batch,end)
            if nextrow<end:
                self.pending[key]=(self.runtime.scan_count,nextrow);b.update(Busy=True,Progress=int(100*nextrow/end));return b
        self.pending.pop(key,None);b.update(Done=True,Busy=False,Progress=100);return b

    def reset(self):
        for sheet in self.sheets.values():self.vendor.release(sheet['key'])
        self.sheets.clear();self.pending.clear()
