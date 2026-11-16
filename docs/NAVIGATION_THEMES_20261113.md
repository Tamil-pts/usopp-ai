# Navigation and appearance refresh - 13 November 2026

The existing React workspace now has a wider desktop sidebar with clear group
labels and descriptions, raised icon tiles, selected-state lighting and a subtle
original engineering sketch background. The top bar and submenu use coordinated
surfaces, borders and restrained shadows. No Angular migration, WebGL renderer,
external icon service or remote background asset was added. The dimensional effect
is CSS, rather than an interactive 3D model. Reduced-motion preferences are respected.

Desktop users can collapse the sidebar. The choice is retained through the existing
account storage mechanism. Medium screens use compact navigation automatically;
mobile screens use a horizontal navigation strip. Existing menu groups, top-level
submenus, permission checks, project selector, team inbox and Chopper remain connected
to their current workflows. No project data or approval logic was changed.

## Five themes

- Light: cool surfaces, ocean navigation and the existing personal accent.
- Dark: midnight surfaces with readable text and the existing personal accent.
- Retro: cream paper, warm terracotta and workshop-inspired sketch details.
- Classic: ivory, ink blue and restrained brass highlights.
- Monochrome: neutral grayscale chrome and controls.

Choose themes from the palette button in the top bar or Settings > Appearance.
The picker provides miniature previews, selected states, keyboard arrow navigation
and Escape dismissal. Theme selection persists through the existing account settings.
Light/Dark retain personal accent customization; curated themes supply their own
accent. Engineering status colors and specialized source/circuit renderers retain
their domain meaning. Embedded DataInspect receives its compatible Light/Dark base
scheme; it is not represented as supporting five independent embedded themes.

The legacy data-theme attribute remains Light/Dark for existing rendering rules.
The separate data-workspace-theme attribute selects the complete workspace palette.
Original asset: src/shared/assets/engineering-sketch.svg.

## Validation

TypeScript and the production build passed. Browser checks cover all five themes,
refresh persistence, collapsed-sidebar persistence, document and Spin Connect menus,
keyboard theme selection, and viewport widths from 390 to 1600 pixels. Theme and
mobile screenshots are under .build/navigation-themes-20261113/. All fixture accounts
and projects use isolated test storage.
