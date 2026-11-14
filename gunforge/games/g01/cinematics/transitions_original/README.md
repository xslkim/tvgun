# 《纸灯城》场景转场 CG

这套视频覆盖正式三关战役中相邻的 16 个可玩场景，包括复用巷口站点编号的水洼。冒险从巷口经水洼、糖葫芦摊、录像厅、天桥至广场，从售票处穿过旧影院，再经候车室、站台、绿皮车厢和灯座，回到爷爷的工作台。

15 支独立 MP4 以路线顺序编号。每段 3.2–5 秒，1280×720、30fps，配新制作的环境过渡音与短音乐提示。夜市用暖杏和深靛，旧影院用紫红和投影暖光，火车站转向沉静的青绿与琥珀。放映光束、车窗光与纸灯层缝构成连续的视觉线索。两次跨关以及从灯座拉到工作台的转场各留 5 秒。

`paper_lantern_city_transitions_review.mp4` 串联所有转场供审看。`transitions.json` 记录游戏段落映射、时长、分镜意图及验证用战役版本。开场、战斗波次、结尾沿用各自的演出；场景清单仅覆盖可玩的场景切换。

源画面由内置图像生成新绘，共四张四格画板，每格独立构图。每个场景的画面可衔接前后两支短片。短片用镜头推拉、滑移、叠化和各段新合成提示音剪成。源画板及来源记录在 `atlases/`，逐镜配对和剪辑参数在 [制作脚本](../../../../pipeline/cinematics/build_transitions.py)。使用已安装的 FFmpeg、Pillow、NumPy、SciPy，从仓库根目录运行：

```powershell
python gunforge/pipeline/cinematics/build_transitions.py
```

`game/` 内的 OGV 已接入三关播放器。用仓库根目录的 `play_paper_lantern_campaign.cmd` 启动，或通过 `gunforge/start_level_player.ps1 -Package paper.lantern_city_cast -Candidate` 启动。播放器在内容区播放转场，保留定位白边并暂停玩法。Enter、Esc 或光枪开始键可以跳过。
