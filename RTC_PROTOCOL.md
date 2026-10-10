# DataInspect RTC sending

The shared PLC logic reads a 19-character timestamp from `nw_rcv_buffer[9..27]`.
DataInspect's default SpinConnect layout sends one 30-byte request with Function 1 and GC 10. The timestamp is attached to that group read; the PLC code processes its RTC fields separately.

| Index | Meaning | Example |
| --- | --- | --- |
| 0 | STX | 3 |
| 1 | Machine ID | 0 |
| 2 | Function | 1 |
| 3..4 | Payload length | 0, 23 |
| 5..6 | Group code | 0, 10 |
| 7..8 | Reserved | 0, 0 |
| 9..12 | Year ASCII | 50, 48, 50, 54 = 2026 |
| 13 | Hyphen | 45 |
| 14..15 | Month ASCII | 49, 48 = 10 |
| 16 | Hyphen | 45 |
| 17..18 | Day ASCII | 48, 56 = 08 |
| 19 | Space | 32 |
| 20..21 | Hour ASCII | 49, 52 = 14 |
| 22 | Colon | 58 |
| 23..24 | Minute ASCII | 48, 53 = 05 |
| 25 | Colon | 58 |
| 26..27 | Second ASCII | 48, 54 = 06 |
| 28 | XOR of indices 0..27 | calculated |
| 29 | ETX | 2 |

This example is `2026-10-08 14:05:06` in the browser's local computer time. Sending is manual; the computer-time checkbox refreshes the preview only. Other PLC projects may use a different function or the legacy ASCII-at-byte-5 layout; select the layout that their receive logic implements.

## Why the watch screenshot shows GC 11

The nine-byte frame `3 0 1 0 2 0 11 11 2` is the GC 11 close request for Machine ID 0. Its valid bytes end at index 8. Values at 9 and above can remain from earlier requests. Capture the RTC request before closure, or use the modal's actual sent frame and backend log. GC 11 has no acknowledgement frame; the client waits for the PLC to close the session.

## PLC checks before claiming the time was set

- Call each ASCII conversion block before reading its output. The supplied order reads the previous invocation's output:

```st
MMS_ASCIIINT_INT0.ASCIIINT_INPUT := rtc_nw_rcv_buffer[9];
MMS_ASCIIINT_INT0();
NEW_YEAR := MMS_ASCIIINT_INT0.INT_OUTPUT;

MMS_ASCIIINT_INT1.ASCIIINT_INPUT := rtc_nw_rcv_buffer[10];
MMS_ASCIIINT_INT1();
NEW_YEAR := NEW_YEAR * 10 + MMS_ASCIIINT_INT1.INT_OUTPUT;
```

- Snapshot RTC characters only when a complete valid 30-byte request has been received. Do not reparse the tail of a nine-byte GC 11 request or other short read every scan. Check separators and digit ranges before applying time.
- The supplied Step0 waits for COMPARE_HOUR and COMPARE_MINUTE. Step5 also requires the PLC's existing date to equal the new date and RTC_TIME_MOVE_BIT to be true. These conditions can delay or prevent correction of a wrong date.
- The project 2 file available here contains the RTC buffer copy, but the supplied conversion/state-machine excerpt is not present in that file. Confirm the complete deployed RTC task includes the actual RTC set call and checks its status.
- A result-code-0 response confirms communication. It does not prove an RTC set call completed. Read PLC RTC using GC 150 metadata and compare with the requested time, allowing elapsed time and any PLC update delay. Group 150 offsets differ between projects; DataInspect uses the loaded metadata.

The original PLC project source is unchanged by this application update. Verify any PLC changes in Automation Studio with the intended operating sequence.
