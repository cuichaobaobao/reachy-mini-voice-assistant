# Changelog

All notable changes to Reachy Mini HA Voice are documented here.

## [1.1.2] - 2026-07-18

### Fixed
- Fill each 512-sample MicroWakeWord audio block from multiple Reachy Mini SDK microphone chunks when necessary, preventing gaps that could stop local wake-word detection.
- Preserve the existing dual-channel Home Assistant audio path and all other voice-assistant behavior.

## [1.1.1] - 2026-07-02

### Changed
- Replace bundled Okay Nabu, Hey Mycroft, Hey Jarvis, and Stop MicroWakeWord files with the current Linux Voice Assistant model files.
- Add optional dual-channel Voice Assistant audio forwarding when the installed ESPHome protocol supports `data2`.
- Keep channel 1 as the wake/stop detection path while forwarding channel 2 as an echo-cancellation reference for Home Assistant.
- Remove remaining old app identity wording from user-facing documentation.

## [1.1.0] - 2026-06-24

### Added
- Start the project as `reachy-mini-ha-voice` with the Python package `reachy_mini_ha_voice`.
- Provide ESPHome auto-discovery for Home Assistant on port 6053.
- Keep the tuned Reachy Mini motion system: official-style 60Hz control, breathing, antenna motion, generated idle micro-actions, listening/thinking/speaking states, emotion moves, DOA wake turns, manual head yaw hold, and body-yaw follow.
- Keep the OHF/Linux Voice inspired MicroWakeWord setup with Okay Nabu, Hey Mycroft, Hey Jarvis, and Stop.
- Keep Home Assistant voice pipeline integration for STT, conversation, TTS, media-player volume, mute, continuous conversation, and wake/stop sensitivity controls.

### Changed
- Rebrand Home Assistant device metadata to the clean `ReachyMini.HAVoice` identity.
- Trim the Home Assistant entity surface to the controls and diagnostics that are useful day to day.
- Keep internal robot capabilities available while removing noisy HA-facing entities such as Head X/Y/Z, raw IMU acceleration/gyro axes, Speech Detected, and Services Suspended.

### Removed
- Remove the previous package identity from package metadata, app entry point, README tags, and user-facing documentation.
- Remove robot-side video/camera features from the app scope; external RTSP remains handled by the separate Mac bridge.
