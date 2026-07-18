# Handoff Summary - Reachy Mini HA Voice

Last updated: 2026-07-18

## Current State

This workspace is a clean, renamed Reachy Mini Home Assistant voice app project.
It is no longer intended to present itself as the old fork/custom app.

Current local project identity:

- Python distribution: `reachy-mini-ha-voice`
- Python package: `reachy_mini_ha_voice`
- Reachy Mini app entry point: `reachy_mini_ha_voice`
- Version: `1.1.1`
- Requires Python: `>=3.12`
- Requires Reachy Mini SDK: `reachy-mini>=1.9.0`

Home Assistant ESPHome discovery metadata should be:

- Manufacturer: `Reachy Mini HA Voice`
- Model: `Reachy Mini Voice Satellite`
- Project: `ReachyMini.HAVoice`

Important: do not push to GitHub or sync to Hugging Face until robot-side testing is complete.

## User Intent

The user wants this to become a clean first-party project, not a visible fork.
Keep the behavior that was tuned over many rounds:

- listening motion
- thinking motion
- speaking motion
- DOA sound-source turning
- posture hold
- posture return
- random generated idle motion
- emotion moves
- continuous conversation
- local wake-word and stop-word detection
- Home Assistant STT / conversation / TTS
- external RTSP video bridge remains separate from this app

Do not reintroduce robot-side camera / RTSP publishing into this app.

## Project Structure

Root files:

- `pyproject.toml`: package metadata, dependencies, entry point, ruff/mypy config
- `README.md`: public project overview and setup
- `CHANGELOG.md`: release notes
- `changelog.json`: app changelog metadata
- `Project_Summary.md`: compact project summary
- `index.html`, `style.css`: Hugging Face Space landing page
- `docs/USER_MANUAL_CN.md`: Chinese user manual
- `docs/USER_MANUAL_EN.md`: English user manual
- `docs/HARDWARE_ACCEPTANCE.md`: physical robot acceptance checklist
- `tests/`: local unit tests

Main package:

- `reachy_mini_ha_voice/main.py`: Reachy Mini app entry class
- `reachy_mini_ha_voice/voice_assistant.py`: main voice service and wake/stop handling
- `reachy_mini_ha_voice/models.py`: shared runtime state and config models
- `reachy_mini_ha_voice/reachy_controller.py`: read-only DOA helper for local wake turns
- `reachy_mini_ha_voice/core/`: config, service base, daemon/robot monitors, utilities
- `reachy_mini_ha_voice/protocol/`: ESPHome protocol, satellite flow, message dispatch, zeroconf
- `reachy_mini_ha_voice/entities/`: HA entity definitions and runtime entity setup
- `reachy_mini_ha_voice/audio/`: local audio helpers, DOA tracker, playback adapters
- `reachy_mini_ha_voice/motion/`: movement manager, idle runtime, command runtime, smoothing, pose composing
- `reachy_mini_ha_voice/animations/`: animation config and conversation animation data
- `reachy_mini_ha_voice/wakewords/`: bundled MicroWakeWord models
- `reachy_mini_ha_voice/sounds/`: bundled local notification sounds
- `reachy_mini_ha_voice/vision.py`: private SDK JPEG frame source for optional face tracking

Removed/cleaned:

- old package `reachy_mini_home_assistant/`
- bundled static web UI under the new package
- unused Home Assistant blueprint folder
- OpenWakeWord / `hey_reachy` assets
- old fork/custom/lichao622 user-facing identity
- old 50Hz/100Hz motion wording

## Dependencies

The app is defined in `pyproject.toml`.

Key runtime dependencies:

- `reachy-mini>=1.9.0`
- `aioesphomeapi>=43.10.1`
- `pymicro-wakeword>=2.0.0,<3.0.0`
- `numpy==2.2.5`
- `soundfile>=0.13.0`
- `scipy>=1.15.3,<2.0.0`
- `zeroconf<1`
- `websockets>=12,<16`

The project now targets Python 3.12. This avoids the earlier dependency conflict where `aiosendspin` required Python 3.12 while the project allowed older Python versions.

## Voice Model State

Bundled wake/stop models are MicroWakeWord models aligned with current Linux Voice Assistant assets:

- `okay_nabu.json` / `okay_nabu.tflite`
- `hey_mycroft.json` / `hey_mycroft.tflite`
- `hey_jarvis.json` / `hey_jarvis.tflite`
- `stop.json` / `stop.tflite`

Active bundled wake IDs:

```python
("okay_nabu", "hey_mycroft", "hey_jarvis")
```

Current probability cutoffs:

- Okay Nabu: `0.85`
- Hey Mycroft: `0.95`
- Hey Jarvis: `0.97`
- Stop: `0.5`

The voice pipeline supports optional ESPHome `VoiceAssistantAudio.data2` when the installed `aioesphomeapi` supports it. Channel 1 is used for local wake/stop detection; optional channel 2 can be forwarded to Home Assistant for AEC/reference use.

## Motion State

Motion is intentionally aligned with the official Reachy Mini conversation app where it matters:

- control loop default: `60Hz`
- `Config.motion.control_rate_hz = 60.0`
- `Config.motion.control_interval = 1.0 / 60.0`
- `DEFAULT_CONTROL_LOOP_FREQUENCY_HZ = 60`
- neutral antenna position follows official-style breathing baseline
- SDK speaking wobble is used through `reachy_mini.enable_wobbling()`

Project-specific tuned behavior is still kept:

- listening state
- thinking state
- speaking state
- emotion moves
- DOA wake orientation
- body-yaw follow
- generated random idle micro-actions
- delayed idle rest when idle motion is disabled

Known nuance:

- Official conversation source still has some stale comments that mention 100Hz, but the executable constant checked from upstream is 60Hz. This project follows the actual 60Hz behavior.

## Home Assistant Surface

The voice app publishes only satellite settings: mute, continuous conversation,
two wake-word thresholds, stop-word threshold, and the ESPHome media player.

Install the official `reachy_mini_homeassistant` integration for all robot
controls, camera, daemon diagnostics, DOA visibility, volume, and recorded
emotion/dance moves. This prevents two HA integrations from competing for the
same robot control surface.

## v1.9 Vision

The app now requires SDK 1.9 or newer and can use its private vision APIs:

- `REACHY_VISION_FACE_TRACKING_ENABLED=true` enables SDK head tracking only
  during listening and thinking; it automatically yields to speaking, idle,
  and emotion motion.
- `REACHY_VISION_JPEG_ENABLED=true` enables private, on-demand JPEG reads.
- `REACHY_VISION_JPEG_REFRESH_HZ=5` limits repeated internal
  `media.get_frame_jpeg()` calls; it does not create a capture loop, HA camera
  entity, or RTSP stream.

## External RTSP Video

Video is not part of this app.

The external RTSP bridge is a separate Mac-side service:

- Mac local controller endpoint: `http://192.168.50.63:18765/start`
- Mac local controller endpoint: `http://192.168.50.63:18765/stop`
- MediaMTX publishes: `rtsp://127.0.0.1:8554/reachy` on Mac
- HA can use the Mac IP form: `rtsp://192.168.50.63:8554/reachy`

Do not merge that bridge back into this app. Keeping it separate avoids camera/audio contention on the robot.

## Local Commands

Run from:

```bash
/Users/lichao/Documents/reachy-mini-ha-custom
```

Compile:

```bash
python3 -m compileall reachy_mini_ha_voice
```

Run unit tests:

```bash
env UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests
```

Import and model probe:

```bash
env UV_CACHE_DIR=.uv-cache uv run python - <<'PY'
import json
from pathlib import Path
import reachy_mini_ha_voice
from reachy_mini_ha_voice.main import ReachyMiniHaVoice
from reachy_mini_ha_voice.core.config import Config
from reachy_mini_ha_voice.motion.movement_manager import DEFAULT_CONTROL_LOOP_FREQUENCY_HZ
from aioesphomeapi.api_pb2 import VoiceAssistantAudio

print("version", reachy_mini_ha_voice.__version__)
print("entry", ReachyMiniHaVoice.__name__)
print("control_rate_hz", Config.motion.control_rate_hz)
print("control_interval", Config.motion.control_interval)
print("default_loop_hz", DEFAULT_CONTROL_LOOP_FREQUENCY_HZ)
print("data2", "data2" in VoiceAssistantAudio.DESCRIPTOR.fields_by_name)

for p in sorted(Path("reachy_mini_ha_voice/wakewords").glob("*.json")):
    data = json.loads(p.read_text())
    print(
        p.name,
        data.get("type"),
        data.get("wake_word"),
        data.get("micro", {}).get("probability_cutoff"),
        p.with_suffix(".tflite").stat().st_size,
    )
PY
```

Expected local verification from the latest run:

- `python3 -m compileall reachy_mini_ha_voice`: passed
- `uv run python -m unittest discover -s tests`: 38 tests passed
- version probe: `1.1.1`
- control rate probe: `60.0`
- default loop probe: `60`
- `data2`: available

## Robot Test Plan Before Push

Before pushing GitHub or syncing Hugging Face, test on the robot:

1. Install/update the app on Reachy Mini.
2. Start from the Reachy Mini desktop app.
3. Confirm the app starts without 400 error.
4. Confirm HA auto-discovers the new ESPHome device identity.
5. Remove old HA ESPHome device if old identity conflicts.
6. Confirm manual ESPHome add works with robot IP and port `6053`.
7. Test wake words:
   - Okay Nabu
   - Hey Mycroft
   - Hey Jarvis
8. Test `stop` during TTS.
9. Test streaming TTS with long response.
10. Test continuous conversation.
11. Test listening/thinking/speaking motion.
12. Test DOA sound-source turn.
13. Test posture hold and return.
14. Test random idle and emotion moves.
15. Test external RTSP bridge running at the same time.
16. Watch CPU/memory and daemon logs if antenna/head motion becomes jerky.

## Current Verification Snapshot

Latest local probe output:

```text
version 1.1.1
entry ReachyMiniHaVoice
control_rate_hz 60.0
control_interval 0.016666666666666666
default_loop_hz 60
data2 True
hey_jarvis.json micro Hey Jarvis 0.97 52272
hey_mycroft.json micro Hey Mycroft 0.95 57248
okay_nabu.json micro Okay Nabu 0.85 80824
stop.json micro Stop 0.5 45544
```

Latest local source-level verification on 2026-07-18:

```text
Ran 10 tests
OK
```

Full integration tests still require the project's Python 3.12 environment.

## Important Cautions

- Do not expose or repeat any Hugging Face token in logs or messages.
- Do not push or sync until the user confirms robot-side testing is stable.
- Do not re-add robot-side video publishing.
- Do not remove `custom_app_url` from `main.py`; it is a Reachy Mini SDK field and is intentionally set to `None`.
- If testing with `uv run` creates `.uv-cache`, `*.egg-info`, `__pycache__`, or `uv.lock`, clean them unless intentionally keeping a lockfile.

## Suggested First Message For A New Codex Session

Paste this into the new session:

```text
我们继续这个项目：/Users/lichao/Documents/reachy-mini-ha-custom

请先阅读 HANDOFF_SUMMARY.md、README.md、pyproject.toml，然后接着做第四阶段实机验证前的最终检查。不要推 GitHub，不要同步 Hugging Face，除非我明确说可以。

当前目标：
1. 这个项目已经改成新的 Reachy Mini HA Voice 身份。
2. 包名是 reachy_mini_ha_voice，版本 1.1.1。
3. 要保留听/思考/说话、DOA、姿态保持、姿态回正、随机 idle、情绪动作。
4. 语音模型要和 Linux Voice 的 MicroWakeWord 对齐，只保留 okay_nabu、hey_mycroft、hey_jarvis、stop。
5. 运动频率/呼吸/中性天线继续对齐官方 conversation app 的 60Hz 行为。
6. 外部 RTSP 视频桥是独立 Mac 服务，不要合并进 app。

请先检查 git 状态、旧身份残留、频率残留、测试状态，然后告诉我下一步实机安装测试怎么做。
```
