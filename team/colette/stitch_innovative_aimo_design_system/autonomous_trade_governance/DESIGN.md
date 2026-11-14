---
name: Autonomous Trade Governance
colors:
  surface: '#f6f8fb'
  surface-dim: '#cddbf5'
  surface-bright: '#ffffff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f0f4f9'
  surface-container: '#e8eef6'
  surface-container-high: '#dde5f0'
  surface-container-highest: '#d2dce9'
  on-surface: '#0e1c2f'
  on-surface-variant: '#434750'
  inverse-surface: '#243145'
  inverse-on-surface: '#ebf1ff'
  outline: '#94a3b8'
  outline-variant: '#cbd5e1'
  surface-tint: '#345f99'
  primary: '#00254d'
  on-primary: '#ffffff'
  primary-container: '#0a2540'
  on-primary-container: '#93c5fd'
  inverse-primary: '#a7c8ff'
  secondary: '#006780'
  on-secondary: '#ffffff'
  secondary-container: '#76dcff'
  on-secondary-container: '#006077'
  tertiary: '#002c1c'
  on-tertiary: '#ffffff'
  tertiary-container: '#00442d'
  on-tertiary-container: '#42b989'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d5e3ff'
  primary-fixed-dim: '#a7c8ff'
  on-primary-fixed: '#001c3b'
  on-primary-fixed-variant: '#174780'
  secondary-fixed: '#b7eaff'
  secondary-fixed-dim: '#6cd3f7'
  on-secondary-fixed: '#001f28'
  on-secondary-fixed-variant: '#004e61'
  tertiary-fixed: '#85f8c4'
  tertiary-fixed-dim: '#68dba9'
  on-tertiary-fixed: '#002114'
  on-tertiary-fixed-variant: '#005137'
  background: '#f9f9ff'
  on-background: '#0e1c2f'
  surface-variant: '#d6e3fe'
  agent-untrusted: '#7c3aed'
  agent-untrusted-bg: '#f3e8ff'
  status-warning: '#d97706'
  status-warning-bg: '#fef3c7'
  status-error: '#dc2626'
  status-error-bg: '#fee2e2'
  status-success-bg: '#d1fae5'
  nordic-frost-lime: '#c0e021'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.025em
  display-lg-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 34px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 30px
    letterSpacing: -0.015em
  title-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  metric-lg:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 34px
    letterSpacing: -0.02em
  body-base:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: '0'
  body-bold:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: '0'
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: '0'
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.06em
  mono-token:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.01em
  mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

This design system defines an enterprise autonomous commerce governance platform for mission-critical B2B food logistics. The brand pairs institutional Nordic trust and cold-chain precision with deterministic AI agent orchestration. The visual tone is authoritative, immaculate, and technologically rigorous.

The core aesthetic combines **Nordic Utilitarian Precision** with **Subtle High-Tech Glassmorphism**:
- **Asymmetric Trust Topology**: Distinct visual semantics separate untrusted generative AI claims from verified deterministic backend validations.
- **Architectural Micro-Borders**: Ghost outlines and crisp 1px structural framing replace heavy shadows, creating clear spatial definition for high-density logistics dashboards.
- **Human-in-the-Loop Clarity**: Calm, low-noise monitoring surfaces step aside during normal automated throughput and surface high-visibility exception signals only when human intervention is mandatory.
- **Auditable Cryptographic Integrity**: Deterministic state transitions, idempotency keys, and append-only hash chains are treated as core visual elements rather than buried metadata.

## Colors

The palette establishes an immediate distinction between enterprise authority, deterministic operational verification, and untrusted machine cognition.

### Trust Boundary Architecture
- **Verified / Deterministic Tier**: Anchored by `primary` Deep Nordic Navy (`#003b73`) and `tertiary` Verified Emerald (`#059669`). Used strictly for confirmed backend decisions (`AUTONOMOUS`, `approved`, `accepted`, `active`), cryptographically intact `prev_hash` links, and verified supplier certifications.
- **Untrusted / LLM Reasoning Tier**: Exclusively demarcated by `agent-untrusted` (`#7c3aed`) on `agent-untrusted-bg` (`#f3e8ff`). Any generative summary, prompt template output, or non-deterministic agent claim must carry this signature to avoid visual conflation with verified database facts.
- **Boundary & Network Telemetry**: Driven by `secondary` Telemetry Cyan (`#0891b2`). Applied to live polling countdowns, ephemeral WebSocket heartbeats, and in-flight lifecycle states (`submitted`, `pending`).
- **Policy Intervention Tiers**: `status-warning` Amber (`#d97706`) governs `REQUIRES_APPROVAL` exceptions (e.g., spending ceiling breaches), while `status-error` Crimson (`#dc2626`) enforces hard stops (`DENIED`, `rejected`, allergen contamination alerts).
- **Subtle Heritage Accent**: `nordic-frost-lime` (`#c0e021`) serves as a high-visibility badge accent for organic credentials, environmental ratings, and trade tier indicators.

## Typography

The typographic hierarchy pairs the objective, humanist clarity of **Inter** with the structural discipline of **JetBrains Mono**.

### Formatting Standards
- **Tabular Figures**: Set `font-variant-numeric: tabular-nums` globally on all table cells, price totals, quote countdown timers, and unit volumes. Currency values must always render with explicit two-decimal precision and standard 3-character ISO suffixes (e.g., `2100.00 EUR`, `1.05 EUR/L`).
- **Cryptographic & System Identifiers**: `customer_id`, `agent_id`, `quote_id`, `approval_request_id`, `order_id`, idempotency keys (`ik_order_9f2a`), and hash nodes (`prev_hash`) must render in `mono-token` or `mono-sm`. Truncate long hashes with middle ellipsis (e.g., `0x8f2a...c4b1`) with a hover tooltip displaying the complete string.
- **Classification Badges**: Section markers, status chips, and trust zone ribbons use `label-caps` in uppercase tracking (`+0.06em`) to ensure instant differentiation from editable fields and prose.

## Layout & Spacing

The layout model employs a responsive 12-column grid system tuned for high information density without visual crowding.

### Screen Adaptations
- **Desktop (1024px – 1440px+)**: 12-column fluid grid, `2rem` page margins, `1.5rem` gutters. Navigation manifests as a persistent left command rail (`240px` wide, collapsible to `64px` icon-only mode). Large tables display 10 full rows per page alongside interactive split-screen inspectors.
- **Tablet (640px – 1023px)**: 8-column layout, `1.5rem` outer margins, `1rem` gutters. Split approval panes convert to top/bottom docked cards.
- **Mobile (< 640px)**: 4-column layout, `1rem` margins, `0.5rem` gutters. Complex multi-column comparison grids (such as product trade tiers) collapse into stacked swipeable cards, maintaining full action parity and minimum 44px tap targets.

### Rhythmic Density
Use compact component padding (`space-xs` to `space-sm`) inside tabular cells, chips, and metadata badges to sustain operational density. Use `space-lg` to `space-xl` strictly for macro boundaries, separating top-level executive metrics from transactional approval queues.

## Elevation & Depth

Visual hierarchy is maintained primarily through surface tint tiers, crisp micro-borders, and targeted glassmorphism rather than heavy drop shadows.

### Elevation Levels
- **Canvas Base (`surface`, `#f6f8fb`)**: The foundational workspace. Recessed controls and group backgrounds sit directly on this cool frost layer.
- **Tier 1 — Data Surfaces (`surface-bright`, `#ffffff`)**: Tabular rows, inspection panels, and cards use solid Glacier White bounded by a 1px solid `outline-variant` (`#cbd5e1`) micro-border. Ambient elevation is minimal (`0 1px 2px rgba(11, 25, 44, 0.04)`).
- **Tier 2 — Elevated Cards & Popovers**: Floating tooltips, dropdown menus, and sticky table summary headers sit at `0 4px 12px rgba(11, 25, 44, 0.08)` with a 1px `outline-variant` boundary.
- **Tier 3 — Real-Time Approval Overlays**: Modal dialogs and priority decision sheets use a glassmorphic surface: `rgba(255, 255, 255, 0.88)` fill, `backdrop-filter: blur(16px)`, a crisp `1px solid rgba(203, 213, 225, 0.8)` rim, and an ambient tinted drop shadow (`0 20px 40px -12px rgba(10, 37, 64, 0.22)`). This leaves background logistics state contextualized but non-interactive.

## Shapes

The design system adopts a calibrated **Rounded** language (`0.5rem` / `8px` standard radius) that projects industrial reliability and geometric cleanliness.

### Component Shapes
- **Standard Controls & Inputs**: Form fields, standard buttons, data table cells, and panel containers apply `0.5rem` (`roundedness: 2`).
- **Cards & Modal Windows**: Master cards and exception panels apply `0.75rem` (`rounded-lg`), while real-time approval modals utilize `1rem` (`rounded-xl`).
- **Telemetry Chips & Badges**: Status indicators, hash tokens, countdown pills, and allergen tags apply full pill rounding (`9999px`) to emphasize their atomic, non-editable data state.

## Components

### 1. Policy Decision Badges
Badges communicate immediate determinism using pill-shaped geometries, 12px monospace text, and synchronized state colors:
- **AUTONOMOUS**: Emerald `#059669` text on `#d1fae5` background with a solid check-shield icon. Indicates order was cleared without human friction.
- **REQUIRES_APPROVAL**: Amber `#92400e` text on `#fef3c7` background with a pulse clock-alert icon. Highlights rule exemptions (e.g., threshold overruns).
- **DENIED**: Crimson `#991b1b` text on `#fee2e2` background with an octagonal stop icon. Blocks execution deterministically (e.g., allergen or contract restriction).

### 2. Trust-Zone Callout Containers
Approval cards require a hard structural separation between machine inference and verified policy:
- **Untrusted Agent Reasoning Callout**: Contained within an `agent-untrusted-bg` (`#f3e8ff`) surface, a 3px left border in `agent-untrusted` (`#7c3aed`), and a top ribbon: `AGENT REASONING · UNVERIFIED PROSE`. Text uses `body-base` Inter, constrained to `65ch` reading width.
- **Deterministic Verification Panel**: Contained within `surface-container-low` (`#f0f4f9`) with a 1px `outline-variant` border, displaying verified price formulas (`EUR`), rule-check timestamps, and cryptographic state.

### 3. Real-Time Approval Modal
- **Structure**: Glassmorphic modal (`rgba(255, 255, 255, 0.88)`, `backdrop-filter: blur(16px)`).
- **Header**: Contains the approval request ID in `mono-token`, policy outcome badge, and a real-time countdown progress bar tracking the 5-minute quote validity window.
- **Actions**: Dual-action layout in footer:
  - *Approve Action*: Solid primary navy (`#003b73`) or emerald (`#059669`) button with white text and a confirmation shield icon.
  - *Reject / Escalate Action*: Ghost white button with a 1px border in `#fca5a5` and `#dc2626` text, preventing misclicks while keeping rejection visible.

### 4. Audit Log Hash-Chain Viewer
- **Grid Layout**: 10 rows per page with strict 40px cell height and `space-sm` horizontal padding.
- **Chain Representation**: Every row displays Actor ID, Event Name, ISO Timestamp, and a truncated `prev_hash` (`mono-sm`). A vertical connecting hairline in Verified Emerald (`#059669`) links adjacent valid hashes, turning red if a hash discontinuity is detected.

### 5. Multi-Tier Quote Selector (`good` / `better` / `best`)
- A 3-column card set comparing alternative fulfillment configurations.
- The recommended autonomous choice is elevated with a 2px solid `secondary` Telemetry Cyan (`#0891b2`) border, a `BEST MATCH` chip, tabular price metrics (`metric-lg`), and paired allergen/carbon-neutral badges.

### 6. Interactive Inputs & Search
- Inputs feature a crisp `#ffffff` surface, 1px `#cbd5e1` micro-border, and `0.5rem` radius.
- On focus, input transitions to a `2px` Telemetry Cyan (`#0891b2`) stroke paired with a subtle `0 0 0 3px rgba(8, 145, 178, 0.15)` ambient ring.