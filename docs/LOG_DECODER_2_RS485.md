# Log Decoder 2 - RS-485 Docklight captures

Open **AI Assist > Chat > Log Decoder 2 (RS-485)**, or the welcome-screen
Log Decoder 2 card. Paste a capture or upload a TXT/LOG/CSV file containing
byte text. Select hexadecimal or decimal input and explicitly select the
device byte order. The tool reads RX lines and wrapped RX byte data; TX lines
and their continuations are excluded. Bare byte sequences are also supported.
CSV files here contain captured bytes, not arbitrary spreadsheet columns.

This initial profile implements the supplied RAP GC 90 shift packet:
40 fields, absolute frame offsets 0-55, start 253/FD, node 1/RHS or 2/LHS,
one-byte group code 90/5A, two-byte total length 56, CRC byte 54 and end 240/F0.
The stated unsigned-short group-code type conflicts with its explicit
one-byte width/position; the decoder reports this and follows byte positions.

Every capture has a seven-column table and a combined CSV export:
Tag, Parameter, Offset, Type, Raw decimal bytes, Decoded value, Finding.
Tag uses the supplied serial number; the protocol did not supply PLC tag codes.
Reserved fields retain raw numeric values. Machine mode/status remain numeric
codes; efficiency and durations are not assigned undocumented scales or units.

No CRC algorithm, polynomial, seed, xor-out or coverage was supplied. CRC is
always unverified. Structure checks do not assert a valid checksum, actual
machine state or a successful physical-device test. Byte order is user-selected
rather than inferred from B&R or SpinConnect conventions. Unsupported group
codes retain header/raw evidence and do not decode shift payload fields.

Input errors, truncated frames, declared-length mismatches, unsupported nodes,
wrong end bytes and calendar/time field ranges are visible. No LLM interprets
these bytes. Processing stays in the browser; there is no serial-port access,
RS-485 transmission or external AI call. The existing SpinConnect/YBS decoder
and Python validation engine are unchanged. The initial profile does not claim
to import arbitrary metadata protocols.

Verification uses constructed packet fixtures (both byte orders, multiple and
wrapped Docklight RX/TX frames, all 40 fields, malformed input and invalid
headers). Browser checks exercise AI Assist access, required byte-order
selection, decoded values, CSV downloads, modal Escape and three viewport widths.
No real Docklight/device capture was provided for physical verification.
