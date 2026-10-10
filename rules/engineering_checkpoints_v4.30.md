# uSOPp Engineering Checkpoints v4.30

## CHECKPOINT 1

Subroutine: `mms_nw_rCyclic.st`

Validation: Verify the default Alarm Receive Timeout logic.

Expected Behaviour:
1. `Alarm_EN_Delay` shall be assigned a default value of 250 when its value is less than or equal to 30.
2. `HMI_read_recv_timeout_time` shall be assigned a default value of 250 when its value is less than or equal to 30.
3. `read_recv_timeout_time` shall be calculated as `HMI_read_recv_timeout_time × 1000`.

Verify:
- Logic exists
- Comparison uses `<= 30`
- Default value is 250
- Final timeout is multiplied by 1000

## CHECKPOINT 2

Subroutine: `mms_nw_rCyclic.st`

Validation: Verify RTC Synchronization Logic.

Expected Behaviour: The project shall copy the received RTC data from `nw_rcv_buffer` to `rtc_nw_rcv_buffer` for every byte from Index 9 through Index 27.

Verify:
- All assignments exist
- No index is missing
- Source buffer is `nw_rcv_buffer`
- Destination buffer is `rtc_nw_rcv_buffer`
- Index sequence is continuous (9–27)

## CHECKPOINT 3

Subroutine: `mms_nw_rCyclic.st`

Validation: Verify Product Code Mapping.

Expected Behaviour: For every CASE Group Code response except Group Code 11, the first parameter copied into the response packet shall be `Blow_room_product_code` using `memcpy()` with Size = 2 bytes.

Verify:
- Present in every Group Code except 11
- Variable is `Blow_room_product_code`
- `memcpy` size is 2 bytes
- It is the first packet parameter copied
- `nw_i` is incremented by 2 immediately after `memcpy()`

## CHECKPOINT 4

Validate the RTC and Ping feature implementation. Search the complete Automation Studio workspace.

RTC accepted implementation names: `MMS_RTC`, `mms_rtc`, `mms_rtc_auto`.

Expected RTC files or equivalent implementation:
- `mms_rtc.fun`
- `mms_rtc_auto/Cyclic.st`
- `mms_rtc_auto/Init.st`
- `mms_rtc_auto/IEC.prg`
- `mms_rtc_auto.var`
- `gVarmms_rtc.var`
- `gVarmms_rtc.typ`

Ping accepted logic names include `Icmp_Ping.st`, `Icmp_Ping.var`, `ICMP_PING`, `IcmpPing`, and `Ping` when equivalent functionality exists.

Accepted Ping HMI pages:
- `MMS_IP_Ping.page`
- `MMS_Ping.page`
- `MMS_IP_PING.page`
- `MMS_PING.page`
- Equivalent page names are accepted when functionality is equivalent.

Ping HMI validation:
- Ping page exists
- IP Address input
- Start Ping button
- Ping status display
- Required variable bindings exist
- Do not fail on object-name differences when functionality is equivalent
- Do not compare pixel positions
- Ignore screen-resolution differences between C70, T30 and HMI variants

Return: PASS / FAIL / NOT FOUND.

If FAIL, explain missing file, missing page, missing variable, missing logic or missing HMI object and provide recommendations.
