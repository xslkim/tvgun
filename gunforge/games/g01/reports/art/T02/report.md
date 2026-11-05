# T02 风格词、风格样图、锚点图库

日期：2026-11-04。状态：**A1 限定特点已审核**。12 张参考图和风格词已按用户反馈落盘；T03 开始制作。

## 产出

浏览器入口：[打开审核画廊](http://127.0.0.1:8765/gallery/)（本机服务运行时可用）。本地文件：[审核画廊源文件](gallery/index.html)。另有 [30 张联系表](contact_sheet.jpg)、[风格词草案](../../../bible/style.md)、[初始审核表](review.yaml)、[完整检查结果](checks.json)、[生成记录](manifest.json)。

共 30 个当前候选：12 站点、6 居民、6 墨怪、6 UI。另有墨鸦 A 版独立图、同底图 A/B 合成图 2 张，以及 5 张被替换的 UI 首稿。候选未复制到正式资产库。A1 后已创建 anchors.json，12 张仅按指定特点批准；review.yaml 记录了用户的限定选择，其余图片待审。

| 编号 / 资产 ID | 文件 | 状态 |
|---|---|---|
| 01 / st_l1_alley | [原始 PNG](gallery/st_l1_alley_original.png) | 已选参考特点 |
| 02 / st_l1_hawthorn | [原始 PNG](gallery/st_l1_hawthorn_original.png) | 待审 |
| 03 / st_l1_video | [原始 PNG](gallery/st_l1_video_original.png) | 待审 |
| 04 / st_l1_bridge | [原始 PNG](gallery/st_l1_bridge_original.png) | 已选参考特点 |
| 05 / st_l2_ticket | [原始 PNG](gallery/st_l2_ticket_original.png) | 待审 |
| 06 / st_l2_posters | [原始 PNG](gallery/st_l2_posters_original.png) | 待审 |
| 07 / st_l2_seats | [原始 PNG](gallery/st_l2_seats_original.png) | 已选参考特点 |
| 08 / st_l2_projector | [原始 PNG](gallery/st_l2_projector_original.png) | 待审 |
| 09 / st_l3_waiting | [原始 PNG](gallery/st_l3_waiting_original.png) | 待审 |
| 10 / st_l3_platform | [原始 PNG](gallery/st_l3_platform_original.png) | 已选参考特点 |
| 11 / st_l3_carriage | [原始 PNG](gallery/st_l3_carriage_original.png) | 待审 |
| 12 / st_l3_base | [原始 PNG](gallery/st_l3_base_original.png) | 已选参考特点 |
| 13 / res_vendor | [原始 PNG](gallery/res_vendor_original.png) | 已选参考特点 |
| 14 / res_video | [原始 PNG](gallery/res_video_original.png) | 待审 |
| 15 / res_projectionist | [原始 PNG](gallery/res_projectionist_original.png) | 已选参考特点 |
| 16 / res_ticket | [原始 PNG](gallery/res_ticket_original.png) | 已选参考特点 |
| 17 / res_cyclist | [原始 PNG](gallery/res_cyclist_original.png) | 已选参考特点 |
| 18 / res_passerby | [原始 PNG](gallery/res_passerby_original.png) | 待审 |
| 19 / ink_tadpole | [原始 PNG](gallery/ink_tadpole_original.png) | 待审 |
| 20 / ink_crow | [原始 PNG](gallery/ink_crow_original.png) | 待审 |
| 21 / ink_rider | [原始 PNG](gallery/ink_rider_original.png) | 已选参考特点 |
| 22 / ink_sign | [原始 PNG](gallery/ink_sign_original.png) | 待审 |
| 23 / ink_tape | [原始 PNG](gallery/ink_tape_original.png) | 已选参考特点 |
| 24 / ink_umbrella | [原始 PNG](gallery/ink_umbrella_original.png) | 待审 |
| 25 / ui_life | [原始 PNG](gallery/ui_life_original.png) | 已选参考特点 |
| 26 / ui_ammo | [原始 PNG](gallery/ui_ammo_original.png) | 待审 |
| 27 / ui_stamp | [原始 PNG](gallery/ui_stamp_original.png) | 待审 |
| 28 / ui_frames | [原始 PNG](gallery/ui_frames_original.png) | 待审 |
| 29 / ui_title | [原始 PNG](gallery/ui_title_original.png) | 待审 |
| 30 / ui_crosshair | [原始 PNG](gallery/ui_crosshair_original.png) | 待审 |
| 对照 / ink_compare_a | [墨 A 原图](gallery/ink_compare_a_original.png) · [合成 A](gallery/comparison_A.png) · [合成 B](gallery/comparison_B.png) | 待审，仅对照 |

墨 A 是强高光与球状红核的刻意对照；墨 B 是原有墨鸦的少高光与平面朱砂印迹。两版使用同一底图、同一显示包围框和位置合成。编辑可能改变细微轮廓，因此不把全部视觉差异归因为材质。B 复用原墨鸦，不重复计图像调用。

灰底 JPG、联系表、合成图均是诊断展示文件。候选原始 PNG 保留工具输出及真实 alpha，未通过调色或裁切去掩盖数值失败。请求尺寸没有独立数值参数；实际返回尺寸逐项记录，正式玩法尺寸留在后续任务归一化与验收。

## 检查结果

以下共 31 个独立图像样本，包含 30 个候选及墨 A 对照；合成预览未混入独立样本统计。C03 失败 12 项，C04 失败 19 项。失败保留，不改阈值使其通过。

| 编号 / 资产 ID | C03 | C04 | C05 | C14 |
|---|---|---|---|---|
| 01 / st_l1_alley | 失败 | 失败 | 待检查 | 待检查 |
| 02 / st_l1_hawthorn | 失败 | 失败 | 待检查 | 待检查 |
| 03 / st_l1_video | 通过 | 失败 | 待检查 | 待检查 |
| 04 / st_l1_bridge | 失败 | 失败 | 待检查 | 待检查 |
| 05 / st_l2_ticket | 通过 | 失败 | 待检查 | 待检查 |
| 06 / st_l2_posters | 通过 | 失败 | 待检查 | 待检查 |
| 07 / st_l2_seats | 通过 | 失败 | 待检查 | 待检查 |
| 08 / st_l2_projector | 通过 | 失败 | 待检查 | 待检查 |
| 09 / st_l3_waiting | 通过 | 失败 | 待检查 | 待检查 |
| 10 / st_l3_platform | 通过 | 失败 | 待检查 | 待检查 |
| 11 / st_l3_carriage | 通过 | 失败 | 待检查 | 待检查 |
| 12 / st_l3_base | 失败 | 失败 | 待检查 | 待检查 |
| 13 / res_vendor | 失败 | 失败 | 待检查 | 待检查 |
| 14 / res_video | 失败 | 失败 | 待检查 | 待检查 |
| 15 / res_projectionist | 失败 | 失败 | 待检查 | 待检查 |
| 16 / res_ticket | 失败 | 失败 | 待检查 | 待检查 |
| 17 / res_cyclist | 失败 | 失败 | 待检查 | 待检查 |
| 18 / res_passerby | 失败 | 失败 | 待检查 | 待检查 |
| 19 / ink_tadpole | 通过 | 通过 | 待检查 | 待检查 |
| 20 / ink_crow | 通过 | 通过 | 待检查 | 待检查 |
| 21 / ink_rider | 通过 | 通过 | 待检查 | 待检查 |
| 22 / ink_sign | 通过 | 通过 | 待检查 | 待检查 |
| 23 / ink_tape | 通过 | 通过 | 待检查 | 待检查 |
| 24 / ink_umbrella | 通过 | 通过 | 待检查 | 待检查 |
| 25 / ui_life | 失败 | 通过 | 待检查 | 待检查 |
| 26 / ui_ammo | 通过 | 通过 | 待检查 | 待检查 |
| 27 / ui_stamp | 通过 | 不适用：独立朱砂印框 | 待检查 | 待检查 |
| 28 / ui_frames | 失败 | 通过 | 待检查 | 待检查 |
| 29 / ui_title | 通过 | 通过 | 待检查 | 待检查 |
| 30 / ui_crosshair | 通过 | 通过 | 待检查 | 待检查 |
| 对照 / ink_compare_a | 通过 | 失败 | 待检查 | 待检查 |

- **C03 亮度**：巷口、糖葫芦摊、天桥、灯座、全部 6 个居民、灯芯 UI、提示框 UI 触发失败。正式版本需收暗纸色和高光，不能直接复制本稿用于生产。
- **C04 色板**：12 个站点和 6 个居民全部低于当前覆盖率阈值，墨 A 对照另失败；6 个默认墨怪通过。检查排除了允许的朱砂色像素，未对场景中烘焙的光照另作分层扣除，因此场景结果是保守预筛，后续应在真实分层素材上重新检查。独立朱砂印框排除普通色板覆盖率后无剩余像素，标为“不适用”，其朱砂色域及整帧面积仍需后续验收。
- **C05 文字**：未安装 Tesseract，自动 OCR 未运行，全部待检查。执行者目视标题为“纸灯城”，其余未见可辨文字；目视说明不替代 OCR 通过结果。
- **C14 风格**：尚无审核人选定锚点，不评分；每图提供执行者目视理由，状态待检查。建议标签不代表人工通过。

## 调用数和费用

T02 已用 **36 / 36 次**：初始 30 次，UI 重出 5 次，墨 A 编辑 1 次。阶段 0A（T02–T07）当前 36 / 120 次；包含 T01 的 3 次能力验证后，项目累计内置图像调用 39 次。没有超限继续重试。

内置工具未披露实际模型、种子、供应商任务 ID 和费用，均记 null / not_reported；**费用未知，不等于零**。未启用外部付费 API，外部调用为 0。旧状态中的 spent_cny=0 仅对应外部现金支出，不表示内置 GPT 免费。

请求文本、尝试编号、输出哈希、实际尺寸、参考图及哈希、检查和审核状态见 manifest。请求指纹由已保存的请求重建并明确标注；调用前的本地预留以 calls.json 的 ID＋attempt 记录为依据，不伪称当时已写入完整请求指纹。原始输出和首稿保存在 D:/gunforge_cache/g01/T02/。

## 成功率

工具返回 36 / 36 次（100%），这只是返回率。当前留作审核候选 30 张，另有 1 张 A 版对照；替换 5 张首轮 UI。**A1 限定参考特点批准 12 张，正式生产资产批准 0 张**，不能用 30/36 作为生产合格率。

- 站点：尝试 12，候选 12；主要问题为场景偏色、部分偏亮、旧式建筑装饰过多、灯座主题不足。
- 居民：尝试 6，候选 6；全部存在亮度与色板失败，纸偶偏厚、铜扣偏多，自行车辐条偏细。
- 墨怪：尝试 6，候选 6；少高光和平印方向较稳定，但墨车夫身份不清、墨招牌轮廓不足、部分羽毛和带丝过细。对照 A 另尝试 1 次，不计默认墨怪成功率。
- UI：尝试 11，候选 6；5 个首稿场景化后重出。灯芯与提示框亮度失败，准星仍残留软光；正式显示尺寸的辨识度、九宫格和引擎检查待后续任务。

## 问题和偏差

1. 首轮 UI 复用了包含灯城、生活物件的风格描述，导致生成装饰插画。已将 UI 改为独立、简短的技术提示词，并保留首稿证据。准星第二次仍有软光，不静默判合格。
2. 提示词指定色值不能保证每个像素都落入色板；当前候选可选择“构图、年代物件、墨质”等局部特点，不能因此批准整图的亮度与配色。
3. 自动 OCR 集成仍待完成；C14 当前按任务要求只提供理由。T00 不标为全部完成。先前合成透视反例 C13 基线也仍有失败，不在本阶段冒充真实光枪验收。
4. 本阶段没有验证命中区、实际显示尺寸、Godot 或真实光枪。T09 及后续批量任务仍须真实 0B 五项验收记录。

## 需要审核人决定

1. **选 6–12 张锚点**，站点、居民、墨怪、UI 每类至少 1 张。新版画廊依次展示四类图片，点击图下「布局、灯光、纸感」等特点即可选中并记录用途；逐图备注选填。选完后生成中文反馈，复制到聊天发送；也可下载 review.yaml 留存。页面不会自动将结果发给执行者。
2. **选墨 A / B，或提出修改意见**。执行者建议 B，减少高光并保持平面朱砂；这只是建议。
3. **确认或修改风格词**。建议强调“平纸片、少铜扣、低亮夜底、生活年代感、简洁 UI”，避免把候选中的厚纸偶、偏橙亮光与软光准星固化为风格。

可优先比较的十张（均未自动选中）：01 巷口（构图/年代物件，需收暗）、07 观众席（光感/构图）、10 站台（横向节奏）、11 车厢（重复窗格）、14 录像厅老板（人物气质）、18 路人（人物气质）、20 墨鸦（墨质）、24 墨伞（轮廓）、25 灯芯（简洁造型，需收暗）、29 标题（字形）。也可选其他候选或拒绝当前方向。

依据 [任务文档 T02](../../../../../../docs/ART_TASKS_PAPER_LANTERN_CITY.md) 的“停止，等审核人”，收到 A1 意见后才会复制锚点、记录锚定项和内容哈希、定稿 style.md，并继续 T03。本次待审核的是风格方向，不要求现在进行真机验证。

## 审核页交互改版（2026-11-04）

按用户反馈改为「挑参考图 → 选墨的感觉 → 复制反馈」三步。技术信息默认折叠，逐图备注选填；每个用途按钮同时完成选图和用途记录。保留固定编号、6–12 张与四类覆盖要求；增加「这一批都不合适」入口，必须填写修改意见后才能生成不批准当前图片的反馈。

结果页提供可直接粘贴到聊天的中文反馈，明确提示尚未发送。剪贴板不可用时自动选中文字供手动复制。旧版浏览器选择迁移到新版，不删除旧记录；项目中的初始 review.yaml 与候选审批状态保持待审。

交互逻辑已使用独立测试数据验证：选择/取消、多用途计数、数量上限、分类覆盖、墨材质和修改意见必填、刷新恢复、旧记录迁移、复制降级和 YAML 解析。此次改版未调用图像生成工具，未重跑或改写数值检查结果。

## A1 审核归档（2026-11-04）

收到用户聊天明确反馈，批准编号 01、04、07、10、12、13、15、16、17、21、23、25 的指定特点。详情以 review.yaml、bible/anchors.json 为准；未选图片保持 pending。墨材质两版均需修改，执行“偏亮面但反光克制”；朱砂沿用上游平面印迹。12 张原始 PNG 已复制到 bible/style_refs/ 并核对哈希，style.md 已定稿。本次批准的是参考特点，不是正式生产资产或真实 0B 验收。
