---
title: 分词与词嵌入：从 BPE 的胜利到"取消 Tokenizer"的浪潮
date: 2026-08-25
tags: [深度学习, 分词, 词嵌入, 大模型]
album: 深度学习专栏
order: 2
excerpt: Tokenization 曾被视为流水线里"最好的必要之恶"。本文梳理 subword 分词如何成为默认范式、它积累了哪些债，以及 ByT5、BLT、FLEXITOKENS、ByteFlow 这条"取消 Tokenizer"的路线如何一步步把边界决策收回模型内部。
---

这是《深度学习专栏》的第二篇。第一篇讲注意力机制从 Bahdanau 走到稀疏与线性注意力的十年；这一篇讲的是流水线上更靠前、也更少被严肃对待的一段——文本在进入 Transformer 之前发生了什么。

我之所以想写这个题目，是因为 2026 年的情况有点反直觉：分词这个看起来早已定型、教科书里一页带过的东西，重新变成了活跃的研究方向。而且这轮研究的主流不是"BPE 再改一点"，而是一个更根本的追问：**LLM 到底还需不需要一个独立的 Tokenizer？**

## 一、先说清楚三个东西的分工

讨论这个问题的人经常把几个概念混在一起，先剥开。

Tokenizer 决定"文本怎么切"。它把 `我喜欢人工智能` 切成若干片段，每个片段映射到词表里的一个整数编号。Embedding 决定"切出来的单元用什么向量表示"。编号 `1532` 去查一张 V×D 的大表，得到一个 4096 维的向量，交给 Transformer。

这张表有多大？一个 15 万词表、4096 维隐层的模型，光 embedding 就有约 6.1 亿参数——和一个小模型整个的体量相当。所以"词表多大"从来不是随手定的工程参数，它直接决定了模型的参数分布。

真正值得琢磨的是这套流水线隐含的一个假设：**切分在训练之前完成、由一个独立于模型的算法决定、且一经训练永不改变。**2026 年这波研究，攻击的正是这个假设。

## 二、Subword 是怎么赢的

按词切分是最直觉的方案，但词表会爆炸，而且永远有没见过的词，只能全部塌缩成 `<UNK>`，信息直接丢失。按字符切分则走向另一个极端：序列长度暴涨，而注意力是 O(N²) 的；单个字符承载的语义又太稀薄，模型要花很多层才能把字符重新组合成语义单元。

Subword 是两者的折中，逻辑相当优雅：高频词保持完整，低频词拆成可复用的子词片段。`doghouse` 即使没见过，也能拆成 `dog` + `house`，OOV 问题被消解掉了。

这一代算法有三个代表。BPE 原本是 1994 年的数据压缩算法，Sennrich 等人 2016 年把它引入神经机器翻译：从字符序列出发，反复合并语料中共现频率最高的相邻对，直到词表达到目标大小。WordPiece 走的是另一条准则——它选择让语言模型似然提升最大的合并，而不是最频繁的合并，这是 Google 在 GNMT/BERT 一系里的选择。SentencePiece 则是工程化集大成者：直接在原始文本上工作、语言无关、把空格编码进符号本身，成为 T5、LLaMA 这些多语言模型的标配。

公平地说，subword 分词是深度学习时代最成功的"基础设施级"设计之一——简单、稳定、可复用。它的问题不在当下，而在于它把一组基于训练语料统计的贪心决策**冻结**进了模型，然后让所有下游为此买单。

## 三、这笔债积累在哪

Karpathy 有个流传很广的说法：tokenization 充其量是"必要之恶"（at best a necessary evil），与真正的语言建模关系不大。SpaceByte 那篇论文的动机部分专门引了他的推文和演讲。这句话在 2020 年前后是共识，但最近两年，"恶"的部分越来越难忽视了。

**第一笔债是多语言不公平。**分词器的合并规则由语料频率决定，而语料天然偏向英文。Ahia 等人在 EMNLP 2023 那篇《Do All Languages Cost the Same?》里给过一组很有冲击力的数字：同一句话，GPT-4o 的 tokenizer 切英文是 29 个 token，切日文是 53 个，切旁遮普文是 254 个。接近九倍的差距，直接换算成 API 账单、上下文窗口占用和推理延迟——而对非拉丁文字，同样的信息量往往需要最多四倍的 UTF-8 字节来表示，处境是双重的。MAGNET（NeurIPS 2024）整篇论文处理的正是这种"过度切分"（over-segmentation）。

**第二笔债是脆弱性。**一个拼写变体、一个大小写变化、一个生僻字符，就可能让整段文本的 token 序列面目全非。ByT5 的实验早就表明字节级模型对噪声鲁棒得多，在拼写和发音敏感的任务上优势明显。另一个常被引用的例子是数字：tokenizer 对数字的切法（逐位切还是成块切）会显著影响算术能力——这是字面意义上的"表示方式决定能力上限"。

**第三笔债我原以为是小事，直到看到系统测量的数据。**大家总觉得 tokenizer 不就是 CPU 上切个字符串么。TokTier（2026 年 7 月）对两个 agent 生态里 15 万余次调用做了统计：编码 agent 的会话模式是"长历史 + 小增量"，中位每次追加约 1.4K 字符；当 prompt 缓存命中率逼近 0.99 时，**tokenization 占首 token 延迟（TTFT）的比例从 10% 涨到了 64%**。GPU 全速运转，CPU 在切词——这在长上下文时代成了真实的系统瓶颈。

## 四、字节级的反攻

要取消 tokenizer，最彻底的做法是直接对 UTF-8 字节建模：词表缩到 256，OOV 的概念从此不存在。ByT5（2021）证明了这条路可行，也暴露了代价——字节序列大约是 token 序列的四倍长，朴素的字节级 Transformer 要多付出一个量级左右的训练 FLOPs 才能追平 subword 模型。SpaceByte 后来把这笔账算得更清楚，并给出了一个朴素但有效的架构改进：在字节流里，只在空格这类天然边界之后插入更大的 Transformer 块，让计算分配跟着边界走，性能就能大致追平 tokenized 模型。

真正的转折点是 Meta FAIR 2024 年 12 月的 Byte Latent Transformer（BLT）。我认为这是这条线上最重要的一篇工作，值得讲细一点。

BLT 的核心观察是：tokenized 模型对每个 token 花等量的计算，但预测难度并不均匀——一个常见词的后缀几乎是白送的，而新句子的第一个词才值得动用大模型。既然如此，边界不应该由统计频率决定，而应该由**信息量**决定。BLT 先单独训一个约一亿参数的小字节模型，用它的下一字节预测熵来划边界：熵超阈值就开一个新 patch。熵模型是个 14 层、滑窗 512 字节的小 Transformer，阈值取 1.09 时平均 patch 约 4.4 字节。可预测的长尾被合并成长 patch 轻量处理，不可预测的位置切成细 patch 交给大模型——计算跟着不确定性走。

架构上它是三段式：轻量局部编码器把字节聚合成 patch 表示，一个深且宽的全局 latent Transformer 承担几乎所有 FLOPs，再由轻量局部解码器还原回字节。编码器里还加了 hash n-gram embedding 来增强对噪声的鲁棒性。BLT 做了字节级模型第一个 FLOP 受控的扩展性研究，规模到 80 亿参数、4 万亿训练字节，结论是在固定推理开销下，字节级的 scaling 曲线比 tokenization 模型更好看——匹配 Llama 3 性能的同时推理 FLOPs 最多省一半。顺带一提，2026 年的后续工作（Fast BLT）用块式离散扩散替换逐字节自回归解码，把推理显存带宽又降了 87%–92%。这条路还在继续变便宜。

BLT 之后，动态边界成了字节级架构的标配，但边界怎么学，各家给出了不同的答案。ByteFlow（2026 年 3 月，Rice 与 Amazon Science）的切入点我认为最见功力：它用潜在表示的**编码率**（coding rate）驱动切分——把分割问题转化成一个有损压缩决策，信息密度高的位置获得更高的编码率、被送入全局计算。工程上尤其聪明的一点是它用 Top-K 选择保持了静态计算图：边界是自适应的，但图的形状是固定的，这对 GPU 映射和内核优化是决定性的友好。

## 五、不推翻重来，让旧模型学会动态切分

上面这条线要求从零预训练，门槛太高，所以还有一条更务实路线：保留 subword tokenizer 和已训练的模型，把切分决策改成动态的。

Cambridge 的 Feher、Vulić 和 Minixhofer 做的 retrofitting（ACL 2025）很有代表性。他们的做法是在 batch 级别跑一个受 BPE 启发的合并算法——在同一批输入里统计子词序列的频率，合并频繁片段，然后用一个预训练的超网络（hypernetwork）**现算**合并后新 token 的 embedding。这个设计一石二鸟：encoder 模型（XLM-R）在 14 种语言上平均缩短 token 序列 20% 以上而性能损失不到 2%；应用到 Mistral-7B 的 prefill 时序列最多缩短 40%。更妙的是，超网络意味着模型不再依赖固定词表查表——词表事实上变成无界的，这悄悄改写了"embedding 必须是一张静态表"的默认设定。

往预训练里做的人则要处理另一个问题：怎么让边界预测器可微且可控。MAGNET 用 Gumbel 技巧把离散边界松弛成可训练的，再用一个二项先验把压缩率锚在目标附近——每个文字系统配一个专属的边界预测器。FLEXITOKENS（俄亥俄州立与华盛顿大学）指出了这里的新的僵化：锚定固定压缩率，等于把"BPE 的刚性"换成了"压缩率的刚性"——医学文本和土耳其语这种形态丰富的语言需要更细的切分，代码和中文反而适合更粗的合并，一个全局定死的压缩率两头不讨好。他们的修法很简洁：把固定压缩率放松成一个区间，损失函数只在越界时惩罚（hinge 形式）。就这么一个改动，过度切分显著减少，多个基准上相对 BPE 和其他梯度化分词器拿到最多 10 个百分点的提升。

## 六、Tokenizer 不统一造成的系统性摩擦

还有一个不那么显眼但影响深远的问题：**世界上没有两个模型的 tokenizer 是一样的。**

标准知识蒸馏假设师生共享 tokenizer，因为 logit 级蒸馏需要两个输出空间逐维对齐。词表一变，teacher 的 5 万维分布对上 student 的 3 万维分布，直接失效。这在实践中捆住了很多手脚——想把一个通用大模型的知识蒸给一个领域专用 tokenizer 的小模型，理论上顺理成章，工程上无从下手。

解法正在收敛到"字节层做公共接口"。MediaTek Research 的 BLD（2026 年 4 月）思路干净：把 teacher 的输出分布转换成字节级概率，给 student 外挂一个轻量字节解码头，蒸馏在这个共享接口上进行，1B 到 8B 的任务上都打得过复杂得多的启发式方法。更早的 ALM（Cambridge）则把"tokenizer 迁移"本身看作自蒸馏问题，能做到把 subword 模型快速迁到字节层。2026 年 2 月还有一篇工作反着走：把 Llama、Qwen、OLMo 这些 token-trained 模型蒸成字节级模型，两阶段课程（先做表示对齐和联合蒸馏，再做字节级 SFT），只花约 1250 亿字节就保留了 teacher 九成以上的能力。这些工作共同说明：字节层正在成为跨 tokenizer 世界的"通用语"。

## 七、系统侧的觉醒

最后说回工程。GPUTOK（2026 年 3 月）把 byte-level BPE 搬上 GPU：合并表放进 `cuCollections static_map`，合并循环写成 CUDA kernel，pair 打包成 64 位键做 GPU 侧查表。在 WikiText103 的 131k token 长序列上，比 tiktoken 快 1.7 倍，比 HuggingFace 的 GPT-2 tokenizer 快 7.6 倍。这篇论文有个很诚实的 profiling 细节：CUDA API 时间的 70%–80% 花在内存分配上——瓶颈不在算法在访存，这种结论只有真做过系统的人才会写出来。

TokTier 走得更远，做成了有状态的分词服务：保存会话的历史 token 序列，增量重切追加部分附近的一个窗口，只有通过精确性校验（保证与全量重切结果逐 ID 一致）才拼接。为"切词"这个操作单独设计一套带契约的服务，放在五年前很难想象。

## 八、回到那个大问题

把这篇和上一篇放在一起看，会发现一个共同的模式。注意力那边的问题是"为什么每个 token 对所有 token 都算 O(N²) 的注意力"，答案是稀疏化、线性化、层次化；分词这边的问题是"为什么边界是预先固定的、计算是均匀分配的"，答案是熵驱动 patch、编码率驱动压缩、区间化的 hinge 损失。**两条线其实在回答同一个问题：一个 Transformer 应该用什么粒度表示信息，又该在什么粒度上分配计算。**

它们还互相成就。BLT 能成立，部分前提是滑动窗口注意力和高效 token mixing 让长字节序列可负担；反过来，字节级模型又把"表示粒度"从超参数变成了可学习量。注意力变便宜了，细粒度才用得起；细粒度学出来了，计算的分配才有了依据。

我个人的判断是，"tokenizer 是否应该作为独立组件存在"这个问题，答案的天平正在向"否"倾斜，但速度会慢于 enthusiasts 的预期——subword 分词是如此成熟、如此嵌入现有基础设施，BLT 这类架构要真正进入主流生产栈，还需要解决推理生态（KV cache 的 patch 化、serving 框架的适配）等一大堆脏活。短期内更可能的现实是分层共存：存量模型靠 retrofitting 和字节级接口续命，新架构从字节层重新出发。

如果读者想顺着这条线读文献，我的建议是这个顺序：ByT5 看动机，SpaceByte 看账怎么算，BLT 看架构思想的完整形态，MAGNET 和 FLEXITOKENS 看边界学习的技术演进，Retrofitting 看务实路线，ByteFlow 看最新的信息论视角。读完之后再回头看 BPE 的原始论文，会有一种"原来起点是这么朴素的一个贪心算法"的恍然。

**Token 从来不是语言建模的第一性单位——它只是我们暂时买得起的一个近似。**这句话，大概就是 2026 年这个方向所有论文共同的注脚。

## 参考文献

1. Sennrich et al. *Neural Machine Translation of Rare Words with Subword Units*. ACL 2016.
2. Kudo & Richardson. *SentencePiece: A Simple and Language Independent Subword Tokenizer and Detokenizer for Neural Text Processing*. EMNLP 2018.
3. Xue et al. *ByT5: Towards a Token-Free Future with Pre-trained Byte-to-Byte Models*. TACL 2021.
4. Ahia et al. *Do All Languages Cost the Same? Tokenization in the Era of Commercial Language Models*. EMNLP 2023.
5. Slagle. *SpaceByte: Towards Deleting Tokenization from Large Language Modeling*. arXiv:2404.14408.
6. Pagnoni et al. *Byte Latent Transformer: Patches Scale Better Than Tokens*. arXiv:2412.09871, ACL 2025.
7. Ahia et al. *MAGNET: Improving the Multilingual Fairness of Language Models with Adaptive Gradient-Based Tokenization*. NeurIPS 2024.
8. Feher, Vulić & Minixhofer. *Retrofitting Large Language Models with Dynamic Tokenization*. ACL 2025, arXiv:2411.18553.
9. Owodunni, Ahia & Kumar. *FLEXITOKENS: Flexible Tokenization for Evolving Language Models*. arXiv:2507.12720.
10. Deng et al. *ByteFlow: Language Modeling through Adaptive Byte Compression without a Tokenizer*. arXiv:2603.03583.
11. Kadamba & Jaisankar. *GPUTOK: GPU Accelerated Byte Level BPE Tokenization*. arXiv:2603.02597.
12. Zhang & Cao. *TokTier: Exact Stateful Tokenization for Agentic LLM Serving*. arXiv:2607.29678.
13. Singh et al. *Cross-Tokenizer LLM Distillation through a Byte-Level Interface*. arXiv:2604.07466.
14. Minixhofer, Vulić & Ponti. *Universal Cross-Tokenizer Distillation via Approximate Likelihood Matching*. arXiv:2503.20083.
15. Bao et al. *Distilling Token-Trained Models into Byte-Level Models*. arXiv:2602.01007.
