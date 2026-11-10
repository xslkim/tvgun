# 《纸灯城》开场 CG

本轮从文字设定新制的 90 秒开场。未取用项目原有画面、视频、角色、音乐、音效或声音参考。

## 看成片

- `paper_lantern_city_opening.mp4`：1920×1080、30fps，含爷爷旁白、原创配乐和音效、中文字幕。
- `paper_lantern_city_opening_clean.mp4`：相同剪辑和声音，不烧录字幕。
- `paper_lantern_city_opening_game.ogv`：1776×936 内容区画面、30fps、Theora/Vorbis，首站播放器在定位白边内播放。
- `opening_zh.srt`、`opening_subtitles.json`：独立字幕。

从首站启动器进入游戏时，首次开始会播放开场。Enter、Esc 或手机开始键可跳过，播放器使用 JSON 字幕。试玩关卡时可加 `-SkipOpening`。见[首站启动说明](../../../../../docs/LEVEL_DESIGN_ENGINE_QUICKSTART.md)。

H3 原始视频为本机新生成的 1152×640、24fps，1080p 交付经过光流补帧、缩放和亮度控制；不宣称原生 1080p。

## 内容与来源

故事从雨夜空椅和磁带开始，经过失手倾墨、墨渗纸、纸灯亮起、纸居民醒来、墨鸦展翼与光照净墨，最后落在片名上。爷爷只在录音中出现，玩家不露脸；纸居民始终是保护对象。开场不揭露“忘”字，也不提前使用结局最后一句。

`keyframes/` 是本轮用内置 GPT 图像工具新生成的工作台、磁带特写、纸城、渗墨特写、墨鸦、倾墨末帧、点灯末帧与透明片名。最初的两张图只输入文字；之后仅在本轮新图之间使用参考。片名保留真实 alpha。

`sources/` 是本轮本地 MiniMax H3 视频。`jobs/` 保存每次任务的提示词、种子、工作流、任务 ID、历史与输出哈希。退回的试拍保留，剪辑只使用 `selected_sources.json` 所列镜头，不会从旧项目素材兜底。

[图像提示词规格与来源记录](image_generation_manifest.json) 列出八张新图的输入参考、实际尺寸、透明通道和哈希；逐镜 H3 的原始生成提示词位于 `jobs/*_workflow.json`。

`audio/` 包含本轮设计的虚构爷爷声音、逐句原始配音、磁带处理后的旁白、程序原创音乐、程序新合成雨声/磁带噪声/叩击/水滴/光音效，以及完整混音。不使用任何现成参考人声、采样音乐或音效库。爷爷先由本地 VoxCPM2 文字设计音色，再以这次新生成的声音保持各句一致。未复刻任何真实人物。

## 复现

剧本和时间轴：`gunforge/pipeline/cinematics/opening_plan.py`。

在 WSL、已有 ComfyUI 服务 `127.0.0.1:8189` 与 H3 权重可用时，用 `generate_opening_h3.py --shots <镜头编号> --take <次数>` 生成。脚本先落盘任务 ID，支持已知任务续查；不盲目重发状态未知的任务。

`generate_opening_voice.py` 使用已安装 VoxCPM2 的虚拟环境。确认本片所需 H3 任务完成、服务队列空闲后才卸载缓存模型并生成旁白；不终止其他任务。

Windows 仓库根目录：

```powershell
python gunforge/pipeline/cinematics/build_opening.py audio
python gunforge/pipeline/cinematics/build_opening.py video
python gunforge/pipeline/cinematics/build_opening.py audit
```

工具依赖：ffmpeg/ffprobe、numpy、scipy、Pillow，字幕用系统 Noto Serif SC。Windows FFmpeg 8.1.1 的 Theora 编码在本片约 60 秒处失败；Windows 7.1 虽完成编码，完整解码时仍出现错误，均不作为可用交付。游戏版使用 WSL 的原生 FFmpeg 7.0.2，导出后严格完整解码并还原 30fps 的 2700 个展示帧，才替换最终文件（Theora 会省略相同重复帧，实际解出的独立帧数可以更少）。`GUNFORGE_THEORA_FFMPEG` 可指定 WSL/Linux 内编码器路径，`GUNFORGE_WSL_DISTRO` 可指定发行版（默认 Ubuntu-22.04）。当前脚本不会自动替换已渲染的镜头；修改选择或调色后应先把对应 `build/sXX.mp4` 另名归档，再重新渲染。

## 游戏接入

游戏版不烘焙定位白边与 HUD；放入既定 1776×936 内容区，外部定位边框始终由游戏保持。字幕用 JSON/SRT 在视频上方单独渲染；开枪或 START 跳过时应同时停止视频、字幕和音频。当前仓库没有可接入的正式过场播放器，因此交付媒体与时间轴，不宣称已经接入引擎或通过真机追踪验收。

## 检查与审核

`qa/technical_report.json` 记录导出规格、2700 帧检查、字幕时间、逐镜抽帧、每秒亮度扫描及最终响度；`qa/voice_readback.json` 保存本地 Whisper 对新配音的回读结果（同音字识别不等于发音错误）。`qa/` 留有逐镜与成片画面证据。`asset_manifest.json` 保存媒体哈希和无历史媒体输入的来源声明。最终仍需你按审看版决定画风、节奏和旁白是否采用，脚本不会代替你写入美术通过记录。

拼接前 `build/normalized/` 将每段固定到精确的 30fps 帧数与相同时间基，防止静态图层合成继承 25fps 后导致音画错位。居民段的背景使用本轮新画的纸城锁定，排除 H3 误生成的太阳；倾墨段采用新视频的碰动加原创末帧的渐变，排除模型擅自点灯的部分。程序渲染控制的是编码前亮度；有损编码与字幕边缘可能有极少数像素略超过 75%，实际比例与峰值保留在报告中，不把离线检查等同于实机验证。

分镜说明：`docs/CG_OPENING_PAPER_LANTERN_CITY.md`。内置图像工具的确切模型、随机种子和费用未披露，均保留 null；本地模型运行不调用外部付费视频或语音 API。
