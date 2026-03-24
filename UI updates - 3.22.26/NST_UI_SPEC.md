# Narrative Stress Test — Start Screen UI Spec

## Overview

This spec defines the redesigned start screen for the Narrative Stress Test (Project B). 
It was designed to match the visual language of CI Autopilot (Project A). 
The reference HTML file (`nst-start-screen.html`) is the source of truth — open it in a browser to see the exact design.

## Design System (shared with Project A)

### Colors
- **Navy (primary):** `#0E3B54` — hero background, section labels, active states, toggle
- **Teal (secondary):** `#1A5C6A` — hero gradient endpoint, focus rings, auto-suggest button
- **Coral (accent):** `#E8643B` — hero brand text, CTA button
- **Background:** `#FAFBFC` — page background (light, NOT dark theme)
- **Card/Input bg:** `#FFFFFF`
- **Text:** `#333333`
- **Labels:** `#0E3B54` (navy)
- **Muted text:** `#6B7580`
- **Helper text:** `#8A939C`
- **Placeholder text:** `#B0BAC2`
- **Borders:** `#D0D7DD` (default), `#A8B8C2` (hover), `#1A5C6A` (focus)
- **Signal tags:** `#4A6A74` text on `#EAF0F2` background

### Typography
- **Font:** DM Sans (Google Fonts) — all weights
- **Hero brand:** 0.75rem, 700 weight, 0.2em letter-spacing, uppercase
- **Hero title:** 1.75rem, 700 weight
- **Section labels:** 0.68rem, 700 weight, 0.14em letter-spacing, uppercase
- **Section descriptions:** 0.78rem, 400 weight
- **Input labels:** 0.8rem, 500 weight, navy color
- **Input text:** 0.88rem
- **Helper text:** 0.72rem
- **Signal tags:** 0.66rem, 500 weight

### Spacing
- Hero padding: 2.5rem top/bottom, 3rem sides
- Main container: max-width 720px, centered, 2rem top padding
- Grid gap: 1rem between columns, 1.1rem between rows
- Divider margin: 0.5rem top, 1.5rem bottom

## Layout Structure (top to bottom)

### 1. Hero Banner
- Full-width navy-to-teal gradient: `linear-gradient(135deg, #0E3B54 0%, #1A5C6A 60%, #2A7A8A 100%)`
- No decorative elements (no circles, no watermarks)
- Content: "PEMETIQ" brand label (coral) → "Narrative Stress Test" title (white) → subtitle (white 65% opacity)

### 2. Company Name + Domain Row
- Two-column grid, equal width
- Left: Company name text input
- Right: Company domain text input with helper text "Auto-populated. Override if the guess is wrong."

### 3. Divider

### 4. Analysis Mode Section
- Section label: "ANALYSIS MODE"
- Section description: "Choose what to test. **Company name only** infers claims from public signals. Paste a document to test the specific claims made in it."
- Three selection cards in a 3-column grid:
  - Each card has: radio indicator (top-right circle), title (bold), description (muted)
  - Cards:
    1. "Company name only" — "Public signals only — no document needed"
    2. "Earnings transcript" — "Extracts and tests every claim in the call"
    3. "Investor memo" — "Tests a pitch deck, memo, or analyst note"
  - Default: "Company name only" selected
  - Active state: 2px navy border, navy-filled radio dot
  - Inactive state: 1px gray border (#D0D7DD), empty radio circle
  - Hover: slightly darker border, faint gray background
- Conditional paste area:
  - Hidden when "Company name only" is selected
  - Shown as a full-width textarea when "Earnings transcript" or "Investor memo" is selected
  - Transcript placeholder: "Paste the full earnings transcript here..."
  - Memo placeholder: "Paste the investor memo or pitch deck text here..."

### 5. Divider

### 6. Company Type + Competitors Row
- Two-column grid, equal width
- Left column: Company type
  - Label: "Company type"
  - Toggle control: "Public" [switch] "Private"
    - Switch is 36x20px navy pill with white 14px knob
    - Active side label is navy, inactive side is muted gray
    - Default: Public (knob on left)
  - Helper text updates dynamically:
    - Public: "10-K / 10-Q filings pulled from SEC EDGAR automatically."
    - Private: "Limited to news, trends, and non-SEC signal sources."
- Right column: Competitors
  - Label: "Competitors"
  - Text input + "Auto-suggest" button side by side
  - Helper: "Up to 4 for Google Trends comparison. Optional."
  - Auto-suggest button: teal text, gray border, teal fill on hover

### 7. Divider

### 8. Signal Sources
- Section label: "SIGNAL SOURCES"
- Row of small tags: SEC EDGAR, Google Trends, GitHub, App Store, Job postings, Wayback Machine, GDELT, Wappalyzer
- Tags: 0.66rem, teal-gray text on light blue-gray background, 3px radius

### 9. CTA Button
- Full-width coral button: "Run stress test"
- 40px height, 6px radius, 600 weight
- Hover: darker coral (#D4572F)

## Streamlit Implementation Notes

### Custom CSS
- Inject via `st.markdown()` with `unsafe_allow_html=True`
- Import DM Sans from Google Fonts in CSS
- Override Streamlit's default theme to match: set background to #FAFBFC, hide default hamburger menu
- Use `.stButton > button` selectors to style buttons
- The hero banner will need to be a full-width HTML block injected at the top

### Component Mapping
- Hero → `st.markdown()` with full HTML/CSS block
- Text inputs → `st.text_input()` styled via CSS overrides
- Mode cards → likely need to be custom HTML with `st.components.v1.html()` or `st.markdown()` with click handlers via Streamlit's `st.session_state`
- Toggle → `st.radio()` styled as toggle, or custom component
- Textarea → `st.text_area()` styled via CSS
- Signal tags → `st.markdown()` with inline HTML
- CTA → `st.button()` styled via CSS

### Streamlit Constraints
- Streamlit re-renders on every interaction — use `st.session_state` to persist mode selection, company type, and form values
- The analysis mode cards with conditional textarea may be simplest as: `st.radio()` for mode selection (styled as cards via CSS) + conditional `st.text_area()` 
- The company type toggle may be simplest as: `st.radio()` with horizontal layout, styled via CSS to look like a toggle
- If the card-based mode selector is too complex in pure Streamlit, fall back to a horizontal `st.radio()` with description text below — the key UX requirement is that the description appears BEFORE the user selects, not after

### What NOT to Do
- Do NOT use Streamlit's dark theme — force light theme
- Do NOT use Streamlit's default sidebar — this design has no sidebar
- Do NOT use default Streamlit component spacing — override with CSS
- Do NOT use blue as an accent color anywhere — the palette is navy/teal/coral only

## Files to Reference
- `nst-start-screen.html` — the exact reference implementation (open in browser)
- Project A's `src/ui/styling.py` — reuse the CSS injection pattern and brand constants
- Project A's `src/ui/components.py` — reuse the hero banner component pattern
