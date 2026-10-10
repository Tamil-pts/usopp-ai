import {GroupResponseData,ParsedParamValue} from '../types';

const fieldAliases = {
  Date: ['date','day','dateday'], Month: ['month'], Year: ['year'],
  Hour: ['hour','hours'], Minute: ['minute','minutes','min','mins'], Second: ['second','seconds','sec','secs'],
};
type Field = keyof typeof fieldAliases;
export type PLCClock = {dateStr:string;values:Record<Field,number>;fields:Record<Field,ParsedParamValue>};

export function readGroup150Clock(response:GroupResponseData|undefined):PLCClock {
  if(!response?.success || response.groupCode!==150)throw new Error(response?.error || 'Group 150 did not return a valid PLC response.');
  const values = {} as Record<Field,number>;
  const fields = {} as Record<Field,ParsedParamValue>;
  for(const field of Object.keys(fieldAliases) as Field[]){
    const matches=(response.parsedValues||[]).filter(item=>{
      if(item.groupCode!==150)return false;
      const name=item.parameter.toLowerCase().replace(/[^a-z]/g,' ').replace(/\b(rtc|plc|current|machine)\b/g,'').replace(/\s/g,'');
      return fieldAliases[field].includes(name);
    });
    if(matches.length!==1)throw new Error(`Group 150: ${matches.length?'ambiguous':'missing'} ${field} parameter. Check the RTC names, offsets and datatypes in metadata.`);
    const item=matches[0];
    if(typeof item.rawValue!=='number'||!Number.isInteger(item.rawValue))throw new Error(`Group 150 ${field}: invalid decoded value at TAG_CODE ${item.tagCode}, payload offset ${item.offset}. Check its datatype and received bytes.`);
    values[field]=item.rawValue;fields[field]=item;
  }
  const {Date:day,Month:month,Year:year,Hour:hour,Minute:minute,Second:second}=values;
  const leap=year%4===0&&(year%100!==0||year%400===0);
  const days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
  if(year<1||year>9999||month<1||month>12||day<1||day>days[month-1]||hour<0||hour>23||minute<0||minute>59||second<0||second>59)
    throw new Error(`Group 150 returned an invalid clock: Date=${day}, Month=${month}, Year=${year}, Hour=${hour}, Minute=${minute}, Second=${second}. Check PLC clock values and metadata offsets.`);
  const pad=(value:number,width=2)=>String(value).padStart(width,'0');
  return {dateStr:`${pad(day)}/${pad(month)}/${pad(year,4)} ${pad(hour)}:${pad(minute)}:${pad(second)}`,values,fields};
}
