# 《纸灯城》宣传视频

五支横版中文宣传片，均为 1280×720、30fps 的 MP4。使用成品关卡实机截帧、开场和片尾的无剧透片段、场景转场 CG，以及为每支视频新合成的配乐。游戏截帧以运镜呈现。

- [三关总览 · 56 秒](01_overview.mp4)
- [夜市 · 55 秒](02_night_market.mp4)
- [旧影院 · 53 秒](03_cinema.mp4)
- [火车站 · 52 秒](04_train_station.mp4)
- [纸雕美术 · 50 秒](05_paper_art.mp4)

`promos.json` 记录各片的画面来源、文案和镜头时长。从仓库根目录运行 `python gunforge/pipeline/cinematics/build_promos.py` 可重新导出，需要 FFmpeg、Pillow、NumPy、SciPy 和 Noto Serif SC 字体。
