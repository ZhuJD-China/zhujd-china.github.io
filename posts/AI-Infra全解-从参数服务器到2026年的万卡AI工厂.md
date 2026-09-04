---
title: AI Infra 全解：从参数服务器到 2026 年的万卡 AI 工厂
date: 2026-09-03
tags: [深度学习, AI Infra, 分布式训练, 推理系统, 集群]
album: 深度学习专栏
order: 4
excerpt: 从 AlexNet 的两块游戏显卡讲到 16 万卡 AI 工厂：参数服务器的兴衰、并行方式圣经、NVLink 与 InfiniBand 的网络军备赛、vLLM 与 Mooncake 的推理革命、DeepSeek 的极致工程，以及 RL 训练栈这个 2026 年最热的战场。
---

这是《深度学习专栏》的第四篇。前三篇讲的都是"模型内部的计算"——注意力怎么算、token 怎么切、数字怎么存。这一篇跳出来讲另一件事：**这些计算跑在什么上面**。我用 3050 跑量化模型的时候，世界的另一头有人在一万六千张 H100 上训练——我们面对的其实是同一套技术体系的两端。

---

## 目录

1. 引子：AI Infra 到底指什么
2. 史前史（2012-2015）：两块游戏显卡引发的学科
3. 框架战争与通信范式（2015-2019）
4. 并行方式圣经（2019-2021）
5. 编译器与 Kernel（2019-2024）
6. 网络军备赛：把机房变成一台计算机
7. 推理革命（2022-2024）：操作系统思想占领 LLM
8. DeepSeek 时刻：极致的软硬协同（2024）
9. 万卡运维：故障才是常态（2024-2026）
10. PD 分离与 KV Cache 外置（2024-2026）
11. RL Infra：2026 年最热的战场
12. 实战：普通工程师怎么用好这些知识
13. 尾声：四篇合奏
14. 参考资料

---

## 1. 引子：AI Infra 到底指什么

"AI Infra"这个词没有严格的边界，但有一条很好用的判据：**凡是"算法之外、但在拖算法后腿"的东西，都是 AI Infra**。往小了说，它是一个 CUDA kernel、一次显存分配；往大了说，是一个由 16 万张 GPU、数万台交换机和几座变电站组成的"AI 工厂"。中间还夹着框架（PyTorch/Megatron）、编译器（Triton/torch.compile）、通信库（NCCL）、推理引擎（vLLM/SGLang）、调度器（K8s/RBG）这些层次。

这个领域有个与众不同的气质：**它的问题几乎全部由别的领域的技术进步"顺便"造成**。模型变大（算法的胜利）→ 显存不够（infra 的问题）；参数变多（算法的胜利）→ 通信量爆炸（infra 的问题）；推理需求暴涨（产品的胜利）→ serving 成本失控（infra 的问题）。所以读 infra 的历史，读的其实是"上层每一次跃进之后，底层怎么把窟窿补上"。

补窟窿的历史可以浓缩成三堵墙：**显存墙**（模型装不下）、**通信墙**（GPU 之间数据传不动）、**利用率墙**（卡买回来了但大部分时间在空转）。这篇的每一节，都在讲怎么翻其中一堵墙。

## 2. 史前史（2012-2015）：两块游戏显卡引发的学科

一切从 AlexNet 开始。2012 年，Krizhevsky、Sutskever 和 Hinton 用**两块消费级 GTX 580**（每块 3 GB 显存）训练出了碾压传统方法的 AlexNet。有个流传很广的细节：因为单卡 3 GB 放不下整个模型，他们把网络劈成两半，一半放一块卡——这大概是大模型"模型并行"的最早民间实践，纯属被显存逼的。

接下来的三年，"深度学习系统"作为一个方向开始成型，两条路线几乎同时出发：

**路线一：分布式训练。** Google 2012 年的 DistBelief（NeurIPS 2012，Jeff Dean 等人）确立了**参数服务器**（Parameter Server）架构：一组 server 节点保管全局参数（一个分布式的 KV 存储），一组 worker 各自处理数据分片，靠 pull/push 同步参数。这个范式在 2014 年被李沐等人的 OSDI 论文《Scaling Distributed Machine Learning with the Parameter Server》系统化，配套的还有 SSP（有界延迟同步）等一致性模型的设计空间。同一时期，HOGWILD!（2011）证明了纯异步的无锁 SGD 在稀疏问题上居然能收敛——这些"容忍不一致"的设计哲学，今天读来依然前卫。

**路线二：让 GPU 本身跑得快。** cuDNN（2014）把卷积的各种实现封装成"挑最快的那种"，第一次让研究者不用手写 CUDA 也能榨干 GPU。今天的很多争论（"为什么我的模型跑不满算力"）在 cuDNN 的设计文档里就已经讨论过了。

这个阶段有个值得记住的事实：**参数服务器统治了那个时代**——因为它解决的是"模型大到单机放不下"的问题，而当时的"大"是推荐系统的 embedding 表（几百 GB 的稀疏参数），不是神经网络权重。注意这个伏笔：LLM 时代的分布式训练最终**没有**沿用 PS 架构，但 PS 并没有死——它在今天的推荐系统里依然是绝对主流。一个架构的兴衰取决于它和负载的匹配度，而不是它本身新不新。

## 3. 框架战争与通信范式（2015-2019）

2015-2017 是深度学习框架的"春秋战国"：Caffe、Theano、Torch、MXNet、TensorFlow、PyTorch 轮番登场。这场战争的结局大家都知道了（PyTorch 赢得了研究界，然后 2.0 之后开始进军生产），但战争的过程比结局更有信息量。

TensorFlow 1.x 的静态图是那个时代的"正确答案"：先定义计算图再执行，天然适合编译优化和部署。但研究者们被它的调试体验折磨得死去活来——print 一个中间变量都要建 session 跑一遍。2017 年底 PyTorch 用动态图（define-by-run）掀桌：写起来就是普通 Python，print 随便打。**易用性在研究场景碾压了性能**，三年内论文实现几乎全数迁移。这个结果对 infra 的启示很深：**决定一个系统生死的往往不是峰值性能，而是"想法到实验结果的回路时间"**。

框架战争的同时，分布式训练的通信范式发生了一次决定性更替：**参数服务器 → 集合通信（AllReduce）**。

PS 架构在 LLM 训练上有两个致命伤：worker 要不停 pull/push 完整参数，通信量随模型大小线性增长且集中在 server（带宽热点）；异步更新虽然吞吐高，但对 LLM 训练的收敛性是灾难。而 AllReduce（环形归约，百度 2016 年引入深度学习）用一种对称得多的方式解决同一个问题：每张卡上都有完整模型副本，梯度算完后所有卡**彼此交换、归约**，没有中心节点。

真正把这条路铺平的是 Uber 的 **Horovod**（2017）和 PyTorch DDP（2018）——用户几行代码把单卡训练变成多卡，底层靠 **NCCL**（NVIDIA 的集合通信库）直接驱动 GPU 的通信硬件。Ring-AllReduce 的通信量是 $2 \cdot \text{模型大小} \cdot \frac{n-1}{n}$，与卡数几乎无关——这个性质让"数据并行 + AllReduce"成为此后五年的默认范式。

顺带一提：NVIDIA 在 2019 年以 69 亿美元收购 Mellanox（InfiniBand 的主要供应商），这桩收购的深远意义几年后才显现——买下了"GPU 之间的网络"这个环节，等于买下了 AI 数据城的城墙。

## 4. 并行方式圣经（2019-2021）

数据并行有个前提：**单卡装得下整个模型**。当模型大到一张卡、一台机器都放不下时，就得换武器了。2019-2021 这三年，学术界把"怎么切一个 Transformer"这个问题研究了个透，成果今天被统称为"3D 并行"。

### 4.1 张量并行（Megatron-LM，2019）

NVIDIA 的 Megatron-LM 给出了教科书级的做法：把每一层的权重矩阵**按列/按行切开**，分给多张卡。前向时每张卡算自己那片矩阵乘，然后在输出上做一次 AllReduce；反向再各来一次。对 Transformer 结构，Megatron 把 Attention 头组和 FFN 都切得很优雅，通信量是每层 $O(b \cdot s \cdot h)$（batch × 序列长 × 隐层宽）的量级。

代价很清楚：**每一层的前后都要通信**，所以 TP 只适合放在 NVLink 域内（单机 8 卡），跨机做 TP 会被网络延迟杀死。这条经验法则（TP ≤ 单机卡数）直到今天依然成立。

### 4.2 流水线并行（GPipe 2018 / PipeDream 2019）

另一条路：把模型**按层切开**，第 1-10 层放机器 A，第 11-20 层放机器 B。这就是流水线并行。问题是流水线有**气泡**（bubble）——第一台机器算第一批数据时，后面的机器都在等。GPipe 用 micro-batch 缓解，PipeDream 贡献了 1F1B 调度。经典气泡公式：

$$\text{Bubble fraction} = \frac{p-1}{m+p-1}$$

其中 $p$ 是流水线级数，$m$ 是 micro-batch 数。直觉：级数越多气泡越大，所以要么堆够多 micro-batch，要么用交错调度（后来 Megatron 的 interleaved 1F1B、DeepSeek 的 DualPipe 都是在这个方向上卷）。

### 4.3 ZeRO（2019）：另一种切法

微软 Deepspeed 团队的 ZeRO 换了个角度：**别切计算，切"训练状态"**。混合精度训练下，一个参数的完整状态其实很胖：

| 状态 | 字节/参数 |
|---|---|
| FP16 参数 | 2 |
| FP16 梯度 | 2 |
| FP32 参数副本 | 4 |
| FP32 momentum（Adam） | 4 |
| FP32 variance（Adam） | 4 |
| **合计** | **16** |

一个 7B 模型，光训练状态就是 112 GB——这就是为什么"7B 模型 fp16 只要 14 GB 但根本训不动"是每个初学者的第一课。ZeRO 的观察是：数据并行下每张卡都**冗余**地保存了全部这些状态，那就切开放：

- **ZeRO-1**：切优化器状态（7B 模型单卡显存从 112 GB → 31.4 GB）
- **ZeRO-2**：再切梯度（→ 18.8 GB）
- **ZeRO-3**：再切参数（→ 2 GB 级别，代价是前向/反向要临时 all-gather 参数）

### 4.4 合流：3D 并行

2021 年，Megatron + DeepSpeed 联手训练 Megatron-Turing NLG 530B，把 TP（机内）+ PP（机间）+ DP（跨副本）组合成完整的"3D 并行"，成了此后所有大模型训练的模板。今天 Megatron 的文档里你能看到更夸张的组合：**TP × PP × CP × EP × DP 五维并行**（CP 切序列长度、EP 切 MoE 专家），总卡数 = 各维乘积——DeepSeek-V3 就是 16-way PP × 64-way EP × ZeRO-1 DP 的组合。

这三年还有一条重要的暗线：**激活值重计算**（用时间换显存，反向时重算前向激活）和 **CPU offload**（ZeRO-Offload/Infinity，把优化器状态放内存/NVMe）。它们和 ZeRO 一起，构成了"显存墙"的完整攻防体系。

## 5. 编译器与 Kernel（2019-2024）

并行方式解决的是"多卡怎么协作"，这一节解决的是"单卡为什么跑不满"。

分析工具是经典的 **Roofline 模型**。一个 kernel 的性能上限由两条线决定：

$$\text{算术强度} = \frac{\text{FLOPs}}{\text{读写字节数}}, \qquad \text{拐点} = \frac{\text{峰值算力}}{\text{峰值带宽}}$$

算术强度低于拐点，你就是 memory-bound（算得快没用，喂不动数据）；高于拐点，才是 compute-bound。现代 GPU 的拐点高得吓人——B200 上大约 280+ FLOP/byte，而很多"看着计算量很大"的算子（比如注意力里的 softmax）算术强度其实只有几十，妥妥的带宽瓶颈。**现代 infra 的很大一部分工作，本质上是把低算术强度的 kernel 改造成高算术强度的**。

改法有三层，按出现时间排：

**手写 kernel（2014-2019）**：cuDNN 时代，专家手写 CUDA。门槛极高，一个资深 kernel 工程师的产出直接决定一个模型能不能跑快。

**编译器（2017-2023）**：XLA（Google）证明"把计算图编译后再执行"能省掉大量冗余访存；TVM 走通用编译路线；OpenAI 的 **Triton**（2019）找到了一个绝妙的卡位——用"类 NumPy 的 Python"写分块程序，编译器帮你生成还不错的 CUDA，把 kernel 开发门槛从"资深"降到"会用 PyTorch 就能学"。到今天，vLLM 里的 paged attention、Liger Kernel、大量 MoE kernel 都是 Triton 写的。

**图编译（2023-）**：PyTorch 2.0 的 `torch.compile` 把"编译"这个动作交到了普通用户手里——`model = torch.compile(model)` 一行代码，TorchDynamo 捕获 FX 图、Inductor 做算子融合、自动生成 Triton kernel。一个 decoder block 的 kernel 启动次数可以从十几次压到四五次。

这一层最重要的故事其实是 **FlashAttention（2022）**——它是"算法-硬件协同设计"的完美标本。注意力本身的数学没变，但把计算重排成 tile 住 SRAM、在线 softmax（数学上严格等价），就把一个 $O(N^2)$ 显存的操作变成了 $O(N)$，直接把长上下文从不可行变成可行。专栏第二篇有它的完整拆解；这里只强调一点：**FlashAttention 出现之前，没有任何编译器能自动把它推出来**。这说明 kernel 层的专家知识在可预见的未来仍然不可替代——2026 年最前沿的尝试（PyTorch 团队的 KernelAgent：让 LLM 读硬件 profiling 数据、自动做 roofline 诊断再优化 Triton kernel，在 KernelBench L1 上平均超过 torch.compile 1.56 倍、达到 H100 屋顶线效率的 89%）已经把"kernel 工程师"这个工种本身变成了 AI 的作业对象，多少有点赛博达芬奇画蛋的意味。

## 6. 网络军备赛：把机房变成一台计算机

前面反复出现一个变量：**GPU 之间的带宽**。这一节讲它怎么一路涨上天的。

先把两个概念分开：**scale-up**（机内/机架内互连，NVLink）和 **scale-out**（机间/集群网络，InfiniBand/以太网）。TP 这类高频通信住 scale-up 域，DP/EP 这类大块数据传输走 scale-out 域。

**NVLink 这条线**，本质是"PCIe 不够用了"（PCIe Gen5 双向也就 128 GB/s，喂不饱 GPU 间梯度交换）：

| 代际 | GPU | 每卡带宽 |
|---|---|---|
| NVLink 1（2016） | P100 | 160 GB/s |
| NVLink 2（2017） | V100 | 300 GB/s |
| NVLink 3（2020） | A100 | 600 GB/s |
| NVLink 4（2022） | H100 | 900 GB/s |
| NVLink 5（2024） | B200 | 1.8 TB/s |
| NVLink 6（2026） | Rubin（VR200 NVL72） | 机架级总带宽约 250 TB/s |

2018 年 DGX-2 引入 **NVSwitch**（NVLink 的交叉开关），让 16 卡全互联成为可能；到 Blackwell 代的 **GB200 NVL72**，一个机架 72 张 GPU 通过机架级 NVSwitch 连成一个统一的 NVLink 域，总带宽 130 TB/s——NVIDIA 官方的说法是"整个机架就是一台 GPU"。这不是修辞：NVL72 上跑 TP，延迟和机内跑几乎没差别。

2026 年 8 月，**Vera Rubin 平台正式量产**，把这条曲线又推了一格：VR200 NVL72 用 72 张 Rubin GPU + 36 颗 Vera CPU（88 个自研 Olympus 核、1.2 TB/s 内存带宽），配 HBM4 和 NVLink 6，官方口径是单机架 token 吞吐达到 GB200 架构的 10 倍，FP4 稀疏算力每节点 50 PFLOPS。供应链也随之换血：HBM4 三家原厂（SK 海力士/三星/美光）在 2026 年三季度全面量产，台积电 CoWoS 先进封装月产能年底突破 13 万片——**AI 算力的瓶颈正在从 GPU 本体转向先进封装和 HBM 产能**，这是 Infra 叙事里新的一层。价格也在重构：一台 VR200 NVL72 机架约 780 万美元（Bernstein 的落地成本调研口径接近 910 万），几乎是 GB300 的一倍——算力增长的同时，"单位算力的资本开支"并没有下降。

**scale-out 这边**是 InfiniBand 和以太网（RoCE）的长期对峙。IB 延迟亚微秒、自带 SHARP（在交换机里直接做归约，all-reduce 带宽翻倍），是超算和头部 AI 工厂的黄金标准；RoCE 用通用以太网硬件承载 RDMA，便宜、生态开放，NVIDIA 用 Spectrum-X（针对 AI 调优的以太网）在这个市场追赶。到 2025-2026 年，两边的带宽都到了 800 Gbps（XDR），拓扑上统一收敛到 **rail-optimized fat-tree**：每台机器的 8 张网卡各接一台 leaf 交换机（同号 GPU 接同一台 leaf），上层 spine 无阻塞全互联——这样跨机 TP/EP 的同号 GPU 通信永远只穿两跳，物理拓扑和通信模式对齐。

最后是能耗这堵新墙：一个万卡集群功率几十 MW（NVL72 单机架 120 kW 起），数据中心选址从"哪里地价便宜"变成"哪里有电"。AI Infra 的最新一层（液冷、直流母线、CPO 光电共封装）已经完全是电力工程了。**"数据中心即计算机"这句话，2026 年是字面成立的。**

而且这个"计算机"的规模单位已经从兆瓦（MW）换成了吉瓦（GW）。2026 年下半年两件事给这个时代盖了章：其一，NVIDIA 与 OpenAI 签下至少 **10 GW** 的系统部署意向、分期投入至多 1000 亿美元，首批设施 2026 年内上线——一家模型公司锁定十座核电站级别的算力；其二，SpaceX 和 NVIDIA 把 Vera Rubin NVL72 做成了**抗辐照的卫星版本（Starmind）**，计划 2027 年四季度发射首批"轨道数据中心"，理由是轨道上太阳能无限、不用买地、不用过环评——尽管 Wood Mackenzie 估算 1 GW 轨道数据中心的建造成本约 1700 亿美元（同等地面设施的三倍多）。当 Infra 的战场从机房延伸到近地轨道，你很难说这是泡沫还是未来——大概率两者都是。

## 7. 推理革命（2022-2024）：操作系统思想占领 LLM

训练 infra 的关键词是"规模"，推理 infra 的关键词是"利用率"。这一段的精彩程度不输任何算法突破——因为它本质上是操作系统思想对 LLM serving 的一次全面移植。

先看问题。LLM 推理有个要命的结构性特征：**生成是逐 token 的串行过程**，而 GPU 擅长并行。如果一条请求一个 GPU 地跑，GPU 利用率低到离谱；如果凑一批请求一起跑（静态批处理），长短不齐的请求会让先做完的占着槽位干等——一批 16 个请求里如果有一个要生成 500 token、其他都是 20 token，那 15 个请求要陪着空转 480 步。

**第一个突破口：Orca（OSDI 2022）的连续批处理**（continuous batching，也叫 iteration-level scheduling）。调度粒度从"请求"降到"迭代"——每生成一个 token 就重新调度一次，做完的立刻下车、排队的立刻上车，让 GPU 的 batch 永远是满的。就这一个改动，吞吐提升最高 **36.9 倍**。这其实就是操作系统"分时复用"的老思想：CPU 不会因为一个进程 sleep 就闲着。

**第二个突破口：vLLM（SOSP 2023）的 PagedAttention**。KV Cache 的问题专栏第二篇详细算过账：序列长度预先未知，按最大长度预留显存造成严重内部碎片，实测显存利用率只有 60% 左右。vLLM 的解法直接照抄操作系统虚拟内存：KV Cache 切成固定大小的 block，逻辑块到物理块靠"页表"（block table）映射，物理块不必连续，还支持写时复制（beam search 分叉时多个序列共享块，写时才复制）。显存利用率直接拉到 95%+，并发数随之大涨。2023 年 6 月 vLLM 开源后迅速成为事实标准——2025 年加入 PyTorch 基金会时，报告的部署量超过 30 万张 GPU。

**第三个突破口：SGLang（2024）的 RadixAttention**。很多请求共享前缀（系统提示词、few-shot 模板、agent 的历史消息）。SGLang 用一棵**基数树**（radix tree）管理所有已生成的 KV Cache，新请求来了先在树上匹配最长前缀，命中就免费复用。这对 agent 负载（每轮对话都带着完整历史）是数量级的收益。SGLang 后来在生产端增长极快（2026 年报告驱动 40 万+ GPU），加上结构化输出、投机解码的工程化都做得很深。

**第四个突破口：投机解码（2022-2023）**。用小模型（或 MTP 头）一次猜几个 token，大模型并行验证——串行瓶颈被"猜+验"的并行模式部分绕开，2-3 倍延迟收益，且数学上保证和大模型自回归输出同分布。专栏第二篇讲 MTP 时提过它的训练侧版本。

这一波浪潮里每个点子单拿出来都不复杂——连续批处理是分时系统、PagedAttention 是虚拟内存、RadixAttention 是缓存、投机解码是分支预测。**LLM serving 的历史给人的启示：当一个问题变成"系统问题"，六十年的系统学积累会整体平移过来。** 这个规律在接下来两节还会重演。

## 8. DeepSeek 时刻：极致的软硬协同（2024）

如果只能选一个案例讲"工程艺术的巅峰"，我会选 DeepSeek-V3（2024 年 12 月）。先看一组数字：671B 参数（激活 37B）的模型，**2048 张 H800**（对华限配版 H100）训练，总成本 2.788M GPU 小时（按租赁价折合约 558 万美元），全程**零不可恢复的 loss spike、零回滚**。对比同期用一万多张 H100 训练的 Llama 3 405B，这份成绩单像来自另一个时代。

拆开看它是怎么做到的，每一层都是上一节内容的极致应用：

**并行策略上反主流**：完全不用 TP（他们判断跨卡 TP 的通信不划算），改用 16-way PP + 64-way EP + ZeRO-1 DP 的组合，把通信重头放在 MoE 的 all-to-all 上，然后专门优化它。

**DualPipe**：流水线气泡和通信开销用"双向微批"彻底对冲——微批从流水线两端同时灌入，前向计算和 all-to-all 通信完全重叠，GPU 利用率压到接近理论值。这是 4.2 节气泡公式那条线的终点站。

**FP8 训练**：训练主力精度直接上 FP8（细节在专栏第三篇讲过），对 H800 的 FP8 Tensor Core 榨得干干净净，配套的细粒度分块量化方案后来直接影响了整个行业（NVIDIA 后来的 NVFP4 思路里能看到它的影子）。

**通信 kernel 自研**：跨节点 all-to-all 的 kernel 自己写，同时吃满 IB 和 NVLink 的带宽，还只占用少量 SM——剩下的 SM 继续做计算。

**架构为 infra 量身定做**：MLA 把 KV cache 压到 70 KB/token（Llama 3 405B 是 516 KB/token），MoE 把每 token 计算量压到 250 GFLOPs（Llama 3 405B 是 2448 GFLOPs）。这两条在专栏第二、三篇都出现过——它们同时也是 infra 决策：**上游的每一次"省"，都直接决定下游集群的规模和成本**。

DeepSeek 之后行业学到的最大一课是：**infra 不是"买卡 + 装框架"的运维问题，而是和模型架构一体的设计问题**。他们的技术报告甚至专门写了一节"给硬件厂商的建议"（通信硬件要有更强的 all-to-all 支持、计算硬件要更好的 FP8 累加精度）——一个训练团队反过来给 NVIDIA 提需求，这在几年前是不可想象的。

顺带把开源生态的另一半补齐：Megatron-LM 这条线在这两年向着 MoE 疯狂进化（DeepEP 通信库集成、EP×DP×TP×PP×CP×VPP 全组合支持、CUDA Graph for MoE），国内字节（veRL、VeOmni）、阿里（RollArt、AgentJet）都在自建 RL 栈（见第 11 节）。**LLM infra 的重心正在从"预训练"整体平移到"后训练 + 推理"**——因为预训练的玩法已经被 DeepSeek 们卷到边际收益递减了。

## 9. 万卡运维：故障才是常态（2024-2026）

前面讲的都是"怎么快"，这一节讲"怎么活着"。它是最容易被科普忽略、却最贴近真实生产的部分。

Meta 训练 Llama 3 405B 的报告（16384 张 H100，54 天预训练）披露了一组此后被广泛引用的数据：**466 次训练中断，其中 47 次是计划内维护，419 次是意外故障——平均每 3 小时坏一次**。故障分布：GPU 相关占 58.7%（GPU 本体 30.1% + HBM3 显存 17.2% + 其他），网络线缆/网卡/交换机占 8%，而 CPU 在 54 天里只坏了 2 次。**GPU 的故障率是 CPU 的上百倍**——700W 功耗、数万次/天的电压电流波动，HBM 在高温下的位翻转，都是常态。

这张故障分布表反过来定义了万卡运维的全部技术栈：

- **checkpoint 体系**：故障后恢复的基础。万卡模型 checkpoint 几 TB，写一次几十分钟，频率和成本要精确平衡——太疏丢进度，太密浪费训练时间。业界现在的做法是异步分层 checkpoint（先写显存/内存，再慢慢落盘 NVMe/对象存储）。
- **自动诊断和排除**：Meta 用 PyTorch NCCL flight recorder 抓通信现场，自动定位"拖后腿"的 GPU（一张慢卡拖慢一万五千张卡）。419 次故障里只有 3 次需要人工干预，其余全自动恢复——**自动化容错把有效训练时间（MFU 分母）撑到 90% 以上**，这才是"万卡集群"能用起来的真正前提。
- **环境监控**：温度波动影响 1-2% 吞吐（频率动态调压的连锁反应），供电瞬时几十 MW 的波动会打到电网极限——运维团队开始需要懂电力的人。

到了 2026 年，这个方向有个新名字：**AI Factory Ops**。十亿瓦级数据中心、液冷、以"训练任务"为一等公民的调度器（gang scheduling：一万个进程要么一起起、要么一起等）、checkpoint 的容灾演练……训练一个前沿模型从"跑个实验"变成了"运营一座工厂"。

## 10. PD 分离与 KV Cache 外置（2024-2026）

推理 infra 在 2024 年后进入"架构重构期"，两波浪潮都源于同一个洞察：**prefill 和 decode 是两种完全不同的负载**。

- **Prefill**（处理输入、填 KV cache）：一次大并行矩阵乘，**compute-bound**，要的是算力。
- **Decode**（逐 token 生成）：每步只算一个 token 却要读全部 KV cache，**memory-bound**，要的是带宽。

两者挤在同一批 GPU 上会互相伤害：一个长文档的 prefill 一跑几百毫秒，正在 decode 的请求全部卡顿（用户观感：生成到一半突然停住）。混部怎么调优都治标不治本。

**解法：物理分离（PD disaggregation）。** Prefill 集群和 decode 集群分开部署，中间用高速网络传 KV cache。DistServe（OSDI 2024）给出了系统化的论证；真正出圈的是月之暗面的 **Mooncake**（FAST 2025 最佳论文）——Kimi 的生产平台，它把这个思想推到了尽头：

1. **KV Cache 成为架构的一等公民**。用集群里闲置的 CPU DRAM + SSD + RDMA 网卡，组一个分布式的 KV cache 池（"以空间换计算"）；
2. **全局调度器 Conductor**：每个调度决策都围绕"哪台机器上已经有这个请求可复用的 KV cache"来算——调度问题变成了缓存放置问题；
3. **实测**：长上下文场景下有效请求容量提升 59%~498%，生产集群数千节点、日处理 token 过千亿。

为什么这事重要？因为** agent 时代的负载就是极端化的长上下文 + 高前缀复用**——一个 agent 会话几十轮，每轮都带着完整历史，而历史的前缀几乎不变。KV cache 外置 + 前缀复用，把这种负载的成本压了一个数量级。2026 年这个方向的生态已经成型：Mooncake 作为独立的 KV cache 存储引擎被 vLLM/SGLang 集成，K8s 侧出现了专门编排"推理角色 + 缓存角色"的 API（阿里和 SGLang 团队的 RBG）。

配套的还有两个概念值得记住：**TTFT/TBT 的 SLO 二元组**（首 token 时间和 token 间隔对延迟感知完全不同，不能混在一个指标里优化），和 **goodput**（满足 SLO 的吞吐——一个系统可以 raw throughput 很高但 goodput 为零，因为没有一个请求是"及时"的）。**指标的定义方式决定架构的形态**，这在 infra 史上反复应验。

## 11. RL Infra：2026 年最热的战场

如果说 2023-2024 是推理 infra 的爆发期，那 2025-2026 的爆发期属于 RL infra。驱动它的不是新算法（PPO/GRPO 都是老朋友），而是**负载本身变形了**：

- **RLHF → 可验证奖励 RL（R1 式）→ agentic RL**：训练对象从"对齐偏好"变成"多轮和环境交互的任务能力"；
- **rollout 成为瓶颈**：每个训练 step 都要让当前策略生成大量轨迹（采样几万条长思维链、或跑几千个环境回合），rollout 集群的规模常常是训练集群的几倍；
- **三种负载异质共存**：训练（compute-heavy）、生成（prefill + decode 混合）、环境/奖励（常常是 CPU 密集的沙盒或另一个模型）——单一并行策略没法同时喂饱它们。

这个领域的代表作是字节跳动的 **veRL**（HybridFlow）：用"混合控制器"架构——上层单控制器编排 RL 数据流（哪些轨迹进 buffer、何时触发训练、参数何时同步给 rollout 集群），内部各引擎（Megatron/FSDP 训练、vLLM/SGLang rollout）保持 SPMD 集合通信的效率。5D 并行被封装在 Model Engine 里，算法工程师写 RL 逻辑时完全不用感知。vLLM 生态的 vime、更激进的 AgentJet（swarm 架构：agent 进程自治地和训练集群交互）、阿里的 RollArt（硬件亲和映射：compute-bound 的给强卡、带宽敏感的给另一类，无状态奖励模型丢给 serverless；3000+ GPU 训练百亿级 MoE，端到端时间比同步基线快 1.35-2.05 倍）——都在同一个方向上卷：**把 RL 训练从"同步大锁"拆成异步流水线，消灭 GPU 空转的"依赖气泡"**。

同步 vs 异步的取舍是这里的永恒主题：同步训练（等最新权重）正确性干净但气泡大；异步训练吞吐高但存在 staleness（旧策略生成的样本喂给新策略）。轨迹级异步（以单条轨迹为调度粒度）是 2026 年的主流答案。

另一条平行线是**推理和训练的融合**：RL 让"训练集群"和"推理集群"的边界模糊了——rollout 本质上就是推理，所以 Mooncake 这套 KV cache 基建在 RL 里同样适用（多个 rollout 实例共享前缀 KV），训练引擎和推理引擎的权重同步（rollout 侧要拿到最新策略）成了新的系统问题（vLLM 的 RLHF 文档和各家的"权重热更新"方案都是干这个的）。

## 12. 实战：普通工程师怎么用好这些知识

看完万卡集群，回到自己的一两台机器——这些历史对普通人的直接用处，按角色分：

**做训练（微调）的人**：先算显存账（4.3 节那张表），单卡/单机放得下就用 DDP；放不下上 FSDP（PyTorch 原生，ZeRO-3 思路）或 LoRA/QLoRA（专栏第三篇）。**始终盯 MFU（模型算力利用率）**：你的有效吞吐 ÷（卡数 × 峰值算力），低于 35% 就该 profiling 了——最常见的三个坑是 dataloader 喂不上（GPU 等数据）、CPU 预处理成了串行瓶颈（`nvidia-smi` 里 GPU 利用率锯齿状波动是典型症状）、以及没用混合精度。工具就两个：`torch.profiler` 和 Nsight Systems，看 timeline 哪里有空洞。

**做推理部署的人**：按第 7、10 节的逻辑选引擎——H100/B200 集群且追求极限吞吐，TensorRT-LLM 或 SGLang；通用场景和最广生态，vLLM；苹果芯片，MLX；边缘设备，llama.cpp。调优时先分清你的负载是 prefill-heavy（长文档问答，关注 TTFT 和 chunked prefill）还是 decode-heavy（长生成，关注并发数和投机解码）；有大量重复前缀（agent、RAG）务必开 prefix caching / RadixAttention，这可能是收益最大的一个开关。监控指标用 goodput 的思路定义（P99 TTFT + P99 TBT 达标率），别只看 tokens/s。

**做 Agent 开发的人**：你已经身处第 10、11 节的世界。会话保持亲和（让同一会话落到同一实例，前缀缓存才能命中）；历史裁剪策略比换更大模型更省钱；如果你的平台有 KV cache 外置能力（HiCache、Mooncake 后端），长会话成本能降一个数量级。

**判断瓶颈位置的四步法**（在任何规模都适用）：

1. 算术强度够不够？（Roofline：先分清 compute-bound 还是 memory-bound）
2. 通信占比多大？（多卡时先看是 TP 跨机了还是 AllReduce 太频繁）
3. 利用率墙在哪？（是 GPU 空转等数据，还是 kernel 本身低效）
4. 故障域多大？（备份和 checkpoint 策略，哪怕只是单机的自动存档）

**最后一条心得**：AI Infra 的技术半衰期其实很短（vLLM 重构了一版、Megatron 每季度一个 roadmap），但三堵墙（显存、通信、利用率）的框架十五年没变过。**学具体工具会过时，学瓶颈的物理学会复利**——细节在变，骨架很稳。

## 13. 尾声：四篇合奏

至此专栏四篇完结。把它们摞在一起看，一个完整的图景浮现出来：**一个 token 的旅程，就是一路被"降本增效"的旅程**——

第二篇（分词）：信息以什么粒度进入系统（token 怎么切最省）；
第一篇（注意力）：计算以什么结构流动（注意力怎么算最快、KV cache 怎么存最小）；
第三篇（量化）：存储以什么精度落库（每个数字用几个 bit）；
本篇（infra）：所有这一切跑在什么样的机器、网络和调度系统上（怎么让一万张卡同时干活）。

四篇其实是同一门学问的四个剖面：**在精度、速度、成本的不可能三角里，给每个具体负载找平衡点**。而且它们互相成就——MLA 让 KV cache 变小，所以 PD 分离的传输才可行；tokenizer 的前缀复用特性，造就了 RadixAttention 的整个价值；FP8 训练的落地，一半功劳属于 Hopper 的 Tensor Core。**算法和系统的最优解，从来都是一起找到的。**

## 14. 参考资料

- Dean et al., *Large Scale Distributed Deep Networks (DistBelief)*, NeurIPS 2012
- Li et al., *Scaling Distributed Machine Learning with the Parameter Server*, OSDI 2014
- Shoeybi et al., *Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parallelism*, 2019
- Huang et al., *GPipe: Efficient Training of Giant Neural Networks using Pipeline Parallelism*, NeurIPS 2019
- Rajbhandari et al., *ZeRO: Memory Optimizations Toward Training Trillion Parameter Models*, SC 2020
- Smith et al., *Using DeepSpeed and Megatron to Train Megatron-Turing NLG 530B*, 2021
- Dao et al., *FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness*, NeurIPS 2022
- Yu et al., *Orca: A Distributed Serving System for Transformer-Based Generative Models*, OSDI 2022
- Kwon et al., *Efficient Memory Management for Large Language Model Serving with PagedAttention (vLLM)*, SOSP 2023
- Zheng et al., *SGLang: Efficient Execution of Structured Language Model Programs*, 2024
- Zhong et al., *DistServe: Disaggregating Prefill and Decoding for Goodput-optimized LLM Serving*, OSDI 2024
- Qin et al., *Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving*, FAST 2025
- DeepSeek-AI, *DeepSeek-V3 Technical Report*, 2024（第 3 章 Infrastructures）
- Dubey et al., *The Llama 3 Herd of Models*, 2024（集群故障数据）
- Sheng et al., *HybridFlow: A Flexible and Efficient RLHF Framework (veRL)*, EuroSys 2025
- RollArt: *Scaling Agentic RL Training via Disaggregated Infrastructure*, 2025
- NVIDIA DGX SuperPOD / NVL72 参考架构文档；NVIDIA《迎接十亿瓦数据中心时代》博客（2025）
- 中证鹏元《Vera Rubin 开启量产周期》专题报告（2026-08）；Vera Rubin NVL72 / Vera CPU / Starmind 相关官方与媒体报道（2026-08）
- NVIDIA × OpenAI 10 GW 合作公告相关报道（2026-09）；SpaceX × NVIDIA Starmind 轨道数据中心报道（2026-08）
- Meta Llama 3 集群运维数据的相关报道（TweakTown / shiftdelete 等对技术报告的转述，2024-07）
- vLLM 与 SGLang 官方文档及 2026 年生态报告
