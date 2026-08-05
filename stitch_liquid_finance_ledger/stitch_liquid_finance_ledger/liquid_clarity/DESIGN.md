---
name: Liquid Clarity
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#3d4947'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#6d7a77'
  outline-variant: '#bcc9c6'
  surface-tint: '#006a61'
  primary: '#00685f'
  on-primary: '#ffffff'
  primary-container: '#008378'
  on-primary-container: '#f4fffc'
  inverse-primary: '#6bd8cb'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#595c5e'
  on-tertiary: '#ffffff'
  tertiary-container: '#727577'
  on-tertiary-container: '#fbfdff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#89f5e7'
  primary-fixed-dim: '#6bd8cb'
  on-primary-fixed: '#00201d'
  on-primary-fixed-variant: '#005049'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#e0e3e5'
  tertiary-fixed-dim: '#c4c7c9'
  on-tertiary-fixed: '#191c1e'
  on-tertiary-fixed-variant: '#444749'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 48px
    fontWeight: '800'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 48px
  xl: 80px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 64px
---

## Brand & Style

This design system centers on a "Liquid Glass" aesthetic, emphasizing transparency, light refraction, and fluid motion. The brand personality is sophisticated, innovative, and crystalline. It targets a high-end tech audience that values precision and a premium feel. 

The UI evokes an emotional response of clarity and calm through a light-mode-first approach. It utilizes **Glassmorphism** heavily but adapts it for high-readability by using high-contrast borders and intelligent backdrop filters. Surfaces feel like polished acrylic or clear water resting on a pure white canvas.

## Colors

The palette is anchored by a pure `#FFFFFF` background to ensure maximum freshness. 
- **Primary Teal (#0D9488):** Optimized for light mode to maintain AA contrast ratios for accessibility. Used for primary actions and highlights.
- **Secondary Slate (#0F172A):** Used for primary text and high-contrast iconography.
- **Neutral/Surface:** We utilize a range of Slate grays for hierarchy. 
- **Liquid Glass Surfaces:** Surfaces use a semi-transparent white (`rgba(255, 255, 255, 0.7)`) combined with a heavy backdrop blur (20px+) to create the glass effect. These must be paired with a subtle, low-opacity slate border to define the edge against the white background.

## Typography

The typography system pairs **Plus Jakarta Sans** for headlines to provide a soft, modern geometric feel, with **Hanken Grotesk** for body and labels to maintain professional precision. 

In this light-mode execution, headlines use the Secondary Slate color to anchor the page. Letter spacing is slightly tightened on larger display text to maintain the "liquid" tension of the brand. Body text uses a slightly lighter slate shade to ensure long-form reading comfort without losing contrast.

## Layout & Spacing

This design system utilizes a **Fluid Grid** model with high-margin breathing room to emphasize the "Liquid" theme. 
- **Desktop:** 12-column grid, 64px outside margins, 24px gutters.
- **Tablet:** 8-column grid, 32px outside margins, 20px gutters.
- **Mobile:** 4-column grid, 16px outside margins, 16px gutters.

Spacing follows an 8px base unit. Component internal padding should favor the "MD" (24px) unit to allow the glass containers to feel spacious and light.

## Elevation & Depth

Depth is communicated through **Glassmorphism** and soft, tinted ambient shadows. Since the background is pure white:
- **Level 1 (Base):** White background.
- **Level 2 (Containers):** `surface_glass` with 20px Backdrop Blur, a 1px border of `border_glass`, and a very soft Y-4, Blur-12 shadow with 4% opacity of the Secondary Slate.
- **Level 3 (Popovers/Modals):** Increased Backdrop Blur (40px) and a double-layered shadow (one sharp 2px shadow, one soft 24px shadow) to simulate physical distance from the white base.

Avoid "pure black" shadows; always tint shadows with the Secondary Slate to maintain the sophisticated color harmony.

## Shapes

The shape language is "Rounded," mimicking the surface tension of water droplets. 
- **Standard UI Elements:** 0.5rem (8px) corner radius.
- **Large Containers/Cards:** 1.5rem (24px) corner radius.
- **Buttons/Inputs:** 0.75rem (12px) to provide a distinct tactile feel compared to the layout grid.

## Components

### Buttons
Primary buttons use the Teal color with a subtle inner-glow (white 10% opacity) at the top to simulate light hitting a liquid surface. Text is white. Secondary buttons use the Glass style with a Slate border and Slate text.

### Cards & Containers
Cards must use the backdrop filter `blur(20px)` and the `surface_glass` variable. They should never be opaque white; the background content should always bleed through slightly to maintain the "Liquid Glass" narrative.

### Input Fields
Inputs should be transparent with a `border_glass` 1px stroke. Upon focus, the stroke transitions to the Primary Teal and gains a subtle outer glow.

### Chips & Tags
Small capsules with a 10% opacity version of the Primary Teal background and 100% opacity Teal text. 

### Lists & Navigation
Use "Ghost" hover states—a subtle 5% Slate background with rounded corners—rather than heavy dividers. This keeps the interface feeling light and unobstructed.