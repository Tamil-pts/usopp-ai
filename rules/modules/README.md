# uSOPp Rule Modules

Rule modules are declarative configurations consumed by `rule_engine_v4_30.py`.

## SC-COMMON-PACKET

`SC-COMMON-PACKET_v1.0.json` is the first configurable module. It discovers active
`CASE nw_group_code OF` branches in `mms_nw_rCyclic.st`, validates packet size,
`memcpy()` parameters, datatype/size consistency and `nw_i` increments, and
generates `<ProjectName>.xlsx`.

Modules are disabled in the default legacy rule set. Add the module configuration
to a reviewed rules JSON when it should be executed.

## BR_RULES

`BR_RULES_v1.0.json` replaces the retired SC-BR-LOGIC rule IDs with BR_RULE-001
through BR_RULE-008. Each draft records the requested category, feature, rule
name, description, machine scope, source file, and expected PLC/HMI logic. The
RTC rule belongs to the MMS_RTC feature; the other seven belong to Spin Connect.
Rules remain disabled until an engineer tests and enables them in Assist.

## SC-FIN-CHECKLIST

`SC-FIN-CHECKLIST_v1.0.json` is the normalized 32-row Spin Connect 2.0 Finisher
checklist. Blank separator rows remain listed in `importSummary`; defined rows keep
their original CSV row number. Imported rules are disabled until an engineer
reviews source files, Group Code ranges and variable substitutions. Packet rows
validate variables, transfer sizes and cursor increments. Source rows validate
executable statements and array declarations.
