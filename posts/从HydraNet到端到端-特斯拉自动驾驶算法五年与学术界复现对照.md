---
title: 从 HydraNet 到端到端：特斯拉自动驾驶算法五年，与学术界的复现对照
date: 2026-09-29
tags: [自动驾驶, 特斯拉, FSD, BEV感知, Occupancy, 端到端, 3D目标检测]
album: 自动驾驶专栏
order: 1
excerpt: 特斯拉从 Mobileye 时代演进至 AI Day 的 HydraNet 与 Occupancy，再到 v12 取代 30 万行 C++ 规则代码、v14 将参数量提升十倍；学术界以 BEVFormer、UniAD、StreamPETR 等工作对各环节逐一开源复现。本文按时间线梳理两条路线的技术选择，逐模块对照，给出 nuScenes 上可复现的指标与实际显存开销。
---

BEVFormer 仓库与特斯拉 AI Day 方案是同一问题的两种解法：闭源、依车队数据 vs 开源、以 nuScenes 为评判。第二篇对比国内七家车企，方法相同。

信息边界：特斯拉不开放代码，描述全部来自 AI Day 2021/2022 公开演讲、官方博客与版本更新说明，推断均已标注；学术界指标取自论文或官方 Model Zoo，可复现；显存标注口径者为社区实测或工程经验值，就近注明。

三点结论：

1. 特斯拉五年主线用学习组件逐级替换人工规则，"单一 backbone + 多任务头"骨架自 2021 未变；
2. 学术界已给出该路线各环节的可复现开源对应物，价值在可归因与可复现；
3. 实质差距在数据规模与闭环评测，不在网络架构；开源教师模型正缩小前者，无法替代后者。

---

## 目录

1. 前史（2016-2020）：从买方案到自研，图像空间到向量空间
2. AI Day 2021：HydraNet 与蒙特卡洛树搜索
3. AI Day 2022：Occupancy Network 逐层拆解
4. 数据引擎：自动标注与 4D 重建
5. 2023-2024：FSD v12，30 万行 C++ 的退场
6. 2024-2026：v13 到 v14，参数量、强化学习与视频基础模型
7. 芯片这条暗线：HW3、HW4 到 AI5
8. 学术界的平行线（一）：DETR3D、BEVDet、BEVDepth 与 BEVFormer
9. 学术界的平行线（二）：稀疏化的 StreamPETR、Sparse4D 与 SparseBEV
10. 学术界的平行线（三）：Occupancy 的公开复现
11. 学术界的平行线（四）：UniAD 与端到端规划
12. 正面对照：逐模块比较
13. 评测的分裂：NDS、L2、闭环与接管率
14. 2026 年的合流：VLA、世界模型与开源教师模型
15. 实践指南：方案选型与显存需求
16. 总结
17. 参考资料

---

![特斯拉与学术界 2021 至 2026 的双泳道时间线](images/tesla-academia-2026/s01-timeline-two-tracks.svg)

图 1｜五年时间线：上泳道为特斯拉公开发布物，下泳道为学术界论文与开源仓库，三组命题（占据表征、稀疏化、端到端）同向推进；横轴为首次公开时间，不代表性能顺序。

## 1. 前史（2016-2020）：从买方案到自研，图像空间到向量空间

2016 年前特斯拉无自己的感知栈，Autopilot 1.0 用 Mobileye EyeQ3 负责图像检测车道线与车辆。2016 年 5 月 Joshua Brown 事故（Model S 在 Autopilot 下撞上横穿的拖挂车）后双方决裂；7 月 Mobileye 宣布不再续约；10 月特斯拉发布自研感知栈 HW2，被迫自建视觉感知栈。

Autopilot 2.0（2016-2019）为"每相机一个 2D 检测器再拼接"：8 路相机各跑一个卷积网络，输出图像平面的 2D 框、车道线与红绿灯，再按相机外参投影至车体坐标系、合成俯视图。AI Day 2022 由 Tesla 归纳其四条局限：

- 地平线附近的深度极不一致，大片区域的深度由两三个像素决定；
- 遮挡无解，开过去之前永远不知道前车挡住的东西；
- 输出结构是 2D 的，而世界是 3D 的；
- 本体论漏洞（ontology cracks）：检测器只认识数据集里有的类别，遇到没见过的东西直接输出"空"。

2020 年前后，Karpathy 团队转向 BEV：统一俯视特征空间、任务在该空间完成。这一转变构成后续演进的起点，也是学术界 2021-2022 年密集跟进的主线。2019 年特斯拉流片自研 HW3（14nm，双 NPU 约 144 TOPS），软件随后围绕自家硬件优化（详见第 7 节）。

## 2. AI Day 2021：HydraNet 与蒙特卡洛树搜索

AI Day 2021 定型感知为 HydraNet（九头蛇网络）：**一个共享 backbone，多个任务头**。此前二十余个网络各自独立，图像特征重复计算；HydraNet 把车辆检测、车道线、红绿灯、交通标志、可行驶区域统一挂载于同一 backbone，单次前向出全部结果。输出为车体坐标系下的向量空间表示，感知与规划仍分两个模块。

规划侧在 2021 年偏传统，AI Day 上演示了搜索算法的三段演进：

| 方案 | 搜索扩展节点数 |
| --- | --- |
| 基础 A* | 约 44,000 |
| A* + 导航路线启发 | 约 22,000 |
| 神经网络引导的蒙特卡洛树搜索（MCTS） | 少于 300 |

（三档数字取自 AI Day 2021 演讲视频的公开复盘，以视频字幕口径为准；同复盘博客正文另有 A* “近 400,000 次扩展”写法。）

2021 年特斯拉规划器是 MCTS：神经网络提供先验，搜索在候选轨迹中选择。感知为神经网络、规划是搜索算法，二者靠人工编写的代价函数衔接——这是 2022 年后全部演进的起点。

## 3. AI Day 2022：Occupancy Network 逐层拆解

2022 年 CVPR 和 AI Day，特斯拉发布了 Occupancy Network——纯视觉路线里最够原创、也最被学术界花力气复现的一块：由 Phil Duan 创建（Ashok Elliswamy 负责方向与对外叙述，Phil 负责工程实现；媒体概括为"Ashok 讲特斯拉想去哪儿，Phil 讲怎么走到那儿"），思想源自机器人占据栅格建图。

### 3.1 为什么 3D 框不够

特斯拉的理由是**几何优先于本体论**（geometry over ontology）：

- 固定框装不了真实形状：卡车顶上的吊臂、侧面拖挂的货物超出 7×3 米框；体素不受形状假设约束，只回答"该格是否占据"。
- 类别局限：AI Day 例——一块托盘，数据集无"托盘"类别，输出仍为空，车随之碰撞；占据表示无类别维度，未知物体同样占据空间。
- 速度与遮挡：占据网络同时输出占据和运动流（occupancy flow），被遮挡区域的运动状态可从时序融合推出。

### 3.2 网络结构

公开结构从左到右读（细节以演讲图为准，参数量和分辨率从未公布）：

1. **Backbone**：8 路相机图像进 RegNet + BiFPN，当时的标准多尺度特征提取器；
2. **注意力模块**：位置编码与固定 query 输入注意力层，产出占据特征体（occupancy feature volume）。固定 query 与 DETR 系列可学习 query 同脉，差别在查询对象由"框"变为"体素是否占据"；
3. **时序融合**：当前特征体与历史（t-1、t-2……）融合，靠自车运动对齐，与 BEVFormer 的 temporal self-attention 解决同一问题（见第 8 节）；
4. **反卷积上采样**：输出**occupancy volume**（每体素占据概率）和 **occupancy flow**（每体素运动向量，色轮编码方向，红进蓝退灰静止）。

速度方面，公开复盘称超过 100 FPS（约为摄像头帧率三倍），未见于官方规格，属二手转述；确认的是按车载实时部署设计。特斯拉另以 NeRF 校验：离线三维重建比对在线占据体，借助车队平均消除雨雾噪声。

### 3.3 和学术界的关系

特斯拉 2022 年 6 月展示 Occupancy Network，此前 3 月 SUTD 与商汤的 OpenOccupancy 已先发；2023 年前后 TPVFormer、SurroundOcc、Occ3D、FB-OCC 密集跟进。两者无代码往来，问题定义与时序融合思路趋同（见第 10 节）。

## 4. 数据引擎：自动标注与 4D 重建

架构之外，数据管线是特斯拉的核心壁垒，AI Day 2021/2022 均以相当篇幅介绍，学术界基本无法复现。

- **Clip**：标注的最小单元是 45 秒-1 分钟的密集传感器片段，不是单帧图像；
- **自动标注**：对同一地点多次通过的车队数据做 4D 重建（早期类 NeRF，后期转几何管线），从视频计算三维真值，由离线大算力模型生成标注；
- **闭环**：影子模式捕捉人类接管与模型分歧片段回流为新训练 clip，人工只处理长尾；
- **算力规模**：AI Day 2022 的数字是训练集群约 1 万张 GPU，另约 4 千张专跑自动标注。

对照组 nuScenes：1000 场景 / 5.5 小时 / 140 万图像 / 39 万雷达帧，人工标注 3D 框与地图。**训练集规模差约四个数量级**（特斯拉按数百万 clip、每 clip 45-60 秒估算为数十万小时到百万小时，nuScenes 仅 5.5 小时）。两侧因此训练目标不同：特斯拉可从像素直出转向指令，学术界限于"图像至 3D 框"或"图像至 3 秒轨迹"。

## 5. 2023-2024：FSD v12，30 万行 C++ 的退场

端到端的转向有明确的技术推动者：Dhaval Shroff 提出并验证该思路，其表述被广泛引用——"不再用规则决定车辆的路径，而是用从数百万人类驾驶样本中学习的神经网络来决定"。二手复盘称其 2022 年 12 月于 Palo Alto 当面提案，缺乏一手佐证；可确认的是该思路成为 FSD v12 的技术路线。

MCTS 的人工代价函数（碰撞概率、舒适度、被接管可能性、类人程度四项加权）是规则体系的最后部分，端到端将其替代。2023 年 8 月 Musk 演示 v12，2024 年 3 月起大规模推送。官方更新说明中被引用最多的一句是：**单一端到端神经网络，从数百万视频片段训练，取代了 30 万行显式 C++ 规则代码**。

"端到端"常被误解为"更大的模型"，关键是训练方式：模块化中感知与规划各独立训练、损失不共享梯度；端到端则统一目标，梯度从最终轨迹回传至图像，感知表征直接由"是否利于规划"塑造。v12 仍保留 Occupancy 与多任务感知模块，只接入统一联合训练图，并非推翻重建。争点是：联合训练的内部权衡不可审计（黑箱），但中间各任务头仍可可视化。

## 6. 2024-2026：v13 到 v14，参数量、强化学习与视频基础模型

v13 于 2024 年底推送，口径为"36 Hz、全分辨率 AI4 视频输入"、原生适配 AI4，数据扩 4.2 倍、训练算力扩 5 倍；重点为接管率下降与更高分辨率输入；HW3 留在 v12.6 分支，两硬件线各自维护。v14 自 2025 年 10 月向 HW4 推送，发布前约 6 周（2025-08）预告**参数量提升 10 倍**，此后按月迭代；至 2026-09-23 最新为 **v14.3.10**（随软件版本 2026.27.10/2026.27.11 推送）。

v14.3.9 新增自动碰撞规避（Automatic Collision Evasion），检测到驾驶员注意力不足时激活 FSD 避险，官方标注**仅限 HW4**。v14.3.10 最具工程分量的一条不是模型能力而是工具链：用 MLIR 从零重写 AI 编译器与 runtime，官方给出反应时间加快约 20%；同一份说明把召唤、FSD 与 Robotaxi 三项功能统一到同一个模型上，并列出后续计划（把推理链扩展到目的地处理以外的全部行为、加入坑洼规避）。

v15 正在 Robotaxi 上跑早期版本，v14 负责人称"约 40% 的轨迹已合并到同一模型"，且 v15 将持续运行在 HW4 而非仅限 HW4+ 或 AI5（Q2 2026 电话会转述，二手）。v15 的可验证性与 v14 相同：只有接管率与里程，无基准成绩。

v14 的技术要点三项：

1. **强化学习进入训练管线**：2022 年规划器中四项手写代价（碰撞、舒适、接管、类人）由奖励函数替代，v14.3 更新说明原文为"升级 FSD 神经网络训练中的强化学习阶段"（upgrading the Reinforcement Learning stage of training the FSD neural network）。这是第 2、5 节所述路线的终点：规则 → 人类示例模仿 → 强化学习；
2. **视觉编码器升级**：v14.2 更新说明称"升级神经网络视觉编码器，用更高分辨率特征改善低可见度场景"；
3. **跨硬件蒸馏**：HW3 装不下 10 倍参数的模型，特斯拉将 HW4 模型蒸馏为 HW3 的"V14 Lite"，官方原文为"把 HW4 V14 的智能蒸馏到 HW3，从而把 HW4 上包括强化学习在内的改进带给 HW3"（Distilled the intelligence from HW4 V14 into HW3）。推送节奏：2026.20.5.1 首发（2026-06-29）→ 6 月下旬 wide release → 14.1 Lite（2026-08-26）→ 14.2 Lite（2026-09-19 与 23 日），HW3 的 Model S 与 Model X 于 9 月 23 日首次收到 14.2 Lite（存量很小）。同源双权重是量产约束下的典型处理；自动碰撞规避等新特性是否随蒸馏进入 Lite 分支，官方未逐项列明（二手口径称未进入）。

2026 年 CVPR DriveX Workshop 上，Phil Duan（个人网站口径为 Director of Engineering at Tesla AI，中文媒体另译"AI 工程总监"等）作《Self-Driving at Scale with Foundation Models》主题演讲。其个人网站履历：主导 Robotaxi 与 FSD v14，此前联合负责 v12/v13，带领数据与感知团队，创建 Occupancy Network，参与构建数据引擎。按其 slide，今日特斯拉感知是一个**视频基础模型**：8 路相机 36 Hz 进一个视觉编码器，出来一排任务头——动作、全景分割、3D 占据、3D 检测、人体网格、关键点跟踪、文字识别等。同一模型服务 FSD、智能召唤（ASS）和 Robotaxi 三个产品。

**该结构与 2021 年的 HydraNet 形态一致**：单一 backbone、多个任务头。五年间变化的是编码器规模、训练目标（人工代价 → 模仿 → RL）与数据量级，不变的是这一骨架。特斯拉 slide 上的表述是"用你关心的任务、用最大规模的数据训练"，即其一贯的多任务学习主张。

按公开资料整理，FSD 各版本分工：

| 人员 | 职务（公开口径） | 贡献 |
| --- | --- | --- |
| Ashok Elliswamy | VP of AI Software，向 Musk 汇报 | FSD 与 AI 团队整体负责人 |
| Phil Duan | Director of Engineering, Tesla AI | v12/v13 联合负责，v14 与 Robotaxi 主导；Occupancy Network 创建者 |
| Dhaval Shroff | Autopilot 工程师 | 端到端思路的提出与验证 |
| Andrej Karpathy | 前 AI 负责人（2022 年 7 月离职） | HydraNet、数据引擎等早期基础；离职早于 v12 |
| Elon Musk | CEO | 关键路线决策（v11→v12 转向端到端、v14 参数量提升等） |

**端到端并非特斯拉首创**，学术界与 NVIDIA 早有同类工作；特斯拉的贡献在于以百万级 clip 与闭环迭代将其推进至量产上车。第 11 节的 UniAD（CVPR 2023 最佳论文）公开时间即早于 v12。

### 6.1 规模口径：订阅、里程与 Robotaxi

算法讨论前要先有一个前置事实：这套系统实际跑了多少。官方与第三方口径的清单如下，定义各不同，混用即误判。

| 指标 | 数值 | 口径与时点 |
| --- | --- | --- |
| FSD 有效订阅数 | 148 万 | 含买断、剔除免费试用；2026 Q2 财报，同比 +56% |
| 北美新车 FSD 附加率 | 超过 55% | 2026 Q2 新交付中含 FSD 订阅的比例 |
| FSD（监督版）累计里程 | 接近 120 亿英里 | 全车队，2026 Q2 |
| 欧洲 FSD 累计里程 | 超过 5000 万公里 | 截至 2026 年 7 月；已获批国家含荷兰、立陶宛、爱沙尼亚、丹麦、比利时 |
| 付费 Robotaxi 累计里程 | 约 240 至 250 万英里 | 2026 Q2 末，**含带安全员的行程** |
| 无监督 Robotaxi 里程 | 38 万英里（Q2 电话会），9 月 3 日后超过 100 万英里 | 不含安全员行程 |
| Robotaxi 车队规模 | **未披露** | 第三方可得的仅为注册库数字，非运营车辆数 |
| 训练数据规模 | **未披露** | 从未公布片段总量或帧数 |

Robotaxi 口径多：官方宣称美国七城，Austin、Dallas、Houston、Miami、Orlando、Tampa 六城跑无监督，旧金山湾区需主驾安全员，Phoenix 与 Las Vegas 标"准备中"；2026 年新增 Dallas/Houston（4 月）、Miami（7-3）、Tampa/Orlando（7-21）。Cybercab 于 9-3 在 Austin 非公开活动发布并限区载客，NHTSA 正在评估；Austin 注册库 409 辆 Model Y + 67 辆 Cybercab（第三方统计）。

里程数字不能互加：240 万英里是含安全员的商业化全量口径，100 万英里是 9 月起的无监督口径，不能用全车队 120 亿英里除以得"无监督占比"。参照：Waymo 截至 2026 年 3 月底无监督里程已超 2.2 亿英里（路透社引第三方分析）。两个数量级差距意味着现有公开里程不足以支撑"是否已验证"的任何结论。

国内侧见第二篇《国产智驾大横评》。此处两条：蔚来 2026 年 4 月公开论坛明确表示无进入该领域的计划；小鹏与吉利分别停留在测试资质与量产计划阶段，均无收费运营数据。

## 7. 芯片这条暗线：HW3、HW4 到 AI5

算法演进始终受"在几十瓦、几十美元的车规芯片上实时运行"的约束，这解释了它比学术界更早放弃稠密 BEV 网格。

| 硬件 | 时间 | 算力（公开口径） | 备注 |
| --- | --- | --- | --- |
| HW3（FSD 芯片） | 2019 量产 | 双 NPU 合计约 144 TOPS | 14nm，自研起点 |
| HW4 / AI4 | 2023 起 | 官方从未公布 TOPS 绝对值 | Musk 口头称约为 HW3 的 4 至 5 倍；16GB 内存，256GB 存储 |
| AI4+ / HW4 Plus | 2026-04 宣布，2027 年中投产 | 算力 +10%、内存带宽 +10% | 每 SoC 内存 16GB 增至 32GB（合计 64GB）；无老车主升级方案 |
| AI5 | 2026-04 完成设计流片 | 报道称 2000+ TOPS，约 AI4 的 8 倍 | 官方在 Q2 电话会称预计 2027 年中量产，且初期先用于 Optimus |

**特斯拉从未官方公布任何车端芯片的 TOPS 绝对值。** 网传 AI4 为 50-280 TOPS、HW3 单芯片约 72 TOPS、AI5 的"2000-2500 TOPS"均为第三方估算。官方只给倍数口径（AI4 约 HW3 的 4-5 倍，AI5 约 AI4 的 8 倍）与定性定位（AI5 对标 H100 级推理）。表中 HW3 的 144 TOPS 属早期公开材料，其余均为倍数或定性。

![HW3、HW4/AI4、AI4+ 与 AI5 的硬件演进与算力口径](images/tesla-academia-2026/s02-chip-timeline.svg)

图 2｜车端硬件演进（实线段=已量产或已发布，虚线段=规划且时间点未确证）。AI5 的算力与时间点均为报道口径，官方未公布完整规格表。

这些数字指向同一约束：车端须同时跑 10 倍参数的端到端模型、占据网络与各任务头，并预留 36 Hz 实时余量——因此必须稀疏化、蒸馏化、与芯片联合设计。学术界在 A100 上单卡单 batch 训练、不受此约束，双方架构分歧由此获得物理层面解释。

## 8. 学术界的平行线（一）：DETR3D、BEVDet、BEVDepth 与 BEVFormer

学术界无车队数据，但有公开基准与可复现代码两项特斯拉不具备的条件。2021-2022 年间，"多相机图像 → BEV"路线密集推进。

**DETR3D**（CoRL 2021，PMLR v164）是首批将 DETR 推广至 3D 的代表：一组可学习 3D 框 query 投影到各相机采样特征、迭代细化。它验证了"稀疏 query + 图像采样"的可行性，但缺少显式 BEV 表征、仅限单帧。

**BEVDet**（2021 末）走另一路径：以 Lift-Splat-Shoot 把图像特征显式投影到 BEV 网格再在 BEV 上检测，确立了"先建 BEV 再做任务"。代价是深度不准时 BEV 随之失真，故有 **BEVDepth**（AAAI 2023）：训练以激光雷达点云提供稠密深度监督（推理不用激光雷达），把深度估计从网络自拟变为显式监督。BEVDepth 在 nuScenes 测试集取得 50.3% mAP、60.0% NDS，一度居纯视觉首位（论文报告口径，未经第三方复算）。

**BEVFormer**（ECCV 2022，本专栏起因的那篇）把整件事统一成一个时空 Transformer，也是学术界对特斯拉 2021-2022 方案最完整的一次公开复现。三个部件：

1. **BEV query**：一张 $H \times W$ 网格铺在车周围（base 为 200×200，范围 $\pm 51.2$ m，每格约 0.5 m），每格一个可学习 query，代表该位置的 BEV 特征；
2. **空间交叉注意力**：每格在高度方向取 4 个参考点（`num_points_in_pillar=4`），投影至 6 路相机图像，经可变形注意力（MSDeformableAttention，每参考点采 8 点）从多尺度 FPN 采样特征。即"图像至 BEV"的可微实现，以稀疏采样规避全图注意力开销；
3. **时序自注意力**：上一帧 BEV 按自车运动旋转平移对齐后，用可变形注意力在邻域采样融合。对应特斯拉 Occupancy 的时序融合，解决同一问题：速度估计和遮挡。

三部件与每帧采样次数见下图（右半为两种注意力算法的量级对照）：

![BEVFormer 的三个部件与每帧采样次数的计算量账本](images/tesla-academia-2026/s03-bevformer-compute.svg)

图 3｜BEVFormer 三部件与计算量账本。像素数取 nuScenes 相机分辨率的量级估算，用于对照而非精确计算。

配置文件里几个数字直接决定了它的显存（`projects/configs/bevformer/bevformer_base.py`）：

```python
bev_h_, bev_w_ = 200, 200        # BEV 网格分辨率
queue_length = 4                  # 一个序列 4 帧
samples_per_gpu = 1               # 每卡 batch = 1
num_query = 900                   # 检测头 query 数
num_layers = 6                    # encoder 6 层
num_points_in_pillar = 4          # 每列参考点
# deformable attention: num_points = 8
total_epochs = 24
lr = 2e-4
```

全图注意力是 $O(HW\cdot\text{pixels})$，不可行；可变形注意力压至 $O(HW\cdot4\cdot8)$，即每格仅采 32 点，使模型能在 A100 上跑。代价是采样点由学习得到、缺乏全局视野，信息需靠 6 层 encoder 逐层补。时序自注意力沿用同机制，query 是当前帧 BEV 格子，key/value 为按自车运动对齐后的上一帧 BEV（`rotate_prev_bev`、`use_shift`、`use_can_bus`），邻域采 8 点；同一车在两帧 BEV 中的位置差让网络学到运动状态，mAVE 因此下降约一半。

参数总开销：注意力与 BEV 特征图显存随网格面积平方，$200^2/150^2\approx1.78$、$200^2/50^2=16$；但实测显存并非按此比例（tiny 6.5 GB → base 28.5 GB，约 4.4 倍），因主要开销还含 backbone、图像特征缓存与 4 帧图像队列。网格越大边际成本越高。这也是 Model Zoo 三档的依据：tiny 的 50×50 验证 pipeline，base 的 200×200 对应论文指标。

![每卡训练显存与网格点数的倍数对照](images/tesla-academia-2026/s04-memory-vs-grid.svg)

图 4｜显存与网格面积的倍数对照。网格面积 16 倍对应显存 4.4 倍，差额来自 backbone、图像特征缓存与 4 帧图像队列。

官方 Model Zoo 的三档配置与真实训练显存：

| 配置 | 网格 | 帧队列 | NDS / mAP（nuScenes val） | 训练显存（每卡） |
| --- | --- | --- | --- | --- |
| BEVFormer-tiny (R50) | 50×50 | 3 | 35.4 / 25.2 | 约 6.5 GB |
| BEVFormer-small (R101-DCN) | 150×150 | 3 | 47.9 / 37.0 | 约 10.5 GB |
| BEVFormer-base (R101-DCN) | 200×200 | 4 | 51.7 / 41.6 | 约 28.5 GB |

base 在 val 上对比 DETR3D（R101：42.5 NDS）提升 9.2 个点，主要来自时序融合带来的速度估计（mAVE 从 0.842 降到 0.394，速度误差减半以上）。论文级最佳 56.9 NDS 用 V2-99 backbone 加额外预训练取得。社区口径训练成本为 8×A100 约两天（约 16 GPU-天）；官方 Model Zoo 未给训练时长，仅给单卡显存 28.5 GB。

必须说明一点：这套代码绑定 2022 年的 mmdet3d 0.x / mmcv 1.x 生态（CUDA ≤ 11.3、PyTorch ≤ 1.12），4090 及更新显卡上编译 mmcv 要打补丁。这是该时期仓库的普遍问题，也是第 15 节实操建议的由来。

## 9. 学术界的平行线（二）：稀疏化的 StreamPETR、Sparse4D 与 SparseBEV

BEVFormer 的稠密网格有个天生的账要算：200×200 的网格里绝大多数格子是空的（荒地、天上），却都要算注意力。2023 年起主流转向**稀疏 query**：不做全局网格，只让 query 跟着物体走。这恰是车端算力约束下的必然选择，和特斯拉方向殊途同归。

**StreamPETR**（ICCV 2023）核心是把时序信息在 query 之间传播：上一帧 query 经自车运动变换直接作为下一帧初始 query，目标中心表征随时间延续。收益在于时序建模成本随 query 数量而非空间分辨率增长：序列拉长到 4+ 帧时既不需像 BEVFormer 那样对齐维护整张 BEV 网格，也不引入随帧数膨胀的稠密特征——这是其显存显著低于 BEVFormer 的结构性原因（定量对照见第 8 节）。官方数字：

| 模型 | 训练 | NDS / mAP（val） | FPS（PyTorch） |
| --- | --- | --- | --- |
| StreamPETR (V2-99, 900q) | 13 小时 | 57.1 / 48.2 | 12.5 |
| StreamPETR (R50, 90ep) | 36 小时 | 53.7 / 43.2 | 26.7 |
| StreamPETR (R50, 428q + nuImg) | 26 小时 | 54.6 / 44.9 | 31.7 |
| StreamPETR-Large（测试集） | — | 67.6 / 62.0 | — |

首行意义：首个在线多相机方法在测试集上达到激光雷达基线。显存与速度均优于 BEVFormer-base，这是稀疏化的直接收益。训练时长口径不同，不严格可比：README 标称均在 8×2080Ti 上进行，而 BEVFormer 的"两天"出自社区（8×A100，折合 16 GPU-天）。

**Sparse4D**（2022-11 arXiv 首发，v2/v3 迭代到 2023 年，后发表 TPAMI 2026）走"稀疏 anchor + 多视角特征采样"：v2 改递归时序融合进一步压延迟与显存，v3 加稠密深度辅助，工业界落地最多（地平线车端有部署）。**SparseBEV**（ICCV 2023 → TPAMI 2026）回应"稀疏 query 丢失稠密上下文"的批评，提出自适应稀疏采样：由 query 依内容决定采样位置，以较小集合逼近稠密 BEV。Model Zoo：r50 在 8×2080Ti 训 21 小时，val NDS 55.6、15.8 FPS；r101 高分辨率配置 val NDS 59.2；另有 EVA02/ViT 大 backbone 配置，测试集 NDS 达 70.2。

**Far3D**（AAAI 2024）面向远距离小目标，megvii-research/Far3D 开源。它们连同 BEVNeXt（CVPR 2024，论证稠密 BEV 仍具竞争力）与 RecurrentBEV（ECCV 2024，25.6 FPS 下 44.5 mAP），构成对 BEVFormer 的系统修正：时序融合必要且收益最大，稠密网格可省，query 应稀疏。

## 10. 学术界的平行线（三）：Occupancy 的公开复现

与特斯拉 Occupancy 对应的学术界工作在 2022-2023 年集中出现，均开源：

| 工作 | 时间 | 贡献 |
| --- | --- | --- |
| OpenOccupancy | 2022 | 首个大规模语义占据 benchmark，给 nuScenes 扩展稠密占据标注 |
| TPVFormer | CVPR 2023 | 三平面（tri-plane）表征替代体素，把 $O(N^3)$ 压到近 $O(N^2)$ |
| SurroundOcc | 2023 | 多相机稠密占据预测 + 数据生成管线，引用近 600 |
| Occ3D | 2023 | 大规模占据预测 benchmark（nuScenes 扩展，含激光雷达真值） |
| OccNet | ICCV 2023 | CVPR 2023 占据挑战赛方案，"场景即占据"统一表征 |
| FB-BEV / FB-OCC | NVIDIA | 前向-后向视角变换，同时做检测与占据 |
| SparseOcc | 2024 | 全稀疏占据架构，与 SparseBEV 同一方向 |

该方向与特斯拉的差异在真值来源：特斯拉以 4D 重建自建真值，学术界以激光雷达累积点云投至体素做真值（Occ3D、OpenOccupancy 同思路）。**以激光雷达监督纯视觉模型，是学术界规避"缺少车队数据"的关键方法**，与 BEVDepth 以点云监督深度同思路。

## 11. 学术界的平行线（四）：UniAD 与端到端规划

FSD v12 公开前一年，学术界已有端到端方案。**UniAD**（CVPR 2023 最佳论文，OpenDriveLab）将感知、跟踪、建图、预测、规划合一于单一网络，明确"以规划为导向"。其显存开销在官方文档中列示：

- 第一阶段（感知模块）：**约 50 GB**，8×A100 训练 6 epoch 约 2 天；`queue_length` 由 5 降至 3 可压缩至约 30 GB，可运行于 V100 32GB；
- 第二阶段（联合训练）：**约 17 GB**，8×A100 训 20 epoch 约 4 天，冻结了 BEV encoder，3090/V100 都能跑。

**VAD**（ICCV 2023，华科 + 地平线）是 UniAD 的效率改进版：全场景矢量化表示（车道线、车辆均为向量而非栅格），去稠密栅格计算开销，规划指标更优：

| 方法 | L2 (m) 1s / 2s / 3s | 碰撞率 (%) 1s / 2s / 3s | FPS |
| --- | --- | --- | --- |
| ST-P3 | 1.33 / 2.11 / 2.90 | 0.23 / 0.62 / 1.27 | 1.6 |
| UniAD | 0.48 / 0.96 / 1.65 | 0.05 / 0.17 / 0.71 | 1.8 |
| VAD-Base | 0.41 / 0.70 / 1.05 | 0.07 / 0.17 / 0.41 | 4.5 |
| VAD-Tiny | 0.46 / 0.76 / 1.12 | 0.21 / 0.35 / 0.58 | 16.8 |

该方向后续工作（至 2026 年）：**VADv2**（概率规划，ICLR 2026 录用）、**SparseDrive**（全稀疏端到端，49.6 mAP，超 UniAD 11.6 个点）、**DiffusionDrive**（CVPR 2025，扩散模型生成多模态轨迹）、**RAD**（NeurIPS 2025，3DGS 环境中执行强化学习后训练）。其中 RAD 意味着学术界同样引入了对驾驶策略的强化学习后训练，与特斯拉 v14 路线趋同。

与特斯拉的实质差异在监督信号：UniAD/VAD 以 nuScenes 中 3 秒的人类轨迹做开环模仿学习，特斯拉使用数百万 clip 与强化学习。第 13 节分析该差异对评测的影响。

## 12. 正面对照：逐模块比较

前 11 节可归纳为一张对照表，同一行对应同一问题的两种做法：

| 维度 | 特斯拉（AI Day 口径 + 版本说明） | 学术界（开源可复现） |
| --- | --- | --- |
| 图像特征 | RegNet + BiFPN（2022）→ 视频基础模型（2026） | ResNet-50/101-DCN、VoVNet、EVA02、ViT |
| 3D 表征 | Occupancy 体素 + 占据流（实时，复盘口径 100+ FPS） | BEV 网格（BEVFormer）或 稀疏 query（StreamPETR/Sparse4D）；Occ3D 系列复现占据 |
| 图像→3D 的注意力 | 位置编码 + 固定 query 的注意力模块（未开源，细节有限） | 空间交叉注意力：4 参考点 × 8 采样点，投影到 6 相机采 FPN 特征 |
| 时序融合 | 4D 占据栅格，按自车运动对齐 | temporal self-attention（BEVFormer，队列 4 帧）/ query 传播（StreamPETR） |
| 规划 | MCTS + 手写代价（2021）→ 端到端模仿（v12）→ 强化学习（v14） | UniAD 开环 L2 模仿 → VAD 矢量化 → RAD 强化学习后训练 |
| 监督来源 | 4D 重建自动标注，车队规模，约 4 千 GPU 专职标注 | 人工标注 nuScenes：1000 场景 / 5.5 小时；激光雷达投影当占据与深度的老师 |
| 数据规模 | 量级上大 4 个数量级（数百万 clip） | nuScenes 训练约 700 场景（约 140 万图） |
| 训练算力 | 约 1 万 GPU 训练集群 | 8×A100 两天（BEVFormer-base）到 8×A100 六天（UniAD 两阶段） |
| 推理硬件 | HW3 144 TOPS → AI5 报道称 2000+ TOPS，几十瓦 | 数据中心 A100/3090，不受功耗约束 |
| 评测 | 无公开基准，以接管率与真实里程为指标 | nuScenes NDS/mAP、开环 L2/碰撞率、CARLA 闭环 |
| 代码 | 零 | 全部开源，Model Zoo 带权重 |

表中最关键的两项差异是**监督来源**与**推理硬件**。学术界架构创新（稀疏 query、矢量化、轻量 BEV）是在无车端功耗约束、仅 5.5 小时数据的条件下完成的；特斯拉工程创新（自动标注、蒸馏、多任务共享）则是在数据充裕但必须满足几十瓦实时约束的条件下完成。两条路线各自受制于自身短板，最终在"稀疏 + 多任务 + 时序"的交集趋同，如下图：

![两条路线的约束差异与最终交集](images/tesla-academia-2026/s06-constraint-divergence.svg)

图 6｜约束差异与交集。横向比较每一行而非整体排名：特斯拉在数据与闭环上领先，学术界在可复现性上领先，共同短板是缺少统一第三方评测。

以下是同基准（nuScenes，避免跨基准比较）的直接对比：

| 方法 | 年份 | 代码 | NDS | 备注 |
| --- | --- | --- | --- | --- |
| FCOS3D | 2021 | 开源 | 42.8（test mAP，官方仓库表） | 单帧，无 BEV；官方未列 NDS |
| DETR3D | 2021 | 开源 | 47.9（test，V2-99） | 稀疏 query 开山 |
| BEVFormer-base | 2022 | 开源 | 51.7（val，R101-DCN）；56.9（test，V2-99） | 时空 BEV，28.5 GB 显存 |
| BEVDepth | 2023 | 开源 | 60.0（test） | 激光雷达深度监督 |
| StreamPETR-Large | 2023 | 开源 | 67.6（test） | 官方 README：首个在线多相机方法追平激光雷达基线（62.0 mAP / 67.6 NDS / 65.3 AMOTA） |
| SparseBEV（EVA02 版） | 2023-2026 | 开源 | 70.2（test） | 稀疏采样 + 大 backbone |
| 特斯拉 | 2022-2026 | 闭源 | 不参赛 | 无公开数字 |

（同类对照常混列 val 与 test 成绩，本表两侧均标注口径，跨行比较需留意。）

![nuScenes 同基准成绩条形图，按 val、test 与其他指标着色](images/tesla-academia-2026/s05-nuscenes-benchmark.svg)

图 5｜nuScenes 同基准成绩。FCOS3D 的 42.8 为 mAP，与 NDS 不同量纲；同一方法换 backbone 即可跨档，故排名反映配置而非路线。

特斯拉未在任何公开基准上提交过成绩，表末行始终为空。这是本次对照最根本的不对称：**学术界以分数为评价体系，特斯拉以接管率为评价体系，两者间无换算关系**。

## 13. 评测的分裂：NDS、L2、闭环与接管率

两种评价体系无法换算，原因在于其测量对象不同。

**NDS/mAP 评价感知**。nuScenes 的 NDS 是加权和：

$$\mathrm{NDS} = \frac{1}{10}\left[5\,\mathrm{mAP} + \sum_{\mathrm{mTP}\in\mathrm{TP}} \bigl(1 - \min(1,\mathrm{mTP})\bigr)\right]$$

五个 TP 项分别为平移、尺度、朝向、速度、属性误差。该指标只反映检测精度，不关规划。BEVFormer 将 mAVE 由 0.842 降至 0.394 从而提升 NDS，但它本身不具驾驶能力。

**开环 L2 评价模仿**。UniAD/VAD 的规划指标协议：以 nuScenes 一段人类驾驶为输入，前 2 秒给模型，预测后 3 秒轨迹，与真实轨迹算 L2。三项学界质疑：

1. **惩罚偏离**：模型选择更安全但与人类不同的路线，仍受 L2 惩罚；
2. **无交互**：不还原其他交通参与者的响应，模型对旁车的影响不反馈进评价；
3. **上限受限于人类**：最优结果为"完全复刻人类"，而 nuScenes 中的人类驾驶本身亦存在平庸操作。

UniAD 仓库为此设 Planning Metric 讨论（issue #29）。CARLA 闭环（VAD 在 Town05 Long 上 Driving Score 30.31，对比 ST-P3 的 11.45）是学术界可提供的更接近真实的评价，但 CARLA 交通模型与真实世界长尾仍有数量级差距。

**接管率衡量的是系统整体**。特斯拉采用每千英里接管次数、真实事故率作为指标，将感知、规划、控制、数据、迭代速度纳入统一核算。优点是直接对应产品表现，局限在于不可复现、不可审计，外界只能依赖其单方公布。

因此"特斯拉与学术界孰优孰劣"目前并无定论：**学术界优势在可复现与可归因（各模块贡献可经消融分离），特斯拉优势在闭环指标与迭代速度**。研究者可以复现 BEVFormer 的每一项数字，但无法验证特斯拉公布的接管率。

### 13.1 2024-2026：评价体系的迁移与新基准

评价体系的分裂在 2024-2026 年间出现部分缓解，原因不是标准统一，而是基准本身换代。以下三类变化直接决定前文数字的可比性边界。

**开环基准的开环化终结**。2022-2023 年 nuScenes 的 L2 协议被广泛质疑后，社区转向"用仿真替代真实数据"。NAVSIM v1（NeurIPS 2024）以非反应式仿真 + PDMS 指标把开环评测改造成可控、可重复的准闭环；NAVSIM v2（CoRL 2025）加反应式背景交通与合成新视角，并支撑 AGC 2025。nuPlan 提供 1200 小时、四城的规划基准；CARLA Leaderboard 2.0 与 Bench2Drive（NeurIPS 2024）承担闭环端到端评测。需说明：不存在官方"nuScenes 2.0"，相关说法未找到一手来源。

**世界模型从生成走向度量。** Wayve 的 GAIA 系列最完整：GAIA-1（2023）建立生成式驾驶世界模型；GAIA-2（2025-03）转潜扩散、多视角与可控生成；GAIA-3（官方博客 2025-12）达 150 亿参数，训练算力与数据约为 GAIA-2 的五倍与十倍，覆盖九国，定位从"生成"转向"安全评估"，可生成 NCAP 式安全场景；GAIA-4（2026-08）把 AI Driver 放入回路做闭环安全度量。学术同期：ViDAR（CVPR 2024）以视觉点云预测做预训练；Raw2Drive（NeurIPS 2025）是对齐世界模型的 RL 端到端驾驶；占据方向有 SparseOcc（ICCV 2023，全稀疏体素 query）、RenderOcc（ECCV 2024，二维渲染监督替代稠密三维标签）、GDFusion（CVPR 2025，统一梯度下降视角的时序融合）、ProtoOcc（CVPR 2025，低分辨率 query 加原型感知视角变换）。

**对本文结论的影响有两条。** 其一，第 8-12 节的 nuScenes 数字仍是感知与开环规划的事实基准，但不足以代表 2026 年的能力上限，跨工作比较须同时注明基准与口径。其二，世界模型把"生成"变成"度量工具"，与特斯拉用 NeRF 校验占据网络、理想用仿真做闭环强化学习同属一类做法：把物理一致性引入训练与验证闭环，是第 4 节数据引擎论点最直接的后续印证。

## 14. 2026 年的合流：VLA、世界模型与开源教师模型

2025-2026 年间，两条路线出现明显趋同，可归纳为四项信号：

1. **特斯拉向学术界靠拢**：CVPR 2026 DriveX keynote 把感知统称为"视频基础模型"，多任务头与共享编码器的表述与学术界的 multi-task foundation model 叙事一致；Phil Duan 在学术 workshop 公开演讲，前所未有；
2. **学术界向特斯拉靠拢**：VAD（ICLR 2026）、RAD（NeurIPS 2025，RL 后训练）、Raw2Drive（NeurIPS 2025）、DiffusionDrive（CVPR 2025 Highlight）对应的正是特斯拉 v12→v14 路径：从模仿学习到生成式规划、再到强化学习；
3. **VLA 与世界模型成新主线**：国内厂商 2025-2026 密集发布（理想公开世界模型 + RL 闭环训练路线，小米 2026 年 5 月开源 OneVL，融合 VLA 与世界模型）；学界有 VLA-World（arXiv 2026）、DriveWorld-VLA（ICML 2026）；
4. **"开源教师模型"**：NVIDIA 2026 年 1 月发布 Alpamayo 家族，核心 Alpamayo 1 为 100 亿参数推理型 VLA，权重开放，官方定位非部署上车而作教师蒸馏至各家系统；配套 AlpaSim 仿真框架（开源）与 1700+ 小时开放驾驶数据。

第 4 点意义最突出："大模型作教师、蒸馏至车端小模型"，正是特斯拉对 HW4→HW3 的处理方式（V14 Lite），特斯拉早五年验证的工程路径如今被头部厂商以开源生态推广。若说 2022 年的格局是"特斯拉 vs 学术界"，2026 年已转成"闭源全栈 vs 开源拼图"：后者尚无法企及前者的数据规模，但模型、仿真、数据三个缺口正被逐个补齐。

## 15. 实践指南：方案选型与显存需求

将各节运行要求对应到具体显卡（训练，batch=1，官方配置）。表中标注"官方"的显存取自 README 的 Model Zoo 实测值，标注"经验值"的为社区实践口径，与"建议显存"一列同属工程参考：

| 目标 | 最低显存 | 建议显存 | 备注 |
| --- | --- | --- | --- |
| BEVFormer-tiny 推理 | 8 GB（经验值） | 12 GB | R50，50×50 网格 |
| BEVFormer-tiny 训练 | 6.5 GB（官方） | 16 GB | README 标 6500M，有 fp16 配置可用 |
| BEVFormer-small 训练 | 10.5 GB（官方） | 24 GB | README 标 10500M，R101-DCN |
| BEVFormer-base 训练 | 28.5 GB（官方） | 32 GB | README 标 28500M；8×A100 两天为社区口径 |
| StreamPETR (R50) 训练 | 16 GB（经验值） | 24 GB | 官方 36 小时（8×2080Ti），成本低于 base |
| SparseBEV (r50) 训练 | 16 GB（经验值） | 24 GB（或 8×2080Ti） | 官方标注 21 小时（8×2080Ti） |
| UniAD 第一阶段 | 30 GB（queue=3） | 50 GB | 官方建议 8 卡，默认 queue=5 约 50 GB |
| UniAD 第二阶段 | 17 GB | 24 GB | 官方文档，冻结 BEV encoder，3090 可跑 |
| VAD-Base 训练 | 24 GB（经验值） | 40 GB | 推理仅 4.5 FPS（研究代码） |

选型建议分三种情况：

- **以理解论文为目标**：运行 StreamPETR 或 BEVFormer-tiny 的 demo，推理显存 10 GB 以内，一日内可获得可视化结果；
- **以出成果为目标**：StreamPETR / SparseBEV 起步，同基准下与 BEVFormer 直接对比，训练成本低一个量级，代码生态亦更新（BEVFormer 的 mmcv 1.x 在新卡上编译是长期存在的问题）；
- **以研究规划为目标**：选 VAD 而非 UniAD，前者更轻量、指标更优，且已接入 CARLA 闭环；UniAD 仅在需要复现其两阶段训练流程时适用。

环境层面需提前说明：这批代码绝大多数绑定 mmdet3d 0.x + mmcv-full ≤ 1.6，属于 CUDA 11.3 时代的产物。4090（sm_89）、Blackwell 架构显卡需自行修补 mmcv 编译，DeepSpeed 与梯度检查点是 24 GB 显存跑 base 配置的必要手段。

## 16. 总结

将五年时间线归纳为三点：

1. **特斯拉持续"去规则化"**：手工特征 + 2D 检测（2016）→ HydraNet + MCTS 手写代价（2021）→ Occupancy + 4D 自动标注（2022）→ 端到端模仿（2024）→ 强化学习 + 十倍参数 + 跨硬件蒸馏（2025-2026）。每步以学习所得替代上一步人工设计，骨架与 2021 年一致；
2. **学术界对各个环节均有开源对应物**：BEVFormer + 时空 BEV，Occ3D 系列 + 占据预测，UniAD/VAD + 端到端，RAD + RL。复现价值在可归因：特斯拉报告只给"接管率下降"，学术界可给"时序融合贡献 mAVE 0.45、稀疏化节省 60% 显存"这类可消融结论；
3. **实质差距在数据与闭环，不在架构**。学术界架构甚至更激进（稀疏、全稀疏、矢量化、扩散），但 nuScenes 5.5 小时训出的模型，与数百万 clip、RL 加闭环迭代的系统不属同一量级。2026 年开源教师模型潮（Alpamayo 等）正在补这一环，但数据与真实里程积累短期难逾越。

第二篇《国产智驾大横评》把同一对照方法移回国内，看华为、小鹏、理想、蔚来、比亚迪、小米、吉利七家 2024-2026 年的技术选择与量产口径。两篇合看：模型范式已趋同（端到端、VLA、世界模型、强化学习），而验证方式、数据披露口径仍分属两套体系。

代码层面拆解另行成文，候选 StreamPETR 的 query 传播与 SparseBEV 的自适应采样。

## 17. 参考资料

**特斯拉侧（全部公开来源）**

- Tesla AI Day 2021 演讲（HydraNet、MCTS 规划、自动标注）
- Tesla AI Day 2022 演讲（Occupancy Network、自动标注集群）
- Think Autonomous: [Tesla's FSD Architecture: From HydraNets to End-To-End](https://www.thinkautonomous.ai/blog/tesla-end-to-end-deep-learning/)、[A Look at Tesla's Occupancy Networks](https://www.thinkautonomous.ai/blog/occupancy-networks/)
- FSD v12 官方更新说明（"单一端到端神经网络取代 30 万行 C++"）、v14.2/v14.3 更新说明（版本与说明存档见 [Not a Tesla App](https://www.notateslaapp.com/software-updates)）
- Phil Duan, CVPR 2026 DriveX Workshop Keynote: *Self-Driving at Scale with Foundation Models*（[视频](https://youtu.be/cjzFjeSmh8M)，入口亦见 [腾讯新闻](https://news.qq.com/rain/a/20260807A03IBX00)）
- [philduan.com](https://www.philduan.com/)（Phil Duan 履历一手来源：Director of Engineering at Tesla AI，co-led v12/v13、主导 v14 与 Robotaxi、创建 Occupancy Network）
- NVIDIA 新闻稿：[Alpamayo 开源模型家族](https://nvidianews.nvidia.com/news/alpamayo-autonomous-vehicle-development)（2026-01-05）

**学术侧（论文与官方仓库）**

- BEVFormer: [arXiv:2203.17270](https://arxiv.org/abs/2203.17270) / [fundamentalvision/BEVFormer](https://github.com/fundamentalvision/bevformer)
- DETR3D ([arXiv:2110.06961](https://arxiv.org/abs/2110.06961))、BEVDet（[arXiv:2112.11797](https://arxiv.org/abs/2112.11797) / [HuangJunJie2017/BEVDet](https://github.com/HuangJunJie2017/BEVDet)）、BEVDepth（[arXiv:2206.10092](https://arxiv.org/abs/2206.10092) / [Megvii-BaseDetection/BEVDepth](https://github.com/Megvii-BaseDetection/BEVDepth)）
- StreamPETR: [arXiv:2303.11926](https://arxiv.org/abs/2303.11926) / [exiawsh/StreamPETR](https://github.com/exiawsh/StreamPETR)（数字取自其 Model Zoo）
- SparseBEV: [arXiv:2308.09244](https://arxiv.org/abs/2308.09244) / [MCG-NJU/SparseBEV](https://github.com/MCG-NJU/SparseBEV)（TPAMI 2026）
- Sparse4D: [arXiv:2211.10581](https://arxiv.org/abs/2211.10581) / [HorizonRobotics/Sparse4D](https://github.com/HorizonRobotics/Sparse4D)
- Far3D: [megvii-research/Far3D](https://github.com/megvii-research/Far3D)
- UniAD: [arXiv:2212.10156](https://arxiv.org/abs/2212.10156) / [OpenDriveLab/UniAD](https://github.com/OpenDriveLab/UniAD)（显存数字取自其 GPU Requirements 一节）
- VAD / VADv2 / RAD / DiffusionDrive: [arXiv:2303.12077](https://arxiv.org/abs/2303.12077)（VAD）、[arXiv:2403.03347](https://arxiv.org/abs/2403.03347)（DiffusionDrive）、[hustvl/VAD](https://github.com/hustvl/VAD)；SparseDrive: [arXiv:2405.19620](https://arxiv.org/abs/2405.19620)
- Occupancy: OpenOccupancy ([arXiv:2203.01274](https://arxiv.org/abs/2203.01274))、SurroundOcc ([arXiv:2303.09551](https://arxiv.org/abs/2303.09551))、Occ3D ([arXiv:2306.02851](https://arxiv.org/abs/2306.02851))、[OpenDriveLab/OccNet](https://github.com/OpenDriveLab/OccNet)、[NVlabs/FB-BEV](https://github.com/NVlabs/FB-BEV)
- VLA 与世界模型: VLA-World ([arXiv:2604.09059](https://arxiv.org/abs/2604.09059))、DriveWorld-VLA ([arXiv:2602.06521](https://arxiv.org/abs/2602.06521))、OneVL ([xiaomi-research/onevl](https://github.com/xiaomi-research/onevl))
- 综述与追踪：[OpenDriveLab/Birds-eye-view-Perception](https://github.com/OpenDriveLab/Birds-eye-view-Perception)、[isLinXu/paper-list](https://github.com/isLinXu/paper-list)、[LMD0311/Awesome-World-Model](https://github.com/LMD0311/Awesome-World-Model)
- 数据集：[nuScenes](https://www.nuscenes.org/)（1000 场景 / 5.5 小时 / 140 万图）、[nuPlan](https://www.nuscenes.org/nuplan)（1200 小时 / 4 城规划基准）
- 新基准与评测：NAVSIM v1（[arXiv:2406.15349](https://arxiv.org/abs/2406.15349)）与 v2（[arXiv:2506.04218](https://arxiv.org/abs/2506.04218)）、Bench2Drive（Bench2Drive-VL：[arXiv:2604.01259](https://arxiv.org/abs/2604.01259)）、[Autonomous Grand Challenge 2025](https://opendrivelab.com/challenge2025/)
- 世界模型与强化学习：Wayve GAIA-3（[官方博客](https://wayve.ai/thinking/gaia-3/)）与 GAIA-4（[官方博客](https://wayve.ai/thinking/gaia-4/)）、ViDAR（[CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/html/Yang_Visual_Point_Cloud_Forecasting_enables_Scalable_Autonomous_Driving_CVPR_2024_paper.html)）、Raw2Drive（[NeurIPS 2025](https://openreview.net/forum?id=CAz7UGRdLs)）、SparseOcc（[arXiv:2312.17118](https://arxiv.org/abs/2312.17118)）、GDFusion（[arXiv:2504.12959](https://arxiv.org/abs/2504.12959)）、ProtoOcc（[arXiv:2503.15185](https://arxiv.org/abs/2503.15185)）
- 版本与规模数据：Tesla Q2 2026 Update（[官方 PDF](https://assets-ir.tesla.com/tesla-contents/IR/TSLA-Q2-2026-Update.pdf)）、FSD 版本与更新说明存档（[Not a Tesla App](https://www.notateslaapp.com/fsd-beta/)）、[tesla.com/robotaxi](https://www.tesla.com/robotaxi)、Waymo 无监督里程对照（[路透社](https://www.reuters.com/business/autos-transportation/waymo-expands-san-francisco-testing-2026-07-23/)）
