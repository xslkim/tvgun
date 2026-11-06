# 离线生图备用流程

1. 按 [ComfyUI 官方 Schnell FP8 步骤](https://docs.comfy.org/tutorials/flux/flux-1-text-to-image#flux-1-schnell-fp8) 安装本地程序和 Apache-2.0 的 [单文件 FP8 权重](https://huggingface.co/Comfy-Org/Flux-1-Schnell/blob/main/flux1-schnell-fp8.safetensors)。导入 [官方模板 JSON](https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/flux_schnell.json)，确认 checkpoint 指向已安装的权重。
2. 使用 [Prompt 库](../../skills/2d-skeletal-character/references/prompt_library.md) 的原型布局，把真实 Alpha 改为饱和纯色键底。选纹理中没有的底色，去除投影和半透明环境光。以 1536×1024 或等比尺寸、4 步、固定 seed 开始。保存运行时 commit、模型 revision、节点 JSON、seed 和原始 PNG。
3. 将工作板放在 `assets/<id>/concept/raw.png`，量绝对裁框，写入 `layout.json` 与 `manifest.json`。每格须有连通的底边。指定 `"background": [r,g,b]`，裁切器从四边洪泛，保留内部同色高光。存在渐变或可见脏边时用多边形遮罩、重出或先抠图。
4. 按 [Skill](../../skills/2d-skeletal-character/SKILL.md) 从切件继续。如果需要可编辑的独立色层，使用 [Qwen Layered 官方流程](https://docs.comfy.org/tutorials/image/qwen/qwen-image-layered)，逐层检查缺失的隐藏面。对脚、手及重叠链仍按关节人工归属。
5. 本机验证了官方工作流的数据结构，没有以这些权重生成项目样本。已有六张 AI 原图可用于离线重建。
