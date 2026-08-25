---
title: 分词与词嵌入全解：从 BPE 到 2026 年的 Tokenizer-Free 时代
date: 2026-08-25
tags: [深度学习, 分词, 词嵌入, 大模型]
album: 深度学习专栏
order: 2
excerpt: 一份系统梳理 Tokenization 与 Embedding 演进史的深度长文：从 word-level 到 BPE/SentencePiece，再到 2026 年的 Dynamic Tokenization、FLEXITOKENS 与 ByteFlow 所代表的 Tokenizer-Free 路线。
---

> 本文是《深度学习专栏》系列第 2 篇。第 1 篇我们梳理了注意力机制从 Bahdanau 到 2026 年稀疏/线性注意力的演进；这一篇我们沿同一个时间轴往前看——在文本进入 Transformer 之前，它到底经历了什么。

---

## 目录

1. 引子：2026 年，分词为什么重新变热
2. 先把三个东西分清楚：Tokenizer、Token ID、Embedding
3. 前史：从 word-level 到 BPE / WordPiece / SentencePiece（2016-2020）
4. 2026 年的"反 Tokenizer"路线：ByteFlow 与 tokenizer-free 语言建模
5. 为什么大家突然重新研究 Tokenization：BPE 的三宗罪
6. 中文：Tokenization 问题的放大器
7. Dynamic Tokenization：让边界随上下文变化
8. Learnable Tokenizer：FLEXITOKENS
9. 更根本的问题：Token 到底应该是什么
10. Embedding 研究还在继续吗
11. 现实工程问题 I：Cross-Tokenizer 蒸馏
12. 现实工程问题 II：Tokenizer 成为推理瓶颈——GPUTOK
13. 2026 年研究地图：五条路线一张图
14. 与注意力机制演进的统一视角
15. 学习建议：2026 年该怎么学 Tokenization
16. 参考资料

---

## 1. 引子：2026 年，分词为什么重新变热

**2026 年，"分词（Tokenization）"反而是一个重新变热的研究方向。**

但有一个非常重要的变化：

> **研究重点已经不是"BPE 怎么再改一点"这么简单，而是在重新追问：LLM 到底还需不需要传统 Tokenizer？**

ICLR 2026 已经出现了直接**取消 Tokenizer**、让模型自己学习字节如何组合的工作（ByteFlow）；ACL 2026 也有专门研究可动态变化 Tokenizer 的论文（MUTANT、FLEXITOKENS）。这不是零星尝试，而是一条清晰的新路线。

一句话总结本文的核心观察：

> **2020 年：研究"怎么把词切成 Token"。**
> **2024 年：研究"怎么把 Token 切得更好"。**
> **2026 年：开始认真研究"为什么一定要有 Token"。**

---

## 2. 先把三个东西分清楚：Tokenizer、Token ID、Embedding

很多人说的"分词和词嵌入"，其实是流水线上三个不同的层次：

```text
原始文本
   ↓
Tokenizer
   ↓
Token ID
   ↓
Embedding
   ↓
向量
   ↓
Transformer
```

以一句中文为例：

> 我喜欢人工智能

可能被 tokenizer 切成：

```text
我 / 喜欢 / 人工 / 智能
```

然后每个片段映射到词表中的编号：

```text
我     → ID 1532
喜欢   → ID 9281
人工   → ID 17421
智能   → ID 3298
```

再通过 Embedding 表查到向量：

```text
1532  → [0.12, -0.43, 0.87, ...]
9281  → [0.51,  0.21, 0.03, ...]
...
```

所以两者的分工是：

- **Tokenization** 解决：*"文本应该怎么切？"*
- **Embedding** 解决：*"这个 Token 应该用什么向量表示？"*

而 2026 年真正有意思的问题是：

> **为什么一定要先固定切好，再查一个固定 Embedding Table？**

这正是当前大量研究在挑战的东西。

---

## 3. 前史：从 word-level 到 BPE / WordPiece / SentencePiece（2016-2020）

要看懂 2026 年的"反叛"，得先知道它反叛的是什么。

### word-level 的困境

最朴素的做法是把"词"当 token。但词表会爆炸：英文几十万词，中文组合无穷，而且总有没见过的词（OOV，Out-of-Vocabulary）。训练时没见过的词只能全部映射成 `<UNK>`，信息直接丢失。

### character-level 的另一极

把每个字符当 token，OOV 问题消失了，但序列变得极长——同样一句话，字符数远多于词数，注意力是 O(N²) 的，序列变长意味着计算成本平方级上升；且单个字符承载的语义太稀薄，模型要花很多层才能把字符组合成有意义的单元。

### Subword：两条路线的折中

现代分词算法都落在"子词"（subword）这个中间粒度上：

- **BPE（Byte Pair Encoding，2016 被引入 NLP）**：从字符开始，迭代地合并语料中最频繁共现的相邻对，直到词表达到目标大小。高频词保持完整，低频词被拆成子词。GPT 系列的 tokenizer 以它为基础。
- **WordPiece（2012/2016）**：Google 用于 BERT，思路与 BPE 相近，但合并准则不是"最频繁"，而是"能让语言模型似然提升最大"的组合。
- **Unigram Language Model（2018）**：反过来，先假设一个大词表，用 EM 算法估计每个子词的概率，再逐步裁掉对似然伤害最小的子词。
- **SentencePiece（2018）**：把上述算法工程化，直接在原始文本上工作（含空格特殊编码），语言无关，成为多语言模型（T5、LLaMA 等）的标配。

这一代方案共同确立了今天 LLM 的默认范式：**先离线训练一个固定 tokenizer，再训练模型，之后永不改变**。

2026 年的新研究，攻击的正是这个"固定"。

---

## 4. 2026 年的"反 Tokenizer"路线：ByteFlow 与 tokenizer-free 语言建模

这是目前最值得关注的路线。

传统 LLM：

```text
文本
 ↓
BPE / SentencePiece（固定、离线训练）
 ↓
Token
 ↓
Embedding
 ↓
Transformer
```

新的路线开始尝试：

```text
UTF-8 bytes
 ↓
模型自己学习如何组合
 ↓
动态 representation
 ↓
Transformer
```

甚至：

```text
文本 → Byte → Transformer
```

**完全没有传统 tokenizer。**

ICLR 2026 的 **ByteFlow** 就是典型代表。它提出 ByteFlow Net，让模型直接从原始 byte stream 中学习 segmentation，而不是提前由固定 tokenizer 决定 token 边界。论文明确把目标定义为 **tokenizer-free language modeling**。

对 byte-level 路线，OOV 概念彻底消失（任何文本都是字节），代价是序列更长——这就与第 1 篇讲的注意力效率研究（线性注意力、稀疏注意力）形成了直接呼应：**注意力变便宜了，细粒度表示才变得可负担**。两条研究线在这里汇合。

---

## 5. 为什么大家突然重新研究 Tokenization：BPE 的三宗罪

### 罪一：Token 是人为固定的

假设 vocabulary 是 50,000 tokens，训练完 tokenizer 后：

```text
"internationalization"
→ international / ization
```

但另一种语言可能被切成：

```text
in / ter / na / tion / al / ization
```

这意味着：

> **同样的信息量，不同语言可能需要完全不同数量的 token。**

这直接影响：

- context length（同样窗口装的内容更少）
- 推理成本（token 多，计算多）
- KV Cache 占用
- attention 计算量
- 多语言能力与长文本能力

ACL 2026 的 **MUTANT** 专门研究多语言 tokenizer 设计，指出 tokenizer 的设计会直接影响 LLM 的性能、训练效率和 inference cost。

### 罪二：切分依赖统计，而非语义/结构

BPE 的合并顺序由语料频率决定。它不知道"中华人民共和国"是一个政治实体，也不知道"光伏电池片"在光伏行业是一个整体概念。它只是在数共现频率。

### 罪三：一次训练，终身使用

Tokenizer 在模型训练前就冻结了。领域迁移（医疗、法律、代码）、语言演化（新词）、词表更新（vocabulary expansion）都变成麻烦的后续工程问题。

---

## 6. 中文：Tokenization 问题的放大器

中文天然把这些问题放大。例如：

```text
中华人民共和国
```

到底应该切成：

```text
中 / 华 / 人 / 民 / 共 / 和 / 国
```

还是：

```text
中华 / 人民 / 共和国
```

还是：

```text
中华人民共和国（一个 token）
```

？

传统 tokenizer 只能根据统计做决定。但统计上最优的切法，并不一定是最适合 Transformer 的 segmentation。这正是研究者开始思考的：

> **Token boundary 是否应该由模型根据上下文动态决定？**

顺带一提，中文的 token efficiency 问题（同样内容比英文消耗更多 token）也直接源于此——这也是国内模型厂商（DeepSeek、GLM、Qwen 等）近年持续优化中文词表压缩率的现实动机。

---

## 7. Dynamic Tokenization：让边界随上下文变化

这是 2026 年的一个重要方向。

传统：

```text
Tokenizer → 固定 → 永远这样切
```

新方法：

```text
Input
 ↓
模型观察上下文
 ↓
动态决定 token boundary
 ↓
生成当前输入最合适的切分
```

例如通用语境下：

```text
今天 / 天气 / 很 / 好
```

但在某个专业领域：

```text
光伏电池片
```

可能动态变成：

```text
光伏 / 电池片
```

甚至整体作为一个 token。

2025 年 ACL 已有工作（Retrofitting LLMs with Dynamic Tokenization）尝试给已有 LLM 加上 dynamic tokenization，在多语言场景下平均减少超过 20% 的 token sequence length，同时性能下降很小。**省 20% 的 token，就是省 20% 的推理成本和 20% 的有效上下文。**

---

## 8. Learnable Tokenizer：FLEXITOKENS

ACL 2026 的 **FLEXITOKENS**（Flexible Tokenization for Evolving Language Models）代表了"Tokenizer 自己学习"的方向。

它不是人工设计 tokenizer，而是：

```text
Byte
 ↓
Learnable Tokenizer
 ↓
模型学习 token boundary
 ↓
Variable-length segments
```

也就是说：

> **Token 不再是固定词表里的东西，而可以成为模型学习出来的东西。**

论文在多语言、形态复杂语言和不同领域上做了实验，报告了相对 BPE 等 baseline 的明显提升。它同时回应了第 5 节的"三宗罪"：边界可学习、可适应演化中的语言、天然适配多语言。

---

## 9. 更根本的问题：Token 到底应该是什么

2026 年 8 月的论文 *What Tokens are Learned when Tokenization is Optimized Jointly with Language Modeling?* 直接研究：

> 如果 Tokenization 和 Language Modeling 一起联合优化，模型最终会自己学出什么样的 token？

他们在 18 种语言上比较了不同的 tokenizer-free / jointly optimized 方法，发现模型学出来的 token 与传统 BPE vocabulary 可以非常不同。

这暗示了一个更深的结论：

> **我们现在使用的"token"，很可能只是历史工程选择，并不是语言建模最优的基本单位。**

---

## 10. Embedding 研究还在继续吗

当然在继续，而且要稍微区分一下。

传统路径：

```text
Token ID → Embedding Lookup → Vector
```

本质上就是：

```python
embedding = Embedding[token_id]
```

这是一个巨大矩阵：V × D。例如 V = 150,000、D = 4096 时参数量约 6.14 亿。**vocabulary 越大，embedding 参数量越大**——这也解释了为什么词表大小是个需要精打细算的工程决策。

当前 embedding 方向的研究关键词包括：

- byte-level / character embedding
- dynamic embedding
- contextual embedding
- compositional embedding（向量组合表示新词）
- factorized embedding（矩阵分解降参数）
- vocabulary expansion / replacement（词表更新）
- multilingual embedding
- cross-tokenizer embedding
- embedding transfer

值得注意的是：如果 tokenizer-free 路线胜出，"Embedding Table 查表"这个操作本身也会被改写——字节序列的表示将来自模型内部的动态计算，而非静态查表。

---

## 11. 现实工程问题 I：Cross-Tokenizer 蒸馏

一个非常现实的问题：不同模型的 Tokenizer 不一样。

```text
Model A：Tokenizer A / Vocabulary A / Embedding A
Model B：Tokenizer B / Vocabulary B / Embedding B
```

如果想把 A 模型的知识蒸馏给 B，就会遇到麻烦：

```text
A: "人工智能" → [1234, 5678]
B: "人工智能" → [8932, 112, 745]
```

Token 序列完全对不上，logit-level 蒸馏直接失效。

ACL 2026 出现了 **Cross-Tokenizer LLM Distillation through a Byte-Level Interface**，尝试用 byte-level 作为两个模型之间的共同接口，解决不同 tokenizer 间的知识蒸馏。论文也明确指出 cross-tokenizer distillation 仍是开放问题——这正是"各家 tokenizer 不统一"这一历史遗产造成的系统性摩擦。

---

## 12. 现实工程问题 II：Tokenizer 成为推理瓶颈——GPUTOK

你可能会觉得：tokenizer 不就是 CPU 上切字符串吗？以前确实影响不大。

但现在 1M、2M 甚至 10M context 越来越常见，GPU 全速运转的同时，CPU tokenizer 可能成为 pipeline 的短板：

```text
GPU：    ████████████████████████  很快
CPU tokenizer： ████                    拖后腿
```

2026 年的 **GPUTOK** 研究直接把 BPE tokenizer GPU 化，在超长输入上相比部分 CPU tokenizer 实现获得明显加速。这提示我们：tokenization 不只是"建模前的预处理"，它本身就是推理基础设施的一部分。

---

## 13. 2026 年研究地图：五条路线一张图

把 2026 年的 Tokenization 研究记成这张图：

```text
                         Tokenization
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
       改进 BPE            Dynamic Token       Tokenizer-Free
          │                   │                   │
   更好的词表             动态切分             Byte-level
   多语言 tokenizer        动态长度             Learned boundary
   Domain tokenizer        Context-aware        ByteFlow
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
                    Cross-Tokenizer
                              │
                    Byte-level interface
                              │
                         Embedding
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        Byte Embedding   Dynamic Embedding   Compositional
```

五条主路线：**改进 BPE / Dynamic Tokenization / Tokenizer-Free / Cross-Tokenizer 接口 / 新一代 Embedding**。

---

## 14. 与注意力机制演进的统一视角

本专栏第 1 篇讲 Attention 的演进，这一篇讲 Tokenization。它们不是孤立的话题，而是同一个问题的两面：

```text
输入表示 → Tokenization → Embedding
                      ↓
          ┌─────────────────┐
          │ Transformer     │
          │  Attention/FFN/ │
          │  MoE ...        │
          └─────────────────┘
                      ↓
                  Output
```

2026 年的研究实际上在同时攻击这条 pipeline 的不同位置：

```text
Tokenizer
   为什么固定？        → Dynamic / Token-free

Attention
   为什么 O(N²)？      → Sparse / Linear / Hybrid

FFN
   为什么每个 token 都算？ → MoE / Conditional Compute

Embedding
   为什么必须固定查表？  → Compositional / Contextual

Inference
   为什么每步重算？      → KV Cache / Speculative Decoding
```

所以如果现在系统学 2026 年的大模型底层原理，不要把 **Tokenizer → Embedding → Attention** 当成三个孤立知识点，而应理解成一个更大的问题：

> **"一个 Transformer 到底应该用什么粒度来表示信息，以及应该在什么粒度上进行计算？"**

注意力效率的进步（第 1 篇）使得更细的表示粒度（本篇）变得可负担；表示粒度的研究又反过来改变注意力的输入分布。两者互相成就。

而且从 2026 年的论文趋势看，**"tokenization 是不是 LLM 必须存在的一层"这个问题，目前远没有定论**。

---

## 15. 学习建议：2026 年该怎么学 Tokenization

**必须学，但学习重点已经变了。**

不要把时间花在"BPE 算法背下来就完事"。应该建立完整的表示链路直觉：

```text
文本 → Unicode/UTF-8 → Byte → 字符 → 词 → Subword → Token
    → Embedding → Contextual Representation → Attention
```

然后真正理解这些问题：

- 为什么我们需要 Token？
- 为什么 Token 粒度会影响模型？
- 为什么 token 数量会影响计算成本？
- 为什么中文、英文、代码会出现不同的 token efficiency？
- 为什么 tokenizer 会影响模型能力？
- 如果取消 tokenizer，Transformer 会发生什么？

这些才是 2026 年更有价值的问题。

---

## 16. 参考资料

1. [ByteFlow: Language Modeling through Adaptive Byte Compression without a Tokenizer — ICLR 2026](https://proceedings.iclr.cc/paper_files/paper/2026/hash/eaf5d2cdb582c058a078d4fdf52a20f9-Abstract-Conference.html)
2. [MUTANT: A Recipe for Multilingual Tokenizer Design — ACL 2026](https://aclanthology.org/2026.acl-long.2146/)
3. [Retrofitting Large Language Models with Dynamic Tokenization — ACL 2025](https://aclanthology.org/2025.acl-long.1444/)
4. [FLEXITOKENS: Flexible Tokenization for Evolving Language Models — Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.848/)
5. [What Tokens are Learned when Tokenization is Optimized Jointly with Language Modeling? — arXiv 2608.17325](https://arxiv.org/abs/2608.17325)
6. [Cross-Tokenizer LLM Distillation through a Byte-Level Interface — ACL 2026 Workshop](https://aclanthology.org/2026.customnlp4u-1.9/)
7. [GPUTOK: GPU Accelerated Byte Level BPE Tokenization — arXiv 2603.02597](https://arxiv.org/abs/2603.02597)
8. 本专栏第 1 篇：《注意力机制全解：从 Bahdanau Attention 到 2026 年的稀疏与线性注意力》
