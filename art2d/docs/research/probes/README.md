# 本机可执行证据

1. 主管线用 `node tools/poc.mjs` 和 `uv -q run --python 3.12 --with Pillow==12.2.0 python tools/poc.py` 生成七骨人形样例及 GIF。样例路径为 [demos/poc](../../../demos/poc/idle.gif)。
2. Godot 使用官方 4.6.3 Windows 稳定版 console 可执行文件。运行 `godot --headless --path docs/research/probes/godot --script res://probe.gd -- <world.json 绝对路径>`。比较同一组逐帧骨骼世界变换。见 [日志](godot/RESULTS.txt)。
3. 从 [Spine Runtime 4.3 示例](https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/4.3/examples/spineboy/export/spineboy-pro.json) 下载 JSON 至临时目录，运行 `node docs/research/probes/spine.mjs <下载路径>`。验证轨道关键值与一处 Bezier 采样。没有安装 Spine 编辑器，未分发原样例或运行时代码。见 [结果](spine-result.json)。
4. 把官方 [FLUX 工作流](https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/flux_schnell.json)、[Qwen Layered 工作流](https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/image_qwen_image_layered.json)、[Animated Drawings 标注样例](https://raw.githubusercontent.com/facebookresearch/AnimatedDrawings/main/examples/characters/char1/char_cfg.yaml) 下载至同一临时目录，保持原名，运行 `node docs/research/probes/ai.mjs <临时目录>`。只验证工作流和输入结构。见 [结果](ai-result.json)。
5. 实际内置生图与裁切证据见 [人形工作板](../../../assets/courier/concept/manifest.json)、[图集](../../../assets/courier/export/atlas.png)、[拼合](../../../assets/courier/preview/master_vs_bind.png) 及 [回归](../../../tools/qa/tests/RESULTS.txt)。
