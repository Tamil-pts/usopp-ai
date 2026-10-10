import { MetadataItem, SpinningMachineType, DropdownReferenceItem } from '../types';

export const SPINNING_MACHINE_TYPES: SpinningMachineType[] = [
  'Carding',
  'Ring Frame',
  'Speed Frame',
  'Finisher',
  'Breaker',
  'Lapformer',
  'Comber',
  'Blow Room',
  'Auto Winder',
  'RAP',
];

export const MACHINE_TYPE_DESCRIPTIONS: Record<SpinningMachineType, string> = {
  'Carding': 'High-production carding machine (e.g. xcarding) with autoleveller, chute feed & flats.',
  'Ring Frame': 'Ring spinning frame with spindle inverter, ring rail servo & pneumafil suction.',
  'Speed Frame': 'Simplex / roving frame with flyer drive, bobbin carriage & roving tension control.',
  'Finisher': 'Finisher drawframe with online autolevelling, sliver quality monitor & can changer.',
  'Breaker': 'Breaker drawframe with multi-sliver creel feed, draft zone & high-speed delivery.',
  'Lapformer': 'Combing preparation lap machine producing high-density uniform sliver laps.',
  'Comber': 'High-speed combing machine with nipper, circular comb & adjustable noil extraction.',
  'Blow Room': 'Opening & cleaning line with bale plucker, coarse cleaner, condenser & chute feed.',
  'Auto Winder': 'Automatic cone/package winder with electronic yarn clearers & autosequence splicer.',
  'RAP': 'Ring Auto Piecer / Doffer automated mobile robot traversing ring frame rails.',
  'Custom': 'Custom machine profile with user-defined tags and group codes.',
};

/**
 * Standard Sheet 2 Dropdown Reference Mappings for Spinning Machines
 * (Maps raw integer codes to user-friendly human readable text)
 */
export const STANDARD_DROPDOWN_REFERENCES: DropdownReferenceItem[] = [
  // Machine Status (Tag 11, Tag 14, Tag 10)
  { tagCode: 11, parameter: 'Machine Status', value: 0, displayText: 'Stopped' },
  { tagCode: 11, parameter: 'Machine Status', value: 1, displayText: 'Running (Normal)' },
  { tagCode: 11, parameter: 'Machine Status', value: 2, displayText: 'Slow Speed / Crawl' },
  { tagCode: 11, parameter: 'Machine Status', value: 3, displayText: 'Can Change in Progress' },
  { tagCode: 11, parameter: 'Machine Status', value: 4, displayText: 'Doffing' },
  { tagCode: 11, parameter: 'Machine Status', value: 5, displayText: 'Fault / Alarm Stop' },
  { tagCode: 11, parameter: 'Machine Status', value: 6, displayText: 'Emergency Stop' },
  { tagCode: 11, parameter: 'Machine Status', value: 7, displayText: 'Maintenance Mode' },

  { tagCode: 14, parameter: 'Machine Status', value: 0, displayText: 'Stopped' },
  { tagCode: 14, parameter: 'Machine Status', value: 1, displayText: 'Running (Normal)' },
  { tagCode: 14, parameter: 'Machine Status', value: 2, displayText: 'Slow Speed / Crawl' },
  { tagCode: 14, parameter: 'Machine Status', value: 3, displayText: 'Can Change in Progress' },
  { tagCode: 14, parameter: 'Machine Status', value: 4, displayText: 'Doffing' },
  { tagCode: 14, parameter: 'Machine Status', value: 5, displayText: 'Fault / Alarm Stop' },
  { tagCode: 14, parameter: 'Machine Status', value: 6, displayText: 'Emergency Stop' },
  { tagCode: 14, parameter: 'Machine Status', value: 7, displayText: 'Maintenance Mode' },

  // RAP Machine Status (Tag 10)
  { tagCode: 10, parameter: 'Machine Status', value: 0, displayText: 'Docked / Standby' },
  { tagCode: 10, parameter: 'Machine Status', value: 1, displayText: 'Patrolling Rails' },
  { tagCode: 10, parameter: 'Machine Status', value: 2, displayText: 'Piecing Spindle' },
  { tagCode: 10, parameter: 'Machine Status', value: 3, displayText: 'Charging Battery' },
  { tagCode: 10, parameter: 'Machine Status', value: 4, displayText: 'Obstacle Warning' },
  { tagCode: 10, parameter: 'Machine Status', value: 5, displayText: 'Fault Stop' },

  // Autoleveller Status (Tag 8)
  { tagCode: 8, parameter: 'A\\L Value', value: 0, displayText: 'Autoleveller OFF' },
  { tagCode: 8, parameter: 'A\\L Value', value: 1, displayText: 'Autoleveller ON (Active)' },
  { tagCode: 8, parameter: 'A\\L Value', value: 2, displayText: 'Correction Limit Warning' },

  // Active Mode (Tag 9)
  { tagCode: 9, parameter: 'ACT Value', value: 0, displayText: 'Manual Mode' },
  { tagCode: 9, parameter: 'ACT Value', value: 1, displayText: 'Auto Control Active' },

  // Card Draft (Tag 24)
  { tagCode: 24, parameter: 'Card Draft', value: 0, displayText: 'Standard Draft (Normal)' },
  { tagCode: 24, parameter: 'Card Draft', value: 1, displayText: 'High Draft Mode' },
  { tagCode: 24, parameter: 'Card Draft', value: 2, displayText: 'Low Draft / Trial' },
];

/**
 * Attaches dropdown options to matching MetadataItem entries
 */
export function attachDropdownsToMetadata(
  items: MetadataItem[],
  dropdowns: DropdownReferenceItem[] = STANDARD_DROPDOWN_REFERENCES
): MetadataItem[] {
  return items.map((item) => {
    const matched = dropdowns.filter(
      (d) =>
        d.tagCode === item.tagCode ||
        (d.parameter && item.parameter && d.parameter.toLowerCase().trim() === item.parameter.toLowerCase().trim())
    );

    if (matched.length > 0) {
      return {
        ...item,
        dropdownOptions: matched.map((m) => ({
          value: m.value,
          label: m.displayText,
          machineVariant: m.machineVariant,
          isAlarm: m.isAlarm,
        })),
      };
    }
    return item;
  });
}

/**
 * Helper to build MetadataItem quickly
 */
function createItem(
  sNo: number,
  screenName: string,
  param: string,
  units: string,
  groupCode: number,
  offset: number,
  dataType: 'REAL' | 'UINT' | 'INT' | 'UDINT' | 'USINT' | 'BOOL',
  min: number | null = null,
  max: number | null = null,
  isWritable: boolean = false
): MetadataItem {
  return {
    sNo,
    screenName,
    machineVariants: 'BOTH',
    parameter: param,
    units,
    min,
    max,
    tagCode: sNo,
    groupCode,
    offset,
    fromVersion: '5.295',
    toVersion: '5.296',
    dataType,
    offsetFactor: 1,
    scaleFactor: 1,
    isVisible: true,
    isWritable,
  };
}

/**
 * Pre-defined presets for all 10 textile spinning machines
 */
export function getPredefinedMachineMetadata(type: SpinningMachineType): MetadataItem[] {
  const getRawItems = (): MetadataItem[] => {
    switch (type) {
    case 'Ring Frame':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Delivery Speed', 'm/min', 20, 0, 'REAL', 0, 50),
        createItem(3, 'Main Operational', 'Yarn Count', 'Ne', 20, 4, 'REAL', 6, 120),
        createItem(4, 'Main Operational', 'Spindle Speed Actual', 'rpm', 20, 8, 'UINT', 0, 25000),
        createItem(5, 'Main Operational', 'Spindle Speed Set', 'rpm', 20, 10, 'UINT', 0, 25000, true),
        createItem(6, 'Main Operational', 'Front Roller Speed', 'rpm', 20, 12, 'REAL', 0, 400),
        createItem(7, 'Main Operational', 'Production', 'kg/h', 20, 16, 'REAL', 0, 100),
        createItem(8, 'Main Operational', 'Twist (TPI)', 'tpi', 20, 20, 'REAL', 5, 50),
        createItem(9, 'Main Operational', 'Current Length', 'm', 20, 24, 'UINT', 0, 6000),
        createItem(10, 'Main Operational', 'Full Cop Length', 'm', 20, 26, 'UINT', 0, 6000, true),
        createItem(11, 'Main Operational', 'Machine Status', '', 20, 28, 'UINT', 0, 10),
        createItem(12, 'Main Operational', 'Ring Rail Position', 'mm', 20, 30, 'REAL', 0, 300),
        createItem(13, 'Main Operational', 'Inverter Frequency', 'Hz', 20, 34, 'REAL', 0, 75),
        createItem(14, 'Settings', 'Number of Spindles', 'sp', 30, 0, 'UINT', 100, 2400),
        createItem(15, 'Settings', 'Cop Diameter Set', 'mm', 30, 2, 'REAL', 20, 60, true),
        createItem(16, 'Settings', 'Ring Rail Chase Length', 'mm', 30, 6, 'REAL', 10, 80, true),
        createItem(17, 'Settings', 'Doff Time Cycle', 's', 30, 10, 'UINT', 30, 300),
        createItem(18, 'Shift Report', 'Shift Production', 'kg', 40, 0, 'REAL', 0, 1000),
        createItem(19, 'Shift Report', 'Total Doffs Completed', '', 40, 4, 'UINT', 0, 100),
        createItem(20, 'Shift Report', 'Pneumafil Waste Estimated', 'kg', 40, 6, 'REAL', 0, 50),
        createItem(21, 'Shift Report', 'Shift Run Time', 'min', 40, 10, 'UINT', 0, 480),
        createItem(22, 'Shift Report', 'Shift Stop Time', 'min', 40, 12, 'UINT', 0, 480),
        createItem(23, 'Drive Status & Frequency', 'Main Motor Left Current', 'A', 80, 0, 'REAL', 0, 200),
        createItem(24, 'Drive Status & Frequency', 'Main Motor Right Current', 'A', 80, 4, 'REAL', 0, 200),
        createItem(25, 'Drive Status & Frequency', 'Suction Pressure', 'Pa', 80, 8, 'INT', 0, 2500),
        createItem(26, 'Drive Status & Frequency', 'Ambient Temperature', '°C', 80, 10, 'REAL', 15, 50),
        createItem(27, 'Drive Status & Frequency', 'Relative Humidity', '%', 80, 14, 'REAL', 30, 90),
        createItem(28, 'Drive Status & Frequency', 'Total Spindle Breaks', '', 80, 18, 'UINT', 0, 500),
        createItem(29, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(30, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(31, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(32, 'History & RTC', 'RTC Hour', '', 150, 4, 'USINT', 0, 23),
        createItem(33, 'History & RTC', 'RTC Minute', '', 150, 5, 'USINT', 0, 59),
        createItem(34, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
        createItem(35, 'Energy Monitor', 'Line Voltage Avg', 'V', 410, 10, 'REAL', 350, 460),
        createItem(36, 'Energy Monitor', 'Total Active Power', 'kW', 410, 26, 'REAL', 0, 150),
        createItem(37, 'Energy Monitor', 'Total Energy', 'kWh', 410, 38, 'REAL', 0, 1000000),
      ];

    case 'Speed Frame':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Delivery Speed', 'm/min', 20, 0, 'REAL', 0, 60),
        createItem(3, 'Main Operational', 'Spindle Speed', 'rpm', 20, 4, 'UINT', 0, 2000),
        createItem(4, 'Main Operational', 'Flyer Speed', 'rpm', 20, 6, 'UINT', 0, 2000),
        createItem(5, 'Main Operational', 'Roving Hank', 'Ne', 20, 8, 'REAL', 0.4, 4.0),
        createItem(6, 'Main Operational', 'Production', 'kg/h', 20, 12, 'REAL', 0, 80),
        createItem(7, 'Main Operational', 'Current Length', 'm', 20, 16, 'UINT', 0, 4000),
        createItem(8, 'Main Operational', 'Target Bobbin Length', 'm', 20, 18, 'UINT', 0, 4000, true),
        createItem(9, 'Main Operational', 'Bobbin Diameter', 'mm', 20, 20, 'REAL', 40, 160),
        createItem(10, 'Main Operational', 'Lift Carriage Speed', 'mm/min', 20, 24, 'REAL', 0, 100),
        createItem(11, 'Main Operational', 'Roving Tension %', '%', 20, 28, 'REAL', 0, 100),
        createItem(12, 'Main Operational', 'Machine Status', '', 20, 32, 'UINT', 0, 10),
        createItem(13, 'Settings', 'Draft Ratio', '', 30, 0, 'REAL', 4, 15, true),
        createItem(14, 'Settings', 'Twist Multiplier (TM)', '', 30, 4, 'REAL', 0.8, 2.5, true),
        createItem(15, 'Shift Report', 'Shift Production', 'kg', 40, 0, 'REAL', 0, 800),
        createItem(16, 'Shift Report', 'Total Doffs', '', 40, 4, 'UINT', 0, 50),
        createItem(17, 'Drive Status & Inverters', 'Flyer Motor Load %', '%', 80, 0, 'REAL', 0, 120),
        createItem(18, 'Drive Status & Inverters', 'Lift Inverter Freq', 'Hz', 80, 4, 'REAL', 0, 70),
        createItem(19, 'Drive Status & Inverters', 'Doff Cycle Stage', '', 80, 8, 'UINT', 0, 8),
        createItem(20, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(21, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(22, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(23, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
      ];

    case 'Finisher':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Delivery Speed', 'm/min', 20, 0, 'REAL', 0, 1100),
        createItem(3, 'Main Operational', 'Delivered Sliver Hank', 'Ne', 20, 4, 'REAL', 0.08, 0.25),
        createItem(4, 'Main Operational', 'Production', 'kg/h', 20, 8, 'REAL', 0, 600),
        createItem(5, 'Main Operational', 'Autoleveller A/L %', '%', 20, 12, 'REAL', -15, 15),
        createItem(6, 'Main Operational', 'Sliver 1m CV%', '%', 20, 16, 'REAL', 0, 5),
        createItem(7, 'Main Operational', 'Sliver 5m CV%', '%', 20, 20, 'REAL', 0, 5),
        createItem(8, 'Main Operational', 'Total Draft Ratio', '', 20, 24, 'REAL', 4, 12),
        createItem(9, 'Main Operational', 'Break Draft', '', 20, 28, 'REAL', 1.0, 1.8),
        createItem(10, 'Main Operational', 'Current Can Length', 'm', 20, 32, 'UINT', 0, 9000),
        createItem(11, 'Main Operational', 'Set Can Length', 'm', 20, 34, 'UINT', 0, 9000, true),
        createItem(12, 'Main Operational', 'Machine Status', '', 20, 36, 'UINT', 0, 10),
        createItem(13, 'Autoleveller Setting', 'Nominal Sliver Weight', 'g/m', 30, 0, 'REAL', 2.0, 8.0, true),
        createItem(14, 'Autoleveller Setting', 'Levelling Intensity', '%', 30, 4, 'REAL', 50, 120, true),
        createItem(15, 'Shift Report', 'Shift Production', 'kg', 40, 0, 'REAL', 0, 4000),
        createItem(16, 'Shift Report', 'Cans Doffed', '', 40, 4, 'UINT', 0, 200),
        createItem(17, 'Autoleveller Diagnostics', 'Scanning Roller mV', 'mV', 80, 0, 'INT', 0, 5000),
        createItem(18, 'Autoleveller Diagnostics', 'Servo Motor Current', 'A', 80, 2, 'REAL', 0, 50),
        createItem(19, 'Autoleveller Diagnostics', 'Suction Pressure', 'Pa', 80, 6, 'INT', 0, 1500),
        createItem(20, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(21, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(22, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(23, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
      ];

    case 'Breaker':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Delivery Speed', 'm/min', 20, 0, 'REAL', 0, 900),
        createItem(3, 'Main Operational', 'Feed Speed', 'm/min', 20, 4, 'REAL', 0, 200),
        createItem(4, 'Main Operational', 'Delivered Sliver Hank', 'Ne', 20, 8, 'REAL', 0.08, 0.25),
        createItem(5, 'Main Operational', 'Production', 'kg/h', 20, 12, 'REAL', 0, 500),
        createItem(6, 'Main Operational', 'Total Draft', '', 20, 16, 'REAL', 4, 10),
        createItem(7, 'Main Operational', 'Current Length', 'm', 20, 20, 'UINT', 0, 8000),
        createItem(8, 'Main Operational', 'Full Can Length', 'm', 20, 22, 'UINT', 0, 8000, true),
        createItem(9, 'Main Operational', 'Creel Stop Count', '', 20, 24, 'UINT', 0, 100),
        createItem(10, 'Main Operational', 'Machine Status', '', 20, 26, 'UINT', 0, 10),
        createItem(11, 'Settings', 'Target Delivery Speed', 'm/min', 30, 0, 'REAL', 200, 900, true),
        createItem(12, 'Shift Report', 'Shift Production', 'kg', 40, 0, 'REAL', 0, 3500),
        createItem(13, 'Shift Report', 'Total Cans', '', 40, 4, 'UINT', 0, 150),
        createItem(14, 'Breaker Diagnostics', 'Main Motor Load %', '%', 80, 0, 'REAL', 0, 100),
        createItem(15, 'Breaker Diagnostics', 'Filter Suction Pa', 'Pa', 80, 4, 'INT', 0, 1500),
        createItem(16, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(17, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(18, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(19, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
      ];

    case 'Lapformer':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Delivery Speed', 'm/min', 20, 0, 'REAL', 0, 200),
        createItem(3, 'Main Operational', 'Lap Weight', 'g/m', 20, 4, 'REAL', 50, 90),
        createItem(4, 'Main Operational', 'Production', 'kg/h', 20, 8, 'REAL', 0, 600),
        createItem(5, 'Main Operational', 'Current Lap Length', 'm', 20, 12, 'UINT', 0, 500),
        createItem(6, 'Main Operational', 'Full Lap Length', 'm', 20, 14, 'UINT', 0, 500, true),
        createItem(7, 'Main Operational', 'Lap Diameter', 'mm', 20, 16, 'REAL', 100, 650),
        createItem(8, 'Main Operational', 'Calender Pressure', 'bar', 20, 20, 'REAL', 0, 10),
        createItem(9, 'Main Operational', 'Machine Status', '', 20, 24, 'UINT', 0, 10),
        createItem(10, 'Settings', 'Lap Weight Setpoint', 'g/m', 30, 0, 'REAL', 50, 90, true),
        createItem(11, 'Settings', 'Calender Pressure Set', 'bar', 30, 4, 'REAL', 1, 8, true),
        createItem(12, 'Shift Report', 'Laps Produced', '', 40, 0, 'UINT', 0, 300),
        createItem(13, 'Shift Report', 'Shift Production', 'kg', 40, 2, 'REAL', 0, 4000),
        createItem(14, 'Lapformer Diagnostics', 'Hydraulic Pressure', 'bar', 80, 0, 'REAL', 0, 100),
        createItem(15, 'Lapformer Diagnostics', 'Calender Motor Current', 'A', 80, 4, 'REAL', 0, 60),
        createItem(16, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(17, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(18, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(19, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
      ];

    case 'Comber':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Nips per Minute', 'nips/min', 20, 0, 'UINT', 0, 600),
        createItem(3, 'Main Operational', 'Delivery Speed', 'm/min', 20, 2, 'REAL', 0, 400),
        createItem(4, 'Main Operational', 'Sliver Hank', 'Ne', 20, 6, 'REAL', 0.1, 0.25),
        createItem(5, 'Main Operational', 'Production', 'kg/h', 20, 10, 'REAL', 0, 120),
        createItem(6, 'Main Operational', 'Waste / Noil %', '%', 20, 14, 'REAL', 5, 30),
        createItem(7, 'Main Operational', 'Lap Feed per Nip', 'mm', 20, 18, 'REAL', 4, 8),
        createItem(8, 'Main Operational', 'Current Can Length', 'm', 20, 22, 'UINT', 0, 8000),
        createItem(9, 'Main Operational', 'Total Can Length', 'm', 20, 24, 'UINT', 0, 8000, true),
        createItem(10, 'Main Operational', 'Machine Status', '', 20, 26, 'UINT', 0, 10),
        createItem(11, 'Settings', 'Target Nips/min', 'nips/min', 30, 0, 'UINT', 200, 600, true),
        createItem(12, 'Settings', 'Top Comb Penetration', 'mm', 30, 2, 'REAL', -1.0, 2.0, true),
        createItem(13, 'Shift Report', 'Combed Sliver Produced', 'kg', 40, 0, 'REAL', 0, 1000),
        createItem(14, 'Shift Report', 'Noil Waste Collected', 'kg', 40, 4, 'REAL', 0, 300),
        createItem(15, 'Comber Diagnostics', 'Brush Motor Current', 'A', 80, 0, 'REAL', 0, 40),
        createItem(16, 'Comber Diagnostics', 'Noil Aspiration Suction', 'Pa', 80, 4, 'INT', 0, 2000),
        createItem(17, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(18, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(19, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(20, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
      ];

    case 'Blow Room':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Line Production Rate', 'kg/h', 20, 0, 'REAL', 0, 1500),
        createItem(3, 'Main Operational', 'Chute Feed Pressure', 'Pa', 20, 4, 'INT', 0, 800),
        createItem(4, 'Main Operational', 'Beater 1 Speed', 'rpm', 20, 6, 'UINT', 0, 1800),
        createItem(5, 'Main Operational', 'Beater 2 Speed', 'rpm', 20, 8, 'UINT', 0, 1800),
        createItem(6, 'Main Operational', 'Condenser Speed', 'rpm', 20, 10, 'UINT', 0, 1200),
        createItem(7, 'Main Operational', 'Fan Suction Pressure', 'Pa', 20, 12, 'INT', 0, 3000),
        createItem(8, 'Main Operational', 'Blend Ratio Component A', '%', 20, 14, 'REAL', 0, 100),
        createItem(9, 'Main Operational', 'Chute Reserve Level', '%', 20, 18, 'REAL', 0, 100),
        createItem(10, 'Main Operational', 'Machine Status', '', 20, 22, 'UINT', 0, 10),
        createItem(11, 'Settings', 'Line Target Output', 'kg/h', 30, 0, 'REAL', 100, 1500, true),
        createItem(12, 'Settings', 'Chute Set Pressure', 'Pa', 30, 4, 'INT', 50, 500, true),
        createItem(13, 'Shift Report', 'Total Material Delivered', 'kg', 40, 0, 'REAL', 0, 12000),
        createItem(14, 'Shift Report', 'Dropping Waste Collected', 'kg', 40, 4, 'REAL', 0, 1000),
        createItem(15, 'Line Diagnostics', 'Beater 1 Motor Current', 'A', 80, 0, 'REAL', 0, 60),
        createItem(16, 'Line Diagnostics', 'Metal Detector Trip Count', '', 80, 4, 'UINT', 0, 50),
        createItem(17, 'Line Diagnostics', 'Spark Detector Status', '', 80, 6, 'BOOL', 0, 1),
        createItem(18, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(19, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(20, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(21, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
      ];

    case 'Auto Winder':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Winding Speed', 'm/min', 20, 0, 'REAL', 0, 2200),
        createItem(3, 'Main Operational', 'Drum Speed', 'rpm', 20, 4, 'UINT', 0, 4000),
        createItem(4, 'Main Operational', 'Yarn Tension', 'cN', 20, 6, 'REAL', 0, 50),
        createItem(5, 'Main Operational', 'Active Winding Units', 'units', 20, 10, 'UINT', 0, 72),
        createItem(6, 'Main Operational', 'Total Clearer Cuts', 'cuts', 20, 12, 'UDINT', 0, 500000),
        createItem(7, 'Main Operational', 'Current Package Length', 'm', 20, 16, 'UDINT', 0, 200000),
        createItem(8, 'Main Operational', 'Package Diameter', 'mm', 20, 20, 'REAL', 50, 320),
        createItem(9, 'Main Operational', 'Splice Cycles Today', '', 20, 24, 'UINT', 0, 10000),
        createItem(10, 'Main Operational', 'Machine Status', '', 20, 26, 'UINT', 0, 10),
        createItem(11, 'Settings', 'Target Winding Speed', 'm/min', 30, 0, 'REAL', 500, 2200, true),
        createItem(12, 'Settings', 'Package Full Length Set', 'm', 30, 4, 'UDINT', 10000, 200000, true),
        createItem(13, 'Shift Report', 'Packages Doffed', '', 40, 0, 'UINT', 0, 800),
        createItem(14, 'Shift Report', 'Shift Yarn Production', 'kg', 40, 2, 'REAL', 0, 2500),
        createItem(15, 'Winder Diagnostics', 'Suction Plant Current', 'A', 80, 0, 'REAL', 0, 50),
        createItem(16, 'Winder Diagnostics', 'Main Compressed Air', 'bar', 80, 4, 'REAL', 0, 10),
        createItem(17, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(18, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(19, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(20, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
      ];

    case 'RAP':
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Main Operational', 'Carriage Spindle Position', 'sp', 20, 0, 'UINT', 1, 2400),
        createItem(3, 'Main Operational', 'Travel Speed', 'm/s', 20, 2, 'REAL', 0, 3.0),
        createItem(4, 'Main Operational', 'Piecing Cycle Duration', 's', 20, 6, 'REAL', 5, 45),
        createItem(5, 'Main Operational', 'Piecing Success Rate', '%', 20, 10, 'REAL', 0, 100),
        createItem(6, 'Main Operational', 'Total Ends Pieced Today', '', 20, 14, 'UINT', 0, 5000),
        createItem(7, 'Main Operational', 'Failed Piecing Retries', '', 20, 16, 'UINT', 0, 500),
        createItem(8, 'Main Operational', 'Gripper Actuator Pressure', 'bar', 20, 18, 'REAL', 0, 8),
        createItem(9, 'Main Operational', 'Robot Battery Voltage', 'V', 20, 22, 'REAL', 20, 30),
        createItem(10, 'Main Operational', 'Machine Status', '', 20, 26, 'UINT', 0, 10),
        createItem(11, 'Settings', 'Spindle Travel Range Min', 'sp', 30, 0, 'UINT', 1, 2400, true),
        createItem(12, 'Settings', 'Spindle Travel Range Max', 'sp', 30, 2, 'UINT', 1, 2400, true),
        createItem(13, 'Shift Report', 'Ends Detected Broken', '', 40, 0, 'UINT', 0, 6000),
        createItem(14, 'Shift Report', 'Successful Piecings', '', 40, 2, 'UINT', 0, 6000),
        createItem(15, 'Robot Diagnostics', 'Travel Servo Current', 'A', 80, 0, 'REAL', 0, 30),
        createItem(16, 'Robot Diagnostics', 'Laser Distance to Rail', 'mm', 80, 4, 'REAL', 10, 200),
        createItem(17, 'Robot Diagnostics', 'Docking Charging Current', 'A', 80, 8, 'REAL', 0, 20),
        createItem(18, 'History & RTC', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(19, 'History & RTC', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(20, 'History & RTC', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(21, 'History & RTC', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
      ];

    case 'Carding':
    default:
      // Carding fallback (if default_metadata.csv hasn't loaded yet)
      return [
        createItem(1, 'Program Version', 'Program Version', '', 10, 0, 'REAL', null, null),
        createItem(2, 'Default screen', 'Delivery Speed', 'm/min', 20, 0, 'REAL', 0, 300),
        createItem(3, 'Default screen', 'Sliver Hank', 'Ne', 20, 4, 'REAL', 0, 300),
        createItem(4, 'Default screen', 'Production', 'kg/h', 20, 8, 'REAL', 0, 250),
        createItem(5, 'Default screen', '5m CV', '%', 20, 12, 'REAL', 0, 15),
        createItem(6, 'Default screen', 'Lickerin Suction Pressure', '%', 20, 16, 'REAL', 0, 300),
        createItem(7, 'Default screen', 'Flats Suction', '%', 20, 20, 'REAL', 0, 300),
        createItem(8, 'Default screen', 'A\\L Value', '%', 20, 24, 'REAL', 0, 300),
        createItem(9, 'Default screen', 'Current Length', 'm', 20, 36, 'UINT', 0, 9999),
        createItem(10, 'Default screen', 'Total CAN Length', 'm', 20, 38, 'UINT', 0, 9999),
        createItem(11, 'Default screen', 'Machine Status', '', 20, 42, 'UINT', 0, 10),
        createItem(12, 'Default screen', 'Chute Pressure', 'Pa', 20, 44, 'INT', 0, 500),
        createItem(13, 'Default screen', 'Feed Weight in gms/mtr', 'g/m', 20, 46, 'REAL', 100, 800),
        createItem(14, 'Default screen', 'Cylinder Speed', 'rpm', 20, 82, 'UINT', 0, 800),
        createItem(15, 'Default screen', 'Flats Speed', 'mm/min', 20, 84, 'REAL', 0, 500),
        createItem(16, 'Default screen', 'Lickerin Speed', 'rpm', 20, 88, 'REAL', 0, 1800),
        createItem(17, 'Drive Status', 'Main Drive Inverter Frequency', 'Hz', 80, 0, 'REAL', 0, 75),
        createItem(18, 'Drive Status', 'Lickerin Motor Current', 'A', 80, 4, 'REAL', 0, 50),
        createItem(19, 'Drive Status', 'Cylinder Motor Current', 'A', 80, 8, 'REAL', 0, 80),
        createItem(20, 'Drive Status', 'Total Machine Efficiency', '%', 80, 12, 'REAL', 0, 100),
        createItem(21, 'Machine History', 'RTC Date (Day)', '', 150, 0, 'USINT', 1, 31),
        createItem(22, 'Machine History', 'RTC Month', '', 150, 1, 'USINT', 1, 12),
        createItem(23, 'Machine History', 'RTC Year', '', 150, 2, 'UINT', 2020, 2099),
        createItem(24, 'Machine History', 'Cumulative Run Hours', 'hrs', 150, 15, 'REAL', 0, 100000),
        createItem(25, 'Energy Monitor', 'Total Active Power', 'kW', 410, 26, 'REAL', 0, 100),
        createItem(26, 'Energy Monitor', 'Total Energy', 'kWh', 410, 38, 'REAL', 0, 1000000),
      ];
    }
  };

  const items=getRawItems();
  // Complete the standard RTC layout in built-in profiles. Uploaded metadata
  // stays authoritative and is never assigned guessed offsets by this helper.
  if(items.some(item=>item.groupCode===150)){
    let nextTag=Math.max(...items.map(item=>item.tagCode))+1;
    for(const [name,offset,max] of [['Hour',4,23],['Minute',5,59],['Second',6,59]] as const){
      if(!items.some(item=>item.groupCode===150 && item.offset===offset)){
        items.push(createItem(nextTag++,'History & RTC',`RTC ${name}`,'',150,offset,'USINT',0,max));
      }
    }
  }
  return attachDropdownsToMetadata(items);
}
