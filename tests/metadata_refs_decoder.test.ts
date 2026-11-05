import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
import {parseExcelWithDropdownReferences,parseCSVMetadata,requireSheet2References,MetadataValidationError,exportMetadataTemplateExcel} from '../nami/src/utils/metadataParser';
import {decoderCsv,decoderValueRow,decoderFrameRow,responseDecoderRows,decimalBytesFromHex,DECODER_CSV_HEADERS} from '../nami/src/utils/decoderCsv';
import {parseGroupValues} from '../nami/src/utils/packetParser';
import type {MetadataItem,ParsedParamValue,GroupResponseData} from '../nami/src/types';

const require=createRequire(new URL('../nami/package.json',import.meta.url));const XLSX=require('xlsx');
const headers=['Parameters','GROUP_CODE','TAG_CODE','TAG_DATA_TYPE','OFFSET','Machine Varients','IS_SHOWN_VALUE_DIFFERENT'];
function workbook(refs:any[][]|null,variant='BOTH',extra:any[][]=[]){
 const book=XLSX.utils.book_new();XLSX.utils.book_append_sheet(book,XLSX.utils.aoa_to_sheet([headers,['Index End AIT',340,653,'DINT',16,variant,'YES'],...extra]),'Metadata');
 if(refs)XLSX.utils.book_append_sheet(book,XLSX.utils.aoa_to_sheet([['TAG_CODE','PLCVAL','SHOWNVAL','MACHINE VARIANT','IS_ALARM'],...refs]),'Sheet2');
 return XLSX.write(book,{type:'array',bookType:'xlsx'});
}
const value=(overrides:Partial<ParsedParamValue>={}):ParsedParamValue=>({tagCode:653,parameter:'Index End AIT',screenName:'SPF',groupCode:340,offset:16,dataType:'DINT',units:'',rawValue:0,formattedValue:'0 (OFF)',rawHex:'00 00 00 00',min:null,max:null,isInRange:true,scaleFactor:1,offsetFactor:1,...overrides});

test('tag 653 YES cannot load without a genuine Sheet2 reference',()=>{
 for(const refs of [null,[],[[652,0,'OFF','BOTH','NO']],[[653,0,'','BOTH','NO']],[[653,'','OFF','BOTH','NO']]]){
  assert.throws(()=>parseExcelWithDropdownReferences(workbook(refs)),(error:any)=>error instanceof MetadataValidationError&&error.message.includes('TAG_CODE 653')&&error.message.includes('GC 340'));
 }
});
test('zero PLC value is a valid reference, and labels and target scopes round-trip exactly',()=>{
 const parsed=parseExcelWithDropdownReferences(workbook([[653,0,'Stopped, "review"','BOTH','NO'],[653,1,'Running','BOTH','NO']]));
 assert.equal(parsed.items[0].isShownValueDifferent,true);assert.equal(parsed.items[0].dropdownOptions?.[0].value,0);
 const exported=exportMetadataTemplateExcel('Custom',parsed.items),reloaded=parseExcelWithDropdownReferences(exported.buffer as ArrayBuffer);
 assert.deepEqual(reloaded.items[0].dropdownOptions,parsed.items[0].dropdownOptions);
 assert.equal(reloaded.items[0].isShownValueDifferent,true);
});
test('a reference for another target or an equal caption on a different tag cannot hide the gap',()=>{
 assert.throws(()=>parseExcelWithDropdownReferences(workbook([[653,0,'OFF','T30','NO']],'C70')),/TAG_CODE 653/);
 const book=XLSX.read(workbook([]),{type:'array'});book.Sheets.Sheet2=XLSX.utils.aoa_to_sheet([['TAG_CODE','PARAMETER','PLCVAL','SHOWNVAL'],[652,'Index End AIT',0,'OFF']]);
 assert.throws(()=>parseExcelWithDropdownReferences(XLSX.write(book,{type:'array',bookType:'xlsx'})),/TAG_CODE 653/);
});
test('CSV preserves the required flag and reports that its references are missing',()=>{
 const csv=headers.join(',')+'\nIndex End AIT,340,653,DINT,16,BOTH,YES\n';const items=parseCSVMetadata(csv);
 assert.equal(items[0].isShownValueDifferent,true);assert.throws(()=>requireSheet2References(items),/TAG_CODE 653/);
});
test('stale metadata cannot turn a missing Sheet2 reference into a successful decode',()=>{
 const item=parseCSVMetadata(headers.join(',')+'\nIndex End AIT,340,653,DINT,0,BOTH,YES\n')[0];
 const result=parseGroupValues(new Uint8Array([0,0,0,0]),[item],true)[0];
 assert.equal(result.rawValue,0);assert.equal(result.isInRange,false);assert.match(result.qualityIssue||'',/Missing Sheet2 reference.*653/);
});
test('CSV has exactly the seven requested headings and preserves raw decimal bytes and findings',()=>{
 const row=decoderValueRow(value({parameter:'Motor, "speed"',formattedValue:'0 (Stopped, "review")',qualityIssue:'Missing Sheet2 reference\nTAG_CODE 653'}));
 const csv=decoderCsv([row]);assert.ok(csv.startsWith('\ufeff'));const book=XLSX.read(csv.replace(/^\uFEFF/,''),{type:'string',raw:true});const rows=XLSX.utils.sheet_to_json(book.Sheets[book.SheetNames[0]],{header:1});
 assert.deepEqual(rows[0],Array.from(DECODER_CSV_HEADERS));assert.equal(rows[1].length,7);assert.equal(rows[1][1],'Motor, "speed"');assert.equal(rows[1][4],'0 0 0 0');assert.equal(rows[1][5],'0 (Stopped, "review")');assert.equal(rows[1][6],'Missing Sheet2 reference\nTAG_CODE 653');
});
test('captured failures export actual received bytes without inventing parameter readings',()=>{
 const row=decoderFrameRow(30,[3,0,1],['Checksum mismatch']);assert.equal(row.decoded,'');assert.equal(row.rawDecimal,'3 0 1');assert.equal(row.finding,'Checksum mismatch');
 assert.equal(decoderFrameRow(30,undefined,['Timeout']).rawDecimal,'Unavailable');
});
test('YBS exports the already decoded actual value and retains frame findings',()=>{
 const v=value({protocol:'ybs',rawValue:30,actualValue:3,formattedValue:'3',rawHex:'00 1e'});
 const response={groupCode:340,parsedValues:[v],rawBytes:[241,0],dataLength:2,expectedLength:4,lengthMatch:false,error:'Frame length mismatch'} as GroupResponseData;
 const row=responseDecoderRows(response)[0];assert.equal(row.decoded,'3');assert.equal(row.rawDecimal,'0 30');assert.match(row.finding,/Frame length mismatch/);
});
test('CSV quotes text and prevents workbook labels becoming formulas; signed readings stay numeric',()=>{
 const csv=decoderCsv([decoderValueRow(value({parameter:'=HYPERLINK("x")',formattedValue:'-2.5'}))]);
 assert.ok(csv.includes("'=HYPERLINK"));assert.ok(csv.includes('"-2.5"'));assert.equal(decimalBytesFromHex('00 ff 10'),'0 255 16');assert.equal(decimalBytesFromHex('invalid'),'');
});
