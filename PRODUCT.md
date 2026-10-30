# Product
<!-- impeccable:product-schema 1 -->

## Purpose

ESL Hub is a private, self-hosted dashboard that turns household data into glanceable updates on 4.2-inch Rainus electronic shelf labels. It also provides one management webpage for configuration, manual updates, and recent run logs.

## Users

- The owner configures integrations, schedules, tags, and layouts.
- Household members read the physical displays at a glance.

## Product context

- The Raspberry Pi deployment is the runtime source of truth.
- Displays cover fitness, Dota 2, weather, Formula 1, energy, family calendar, Mercedes listings, and Microsoft To Do.
- The Microsoft To Do browser and display controller use the same read-only Microsoft Graph connection.
- The management webpage is an operational tool, not a replacement for the source services.

## Experience principles

- Make the most important state understandable in a few seconds.
- Preserve the established management flow across display types.
- Keep credentials and private item content out of logs and source control.
- Make disabled or incomplete integrations safe by default.
- Prefer explicit labels and useful status text over decorative controls.

## Technical constraints

- Physical tags are 400 by 300 pixels and support black, white, and red.
- The gateway expects a 250-entry `prInfo` array, with layout fields mapped to fixed register indexes.
- Runtime configuration and credentials live in the gitignored `config.json` file.
- A controller must not publish until its display tag ID is configured.

## Current evidence

- The connected Microsoft To Do account currently has more active tasks than fit on one display.
- Most tasks do not have due dates, priorities, recurrence, or categories.
- A list-oriented summary is therefore the strongest default, with task-oriented alternatives available through the same controller payload.

## Open decisions

- Select the first Microsoft To Do tag layout from the proposed display concepts.
- Add the new physical display tag ID.

## RonHub management scope

The homepage prioritizes quick health checks and fixing failures across five
systems: ESL Home Hub, the Zectrix Note 4C Family Calendar, Insignia Facebook
Notifications, Reddit Unban, and Shambu Local GPU access over Tailscale.
The Pi remains authoritative for the live deployment. Calendar control is a
separate Pi service; Insignia runs in Azure; Reddit and GPU telemetry arrive
through the Windows status bridge. Existing schedules and controller behavior
are preserved. Future systems join through a shared registry and status adapter.

The interface uses explicit status labels and observation times. Stale telemetry,
failed work, paused schedules, and quiet hours are separate states. The layout
adapts to desktop and mobile while keeping controls and active selections stable.
