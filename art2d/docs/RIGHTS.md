# 工具、模型及素材授权记录

范围为当前非商业研究、演示和生产验证。记录日期 2026-11-06。仓库的公开/再分发要按实际使用组件和产品条款复核。

## 实际使用

| 组件 | 许可或边界 |
| --- | --- |
| 内置图像生成 | 闭源服务，适用使用者的服务条款；六份原始图与其裁切、图集、动画均由原创文字生成。无第三方现有角色目标、外部参考图或素材输入。输出使用权与第三方相似性应按实际发布审核。模型精确版本、seed 及采样设置未提供。[OpenAI 产品条款](https://openai.com/policies/terms-of-use/) |
| Node.js 24.22.1 / JS 运行时 | Node 核心 MIT 与 bundled third-party notices。工作区不打包 Node。[许可证](https://github.com/nodejs/node/blob/main/LICENSE) |
| Python 3.12.10 / Pillow 12.2.0 / uv | Python PSF；Pillow HPND；uv MIT/Apache-2.0 双许可。脚本使用系统或 uv 缓存运行时，仓库不分发解释器与依赖二进制。[Python](https://docs.python.org/3/license.html) · [Pillow](https://github.com/python-pillow/Pillow/blob/main/LICENSE) · [uv](https://github.com/astral-sh/uv) |
| Edge / Canvas | Edge 本机无头验证，用户可选兼容浏览器。Canvas 为标准接口，无运行时专有库随包发货。[Canvas](https://html.spec.whatwg.org/multipage/canvas.html) |
| Godot 4.6.3 | MIT。只运行验证，用的官方可执行文件保存在临时目录，项目不分发。若未来打包引擎，按官方文档附带版权与依赖公告。[许可](https://godotengine.org/license/) |
| Spine / Meta / Comfy 官方样本 | 只从官方源下载到临时目录读取格式与工作流结构，原素材不进入仓库。Spine Runtime License 与编辑器条款独立；Meta code MIT；Comfy 工作流及权重按对应条款。见 [探针链接](research/probes/README.md)。 |
| 项目原创代码 | 随现有仓库留档，未代用户声明新的公开许可证。 |

候选及模型许可见 [调研](research/REPORT.md)。没有引用的参考图片或视频随项目再分发，参照链接见 [参考索引](../assets/references/SOURCES.md)。LFS 规则见本目录 `.gitattributes`，保留原图字节以便核对哈希。
