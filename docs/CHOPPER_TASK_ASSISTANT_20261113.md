# Top menus and Chopper task assistant — 13 November 2026

The existing module rail remains the main menu. Top submenus now use clearer active states and spacing. Documents opens in a viewport-positioned dropdown with keyboard arrows, Home/End, Escape and outside-click handling. Assist highlights its current tab. Cancelled unsaved navigation does not switch the module rail group or dispatch a WorkHub navigation request.

The top-center Chopper opens a task catalog and conversation panel. Fifteen supported tasks cover project creation, FRD/MOM/validation/FAT/closure drafting, flowcharts/infographics, mind maps, dashboards, document and PLC comparison, ByteMap validation, DataInspect, LogicScan and file analysis in full Chat. Search filters the catalog. Common create/compare/validate requests in chat produce an explicit Start task button.

Actions reuse the existing editors and tools. Creating a document opens its existing numbered-document creation workflow; users choose project links, input evidence, create/save/submit and review through the normal controls. Chopper does not claim that opening a workspace saved a file, approved a document or completed a PLC test. Responses receive the supported task list and an instruction to avoid claiming execution without tool evidence. Backend access and approval checks remain authoritative. Full automation of arbitrary application operations is not implemented.

Module visibility filters available tasks. Demo users do not see creation tasks. Existing history and unsaved guards are reused by task launches. No new external AI service is required.

Browser verification uses isolated accounts and data: menu keyboard/dismissal, FRD creation from a task card, flowchart creation from a text command, and Document Compare routing. Run `.venv/Scripts/python.exe tests/chopper_tasks_browser.py` after building the main UI. Logs: `.build/chopper-tasks-20261113/browser.log`.

Final browser checks passed: mobile task panel bounds, keyboard menu handling, FRD creation card, flowchart text command, document comparison launch, and retention of both menu and workspace when an unsaved-navigation prompt is cancelled.

Detailed FRD, flowchart and mind-map requests are carried into the creation dialog as the brief; requests longer than 40 characters select the existing Chopper drafting mode. Users review the brief and start generation with the existing controls. Dashboard requests retain their original widget/layout prompt.
