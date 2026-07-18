# Reachy Mini Hardware Acceptance

Run this checklist on a Reachy Mini with daemon and SDK version 1.9.0 or newer.
Do not publish, tag, or sync the project until every required check passes.

## Before Starting

1. Install the official `reachy_mini_homeassistant` integration and confirm it owns robot controls, camera, daemon status, volume, and recorded moves.
2. Install this app and select `reachy_mini_ha_voice` as the Reachy Mini app.
3. Add the discovered ESPHome voice device in Home Assistant on port `6053`.
4. Confirm that this device publishes only media player, mute, continuous conversation, and wake/stop sensitivity settings.

## Required Voice Checks

1. Confirm `okay_nabu`, `hey_mycroft`, and `hey_jarvis` each start a Home Assistant voice request.
2. Confirm another wake model cannot be selected or detected.
3. During TTS, say `stop` and confirm playback ends promptly; it must not start a new request.
4. Confirm mute suspends local wake detection and unmute restores it.
5. Confirm continuous conversation returns to listening without a new wake word.

## Required Motion Checks

1. Observe listening, thinking, and speaking states during a complete request.
2. Speak from two different directions and confirm DOA turns toward the source without oscillation.
3. After the request, confirm the head/body posture returns smoothly and remains stable.
4. Leave the robot idle long enough to observe breathing, neutral antenna motion, and a generated idle action.
5. Trigger an emotion through the existing voice behavior and confirm it completes before normal idle motion resumes.

## Optional Vision Checks

Set `REACHY_VISION_FACE_TRACKING_ENABLED=true` and
`REACHY_VISION_JPEG_ENABLED=true`, restart the app, then confirm:

1. The SDK camera frame probe succeeds in the app log.
2. Head tracking runs only while listening or thinking.
3. Head tracking stops before speaking and while idle.
4. The official integration remains the only Home Assistant camera entity; this app must not add RTSP, a camera entity, or manual vision controls.

## Evidence To Record

Record the robot SDK version, app version, Home Assistant version, a short log excerpt for startup and one successful request, and any observed motion or audio issue. Mark the release ready only when all required checks pass.
