# YBS support in DataInspect (4.71.2)

## Use

1. Open DataInspect, **Manage targets**, set **Request frame → Server → YBS (Embedded C)**, and enter the device IP, TCP port and Machine ID. This frame selection is separate from Machine Type. The supplied capture uses ID 1; no device port is assumed.
2. Save and apply. The supplied `ybs_meta_data_with RAP_121836.xlsx` is available as the YBS factory metadata (10,244 fields, 18 groups). Upload a newer YBS workbook through the existing metadata dialog when available.
3. Test connection reads GC 10. Read selected groups normally, or paste a full decimal response into **Manual received data** for offline decoding.
4. Read actual values in the parameter table; each YBS value retains its raw number, raw hex, factors and source worksheet row. Excel verification exports include these columns. The packet inspector shows the YBS header and checksum rules.
5. Live collection is opt-in and uses the same YBS profile. Dashboard bindings use actual values. Saved test results retain the source metadata. YBS metadata template exports preserve the original YBS type names and factors.

### Build a request frame

In **Manage targets → Manual Data Frame Editor & Sender**, choose **Server → B&R (SpinConnect)** or **Server → YBS (Embedded C)**, enter Machine ID and Read group code, then use **Generate read frame**. Decimal and HEX previews show the actual bytes in the editor. **YBS GC 70** is also available as a shortcut. **Save & Apply** retains the selected frame for normal reads and live collection. The same selector is available under **Connection settings**.

For **Server → YBS**, Machine ID **1**, GC **70**, the read frame is:

```text
writeBuffer: [241 1 1 0 9 0 70 65 240]  length 9
HEX: F1 01 01 00 09 00 46 41 F0
```

The checksum is 65 (41 hex), using XOR seed FF. The request builder uses the selected protocol rather than the machine department. Old YBS targets without an explicit frame selection retain the YBS profile. Changing a frame selection clears the configured live groups and stops collection until the new groups are selected and enabled.

The existing SpinConnect simulator and RTC writer are separate profiles. The supplied captures do not establish a YBS clock-write command or date encoding. YBS reads use network targets or offline bytes; no speculative RTC write or SpinConnect GC 11 close command is sent to YBS.

## Capture-derived wire profile

| Byte | Meaning |
| --- | --- |
| 0 | F1 start marker |
| 1 | Machine ID |
| 2 | Function 1 (captured reads and responses) |
| 3–4 | Big-endian **total frame length**, including header and trailer |
| 5–6 | Big-endian Group Code, also present in responses |
| 7 through length − 3 | Data |
| length − 2 | XOR of all preceding bytes, initial seed FF |
| length − 1 | F0 end marker |

Data is big-endian in the supplied captures. **The user confirmed YBS's embedded C type widths and sequential offsets. YBS type names are not IEC type names:** UCHAR is 1 unsigned byte, USINT is 2 unsigned bytes, UINT is 4 unsigned bytes, and FLOAT is 4-byte IEEE 754. Internally these normalize to USINT, UINT, UDINT and REAL respectively. Global IEC and SpinConnect type widths are unchanged.

`actual = raw / Divison factor * Multiplication factor` (the workbook spells division `Divison`). For example, GC 45 Average TPI is raw 1625 / 100 = 16.25; Pneumafill Kg is raw 1260 / 1000 = 1.260 kg; Count is raw 235 / 10 = 23.5. GC 10 version 6261 / 1000 = 6.261. Range checks use actual values for this profile.

There are no explicit offsets or tag codes in the workbook. As requested, offsets are calculated by accumulating the confirmed field widths in row order within each group; generated tag identities refer to source row numbers. Names and status meanings are never borrowed from SpinConnect. Only explicit Bit:0…Bit:15 labels are applied. For example, spindle raw 128 activates Bit 7, **Left**, not a guessed running state.

The supplied frames support the header/checksum and byte-order rules, and the user confirmed the field-width/offset convention. The discrepancies below remain recorded: this capture cannot establish which device/service/logging stage damaged GC 21 or what the two unmapped GC 70 bytes mean.

## Supplied-log findings

537 frame lines: 268 valid read requests and 269 responses. **189 responses pass wire checks; all 80 GC 21 responses fail checksum and are missing F0.** Their declared/captured total length is 143 bytes. Invalid responses are withheld from value decoding. This establishes a problem in the recorded GC 21 frames, not which device/service/logging stage caused it.

| GC | Workbook data bytes | Captured data bytes | Finding |
| --- | ---: | ---: | --- |
| 10 | 26 | 26 | Length matches |
| 21 | 134 | 134 | All 80 frames invalid; values unverified |
| 22, 23, 24, 25 | 4800 each | 3648 each | Workbook has 2400 spindle fields; frame fits 1824. GC 30 reports 1824 configured spindles. Remaining 576 fields stay unavailable. |
| 30 | 11 | 11 | Length matches |
| 40 | 18 | 18 | Length matches |
| 45, 60 | 136 each | 136 each | Length matches |
| 55 | 116 | 116 | Length matches |
| 70 | 6 | 8 | Two trailing bytes unmapped. Do not assume a year offset or new fields. |
| 76 | 100 | 76 | 24 metadata fields missing |
| 77 | 50 | 14 | 36 metadata fields missing |
| 90 | 98 | 98 | Length matches |
| 91 | 112 | 112 | Length matches |
| 92 | 38 | 38 | Length matches |
| 93 | 94 | 94 | Length matches |

No array auto-trimming, zero-filling or checksum repair is performed. A wire-valid frame with a metadata length mismatch is not reported as a fully matched group. Matching length alone does not prove every field's meaning.

## Reusable decoder and audit

`python_engine/ybs.py` provides frame building/validation, workbook row normalization and raw/actual decoding. It uses the Python standard library; Excel audit import/export uses the existing openpyxl dependency. Browser and backend decoders share the same normalized schema.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/audit_ybs.py --metadata "path\ybs.xlsx" --log "path\capture.txt" --output "release\ybs-audit"
```

The audit produces `YBS_audit.xlsx` and `YBS_audit.json` with source hashes, line numbers, per-frame checks, group layouts and first-valid-group raw/actual samples. Repeated log excerpts are counted as recorded, not silently deduplicated.

Verification for this release covered all 537 captured frames in Python and TypeScript, all 10,244 normalized rows, XLSX/CSV metadata round trips, raw/actual examples, invalid-frame rejection, missing-array fields, log decoding and fragmented loopback TCP exchanges. SpinConnect request bytes and little-endian REAL decoding were checked. A physical YBS device and the Ubuntu deployment have not been verified.

## Frame error explanations (4.71.2)

Chopper and the YBS DataInspect packet inspector show byte checks with zero-based positions, expected and received decimal/HEX values, length checks, possible trailer-placement patterns and next checks. Invalid frames retain no trusted parameter readings. The Explain this capture action passes the selected raw bytes and source lines; the server recalculates YBS faults directly before optional model generation.

A final byte that matches the XOR over preceding bytes but is not F0 is reported as a possible trailer-position problem. It is not proof that firmware caused the fault. Compare embedded C transmit bytes, Go socket receive bytes and the logged frame before changing source or metadata.
