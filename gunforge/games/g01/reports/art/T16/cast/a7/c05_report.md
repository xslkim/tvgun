# 《纸灯城》三关候选 C05 文字检查

按当前隔离包逐件核对 296 张 PNG 的 SHA-256。256 条色彩图资源记录对应 254 个不同文件内容，均使用 Tesseract.js 7.0.0 中英文模型扫描。独立命中遮罩和灰度影响罩共 40 条，C05 不适用。[逐件结果](c05_text.json) · [带定位框的复核页](c05_review.html)

| 结果 | 资源记录数 |
| --- | ---: |
| 自动检查通过 | 174 |
| 待目视复核 | 82 |
| 自动检查失败 | 0 |
| C05 不适用 | 40 |

四张原始字形均识别为预定的「纸灯城」「夜市」「旧影院」「火车站」。标题和章节转场的三张同构建 Godot 原帧裁出对应字形后，四处也都识别正确。黑底材质样本四张均识别正确，白底材质压力样本四张均未识别为预定文字。开始和章节转场使用游戏内的深色遮罩。[Godot 实际画面与材质样本](c05_rendered.json) · [当前三关画廊](../gallery.html)

空白对照无输出，加入 `LANTERN 2026` 的对照被拒绝。每个疑似样本只自动复扫一次。82 个疑似项中，77 个复扫后无文字输出，5 个在两次扫描中都有输出。前者仍保留第一次的识别内容和位置。复核页将两次均有输出的样本排在前面。

| 两次均有输出 | 已查看的定位区域 |
| --- | --- |
| `footbridge.image_003` | 天桥栏杆的重复竖线 |
| `footbridge.image_007` | 灯笼挂绳、纸面与垂穗 |
| `platform.image_005` | 车窗、车门与黄色饰边 |
| `plaza.image_049` | 龙尾鳞片 |
| `video_shop.image_013` | 录像厅老板的纸偶分件 |

上表定位区域未发现可辨文字。其余疑似项及正式 A7 美术签核待审核。工作台「忘」字是七笔组成的 Boss，逐笔归属和可射范围见专项验证。[工作台七笔](../workbench_readability/report.md)

同一隔离包通过 15 站、118 条输入回放、失败重试和片尾跳过。运行素材检查使用现成的中英文 OCR 模型。

## 复跑

按[构建隔离目录](../report.md#构建隔离目录)准备 `$stage`。OCR 使用 Node 和已安装的 `tesseract.js`。若依赖在自定义目录，令 `ART_NODE_MODULES` 指向该 `node_modules`。在仓库根目录运行。

```powershell
$cast = 'gunforge/games/g01/reports/art/T16/cast'
$script = 'gunforge/pipeline/art/t16_asset_text.py'
$ocr = 'gunforge/pipeline/art/ocr.cjs'
$work = Join-Path $env:TEMP 'paper-cast-c05'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
uv run --locked --project gunforge/pipeline/art python $script prepare --stage $stage --manifest "$cast/candidate_manifest.json" --coverage "$cast/a7/asset_coverage.json" --work $work
node $ocr --batch "$work/first.json" 4 | Out-File -Encoding utf8 "$work/first.jsonl"
if ($LASTEXITCODE) { throw 'First OCR batch failed' }
uv run --locked --project gunforge/pipeline/art python $script retry --work $work
node $ocr --batch "$work/retry.json" 3 | Out-File -Encoding utf8 "$work/retry.jsonl"
if ($LASTEXITCODE) { throw 'OCR retry failed' }
uv run --locked --project gunforge/pipeline/art python $script report --work $work --output "$work/c05_text.json" --gallery "$work/c05_review.html"
```

原始 OCR 输出、Godot 材质样本与原帧字形裁图位于 `D:\gunforge_cache\t16_cast_c05`。三张原帧的像素哈希、裁图坐标及识别结果随报告保留。[渲染证据](c05_rendered.json)
