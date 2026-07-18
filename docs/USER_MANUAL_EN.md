# Reachy Mini Voice Assistant User Manual

## Installation

Install `reachy_mini_ha_voice` from the Reachy Mini app store. When started, it runs an ESPHome-compatible voice satellite on the robot.

Home Assistant should usually discover a new ESPHome device automatically:

- Name: `Reachy Mini Voice Assistant ******`
- Port: `6053`
- Manufacturer: `Reachy Mini Voice Assistant`
- Project: `ReachyMini.VoiceAssistant`

If discovery fails, add ESPHome manually in Home Assistant and enter the robot IP address with port `6053`.

## Voice

- Local MicroWakeWord wake words: Okay Nabu, Hey Mycroft, Hey Jarvis
- Local Stop word
- Home Assistant handles STT, conversation, and TTS
- Continuous conversation, mute, wake sensitivity, and stop sensitivity are exposed in Home Assistant

## Motion

The app keeps the tuned motion system:

- Official-style 60Hz motion control
- Official idle breathing and antenna motion
- SDK speaking wobbling
- Listening, thinking, speaking, and timer motions
- Realtime generated idle micro-actions
- DOA sound-source wake turns
- Optional SDK face tracking during listening and thinking

## Home Assistant Entities

### Controls

| Entity | Type | Description |
| --- | --- | --- |
| Mute | Switch | Pause/resume the voice pipeline |
| Continuous Conversation | Switch | Multi-turn conversation |

### Voice Tuning

| Entity | Type | Description |
| --- | --- | --- |
| Wake Word 1 Sensitivity | Number | First active wake word threshold |
| Wake Word 2 Sensitivity | Number | Second active wake word threshold |
| Stop Word Sensitivity | Number | Stop word threshold |

## Out Of Scope

This app does not publish robot controls, camera, daemon diagnostics, or recorded moves. Use the official Reachy Mini Home Assistant integration for those features. `REACHY_VISION_FACE_TRACKING_ENABLED=true` enables private SDK face tracking, while `REACHY_VISION_JPEG_ENABLED=true` enables private on-demand JPEG reads. `REACHY_VISION_JPEG_REFRESH_HZ=5` limits repeated reads but does not start a capture loop. The app still does not expose another camera entity or RTSP stream.
