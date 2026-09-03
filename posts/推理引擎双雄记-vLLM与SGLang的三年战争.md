---
title: 推理引擎双雄记：vLLM 与 SGLang 的三年战争
date: 2026-09-03
tags: [深度学习, AI Infra, vLLM, SGLang, 推理引擎]
album: 深度学习专栏
order: 5
excerpt: 从 PagedAttention 和 RadixAttention 两种哲学出发，复盘 vLLM 与 SGLang 三年的缠斗：V1 重构、DeepSeek 之战、基准测试的罗生门、Rust 化与商业化，以及两个引擎正在趋同的 2026 年。
---

这是《深度学习专栏》的第五篇，可以看作上一篇《AI Infra 全解》第 7 节的展开——那次写推理革命只给了一千字的篇幅，但 vLLM 和 SGLang 这两个项目值得单独写一篇。

写这篇的动机有个私心：我自己部署模型时，"到底用哪个"这个问题反复出现过太多次，每次去搜，得到的答案都是过时的或互相矛盾的（A 说 SGLang 快 29%，B 说 vLLM 高并发强，C 说"看场景"——等于没说）。所以这次我把两个项目三年的发展史从头捋了一遍，结论是：**这个问题的答案确实随时间漂移，但漂移的方向是有规律的**。把史实搞清楚之后，"怎么选"反而变得简单了。

---

## 目录

1. 引子：编译器战争的重演
2. 前传：没有好引擎的年代（2022-2023）
3. vLLM 简史：从一篇论文到一个基金会
4. SGLang 简史：从一门语言到一个引擎
5. 架构对撞：两种哲学的正面交锋
6. 基准测试的罗生门
7. 各自的 2026：忙着不同的事
8. 未来展望：趋同、分叉与商业化
9. 实战：2026 年年中怎么选
10. 尾声：五篇合奏
11. 参考资料

---

## 1. 引子：编译器战争的重演

先说一个观感：vLLM vs SGLang 这场竞争，和当年 GCC vs LLVM 的结构惊人地像。

vLLM 如 GCC——先出现、定义了问题本身（PagedAttention 之于 KV cache，正如 GCC 之于开放编译生态）、社区最大、贡献者最多（2000+）、硬件后端最全，是所有人的默认第一选择；SGLang 如 LLVM——更年轻、代码库更轻、架构上更激进（一开始就把"前缀复用"当作一等公民而非后补特性）、迭代速度快、在特定战场上（DeepSeek 系、agent 负载）常常更快。

这种格局在基础设施软件的历史上一再重演，而且结局通常是**双赢的持久共存**：GCC 和 LLVM 都活着，分别统治不同场景。所以我先剧透结论——这篇文章不是要选出一个赢家，而是想讲清楚那条分界线到底画在哪，以及它为什么一直在移动。

## 2. 前传：没有好引擎的年代（2022-2023）

上一篇讲过 Orca（OSDI 2022）用连续批处理把推理吞吐提升了最高 36.9 倍，这里补充当时工业界的另一条线：NVIDIA 的 FasterTransformer 走"手写 kernel 极致优化"路线，HuggingFace 的 TGI 走"快速堆功能"路线。2023 年上半年之前，开源推理的现状是——每个方案都缺一块：Orca 没开源，FasterTransformer 难用且只支持少数模型，TGI 的显存管理粗糙，KV cache 的浪费率普遍在 60-80%。

这个空窗期就是 vLLM 的机会窗口。

## 3. vLLM 简史：从一篇论文到一个基金会

### 3.1 出身（2023）

vLLM 出自 UC Berkeley 的 Sky Computing Lab（Woosuk Kwon、Zhuohan Li 等，导师是 Ion Stoica——就是那个 RDD 论文作者、AMPLab/Apache Spark 背后的 Ion Stoica，系统圈的嫡系血脉）。2023 年 6 月开源，10 月论文上了 SOSP。

核心贡献只有一个，但足够狠：**PagedAttention**。上一篇讲过它的思想——照抄操作系统虚拟内存的分页机制管 KV cache，显存浪费从 60-80% 压到 4% 以下，吞吐比当时的 SOTA（FasterTransformer、Orca）高 2-4 倍。这里补一个当年被忽略的细节：vLLM 这个名字里的 "v"，指的就是 "virtual"（虚拟内存）——整个项目是一个双关语。

出生头两年最关键的决策其实是**社区运营**：项目从第一天就按中立开源社区来运营，公司旗帜降到最低，这为它后来吸纳 Red Hat（Neural Magic）、Anyscale、IBM、AMD、Intel、NVIDIA 的持续贡献铺平了路。到 2025 年，月均 PR 800+，成为 GitHub 上最活跃的 AI infra 项目之一。

### 3.2 V1 重构：壮士断腕（2024-2025）

2024 年中，团队遇到了经典的"成功者的困境"：功能各自为战地堆了一年半（投机解码、前缀缓存、chunked prefill……），互相组合会出 bug，技术债堆积。"V0 的每个功能单独测试都很好，一起用就没人说得清行为"——这是他们自己博客里的话。

于是有了 2025 年 1 月的 **V1 重构**。四个设计目标值得逐条品味，因为它们代表了推理引擎的"第二次抽象"：

1. **统一调度器**：取消 prefill/decode 的阶段区分，一切调度决策表示成一个字典 `{request_id: num_tokens}`——这个表示简单到可以统一支持 chunked prefill、前缀缓存、投机解码（上一代架构里这三个功能各有各的调度路径，组合即灾难）；
2. **异步调度**：API server、tokenizer、detokenizer 移出关键路径，`EngineCore` 独立进程专注调度和执行——小模型在 H100 上单步执行只要 5ms，Python 的 CPU 开销成了主要瓶颈，这在 2023 年是不可想象的（那时模型每步几百 ms，CPU 慢点无所谓）；
3. **零开销前缀缓存**：V0 里前缀缓存默认关闭（命中率低时反而降速），V1 优化到命中率 0% 时损失也小于 1%，于是敢默认开启——**"默认开启一切"成了 V1 的口号**；
4. **TP 通信架构清理**：每个 worker 平等地接收广播，不再有"worker 0 兼任调度器"的特权设计。

时间线：2025 年 1 月 alpha，3 月（v0.8.0）成为默认引擎，10 月（v0.11.0，538 commits、207 位贡献者）**彻底删除 V0 代码**。一年内完成心脏移植手术，而且是在月活几百万 GPU 的生产系统上做的——这个执行魄力，是 vLLM 历史上我认为最被低估的一页。

### 3.3 成人礼（2025-2026）

- **2025 年 5 月**：加入 PyTorch 基金会，获得中立治理身份（和当年 Linux 基金会收编的剧本一样——都发生在项目成为行业公共设施之后）；
- **2025 年 12 月**：HuggingFace 官方宣布 TGI 进入维护模式，推荐用户迁移到 vLLM。一个时代正式落幕：**"开源推理引擎"这个赛道的第一轮洗牌结束，vLLM 拿走了通用场景的王座**（到 2026 年年中 79K stars，官方口径驱动 40-50 万张 GPU）；
- **2026 年 1 月**：核心维护者团队（Simon Mo、Woosuk Kwon 等）成立商业化公司 **Inferact**（首轮融资 1.5 亿美元、估值 8 亿）——注意模式是"开源引擎之上的托管服务"，引擎本身依然 Apache 2.0，社区反复强调这一点。

## 4. SGLang 简史：从一门语言到一个引擎

### 4.1 出身（2023-2024）：被名字耽误的引擎

SGLang 的出身容易被误解。它的名字全称是 **S**trured **G**eneration **L**ang...（Structured Generation Language）——它最初真的是一门语言：LMSYS 团队（Lianmin Zheng、Ying Sheng 等，同样是 Berkeley 系，LMSYS 就是做 Chatbot Arena 的那个组织）想解决的是"多次 LLM 调用组成复杂程序"的编程问题，前端是一个 Python 嵌入式 DSL，为多步调用提供缓存、并行、约束解码的原语。

但历史很快证明：**这门语言附赠的推理引擎比语言本身重要得多**。因为要做跨调用的 KV cache 复用，他们顺手发明了 RadixAttention；因为引擎性能领先，各大厂开始拿它跑生产。于是项目的重心完全转向了引擎，"语言"退化成一个研究 API。这是 infra 史上常见的"副产物逆袭"——为了 A 发明的 B，最后 A 没人用、B 成了基石。

版本节点（每个都是一次性能飞跃的宣言）：

| 版本 | 时间 | 关键词 |
|---|---|---|
| v0.1 | 2024-01 | RadixAttention：前缀复用 5 倍吞吐；约束解码 3 倍 |
| v0.2 | 2024-07 | overlap scheduler：CPU 开销砍 3 倍 |
| v0.3 | 2024-09 | DeepSeek MLA 的 Triton kernel 7 倍；torch.compile 1.5 倍 |
| v0.4 | 2024-12 | 零开销调度器、cache-aware 路由、XGrammar、全球首个跑通 DeepSeek V3 |

### 4.2 DeepSeek 之战（2024-2025）

SGLang 真正的成人礼是 DeepSeek。2024 年 12 月 DeepSeek V3 发布时，SGLang 是全球第一个跑通它的开源引擎；2025 年 1 月 R1 爆火，SGLang 提供 day-1 支持（NVIDIA + AMD）。这背后是长期的技术押注：v0.3 就为 MLA 写了专用 Triton kernel，而 MLA 恰好是 DeepSeek 系的核心结构。

2025 年 5 月的战役最典型：SGLang 发布了 DeepSeek V3/R1 的**专家并行 + PD 分离**开源实现，96 张 GPU 上做到每节点 52.3K input tok/s，号称比 DeepSeek 官方 API 价格便宜 5 倍，10+ 个团队复现。这次战役给 SGLang 打下的标签——"新架构模型的 day-0 支持"——成了它此后最重要的护城河：DeepSeek V3.2（DSA 稀疏注意力）、gpt-oss、GLM-4.5、Kimi K2/K3、Qwen3.5……2025 年下半年起，"新模型发布当天哪个引擎能跑"几乎成了两个团队的赛点。

用户结构的分水岭也在这里：**SGLang 成了 xAI（Grok，10 万+ GPU）的默认推理引擎，也是 AMD 生态的事实标准引擎**（Azure 上的 DeepSeek-on-MI300X 就是 SGLang 方案）。一个偏前沿实验室 + 非 NVIDIA 硬件的联盟，和 vLLM 的"最大公约数"联盟形成了有趣的对照。

### 4.3 引擎之外（2025）

SGLang 2025 年的另一条主线是把引擎变成生态，四个作品都值得记：

- **slime**：自研 RL 框架（Megatron 训练 + SGLang rollout），给 GLM-4.5/4.6 做了大规模训练——推理引擎公司反过来定义 RL 训练栈，这个信号在上一篇第 11 节提过；
- **HiCache**：分层 KV cache（GPU → CPU → 存储，可插拔 Mooncake/3FS 后端），长上下文场景吞吐最高 6 倍、TTFT 降 84%；
- **SpecForge**：投机解码草稿模型（EAGLE-3）的训练流水线——"投机解码"从推理技巧变成了完整的训练生态；
- **SGLang-Jax**（2025-10）：纯 Jax/XLA 的 TPU 原生后端，为 Google 的 TPU 开放做卡位。

### 4.4 商业化（2026）

和 vLLM 殊途同归：2026 年 5 月，SGLang 的商业化主体 **RadixArk** 成立，模式和 Inferact 一模一样——开源引擎 + 商业托管。两家前后脚成立，剧本都抄的同一份（也许该说，抄的是 Databricks/Red Hat 的作业）。

## 5. 架构对撞：两种哲学的正面交锋

现在把两个引擎的核心差异摊开。一句话版本：**vLLM 的第一性问题是"显存怎么管"，SGLang 的第一性问题是"缓存怎么复用"**。

### 5.1 KV cache 管理：PagedAttention vs RadixAttention

两者不是同一层面的东西，这是最常见的误解。PagedAttention 解决的是**存储**问题（怎么放不浪费）；RadixAttention 解决的是**查找**问题（怎么知道能复用）。事实上 SGLang 内部也用分页存储，vLLM 后来也做了前缀缓存——真正 differed 的是数据结构和默认假设：

| | vLLM (V1) | SGLang |
|---|---|---|
| 数据结构 | 哈希前缀缓存 + LRU 驱逐 | 基数树（radix tree）全局管理 |
| 复用粒度 | 按 block 哈希匹配 | 树上最长前缀匹配，天然支持分叉共享 |
| 设计假设 | 复用是优化（默认开，但零开销才敢开） | 复用是架构的中心（调度、路由都围绕它） |
| 路由层 | 无内建 cache-aware 路由 | SGL-Router：按缓存命中最优选 worker |

基数树的实际收益在哪：多轮对话（新请求 = 旧会话 + 增量）、few-shot 批量调用（共享示例前缀）、agent 分叉（self-consistency 采样从同一前缀展开几十条）。SGLang 论文里的实测缓存命中率：Vicuna-33B 74.1%，LLaVA-Next-34B 52.4%。cache-aware 路由器把命中率从 round-robin 的 20% 拉到 75%，吞吐翻倍。而这一切对用户是透明的——SGLang 原文的卖点就是"自动的"。

### 5.2 调度器：殊途同归的两次重写

有意思的是，两家在过去三年各自做了一次"调度器重写"，而且答案几乎相同——**CPU 让开 GPU 的路**：

- vLLM V1 的 `EngineCore`：API/分词/流式输出全部移出执行循环，异步调度成为 2026 年的默认；
- SGLang v0.4 的 overlap scheduler：CPU 准备第 N+1 批和 GPU 算第 N 批重叠，把 batch 间隙从约 12ms 压到 38μs。

连最终归宿都一样：都觉得 Python 是瓶颈。vLLM 把 PagedAttention 核心下沉到 C++ CUDA 扩展；SGLang 走了两步——sgl-kernel 用 C++/CUDA，2026 年开始把 HTTP/tokenizer/detokenizer 的前端迁移到 Rust（v0.5.17 的 opt-in Rust server）。**推理引擎的宿命就是逐步抛弃 Python**，这条两家都逃不掉。

### 5.3 结构化输出：一场双方共建的胜利

约束解码（强制输出合法 JSON/正则）是 agent 时代刚需。这个领域的故事是罕见的合作叙事：SGLang 孵化了 **XGrammar**（MLC-LLM 团队开发，语法编译成位掩码，每 token 开销 <40μs），然后它成了 vLLM、SGLang、TensorRT-LLM 三家共同的默认后端。竞争最激烈的两个项目，在基础组件上选择了共享——因为这块的收益属于整个生态，不值得内耗。（顺带：SGLang 在 XGrammar 之上还有一层自适应容错调度，结构化输出 benchmark 上仍保持领先。）

## 6. 基准测试的罗生门

"到底谁快"是所有讨论的起点，也是最容易误导的部分。我找到的三份测试，结论互相打架，放在一起看才完整：

**测试 A（流传最广）**：H100、Llama 3.1 8B 混合负载，SGLang ~16,200 tok/s vs vLLM ~12,500 tok/s，**SGLang 领先 29%**。这是 2026 年网上引用最多的数字，也是"SGLang 更快"印象的主要来源。

**测试 B（反例）**：vLLM 仓库 issue #37730，Qwen2.5-0.5B、单张 L4、150 并发：vLLM 363 req/s，SGLang 150 req/s——**vLLM 反超 2.4 倍**。原因很具体：高并发下 SGLang 的 Python 路由层卡在 GIL 上（只用上约 1.3 核），vLLM 的 C++ 扩展吃满 2.5 核。这个测试之后 SGLang 加速了 Rust 化——负面 benchmark 是开源项目最好的体检。

**测试 C（精细对照）**：2×H100、DeepSeek-R1-Distill-8B、2025 年 12 月：

| 指标 | 胜者 | 数字 |
|---|---|---|
| TTFT @ c=1 | SGLang | 583ms vs 2,141ms（3.7 倍） |
| 峰值吞吐 | vLLM | 5,129 vs 4,638 tok/s（高 11%） |
| 缓存命中后的 TTFT | SGLang | 恒定 580ms（instant cache） |
| 8K 长上下文 | vLLM | 约 2 倍 |

三份测试合起来的真相是：**没有"谁快"，只有"什么负载下谁快"**。大致的规律：

- 高前缀复用（多轮、RAG、agent）→ SGLang 显著强（基数树 + cache-aware 路由的主场）
- 高并发小模型 → vLLM 的 C++/异步调度更稳
- 长上下文、首次 prompt → vLLM 的 chunked prefill 和长上下文优化更深
- 新架构模型（MLA、稀疏注意力、MTP）→ SGLang 通常先跑通
- 硬件生态（尤其国产/AMD/TPU 兼容）→ vLLM 的插件体系覆盖最广

另外要警惕所有不带完整元数据的基准：模型、量化、上下文长度、并发曲线、SLO 定义、版本号（两个引擎都是两周一个大版本，三个月前的测试基本作废）。我个人的经验法则：**看到"快 30%"的结论，先查它用的是几个月前的版本**。

## 7. 各自的 2026：忙着不同的事

2026 年年中的两个项目，用一个不严谨但传神的说法：**vLLM 在造平台，SGLang 在压延迟**。

**vLLM 的 2026 关键词是"往外长"**。Semantic Router（v0.1 Iris → v0.3 Themis）把推理引擎升级成了"多模型路由系统"——信号-决策插件架构、语义缓存、MoM（Mixture-of-Models）路由，一个入口后面挂多个模型自动分发；vLLM-Omni 把多模态（TTS、视频生成、扩散模型）都收进来；vime 做 RL 框架、AFD 插件做注意力/FFN 分离服务、TileRT 做延迟敏感型专用 decode。性能数字上也有硬货：Qwen3.5 上做到 25K TPS/GPU、Kimi K3/GLM-5.2/Qwen3.8-2.4T 的 day-0 支持。而 v0.20 的 Model Runner V2 在做最后一次核心模块化，官方口径是"离 1.0 只差一两步"——这个从 0.1 至今没到过 1.0 的项目，正在给自己补办成人礼。

**SGLang 的 2026 关键词是"往深长"**。v0.5.17/v0.5.18（一个版本 582-710 个 PR、200 左右贡献者，节奏是 vLLM 的两倍）在干几件很"底层"的事：session-aware cache 让 agent 会话能影响缓存驱逐决策（缓存认识到了"应用还关不关心这段状态"）；weight daemon 让模型权重活得比引擎进程久（崩溃恢复从分钟级到亚秒级）；checkpoint 分阶段加载和 CUDA graph 捕获重叠（启动快 2.4 倍）；Rust 前端逐步替换 Python 的 HTTP/分词路径。它 2026 Q1 的 roadmap 写得非常工程化：overlap scheduler 默认开、prefill CUDA graph 默认开、Mem Cache V2 重构、PP/EP/CP 全部重构、RL 集成的训练-推理一致性……

两家 roadmap 放一起看还有个彩蛋：**对方最擅长的东西都在自己的计划里**。vLLM 在补 cache-aware 能力和 agent 支持，SGLang 在补通用性和硬件广度。竞争没有让它们分道扬镳，反而像两块相向生长的大陆。

## 8. 未来展望：趋同、分叉与商业化

往后看两三年，我觉得有三条线值得盯：

**其一，功能趋同，但"出身"留下的性格差异会长期存在。**前缀缓存、投机解码、PD 分离、多模态——功能清单正在拉平（连 XGrammar 都是共享的）。但设计出身决定肌肉记忆：vLLM 遇到新需求的第一反应是"怎么让默认行为更稳"（零配置哲学），SGLang 的第一反应是"怎么让峰值更高"（benchmark 哲学）。生产选型和竞技选型会长期存在，正如 GCC 和 LLVM。

**其二，agent 会重塑引擎的形态，这是比吞吐更大的变量。**两个引擎 2026 年的发力方向高度一致地指向 agent：vLLM 说"KV 可以放在哪"要变成基础设施契约，SGLang 说"应用还活着吗"要参与调度决策。翻译过来：**推理引擎正在长出状态和会话的概念**——从无状态的 token 泵（请求进来、token 出去、一切归零）变成有记忆、有生命周期、感知应用语义的运行时。SGLang 0.5.17 那个"什么可以活得比什么久"的提法，我认为会是这个转变里被反复引用的表述。RL 基建（上一节、也是上一篇第 11 节的话题）是同一件事的另一面：训练和推理的边界在消失，引擎必须两头都懂。

**其三，商业化会考验开源初心，这是最大的不确定项。**Inferact（1.5 亿美元）和 RadixArk 前后脚成立，剧本相同：引擎永远开源，卖托管和企业服务。这个模式在数据库领域被验证过（Databricks/Confluent），但也有前车之鉴——一旦核心团队的商业产品需要差异化，开源社区的功能节奏就可能被微妙地影响。两个项目都靠着基金会/社区结构做了缓冲（vLLM 有 PyTorch 基金会托管，SGLang 有 LMSYS 的学术出身），但 2027 年再看这条时，商业压力大概率会更具体。

最后一个大胆一点的预测：**"vLLM 还是 SGLang"这个问题本身会过时**。当 Semantic Router 和 OME 这类编排层成熟后，路由器在多个引擎后端之间动态选择会成为常态（甚至同一个集群混部）。就像今天没人问"该用 GCC 还是 LLVM"——编译器套件替你决定了。引擎的战争在往下沉，上层在长出新的抽象。

## 9. 实战：2026 年年中怎么选

落地建议，按我自己的使用经验整理（同样，以 2026 年中为时间戳，这行的保质期大概是半年）：

**默认起点用 vLLM**。这不是性能判断，是生态判断：文档最全、踩坑的人最多、你遇到的任何问题大概率有人提过 issue、OpenAI API 兼容性打磨得最好。新团队、新项目、模型是主流架构（Llama/Qwen/Mistral 系）、没有专门的人盯推理——闭眼选 vLLM，出错概率最低。

**以下四种情况切 SGLang**：

1. **负载是 agent/多轮/RAG 重度**——前缀复用是你最大的成本项，基数树 + cache-aware 路由是碾压性优势（想想测试 C 里恒定 580ms 的 TTFT）；
2. **跑最新架构的模型**——MLA、DSA、MTP、混合注意力这些，SGLang 的 day-0 传统 + 与模型厂商的深度合作（DeepSeek/xAI/GLM/Kimi 的优化都是联合做的）通常意味着几周的性能窗口期；
3. **AMD 或 TPU 硬件**——SGLang 是 AMD 生态事实标准（MI300X/MI355X 的优化深度目前领先），TPU 有 SGLang-Jax 原生方案；
4. **结构化输出要求苛刻**——XGrammar + 自适应容错调度的组合，在 JSON/语法约束的吞吐上目前仍是第一梯队。

**几个部署层面的冷知识**：

- 版本比选型更重要：两个引擎都是双周级发版，**升级带来的性能变化经常大于换引擎**。选定了就跟着版本走，别拿半年前的版本做决定；
- SGLang 的高并发 Python 瓶颈（测试 B 的坑）在 Rust server 全面转正前仍要留意——如果你的场景是"小模型 + 极高并发"，要么等 `--rust-server` 稳定，要么留 vLLM 的对照组；
- 两者的核心参数哲学不同：vLLM 追求零配置（默认值即最优），SGLang 的性能档位（overlap scheduler、CUDA graph、HiCache）经常需要显式打开——用 SGLang 值得花一个下午读一遍它的性能调优文档；
- 混部不是异端：生产上 PD 分离 + 两个引擎各管一段（比如 prefill 用一个、decode 用另一个）的架构已经有人跑，Mooncake 这类 KV 传输层让引擎之间的边界变得可拆。

**一条元建议**：别把"用哪个引擎"当成一次性的架构决策。写一层薄的抽象（或者直接用 OpenAI 兼容 API），让后端可以换——这两个项目的相对优劣势在过去三年里翻过好几次面，未来也会。

## 10. 尾声：五篇合奏

专栏写到这里正好五篇，回头看是一条完整的链：**分词**决定信息怎么进来，**注意力**决定计算怎么流动，**量化**决定数字怎么存储，**infra**决定机器怎么协作——而这第五篇讲的，是这一切之上离开发者最近的一层：**把这些优化打包成人人可用的一行命令**。

写这五篇的过程中我反复确认了一件事：学术界的每篇论文（Orca、PagedAttention、RadixAttention、Mooncake……）和工业界的每个版本号（V1、v0.4、v0.5.17……）之间的距离，比论文之间批评的"工程差距"有趣得多。一篇 SOSP 论文定义一个问题，一个 GitHub 项目把它变成 commodity，然后一群公司的生产环境把它逼成基础设施——vLLM 和 SGLang 的三年战争，只是这个循环最近的一次运转。

## 11. 参考资料

- Kwon et al., *Efficient Memory Management for Large Language Model Serving with PagedAttention (vLLM)*, SOSP 2023
- Zheng et al., *SGLang: Efficient Execution of Structured Language Model Programs*, arXiv 2312.07104 / NeurIPS 2024
- vLLM 官方博客：*vLLM V1: A Major Upgrade to vLLM's Core Architecture*（2025-01）；*vLLM 2025 Retrospective & 2026 Roadmap*（Office Hours #38 整理稿）
- vLLM V1 用户指南与 v0.11.0、v0.20.x Release Notes（GitHub Releases）
- LMSYS 官方博客：SGLang v0.4（2024-12）、*Large-Scale EP Inference*（2025-05）、slime（2025-07）、SpecForge（2025-07）、HiCache（2025-09）、Deterministic Inference（2025-09）、SGLang-Jax（2025-10）
- SGLang 官方仓库：*Development Roadmap (2026 Q1)* issue #12780；v0.5.17 / v0.5.18 Release Notes
- Sheng, *Efficient LLM Inference with SGLang*（LLMSys 2025 春季课程讲义）
- Benchmark 三方对照：PremAI/DeployBase 与 Morph LLM 的 H100 对比（2026）；vLLM issue #37730（Radix vs PagedAttention Scaling，2026-03）；srawlin/vllm-vs-sglang-performance-benchmark BENCHMARK_REPORT（2×H100，2025-12）
- Inferact 成立报道：TechCrunch（2026-01-22）；RadixArk 公开信息（2026-05）
- ChatForest 2026 年度评测：vLLM（2026-05-07）与 SGLang（2026-05-07）两篇 Review
