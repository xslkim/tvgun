# 动画与数据合同

## 动作制作

按游戏需求选动作。通常从 `idle`、所需的 `walk` / `run` / `fly`、`attack_light`、`hit` 和 `death` 起步。再按角色补跳跃、重击、施法或其他动作。完整模板动作和名称见 [曲线实现](../../pipeline/anim/clips.mjs)。

先定关键姿势、支撑区间、地速和事件，再制作曲线。步态必须区分支撑与摆动，原地走跑由地速抵消支撑脚在角色空间的后移。走路持续有支撑，跑步有腾空。攻击区分预备、命中和恢复。 `footstep` 对应接触点，`hit`、`sfx`、`fx_spawn` 用于接入游戏事件。

## 游戏接入

- 交付整个 `assets/<id>/export/`。读取 `character.json` 中的 `rig.version`、`rig.atlas`、`rig.attachments` 和 `clips`。图集和动作路径相对于该目录。采样、世界骨架和蒙皮可参考 [运行时](../../pipeline/rig/runtime.mjs)。
- 每个 clip 含 `name,duration,fps,bake_hz,frames,events,keyTimes,meta`。时间为秒，30 fps 预览，120 Hz 烘焙。帧内以骨名映射到 `[dx,dy,dAngle,sx,sy]`，缺省值为 `[0,0,0,1,1]`，时间采样线性插值。缩放作用于局部点与直接子骨偏移，子骨不继承缩放基底。世界坐标以像素存储，游戏侧设定像素与游戏单位的换算。
- 循环播放范围为 `[0,duration)`，保留尾帧做插值和接缝检查。按游标派发 `events`，处理首帧、循环回绕与一次性动作末帧。事件效果、碰撞与命中由游戏侧定义。
- `meta.root_motion_mode` 为 `in_place` 或 `root`。原地位移由控制器按 `locomotion_speed` 驱动，根位移动作由游戏处理根轨增量与碰撞，避免画面重复位移。跨动作足锁由游戏侧处理。
- 支撑点在 `rig/rig_meta.json`，接触区间在 `meta.contact_intervals`，跨循环的区间拆成两段。源姿势时间和 QA 元数据分别保存在 `anim/blocking.json` 和 `anim/anim_meta.json`。例外须明确规则、骨名、时间范围和理由，硬规则仍检查。

## 验收

`node tools/qa/check.mjs <id>` 写出报告和关节曲线，`node tools/qa/render.mjs <id>` 生成 GIF、关键帧、问题帧及像素地面测量。附加 `--debug` 生成骨架 GIF 和洋葱皮。

- 自动检查覆盖反折、角速、位移跳变、骨长、滑步、接缝、事件和网格翻面。地面与脚锁以 0.01H 为容差，非弹性骨长偏离上限 2%。样例的完整阈值以 [检查器](../../tools/qa/check.mjs) 为准。
- 自动 QA 无错误后，目视对照设定与真实渲染，检查遮挡、关键配件、接地、节奏和转场。支撑点通过时，贴图仍可能穿地。 [检查清单](../../skills/2d-skeletal-character/references/checklists.md)
