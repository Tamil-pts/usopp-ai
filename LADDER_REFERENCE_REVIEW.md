# Ladder reference review and implementation — 4.64.3

## 4.64.8 follow-up

- Unchanged .ld files now get network models too. Selecting a ladder opens the
  explicit Ladder diagram view; unchanged files initially show all networks.
  Show all source and Differences remain separate XML evidence views.
- Older saved comparisons can rebuild missing diagrams from saved source and
  local/global declarations. Rerun only when the retained source is missing.
- Older AS XML may omit the type on the header and middle/bottom rows. The
  renderer uses the type from that block's top row, keeping one continuous body
  and the header's instance. Saved schema-2 models upgrade during rendering.
- Comparison trees and selected exports omit .prg/.pkg files. Their metadata
  still provides program/package ordering and descriptions.

Inputs read from the workspace:

- `LRJ9SXV16346_09092026/Logical/hs_flts/hs_fltsCyclic.ld`
- `hs_fltsCyclic.ld.pdf`
- `C:/Users/PTPL0241/Projects/Project 3/Logical/hs_mcseq/hs_mcseqCyclic.ld`
- Supplied screenshots of hs_mcseq networks 0007, 0011 and 0012, and the Project 2 / Project 1 faultCyclic comparison.

The XML has 84 networks. The PDF has 85 physical pages: pages 1–9 are project listings, pages 10–83 contain ladder drawings (including continuation sheets), and pages 84–85 list variables. PDF physical page numbers differ from the printed numbers after continuation sheets.

## Drawing cases verified against the PDF

| Network | PDF physical page | XML / drawing relationship |
| --- | --- | --- |
| 0001 | 10 | Normally closed emergency contact, normally open STARTTMR_T62.Q, and set coil. Set coils display S. |
| 0008 | 11 | Two contacts drive A_Main_Fan_Mtr_TPU_Flt_V513_3. A branch after STARTTMR_T62.Q drives A_Safety_Relay_trip. The second row has an empty cell with or=true in column 2 (one-based). The junction is on the right edge of that cell, not before STARTTMR_T62.Q. |
| 0015 | 13 (printed 12) | TSERVO_FAULT is one TON block. Header, top and bottom rows carry its instance, IN/Q and PT/ET pins. The two input contacts are parallel at IN; t#3S connects separately to PT. An OR-marked contact joins at its right edge. |
| 0017 | 13 | R_TRIG_SYS_PRS is one R_TRIG block with a header row and topbottom pin row. Both rows must retain the same instance identity. Q drives a set coil. |
| 0083 | 79–83 | A_MODULE_MISSING_FAULT is driven by a 45-row hardware-status network with many parallel branches and selection/bypass gates. Continuation pages are parts of this one network, not new networks. |
| 0084 | 83 | Two normally closed module-status contacts and FLOW_SENSOR_ENABLED drive the ordinary A_MODULE_MISSING_Addition coil. |

This is fault and interlock logic: emergency/door/drive fault latches, pressure and speed checks, timed supervision, battery status and hardware module status. The excerpt alone does not establish the complete machine operating sequence.

## Renderer changes implemented

- OR junctions now join the right edge of the XML cell. Empty OR cells draw a vertical junction without adding a Boolean bypass from the left rail.
- Header and topbottom bodies retain one block identity and its instance. Functions and function blocks occupy two logical columns; other cells occupy one. Raw XML child indices are retained separately.
- Continuous multi-row function/block bodies share aligned input and output pins. Analog values connect separately from Boolean branches; unused output stubs do not touch the power rail.
- Source declarations provide datatype labels and declaration comments where available. Click a symbol for variable, instance, logical row/column, declaration and related uses. Unknown analog types remain blank.
- Network comments, S/R coil notation, commented state and source identity are retained. The main MatchView display is graphical, with common zoom and linked scrolling; readable summaries remain collapsed.
- HTML/SVG retain the complete diagram. PDF and Word use matching continuation tiles at grid boundaries, keeping short blocks together. JSON retains the normalized model and SVG. Report cache fingerprints include the renderer version.

## Additional reference cases verified

| Reference | Result |
| --- | --- |
| hs_mcseq 0007 | EQ, AND, OR and R_TRIG occupy logical columns 2, 4, 9 and 11 (one-based). Instance R3, three reset coils and the nested bypass branch are retained. |
| hs_mcseq 0011 | AND/EQ and UDINT_TO_TIME feed one TON Y20_Tmr_T215; its XML segments at different raw child indices align at logical column 10. |
| hs_mcseq 0012 | R_TRIG R4 keeps its header instance and CLK/Q pins. |
| faultCyclic Project 2 vs Project 1 | Developed network 0027 is added. Both source network 0028 records are paired and highlight T#15S versus INCH_PB_SENSING_PT. |

All 123 hs_mcseq and 84 hs_flts networks parsed without model warnings. The
17 ladder/project-knowledge/cross-reference regression tests passed. The actual
fault comparison was exported as HTML, PDF, Word and JSON; SVG-to-PDF continuation
geometry and authenticated view/SVG/PNG routes were checked. The PDF and PNG
renderings were visually reviewed.

Sample artifacts are in
`.usopp_exports/ladder/Project1_All_TEST_20261008_Ladder_4.64.3/`.
The full comparison contains 2 added, 10 removed, 19 modified and 61 unchanged
paired networks across the 90-network base and 82-network developed source.

## Remaining limits

Geometry follows the source topology; typography, spacing and line wrapping are
not pixel-identical to Automation Studio. Unsupported XML elements produce
warnings. Static diagrams do not show live values or execution state. Saved old
models are upgraded on rendering, but rerun older comparisons for corrected
network pairing and new exports. Neither reference PLC file was changed.
