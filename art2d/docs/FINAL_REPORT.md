# 交付验收记录

游戏开发 Agent 从 [README](../README.md) 开始。工具和样例用于 2D 角色资源生产，项目动作范围与美术风格由游戏需求决定。

- 五个主 Demo 共 47 段动画，Skill 验证角色另有 11 段，自动检查均为 0 错误。15 项动作 QA 回归和浏览器播放测试通过。 [示例与报告](../demos/README.md) · [回归日志](../tools/qa/tests/RESULTS.txt) · [成品清单](../tools/qa/tests/INVENTORY.txt)
- 黄铜信使按设定重新切件和绑定。成品检查对比剪影、围巾与图层顺序，保留视觉复检证据。 [复检](../assets/courier/qa/visual_recheck.md)
- 使用新角色从原图复跑了生产 Skill。内置生图服务的精确模型版本及 seed 未公开，清单保留了 Prompt、原图和哈希。 [Skill 复现](../skills/2d-skeletal-character/VALIDATION.md) · [来源与授权](RIGHTS.md)
- Canvas 为实测运行时。Godot 探针只验证骨架与采样，备选离线模型只核验工作流。 [初始选型](DECISIONS.md) · [调研](research/REPORT.md) · [原任务书（归档）](archive/TASK_2D_Skeletal_Animation_Agent_Guide.md)
