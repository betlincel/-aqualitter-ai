---
name: Telemetry Civic Console
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#bccac0'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#87948b'
  outline-variant: '#3d4a42'
  surface-tint: '#68dba9'
  primary: '#68dba9'
  on-primary: '#003825'
  primary-container: '#25a475'
  on-primary-container: '#00311f'
  inverse-primary: '#006c4a'
  secondary: '#ffb3ad'
  on-secondary: '#68000a'
  secondary-container: '#a40217'
  on-secondary-container: '#ffaea8'
  tertiary: '#ffb3ae'
  on-tertiary: '#601214'
  tertiary-container: '#dd706b'
  on-tertiary-container: '#570b0e'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#85f8c4'
  primary-fixed-dim: '#68dba9'
  on-primary-fixed: '#002114'
  on-primary-fixed-variant: '#005137'
  secondary-fixed: '#ffdad7'
  secondary-fixed-dim: '#ffb3ad'
  on-secondary-fixed: '#410004'
  on-secondary-fixed-variant: '#930013'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ae'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#7f2928'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  display-lg:
    fontFamily: Manrope
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-xl:
    fontFamily: Manrope
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.015em
  headline-lg:
    fontFamily: Manrope
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 30px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Manrope
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0.01em
  mono-metric:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.02em
  mono-data:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-caps:
    fontFamily: Geist
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.06em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
  space-2xl: 2rem
---

## Brand & Style

This design system establishes an operational standard for municipal telemetry and autonomous waterway cleanup systems. The aesthetic fuses institutional municipal authority with developer-grade environmental telemetry. It rejects decorative clutter in favor of high-density operational legibility, situational awareness, and split-second alert discernment.

The design language balances two core dynamics:
- **Calm, High-Precision Telemetry:** Under ordinary conditions, the system presents an organized, low-strain dark environment dominated by neutral deep-slate containers, razor-thin structural borders, and structured tabular typography.
- **Strict Semantic Accents:** Color operates purely as functional signal. Emerald accents denote operational health, eco-efficiency metrics, and autonomous route fidelity. Muted coral accents are reserved exclusively for litter anomalies, hazardous density alerts, and hardware blockages.

Surfaces borrow subtle cues from modern telemetry tools: faint surface glassmorphism for floating overlays, low-reflectance backgrounds, and micro-borders defining exact coordinate modules.

## Colors

The palette is engineered strictly for low-fatigue monitoring during extended mission ops and multi-screen municipal operations centers.

### Primary Color
- **Seed & Eco Telemetry (`#059669` / Emerald):** Applied strictly to positive telemetry vectors: fuel savings, autonomous surface coverage, litter retrieval capacity metrics, and optimal path corridors.

### Secondary Color
- **Debris & Anomaly Alert (`#EF4444` / Muted Coral Red):** Restricted to high-salience telemetry: critical debris accumulation thresholds, obstacle collision paths, sensor occlusion alerts, and containment bin saturation warnings.

### Neutrals & Surfaces
- **Canvas Base (`#0F172A`):** Deep slate-navy base providing maximum perceived contrast without pure black retinal fatigue.
- **Container / Card (`#1E293B`):** Elevation layer for charts, sensor matrices, vessel health nodes, and camera feeds.
- **Structural Outlines (`#334155`):** 1px boundaries dividing spatial panels and tabular modules without visual weight.
- **Primary Typography (`#F8FAFC`):** Pure off-white high-contrast text for critical readout figures and active states.
- **Secondary Typography (`#94A3B8`):** Subdued slate for engineering units, timestamp feeds, latitude/longitude readouts, and secondary navigational labels.

## Typography

The type system blends the balanced authority of **Manrope** for primary headers and module titles with the dense, developer-grade precision of **Geist** for tabular figures, operational status logs, coordinates, and telemetry stream indicators.

- **Manrope:** Drives dashboard titles, module headings, and diagnostic alert headers. Features slight tracking contraction to feel technical yet civic and official.
- **Geist:** Used for standard body, dense operational matrices, table columns, and all numerical outputs. Its tabular metrics align clean decimal figures in real-time telemetry tables.
- **Letter Spacing & Casing:** Micro-labels, tracking axes, and telemetry category titles must utilize `label-caps` in full uppercase with +0.06em tracking to preserve scanning speed under multi-feed conditions.

## Layout & Spacing

Telemetry dashboards demand structured modularity. The layout utilizes an asymmetric fluid grid optimized for high-resolution displays (1440px to 4K multi-monitor arrays) while maintaining stackable responsive safety for field tablets.

- **Desktop Framework:** 12-column grid layout with fixed command sidebars (280px), multi-pane telemetry grids (4, 6, or 8-column modules), and continuous situational ribbon headers.
- **Spatial Rhythm:** Built upon a dense 4px base increment (`space-xs` = 4px, `space-sm` = 8px, `space-md` = 12px, `space-lg` = 16px, `space-xl` = 24px, `space-2xl` = 32px).
- **Responsive Handling:**
  - **Desktop (1280px+):** Full multi-pane tiling with active map viewports, real-time debris feed lists, and continuous metrics sidecar.
  - **Tablet (768px - 1279px):** Split dual-column stack. Map viewport locks to top half; telemetry grids collapse to 2 columns below with horizontal data ribbons.
  - **Mobile (<768px):** Single-column stacked triage mode; interactive canvas collapses to contextual alert cards, toggleable map sheets, and single-metric summary cards.

## Elevation & Depth

Visual hierarchy does not rely on heavy drop shadows. Elevation is rendered using strict tonal layering paired with crisp 1px borders and translucent glassmorphism for floating spatial overlays.

- **Layer 0 (Canvas Base):** Solid `#0F172A`. Base layer for background grids, map viewports, and root navigation frames.
- **Layer 1 (Card & Module Tier):** `#1E293B` bounded by a 1px solid stroke of `#334155`. Cards do not project exterior drop shadows; separation is defined exclusively through line geometry.
- **Layer 2 (Floating Overlays & Menus):** `rgba(30, 41, 59, 0.85)` surface with a 12px backdrop blur (`backdrop-filter: blur(12px)`) and a subtle inner highlight (`box-shadow: inset 0 1px 0 0 rgba(248, 250, 252, 0.05)`). Used for telemetry map HUDs, vessel hover cards, and dropdown filters.
- **Layer 3 (Modal / Critical Alert Intercepts):** `#1E293B` with an ambient diffused shadow: `0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)`, bordered by `#EF4444` when active debris or system breach conditions trigger.

## Shapes

The design uses a restrained `1` (Soft) roundedness profile to maintain a clinical, high-tech instrument feel while avoiding harsh brutalist corners.

- **Base Radius (0.25rem / 4px):** Standard controls, buttons, table rows, input fields, and metric indicator chips.
- **Container Radius (0.5rem / 8px):** Used for `rounded-lg` cards, modular analytics containers, modal viewports, and camera stream containers.
- **Floating Overlays (0.75rem / 12px):** Used for `rounded-xl` map HUDs and high-level mission control panels.
- **Geometric Strictness:** Roundedness is never applied purely decoratively; corners remain tight to maximize usable internal data density and screen real estate.

## Components

### Buttons
- **Primary Action (Eco / Ops):** Background `#059669`, text `#F8FAFC`, radius `4px`. Hover: `#047857`. Active state includes a crisp 1px inset ring.
- **Destructive / Anomaly Triage:** Background `rgba(239, 68, 68, 0.12)`, border `1px solid #EF4444`, text `#EF4444`. Hover: background `#EF4444`, text `#FFFFFF`.
- **Ghost / Neutral Action:** Background `transparent`, border `1px solid #334155`, text `#F8FAFC`. Hover: background `#1E293B`, border `#64748B`.

### Status Chips & Badges
- **Eco / Metric Chips:** Background `rgba(5, 150, 105, 0.15)`, text `#34D399`, border `1px solid rgba(5, 150, 105, 0.3)`. Contains a 6px circular indicator dot.
- **Debris Hazard Chips:** Background `rgba(239, 68, 68, 0.15)`, text `#FCA5A5`, border `1px solid rgba(239, 68, 68, 0.3)`. Pulse effect permitted only on active untriaged obstacles.
- **Neutral Telemetry Chips:** Background `#0F172A`, text `#94A3B8`, border `1px solid #334155`.

### Input Fields & Controls
- **Text & Coordinate Fields:** Background `#0F172A`, border `1px solid #334155`, text `#F8FAFC`, placeholder `#64748B`. Focus: border `1px solid #059669`, ring `0 0 0 1px #059669`.
- **Checkboxes & Radios:** 16px square/circle with `#0F172A` fill and `1px solid #334155` border. Checked: background `#059669` with pure white vector checkmark.

### Telemetry Cards & Module Panels
- Default structure: Background `#1E293B`, border `1px solid #334155`, radius `8px`, padding `16px`.
- Card Header: `Manrope` 14px bold title, uppercase label status on the right, separated from content by a 1px internal rule (`#334155`).

### Data Tables & Sensor Lists
- Dense tabular layout with rows bounded by bottom borders `1px solid #1E293B`.
- Header row uses uppercase `label-caps` typography (`#94A3B8`). Numeric data columns align right with tabular figures in `Geist`.
- Hover state: Background `rgba(255, 255, 255, 0.02)`.

### Domain-Specific Components
- **Debris Threat Banner:** A top-anchored drawer or pinned widget bordered in `#EF4444` displaying AI confidence level (e.g., `PLASTIC_ACCUMULATION: 94.2%`), estimated mass in kg, and immediate geofence override toggles.
- **Vessel Telemetry Gauge:** Circular or horizontal segmented progress bar using `#059669` for autonomous battery reserve, payload capacity, and path efficiency indexes.