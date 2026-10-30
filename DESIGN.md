---
name: RonHub
description: A calm household service book for checking health and fixing failures.
colors:
  canvas: "#fbfcfa"
  rail: "#f1f3ef"
  panel: "#fff"
  ink: "#25372f"
  muted: "#64716a"
  line: "#dfe5de"
  soft: "#f5f7f3"
  green: "#245648"
  green-soft: "#e3eee6"
  green-hover: "#183f33"
  focus: "#3d7966"
  amber: "#8d531a"
  amber-soft: "#fbf3e7"
  red: "#a43f35"
  red-soft: "#faeeeb"
  blue: "#345d81"
  blue-soft: "#edf3f9"
  healthy: "#386747"
  healthy-soft: "#eaf3ec"
  badge-neutral: "#5c6a61"
  badge-neutral-soft: "#edf0ec"
typography:
  display:
    fontFamily: "Inter, sans-serif"
    fontSize: "32px"
    fontWeight: 620
    lineHeight: 1.25
    letterSpacing: "-.025em"
  headline:
    fontFamily: "Inter, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-.015em"
  detail:
    fontFamily: "Inter, sans-serif"
    fontSize: "23px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-.015em"
  title:
    fontFamily: "Inter, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Inter, sans-serif"
    fontSize: "12px"
    fontWeight: 550
    lineHeight: 1.5
  metadata:
    fontFamily: "Inter, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.5
  metric:
    fontFamily: "Inter, sans-serif"
    fontSize: "30px"
    fontWeight: 550
    lineHeight: 1.5
  log:
    fontFamily: "Consolas, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.7
rounded:
  panel: "14px"
  control: "7px"
  navigation: "8px"
  badge: "5px"
  tab: "6px"
  empty: "12px"
  device: "16px"
  toast: "9px"
spacing:
  tight: "8px"
  compact: "12px"
  inset: "18px"
  mobile-gutter: "20px"
  panel: "22px"
  inner: "24px"
  narrow-gutter: "26px"
  heading: "28px"
  section: "30px"
  form: "32px"
  desktop-gutter: "40px"
components:
  button-primary:
    backgroundColor: "{colors.green}"
    textColor: "{colors.panel}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 13px"
  button-primary-hover:
    backgroundColor: "{colors.green-hover}"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 13px"
  button-secondary-hover:
    backgroundColor: "{colors.soft}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 13px"
  button-quiet-hover:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.ink}"
  field:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 11px"
  navigation-active:
    backgroundColor: "{colors.green-soft}"
    textColor: "{colors.green}"
    rounded: "{rounded.navigation}"
    padding: "11px 13px"
  badge-healthy:
    backgroundColor: "{colors.healthy-soft}"
    textColor: "{colors.healthy}"
    rounded: "{rounded.badge}"
    padding: "4px 7px"
  badge-warning:
    backgroundColor: "{colors.amber-soft}"
    textColor: "{colors.amber}"
    rounded: "{rounded.badge}"
    padding: "4px 7px"
  badge-error:
    backgroundColor: "{colors.red-soft}"
    textColor: "{colors.red}"
    rounded: "{rounded.badge}"
    padding: "4px 7px"
  badge-running:
    backgroundColor: "{colors.blue-soft}"
    textColor: "{colors.blue}"
    rounded: "{rounded.badge}"
    padding: "4px 7px"
  badge-neutral:
    backgroundColor: "{colors.badge-neutral-soft}"
    textColor: "{colors.badge-neutral}"
    rounded: "{rounded.badge}"
    padding: "4px 7px"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "22px"
  health-summary:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "19px 22px"
  system-row:
    textColor: "{colors.ink}"
    padding: "20px 3px"
  activity-row:
    textColor: "{colors.ink}"
    padding: "13px 2px"
---

# Design System: RonHub

## Overview

**Creative North Star: "The Household Service Book"**

RonHub uses warm white space, pale stone navigation, and deep evergreen controls to make household systems readable at a glance. The character is calm, compact, and practical. Clear names, aligned values, and short descriptions carry the interface.

The world is built from typography, thin rules, native SVG line icons, and restrained surfaces. Spacing separates tasks without turning every section into a card. Color points to a current location, a useful action, or a measured state. Controls and live information remain stable while someone reads, selects text, or edits settings.

**Key Characteristics:**

- Warm neutral surfaces with evergreen navigation and actions.
- Compact Inter typography with tabular timestamps and measurements.
- Open lists for systems and activity, bordered panels for related facts.
- Written status, visible freshness, and specific recovery actions.
- Stable interaction during automatic status refreshes.

## Colors

The palette combines warm neutral surfaces with evergreen controls and restrained semantic state colors. The frontmatter is the normative source for color values; names below explain their use.

### Primary

- **Deep Evergreen** (`green`): primary actions, links, active navigation text, input accents, and selected text backgrounds.
- **Evergreen Wash** (`green-soft`): selected navigation and display tabs.
- **Deep Evergreen Hover** (`green-hover`): the primary button hover state.
- **Focus Evergreen** (`focus`): the shared visible keyboard outline.

### Secondary

- **Rust** (`red`, `red-soft`): errors and unreachable systems, with a pale surface behind the written status.
- **Amber** (`amber`, `amber-soft`): warnings, recovery notices, and connection alerts.
- **Slate Blue** (`blue`, `blue-soft`): an update currently running.
- **Leaf Green** (`healthy`, `healthy-soft`): confirmed healthy status badges.

### Neutral

- **Warm Canvas** (`canvas`): the page background.
- **Pale Stone** (`rail`): the persistent navigation region.
- **White Panel** (`panel`): controls and bounded supporting information.
- **Soft Stone** (`soft`): health summaries, subtle hover surfaces, and subdued supporting blocks.
- **Evergreen Ink** (`ink`): primary text.
- **Muted Sage Ink** (`muted`): secondary descriptions, labels, and timestamps.
- **Stone Rule** (`line`): one-pixel boundaries and dividers.
- **Neutral Status** (`badge-neutral`, `badge-neutral-soft`): unverified, paused, and quiet-hour badges.

**The Written Status Rule.** Pair every status color with a readable state or an accessible label. Distinguish healthy, needs attention, unreachable, unverified, paused, quiet hours, and updating.

## Typography

**Display and body font:** Inter, self-hosted from `ronhub/static/fonts/InterVariable.woff2`, with `sans-serif` fallback. The source is the official `rsms/inter` project, distributed with the SIL Open Font License in `ronhub/static/fonts/LICENSE.txt`. The normal variable face supports weights 100 through 900, is preloaded, and uses `font-display: swap` with font synthesis disabled.

**Log font:** Consolas, with monospace fallback.

Inter supplies a compact, clear hierarchy rather than a decorative display treatment. Most operational labels are smaller than the body baseline, with spacing and weight separating names from supporting evidence. Paragraphs have a maximum width of 72 characters.

### Hierarchy

- **Display:** page titles use the `display` role, balanced wrapping, and a compact line height.
- **Headline:** section titles use the `headline` role. System detail titles use the larger `detail` role.
- **Title:** panel headings use the `title` role. System names use a smaller, semibold treatment (13px, weight 600).
- **Body:** the base document uses `body`; descriptive panel and form text commonly uses 12px.
- **Label:** buttons use `label`; state badges use 11px at weight 550. Secondary metadata uses the `metadata` role.
- **Metric:** prominent GPU measurements use `metric`; general inline measurements use 20px at weight 550.
- **Log:** run output uses `log`, preserves line breaks, and wraps long content.

**The Aligned Evidence Rule.** Use tabular numerals for measurements, fact values, and timestamps. Keep monospace reserved for run output.

At the mobile breakpoint, page titles become 27px, detail titles become 21px, and section headings become 16px. Badges become 10px. These are explicit responsive adjustments, not a fluid type scale.

## Layout

The desktop shell uses a fixed left rail (248px) and a matching workspace offset. Its top bar is 70px high. Main content is centered within a maximum width of 1540px, with 36px top padding and 40px horizontal and bottom padding.

The reusable spatial pattern is a flexible working column and a narrower supporting column. Overview uses a 285px supporting column and a 30px gap. Detail pages use a 300px supporting column; forms use 290px with a 32px gap. Forms stop at 780px, with two field columns and 20px between fields. Sections are typically separated by 30px.

System rows align icon, name and host, status, next action, and a chevron. Their names can wrap without displacing the status. Activity rows use a flexible description followed by a timestamp and disclosure indicator. Fact lists pair a muted label with a right-aligned value.

| Viewport rule | Applied behavior |
| --- | --- |
| At least 1600px | Main top padding becomes 44px; overview support width becomes 310px with a 36px gap; system rows gain 23px vertical padding. |
| At most 1220px | Rail and workspace offset become 220px; page gutters become 26px; support columns become 250px; system rows hide the next-action column. |
| At most 1000px | Overview, detail, form, and calendar layouts become one main column. Overview support content and calendar supporting sections can form two columns. |
| At most 760px | The rail becomes a top header with a Menu disclosure; workspace offset becomes zero; gutters become 20px; fields and supporting sections become one column. Tabs can scroll horizontally. |

The calendar preview and its details use a dedicated two-column arrangement on wide screens, then stack. The device image keeps its 4:3 aspect ratio and scales inside a 426px maximum-width frame. Event information remains available as text below it.

## Elevation & Depth

Tonal layering and fine borders establish depth. System lists, activity, and facts sit directly on the canvas. Panels have no resting shadow. Diffuse elevation appears on temporary feedback and the physical calendar frame.

### Shadow Vocabulary

- **Toast elevation** (`0 10px 30px #25372f14`): separates a temporary status message from the page.
- **Device elevation** (`0 7px 20px #2f403325`): gives the calendar frame a restrained physical presence.

**The Quiet Depth Rule.** Use borders and tone for ordinary information. Reserve diffuse shadows for temporary feedback and the calendar device frame.

## Shapes

Large bounded surfaces use the panel radius. Controls use the smaller control radius; navigation, tabs, badges, and feedback each retain their own compact rounding. System rows remain rectangular and are separated by one-pixel rules. Status dots are circular; they accompany text rather than replace it.

Icons are native inline SVG with no fill, rounded caps and joins, and a 1.65px stroke. The usual icon box is 20px; button and tab icons are 16px. The house mark is also SVG. Keep icons legible, simple, and subordinate to names.

The calendar image is live output from the existing controller. Its four-color rendering belongs to the device, while the surrounding frame follows RonHub's neutral materials.

## Components

### Buttons

Compact controls use a minimum height of 38px, the control radius, and the padding in the frontmatter. Primary buttons use evergreen with white text. Secondary buttons use a white surface and a fine border. Quiet buttons have transparent surfaces and muted text.

Hover changes background and border color over 160ms with `ease-out`. The shared keyboard focus treatment is a 2px evergreen outline with a 4px offset. Disabled buttons use 0.55 opacity and a wait cursor. Run and save actions change their text while pending. Small controls have a 31px minimum height; page heading controls use a 35px minimum at the mobile breakpoint.

### Status Badges and Health Summaries

Badges are compact written states with a small dot. Healthy, warning, error, running, and neutral treatments are distinct. A summary combines a shield or warning icon, a direct sentence, freshness text, and either a badge or aggregate metadata.

Pauses and scheduled quiet hours have their own labels. Missing evidence reads as unverified or unavailable. Errors carry an explanation and a route to a relevant control or recovery page.

**Freshness and evidence.** Present health as observed evidence with its timestamp. A successful page render does not establish system health, and a historical retry must not be labeled as an upcoming run.

The overview refreshes system state every 20 seconds, with retries backing off to 60 seconds. The Local GPU page also fetches its report every five seconds while visible. Its companion checks become stale after the report's 65-second freshness budget; GPU measurements expire after 15 seconds. Preserve the distinction between connection readiness, idle Ollama, measured GPU use, and recorded activity.

### Cards and Containers

Panels use white backgrounds, thin stone borders, the panel radius, and 22px padding. Host panels use 21px padding. Mobile panels use 19px, while host panels retain 20px. Use bounded panels for a coherent set of facts or supporting controls; retain open rows for repeated systems and runs.

Issue containers have a pale warm background, an amber-tinted outline, and separated rows. Empty states use a dashed border and direct text. Initial loading uses static soft blocks. Connection failure retains the last received state and adds a persistent alert with its timestamp and a recovery action.

### Inputs and Fields

Fields use visible labels, white backgrounds, fine borders, the control radius, and a 40px minimum height. Inputs use 13px text and the field padding in the frontmatter. Supporting instructions use 11px muted text. Native checkboxes, select controls, and time fields keep their familiar interaction.

Hover strengthens the border; keyboard focus uses the shared outline. Save feedback appears in a dedicated status message, with error text colored rust. Native required and numeric constraints remain in effect. Password fields describe whether a credential is saved and leave existing values intact when no replacement is entered.

### Navigation

The main rail groups Overview, five systems, and Hub settings. Its active link uses the evergreen wash, evergreen text, a slightly stronger icon stroke, and `aria-current="page"`. Links have a 46px minimum height with generous horizontal padding.

On mobile, a labeled Menu button controls the navigation disclosure and exposes its expanded state. ESL display navigation uses horizontally scrollable links. Project views use underlined text links. Both identify the current page with `aria-current`.

Use real links for routes, real buttons for commands, and labeled navigation landmarks. Client navigation updates the document title and breadcrumb, closes the mobile menu, and moves focus to the main region. A skip link precedes navigation.

### System Rows, Facts, and Run History

Every system uses the same name, host, health, and next-action vocabulary. Supporting facts use definition lists. Run history uses native `details` and `summary` elements so output can be inspected with a keyboard. Expanded logs use a bounded, scrollable preformatted area with long-line wrapping.

The Local GPU view follows the same structure for Shambu: live load and memory, connection checks, model availability, remote access, and observed Ollama activity. Activity bars describe recorded hourly windows and have an accessible summary. The empty state explains what evidence is awaited.

### Live Updates and Feedback

**Stable interaction.** Continue fetching status while a person interacts, but defer replacing the current page while a control has focus or text is selected. Resume after interaction ends.

Forms, the embedded calendar controller, and task lists remain mounted across background refreshes. Open run disclosures and scroll position survive ordinary renders. Explicit navigation resets the view. Unsaved changes are protected before navigation, reloading settings, or leaving the page.

Toast feedback uses a polite status region. Persistent connection errors use an alert. Loading state is exposed through `aria-busy`; decorative icons are hidden from assistive technology. The calendar image has descriptive alternative text and a text event list. Percentage host meters expose their label, value, and range.

Motion stays limited to state feedback: background and color transitions, plus a rotating disclosure chevron. Under `prefers-reduced-motion: reduce`, transitions and animations are disabled and scroll behavior becomes automatic.

## Do's and Don'ts

### Do:

- Do use the current CSS values and semantic roles in the frontmatter when extending the interface.
- Do pair status color with words, include freshness, and give failures a relevant next action.
- Do keep system names, timestamps, and fact values aligned across all five system pages.
- Do retain keyboard focus, selected text, form edits, open run output, and scroll position during background refreshes.
- Do use the self-hosted Inter face, tabular evidence, and native SVG icons.
- Do preserve the calendar controller's live image and provide its event information as text.
- Do honor reduced motion and use semantic links, buttons, labels, and disclosures.
- Do write direct interface copy using commas, periods, colons, parentheses, or hyphens.

### Don't:

- Don't infer health from a rendered page, hide missing evidence behind a healthy badge, or present an expired retry as a future action.
- Don't replace focused controls or selected content during automatic refreshes.
- Don't turn every list row or section into a shadowed card.
- Don't use color or an unlabeled icon as the only explanation of a state or command.
- Don't use decorative imagery to replace operational evidence.
- Don't use em dashes in interface copy or documentation.
