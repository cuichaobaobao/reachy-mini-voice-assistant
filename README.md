---
title: Reachy Mini Voice Assistant
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: static
pinned: false
short_description: Reachy Mini voice companion for Home Assistant
tags:
  - reachy_mini
  - reachy_mini_python_app
  - reachy_mini_ha_voice
  - home_assistant
  - homeassistant
---

# Reachy Mini HA Voice

Reachy Mini HA Voice turns Reachy Mini into a Home Assistant voice companion.
It runs directly on the robot, exposes an ESPHome-compatible voice satellite,
keeps local wake/stop detection, and drives Reachy Mini motion so voice
interactions feel alive instead of static.

This is a clean project with its own package and app identity:

- Python distribution: `reachy-mini-ha-voice`
- Python package: `reachy_mini_ha_voice`
- Reachy Mini app entry point: `reachy_mini_ha_voice`
- Home Assistant device family: `Reachy Mini Voice`

## Highlights

- ESPHome auto-discovery for Home Assistant on port `6053`
- Local MicroWakeWord wake detection
- Wake words: Okay Nabu, Hey Mycroft, Hey Jarvis
- Local Stop word during TTS
- Home Assistant STT, conversation, and TTS pipeline integration
- Continuous conversation support
- DOA sound-source wake turns
- Tuned Reachy motion: listening, thinking, speaking, timers, emotions, idle breathing, antennas, and generated idle micro-actions
- Official-style 60Hz motion control and SDK speaking wobble
- Optional private SDK face tracking during listening/thinking
- Private rate-limited JPEG frame source; no additional camera entity

## Home Assistant Setup

1. Install the official `reachy_mini_homeassistant` integration for robot controls, camera, daemon status, and recorded moves.
2. Install and start this app on Reachy Mini.
3. Configure it as the daemon's default app if you want v1.9 antenna-touch and boot startup.
4. In Home Assistant, open **Settings → Devices & Services**.
5. Accept the discovered ESPHome device, or add ESPHome manually.
6. If adding manually, use the robot IP address and port `6053`.

The discovered device should use metadata similar to:

- Manufacturer: `Reachy Mini HA Voice`
- Model: `Reachy Mini Voice Satellite`
- Project: `ReachyMini.HAVoice`

If you previously used an older app identity, remove the old ESPHome device from
Home Assistant first, then add the newly discovered device.

## Home Assistant Entities

This app publishes only voice-satellite settings:

- Mute and continuous conversation
- Wake word slot 1, wake word slot 2, and stop-word sensitivity
- The standard ESPHome media player

Install the official Reachy Mini Home Assistant integration for all robot
controls, camera, daemon diagnostics, DOA visibility, and emotion/dance moves.

## Motion Design

The motion system follows the current official Reachy Mini conversation style
where it matters:

- 60Hz control loop
- official-style idle breathing and antenna motion
- SDK-driven speaking wobble

It also preserves the behavior tuned for this project:

- generated idle micro-actions instead of a simple repeated loop
- DOA-based wake orientation
- listening/thinking/speaking personality states
- delayed idle rest behavior when idle motion is disabled
- optional SDK face tracking during listening and thinking

## Voice Design

The voice pipeline follows the same broad shape as Linux Voice Assistant style
setups:

- local lightweight wake/stop detection
- Home Assistant handles STT, intent/conversation, and TTS
- Stop remains available during TTS
- sensitivity controls map to active wake-word slots

## Video

This app does not publish a camera or RTSP video. Vision has independent,
disabled-by-default switches:

- `REACHY_VISION_FACE_TRACKING_ENABLED=true` enables SDK face tracking during
  listening and thinking.
- `REACHY_VISION_JPEG_ENABLED=true` permits on-demand private JPEG reads.
- `REACHY_VISION_JPEG_REFRESH_HZ=5` limits repeated reads to 5Hz; it does not
  start a continuous capture loop.

Camera publication remains the official Reachy Mini Home Assistant
integration's responsibility.

## Hardware Acceptance

Use the [hardware acceptance checklist](docs/HARDWARE_ACCEPTANCE.md) on a
physical robot before publishing or synchronizing a release.

## Development

```bash
python -m compileall reachy_mini_ha_voice
python -m unittest discover -s tests
```

The project targets Python 3.12 and Reachy Mini SDK 1.9.0 or newer.

## Release

Version history starts at `1.1.0` for this clean project identity. See
[CHANGELOG.md](CHANGELOG.md).
