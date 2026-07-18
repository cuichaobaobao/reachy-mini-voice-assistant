# Release Audit Plan

## Goal

Prepare `reachy_mini_ha_voice` version 1.1.1 for publication after the
identity migration, voice-surface reduction, SDK 1.9 alignment, and optional
private vision work.

## Approach

1. Verify the current repository state, package metadata, app entry point, and
   GitHub/Hugging Face remotes.
2. Run full static checks and correct code-quality issues without changing the
   intended Home Assistant control boundary.
3. Run the complete test suite and build a wheel to verify installable assets
   and metadata.
4. Inspect the staged change set, commit the complete migration, and push it to
   the configured GitHub and Hugging Face remotes.

## Confirmed Direction

- This is an on-robot Python voice app, so the Python application path is the
  appropriate official flavour.
- The app retains only voice-satellite entities; the official Home Assistant
  integration owns manual robot controls, camera publication, and daemon
  diagnostics.
- Physical hardware acceptance remains a post-push requirement documented in
  `docs/HARDWARE_ACCEPTANCE.md`.
