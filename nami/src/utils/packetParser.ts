import { MetadataItem, ParsedParamValue } from '../types';
import {formatDecodedValue} from './valueDisplay';
import {dataQualityIssue} from './dataQuality';
import {parseYbsFrame,buildYbsReadRequest} from './ybsProtocol';

export function buildReadGroupRequest(machineId: number, groupCode: number,protocol:'spinconnect'|'ybs'='spinconnect'): Uint8Array {
  if(protocol==='ybs')return buildYbsReadRequest(machineId,groupCode);
  const buf = new Uint8Array(9);
  buf[0] = 0x03; // STX
  buf[1] = machineId & 0xff; // Machine ID
  buf[2] = 0x01; // Function Code 1: Read Group
  buf[3] = 0x00; // Payload length MSB
  buf[4] = 0x02; // Payload length LSB (2 bytes payload)
  buf[5] = (groupCode >> 8) & 0xff; // Group Code MSB
  buf[6] = groupCode & 0xff; // Group Code LSB

  // Checksum: XOR of bytes 0 through 6
  let checksum = 0;
  for (let i = 0; i <= 6; i++) {
    checksum ^= buf[i];
  }
  buf[7] = checksum & 0xff;
  buf[8] = 0x02; // ETX

  return buf;
}

/**
 * Calculates XOR checksum across bytes from startIndex up to (exclusive) endIndex
 */
export function calculateXorChecksum(bytes: number[] | Uint8Array, startIndex: number = 0, endIndex?: number): number {
  const end = endIndex !== undefined ? endIndex : bytes.length;
  let chk = 0;
  for (let i = startIndex; i < end; i++) {
    chk ^= (bytes[i] & 0xff);
  }
  return chk & 0xff;
}

/**
 * Spin Connect 30-Byte Request Frame (From Factory Protocol Spec):
 * Array 0: 3 (STX)
 * Array 1: Machine ID (e.g. 0)
 * Array 2: Function code (1 = read group with attached RTC)
 * Array 3: 0 (Length MSB)
 * Array 4: 23 (Length LSB = 23 bytes payload)
 * Array 5: Group Code MSB
 * Array 6: Group Code LSB
 * Array 7: 0 (Reserved)
 * Array 8: 0 (Reserved)
 * Array 9..27: RTC Data (19 bytes of ASCII timestamp "YYYY-MM-DD HH:MM:SS")
 * Array 28: Check sum (XOR of all bytes from STX to before ETX, bytes 0..27)
 * Array 29: 2 (ETX)
 */
export function buildSpinConnect30ByteRequest(
  machineId: number = 0,
  groupCode: number = 10,
  functionCode: number = 1,
  timestampStr?: string
): Uint8Array {
  const buf = new Uint8Array(30);
  buf[0] = 0x03; // STX
  buf[1] = machineId & 0xff;
  buf[2] = functionCode & 0xff;
  buf[3] = 0x00; // Length MSB
  buf[4] = 23;   // Length LSB (23 bytes payload)
  buf[5] = (groupCode >> 8) & 0xff;
  buf[6] = groupCode & 0xff;
  buf[7] = 0x00; // Reserved
  buf[8] = 0x00; // Reserved

  let rtcStr = timestampStr;
  if (rtcStr === undefined) {
    const now = new Date();
    const YYYY = now.getFullYear();
    const MM = String(now.getMonth() + 1).padStart(2, '0');
    const DD = String(now.getDate()).padStart(2, '0');
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    rtcStr = `${YYYY}-${MM}-${DD} ${hh}:${mm}:${ss}`;
  }

  if (!isValidSpinConnectTimestamp(rtcStr)) throw new Error('Use a valid YYYY-MM-DD HH:MM:SS timestamp');
  for (let i = 0; i < 19; i++) {
    buf[9 + i] = rtcStr.charCodeAt(i);
  }

  // Checksum is XOR of all bytes from STX (0) to before ETX (27)
  let chk = 0;
  for (let i = 0; i < 28; i++) {
    chk ^= buf[i];
  }
  buf[28] = chk & 0xff;
  buf[29] = 0x02; // ETX

  return buf;
}

export function isValidSpinConnectTimestamp(value: string): boolean {
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$/.test(value)) return false;
  const [year, month, day, hour, minute, second] = value.match(/\d+/g)!.map(Number);
  const check = new Date(0);
  check.setFullYear(year, month - 1, day);
  check.setHours(hour, minute, second, 0);
  return year >= 1 && check.getFullYear() === year && check.getMonth() === month - 1 && check.getDate() === day
    && check.getHours() === hour && check.getMinutes() === minute && check.getSeconds() === second;
}

export type RTCFormatType =
  | 'YYYYMMDDHHMMSS'
  | 'DDMMYYYYHHMMSS'
  | 'YYMMDDHHMMSS'
  | 'DDMMYYHHMMSS'
  | 'ISO'
  | 'EUROPEAN';

export function formatRTCDateTime(date: Date, formatType: RTCFormatType): string {
  const pad = (n: number, width: number = 2) => n.toString().padStart(width, '0');
  const year = date.getFullYear();
  const yy = year % 100;
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const seconds = date.getSeconds();

  switch (formatType) {
    case 'YYYYMMDDHHMMSS':
      return `${pad(year, 4)}${pad(month)}${pad(day)}${pad(hours)}${pad(minutes)}${pad(seconds)}`;
    case 'DDMMYYYYHHMMSS':
      return `${pad(day)}${pad(month)}${pad(year, 4)}${pad(hours)}${pad(minutes)}${pad(seconds)}`;
    case 'YYMMDDHHMMSS':
      return `${pad(yy)}${pad(month)}${pad(day)}${pad(hours)}${pad(minutes)}${pad(seconds)}`;
    case 'DDMMYYHHMMSS':
      return `${pad(day)}${pad(month)}${pad(yy)}${pad(hours)}${pad(minutes)}${pad(seconds)}`;
    case 'ISO':
      return `${pad(year, 4)}-${pad(month)}-${pad(day)} ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    case 'EUROPEAN':
      return `${pad(day)}/${pad(month)}/${pad(year, 4)} ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    default:
      return `${pad(year, 4)}${pad(month)}${pad(day)}${pad(hours)}${pad(minutes)}${pad(seconds)}`;
  }
}

export function buildRTCPacket(machineId: number, functionCode: number = 2, asciiString: string): Uint8Array {
  if (!asciiString || !/^[\x00-\x7f]+$/.test(asciiString) || asciiString.length > 65535) throw new Error('Use nonempty ASCII text');
  const encoder = new TextEncoder();
  const asciiBytes = encoder.encode(asciiString);
  const payloadLen = asciiBytes.length;
  const totalLen = payloadLen + 7;
  const buf = new Uint8Array(totalLen);

  buf[0] = 0x03; // STX
  buf[1] = machineId & 0xff; // Machine ID
  buf[2] = functionCode & 0xff; // Function Code (e.g. 2 for RTC Write)
  buf[3] = (payloadLen >> 8) & 0xff; // Payload length MSB
  buf[4] = payloadLen & 0xff; // Payload length LSB
  buf.set(asciiBytes, 5);

  let checksum = 0;
  for (let i = 0; i < 5 + payloadLen; i++) {
    checksum ^= buf[i];
  }
  buf[5 + payloadLen] = checksum & 0xff;
  buf[5 + payloadLen + 1] = 0x02; // ETX

  return buf;
}

export function parsePLCResponse(
  rawBytes: Uint8Array | number[],
  expectedMachineId?: number,
  expectedGroupCode?:number
): {
  success: boolean;
  resultCode: number;
  dataLength: number;
  dataBytes: Uint8Array;
  error?: string;
  checksumValid: boolean;
  frameLength?:number;protocol?:'ybs'|'spinconnect';groupCode?:number;
} {
  const bytes = rawBytes instanceof Uint8Array ? rawBytes : new Uint8Array(rawBytes);
  if(bytes[0]===241)return parseYbsFrame(bytes,expectedMachineId,expectedGroupCode);

  if (bytes.length < 7) {
    return {
      success: false,
      resultCode: -1,
      dataLength: 0,
      dataBytes: new Uint8Array(0),
      error: `Frame too short (${bytes.length} bytes, minimum 7 required)`,
      checksumValid: false,
    };
  }

  if (bytes[0] !== 0x03 && bytes[0] !== 0x02) {
    return {
      success: false,
      resultCode: -1,
      dataLength: 0,
      dataBytes: new Uint8Array(0),
      error: `Invalid STX byte: 0x${bytes[0].toString(16).padStart(2, '0')} (expected 0x03 or 0x02)`,
      checksumValid: false,
    };
  }

  const machineId = bytes[1];
  if (expectedMachineId !== undefined && machineId !== expectedMachineId) {
    return {success: false, resultCode: bytes[2], dataLength: 0, dataBytes: new Uint8Array(0), checksumValid: false,
      error: `Machine ID mismatch: received ${machineId}, expected ${expectedMachineId}`};
  }

  const resultCode = bytes[2];
  const dataLen = (bytes[3] << 8) | bytes[4];
  const expectedTotalLen = dataLen + 7;

  if (bytes.length < expectedTotalLen) {
    return {
      success: false,
      resultCode,
      dataLength: dataLen,
      dataBytes: new Uint8Array(0),
      error: `Incomplete response frame: got ${bytes.length} bytes, expected ${expectedTotalLen}`,
      checksumValid: false,
    };
  }

  const etxByte = bytes[expectedTotalLen - 1];
  if (etxByte !== 0x02 && etxByte !== 0x03) {
    return {
      success: false,
      resultCode,
      dataLength: dataLen,
      dataBytes: new Uint8Array(0),
      error: `Invalid ETX byte: 0x${etxByte.toString(16).padStart(2, '0')} (expected 0x02 or 0x03)`,
      checksumValid: false,
    };
  }

  // Verify checksum: XOR of bytes 0 to (5 + dataLen - 1)
  let calculatedXor = 0;
  for (let i = 0; i < 5 + dataLen; i++) {
    calculatedXor ^= bytes[i];
  }
  const receivedChecksum = bytes[5 + dataLen];
  const checksumValid = calculatedXor === receivedChecksum;

  if (!checksumValid) {
    return {
      success: false,
      resultCode,
      dataLength: dataLen,
      dataBytes: bytes.slice(5, 5 + dataLen),
      error: `Checksum mismatch: calculated 0x${calculatedXor.toString(16).padStart(2, '0')}, received 0x${receivedChecksum.toString(16).padStart(2, '0')}`,
      checksumValid: false,
    };
  }

  const errorMessages: Record<number, string> = {
    0: 'Success',
    10: 'ETX not received by PLC',
    11: 'Checksum error on PLC',
    12: 'Invalid function code on PLC',
    13: 'Complete frame not received on PLC',
    14: 'Invalid group code on PLC',
  };

  const dataBytes = bytes.slice(5, 5 + dataLen);

  return {
    success: resultCode === 0,
    resultCode,
    dataLength: dataLen,
    dataBytes,
    error: resultCode !== 0 ? (errorMessages[resultCode] || `PLC error code ${resultCode}`) : undefined,
    checksumValid: true,
  };
}

export function parseGroupValues(
  dataBytes: Uint8Array,
  metaItems: MetadataItem[],
  isLittleEndian: boolean = true
): ParsedParamValue[] {
  const dataView = new DataView(dataBytes.buffer, dataBytes.byteOffset, dataBytes.byteLength);
  const results: ParsedParamValue[] = [];

  for (const item of metaItems) {
    const littleEndian=item.protocol==='ybs'?false:isLittleEndian;
    const offset = item.offset;
    let rawValue: any = null;
    let hexValue = '';
    let formattedValue = '';
    let isInRange = true;
    let dropdownText: string | undefined;

    try {
      const type = item.dataType.toUpperCase().trim();
      const arrayMatch = type.match(/^(REAL|LREAL|DINT|UINT|INT|UDINT|USINT|SINT|BOOL|BYTE|STRING)\[(\d+)\]$/);
      const baseType = arrayMatch ? arrayMatch[1] : type;
      const arrayCount = arrayMatch ? Number(arrayMatch[2]) : 1;

      // Decode numeric/boolean arrays from the metadata-defined offset instead of
      // falling through to the scalar default decoder.
      if (arrayMatch && arrayCount > 1 && baseType !== 'STRING') {
        const sizes: Record<string, number> = { REAL: 4, LREAL: 8, DINT: 4, UINT: 2, INT: 2, UDINT: 4, USINT: 1, SINT: 1, BOOL: 1, BYTE: 1 };
        const elementSize = sizes[baseType] || 1;
        const values: any[] = [];
        const hexParts: string[] = [];

        for (let i = 0; i < arrayCount; i++) {
          const elementOffset = offset + i * elementSize;
          if (elementOffset + elementSize > dataBytes.length) {
            values.push(null);
            continue;
          }
          let value: any;
          switch (baseType) {
            case 'REAL': value = dataView.getFloat32(elementOffset, littleEndian); break;
            case 'LREAL': value = dataView.getFloat64(elementOffset, littleEndian); break;
            case 'DINT': value = dataView.getInt32(elementOffset, littleEndian); break;
            case 'UINT': value = dataView.getUint16(elementOffset, littleEndian); break;
            case 'INT': value = dataView.getInt16(elementOffset, littleEndian); break;
            case 'UDINT': value = dataView.getUint32(elementOffset, littleEndian); break;
            case 'USINT': value = dataView.getUint8(elementOffset); break;
            case 'SINT': value = dataView.getInt8(elementOffset); break;
            case 'BOOL': value = dataView.getUint8(elementOffset) !== 0; break;
            case 'BYTE': value = dataView.getUint8(elementOffset); break;
          }
          values.push(value);
          hexParts.push(...Array.from(dataBytes.slice(elementOffset, elementOffset + elementSize)).map(x => x.toString(16).padStart(2, '0')));
        }

        rawValue = values;
        formattedValue = formatDecodedValue(values);
        hexValue = hexParts.join(' ');
      } else {
      // Group 30 fault history uses one BYTE as an 8-bit alarm bitmap.
      // Sheet 2 PLCVAL is the bit number (0..7), SHOWNVAL is the alarm text,
      // and IS_ALARM=YES marks entries that must be decoded as active bits.
      const group30AlarmOptions = item.groupCode === 30
        ? (item.dropdownOptions || []).filter((opt) => opt.isAlarm === true && Number.isInteger(Number(opt.value)) && Number(opt.value) >= 0 && Number(opt.value) <= 7)
        : [];
      if (group30AlarmOptions.length > 0) {
        if (offset + 1 <= dataBytes.length) {
          const rawByte = dataView.getUint8(offset);
          rawValue = rawByte;
          hexValue = rawByte.toString(16).padStart(2, '0');
          const active = group30AlarmOptions
            .filter((opt) => ((rawByte >> Number(opt.value)) & 1) === 1)
            .map((opt) => `Bit ${Number(opt.value)}: ${opt.label}`);
          formattedValue = active.length ? active.join(' | ') : 'No active alarm';
          dropdownText = active.length ? active.join(' | ') : undefined;
        } else {
          formattedValue = '[Buffer Overflow]';
        }
      } else switch (baseType) {
        case 'REAL': {
          if (offset + 4 <= dataBytes.length) {
            rawValue = dataView.getFloat32(offset, littleEndian);
            formattedValue = formatDecodedValue(rawValue);
            const b = dataBytes.slice(offset, offset + 4);
            hexValue = Array.from(b).map(x => x.toString(16).padStart(2, '0')).join(' ');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        case 'LREAL': {
          if (offset + 8 <= dataBytes.length) {
            rawValue = dataView.getFloat64(offset, littleEndian);
            formattedValue = formatDecodedValue(rawValue);
            const b = dataBytes.slice(offset, offset + 8);
            hexValue = Array.from(b).map(x => x.toString(16).padStart(2, '0')).join(' ');
          } else formattedValue = '[Buffer Overflow]';
          break;
        }
        case 'DINT': {
          if (offset + 4 <= dataBytes.length) {
            rawValue = dataView.getInt32(offset, littleEndian);
            formattedValue = `${rawValue}`;
            const b = dataBytes.slice(offset, offset + 4);
            hexValue = Array.from(b).map(x => x.toString(16).padStart(2, '0')).join(' ');
          } else formattedValue = '[Buffer Overflow]';
          break;
        }
        case 'UINT': {
          if (offset + 2 <= dataBytes.length) {
            rawValue = dataView.getUint16(offset, littleEndian);
            formattedValue = `${rawValue}`;
            const b = dataBytes.slice(offset, offset + 2);
            hexValue = Array.from(b).map(x => x.toString(16).padStart(2, '0')).join(' ');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        case 'INT': {
          if (offset + 2 <= dataBytes.length) {
            rawValue = dataView.getInt16(offset, littleEndian);
            formattedValue = `${rawValue}`;
            const b = dataBytes.slice(offset, offset + 2);
            hexValue = Array.from(b).map(x => x.toString(16).padStart(2, '0')).join(' ');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        case 'UDINT': {
          if (offset + 4 <= dataBytes.length) {
            rawValue = dataView.getUint32(offset, littleEndian);
            formattedValue = `${rawValue}`;
            const b = dataBytes.slice(offset, offset + 4);
            hexValue = Array.from(b).map(x => x.toString(16).padStart(2, '0')).join(' ');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        case 'USINT': {
          if (offset + 1 <= dataBytes.length) {
            rawValue = dataView.getUint8(offset);
            formattedValue = `${rawValue}`;
            hexValue = rawValue.toString(16).padStart(2, '0');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        case 'SINT': {
          if (offset + 1 <= dataBytes.length) {
            rawValue = dataView.getInt8(offset);
            formattedValue = `${rawValue}`;
            hexValue = (rawValue & 0xff).toString(16).padStart(2, '0');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        case 'BOOL': {
          if (offset + 1 <= dataBytes.length) {
            const rawByte = dataView.getUint8(offset);
            rawValue = rawByte !== 0;
            formattedValue = formatDecodedValue(rawValue);
            hexValue = rawByte.toString(16).padStart(2, '0');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        case 'BYTE': {
          if (offset + 1 <= dataBytes.length) {
            rawValue = dataView.getUint8(offset);
            formattedValue = `0x${rawValue.toString(16).padStart(2, '0')} (${rawValue})`;
            hexValue = rawValue.toString(16).padStart(2, '0');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        case 'STRING': {
          // STRING decoding is strictly metadata-driven. Do not guess alternate offsets.
          const strLength = item.arraySize && item.arraySize > 0 ? item.arraySize : 50;
          if (offset >= 0 && offset < dataBytes.length) {
            const end = Math.min(offset + strLength, dataBytes.length);
            const slice = dataBytes.slice(offset, end);
            let nullTerm = slice.indexOf(0);
            if (nullTerm === -1) nullTerm = slice.length;
            const textDecoder = new TextDecoder('utf-8');
            const candidate = textDecoder.decode(slice.subarray(0, nullTerm)).trim();
            rawValue = candidate;
            formattedValue = candidate || '(empty string)';
            hexValue = Array.from(slice.subarray(0, Math.min(nullTerm, 8)))
              .map(x => x.toString(16).padStart(2, '0')).join(' ') + (candidate ? ` ("${candidate}")` : '');
          } else {
            formattedValue = '[Buffer Overflow]';
          }
          break;
        }
        default: {
          if (offset < dataBytes.length) {
            rawValue = dataBytes[offset];
            formattedValue = `${rawValue}`;
            hexValue = rawValue.toString(16).padStart(2, '0');
          }
        }
      }
      }

      // Make metadata/payload boundary errors explicit. A value that is
      // outside the received PLC payload must never look like a pending read.
      if (rawValue === null && formattedValue === '[Buffer Overflow]') {
        formattedValue = `[Buffer Overflow: offset ${offset}, payload ${dataBytes.length} bytes]`;
        isInRange = false;
      }

      let actualValue:number|null|undefined;
      if(item.protocol==='ybs'){
        const divide=item.divideFactor??1,multiply=item.multiplyFactor??1;
        actualValue=typeof rawValue==='number'&&Number.isFinite(rawValue)&&Number.isFinite(divide)&&divide>0&&Number.isFinite(multiply)?rawValue/divide*multiply:null;
        if(actualValue!==null&&!Number.isFinite(actualValue))actualValue=null;
        formattedValue=actualValue===null?'Unavailable':formatDecodedValue(actualValue);
        if(actualValue!==null&&item.bitDefinitions?.length&&Number.isInteger(rawValue)){
          const active=item.bitDefinitions.filter(bit=>Boolean(rawValue&(2**bit.bit))).map(bit=>`Bit ${bit.bit}: ${bit.label}`);
          dropdownText=active.join(' | ')||undefined;
          if(dropdownText)formattedValue+=` (${dropdownText})`;
        }
      }
      const outsideLimits = typeof actualValue==='number' && ((item.min!==null && actualValue<item.min) || (item.max!==null && actualValue>item.max));
      let qualityIssue = item.protocol==='ybs' ? (actualValue===null ? `Missing or invalid YBS value at payload offset ${offset} (${dataBytes.length} bytes received).` : outsideLimits ? 'Actual value is outside the metadata limits.' : undefined) : dataQualityIssue(rawValue, item.parameter);
      isInRange = !qualityIssue;

      // Check for Dropdown Reference mapping (Sheet 2)
      const isGroup30BitAlarm = item.groupCode === 30 && (item.dropdownOptions || []).some((opt) => opt.isAlarm === true);
      if(item.protocol!=='ybs'&&item.isShownValueDifferent&&!(item.dropdownOptions||[]).some(option=>
        String(option.value??'').trim()!==''&&!/^(?:<null>|null|none)?$/i.test(String(option.label??'').trim()))) {
        qualityIssue=[qualityIssue,`Missing Sheet2 reference for TAG_CODE ${item.tagCode}. Displayed labels are unavailable; review the workbook.`].filter(Boolean).join(' ');
        isInRange=false;
        if(typeof rawValue==='boolean')formattedValue=String(rawValue);
      }
      if (item.protocol!=='ybs' && !isGroup30BitAlarm && item.dropdownOptions && item.dropdownOptions.length > 0 && rawValue !== null && rawValue !== undefined) {
        const matchedOption = item.dropdownOptions.find(
          (opt) => Number(opt.value) === Number(rawValue) || String(opt.value) === String(rawValue)
        );
        if (matchedOption) {
          dropdownText = matchedOption.label;
          formattedValue = `${formatDecodedValue(rawValue)} (${matchedOption.label})`;
        }
      }

      results.push({
        tagCode: item.tagCode,
        parameter: item.parameter,
        screenName: item.screenName,
        groupCode: item.groupCode,
        offset: item.offset,
        dataType: item.dataType,
        units: item.units,
        rawValue,
        ...(item.protocol==='ybs'?{actualValue,protocol:'ybs' as const,wireDataType:item.wireDataType,divideFactor:item.divideFactor,multiplyFactor:item.multiplyFactor,sourceRow:item.sourceRow,sourceSheet:item.sourceSheet,layoutInferred:item.layoutInferred}:{}),
        formattedValue,
        rawHex: hexValue,
        min: item.min,
        max: item.max,
        isInRange,
        qualityIssue,
        scaleFactor: item.scaleFactor,
        offsetFactor: item.offsetFactor,
        bitNo: item.bitNo,
        dropdownText,
      });
    } catch (e: any) {
      formattedValue = `Error: ${e.message}`;
      results.push({
        tagCode: item.tagCode,
        parameter: item.parameter,
        screenName: item.screenName,
        groupCode: item.groupCode,
        offset: item.offset,
        dataType: item.dataType,
        units: item.units,
        rawValue: null,
        formattedValue,
        rawHex: hexValue,
        min: item.min,
        max: item.max,
        isInRange: false,
        scaleFactor: item.scaleFactor,
        offsetFactor: item.offsetFactor,
        bitNo: item.bitNo,
      });
    }
  }

  return results;
}

export function formatHexDump(bytes: Uint8Array | number[]): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let hexDump = '';
  for (let i = 0; i < arr.length; i += 16) {
    const chunk = arr.slice(i, i + 16);
    const offsetStr = i.toString(16).padStart(4, '0');
    const hexParts = Array.from(chunk).map(b => b.toString(16).padStart(2, '0')).join(' ');
    const paddedHex = hexParts.padEnd(48, ' ');
    const ascii = Array.from(chunk).map(b => (b >= 32 && b <= 126 ? String.fromCharCode(b) : '.')).join('');
    hexDump += `${offsetStr}:  ${paddedHex}  |${ascii}|\n`;
  }
  return hexDump;
}

/**
 * Formats a byte array in B&R Automation Studio Watch List style:
 * nw_snd_buffer[0] = 3 (0x03)
 * nw_snd_buffer[197] = 82 ('R', 0x52)
 */
export function formatAsBRWatchList(
  bytes: number[] | Uint8Array,
  arrayName: string = 'nw_snd_buffer',
  startIndex: number = 0
): string {
  const arr = Array.from(bytes);
  const lines: string[] = [];
  for (let i = 0; i < arr.length; i++) {
    const val = arr[i] & 0xff;
    const actualIndex = startIndex + i;
    const hex = '0x' + val.toString(16).padStart(2, '0').toUpperCase();
    let charDesc = '';
    if (val >= 32 && val <= 126) {
      charDesc = ` '${String.fromCharCode(val)}'`;
    }
    lines.push(`${arrayName}[${actualIndex}] = ${val}${charDesc} (${hex})`);
  }
  return lines.join('\n');
}

/**
 * Formats bytes as a standard JavaScript / JSON array string: [3, 0, 0, ...]
 */
export function formatAsByteArray(bytes: number[] | Uint8Array): string {
  const arr = Array.from(bytes);
  return `[${arr.join(', ')}]`;
}

/**
 * Formats bytes as a C / ST hex array string: [0x03, 0x00, 0x00, ...]
 */
export function formatAsHexArray(bytes: number[] | Uint8Array): string {
  const arr = Array.from(bytes);
  return `[${arr.map(b => '0x' + (b & 0xff).toString(16).padStart(2, '0').toUpperCase()).join(', ')}]`;
}

export interface RawArrayParseResult {
  success: boolean;
  bytes: number[];
  detectedFormat: string;
  error?: string;
  isFullFrame: boolean;
  dataLength?: number;
}

/**
 * Universal raw array parser:
 * Accepts pasted data from:
 * 1. B&R Automation Studio watch list (e.g. "nw_snd_buffer[197] 82" or "nw_snd_buffer[197] = 82")
 * 2. Comma-separated decimal array (e.g. "[3, 0, 0, ...]" or "3, 0, 0, 0, 245, ...")
 * 3. Space-separated or comma-separated hex (e.g. "03 00 00 00 F5 52 55 55 55 00" or "0x03, 0x00, ...")
 * 4. Index-based listings (e.g. "197: 82", "[197] 82")
 */
export function parseRawArrayInput(input: string): RawArrayParseResult {
  if (!input || !input.trim()) {
    return {
      success: false,
      bytes: [],
      detectedFormat: 'Empty',
      error: 'No input provided. Please paste an array of bytes.',
      isFullFrame: false,
    };
  }

  const trimmed = input.trim();

  // Pattern 1: Check for B&R Automation Studio watch list or indexed format
  // Matches lines like: nw_snd_buffer[197] 82  OR  nw_snd_buffer[197] = 82  OR  [197] 82  OR  197: 82
  const indexedPattern = /(?:nw_snd_buffer|buffer|arr|data)?\s*\[\s*(\d+)\s*\]\s*(?:=|:|\t|\s)\s*([0-9a-fA-FxX]+)/g;
  const indexMatches = Array.from(trimmed.matchAll(indexedPattern));

  if (indexMatches.length >= 3) {
    // Collect by index
    const indexMap = new Map<number, number>();
    let maxIdx = 0;
    for (const m of indexMatches) {
      const idx = parseInt(m[1], 10);
      let valStr = m[2].trim();
      let val = 0;
      if (valStr.startsWith('0x') || valStr.startsWith('0X')) {
        val = parseInt(valStr, 16);
      } else {
        val = parseInt(valStr, 10);
      }
      if (!isNaN(idx) && !isNaN(val)) {
        indexMap.set(idx, val & 0xff);
        if (idx > maxIdx) maxIdx = idx;
      }
    }

    // Build contiguous array from 0 to maxIdx
    const bytes: number[] = new Array(maxIdx + 1).fill(0);
    for (const [idx, val] of indexMap.entries()) {
      if (idx < bytes.length) {
        bytes[idx] = val;
      }
    }

    const isFull = bytes.length >= 7 && (bytes[0] === 0x03 || bytes[0] === 0x02);
    return {
      success: true,
      bytes,
      detectedFormat: `B&R Automation Studio Watch List (${indexMatches.length} indexed entries)`,
      isFullFrame: isFull,
      dataLength: isFull ? (bytes[3] << 8) | bytes[4] : bytes.length,
    };
  }

  // Pattern 2: Hex array with 0x prefix (e.g. 0x03, 0x00, 0x00...)
  if (trimmed.includes('0x') || trimmed.includes('0X')) {
    const hexMatches = trimmed.match(/0[xX][0-9a-fA-F]{1,2}/g);
    if (hexMatches && hexMatches.length > 0) {
      const bytes = hexMatches.map(h => parseInt(h, 16) & 0xff);
      const isFull = bytes.length >= 7 && (bytes[0] === 0x03 || bytes[0] === 0x02);
      return {
        success: true,
        bytes,
        detectedFormat: `Hex Array 0x.. (${bytes.length} bytes)`,
        isFullFrame: isFull,
        dataLength: isFull ? (bytes[3] << 8) | bytes[4] : bytes.length,
      };
    }
  }

  // Pattern 3: Clean string of brackets and check if it's pure Hex bytes (e.g. "03 00 00 00 F5 52 55 55 55 00")
  // Or comma/space separated decimals (e.g. "3, 0, 0, 0, 245, 82, 85, 85, 85, 0")
  const cleaned = trimmed.replace(/^[\[\(\{]/, '').replace(/[\]\)\}]$/, '').trim();
  const tokens = cleaned.split(/[\s,;]+/).filter(Boolean);

  if (tokens.length === 0) {
    return {
      success: false,
      bytes: [],
      detectedFormat: 'Unknown',
      error: 'Could not parse any bytes from input.',
      isFullFrame: false,
    };
  }

  // Check if tokens look like 2-digit hex without prefix (e.g. "03", "00", "F5", "52")
  const isAllHexPairs = tokens.every(t => /^[0-9a-fA-F]{1,2}$/.test(t));
  const hasHexLetters = tokens.some(t => /[a-fA-F]/.test(t));

  if (isAllHexPairs && (hasHexLetters || tokens.length >= 4)) {
    // If they all parse as valid hex
    const bytes = tokens.map(t => parseInt(t, 16) & 0xff);
    const isFull = bytes.length >= 7 && (bytes[0] === 0x03 || bytes[0] === 0x02);
    return {
      success: true,
      bytes,
      detectedFormat: `Hex String (${bytes.length} bytes)`,
      isFullFrame: isFull,
      dataLength: isFull ? (bytes[3] << 8) | bytes[4] : bytes.length,
    };
  }

  // Default: Parse as decimal numbers
  const bytes: number[] = [];
  let parseErrors = 0;
  for (const t of tokens) {
    const num = Number(t);
    if (!isNaN(num) && num >= 0 && num <= 255) {
      bytes.push(Math.round(num));
    } else {
      parseErrors++;
    }
  }

  if (bytes.length === 0) {
    return {
      success: false,
      bytes: [],
      detectedFormat: 'Invalid',
      error: `Failed to parse valid byte values (0-255). Encountered ${parseErrors} invalid tokens.`,
      isFullFrame: false,
    };
  }

  const isFull = bytes.length >= 7 && (bytes[0] === 0x03 || bytes[0] === 0x02);
  return {
    success: true,
    bytes,
    detectedFormat: `Decimal Byte Array (${bytes.length} bytes)`,
    isFullFrame: isFull,
    dataLength: isFull ? (bytes[3] << 8) | bytes[4] : bytes.length,
  };
}
