# Chopper MCP and engineering exports - 4.61.0

## MCP server

uSOPp exposes an authenticated MCP Streamable HTTP endpoint at
`http://127.0.0.1:8200/api/mcp/`. It uses the official Python MCP SDK and supports
protocol negotiation, initialization, tools/list and tools/call.

Open **Settings > Chopper AI connection > MCP** to copy the endpoint and create
a token. Configure an MCP client that supports Streamable HTTP with that URL
and header `Authorization: Bearer <your token>`. Tokens expire after 12 hours;
revoke them from Settings. They carry the signed-in account's permissions.
Do not put tokens into project files or shared reports.

Upload/select a project in ByteMap first and use its `sessionId` in tool calls.

| Tool | Purpose |
| --- | --- |
| project_context | Project identity, active configuration, saved run summaries |
| read_source | Read project-relative B&R code and its version hash |
| find_variable | Exact variable references with file and line |
| ladder_networks | Ladder cells, rows, columns, pins and branch connections |
| validate_project | Run ByteMap or generate MetaWorks metadata and save a new run |
| prepare_rule | Create a draft for engineer review; does not enable it |

The MCP server and local GGUF inference are separate capabilities in one app.
An MCP-capable client chooses when to call the tools. The chat does not execute
arbitrary model-generated code. B&R changes use the existing reviewed source
editor, backups and version checks. AS 2.7 binary containers remain view-only.

## Standard names

New generated rule IDs use `BndR_ID_000001` and increment locally. Existing rules
receive persistent standard display IDs while their saved internal references
stay valid. The registry is `.usopp_exports/identifiers.sqlite3`; preserve it
with the application's data when moving installations. IDs are local to an
installation, not a globally unique registry across servers.

Test/run identity and report filenames use:

`<project>_<department>_TEST_<YYYYMMDD_HHMMSS>_<unique suffix>`

Timestamps use India time. The suffix distinguishes repeated/concurrent runs.
Unsafe filename characters are replaced and long names are shortened.
WorkHub, ByteMap, LogicScan and MatchView display the run identity; report and
metadata downloads use it. Older cached runs may need to be rerun to obtain
the current ID and graphical ladder model.

## Metadata compatibility

MetaWorks generation and workbook Save/Export normalize MIN, MAX, SCALE_FACTOR
and OFFSET_FACTOR to Excel numeric cells with General formatting. Decimal,
scientific, quoted and IEC typed numeric literals are supported. Null markers
stay null markers. Unresolved expressions are reported with sheet/cell instead
of being exported as string limits. Saving an edited workbook creates a copy.

For a previously exported workbook, open it in the workbook viewer and export
again, or regenerate it from its project. Changing only the Excel visual style
does not convert a string into a numeric XML cell. Importable metadata keeps its
required sheets/headers; report cover pages do not go into metadata files.

## Graphical ladder comparison

MatchView reconstructs supported Automation Studio Ladder XML as a shared
structured model and interactive SVG: contacts, coils, analog inputs/outputs,
functions, function-block instances/pins, lines, empty cells and OR markers.
Rows/columns come from the source, not an AI-generated image. Select Show all
to inspect unchanged networks. Click symbols for details and other locations
in the current ladder source; MCP find_variable provides project references.

Added elements are green, removed red, modified amber. SVG/PNG downloads use the
run ID. HTML/PDF/Word comparison reports contain diagrams for changed networks;
PDF keeps vector diagrams and Word embeds PNG. SVG/PNG are exported separately.

This is a structural diagram, not an execution simulator or a pixel-for-pixel
Automation Studio editor. Unknown XML elements produce visible warnings.
Supported OR markers reconstruct branches from their grid positions; unusual
or proprietary XML layouts require source review. Wide report diagrams scale
to the page; use the SVG to inspect them at full detail.

Word export removes non-XML characters from legacy source evidence and includes
ladder details without the former undefined-variable failure.

## Verification in this release

Python compilation, TypeScript checks, numeric XLSX round trips, Project 2
metadata generation (1,002 parameters), a real 8-network Ladder XML comparison,
HTML/PDF/DOCX/SVG/PNG generation, concurrent rule-ID allocation, authenticated MCP
tool calls/revocation, and bundled-runtime GGUF inference were checked.
The packaged Windows app also passed Admin sign-in, HTML/PDF/Word ladder exports,
MCP access, GGUF inference/start/stop and embedded Project 2 metadata generation.
SpinConnect upload and live PLC communication were not available for this check.
