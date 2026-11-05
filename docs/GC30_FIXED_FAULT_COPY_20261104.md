# Group 30 fixed fault-buffer payload

ByteMap accepts the following single-copy layout with **WARNING**, rather than
requiring an unused `nw_i` cursor:

```iecst
nw_snd_buffer[3] := 0;
nw_snd_buffer[4] := 20;
memcpy(ADR(nw_snd_buffer[5]), ADR(Temp_nw_snd_buffer[1]), 20);
nw_snd_buffer_length := ((nw_snd_buffer[3] * 256) + nw_snd_buffer[4] + 5);
nw_snd_response := TRUE;
```

This copies fault bytes 1–20 into send-buffer bytes 5–24. The payload is 20
bytes and the response including its header is 25 bytes. The source-linked
`GC30 Fixed Bulk Copy` warning explains the accepted layout. JSON, the packet
path view and Excel retain the warning; no PLC source is rewritten.

The exception applies only to Group 30, with one positive-length fixed copy
at byte 5 from an indexed source array, no cursor usage, no conditional/loop
layout and no additional payload writes. BOOL/string fields and copying from
the protocol send/receive buffers do not receive this exception. Ordinary
cursor-based Group 30 layouts and other group codes keep their existing rules.

Packet sizes, declared source/destination bounds, source resolution, alarm
packing, metadata and response setup are still checked. An error in these
checks can still make the group fail. Metadata offsets remain payload-relative
(0–19 here); saved reports retain their original results until validation is
run again.

Checked on 4 November 2026 with 38 targeted regression tests and the real
authenticated `/api/validate` handler running the engine subprocess. The Excel
download contained the warning. The supplied pattern produced 20 configured
and copied bytes, one warning and zero failures. Artifacts:
`.build/gc30-fixed-copy-20261104/`.
