# Reachy Mini Voice Assistant - Project Summary

Reachy Mini Voice Assistant is a Home Assistant voice companion app for Reachy Mini.
It runs on the robot, exposes an ESPHome-compatible voice satellite, and keeps
the motion behavior we tuned for a more alive, less mechanical personality.

## Runtime Scope

- ESPHome protocol server on port 6053 with mDNS auto-discovery.
- Local MicroWakeWord detection for Okay Nabu, Hey Mycroft, Hey Jarvis, and Stop.
- Home Assistant pipeline for STT, conversation, TTS, timers, and media playback.
- Reachy Mini motion feedback for wake, listening, thinking, speaking, timers,
  emotions, idle breathing, generated idle micro-actions, and DOA wake turns.
- Optional SDK face tracking during listening and thinking, with a private
  rate-limited JPEG frame source for local voice vision.

## Home Assistant Entity Surface

The ESPHome device publishes only voice-satellite settings: mute, continuous
conversation, two wake-word thresholds, stop-word threshold, and media player.
The official Reachy Mini Home Assistant integration owns robot controls,
camera, daemon diagnostics, DOA visibility, volume, and recorded moves.

## Motion Policy

The app follows the current official Reachy Mini conversation style where it matters:

- 60Hz motion control cadence.
- Official-style idle breathing and antenna layer.
- SDK-driven speaking wobble.

It also keeps the behavior tuned for this project:

- Generated idle micro-actions instead of a simple fixed loop.
- DOA-based wake orientation.
- Listening/thinking/speaking personality states.

## Out Of Scope

This app does not publish camera or RTSP entities. It can privately use SDK
JPEG frames and face tracking when `REACHY_VISION_FACE_TRACKING_ENABLED=true`.
Camera publication remains the official integration's responsibility.
