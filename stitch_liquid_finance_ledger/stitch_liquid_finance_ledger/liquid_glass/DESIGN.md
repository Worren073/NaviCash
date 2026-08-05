---
name: Liquid Glass
colors:
  surface: '#0c1324'
  surface-dim: '#0c1324'
  surface-bright: '#33394c'
  surface-container-lowest: '#070d1f'
  surface-container-low: '#151b2d'
  surface-container: '#191f31'
  surface-container-high: '#23293c'
  surface-container-highest: '#2e3447'
  on-surface: '#dce1fb'
  on-surface-variant: '#bcc9c6'
  inverse-surface: '#dce1fb'
  inverse-on-surface: '#2a3043'
  outline: '#879391'
  outline-variant: '#3d4947'
  surface-tint: '#6bd8cb'
  primary: '#6bd8cb'
  on-primary: '#003732'
  primary-container: '#29a195'
  on-primary-container: '#00302b'
  inverse-primary: '#006a61'
  secondary: '#bcc7de'
  on-secondary: '#263143'
  secondary-container: '#3e495d'
  on-secondary-container: '#aeb9d0'
  tertiary: '#ffb59a'
  on-tertiary: '#591c02'
  tertiary-container: '#d27956'
  on-tertiary-container: '#4f1700'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#89f5e7'
  primary-fixed-dim: '#6bd8cb'
  on-primary-fixed: '#00201d'
  on-primary-fixed-variant: '#005049'
  secondary-fixed: '#d8e3fb'
  secondary-fixed-dim: '#bcc7de'
  on-secondary-fixed: '#111c2d'
  on-secondary-fixed-variant: '#3c475a'
  tertiary-fixed: '#ffdbce'
  tertiary-fixed-dim: '#ffb59a'
  on-tertiary-fixed: '#370e00'
  on-tertiary-fixed-variant: '#773215'
  background: '#0c1324'
  on-background: '#dce1fb'
  surface-variant: '#2e3447'
  glass-surface: rgba(255, 255, 255, 0.06)
  glass-border: rgba(255, 255, 255, 0.12)
  status-paid: '#2DD4BF'
  status-delayed: '#F43F5E'
  status-pending: '#FB7185'
  status-warning: '#FBBF24'
  income: '#4ADE80'
  expense: '#FB7185'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  numeric-display:
    fontFamily: Geist
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.03em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-padding: 1.25rem
  element-gap: 1rem
  stack-tight: 0.5rem
  section-margin: 2rem
  bottom-nav-height: 80px
---

## Brand & Style

The design system for this mobile-first financial application is built on the **Liquid Glass** narrative—a fusion of high-end **Glassmorphism** and **Corporate Modern** sensibilities. It is designed to evoke a sense of "digital liquidity" and transparency, crucial for a personal finance app operating in volatile economic environments like Venezuela.

The aesthetic prioritizes depth and material realism through translucent layers, high-density background blurs, and "specular" edge highlights. This creates a premium, tech-forward experience that feels both futuristic and securely grounded. The UI communicates "trust through clarity," using depth to separate the conceptual layers of financial data—moving from a deep, atmospheric base to vibrant, interactive glass "panes" that float atop the canvas.

## Colors

The palette is anchored in a dark-mode-first environment to enhance the luminous quality of the glass effects.

- **Primary & Secondary:** A core of "Financial Teal" (`#0D9488`) provides a professional, calming interactive color. This is balanced against deep Slate (`#1E293B`) for secondary structures.
- **Glass Surfaces:** Instead of solid fills, the system uses `glass-surface` (a low-opacity white) and `glass-border` (a slightly more opaque edge) to define containers.
- **Semantic Logic:** Status colors are high-chroma to ensure visibility against dark, blurred backgrounds. 
  - **Incomes** use vibrant greens (`#4ADE80`).
  - **Expenses and Delayed items** use urgent roses and reds (`#F43F5E`).
- **USD Anchor:** Reference values in USD should always be presented in a muted, silver-tinted neutral to distinguish them from the primary VES transaction amounts.

## Typography

The typography uses **Geist** for its technical precision and exceptional legibility at small sizes, which is critical for dense financial lists.

- **Financial Data:** A specific `numeric-display` style is used for account balances. It features tighter letter spacing and a heavy weight to command authority.
- **Hierarchical Contrast:** Use `label-sm` in uppercase for metadata headers (e.g., "TASA DEL DÍA") to create a clear distinction from primary data points.
- **Multi-Currency Display:** When showing USD conversions alongside VES, the primary amount uses `body-lg` (Bold), while the secondary conversion uses `body-md` with 60% opacity to denote its role as a reference.

## Layout & Spacing

This design system employs a **mobile-first fluid grid** designed for a PWA (Progressive Web App) environment. 

- **The Dashboard Grid:** Content is organized into cards that span the full width of the viewport minus the `container-padding`. 
- **Action Density:** Financial lists use a high-density vertical rhythm (`stack-tight`) to ensure maximum information is visible without scrolling, catering to the "10-second data entry" requirement.
- **Floating Architecture:** The layout relies on a fixed-position bottom navigation bar that sits 16px above the viewport edge, creating a floating effect consistent with the glass narrative.
- **Safe Zones:** Always account for mobile browser chrome (URL bars) and "home indicators" by using dynamic CSS variables for the bottom navigation offset.

## Elevation & Depth

Depth is the defining characteristic of this design system. It is achieved through three specific layers:

1.  **The Atmospheric Base:** A deep gradient background (`#020617` to `#0F172A`) that acts as the "void" where elements float.
2.  **The Glass Layer (Standard):** Used for cards and secondary actions. It features a `backdrop-filter: blur(20px)`, a `1px` border of `glass-border`, and a subtle `inner-shadow` (white, 10% opacity) at the top edge to simulate light hitting the thickness of the glass.
3.  **The Active Layer (Elevated):** Used for the floating bottom nav and modals. These have a higher blur (`40px`) and a more pronounced ambient shadow (tinted with the `primary_color` at 15% opacity) to signify their proximity to the user.

## Shapes

The shape language is consistently **Rounded**, reflecting a modern, approachable fintech tool.

- **Standard Elements:** Cards, input fields, and modal containers use a `1rem` radius. 
- **Interactive Elements:** Primary buttons and chips use a "Pill" shape (fully rounded) to maximize touch-target friendliness.
- **The Floating Action Button (FAB):** The central "+" button in the bottom nav is a perfect circle, creating a clear visual anchor for the app's primary function (adding a transaction).

## Components

- **Glass Cards:** The primary container for transactions. Must include a subtle gradient overlay (5% opacity) to prevent the blurred background from making text illegible.
- **Floating Bottom Nav:** A semi-transparent glass bar with a cutout or raised center for the circular `+` Action Button. Icons should be line-art style with a 2px stroke.
- **Currency Inputs:** Large, center-aligned text fields with no background (ghost style) until focused, at which point they expand into a glass container.
- **Status Chips:** Small, pill-shaped labels with a low-opacity version of the status color as the background and a high-contrast version for the text (e.g., Background: `status-paid` at 20%, Text: `status-paid` at 100%).
- **Quick Action Shortcuts:** A horizontal scrolling row of glass circles with vibrant icons, allowing for "1-tap" categorization.
- **Progress Bars:** For savings goals, use a "glass tube" track with a solid `primary_color` fill that has a slight outer glow to simulate liquid energy.