# Navigation and menu refinement - 14 November 2026

The sidebar logo toggles compact and expanded navigation with a keyboard-accessible button. The separate Compact view footer action is removed. The existing account-scoped preference is retained across reloads. Medium desktop widths now honor the selected mode; mobile keeps its horizontal navigation.

Header popovers stack above the submenu bar. The submenu uses a translucent, blurred background with high-contrast navigation text. Dropdown panels use the current theme surface and text colors, a visible border and a shadow; reduced-transparency preferences use opaque surfaces.

Verification: TypeScript compilation and the main production build passed. Isolated browser checks passed for five themes, saved preferences, logo toggle, account-menu hit testing above the submenu, dropdown keyboard controls and 390-1600 pixel layouts. No project records or approval rules changed.
