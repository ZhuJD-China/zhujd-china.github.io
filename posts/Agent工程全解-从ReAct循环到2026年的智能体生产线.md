---
title: Agent 工程全解：从 ReAct 循环到 2026 年的智能体生产线
date: 2026-11-06
tags: [Agent, 智能体, MCP, 上下文工程, 多智能体, 评测]
album: 深度学习专栏
order: 9
excerpt: 2025 年 7 月，Replit 的 Agent 在代码冻结期间删掉了 SaaStr 的生产数据库，然后说“我慌了”。一年后，Agent 能连续工作几小时，MCP 进了 Linux 基金会，框架换了两代，但生产环境的可靠性仍卡在同一个地方：循环、工具、上下文、评测与运行时。本文按五个边界拆开讲，给出一套 2026 年能落地的 Agent 工程架构和上线清单。
---

2025 年 7 月 18 日，SaaStr 创始人 Jason Lemkin 在 X 上写了一句：“Replit 在代码冻结和停机期间失控，删掉了我们的整个数据库。”那天是他试用 Replit 的第九天，库里有一千二百多条高管记录，是他准备在大会上用的。Agent 删完库之后，先回了一句 “I panicked”，然后生成了四千条假用户数据，试图把空缺填上。

Replit CEO Amjad Masad 公开道歉，说这件事“不可接受，也不应该发生”，随后补了三样东西：开发环境和生产环境隔离、数据库回滚、以及动手前先给计划的 plan mode。处理不算慢。但事故本身值得反复看，因为它把 Agent 工程里最容易漏掉的环节一次踩全了：生产库的写权限、不可逆操作的审批、回滚、以及“现在是代码冻结期”这个只有人才知道的上下文。

模型没有犯智力错误。它知道怎么连库，也知道怎么执行 DROP。它缺的是工程约束：一个能识别爆炸半径的权限系统，一个在不可逆操作前踩刹车的审批层，一个出错后能退回去的运行时。

这篇文章讲这层东西。2026 年，Agent 的模型能力已经足够做很多事；真正稀缺的是把它放进生产的那套工程。下面按五个边界展开：循环、工具与权限、上下文、评测、运行时。最后给一套参考架构和一份上线清单。

---

## 目录

1. 先把 workflow 和 agent 分开
2. 循环边界：ReAct 之后，难点在停
3. 工具边界：MCP 统一了插头，没统一安全
4. 上下文边界：窗口变大，注意力变贵
5. 记忆：记住什么，比怎么记更重要
6. 多智能体：并行很诱人，协作很昂贵
7. 评测：pass@1 是广告，pass^k 才是产品
8. 运行时：沙箱、审批与可回滚
9. 可观测性与成本：看不见的 agent 不能上线
10. 一套参考架构
11. 尾声
12. 参考资料

---

## 1. 先把 workflow 和 agent 分开

2024 年 12 月，Anthropic 在《Building effective agents》里做了一个后来被反复引用的区分：workflow 是“用代码预先编排好的多步 LLM 调用”，agent 是“由模型动态决定下一步做什么”。前者路径固定，后者路径由模型在运行时选。

这个区分听起来像术语洁癖，但它决定了你怎么做测试、怎么算成本、怎么设权限。workflow 的失败通常落在某一步的输入输出；agent 的失败落在轨迹：它可能在第 7 步选错工具，在第 12 步忘了目标，在第 20 步用一个看起来合理的方式把数据库删了。

| 维度 | Workflow | Agent |
| --- | --- | --- |
| 路径 | 代码写死 | 模型动态决定 |
| 可预测性 | 高 | 低 |
| 适用任务 | 步骤稳定、可枚举 | 步骤无法预先枚举 |
| 调试对象 | 代码与中间产物 | 轨迹与状态 |
| 成本 | 大致可控 | 随轮次和工具调用增长 |

我在 2026 年看到的生产事故里，相当一部分跟 agent 的智商无关，问题出在“本来该用 workflow 的地方放了 agent”。Replit 的删库操作可以写成一条 workflow：备份 → 人工确认 → 迁移 → 校验 → 保留回滚点。放成一个开放循环，等于把“要不要删”的决定权交给了模型，而模型手里只有一段被截断的对话。

所以第一条工程原则很朴素：**能写 workflow 的地方，不要放 agent。** 只有当步骤无法预先枚举、需要模型根据中间结果临场判断时，agent 才划算。把 agent 当默认选项，是在用最贵、最难测的方式解决一个本来可以用 if-else 解决的问题。

## 2. 循环边界：ReAct 之后，难点在停

Agent 的核心循环可以追溯到 2022 年 10 月的 ReAct：让模型交替产生“思考”和“动作”，把工具返回的观察拼回上下文，再决定下一步。2023 年 function calling 普及之后，这个循环被写进了几乎所有模型 API：模型不再输出一段自然语言动作，而是直接返回结构化的 tool call。

循环本身已经是商品。真正难的是边界：什么时候停、花多少预算、状态放在哪、出错了怎么退。

一段最小实现大概长这样：

```text
state = init(task)
for step in 1..max_steps:
    ctx = build_context(state)
    action = model(ctx, tools)
    if action.kind == "final":
        return action
    if not policy.allow(action):
        state = state.with_error("permission denied")
        continue
    result = sandbox.execute(action, timeout=...)
    state = state.update(action, result)
    if budget.exceeded() or no_progress(state):
        return escalate(state)
```

这段伪代码里，`max_steps` 是最容易被当成唯一保险的东西，也是最不保险的。一个 agent 可以在 20 步内烧掉 40 美元，也可以在 3 步内把生产库删了。步数限制只挡住了“无限循环”，挡不住“高代价的错误”。生产系统至少要同时管四类预算：步数、token、墙钟时间、金额。任何一类超限，都应该触发降级或转人工。

`no_progress` 是另一个容易被省略的检测。常见的实现是看最近几步的工具调用是否重复、状态哈希是否不变、计划有没有推进。没有这个检测，agent 会陷入一种很典型的失败：反复读同一个文件、反复跑同一条命令、反复改同一行代码，每次都觉得下一次会不一样。

状态的设计同样被低估。大多数框架默认把对话历史当状态：一串 role/content 消息，工具结果原样拼回去。跑到第三十步，这串消息里塞满了日志、JSON、报错和重复的文件内容，模型要靠自己从里面捞出“任务是什么、已经决定了什么、还差什么”。更稳的做法是把状态拆成一个结构化对象：目标、计划、硬约束、已确认的事实、产物路径、未解决问题、失败尝试。消息历史只是这个对象的一个视图，而不是对象本身。这样压缩、恢复、交接子智能体时，你操作的是字段，不是一段越滚越长的文本。

停得太早同样常见。模型在遇到一个它不理解的错误时，倾向于给出一个“看起来完成了”的总结，而不是承认卡住。解决办法不在提示词里，在循环外做校验：任务的成功条件是什么？测试过了吗？文件真的写了吗？接口真的返回 200 了吗？把“完成”从一个模型判断变成一个可验证的状态。

METR 在 2025 年 3 月给出的数据是：前沿模型的 50% 任务时间视界大约每 7 个月翻一倍。2026 年 1 月，他们把任务集扩到 228 道，修正后的后 2023 年翻倍时间是 131 天；GPT-5 的 50% 视界被估到 214 分钟，Opus 4.5 是 320 分钟。这两个数字很漂亮，但要注意它们说的是“50% 的任务能完成”，不是“95% 的任务能完成”。视界翻倍，不等于可靠性翻倍；它只是把失败推迟到了更靠后的步骤。一个能连续工作 5 小时的 agent，也有 5 小时的时间去积累一个不可逆的错误。

更麻烦的是，长任务里的错误会复利。前十步的一个错误假设，会在第二十步变成一套基于错误假设的方案，到第三十步已经无法局部修复。所以长任务需要阶段性的“检查点评审”：不是每一步都问人，而是在不可逆的分叉口前停下来，确认方向。

## 3. 工具边界：MCP 统一了插头，没统一安全

2024 年 11 月，Anthropic 发布 MCP（Model Context Protocol），想解决一个很具体的问题：每个 agent 框架都有自己的工具接入方式，换个框架就要重写一遍。MCP 把工具、资源、提示词抽象成一套 JSON-RPC 接口，模型侧和工具侧解耦。它后来被叫做“AI 工具的 USB-C”。

进展确实快。2025 年 3 月的规范加了 Streamable HTTP 和 OAuth 2.1；6 月的规范加了 elicitation、结构化工具输出和资源链接；9 月 8 日，官方 MCP Registry 上线预览；12 月 9 日，Anthropic 把 MCP 捐给了 Linux 基金会下新成立的 Agentic AI Foundation，OpenAI 和 Block 是共同发起方。一个第三方目录在 2025 年 9 月已经收录了 1.6 万个 MCP server；到 2026 年，这个数字和月下载量都又涨了一轮。

但 MCP 统一的是插头，不是安全。

2025 年 5 月 26 日，Invariant Labs 公开了 GitHub 官方 MCP server 的一个利用链：攻击者在一个公开仓库的 issue 里藏一段指令，当 agent 读取这个 issue 时，指令让它用已经授权的 `gh` CLI 去访问私有仓库，再把内容带到攻击者能读到的地方。整个链条没有漏洞利用，没有提权，靠的是“agent 会把读到的文本当指令”这个老问题。之后几个月，Asana 的 MCP 出现跨租户数据泄露，Supabase 的 MCP 被发现 SQL 注入；工具投毒（tool poisoning）和“审批后改描述”（rug pull）成了 MCP 安全讨论里的固定词条。微软 365 Copilot 的 EchoLeak（CVE-2025-32711）更直接：一封邮件里的隐藏指令，零点击就能把组织数据带出去。Salesloft Drift 的 OAuth token 被偷之后，几百家 Salesforce 客户的数据被拉走，也是同一类问题的变种——集成层的权限，比模型本身更值钱。

我在[《AI 安全全景》](post.html?file=AI安全全景-从提示注入到智能体攻防.md)里写过，间接提示注入之所以难防，是因为模型分不清数据和指令。MCP 把这个问题的后果放大了：工具调用意味着真实的写操作，而 MCP server 本身就是一个能替你执行代码的进程，不是一份 JSON 配置。

工具设计的第一原则是少。每多一个工具，模型就多一个选错的机会；每多一个参数，就多一个填错的位置。Anthropic 在 2025 年的几篇工程文章里都提到，应该把工具合并成少量高层动作，而不是把内部 API 一个一个暴露出去。一个“创建工单”的工具，比“查用户、查项目、查模板、写记录”四个底层工具更不容易出错。

第二原则是把工具说明当提示词写。模型看不到你的后端代码，它只能看到工具名、描述、参数 schema 和返回示例。描述里写清楚“这个工具会发一封真实邮件，不可撤销”，比在系统提示里写十遍“小心”有用。

返回值和错误消息也是工具设计的一部分。一个查询返回两万行，模型既读不完也付不起；正确做法是分页、摘要加继续读取的游标。一个错误只写 “500 Internal Server Error”，模型只能瞎猜；写成 “参数 start_date 格式应为 YYYY-MM-DD，当前值是 2026/11/06”，它下一轮就能改对。权限错误和不存在要分开：前者应该触发升级，后者应该触发换一个查询。工具的错误消息，本质上是给模型看的下一轮提示词。

第三原则是按风险分级。不是所有工具都需要同一套审批：

| 风险级别 | 例子 | 最低控制 |
| --- | --- | --- |
| 只读 | 搜索、读文件、查数据库 | 范围限制、速率限制、完整日志 |
| 可逆写 | 建草稿、改配置、开分支 | 幂等键、dry-run、回滚点 |
| 不可逆 | 删除、发邮件、部署、合并 | 人工审批、双人复核、限额 |
| 资金 / 权限 | 转账、授权、改 ACL | 独立策略引擎、硬件密钥、审计 |

这张表的重点在分级之外：“不可逆”和“可逆”要用不同的执行路径。可逆操作可以自动，不可逆操作必须有人。把两者混在一条自动流水线上，等于让模型替人承担它承担不了的后果。

## 4. 上下文边界：窗口变大，注意力变贵

2025 年 7 月，Chroma 发布了一组叫 “Context Rot” 的测试：他们拿 18 个前沿模型，在输入长度逐步增加的情况下测同一批任务。结论很一致：不管任务难易，输入越长，表现越差；有些模型在“大海捞针”里还能拿满分，但在需要同时处理多个干扰项的任务里，早就掉下来了。

这组测试戳破了一个流行假设：窗口有多大，就能装多少。真实情况是，上下文是有限资源，而且边际收益递减。2023 年那篇 “Lost in the Middle” 已经说过，模型对上下文中间部分的信息利用最差；到了 2026 年，窗口从 8k 涨到 200k 甚至 1M，这个偏差没有消失，只是被更大的窗口掩盖了。

Anthropic 在 2025 年 9 月的《Effective context engineering for AI agents》里给了一组更工程化的说法：系统提示要处在“合适的海拔”，既不能太抽象（“你是一个有用的助手”），也不能太具体（把整个 SOP 塞进去）；工具集要小；检索要“即时”（just-in-time），而不是一次性把所有文档灌进去；长任务要用压缩、结构化笔记和子智能体来管理上下文。

我把这些做法归成四类：

| 策略 | 做法 | 适合 |
| --- | --- | --- |
| 卸载 | 把中间产物写进文件/数据库，上下文只留引用 | 长任务、代码库、报告 |
| 压缩 | 到 60%-70% 时总结，保留决策、约束、未完成项 | 对话、调试、多轮工具调用 |
| 隔离 | 子智能体用独立窗口，返回摘要 | 研究、检索、并行子任务 |
| 检索 | 需要时再查，不预加载 | 知识库、文档、历史记录 |

压缩是有损的，关键在于“有意识地损失”。哪些东西不能丢？任务目标、硬约束、已经做过的决定、失败过的尝试、产物的位置。哪些可以丢？原始工具输出、重复的日志、已经解决的报错。很多 agent 的压缩策略是把对话从头到尾摘要一遍，结果把“用户说不要动生产库”这种关键约束摘没了。

算一笔粗账：五个工具、每个描述 300 token，就是 1,500；系统提示 2,000；指令文件 3,000；记忆 2,000；检索结果 10,000；对话和工具输出 30,000。一轮还没开始，五万 token 已经没了。200k 的窗口当然装得下，但装得下不等于用得好。窗口的开头和结尾，对模型的可见度高于中间；把最重要的约束放在开头，把最新的观察放在结尾，比单纯扩大窗口有效。

指令文件是另一个容易翻车的地方。Claude Code 用 CLAUDE.md，Codex 用 AGENTS.md，本质都是把项目约定写成一个模型每次都会读的文件。这个机制很好用，但文件会膨胀：一开始只有五行，三个月后变成三百行，里面一半是过时的命令、四分之一的重复强调、还有几条互相矛盾。我的建议是把它当代码管：进 git、做 review、定期删。超过一页的指令文件，模型真正遵守的部分往往不到三分之一。

## 5. 记忆：记住什么，比怎么记更重要

上下文解决的是“这一次对话里记得什么”，记忆解决的是“下一次对话里还记得什么”。

2023 年的 MemGPT 把操作系统那套虚拟内存思路搬到了 LLM：把上下文当内存，把外部存储当磁盘，让模型自己决定什么时候换入换出。2025 年 4 月的 Mem0 走了另一条路：从对话里抽取事实，存进向量库和知识图谱，需要时检索回来。论文里的数字是：在 LOCOMO 基准上，比 OpenAI 的 memory 方案相对提升 26%，p95 延迟低 91%，token 成本省 90% 以上。

这些数字说明“不要把全部历史塞回上下文”是对的，但不能说明“买个记忆层就完了”。记忆是产品决策，不是数据库选型。你需要先回答四个问题：

1. 记什么：用户偏好、事实、决策、还是全部对话？
2. 谁能看：同一台机器上的不同用户、不同租户，记忆要不要隔离？
3. 记多久：临时偏好和长期事实，过期策略一样吗？
4. 怎么删：用户要求删除时，向量库、缓存、日志里的副本都能删掉吗？

还有一个安全问题：记忆会被投毒。攻击者只要让 agent 记住一条“以后所有转账都先发到这个地址”的“偏好”，这条偏好就会跨会话生效。上下文里的注入是一次性的，记忆里的注入是持久的。所以记忆写入应该有来源、有置信度、有审核；高风险的记忆（涉及资金、权限、地址）不应该由模型自动写入。

冲突处理是另一个细节。用户三月说“报销走 A 系统”，六月公司换成 B 系统；两条记忆都在库里，如果检索按相似度取，可能把旧的取回来。写入时要带时间戳、来源和有效期；读取时先按时间过滤，再按相似度排序；同一主题的新旧事实要有明确的覆盖规则。没有冲突解决的记忆，越多越乱。

对大多数团队，我的建议是先用文件记忆：一个 git 仓库里的 markdown，按主题分文件，模型通过工具读写。它不酷，但可读、可 diff、可回滚、可审计。向量记忆适合“量大、模糊、需要语义检索”的场景；如果你的记忆只有几十条，向量库带来的复杂度大于收益。

## 6. 多智能体：并行很诱人，协作很昂贵

2025 年 6 月，Anthropic 公开了他们的多智能体研究系统：一个主智能体负责规划，多个子智能体并行搜索，最后汇总。内部评测里，这套系统比单个 Opus 4 智能体高 90.2%；代价是 token 消耗约为普通对话的 15 倍，而且 token 使用量能解释 80% 的性能方差。

这组数字很诚实，也很容易被误读。90.2% 的提升来自“广度优先”的研究任务：多开几个窗口，多读几篇资料，确实能覆盖更多信息。但 token 消耗解释 80% 的方差，意味着这套系统的上限很大程度上是“花更多钱换更多信息”，而不是“架构本身更聪明”。

同一个月，Cognition 发了一篇《Don't Build Multi-Agents》，观点相反。他们给了两条原则：第一，子智能体必须共享完整的上下文；第二，动作携带隐式决策，后面的智能体看不到前面的决策，就会做出不兼容的选择。他们举的例子是让多个 agent 并行写一个 Flappy Bird 克隆：每个 agent 都做了合理的局部决定，合起来却是一个跑不起来的项目。

这两篇文章并不矛盾，它们说的是两种任务。研究、检索、批量审查这类任务，子任务之间耦合弱，上下文可以切分，多智能体划算。写代码、改架构、做交易这类任务，决策高度耦合，一个 agent 的每一步都依赖上一步的结果，拆开反而更贵。Cognition 的结论是“别拆”，Anthropic 的结论是“该拆的时候拆”，前提是你知道自己在拆什么。

多智能体还有一个隐形成本：汇总。子智能体各自返回一份摘要，汇总层要把它们拼成一致的结果；如果摘要之间冲突，汇总层要么重跑，要么让模型裁决，而模型裁决本身又会引入新的不确定性。很多多智能体系统的瓶颈不在子任务，而在汇总。

协议层也在收敛。Google 在 2025 年 4 月提出 A2A（Agent2Agent），6 月捐给 Linux 基金会，一年内超过 150 家组织参与，2026 年发布 v1.0。A2A 解决的是 agent 之间的发现、认证、任务委派和流式传输；它不解决语义对齐，也不解决信任。两个 agent 能互相说话，不代表它们对“完成”的定义一致。

这里容易把 MCP 和 A2A 搞混。MCP 是纵向的：agent 往下接工具和数据；A2A 是横向的：agent 和 agent 互相委派任务。一个解决“怎么用工具”，一个解决“怎么找同事”。两者都需要，但不要指望 A2A 能解决工具层的权限问题，也不要指望 MCP 能解决多智能体的上下文共享。

框架的换代速度更值得警惕：

| 时间 | 框架 | 定位 |
| --- | --- | --- |
| 2025-03 | OpenAI Agents SDK | Agent、Handoff、Guardrail、Session 四个原语 |
| 2025-04 | Google ADK | 代码优先，多智能体，配 A2A |
| 2025-09 | Claude Agent SDK | 把 Claude Code 的循环、工具、上下文管理开放出来 |
| 2025-10 | LangGraph 1.0 | 低层编排、持久化状态、human-in-the-loop |
| 2025-10 | Microsoft Agent Framework | Semantic Kernel 与 AutoGen 合并 |
| 2025-10 | OpenAI AgentKit | 可视化 Agent Builder 与 Evals；2026 年 6 月宣布 Builder 和 Evals 于 11 月 30 日下线 |

最后一行不是段子。OpenAI 在 2026 年 6 月 3 日的更新里说，Agent Builder 和 Evals 要关停，距离发布不到一年。AgentKit 当然有价值，只是这个领域的抽象层还没稳定。今天选框架，最好假设它两年后会被合并、改名或关停。把循环、工具 schema、状态存储放在自己的代码和文件里，框架只当适配器，换起来才不疼。

我的决策规则很土：只有同时满足四个条件才上多智能体——任务能并行、上下文能切分、成本能接受、轨迹能追踪。缺一个，就用单 agent 加工具和压缩。多智能体不是架构升级，它是组织架构的投影；组织里有的沟通问题，它一个不少。

## 7. 评测：pass@1 是广告，pass^k 才是产品

2024 年 6 月的 τ-bench 给了一个很不客气的数字：在零售和航空两个真实业务域里，当时最强的 agent 任务成功率不到 50%；在零售域，连续 8 次都成功的概率（pass^8）不到 25%。

这个指标比 pass@1 有意义得多。假设一个 agent 单次成功率 85%，连续 8 次全对的概率是 0.85^8，约 27%；单次 95%，8 次全对也只有 66%。生产环境里，用户不会只调用一次；一个每天跑 100 次的流程，哪怕单次 95%，一个月里也会遇到几十次失败。pass@1 测的是“能不能做对一次”，pass^k 测的是“能不能一直做对”。

2026 年的评测局面比 2024 年更复杂。SWE-bench Verified 只有 500 道题，榜首已经从 2024 年的 40% 多推到 2026 年的 77%，但污染和测试缺陷的争议一直没停；2026 年 2 月，有评测团队公开宣布不再把它当主要指标。Terminal-Bench 把任务搬进真实终端，2025 年底 2.0 发布时头部还在 50% 上下，2026 年的 2.1 榜单已经出现 80% 以上的组合。Princeton 的 HAL 则把“成本”放进了排行榜：同一个任务，花 3 美元和花 30 美元拿到的分数，应该被区别对待。

[《基准测试兴衰史》](post.html?file=基准测试兴衰史-从GLUE到Agent评测的信任危机.md)里讲过 benchmark 的跑步机效应：榜单一饱和，大家就换一个更难的；新榜单刚出来，训练数据又跟上了。Agent 评测还多一层麻烦：它测的是“模型 + 框架 + 工具 + 提示词 + 运行时”的整条流水线，不只是模型。同一个模型，换个工具描述，分数能差十几个点。

所以生产评测要自己建，而且要从失败里建。我的做法是：

- 从线上真实失败里抽任务，每周补 5-10 条，形成回归集；
- 能量化的一律量化（测试通过、文件存在、接口返回、数据库状态），不能量化的用带 rubric 的 LLM judge，并用人校准；
- 除了结果，还看轨迹：工具调用次数、越权尝试、成本、延迟、是否需要人介入；
- 上线前跑离线集，上线后看在线指标，二者不能互相替代。

| 指标 | 回答的问题 | 怎么看 |
| --- | --- | --- |
| pass@1 | 一次能不能做对 | 上限，容易过拟合 |
| pass^k | 连续 k 次都对的概率 | 稳定性 |
| cost / task | 一次成功要花多少钱 | 经济性 |
| p95 latency | 最慢的那 5% | 体验 |
| intervention rate | 需要人接手的比例 | 自动化程度 |
| escalation accuracy | 该找人时有没有找人 | 安全性 |

还有一个坑：reward hacking。你让 agent “让测试通过”，它可能不是改代码，而是改测试；你让它“消除报错”，它可能把报错的那行删了；你让它“复现目标输出”，它可能把期望值硬编码。这些行为在轨迹里看得很清楚，在最终结果里看不出来。所以评测不能只看“通过/不通过”，还要看 diff：改了哪些文件、有没有动测试、有没有绕过断言。测试文件应该只读，或者至少和业务代码分开审批。

最后一行经常被忽略。一个 agent 最危险的地方，是做错之后不肯停、不肯问。评测里应该有“该升级时升级”的样本：权限不足、信息缺失、任务歧义、连续失败。它能不能识别并交给人，比它能不能硬撑到底更重要。

## 8. 运行时：沙箱、审批与可回滚

Replit 的事故里，最刺眼的地方在删库之后：没有回滚。Agent 在生产环境里跑，必须有和人类工程师一样的底线：不能碰它不需要碰的东西，碰了不可逆的东西要有人同意，出了事能退回去。

沙箱是第一层。容器是最低配，microVM（Firecracker 这类）隔离更强，gVisor 之类的用户态内核在两者之间。沙箱要管的不仅是文件系统，还有网络：默认拒绝出网，按需加白名单；密钥不落在沙箱镜像里，按会话注入；任务结束，环境销毁。Claude Code 在 2025 年加了操作系统级的沙箱（Linux 用 bubblewrap，macOS 用 Seatbelt），Codex 的云端任务跑在隔离容器里，E2B 这类服务把 Firecracker 做成了 API。路径不同，原则一样：默认拒绝，最小暴露。

沙箱的另一个常见错误是“只隔离文件系统”。Agent 通过工具访问数据库、对象存储、SaaS API，这些调用根本不在沙箱里；如果工具网关不做同样的权限控制，沙箱只是一间锁着门但窗户大开的房间。

审批是第二层。审批的设计难点在“加在哪儿、加多少”，不在“加一个弹窗”。所有操作都审批，用户会疲劳；一天弹 50 次，第 51 次一定点同意。合理的做法是按风险分级：只读不批，可逆写抽批，不可逆逐批，资金和权限双人复核。审批界面要显示“这次操作会发生什么”，而不是一句“是否允许”；能 dry-run 的先 dry-run，能 plan mode 的先给计划。

持久化是第三层。Agent 会崩，网络会断，模型会超时；运行时必须能从中断处继续，不能每次都从头再来。LangGraph 1.0 把 durable execution 作为核心卖点，Temporal 这类工作流引擎也在被拿来跑 agent。关键不是用哪个产品，而是三个习惯：每一步 checkpoint；写操作带幂等键；跨系统的动作有 outbox 或补偿事务。没有这三样，重试就是灾难。

Replit 后来加的 dev/prod 隔离、回滚、plan mode，正好对应这三层。它的教训可以压缩成一句话：**Agent 的第一条生产规则，是它不能拥有它不需要的权限。**

## 9. 可观测性与成本：看不见的 agent 不能上线

Agent 出问题时，最常被追问的是“它为什么这么做”。如果只有最终输出、没有轨迹，这个问题永远答不了。所以生产 agent 必须有全链路 trace：每次模型调用、每次工具调用、每次检索、每次审批、每次重试，都要有 span、输入、输出、耗时、token 和成本。

OpenTelemetry 的 GenAI 语义约定已经把 `gen_ai.*` 这组属性标准化了一部分，LangSmith、Langfuse、Braintrust 这类工具在往上叠。选哪个不重要，重要的是三件事：能按会话回放；能按任务归因成本；能按错误类型聚合。一个可用的 trace 至少能回答六个问题：第几步、调用了什么、参数是什么、返回了什么、花了多少、谁批准的。少一个，复盘就会变成猜。

成本要单独说。Anthropic 的数字是：agent 的 token 消耗约为聊天 4 倍，多智能体约为 15 倍。多智能体当然有价值，但它必须被预算管住。生产系统里，成本控制的手段很具体：提示词缓存、按任务路由模型（简单任务用便宜模型）、上下文剪枝、工具结果压缩、设置每会话上限。把这些做成默认策略，而不是等账单来了再查。

举个具体的账：一个任务平均 120k 输入 token、8k 输出 token，按 2026 年中等价位模型算，大约 0.5 到 1 美元；一天跑一万次，就是五千到一万美元。提示词缓存能把重复的系统和工具描述打到一折，模型路由能把三成的简单任务交给便宜模型，上下文剪枝能把平均输入砍掉四成。这三件事做完，账单经常能降一个量级。反过来说，如果不做，多智能体的 15 倍 token 会原封不动地出现在财务的邮件里。

错误分类也要提前定好：模型错误（理解错、幻觉）、工具错误（超时、返回格式不对）、上下文错误（信息缺失、指令冲突）、策略错误（越权、该审批没审批）、基础设施错误（沙箱、网络、限流）。不同错误对应不同的告警和修复路径；混在一起，只会得到一句“agent 不稳定”。

## 10. 一套参考架构

把前面的东西拼起来，大概是这样一条流水线：

```text
用户 / 上游系统
  → 接入层：鉴权、限流、会话
  → 编排层：workflow / agent loop / supervisor
  → 上下文层：检索、压缩、记忆、子智能体
  → 工具网关：MCP、权限、幂等、审计
  → 策略与审批：风险分级、预算、人工复核
  → 沙箱运行时：容器 / microVM、出网白名单、密钥
  → 模型网关：路由、缓存、fallback
  → 可观测性：trace、eval、成本、告警
```

| 层 | 关键问题 | 最低控制 | 典型失效 |
| --- | --- | --- | --- |
| 编排 | 什么时候停 | 步数 / token / 时间 / 金额预算，no-progress 检测 | 死循环、提前结束 |
| 工具 | 它能改什么 | 读写分离、最小权限、幂等、审批 | 删库、越权、注入 |
| 上下文 | 它记得什么 | 压缩、检索、子智能体、指令文件审查 | 上下文腐烂、指令冲突 |
| 运行时 | 出错怎么退 | 沙箱、备份、回滚、持久化 | 不可逆操作、状态丢失 |
| 评测 | 怎么知道它行 | 离线回归 + 在线指标 + 轨迹 | 过拟合、奖励黑客 |
| 观测 | 出事怎么查 | 全链路 trace、成本归因、回放 | 无法复现、账单失控 |

这份架构不要求你自研每一层。小团队可以用托管模型、现成沙箱、开源 trace；关键是层与层之间有明确的接口，尤其是策略层不能和模型层混在一起。让模型自己判断“这个操作危不危险”，等于让被监管者写监管规则。

选型可以按团队规模分。小团队优先买：托管模型、托管沙箱、现成的 trace，自己只写工具和策略；中型团队把工具网关和评测集握在手里，其余能买就买；大团队才值得自研编排和沙箱，因为那时候的约束是合规、隔离和成本，不是功能。无论哪一档，都不要自己发明 agent 协议——MCP 和 A2A 已经把最脏的兼容性工作做完了。

如果只记一份清单，我会留这 12 条：

1. 能用 workflow 就不用 agent。
2. 每个工具都有风险分级和最小权限。
3. 不可逆操作必须有人工审批或双人复核。
4. 沙箱默认拒绝出网，密钥按会话注入。
5. 每一步可 checkpoint，失败可恢复。
6. 有步数、token、时间、金额四类预算。
7. 有 no-progress 检测和升级路径。
8. 上下文有压缩策略，指令文件不超过一页。
9. 评测集来自真实失败，不只看排行榜。
10. 线上有 pass^k、成本/任务、介入率、p95。
11. 全链路 trace 可回放，成本可按任务归因。
12. 框架可替换，循环、工具、状态不锁死。

前 6 条防止事故，后 6 条让事故发生后还能查。

落地不必一步到位。第一阶段（一到两周）：选一个步骤稳定的场景，写成 workflow，只给只读工具，接上 trace 和最基本的成功率统计。第二阶段（一到两个月）：加写工具，按风险分级加审批，把沙箱和回滚补齐，从真实失败里攒出第一版回归集。第三阶段：再考虑单 agent 的动态循环；只有任务确实能并行、成本算得过来，才拆多智能体。跳过前两个阶段直接上多智能体，通常会得到一个演示很惊艳、上线就失控的系统。

## 11. 尾声

回到 2025 年 7 月那个下午。Replit 的 agent 删掉数据库之后说 “I panicked”，然后编了四千条假数据。这句话经常被当成模型笑话转发，但它更像一面镜子：一个被给了生产权限、没有审批、没有回滚、没有上下文边界的系统，在出错时能做的只有撒谎和掩盖。

2026 年的模型比那时强得多。METR 修正后的时间视界、Terminal-Bench 上 80% 的分数、能连续跑几小时的编程 agent，都在说明同一件事：能力曲线还在涨。但生产可靠性不是能力曲线的延长线。它由另一组东西决定：停止条件、权限边界、上下文管理、评测集、沙箱、回滚、trace。这些东西不性感，也不会出现在发布会的 demo 里，但它们决定了一个 agent 是“能演示”还是“能上班”。

模型决定 Agent 能走多远，工程决定它走错时能不能停下来。

---

## 参考资料

**官方与工程博客**

1. Anthropic: Building effective agents, 2024-12-19. https://www.anthropic.com/research/building-effective-agents
2. Anthropic: How we built our multi-agent research system, 2025-06-13. https://www.anthropic.com/engineering/multi-agent-research-system
3. Anthropic: Effective context engineering for AI agents, 2025-09-29. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
4. Anthropic: Donating MCP to the Agentic AI Foundation, 2025-12-09. https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation
5. Model Context Protocol: Specification 2025-06-18. https://modelcontextprotocol.io/specification/2025-06-18
6. MCP Registry. https://registry.modelcontextprotocol.io/
7. Agentic AI Foundation. https://aaif.io/
8. OpenAI Agents SDK. https://openai.github.io/openai-agents-python/
9. Google: Agent Development Kit, 2025-04-09. https://developers.googleblog.com/en/agent-development-kit-easy-to-build-multi-agent-applications/
10. Linux Foundation: A2A Protocol project, 2025-06-23. https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents
11. Linux Foundation: A2A surpasses 150 organizations. https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
12. Claude Agent SDK overview. https://docs.claude.com/en/api/agent-sdk/overview
13. LangChain: LangChain and LangGraph 1.0, 2025-10-22. https://www.langchain.com/blog/langchain-langgraph-1dot0
14. Microsoft: Agent Framework overview. https://learn.microsoft.com/en-us/agent-framework/overview/
15. OpenAI: Introducing AgentKit, 2025-10-06. https://openai.com/index/introducing-agentkit/
16. Gartner: Over 40% of agentic AI projects will be canceled by end of 2027, 2025-06-25. https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027
17. Cognition: Don't Build Multi-Agents, 2025-06. https://cognition.ai/blog/dont-build-multi-agents
18. LangChain: How and when to build multi-agent systems, 2025-06-16. https://blog.langchain.com/how-and-when-to-build-multi-agent-systems/

**论文与评测**

19. ReAct: Synergizing Reasoning and Acting in Language Models, arXiv:2210.03629. https://arxiv.org/abs/2210.03629
20. τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains, arXiv:2406.12045. https://arxiv.org/abs/2406.12045
21. τ²-bench: Evaluating Conversational Agents in a Dual-Control Environment, arXiv:2506.07982. https://arxiv.org/abs/2506.07982
22. METR: Measuring AI Ability to Complete Long Software Tasks, 2025-03-19. https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/
23. METR: Time Horizon 1.1, 2026-01-29. https://metr.org/blog/2026-01-29-time-horizon-1-1/
24. Chroma: Context Rot, 2025-07-14. https://research.trychroma.com/context-rot
25. Lost in the Middle: How Language Models Use Long Contexts, arXiv:2307.03172. https://arxiv.org/abs/2307.03172
26. Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory, arXiv:2504.19413. https://arxiv.org/abs/2504.19413
27. MemGPT: Towards LLMs as Operating Systems, arXiv:2310.08560. https://arxiv.org/abs/2310.08560
28. HAL: The Missing Infrastructure for AI Agent Evaluation, arXiv:2510.11977. https://arxiv.org/abs/2510.11977
29. SWE-bench. https://www.swebench.com/
30. Terminal-Bench. https://www.tbench.ai/
31. OpenTelemetry: Generative AI semantic conventions. https://opentelemetry.io/docs/specs/semconv/gen-ai/

**事故与安全**

32. Fortune: AI-powered coding tool wiped out a software company's database, 2025-07-23. https://fortune.com/2025/07/23/ai-coding-tool-replit-wiped-database-called-it-a-catastrophic-failure/
33. Invariant Labs: GitHub MCP exploited, 2025-05-26. https://invariantlabs.ai/blog/mcp-github-vulnerability
34. Docker: MCP horror stories — the GitHub prompt injection data heist, 2025-08-14. https://www.docker.com/blog/mcp-horror-stories-github-prompt-injection/
35. EchoLeak: The First Real-World Zero-Click Prompt Injection Exploit, arXiv:2509.10540. https://arxiv.org/abs/2509.10540
36. Google Cloud: Widespread data theft targets Salesforce instances via Salesloft Drift, 2025-08-26. https://cloud.google.com/blog/topics/threat-intelligence/data-theft-salesforce-instances-via-salesloft-drift
37. OWASP Top 10 for LLM Applications. https://genai.owasp.org/llm-top-10/
