# 原型骨架

将对应 JSON 复制到角色的 `concept/rig_layout.json`。模板以通过数值 QA 的样例坐标为起点。把样例的 ID、尺寸、各部件锚点、连接和限制替换成新角色数值。逐一检查实际贴图的极限姿势。动作曲线和状态机在 [clips.mjs](../../anim/clips.mjs)，动作关键时间和接触参数见 [动画规范](../../../docs/spec/ANIM_SPEC.md)。
