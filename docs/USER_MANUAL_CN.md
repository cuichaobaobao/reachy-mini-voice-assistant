# Reachy Mini HA Voice 用户手册

## 安装

从 Reachy Mini 应用商店安装 `reachy_mini_ha_voice`，启动后它会在机器人上开启 ESPHome 兼容的语音卫星服务。

Home Assistant 通常会自动发现新的 ESPHome 设备：

- 名称：`Reachy Mini Voice ******`
- 端口：`6053`
- 制造商：`Reachy Mini HA Voice`
- 项目：`ReachyMini.HAVoice`

如果自动发现失败，可以在 Home Assistant 中手动添加 ESPHome，并填写机器人 IP 和端口 `6053`。

## 语音

- 本地 MicroWakeWord 唤醒词：Okay Nabu、Hey Mycroft、Hey Jarvis
- 本地 Stop 停止词
- STT、对话代理、TTS 由 Home Assistant 管线处理
- 支持连续对话、静音、唤醒词灵敏度和 Stop 灵敏度

## 动作

应用保留调教后的动作系统：

- 官方风格 60Hz 运动控制
- 官方呼吸待机和天线动作
- SDK 说话 wobbling
- 聆听、思考、说话、计时器提醒动作
- 实时生成的空闲微动作
- DOA 声源方向唤醒转头
- 可选的 SDK 人脸注视，仅在聆听和思考时启用

## Home Assistant 实体

### 常用控制

| 实体 | 类型 | 说明 |
| --- | --- | --- |
| Mute | 开关 | 暂停/恢复语音链路 |
| Continuous Conversation | 开关 | 连续对话 |

### 语音调校

| 实体 | 类型 | 说明 |
| --- | --- | --- |
| Wake Word 1 Sensitivity | 数值 | 第一个启用唤醒词阈值 |
| Wake Word 2 Sensitivity | 数值 | 第二个启用唤醒词阈值 |
| Stop Word Sensitivity | 数值 | Stop 停止词阈值 |

## 不包含

本应用不发布机器人控制、摄像头、daemon 诊断或录制动作，请使用官方 Reachy Mini Home Assistant 集成。`REACHY_VISION_FACE_TRACKING_ENABLED=true` 独立开启 SDK 人脸追踪；`REACHY_VISION_JPEG_ENABLED=true` 独立允许按需读取 JPEG 帧。`REACHY_VISION_JPEG_REFRESH_HZ=5` 只限制连续请求时的最大读取频率，不会启动持续抓帧循环。应用不会新增摄像头实体或 RTSP 推流。
