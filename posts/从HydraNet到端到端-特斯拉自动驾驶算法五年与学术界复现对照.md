---
title: 从 HydraNet 到端到端：特斯拉自动驾驶算法五年，与学术界的复现对照
date: 2026-09-29
tags: [自动驾驶, 特斯拉, FSD, BEV感知, Occupancy, 端到端, 3D目标检测]
album: 自动驾驶专栏
order: 1
excerpt: 特斯拉从 Mobileye 时代演进至 AI Day 的 HydraNet 与 Occupancy，再到 v12 取代 30 万行 C++ 规则代码、v14 将参数量提升十倍；学术界以 BEVFormer、UniAD、StreamPETR 等工作对各环节逐一开源复现。本文按时间线梳理两条路线的技术选择，逐模块对照，给出 nuScenes 上可复现的指标与实际显存开销。
---

《自动驾驶专栏》第一篇。写作缘起是梳理 BEVFormer 仓库时注意到，它与特斯拉 AI Day 公开的技术方案面向同一问题的两种解法：一侧闭源、依托车队数据，一侧开源、以 nuScenes 基准为评价体系。两条路线的技术相互参照、相互追赶，放在一起考察比单独考察任一侧更为完整。

本文首先说明信息边界：特斯拉不开放任何代码，文中关于特斯拉的描述全部来自 AI Day 2021/2022 的公开演讲、官方博客与版本更新说明，属推断之处均会标注；学术界部分的指标取自论文或官方仓库的 Model Zoo，可自行复现验证；显存与时长中标注口径者为社区实测或工程经验值，文中均就近注明。

本文的核心结论有三点：其一，特斯拉五年演进的主线是用学习组件逐级替换人工规则，而"单一 backbone + 多任务头"的骨架自 2021 年起未变；其二，学术界已对这条路线的各环节给出可复现的开源对应物，其价值在于可归因与可复现，而非榜单分数；其三，双方的实质差距在数据规模与闭环评测，而非网络架构；开源教师模型正在缩小前者，但无法替代后者。

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

## 1. 前史（2016-2020）：从买方案到自研，图像空间到向量空间

2016 年之前的特斯拉没有自己的感知栈，Autopilot 1.0 用的是 Mobileye 的 EyeQ3 方案：Mobileye 负责从图像里检测车道线和车辆，特斯拉负责控制。2016 年 5 月 7 日的致命事故（Joshua Brown 事故，Model S 在 Autopilot 开启状态下撞上横穿的白色拖挂车）之后双方关系恶化；2016 年 7 月 26 日 Mobileye 在财报电话会上宣布合同期满后不再续约，2016 年 10 月特斯拉发布搭载自研感知栈的第二代 Autopilot 硬件（HW2），双方正式分家。其直接后果是特斯拉必须自建视觉感知，而当时它的选择比今天少得多。

Autopilot 2.0 时代（2016-2019）的做法可概括为"每个相机一个 2D 检测器，再行拼接"：8 路相机各自运行一个卷积网络，输出图像平面上的 2D 框、车道线与红绿灯，再依据相机外参将这些 2D 结果投影至车体坐标系，合成一张俯视图。该路线的局限在 AI Day 2022 演讲中由 Tesla 自己归纳为四条：

- 地平线附近的深度极不一致，大片区域的深度实际由两三个像素决定；
- 遮挡无解，被前车挡住的东西就是看不见，开过去之前永远不知道；
- 输出结构是 2D 的，而世界是 3D 的；
- 本体论漏洞（ontology cracks）：检测器只认识数据集里有的类别，遇到没见过的东西直接输出"空"。

2020 年前后，Andrej Karpathy 团队将方向转向 BEV（Bird's-Eye-View，鸟瞰图）：不再于图像平面各自检测后再拼接，而是先学习统一的俯视特征空间，所有任务在该空间内完成。这一转变构成后续演进的起点，也是学术界 2021-2022 年密集跟进的主线。

硬件时间线在此记录，第 7 节将再次引用：2019 年特斯拉流片自研 HW3（FSD 芯片，14nm，双 NPU 合计约 144 TOPS），此后软件开始围绕自家硬件进行优化。

## 2. AI Day 2021：HydraNet 与蒙特卡洛树搜索

AI Day 2021 将感知侧架构定型为 HydraNet（九头蛇网络），核心思想可概括为：**一个共享 backbone，多个任务头**。此前方案为二十余个网络各自独立，图像特征被重复计算；HydraNet 将这些任务（车辆检测、车道线、红绿灯、交通标志、可行驶区域等）统一挂载于同一 backbone，单次前向输出全部结果。多任务学习在此不仅降低计算开销，任务之间还可互相提供归纳偏置。

HydraNet 的输出位于"向量空间"（vector space），即车体坐标系下的结构化表示：物体位置、速度、车道线走向。该层仍为模块化架构：感知与规划分属两个模块。

规划侧在 2021 年采用的方法相对传统。AI Day 上展示了搜索算法的三段演进：

| 方案 | 搜索扩展节点数 |
| --- | --- |
| 基础 A* | 约 44,000 |
| A* + 导航路线启发 | 约 22,000 |
| 神经网络引导的蒙特卡洛树搜索（MCTS） | 少于 300 |

（三档数字取自 AI Day 2021 演讲视频的公开复盘；该复盘博客正文另有 A* "近 400,000 次扩展"的写法，此处以视频字幕口径为准。）

综上，2021 年的特斯拉规划器是 MCTS：神经网络为搜索提供先验，搜索在候选轨迹中选择。**该结构的关键在于：感知为神经网络，规划为搜索算法，二者依靠人工编写的代价函数衔接**。这一衔接环节是 2022 年之后全部演进的起点。

## 3. AI Day 2022：Occupancy Network 逐层拆解

2022 年 CVPR 和 AI Day 上，特斯拉发布了 Occupancy Network（占据网络），这是它纯视觉路线里最有原创性的一块，也是后来学术界花最多力气复现的一块。根据 Phil Duan 的个人网站履历，该网络由他创建，并在 AI Day 2022 与 CVPR 2023 上做了公开讲解；团队分工上，Ashok Elliswamy 作为 VP of AI Software 负责整体方向与对外叙述，Phil Duan 负责工程实现与落地，媒体对此的概括是"Ashok 讲的是特斯拉想去哪儿，Phil 讲的是怎么走到那儿"。技术思想源自机器人领域的占据栅格建图（occupancy grid mapping）：把空间切成格子，每个格子回答"有没有东西"。特斯拉把它升级成三维、体素化、多视角的版本。

### 3.1 为什么 3D 框不够

特斯拉给出的理由是几何优先于本体论（geometry over ontology）：

- **固定框表征的固有限制**：给一辆卡车分配 7×3 米的框，但卡车顶上伸出的吊臂、侧面拖挂的货物无法被框表示；体素不受形状假设约束，仅回答"该格是否占据"。
- **类别局限**：检测器仅识别训练集中的类别。AI Day 所举例子为一块托盘，即使检测器检出，数据集中亦无"托盘"类别，输出仍为空，车辆随之发生碰撞。占据表示不含类别维度，未知物体同样占据空间。
- **速度与遮挡**：占据网络同时输出占据和运动流（occupancy flow），被遮挡区域的运动状态也能从时序融合里推出来。

### 3.2 网络结构

AI Day 2022 公开的结构可以从左到右读（细节以演讲图为准，参数量和分辨率特斯拉从未公布）：

1. **Backbone**：8 路相机图像进 RegNet + BiFPN，2022 年当时的标准多尺度特征提取器；
2. **注意力模块**：将位置编码（positional image encoding）与固定 query 输入注意力层，产出占据特征体（occupancy feature volume）。固定 query 的语义与 DETR 系列的可学习 query 一脉相承，区别在于查询对象由"框"变为"体素是否占据"（演讲未公布固定 query 的具体设计，此处理解为结构对照）；
3. **时序融合**：当前时刻的特征体与历史时刻（t-1、t-2……）的特征体融合，形成 4D 占据栅格。这一步靠自车运动做坐标对齐，和 BEVFormer 的 temporal self-attention 要解决的是同一个问题（见第 8 节）；
4. **反卷积上采样**：输出两样东西，**occupancy volume**（每个体素的占据概率）和 **occupancy flow**（每个体素的运动向量，用色轮编码方向，红进蓝退灰静止）。

关于推理速度，公开复盘给出的数字是超过 100 FPS（约为摄像头帧率的三倍），该数字未见于官方规格文件，属二手转述；可确认的是该网络按车载实时部署设计。同时特斯拉提出以 NeRF 做校验：离线对场景进行三维重建，与在线预测的占据体比对，借助车队平均（fleet averaging）消除雨雾模糊引入的噪声。

### 3.3 和学术界的关系

一项技术史事实值得注意：Occupancy Network 发布前后，学术界几乎同步开展了同一方向的研究。特斯拉于 2022 年 6 月展示，同年 3 月 SUTD 与商汤已发布 OpenOccupancy benchmark，2023 年前后 TPVFormer、SurroundOcc、Occ3D、FB-OCC 密集跟进。两者无代码往来，但问题定义、体素表征与时序融合的思路高度趋同，其共同上游为机器人占据栅格与 DETR。详见第 10 节。

## 4. 数据引擎：自动标注与 4D 重建

架构之外，数据管线是特斯拉的核心壁垒，AI Day 2021/2022 均以相当篇幅介绍，该部分学术界基本无法复现。

- **Clip**：标注的最小单元是 45 秒到 1 分钟的密集传感器数据片段，不是单帧图像；
- **自动标注（auto-labeling）**：对同一地点多次通过的车队数据执行 4D 重建（早期采用类 NeRF 的重建方法，后期转为更工程化的多视角几何管线），从视频中计算三维真值，再由离线大算力模型（不受车端算力限制）生成标注；
- **数据引擎闭环**：影子模式（shadow mode）捕捉人类接管与模型分歧的片段，回流为新的训练 clip，人类标注员仅处理模型无法覆盖的长尾场景；
- **算力规模**：AI Day 2022 给的数字是训练集群约 1 万张 GPU，另有约 4 千张专门跑自动标注。

对照组为学术界的 nuScenes：1000 个 20 秒场景、约 5.5 小时、140 万张相机图像、39 万帧激光雷达，人工标注 3D 框与地图。**训练集规模相差约四个数量级**：按数百万 clip、每 clip 45-60 秒估算，特斯拉侧为数十万至百万小时量级，nuScenes 仅 5.5 小时，量级差约 $10^4$；而 nuScenes 已是学术界规模最大、成本最高的公开数据集之一。该差距决定了两侧的训练目标：特斯拉可训练从像素直接输出转向指令的模型，学术界则限于"图像至 3D 框"或"图像至 3 秒轨迹"。

## 5. 2023-2024：FSD v12，30 万行 C++ 的退场

端到端的转向有明确的技术推动者：Autopilot 工程师 Dhaval Shroff 提出并验证了这一思路，其表述被广泛引用——"不再用规则决定车辆的路径，而是用从数百万人类驾驶样本中学习的神经网络来决定"，转述中另有"像 ChatGPT，但对的是车"一语。流传较广的"2022 年 12 月于 Palo Alto 总部会议上当面提案"这一时间与情节，目前仅见于二手复盘（thinkautonomous 博客），缺乏一手材料佐证；可以确认的是其结果：该思路成为 FSD v12 的技术路线。

架构上的变化在第 2 节已有铺垫：MCTS 中的人工代价函数（碰撞概率、舒适度、被接管可能性、类人程度四项加权）是规则体系的最后组成部分，端到端训练将其整体替代。2023 年 8 月 Musk 直播演示 v12，2024 年 3 月起大规模推送。官方更新说明中被引用最多的一句是：**单一端到端神经网络，从数百万视频片段训练，取代了 30 万行显式 C++ 规则代码**。

此处需明确"端到端"的实际含义，该术语常被误解为"更换了更大的模型"。其区别在于训练方式：

- **模块化多网络学习**：模块 A（感知）在检测数据集上单独训练，模块 B（规划）以 A 的输出单独训练。A 不针对 B 的目标进行优化，两者的损失函数不共享梯度；
- **端到端**：以统一目标训练，梯度从最终轨迹回传至图像输入。感知学到的表征直接由"该感知方式对规划是否有效"这一目标塑造；

按公开资料，v12 保留了 Occupancy 与多任务感知等模块，仅将其接入统一的联合训练计算图，代价函数由手写转为学习得到。因此它并非推翻重建，而是将 2021-2022 年积累的模块整合为可微的整体。批评者认为此举引入黑箱，支持者认为中间表征仍可可视化，两种观点各有依据：黑箱性体现在联合训练的内部权衡，可解释性体现在各中间任务头依然保留。

## 6. 2024-2026：v13 到 v14，参数量、强化学习与视频基础模型

v13 于 2024 年底推送（约 2024 年 11-12 月），官方更新说明的核心表述为"36 Hz、全分辨率 AI4 视频输入"（full-resolution AI4 video inputs）、原生适配 AI4 输入与神经网络架构，并将数据扩展 4.2 倍、训练算力扩展 5 倍；重点为接管率下降与更高分辨率输入；HW3 车型停留在 v12.6 分支，此后两条硬件线各自维护版本。v14 为 2025 年 10 月起向 HW4 推送的大版本，Musk 在发布前约 6 周（2025 年 8 月）预告其特征为**参数量提升 10 倍**，2026 年上半年陆续迭代至 v14.3.x。

综合更新说明与公开演讲，v14 的技术要点可归纳为三项：

1. **强化学习进入训练管线**。2022 年规划器中四项手写代价（碰撞、舒适、接管、类人）由奖励函数替代，v14.3 的更新说明原文为"升级 FSD 神经网络训练中的强化学习阶段"（upgrading the Reinforcement Learning stage of training the FSD neural network）。这是第 2 节与第 5 节所述路线的终点：规则 → 人类示例模仿 → 强化学习；
2. **视觉编码器升级**。v14.2 的更新说明提到"升级神经网络视觉编码器，用更高分辨率特征改善低可见度场景"；
3. **跨硬件蒸馏**。HW3 无法承载 10 倍参数的模型，特斯拉将 HW4 上的大模型蒸馏为 HW3 的"V14 Lite"（2026.20.5.1 起推送，2026 年 7 月下旬全量）。同源双权重，是量产约束下的典型技术处理。

2026 年 CVPR DriveX Workshop 上，Tesla AI 的 Phil Duan 做了题为《Self-Driving at Scale with Foundation Models》的主题演讲。其头衔以个人网站为准：Director of Engineering at Tesla AI，中文媒体另有"AI 工程总监""Autopilot 工程总监""首席软件工程师"等不同译法，引用时以其自述为基准。个人网站载明的履历为：主导 Robotaxi 上线与 FSD v14 发布，此前联合负责（co-led）v12 与 v13 版本，带领数据与感知团队，创建 Occupancy Network，并参与构建数据引擎。按公开分享的 slide，今天特斯拉的感知是一个**视频基础模型**：8 路相机 36 Hz 进一个视觉编码器，出来一排任务头：动作（规划）、全景分割、3D 占据、3D 检测、人体网格、关键点跟踪、文字识别等。同一套模型还同时服务 FSD、实际智能召唤（ASS）和 Robotaxi 三个产品。

**该结构与 2021 年的 HydraNet 形态一致**：单一 backbone，多个任务头。五年间变化的是编码器规模、训练目标函数（人工代价 → 模仿 → RL）与数据量级，不变的是这一骨架。特斯拉 slide 上的表述是"用你关心的任务、用最大规模的数据训练"，这即是其五年来对多任务学习的一贯主张。

这一时期的人员归属值得厘清，因为公开报道中的头衔与分工常有出入。按可核实的材料，FSD v12 至 v14 的演进并非单一负责人之功：

| 人员 | 职务（公开口径） | 贡献 |
| --- | --- | --- |
| Ashok Elliswamy | VP of AI Software，向 Musk 汇报 | FSD 与 AI 团队整体负责人 |
| Phil Duan | Director of Engineering, Tesla AI | v12/v13 联合负责，v14 与 Robotaxi 主导；Occupancy Network 创建者 |
| Dhaval Shroff | Autopilot 工程师 | 端到端思路的提出与验证 |
| Andrej Karpathy | 前 AI 负责人（2022 年 7 月离职） | HydraNet、数据引擎等早期基础；离职早于 v12 |
| Elon Musk | CEO | 关键路线决策（v11→v12 转向端到端、v14 参数量提升等） |

需要明确的一点是：**端到端并非特斯拉首创**，学术界与 NVIDIA 早有同类工作；特斯拉的贡献在于以百万级 clip 与闭环迭代将其推进至量产上车。第 11 节的 UniAD（CVPR 2023 最佳论文）公开时间即早于 v12。

## 7. 芯片这条暗线：HW3、HW4 到 AI5

算法演进无法回避硬件因素：特斯拉的算法选择始终受"在几十瓦、几十美元的车规芯片上实时运行"这一约束影响，该约束亦解释了它为何比学术界更早放弃稠密 BEV 网格。

| 硬件 | 时间 | 算力（公开口径） | 备注 |
| --- | --- | --- | --- |
| HW3（FSD 芯片） | 2019 量产 | 双 NPU 合计约 144 TOPS | 14nm，自研起点 |
| HW4 / AI4 | 2023 起 | 约 3-5 倍于 HW3 | 16GB RAM，256GB 存储 |
| AI4+（过渡款） | 规划中 | 内存翻倍至每 SoC 32GB | 介于 HW4 与 AI5 之间 |
| AI5 | 2026 年流片 | 报道称 2000-2500 TOPS，约 AI4 的 8 倍 | 官方称对标 H100 级别的模型推理 |

（TOPS 数字来自公开报道与高管访谈，非官方规格书，仅供参考。）

这些数字指向同一约束：车端需同时运行 10 倍参数的端到端模型、占据网络与各任务头，并预留 36 Hz 的实时余量，因此模型必须稀疏化、蒸馏化，并与芯片联合设计。同期学术界在 A100 上以单卡单 batch 训练，不受该约束，双方的架构分歧由此获得物理层面的解释。

## 8. 学术界的平行线（一）：DETR3D、BEVDet、BEVDepth 与 BEVFormer

学术界虽无车队数据，但具备两项特斯拉不具备的条件：公开基准与可复现代码。2021-2022 年间，"多相机图像 → BEV"路线得到密集推进。

**DETR3D**（CoRL 2021）是将 DETR 推广至 3D 的代表工作：一组可学习的 3D 框 query 投影至各相机图像采样特征，迭代细化框。该工作验证了"稀疏 query + 图像采样"的可行性，但缺少显式 BEV 表征，时序亦仅限单帧。

**BEVDet**（2021 末）采用另一路径：以 Lift-Splat-Shoot 视角变换将图像特征显式投影至 BEV 网格，再在 BEV 上执行检测，确立了"先建 BEV 再做任务"的顺序。其代价是深度估计不准时 BEV 特征随之失真，因此有了 **BEVDepth**（AAAI 2023）：训练阶段以激光雷达点云提供稠密深度监督（推理阶段不使用激光雷达），将深度估计从网络自主预测转为有监督学习。BEVDepth 在 nuScenes 测试集上取得 50.3% mAP、60.0% NDS，一度居纯视觉首位。

**BEVFormer**（ECCV 2022，就是本专栏起因的那篇）把整件事统一成一个时空 Transformer，也是学术界对特斯拉 2021-2022 方案最完整的一次公开复现。三个部件：

1. **BEV query**：一张 $H \times W$ 的网格铺在车周围（base 配置 200×200，范围 $\pm 51.2$ 米，也就是每格约 0.5 米），每个格子是一个可学习 query，代表该位置的 BEV 特征；
2. **空间交叉注意力（spatial cross-attention）**：每个 BEV 格子在高度方向取 4 个参考点（`num_points_in_pillar=4`），投影至 6 路相机图像，经可变形注意力（MSDeformableAttention，每个参考点采样 8 点）从多尺度 FPN 特征中采样。该步骤即"图像至 BEV"的可微实现，以稀疏采样规避全图注意力的开销；
3. **时序自注意力（temporal self-attention）**：把上一帧的 BEV 特征按自车运动旋转平移对齐后，用可变形注意力在邻域采样融合。这一步对应特斯拉 Occupancy 里的时序融合，解决的是同一个问题：速度估计和遮挡。

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

以下给出这三个部件的数学形式，以明确其计算内容与开销所在。

**参考点的生成**。BEV 网格第 $(i,j)$ 个格子的世界坐标先落在地面上：

$$p_{ij} = \left(x_{\min} + \frac{j+0.5}{W}\Delta x,\quad y_{\min} + \frac{i+0.5}{H}\Delta y\right)$$

然后在高度方向取 $N_r = 4$ 个参考点（等间隔分布于 $z_{\min}$ 至 $z_{\max}$ 之间），各参考点经相机内外参投影至 6 路图像的像素坐标 $(u,v)$。参考点所属相机及其是否位于图像范围内，决定该点可从哪几路图像获取特征。

**空间交叉注意力**用的是可变形注意力的三维版：对每个参考点 $p$，采样 $K = 8$ 个偏移点，注意力只在这 8 个点上算：

$$\mathrm{SCA}(q, p) = \sum_{l=1}^{L}\sum_{k=1}^{K} A_{lk} \cdot W_l\, x_l\bigl(\phi_l(p) + \Delta p_{lk}\bigr)$$

其中 $A_{lk}$ 是 softmax 归一化的注意力权重，$\Delta p_{lk}$ 是网络学习得到的采样偏移，$\phi_l(p)$ 是将 3D 参考点投至第 $l$ 层特征图的像素位置。该设计的计算量如下：若对每个 BEV 格子在整幅图像上做全注意力，计算量为 $O(HW \cdot \text{pixels})$，200×200 网格乘以百万级像素不可行；可变形注意力将其降至 $O(HW \cdot 4 \cdot 8)$，**每个格子仅采样 32 个点**，这是该模型得以在 A100 上运行的直接原因。代价在于采样点由学习得到，缺乏全局视野，视野外信息需通过 6 层 encoder 逐层补充。

**时序自注意力**沿用同一机制，query 为当前帧 BEV 格子，key/value 为上一帧 BEV 特征：首先按自车运动对上一帧 BEV 做旋转平移（配置中 `rotate_prev_bev`、`use_shift`、`use_can_bus` 三个开关分别对应旋转、平移与 CAN 总线速度补偿），随后在对齐位置附近采样 8 点。速度估计即由此而来：同一车辆在两帧 BEV 中的位置差使网络得以学习其运动状态，mAVE 因此下降约一半。

**稠密网格的计算量分析**。直觉上 H×W 网格的计算量随面积变化，$200^2 / 150^2 \approx 1.78$，$200^2 / 50^2 = 16$。但实测显存并非该比例（tiny 6.5 GB → base 28.5 GB，约 4.4 倍），因为主要开销还包括 backbone、图像特征缓存与队列中 4 帧图像本身。随网格平方增长的部分仅限注意力与 BEV 特征图显存，故网格越大边际成本越高。这也解释了 Model Zoo 三档配置的划分依据：tiny 的 50×50 面向 pipeline 的快速验证，base 的 200×200 对应论文指标。

官方 Model Zoo 的三档配置与真实训练显存：

| 配置 | 网格 | 帧队列 | NDS / mAP（nuScenes val） | 训练显存（每卡） |
| --- | --- | --- | --- | --- |
| BEVFormer-tiny (R50) | 50×50 | 3 | 35.4 / 25.2 | 约 6.5 GB |
| BEVFormer-small (R101-DCN) | 150×150 | 3 | 47.9 / 37.0 | 约 10.5 GB |
| BEVFormer-base (R101-DCN) | 200×200 | 4 | 51.7 / 41.6 | 约 28.5 GB |

base 在 val 上对比 DETR3D（R101：42.5 NDS）提升 9.2 个点，主要来自时序融合带来的速度估计（mAVE 从 0.842 降到 0.394，速度误差减半以上）。论文级最佳成绩 56.9 NDS 是用 V2-99 backbone 加额外预训练拿到的。训练成本上，社区口径为 8×A100 约两天（折合约 16 个 GPU-天，若按单卡折算约需两周以上）；官方 Model Zoo 未给出训练时长，仅给出单卡显存 28.5 GB。

一个必须说明的工程事实：这套代码绑定 2022 年的 mmdet3d 0.x / mmcv 1.x 生态（CUDA ≤ 11.3、PyTorch ≤ 1.12），在 4090 及更新的显卡上编译 mmcv 需要打补丁。这是该时期仓库的普遍问题，也是第 15 节实操建议的由来。

## 9. 学术界的平行线（二）：稀疏化的 StreamPETR、Sparse4D 与 SparseBEV

BEVFormer 的稠密网格有个天生的账要算：200×200 的网格里绝大多数格子是空的（停车场外的荒地、天上），却都要算注意力。2023 年起，主流转向**稀疏 query**：不做全局网格，只让 query 跟着物体走。这条线恰好也是车端算力约束下的必然选择，和特斯拉的方向殊途同归。

**StreamPETR**（ICCV 2023）继承 PETR 的 query 体系，核心是把时序信息在 query 之间传播（propagation）：上一帧的 query 经过自车运动变换后直接作为下一帧的初始 query，物体为中心的表征随时间延续。该机制的关键收益在于时序建模的成本随 query 数量增长，而不随空间分辨率增长：序列长度增至 4+ 帧时既不需要像 BEVFormer 那样对齐并维护整张 BEV 网格，也不引入随帧数线性膨胀的稠密特征，这正是其显存显著低于 BEVFormer 的结构性原因（定量对照见第 8 节）。官方仓库的数字：

| 模型 | 训练 | NDS / mAP（val） | FPS（PyTorch） |
| --- | --- | --- | --- |
| StreamPETR (V2-99, 900q) | 13 小时 | 57.1 / 48.2 | 12.5 |
| StreamPETR (R50, 90ep) | 36 小时 | 53.7 / 43.2 | 26.7 |
| StreamPETR (R50, 428q + nuImg) | 26 小时 | 54.6 / 44.9 | 31.7 |
| StreamPETR-Large（测试集） | — | 67.6 / 62.0 | — |

末行的意义在于：首个在线多相机方法在测试集上达到激光雷达基线的水平。其显存与速度均显著优于 BEVFormer-base，这是稀疏化的直接收益。两者的训练时长口径不同，不构成严格对比：README 标注训练均在 8×2080Ti 上进行，13 小时一行的 12.5 FPS 则标注为 RTX 3090 实测，而 BEVFormer 的"两天"出自社区实测（8×A100，折合 16 个 GPU-天）。

**Sparse4D**（2022 年 11 月 arXiv 首发，v2/v3 迭代至 2023 年，后正式发表于 TPAMI 2026）走"稀疏 anchor + 多视角特征采样"的路子，v2 改成递归时序融合，进一步压延迟和显存，v3 加稠密深度辅助。它在工业界落地最多（地平线车端有部署），官方代码在 HorizonRobotics/Sparse4D。

**SparseBEV**（ICCV 2023 → TPAMI 2026）回应"稀疏 query 丢失 BEV 稠密上下文"的批评，提出自适应稀疏采样：由 query 依内容决定采样位置，以较小的 query 集合逼近稠密 BEV 的效果。官方 Model Zoo 显示 r50 配置在 8×2080Ti 上训练 21 小时，val NDS 55.6、15.8 FPS；r101 高分辨率配置 val NDS 59.2；此外提供基于 EVA02/ViT 的大 backbone 配置，测试集 NDS 达 70.2。

**Far3D**（AAAI 2024）针对远距离小目标（长尾场景中的远处车辆），megvii-research/Far3D 开源。

上述工作连同 BEVNeXt（CVPR 2024，论证稠密 BEV 仍具竞争力）与 RecurrentBEV（ECCV 2024，25.6 FPS 下 44.5 mAP），构成对 BEVFormer 的系统性修正：时序融合为必要项且收益最大，稠密网格可以省略，query 应当稀疏。

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

该方向与特斯拉的差异在真值来源：特斯拉以 4D 重建自建真值（车队对同一地点多次经过），学术界以激光雷达累积点云投影至体素作为真值（Occ3D、OpenOccupancy 均为此思路）。**以激光雷达监督纯视觉模型，是学术界规避"缺少车队数据"这一约束的关键方法**，与 BEVDepth 以点云监督深度属同一思路。

## 11. 学术界的平行线（四）：UniAD 与端到端规划

FSD v12 公开前一年，学术界已给出端到端方案。**UniAD**（CVPR 2023 最佳论文，OpenDriveLab）将感知、跟踪、建图、预测、规划统一于单一网络，明确"以规划为导向"：前述各任务均服务于末端的轨迹预测。其显存开销在官方文档中列示如下：

- 第一阶段（感知模块）：**约 50 GB** 显存，8×A100 训练 6 epoch 约 2 天；将 `queue_length` 由 5 降至 3 可压缩至约 30 GB，可运行于 V100 32GB；
- 第二阶段（联合训练）：**约 17 GB**，8×A100 训 20 epoch 约 4 天，因为冻结了 BEV encoder，3090/V100 都能跑。

**VAD**（ICCV 2023，华科 + 地平线）是 UniAD 的效率改进版：采用全场景矢量化表示（车道线、车辆均为向量而非栅格），去除稠密栅格的计算开销，规划指标更优：

| 方法 | L2 (m) 1s / 2s / 3s | 碰撞率 (%) 1s / 2s / 3s | FPS |
| --- | --- | --- | --- |
| ST-P3 | 1.33 / 2.11 / 2.90 | 0.23 / 0.62 / 1.27 | 1.6 |
| UniAD | 0.48 / 0.96 / 1.65 | 0.05 / 0.17 / 0.71 | 1.8 |
| VAD-Base | 0.41 / 0.70 / 1.05 | 0.07 / 0.17 / 0.41 | 4.5 |
| VAD-Tiny | 0.46 / 0.76 / 1.12 | 0.21 / 0.35 / 0.58 | 16.8 |

该方向的后续工作（截至 2026 年）：**VADv2**（概率规划，ICLR 2026 录用）、**SparseDrive**（全稀疏端到端，49.6 mAP，超 UniAD 11.6 个点）、**DiffusionDrive**（CVPR 2025，扩散模型生成多模态轨迹）、**RAD**（NeurIPS 2025，3DGS 环境中执行强化学习后训练）。其中 RAD 表明学术界同样引入了强化学习后训练驾驶策略，与特斯拉 v14 的路线趋同，两者在训练范式上再度交汇。

与特斯拉的实质差异在监督信号：UniAD/VAD 以 nuScenes 中 3 秒的人类轨迹执行开环模仿学习，特斯拉则使用数百万 clip 与强化学习。第 13 节将分析该差异对评测的影响。

## 12. 正面对照：逐模块比较

将前述 11 节归纳为一张对照表，同一行对应同一问题的两种做法：

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

表中最关键的两项差异是**监督来源**与**推理硬件**。学术界的架构创新（稀疏 query、矢量化、轻量 BEV）是在无车端功耗约束、但仅有 5.5 小时数据的条件下完成的；特斯拉的工程创新（自动标注、蒸馏、多任务共享）是在数据充裕、但必须满足几十瓦芯片实时约束的条件下完成的。两条路线各自受制于自身短板，最终在"稀疏 + 多任务 + 时序"的交集上趋于一致。

以下是同基准（nuScenes，避免跨基准比较）的直接对比：

| 方法 | 年份 | 代码 | NDS | 备注 |
| --- | --- | --- | --- | --- |
| FCOS3D | 2021 | 开源 | 42.8（test，R101） | 单帧，无 BEV |
| DETR3D | 2021 | 开源 | 47.9（test，V2-99） | 稀疏 query 开山 |
| BEVFormer-base | 2022 | 开源 | 51.7（val，R101-DCN）；56.9（test，V2-99） | 时空 BEV，28.5 GB 显存 |
| BEVDepth | 2023 | 开源 | 60.0（test） | 激光雷达深度监督 |
| StreamPETR-Large | 2023 | 开源 | 67.6 | 官方 README：首个在线多相机方法追平激光雷达基线（62.0 mAP / 67.6 NDS / 65.3 AMOTA） |
| SparseBEV（EVA02 版） | 2023-2026 | 开源 | 70.2（test） | 稀疏采样 + 大 backbone |
| 特斯拉 | 2022-2026 | 闭源 | 不参赛 | 无公开数字 |

（同类对照常将 val 与 test 成绩混列，本表两侧均标注口径，跨行比较时需注意区分。）

特斯拉未在任何公开基准上提交过成绩，表中最后一行因此始终为空。这是本次对照最根本的不对称：**学术界以分数为评价体系，特斯拉以接管率为评价体系，两者之间不存在换算关系**。

## 13. 评测的分裂：NDS、L2、闭环与接管率

两种评价体系无法换算，原因在于其测量对象不同。

**NDS/mAP 评价感知**。nuScenes 的 NDS 是加权和：

$$\mathrm{NDS} = \frac{1}{10}\left[5\,\mathrm{mAP} + \sum_{\mathrm{mTP}\in\mathrm{TP}} \bigl(1 - \min(1,\mathrm{mTP})\bigr)\right]$$

五个 TP 项分别为平移、尺度、朝向、速度、属性误差。该指标仅反映检测精度，与规划质量无关。BEVFormer 将 mAVE 由 0.842 降至 0.394 从而提升 NDS，但该模型本身并不具备驾驶能力。

**开环 L2 评价模仿**。UniAD/VAD 所采用的规划指标协议如下：以 nuScenes 一段人类驾驶为输入，前 2 秒提供给模型，由其预测后 3 秒轨迹，与人类真实轨迹计算 L2 距离。该协议存在三项已被学界指出的局限：

1. **惩罚偏离**：模型选择更安全但与人类不同的路线，仍会受到 L2 惩罚；
2. **无交互**：不还原其他交通参与者的响应，模型对旁车造成的影响不会在评价中反馈；
3. **上限受限于人类**：最优结果为"完全复刻人类"，而 nuScenes 中的人类驾驶本身亦存在平庸操作。

UniAD 仓库为此设立 Planning Metric 讨论（issue #29），社区围绕开环结果的可比性多次讨论。CARLA 闭环（VAD 在 Town05 Long 上 Driving Score 30.31，对比 ST-P3 的 11.45）是学术界可提供的更接近真实的评价，但 CARLA 的交通模型与真实世界长尾场景仍存在数量级差距。

**接管率衡量的是系统整体**。特斯拉采用每千英里接管次数、真实事故率作为指标，将感知、规划、控制、数据、迭代速度纳入统一核算。其优点是直接对应产品表现，局限在于不可复现、不可审计，外界只能依赖其单方公布的数据。

因此，"特斯拉与学术界孰优孰劣"目前并无定论，双方各有优势：**学术界的优势在可复现与可归因（各模块贡献可经消融实验分离），特斯拉的优势在闭环指标与迭代速度**。研究者可以复现 BEVFormer 的每一项数字，但无法验证特斯拉公布的接管率。

## 14. 2026 年的合流：VLA、世界模型与开源教师模型

2025-2026 年间，两条路线出现明显趋同，可归纳为四项信号：

1. **特斯拉向学术界靠拢**：CVPR 2026 DriveX keynote 将感知统称为"视频基础模型"，多任务头与共享编码器的表述与学术界的 multi-task foundation model 叙事一致；Phil Duan 在学术 workshop 上公开演讲，此类情况在此前较少出现；
2. **学术界向特斯拉靠拢**：VAD（ICLR 2026）、RAD（NeurIPS 2025，强化学习后训练）、DiffusionDrive（CVPR 2025）等工作所对应的正是特斯拉 v12→v14 的路径：从模仿学习到生成式规划，再到强化学习；
3. **VLA 与世界模型成为新主线**：国内厂商（理想、小米等）在 2025-2026 年密集发布 VLA 与世界模型方案（理想公开了世界模型 + 强化学习闭环训练路线，小米 2026 年 5 月开源 OneVL，融合 VLA 与世界模型）；学界有 VLA-World（arXiv 2026）、DriveWorld-VLA（ICML 2026）等工作；
4. **头部厂商发布"开源教师模型"**：NVIDIA 2026 年 1 月发布 Alpamayo 家族，其中 Alpamayo 1 为 100 亿参数的推理型 VLA 模型，权重在 HuggingFace 开放，官方定位为不直接部署上车、而是作为教师模型蒸馏至各家的系统；配套 AlpaSim 仿真框架（开源）与 1700+ 小时开放驾驶数据。

第 4 点意义尤为突出："大模型作为教师、蒸馏至车端小模型"，正是特斯拉对 HW4→HW3 的处理方式（V14 Lite）。特斯拉早五年验证的工程路径，如今被头部厂商以开源生态的形式推广至全行业。若说 2022 年的对照格局是"特斯拉 vs 学术界"，2026 年则已转变为"闭源全栈 vs 开源拼图"：后者尚无法企及前者的数据规模，但模型、仿真、数据三个环节的缺口正在被逐个补齐。

## 15. 实践指南：方案选型与显存需求

将前述各节的运行要求对应到具体显卡（训练，batch=1，官方配置）。表中标注"官方"的显存取自 README 的 Model Zoo 实测值，标注"经验值"的为社区实践口径，与"建议显存"一列同属工程参考：

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
- **以研究规划为目标**：选择 VAD 而非 UniAD，前者更轻量、指标更优，且已接入 CARLA 闭环；UniAD 仅在需要复现其两阶段训练流程时适用。

环境层面的问题需提前说明：这批代码绝大多数绑定 mmdet3d 0.x + mmcv-full ≤ 1.6，属于 CUDA 11.3 时代的产物。4090（sm_89）、Blackwell 架构的显卡需自行修补 mmcv 编译，DeepSpeed 与梯度检查点是 24 GB 显存运行 base 配置的必要手段。

## 16. 总结

将五年时间线归纳为三点：

1. **特斯拉的算法演进呈现持续的"去规则化"趋势**：手工特征 + 2D 检测（2016）→ HydraNet + MCTS 手写代价（2021）→ Occupancy + 4D 自动标注（2022）→ 端到端模仿（2024）→ 强化学习 + 十倍参数 + 跨硬件蒸馏（2025-2026）。每一步均以学习所得替代上一步的人工设计，最终保留的骨架（单一 backbone、一排任务头）与 2021 年一致；
2. **学术界对该路线的各环节均给出了开源对应物**：BEVFormer 对应时空 BEV，Occ3D 系列对应占据预测，UniAD/VAD 对应端到端，RAD 对应 RL。复现的价值不在分数，而在可归因：特斯拉的报告仅给出"接管率下降"，学术界的论文可以给出"时序融合贡献 mAVE 0.45、稀疏化节省 60% 显存"这类可消融的结论；
3. **双方的实质差距在数据与闭环，而不在架构**。架构层面学术界甚至更为激进（稀疏、全稀疏、矢量化、扩散），但 nuScenes 5.5 小时数据训练的模型，与数百万 clip 加 RL 加闭环迭代得到的系统，不属同一量级。2026 年的开源教师模型潮（Alpamayo 等）正在弥补的正是这一环节，但数据与真实里程的积累短期内难以逾越。

下一篇将选择具体工作的代码进行拆解，候选为 StreamPETR 的 query 传播与 SparseBEV 的自适应采样。

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
- 数据集：[nuScenes](https://www.nuscenes.org/)（1000 场景 / 5.5 小时 / 140 万图）
