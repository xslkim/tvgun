# T15 灯城回望片尾候选

`paper.lantern_city_epilogue` 在工作台「忘」字第七笔净化后播放 58 秒片尾。新全景让夜市、旧影院和火车站同框。Godot 执行叠化、运镜、字幕和结算。[有声片尾 MP4](epilogue_wide.mp4) · [全景原图](../../../assets/cutscenes/epilogue/city_wide_v1.png) · [内置 imagegen 提示词与参考图](city_wide_generation.json)

| 时间 | 画面与声音 |
| --- | --- |
| 0–7.2 秒 | 工作台纸灯从暗到亮，响起点灯声与磁带按键。 |
| 7.2–20.8 秒 | 叠化到夜市街巷。爷爷从 9.0 秒说「夜市的灯，又亮了起来。」 |
| 20.8–47.8 秒 | 从街巷叠化到灯城全景，镜头慢慢拉远，让三处地标同时可见。配乐沿用开场旋律的音型，改用轻八音盒。 |
| 47.8–58.0 秒 | 回到工作台。爷爷从 49.0 秒说「灯亮着，就还在。」纸灯留亮，磁带收尾。 |

[灯城拉远前](ending_wide_near.jpg) · [全景停留](ending_wide_full.jpg) · [58 秒音轨 WAV](../../../assets/cutscenes/epilogue/ending_wide_tape.wav)

## 试玩

在仓库根目录的 PowerShell 运行以下命令。可加 `-SkipOpening` 跳过开场视频。第七笔净化后，按 Enter、Esc 或光枪开始键均可跳过片尾。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_epilogue -Candidate
```

三关 15 站、114 条输入回放和工作台失败重试通过。自然播完与从四段跳过均保留相同结算。播放器用 Enter、Esc 和本机 UDP 模拟光枪验证跳过后音轨停止，显示设置中的暂停与恢复、结算后的重试也通过。夜市和全景纹理均在前一镜预载。[本版软件与媒体验证](wide_checks.json)

两句沿用 20.4 秒短版录音。点灯时，片尾音轨接替之前的环境声。混音回读与游戏字幕一致。Windows 无声驱动的全程试播在两处旁白起点测得最大 0.27 秒偏差，字幕窗口均覆盖旁白。预览由 Godot 抓帧导出，末尾保留 0.8 秒结算。全景原图、8 张原尺寸抓帧和 59 张视频逐秒抽帧通过 C03 亮度检查。

## 待验

待复核全景美术、58 秒节奏和旁白混音，并用实体光枪验证跳过。短版仍可供对照。[20.4 秒有声短版](epilogue_voiced.mp4) · [短版旁白验证](audio_checks.json) · [早期无声版验证](software_checks.json)
