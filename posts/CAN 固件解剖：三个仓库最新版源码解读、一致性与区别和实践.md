---
title: CAN 固件解剖：在中国开启 FSD 的原理，与三个仓库的同构、分化与实测
date: 2026-10-01
tags: [自动驾驶, CAN总线, 嵌入式, 固件分析, 特斯拉, 源码分析]
album: 自动驾驶专栏
order: 3
excerpt: 三个公开仓库的最新版源码逐行解剖：钉死 commit 与行号后对照同一套骨架，讲清在中国"开启 FSD"的一条链路与三道门，再落到一台具体车——China HW4.0、2025 款 Model 3 的选型、购买、X179 接线与烧录。附 1183 个宿主用例（三仓）与 18 次板级构建的实测汇总。
---

《自动驾驶专栏》第三篇，2026-10-01。**原理一句话先给**：车机上的"已勾选"只是一帧 CAN 报文里的一个比特，所有工具做的事情都是让固件不再去看那一帧；而权益与地域围栏都不在这一帧里——这就是第 1 节的"一条链路、三道门"。

围绕同一条 CAN 总线的公开实现不止一个，本文考察其中三个：PlatformIO 固件工程 `tesla-open-can-mod`、Flipper Zero 应用 `flipper-tesla-fsd`、ESP-IDF 固件平台 `ev-open-can-tools`——三者形态差异显著，分别采用编译期选型、运行时菜单与网页开关。逐行解剖后可以看到：**收发序列集中于同一批文件，抽象骨架高度重合，分化集中在少数几条明确的维度上**。最后落到一台具体车辆（China HW4.0、2025 款 Model 3、2026.2.11），完成选型、采购、接线与烧录的全过程记录。

**结论前置。**下表六行是全文的结论，先于证据给出，每一行标注可回查的章节：

| 议题 | 结论 | 详见 |
| --- | --- | --- |
| **版本** | 三个仓库分别钉死在 `815e000`、`ffbb24e`（`v2.16-beta.34`）、`6d37392`（`v4.0.0-beta.3`，在 `dev` 分支而非 `main`）。**行号一律按这三个 commit；但第 8 节的实跑有一家停在 `6a3404f`** | 第 0 节 |
| **一致性** | 启动、运行、业务三层序列落在同一批文件里；绝对位号寻址、"校验和只管自己起的头"、"先清再置"的读改写纪律三家一致；`tesla-open-can-mod` 与 `ev-open` 的业务接口三个纯虚方法名逐字相同 | 第 5 节 |
| **区别** | 五条维度：选型在哪一层、发送许可在哪一层、OTA 期间的行为、功能面、许可证与发布。**分化最深的是发送许可**——一家不存在，一家让业务层每条路径各调一次（靠自律，五处调用），一家挂在驱动回调上（靠结构，业务层绕不过） | 第 6 节 |
| **在中国"开启"FSD 的原理** | 一条链路、三道门。车机把"用户已勾选"写进一帧 CAN 报文（`0x3FD` 的 `byte[4]` 第 6 位＝bit 38），固件的判定函数（先查编译期宏 → 再查运行时标志 → 最后读帧上的位）决定要不要注入——三家的覆写都落在这一个点上。另两道门不由固件动：权益在账号与服务端；地域围栏 `2026.14.x` 起位于总线之外（`esp32/README.md:430`） | 第 1 节 |
| **实测** | 18 个板级环境中 17 个可构建；宿主侧 1833 个用例（**三仓 1183 + 对照仓 650**，切分见 8.1）。**失败项比"1181 过"更说明问题**：宿主侧 2 个 native 套件因缺 `strlcpy` 编不过（不是代码错）、板级侧 `feather_rp2040_can` 死在失效包名上、`ev-open` 一个脚本在中文 Windows 上按 GBK 解码崩溃——三个根因、四处失败点，详见 4.6 与 8.3 | 第 8 节 |
| **边界** | 不烧录、不接车、不验证上车效果；仓库的指南到此为止 | 第 14 节 |

**最短路径：**只想弄懂原理读第 1 节（16 行讲清一条链路、三道门）；只想动手做读 12.7（十一步，唯一带 go / no-go 判据的清单）；想核数据读第 8 节。

> ### 本文的前提，读者先看这一框
>
> **分析对象**是三个公开仓库的**源码**，不是车。本文自始至终是一个"读代码的人"，不是"改装过车的人"——这一点决定了下文每一条的效力上限。
>
> **能力假设**：工具侧的写入能力**只有一帧**——`0x3FD`（或 Legacy 的 `0x3EE`）上那一位。没有服务端账号、没有以太网、没有 Fleet API、没有硬件密钥。本文讨论的全部固件侧手段，都在这个假设内。
>
> **不假设的事**：车端拿到这一帧之后会做什么。三道门里第一道门在总线内，后两道在总线外（1.3、1.4）；本文对后两者只能给出"为什么动不了"的机制说明，**给不出也无法给出"动了会怎样"的预测**。
>
> **证据分级**贯穿全文，三档定义见 0.2：**一手**（我能直接拿到原文）／**社区回报**（第三方单点陈述，我未独立核实）／**未核实**（我明确没有验证）。凡是第三档的结论，正文就地标注。
>
> **不做的事**：规避检测、隐匿接入、移除车上通信模块——一概不写。这不是姿态，是 1.4 已经给出理由：上游自己那条 "拔 SIM 降低检测风险" 的建议，本文在 1.4 只记录它存在、略去其操作步骤。

**三条读法，按你要的东西选：**

- **只想弄懂原理** → 0.4（帧 ID 与术语）→ 1.1（一条链路、三道门）→ 5、6（一致与分化）。这四节读完，勾选位、权益、地域锁的关系就清楚了。
- **只想马上动手** → 11.1（主方案与它的代价）→ 11.2、11.3（买什么）→ **12.7（十一步操作序列，全文的操作入口）**→ 13.1（两条预编译路径）→ 14.1、14.2（面板四步与那个默认关的主开关）、14.4（抓帧回放）。想先确认"这块板子能不能用"再看 11.6。
- **想核我的实测数据** → 8（宿主测试与板级构建）→ 0.2（证据分档约定）。第 2–4 节的所有 `file:line` 都与 8 的表同源。

---

## 目录

**第一部分 · 范围与关键分歧**

- **0. 三个版本，先钉死** —— 三个仓库的 commit / tag、证据分档约定、三家同源的来历、帧 ID 与术语对照
- **1. 在中国"开启"FSD：一条链路，三道门** —— 勾选位、权益与地域围栏三道门的可动性

**第二部分 · 逐仓库解剖**

- **2. `tesla-open-can-mod`：最干净的教学样本** —— 文件地图、三层序列、位操作与校验和、门控清单
- **3. `flipper-tesla-fsd`：整个生态的重心** —— 两份业务层、发送许可、nag killer 与 bit47 的两次改口
- **4. `ev-open-can-tools`：最像平台的一个** —— 平台化选型、OTA 闸、驱动回调许可与两处实测故障

**第三部分 · 一致性与区别**

- **5. 一致：同一个骨架** —— 三层序列对照表与五处跨仓库共识
- **6. 区别：五条维度** —— 选型、发送许可、OTA 期间行为、功能面、许可证与发布
- **7. 定位：三个仓库在哪一层** —— 三层定位图；三家都住总线层，差别在总线层内部的纵深

**第四部分 · 实测与未知**

- **8. 实测汇总** —— 宿主 1183 例（三仓，含对照仓 1833）、18 次板级构建与六条报错分组
- **9. 兼容性：一个诚实的未知** —— 2026.2.11 该编哪个宏，可验证与不可验证的分界

**第五部分 · 一台具体配置的实践**（China HW4.0 / 2025 款 Model 3 / 2026.2.11）

- **10. 先把车钉死：这台车意味着什么** —— HW4、DoIP、X179 针号、SOP 时间线四条硬约束
- **11. 选什么、买什么** —— 主方案与代价、清单、线材、五套备选与三家的 ESP32-S3 支持实践
- **12. 接线：从 X179 到螺丝端子** —— 位置口径、20/26-pin 引脚表、终结电阻、供电三坑与十一步序列
- **13. 烧录与上电：三条路** —— 两条预编译路径（ESP32 / Flipper）与本地编译，以及两处文档裂缝
- **14. 板子与车上的操作流程，以及仓库的指南到此为止** —— dashboard 四步、面板开关清单、抓帧回放与边界

**第六部分 · 出处与总结**

- **15. 参考与引用：本文用到的每一条外部出处** —— 按性质分层的单一出处表、证据分层与高频锚点反查
- **16. 总结** —— 四条判断、方法论与全文边界

---

# 第一部分 · 范围与关键分歧

本部分先交代版本与证据约定，再把三个仓库在 FSD 地域围栏这一个具体问题上先行对照。

## 0. 三个版本，先钉死

**行号只有钉在版本上才有意义，而钉住行号的前提是先钉住版本。**三行均于 2026-10-01 用 `git ls-remote` 实时查询。

### 0.1 三个仓库的 commit 与 tag

**下表三格对应 2–9 节的全部 `file:line`，换一格就要重推**：

| 仓库 | commit | 版本 | 说明 |
| --- | --- | --- | --- |
| [`1-v-1/tesla-open-can-mod`](https://github.com/1-v-1/tesla-open-can-mod) | `815e000` | 无 tag、无 release | 最后一次 push 停在 2026-04-02，距查询日 183 天。第 2 节全部行号按该 commit 的检出逐条核对 |
| [`hypery11/flipper-tesla-fsd`](https://github.com/hypery11/flipper-tesla-fsd) | `ffbb24e` | `v2.16-beta.34`（2026-10-01） | 查询当天仍在提交；`esp32/.firmware/main.cpp` 在 beta.33 至 beta.34 之间移动 25 行 |
| [`ev-open-can-tools/ev-open-can-tools`](https://github.com/ev-open-can-tools/ev-open-can-tools) | `6d37392` | `v4.0.0-beta.3`（2026-09-20） | 不在默认分支：`main` 停在 `338d276`（2026-08-05，`VERSION` 写 3.1.1），须检出 `dev`。两线于 `447049d`（2026-07-31）分叉，`dev` 领先 14 个提交 |

第三行有个容易踩的坑：仓库接口返回的 `pushed_at` 记录的是 `dev` 的推送时间，而默认 clone 拿到的是 `main`——两者相差 46 天。

### 0.2 证据约定：按结论类型分档，不混用

| 结论类型 | 验证方式 |
| --- | --- |
| 某段代码在哪一行 / 文档与代码对不上 | 在上表所列 commit 的检出上逐行读、双方各 grep 一次，可复现；每条标 `文件:行号` |
| 测试数量与断言 | 逐个 `RUN_TEST` 计数，并实际执行 |
| 板级 env 能否编出固件 | 安装 PlatformIO 实际构建，输出见第 8 节 |
| HW4 / 某个 OTA 版本该编哪个宏 | 规则来自仓库 README，行号可复现；上车效果未验证 |
| X179 引脚、哪对线上是哪条总线 | 仓库文档原文加出处行号；本文未接车、未使用示波器，未实测 |
| star、日期、tag、价格、兼容性、行业事件 | `git ls-remote`、公开接口、网络检索，附 URL 与页面日期，可复现但未逐行核验 |
| 烧录之后车会怎么反应 | 完全不验证：没有板子、没有线束、没有车辆，见第 14 节 |

### 0.3 三家同源，不是巧合

0.1 表第一行"停在 2026-04-02"不是孤例。把各家 README 的自述拼起来（`flipper` 两处行号取自 `ffbb24e`，一手；`jvanakker` 引文访问于 2026-10-02），这条线是连着的：

- **原始研究** `Starmixcraft/tesla-fsd-can-mod`（CanFeather）——`flipper` `README.md:374` 称其 "original CanFeather FSD research" 并注明 **"GitLab repo removed"**；两个镜像（`jvanakker/tesla-fsd-can-mod`、`Karolynaz/waymo-fsd-can-mod`）自陈是它的副本。
- **后续正统** `ev-open-can-tools`——`flipper` `README.md:361` 称其为 "The upstream community project"，并写明"Formerly `Tesla-OPEN-CAN-MOD` on GitLab; that group was renamed"。第 4 节那个"最像平台"的仓库就是这条线的现存端。
- **下架原因**两个镜像都指向存档站 `fsdcanmod.com`，**该域名 2026-10-02 已无法解析**（DNS 查询失败，复核两次）。页面内容我只从检索快照读到 "Both GitLab repos taken down by Tesla DMCA (April 2026)"——**DMCA 的定性归入未核实**，可核实的只有上述两处 README 的 "removed / taken down"。

**三点直接影响。**其一，教学样本停更与 "April 2026" 的下架窗口时间重合，**但时间重合不是因果**——`1-v-1` 与 GitLab 原仓的 fork 关系我未查到（GitHub API 被限流），反过来把"停更"读作"弃坑"同样没依据。其二，9.3 引用的 `jvanakker` 失效标注出自同一镜像 README，**指涉 CanFeather 原始固件、不是本文第 2 节的样本代码**。其三，flipper 称 ev-open 为 upstream——**这给第 5 节那张"几乎能互相覆盖"的骨架表提供了注脚：同源，不是巧合**。

### 0.4 帧 ID 与术语对照

后文引用帧时，本文先给十进制（与三份源码里的 `frame.id == ...` 一致），再括注上游文档惯用的十六进制；两者是纯算术换算（`0x3FD` = 3×256 + 0xFD = 1021）。下表逐条取自 `flipper` 的 CAN ID 表（`README.md:310-329`，**共 18 行，本文只列与本文结论相关的 11 行**），钉在 `ffbb24e`，**行号于 2026-10-01 复核**——上游 README 会被改写，若你日后核不上，先确认时点。

| 十进制 | 十六进制 | 信号名 | 方向 | 本文出现处 |
| --- | --- | --- | --- | --- |
| 1021 | `0x3FD` | `UI_autopilotControl` | TX | **选择位（bit 38，读）与 FSD 使能（bit 46，写）都在这一帧**（1.1、2.4） |
| 1006 | `0x3EE` | `UI_autopilotControl` | TX | 同上，Legacy HW1/HW2（2.4） |
| 921 | `0x399` | `ISA_speedLimit` / `DAS_status` | TX/RX | 按硬件代际分派：Legacy/HW3 读 DAS 状态，HW4 走 ISA 速度警告抑制（2.6） |
| 1016 | `0x3F8` | `UI_driverAssistControl` | TX | HW3/HW4 的第二条监听帧；telemetry-off 涉及的位在其中（2.4、14.2） |
| 962 | `0x3C2` | `VCLEFT_switchStatus` | TX | 工具写入以模拟转向柱按键（ScrollPress AP），并决定可见总线（1.4、11.5、12.3） |
| 880 | `0x370` | `EPAS3P_sysStatus` | TX | nag 回声所在的 Chassis CAN 帧（3.5、12.2） |
| 923 | `0x39B` | `DAS_status` | RX | HW4/Highland HW3 的 AP 状态，AP-First（14.x）读它判断 AP 是否已接合（1.4、10.1） |
| 792 | `0x318` | `GTW_carState` | RX | OTA 检测（6.3、14.2） |
| 817 | `0x331` | `DAS_autopilotConfig` | TX | TLSSC Restore（1.4、14.2） |
| 2047 | `0x7FF` | `GTW_carConfig` | TX | GTW Config Replay 与档位覆盖（1.4） |
| 787 | `0x313` | `UI_trackModeSettings` | TX | Track Mode（平衡 / 稳定 / 散热）。**全文只在 3.6 的校验和清单与 5.2 提过，没有展开**——它不在本文这台车要注入的那几帧上 |
| *（上表 18 行中未列的 7 行）* | | | | `0x082` 电池预热触发、`0x398` 车型识别、BMS 四帧（`0x132` 电压电流 / `0x292` 电量 / `0x312` 温度 / `0x33A` 能耗）。**它们不参与本文任何一条结论**，故不列；见 `README.md:320`、`322`、`326-329` |

**方向列的 TX/RX 是"工具"视角**：TX＝工具发送、RX＝工具接收。同一 ID 在不同硬件代际下角色会互换——`0x399` 在 Legacy/HW3 上工具只读，在 HW4 上还要写 ISA 抑制位，这是 2.6 那段代码存在的理由。

**两处上游自身的命名分歧先记下来。**其一，flipper 的源码注释把选择位所在帧写作 `DAS_autopilotControl`（`fsd_can_ops.h:55`），同一仓库的 README 信号表写作 `UI_autopilotControl`（`README.md:315`）——同一帧（`0x3FD` / `0x3EE`），两种叫法。读源码以注释为准，检索上游文档用后者。其二，同一份 README 里 **`0x7FF` 与 `0x398` 两个不同的 ID 都被写作 `GTW_carConfig`**（`:319` 与 `:322`），但角色相反——前者 TX 供 GTW Config Replay 与档位覆盖，后者 RX 供车型识别。**同一信号名配两个 ID，这是本文见到最隐蔽的一处上游分歧**，检索时务必带 ID。

读本文需要的八个术语（后两个在后文反复出现，此处一次定死）：

| 术语 | 在本文与源码里的具体含义 |
| --- | --- |
| 仲裁 ID（arbitration ID） | CAN 帧的地址字段，代码里就是 `frame.id` |
| 数据长度码（DLC） | 帧的数据字节数，代码里 `frame.dlc`；多处用 `dlc < 5` / `< 8` 提前返回 |
| 多路复用（mux） | 一帧 ID 用 `data[0]` 低 3 位（`data[0] & 0x07`）区分用途，mux 0 / 1 / 2 各是一组语义 |
| 绝对位号 | 这一层没有 DBC 文件，"起始位 + 长度"已被手工展开成比特序号，如 `setBit(frame, 46, true)`（5.1） |
| 读-改-重发（read-modify-retransmit，RMR） | 三家工具的核心动作：收到帧 → 改若干比特 → 立即回发；因此发送方多为工具自己 |
| 滚动计数器（rolling counter） | 帧内逐帧递增的防伪字段；工具回发时必须跟着递增，否则车端判为无效帧 |
| 显性 / 隐性（dominant / recessive） | CAN 用 CAN_H 与 CAN_L 两根线之间的**电压差**表示逻辑（差分信号）；两处同为隐性时为隐性，任一处为显性即显性。靠这条"显性覆盖隐性"的规则（物理上是线与关系）完成多节点仲裁，优先级由 ID 决定 |
| 覆写（override） | 本文特指**固件跳过读取帧上的判定、改用自己的开关直接决定结果**（如 `force_fsd` 让判定函数不看该位、直接返回 true），不是"覆盖文件"，也不是改写源码 |

---

## 1. 在中国"开启"FSD：一条链路，三道门

三个仓库都实现了同一条路径：绕过车机界面的勾选状态，在总线层直接判定 FSD 已选中；三者也都在各自文档中声明，这条路径不改变车辆权益。能被固件动的那一段是清楚的，动不了的那一段也同样清楚——中间隔着三道彼此独立的门。本节先讲完整链路，再逐道门给出三份源码的位置与差异。

### 1.1 一条链路，三道门

**先说链路。**车机界面上 FSD 那个勾选框本身不改变车辆行为，它只是通过一帧 `UI_autopilotControl`（CAN ID `0x3FD`，即十进制 1021；Legacy 走 `0x3EE` = 1006，帧 ID 与信号名对照见 0.4）告诉车上的自动驾驶计算机"用户已经勾选"——这个状态落在**第 5 个数据字节（`data[4]`）里的第 6 位**（`can_helpers.h:21`、`fsd_can_ops.h:62`；`ev-open-can-tools` 读第 5 位、函数名 `isADSelectedInUI`）。

**位号怎么数，别搞混**：后文所有"`byte[4]` 的第 6 位""bit 38"说的是同一个位置——代码里的 `data[4]` 是第 5 个字节（`data` 从 0 数），它内部的第 6 位换算成整帧的比特序号就是 38（`4 × 8 + 6`）。

**一个 bit，两个名字，两种方向——这是全文最容易读错的一处。**`0x3FD` 上有两位必须分开看，`flipper` README 自己在 `:315` 一行里把它们并列写出：

| 位 | mux | 方向 | 含义 | 上游两处叫法 |
| --- | --- | --- | --- | --- |
| **bit 38**（`byte[4]` bit 6） | mux 0 | **读** | 那个勾选框的状态本身。上游称它 **TLSSC flag**（`SECURITY.md:28`）；本文一直叫它"选择位"——**同一个 bit** | `UI_fsdStopsControlEnabled`（`1-v-1` README 的 DBC 表）/ "TLSSC bit38"（flipper `:315`） |
| **bit 46** | mux 0 | **写** | 工具真正写下去的那一位：把"已选中"翻译成车端认的"使能" | "enable FSD"（`1-v-1` README）/ "FSD unlock — bit46/60"（flipper `:315`） |

所以完整的动作是**读 38、写 46**，不是"把 38 改成 1"。这也解释了 1.2 那个判定函数为什么存在：它读 38，handler 才决定要不要去写 46（2.4 的 `setBit(frame, 46, true)`）。**本文此前把 38 同时叫"选择位"和"TLSSC 标志"而没有点明是同一个位，是一处真实的表述缺陷，此处补正。**

固件要做的只有一件事：读 bit 38，决定后续帧要不要按"已选中"处理。三个仓库都把它抽成一个无状态判定函数（逐字对照见 1.2）。**所有"在中国开启 FSD"的固件侧手段，动作都只有一个：让这个函数不看帧、直接返回 `true`**；随后的注入、改比特、解除 nag 都在这条分支的下游。

**再说三道门**，它们决定这条路径能走多远：

1. **选择位**——在总线上，可被固件覆写（1.2）。
2. **权益**——订阅与购买状态在账号与服务端，不由总线帧表达（1.3）。
3. **地域围栏**——2026.8.6 起是神经网络层的区域检查，2026.14.x 起明写位于总线之外（1.4）。

第一道门能动；第三道门连绕的入口都没有；夹在中间的权益门，工具能做的只是把读者引到官方流程上去。

**一处预告，免得读到 1.4 时以为本文自相矛盾**：上面说的是"FSD 位本身"的处境——它只在勾选位那一帧里，覆写它绕不过权益与地域锁。但"让车进 AP"这一步并非只有这一条路：1.4 会讲到 `0x3C2` 转向柱开关帧这条经确认的 14.x 绕过（它改的是另一帧、另一个信号）。**本文对"能改哪一帧"与"能走到哪一步"始终分开讲，两者不可互相推导。**

![一条链路与三道门：勾选状态是一帧 CAN 报文里的一个比特](images/can-mod-teardown-2026/s00-fsd-chain.svg)

图 1｜一条链路与三道门：工具能动的只有第一道（选择位），权益与地域围栏都不在这一帧里。

### 1.2 第一道门：选择位——同一种形状，三种命名

第一道门就是 1.1 那条链路上的判定函数。三份源码的结构一致：**一个无状态函数，先查编译期宏，再查运行时标志，最后读帧上的位**——三段自上而下，命中任何一段就返回。

下表把这三段逐家摊开。**列的读法**：从"判定函数"列找到函数名，后面三列就是它的三段判据（编译期 / 运行时 / 帧上那位），最后两列是它落在哪儿（持久化）与哪条测试守着它。三家的函数名与读的那一位都不同，但三段形状一模一样。

| 仓库 | 判定函数 | 编译期宏 | 运行时标志 | 持久化位置 | 专项测试 |
| --- | --- | --- | --- | --- | --- |
| `tesla-open-can-mod` | `isFSDSelectedInUI`（`include/can_helpers.h:13-23`） | `FORCE_FSD`（`can_helpers.h:15`、`RP2040CAN.ino:32`） | `forceFSDRuntime`（`can_helpers.h:6`） | NVS `force_fsd`（`web_server.h:41`、`:51`、`:329`） | `test_native_force_fsd`、`test_native_helpers` |
| `flipper-tesla-fsd` | `tesla_is_fsd_selected`（`fsd_logic/fsd_can_ops.h:58-63`） | 无 | `state->force_fsd`、`state->china_mode`（`fsd_state.h:299`） | NVS `fsd/force`、`fsd/china`（`esp32/.firmware/prefs.cpp:27`、`:28`） | `test_fsd_core` |
| `ev-open-can-tools` | `isADSelectedInUI`（`include/can_helpers.h:76-81`） | `BYPASS_TLSSC_REQUIREMENT`（`can_helpers.h:6-12`） | `bypassTlsscRequirementRuntime`（`can_helpers.h:52`） | profile 脚本（`scripts/platformio_set_profile.py:18`） | `test_native_bypass_tlssc_requirement` |

以 `flipper-tesla-fsd` 的实现为样本，`fsd_logic/fsd_can_ops.h:55-63` 逐字如下：

```c
// UI "FSD selected" flag from DAS_autopilotControl byte 4 bit 6.
// force_fsd / china_mode bypass the UI check (china_mode is ESP32-only today;
// Flipper passes false).
static inline bool tesla_is_fsd_selected(const uint8_t* data, uint8_t dlc, bool force_fsd,
                                         bool china_mode) {
    if (force_fsd || china_mode) return true;
    if (dlc < 5) return false;
    return (data[4] >> 6) & 0x01u;
}
```

**七行读三段**：第 1 行把两个运行时开关合成一个判据——`force_fsd`（通用）或 `china_mode`（区域专用），任一为真就跳到 `return true`，**根本不往下读帧**；第 2 行是长度护栏，`dlc < 5` 就返回 false；第 3 行才是真正读帧，取 `data[4]` 的第 6 位。三家都是这个顺序，差别只在各自的前两段分别叫什么。

该函数原本在两个 handler 中各有一份副本。仓库在文件头记录了合并原因（`fsd_can_ops.h:7-10`，逐字，行首 `*` 为原文注释符）：

```c
 * alike, with no frame-type coupling. They were duplicated in both handlers;
 * keeping one copy removes the drift (e.g. the ESP32 had a china_mode branch in
 * its FSD-selected check that the Flipper copy lacked — folded in here as a
 * parameter, so each platform keeps its own behavior while sharing the logic).
```

**形状相同不等于判的是同一件事。**两处具体差异——这是本节唯一要读者记住的：

**其一，读的位不同。** `tesla-open-can-mod` 与 `flipper-tesla-fsd` 取第 6 位，`ev-open-can-tools` 取第 5 位（`can_helpers.h:80`），且其函数名为 `isADSelectedInUI`，**判定的并非同一个信号**。本文不推断两者的信号映射——所以读 ev-open 代码时不要拿本文的位号去对照。

**其二，只有 `flipper-tesla-fsd` 带有区域相关的独立开关。** `fsd_state.h:299` 的字段注释为 `bypass FSD UI selection check for China vehicles`；该开关只在 ESP32 分支存在，Flipper 分支传 `false`（`fsd_logic/fsd_handler.c:94`）。

这一平台差异由仓库自身记录于 `fsd_can_ops.h:7-10`，并由 `test/test_fsd_core.c:1274` 用一条断言覆盖了 Flipper 包装层到不了的路径。网页控制台上，`force_fsd` 与 `china_mode` 是两个独立开关（`esp32/.firmware/web_dashboard.cpp:494-499`）。

### 1.3 第二道门：权益在总线之外

固件改写的只是自身的判定输入，不产生车辆权益。**前三个仓库都用明确的句子说了这件事，第四个没有**——逐条摆出来：

| 仓库 | 原文 | 出处 | 说的是权益吗 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | Any attempt to bypass the purchase or subscription requirement for Full Self-Driving (FSD) will result in a permanent ban from Tesla services. | `README.md:10` | 是（并给出后果） |
| `tesla-open-can-mod` | **You must have an active FSD package on the vehicle** — either purchased or subscribed. This board enables the FSD functionality on the CAN bus level, but the vehicle still needs a valid FSD entitlement from Tesla. | `README.md:27` | 是（并区分了 CAN 层与权益） |
| `flipper-tesla-fsd` | A real FSD purchase or subscription is still required, and it does not unlock FSD on Tesla firmware 2026.14 and newer. | `.catalog/README.md:7` | 是 |
| `ev-open-can-tools` | This project is **not plug-and-play**. CAN connects vehicle computers, including safety-critical systems. | `README.md:9` | **否**——它讲的是安全与合规风险，不是权益 |

**所以"三份文档口径一致"这句话要打个折**：前两家直说了权益与 CAN 层是两回事，第三家（ev-open）通篇没提权益，只提醒 CAN 连着安全攸关的系统。**"没说"不等于"不成立"**——本文的判断来自前两家的明文与 1.4 引的 `SECURITY.md`（主权益路径走以太网），不是来自 ev-open 的沉默。

信号层面的区分见 flipper 侧的字典：`enhauto-re/CAN_DICTIONARY.md:73` 与 `:74` 把 `UI_enableFullSelfDriving`（使能）与 `UI_hasFullSelfDriving`（权益校验）列为两个不同信号。第 1.2 节的覆写作用于前者，不及于后者。

`tesla-open-can-mod` 另有一份面向受限地区的账户操作指南 `guides/FSD_SUBSCRIPTION_GUIDE.md`，其自带免责声明位于 `:5`。本文记录该文件的存在与行号，不转述其步骤。

**这道门有两种失败方式，症状一样、成因不同——不分开就会给出错误的补救建议。**flipper 的 issue `#119`（China HW4 / 2026.8.3.6 / 已购 FSD 但从未接合）里，项目作者本人给出了这个区分（社区回报，本文未 clone 核验该 issue 页面，仅据检索快照）：

| | 被封（banned） | 从未授予（never granted） |
| --- | --- | --- |
| 服务端发生了什么 | 权益被**撤销**——检测到 CAN 设备后远程下发 | 权益**从未下发**给这个地区/这辆车 |
| 症状 | 曾经能用，后来不能 | 装上工具也从来就没能用过 |
| 能否用总线绕过 | 不能 | 不能 |

作者的判词是 **"Banned = revoked; this = never granted."** 并给出该次的具体机制：在 China HW4 上，**自动驾驶档位由车端从服务端的权益状态重新推导出来**（`0x7FF`），所以往总线上注入 SELF_DRIVING 档位**零效果**（据其引用的 issue `#117`）。issue `#122` 被指向为"合并后的状态说明"。

**这条与 1.4 引的 `SECURITY.md:30` 是同一件事的两次独立陈述**（一个说"主权益路径走以太网"，一个说"档位由服务端状态重新推导、注入无效"），而两者都出自同一个仓库的作者之手。**它把 1.5 的"够不着"从一个论断变成了一个有机制解释的结论：不是缺一帧，是缺一份服务端下发的状态。**

> **一处订正**：本文此前把"档位注入无效"只记在 `SECURITY.md:30` 一处。issue `#119` / `#117` 是上游作者本人在 2026 年夏给出的同向表述，且明确限定在 **China HW4** 上——**与本文这台车同硬件代际、同地区**，尽管版本不同（该例为 2026.8.3.6，本车 2026.2.11）。这一条本文标为社区回报，因为它来自 issue 而非钉死的文件行号。

### 1.4 第三道门：地域围栏与版本分界

**先说这道门为什么存在——这不是技术问题，是监管问题。**（以下三条全部为媒体报道，非一手，本文标为**未核实**；列出来是因为它们决定了这道门的性质，而不在于本文依赖它们。）

- 中国的 FSD 试点于 2025 年 3 月启动，随后被工信部与市场监管总局叫停（新规要求先进驾驶辅助的重大技术参数变更须事先批准、须报事故、缺陷须报召回计划）。
- 截至 2026-05-21，完整版 FSD 在中国**仍未获批**；已进入中国的是阉割版，来源明确表示"不是完整版、不是 FSD V14"。
- 2026-04 的清理行动中，Tesla 在**中国单独就查获逾 10 万辆**装有此类改装的车，涉事设备在亚洲售价 $700–$2,000、欧洲约 €500；车机提示原文为 "Your vehicle has detected an unauthorized third-party device. As a precaution, some driver assistance functions have been disabled for safety reasons"。时间点与 FSD v14.3 的推送重合。

**所以本文这台车面对的不是一个"版本对不对"的问题，而是"这道门什么时候开"的问题。**后文 9 节花整节论证"2026.2.11 该编哪个宏"不可判定——那个问题在这一层其实让位于一个更前置、也本文无法回答的问题。**这也是本文只写"仓库的指南到此为止"而不给操作建议的原因之一。**

这一道门没有源码可查，只有文档自述。`esp32/README.md:422` 先声明了整张兼容性表的性质：

> This table is informational from field reports/upstream notes. The ESP32 code itself does not hardcode firmware-version checks.

据此，下表三行的证据等级为社区回报，非一手。原文如下（引文按证据需要保留，`:429` 中段一处操作性应对以 `[…]` 略去）：

| 版本 | Notes（原文） | 行号 |
| --- | --- | --- |
| 2026.8.6 | HW4 injection path broken on this build — use Force HW3. Region lock applies too (next row) | `:428` |
| 2026.8.6+ | Region lock — FSD neural net refuses to run in some regions. […] | `:429` |
| 2026.14.x and newer | FSD unlock blocked by the activation preflight and an off-CAN region lock; nag killer / TLSSC still work | `:430` |

`:430` 的 `off-CAN region lock` 是本节的关键约束：在该版本区间，地域锁不由总线帧表达，第 1.2 节的覆写路径对它不生效。`.catalog/README.md:7` 的 `it does not unlock FSD on Tesla firmware 2026.14 and newer` 与之一致，两处独立表述互相印证。

上游为这条分界线准备的不是"解锁"，而是两个绕开手段——它们正好划出了"固件还能做什么"的上界：

- **AP-First (14.x)**（`README.md:123`）：把 `0x3FD` 的注入推迟到 AP 已被接合之后，README 标注它 **"Required for Tesla firmware 2026.14.x"**。它改的是注入时机，不改地域锁本身。
- **GTW Config Replay**（`README.md:124`，v2.15 起由 "Ban Shield" 改名）：监视 `0x7FF` `GTW_carConfig`，在网关发出被改动的帧时实时重放事先学到的健康广播。README 自陈的边界写得很清楚——**只作用在 CAN 广播层，不撤销 NVRAM 或服务端的封禁状态，也不阻止封禁**。

还有第三个手段必须单列，因为它改变了"14.x 完全解不了"这句话的边界。`ROADMAP.md:12`（钉在 `ffbb24e`）把 **`0x3C2` ScrollPress AP** 记作 **"first confirmed 2026.14.x bypass"**（PR #82）：它不碰 FSD 的任何一位，而是往 `VCLEFT_switchStatus`（`0x3C2`）的 mux=1 帧里**注入一串模拟滚动轮的时序**——按住右滚轮 `swcRightPressed`（bits 12-13）约 250 ms → 上滚 `swcRightScrollTicks`（bits 24-29）约 150 ms → 再按住 → 再上滚，**触发时机是 `DAS_autopilotState` 由 0 跳到 1 的瞬间**（`README.md:133`）。让车机认为人真的拨了转向柱。

`README.md:133` 同一格还记了两条本文此前没有的信息：**它是 @JakNo 在 Highland HW4 / 2026.14.2 上发现并台架验证的（issue `#43`，时序实现 PR `#82`）**；以及 **"no `0x3FD` touch"**——它压根不碰 FSD 位，这正是它能绕开 preflight 的原因。

> **一处订正**：本文上一版把这串时序标为 `ROADMAP.md:107-110`，是错的。本文已于 2026-10-01 复核 `ffbb24e` 检出——`ROADMAP.md:107-110` 是座椅加热与 Track Mode 的路线图条目；**这串时序的唯一出处是 `README.md:133`**，ROADMAP 只在 `:12` 记了一行标签。

**这条我按其原样记录，并把三条限定一起摆出来**，因为它们比"它能用"更重要：

1. **HW4-only，且只在 Service mode 下有效**（`README.md:133`）。
2. **它在 HW3 上有安全争议**：一次 HW3 / 2026.14.6 的负面测试报告了**紧急刹车**，一度导致该功能在 v2.15 里对 HW3 关闭；ROADMAP `:40` 说这次负面结果"可能"源于 `0x399`/`0x39B` DAS 读回失败（已在 #92 修复），**截至 `ffbb24e` 仍列为待办、要求用当前代码重测后再决定是否在 HW3 上开放**。我没有任何条件判断这个重测的结论，本文也不建议在 HW3 上试它。
3. **它绕开的是地域锁对"注入"这一环的限制，不是权益**——上车仍需有效资格（1.3）。

另有一项被上游自己列为"边缘收益"的提案：用 DNS 伪装 Tesla 域名以保留地图/多媒体、同时降低封禁风险。`ROADMAP.md:42` 明确写着由于遥测路径的**双向 TLS 证书锁定**，这对防封禁只是边际改善，主要价值在体验——**这也从侧面说明权益校验那条路（1.3 第二道门）是封不掉的。**

**第三条边界比上面两条更硬，来自另一份一手文件。** `SECURITY.md:19-32`（钉在 `ffbb24e`）把 VIN 封禁的机制拆到了位一级，并逐条标明证据来源（"community research, April 2026"，即社区研究、引用 issue `#18`）：

| 机制 | 位置 | 状态 |
| --- | --- | --- |
| `GTW_autopilot` 档位从 SELF_DRIVING(3) 降为 ENHANCED(2) | `0x7FF` mux=2 byte[5] bits 4:2 | 社区研究 |
| TLSSC 标志位被独立清零 | `0x3FD` mux=0 byte[4] bit 6（bit 38）；同字节 bit 7 是 Continue on Green，不是 TLSSC | 社区研究 |
| FSD 挂起状态置为 SUSPENDED | `0x259 APP_fsdSuspendState` | 社区研究 |
| **AP ECU 的主权益路径似乎是 Ethernet** | —— | 社区研究 |

`SECURITY.md:30` 那句是这一整节里最要紧的判断：**单靠影子注入 `0x7FF` 并不能解除封禁，因为主权益路径走的是以太网**——这正好从反面印证了第 1 节第二道门"权益不在总线上"。**这半句推翻了 GTW Config Replay 的全部价值**，也是 1.5 里"够不着"必须限定范围的原因。

同一行的下半句给出一个**必须成对使用**的组合，效果比任何单开关都强：**TLSSC Restore（写 `0x331`）+ `0x3FD` mux0 bit 38** 由 `@RoyRakete` 在被封的 HW3 / 2026.2.6 上确认能可靠重新让 AP/TACC 接合（issue `#18` 楼中楼）。注意 bit 38 就是 1.1 那张表里的**读**位——它在这里被当作"写回勾选状态"用，`SECURITY.md` 原话是这一对**"together"** 才可靠，任一单独开在部分封禁固件上不可靠。`SECURITY.md:31-32` 再补两条限定：TLSSC Restore 单独只能部分恢复停车标志/红绿灯、**不恢复完整 FSD**；且 Intel HW3 的封禁执行比 Palladium/HW4 更激进。

**从这一段能读出工具作者的方法论**：他们没有声称"解开封禁"，只声称"这一对开关能让 AP/TACC 接合"。**把可验证的窄结论与不可验证的宽结论分开写**——本文全文沿用这个纪律，这也是 9 节敢于整节写"不可判定"的原因。

`SECURITY.md:23-24` 另记了一条操作面的事实：封禁**跨账号转移、FSD 重新订阅、乃至 Service 端重装软件都持续存在**，拔 SIM 卡只能降低、不能消除被检测的风险。这解释了为什么第 14 节把 VIN 封禁列为"项目方风险自述"里最高风险的一条。

### 1.5 本节结论

三道门的可动性各不相同。第一道门在总线上，三仓库的覆写能力高度同形，差异集中在是否提供区域相关的独立开关、编译期与运行时的取舍、以及判定所读的位；后两道门都不在总线上——覆写产生不了权益（1.3，另两家明文、ev-open 未表态），2026.14.x 起也够不着地域锁，而**只有 `flipper-tesla-fsd` 明确记出了这条版本分界**。

**"够不着"要限定范围，否则会说过头。** 够不着的地域锁与权益，其判定都在车端以太网与服务端，CAN 帧改不动；但"注入"这一环在 14.x 上并非完全封死——`ROADMAP.md:12` 记录的 `0x3C2` ScrollPress AP 是首个经确认的 14.x 绕过（PR #82），它改的是转向柱开关帧而不是 FSD 位，代价与安全争议见 1.4。所以更准确的说法是：**FSD 位本身在 14.x 起无法用总线覆写点亮，但进 AP 的那一步在特定硬件与条件下另有其法。** 上车资格仍是前提（1.3）。

所以"开启 FSD"里能被工具推进的，只有从勾选位到注入之间的那一段。第 5、6 节把这一组对照放进更大的一致性与分化维度里看。

---

# 第二部分 · 逐仓库解剖

三份源码用同一套方法读：**文件地图 → 启动 / 运行 / 业务三层序列 → 横切面（位操作、校验和、驱动）→ 测试与实测**。三节的小节编号刻意同构，方便横向对照；每节末尾的小节编号若与其他节不同，是因为该仓在这条骨架上确有一块别家没有的内容（如 3.5 的 nag killer、3.7 的 bit47 改口、4.6 的两处真故障），我按事实标注而非强行拉齐。

| | 2 `tesla-open-can-mod` | 3 `flipper-tesla-fsd` | 4 `ev-open-can-tools` |
| --- | --- | --- | --- |
| 地图 | 2.1 | 3.1 | 4.1 |
| 启动 / 运行 / 业务 | 2.2 / 2.3 / 2.4 | 3.2 / 3.3 / 3.4 | 4.2 / 4.3 / 4.4 |
| 横切面 | 2.5 / 2.6 / 2.7 | 3.6 | 4.5 |
| 门控（本仓特有或前置） | 2.9 | 3.4 | 4.5 |
| 测试 | 2.8 | **3.8** | **4.7** |
| 独有内容 | — | 3.5 nag killer、3.7 bit47 改口 | 4.6 两处真故障 |

**表里两个约定**：3.4 与 4.5 各出现两次不是笔误——3.4 既是"业务层"也是 flipper 的四道门所在，4.5 既是"横切面"也是 ev-open 发送许可所在；测试行的加粗表示该节是独立小节（3.8 与 4.7 各有引言与结论，2.8 没有）。

每节开头都有一句钉住 commit 的说明；**行号只在那个 commit 上成立。**

## 2. `tesla-open-can-mod`：最干净的教学样本

> **本节行号与文件行数全部钉在 `815e000` 的检出上**（无 tag、无 release，最后一次 push 停在 2026-04-02，见第 0 节表的第一行）。

三个仓库中，该仓库的抽象分层最清晰、规模最小，适合作为第一个解剖对象。本节要回答的是：**一段"收到帧、改几个比特、发回去"的逻辑，在源码里究竟落在哪几个文件、哪几层。**

**本节是全文最长的一节，也是后两节的基线**：2.5/2.6/2.7 三个横切面在这里逐字展开，3.6 与 4.5 只讲各自相对它的差量。**只想看原理跳 1.1 与第 5、6 节；只想看这台车怎么接，看 11–14 节。**通读本节的顺序：2.1（地图）→ 2.2/2.3/2.4（三层序列）→ 2.5/2.7/2.8（横切面基线）→ 2.8/2.9（测试与门控）；2.6 是插在其中的一个完整案例，可独立阅读。

### 2.1 地图：七个文件

去掉许可证与图片，真正有信息量的文件是这七个（行数为 `815e000` 检出实测）：

| 文件 | 行数 | 承担什么 |
| --- | --- | --- |
| `RP2040CAN.ino` | 70 | Arduino 入口：选板子、选车型、转发到 `app.h` |
| `src/main.cpp` | 47 | PlatformIO 入口，与 `.ino` 等价 |
| `include/app.h` | 87 | 第一、二层序列：`appSetup()` 与 `appLoop()` |
| `include/handlers.h` | 301 | 第三层序列：三个 handler 的 `handleMessage()` |
| `include/can_helpers.h` | 46 | 位操作原语与 UI 选择位判定 |
| `include/can_frame_types.h` | 11 | 可移植的 `CanFrame` 结构 |
| `include/drivers/*.h` | 5 个文件 | 四个驱动实现 + 一个抽象接口 |

分工即设计：车辆逻辑集中在 `handlers.h` 与 `app.h`，入口文件只做选型转发。换板子改 `platformio.ini`，换车型改一行宏，业务逻辑不动。

![三层序列的位置与分工](images/can-mod-teardown-2026/s01-three-layers.svg)

图 2｜三层序列各自住在哪个文件、由谁触发。

### 2.2 第一层序列：启动

`include/app.h:37-60` 逐字如下（`appSetup` 的主体；`app.h:61-67` 是条件编译的 WiFi 初始化块，与本节论点无关）：

```cpp
template <typename Driver>
static void appSetup(std::unique_ptr<Driver> drv, const char *readyMsg)
{
    appHandler = std::make_unique<SelectedHandler>();
    delay(1500);
    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && millis() - t0 < 1000)
    {
    }

    appDriver = std::move(drv);
    if (!appDriver->init())
    {
        Serial.println("CAN init failed");
    }

    appDriver->setFilters(appHandler->filterIds(), appHandler->filterIdCount());
    if constexpr (Driver::kSupportsISR)
    {
        appDriver->enableInterrupt(canISR);
    }

    Serial.println(readyMsg);
```

顺序是固定的，且顺序本身有含义。

handler 必须先于驱动建立，因为 `setFilters()` 一行要从 handler 取过滤器清单，"听哪些 ID"的决定权因此在业务层；驱动不知道自己在听什么，只负责执行。过滤器装在硬件层：控制器只把匹配的 ID 上报 CPU，其余帧在芯片内即被丢弃。车身总线每秒数百帧，全部进中断会淹没主循环。

末句 `if constexpr` 是 C++17 的编译期分支，条件不成立的分支不被实例化；不支持中断的驱动，连 `frameReady` 检查的机器码都不会生成。

`frameReady` 的初值是一个容易看漏的细节，`include/app.h:30`：

```cpp
static volatile bool frameReady = true;
```

初值为 `true`，因此第一圈循环无论有无中断都会进入一次。这使"等第一帧"不产生等待，代价是第一圈可能空转一次 `while(read)`。

### 2.3 第二层序列：运行

`include/app.h:69-87` 逐字如下：

```cpp
template <typename Driver>
static void appLoop()
{
    if constexpr (Driver::kSupportsISR)
    {
        if (!frameReady)
            return;
        frameReady = false;
    }

    CanFrame frame;
    while (appDriver->read(frame))
    {
        digitalWrite(PIN_LED, LOW);
        appHandler->frameCount++;
        appHandler->handleMessage(frame, *appDriver);
    }
    digitalWrite(PIN_LED, HIGH);
}
```

两处设计需要说明。

`while(read)` 采用排空模式：中断只作为"有活了"的信号，真正的读取由主循环连续调用 `read()` 直至队列为空。这样 ISR 只做一件事，置位一个布尔，耗时极短。

`volatile` 不可省略：`frameReady` 由 ISR 写、主循环读，没有它编译器可能将其缓存于寄存器，主循环将看不到中断的写入。

### 2.4 第三层序列：业务与多路复用

`include/handlers.h` 是实现所在。三个 handler 结构高度一致，均继承 `CarManagerBase`（`handlers.h:17-29`）：

```cpp
struct CarManagerBase
{
    Shared<int> speedProfile{1};
    Shared<bool> FSDEnabled{false};
    Shared<bool> enablePrint{true};
    Shared<uint32_t> frameCount{0};
    Shared<uint32_t> framesSent{0};
    Shared<int> speedOffset{0};
    virtual void handleMessage(CanFrame &frame, CanDriver &driver) = 0;
    virtual const uint32_t *filterIds() const = 0;
    virtual uint8_t filterIdCount() const = 0;
    virtual ~CarManagerBase() = default;
};
```

`Shared<T>` 定义于 `include/shared_types.h`：设备侧是 `std::atomic<T>`，原生构建下退化为裸类型。这一层封装解释了为何同一组成员能在中断与主循环之间共享而无需额外加锁。

`filterIds()` 与 `handleMessage()` 是一对：同一个类既声明听什么，又实现听到了怎么办。过滤器与处理逻辑因此在代码上强制对齐，改一处不会漏另一处。

三个派生类监听的 ID 各不同（HW4 的 921 分支受编译期宏控制，见 2.6）：

| Handler | 行范围 | 监听 ID |
| --- | --- | --- |
| `LegacyHandler` | `handlers.h:31-95` | 69、1006（`handlers.h:35`） |
| `HW3Handler` | `handlers.h:97-192` | 1016、1021（`handlers.h:101`） |
| `HW4Handler` | `handlers.h:194-301` | 921、1016、1021（`handlers.h:199`；未定义宏时为 1016、1021，`:204`） |

选型发生在编译期，`include/app.h:17-25`：

```cpp
#if defined(HW4)
using SelectedHandler = HW4Handler;
#elif defined(HW3)
using SelectedHandler = HW3Handler;
#elif defined(LEGACY)
using SelectedHandler = LegacyHandler;
#else
#error "Define HW4, HW3 or LEGACY in build_flags"
#endif
```

`using SelectedHandler = ...` 是类型别名而非运行时变量：选型在编译期完成，运行时不存在"判断当前是哪款车"的分支，代价是每种车配每种板子都要单独编译。未定义任一宏时由 `include/app.h:24` 的 `#error` 终止构建，而非静默退回默认车型——这条兜底在第 13.3 节会撞上一次。

多路复用：一条 ID 三组语义。以 `HW3Handler` 为样本（`handlers.h:129-173`），ID 1021 上的处理按 `data[0]` 低 3 位分成三支：

```cpp
if (frame.id == 1021)
{
    if (frame.dlc < 8)
        return;
    auto index = readMuxID(frame);
    if (index == 0)
        FSDEnabled = isFSDSelectedInUI(frame);
    if (index == 0 && FSDEnabled)
    {
        speedOffset = std::max(std::min(((uint8_t)((frame.data[3] >> 1) & 0x3F) - 30) * 5, 100), 0);
        // …（速度档 switch，handlers.h:140-153）
        setBit(frame, 46, true);
        setSpeedProfileV12V13(frame, speedProfile);
        framesSent++;
        driver.send(frame);
    }
    if (index == 1)
    {
        setBit(frame, 19, false);
        framesSent++;
        driver.send(frame);
    }
    if (index == 2 && FSDEnabled)
    {
        frame.data[0] &= ~(0b11000000);
        frame.data[1] &= ~(0b00111111);
        frame.data[0] |= (speedOffset & 0x03) << 6;
        frame.data[1] |= (speedOffset >> 2);
        framesSent++;
        driver.send(frame);
    }
}
```

（引文省略 `handlers.h:140-153` 的速度档 `switch`，其余逐字对应 `handlers.h:129-173`；其后的 `#ifndef NATIVE_BUILD` 串口打印块位于 `:174-190`，不属该范围。）

mux 0 刷新状态，mux 2 应用缓存，mux 1 完全不理会缓存。mux 2 那支带 `&& FSDEnabled`，用 mux 0 存下的值；mux 1 那支根本没引用 `FSDEnabled`，收到 mux 1 帧即改比特回发。

![状态缓存的时序耦合](images/can-mod-teardown-2026/s02-state-latch.svg)

图 3｜mux 0 写入状态、mux 2 复用状态，mux 1 两者都不做。

**这个耦合曾是个 bug，值得多看一眼。**mux 2 的帧自己带一个 `data[4]`，早期实现若在每个分支都重读 UI 位，这帧会把 mux 0 刚存下的状态覆盖掉——测试注释里叫它 "FSD shadowing fix"（`test/test_native_hw3/test_hw3_handler.cpp:55`，HW4 有孪生测试在 `test_hw4_handler.cpp:62`），说的就是变量遮蔽。修复方式是让读取只发生在 mux 0，并用一条回归测试锁死"mux 2 帧的 `data[4]` 为 0 也不会把 `FSDEnabled` 冲掉"。

**修复本身不是重点，流程才是**：发现隐式耦合、加测试锁死、把修复意图写进测试名。mux 1 分支的断言见 2.9。

三个 handler 的 mux 1 分支写法相同，但三者的 mux 2 不一致：HW3 检查缓存（`handlers.h:165`），HW4 不检查（`handlers.h:276` 为光秃秃的 `if (index == 2)`），Legacy 没有 mux 2 这一支。

### 2.5 横切面一：位操作与读改写纪律

`include/can_helpers.h` 全文 46 行，是整个项目的词汇表，`can_helpers.h:5-46` 逐字如下：

```cpp
inline Shared<bool> forceFSDRuntime{false};

inline uint8_t readMuxID(const CanFrame &frame)
{
    return frame.data[0] & 0x07;
}

inline bool isFSDSelectedInUI(const CanFrame &frame)
{
#if defined(FORCE_FSD)
    (void)frame;
    return true;
#else
    if (forceFSDRuntime)
        return true;
    return (frame.data[4] >> 6) & 0x01;
#endif
}

inline void setSpeedProfileV12V13(CanFrame &frame, int profile)
{
    frame.data[6] &= ~0x06;
    frame.data[6] |= (profile << 1);
}

inline void setBit(CanFrame &frame, int bit, bool value)
{
    if (bit < 0 || bit >= 64)
        return; // bounds guard: CanFrame.data is 8 bytes
    int byteIndex = bit / 8;
    int bitIndex = bit % 8;
    uint8_t mask = static_cast<uint8_t>(1U << bitIndex);
    if (value)
    {
        frame.data[byteIndex] |= mask;
    }
    else
    {
        frame.data[byteIndex] &= static_cast<uint8_t>(~mask);
    }
}
```

即全文除 `#pragma once` 与两条 `#include` 之外的全部内容。

`isFSDSelectedInUI` 与 1.2 节对照表里的三份实现是同一处结构：编译期宏、运行时标志、读帧上的位，三段自上而下。本仓库把它放在通用工具头中，因此 HW3、HW4、Legacy 三个 handler 共用同一份判定。

`setSpeedProfileV12V13` 是读改写的纪律示范。掩码 `~0x06` 保留字节里其他位，只动该动的两比特。误伤相邻字段是这类工具最常见的 bug，掩码写法从结构上堵死了它。

`setBit` 用绝对位号寻址：`bit / 8` 定位字节、`bit % 8` 定位位内偏移，并在 `:33-34` 加了越界护栏。这解释了代码中 19、46、47、59、60 这些魔数的来历——DBC 的"起始位 + 长度"语义在这一层已被手工展开成绝对位号（5.1）。

### 2.6 横切面二：校验和，HW4 独有的一支

`HW4Handler` 的 `921` 分支是其他 handler 没有的（`handlers.h:213-227`），逐字如下：

```cpp
#if defined(ISA_SPEED_CHIME_SUPPRESS)
        if (frame.id == 921)
        {
            if (frame.dlc < 8)
                return;
            frame.data[1] |= 0x20;
            uint8_t sum = 0;
            for (int i = 0; i < 7; i++)
                sum += frame.data[i];
            sum += (921 & 0xFF) + (921 >> 8);
            frame.data[7] = sum & 0xFF;
            framesSent++;
            driver.send(frame);
            return;
        }
#endif
```

三个细节。

改了前 7 字节就必须重算第 8 字节，否则接收方校验失败、整帧被丢；丢帧在总线上表现成"偶发不生效"，排查代价极高。校验和里还掺了 ID 的高低字节，使校验覆盖"这是哪条报文"，防止帧被换到别的 ID 上仍能通过。

末尾的 `return` 提前退出，改完这帧就不再走后面的 FSD 逻辑。测试 `test_hw4_isa_suppress_returns_early_no_further_processing`（`test_hw4_handler.cpp:224`）断言的正是"只有一次发送"。

开关本身是编译期宏，三处配置点全部默认关闭：

| 配置点 | 行号 | 默认状态 |
| --- | --- | --- |
| 草图中的可选项 | `RP2040CAN.ino:30` | 已注释 |
| HW4 过滤器清单 | `handlers.h:198-201` | 未定义宏时只听 1016、1021（`:204`） |
| `platformio.ini` 各硬件 env | `:8`、`:16`、`:24`、`:30` | 均未定义 |

只有原生测试环境把它打开（`platformio.ini:34`、`:40`）。按仓库自带配置构建出的任何硬件固件都不含这条 921 路径；要在车上启用，须自行在 `.ino` 中取消注释，由 `scripts/platformio_sync_ino_defines.py` 同步进 `build_flags`（README `:246-253` 记录了这一机制）。同文件 `handlers.h:263` 的 `EMERGENCY_VEHICLE_DETECTION` 结构相同，默认同样注释于 `RP2040CAN.ino:31`。

### 2.7 横切面三：驱动抽象与过滤器掩码

`include/drivers/can_driver.h` 全文 13 行，接口就是 `init` / `setFilters` / `enableInterrupt` / `read` / `send` 五个纯虚方法加一个虚析构（`can_driver.h:7-12`）。

四个实现各带一个 `kSupportsISR` 编译期常量：`MCP2515Driver`（SPI 外置，`mcp2515_driver.h:12`）为 `true`，其余三个均为 `false`，即只有 SPI 外置控制器用中断，三个内置控制器全部走轮询。SAME51 的理由写在源码里，`same51_driver.h:41-43` 逐字如下：

```cpp
// SAME51 uses register reads (no SPI overhead) and an 8-deep HW FIFO.
// The library's onReceive() consumes frames inside the ISR, which is
// incompatible with our "flag + drain" pattern. Keep polling with HW filters.
```

即轮询是权衡后的选择而非省事：库的 ISR 回调会把帧在中断里消费掉，与"置位 + 排空"模式不兼容。TWAI 的 `kSupportsISR = false`（`twai_driver.h:10`）没有配套注释，此处不代其推断理由。

`TWAIDriver` 还实现了自恢复（`twai_driver.h:60-99`）：`read()` 与 `send()` 的失败路径都会检查 `isBusOff()` 并调用 `recoverWithCooldown()`（`:71-72`、`:98-99`）。总线错误累积到阈值会进 bus-off，不主动恢复就永久失联；四个驱动中只有它做了这件事，另有 `tryRecover()`（`:130`）处理更严重的场景。

过滤器掩码的数学。 MCP2515 有 6 个独立精确匹配槽位，TWAI 与 SAME51 只有一个组合滤波器，单滤波器要接受多个 ID 就得算掩码（`twai_driver.h:32-46`）：

```cpp
uint32_t differ = 0;
for (uint8_t i = 1; i < count; i++)
{
    differ |= ids[0] ^ ids[i];
}

uint32_t base = ids[0] & ~differ;
f_config_.acceptance_code = base << 21;
f_config_.acceptance_mask = (differ << 21) | 0x001FFFFF;
f_config_.single_filter = true;
```

逻辑是任意两个 ID 异或，不同的位就是"不关心"位；并起来当掩码，剩下的位必须匹配第一个 ID。副作用是掩码越宽、接受的 ID 越多——Legacy 的两个 ID（69 和 1006）差得远，掩码会放过一堆无关 ID，测试文件自己承认（`test_native_twai/test_twai_filter.cpp:135`：`// --- Legacy: wide gap means wider mask (false positives expected) ---`）。

**这不是疏忽，是单滤波器的固有代价**：正确性由软件保证，`handleMessage()` 每支都先 `if (frame.id == ...)` 精确比对。硬件过滤只负责省电省中断，不负责语义正确。

### 2.8 测试：99 条断言，107 次执行

七个测试套件，全部为原生构建，不碰硬件。逐个 `RUN_TEST` 静态计数的结果：

| 测试组 | 断言数 | 覆盖对象 |
| --- | --- | --- |
| `test_native_helpers` | 21 | 位操作原语与运行时标志 |
| `test_native_legacy` | 12 | `LegacyHandler` |
| `test_native_hw3` | 13 | `HW3Handler` |
| `test_native_hw4` | 22 | `HW4Handler`（含 ISA 校验和） |
| `test_native_twai` | 17 | TWAI 过滤器掩码数学 |
| `test_native_log_buffer` | 8 | 环形日志缓冲 |
| `test_native_force_fsd` | 6 | `FORCE_FSD` 下不依赖 UI 勾选 |
| **唯一断言合计** | **99** | |

**99 与 107 的差是重复执行，不是多出来的断言。**按 env 分配：`[env:native]` 吸收前六组（`platformio.ini:35-36` 的 `test_ignore` 排除 `force_fsd`）得 93 次，`[env:native_force_fsd]` 得 6 次，`[env:native_log_buffer]` 再跑一次 `log_buffer` 得 8 次——**那 8 条被算了两遍**（在 `[env:native]` 里已经跑过）。合计 8 次套件运行、107 次执行，2026-10-01 实测 `107/107` 通过。

`platformio.ini:32-36` 把它们跑在主机上：`platform = native`、`build_flags = -std=c++17 -DNATIVE_BUILD ...`、`test_filter = test_native_*`。主机编译器由 README `:239` 指定为 MinGW-w64 GCC。

`-DNATIVE_BUILD` 是关键开关：`include/app.h:9-11` 与 `include/handlers.h:11-13` 都用它隔离 Arduino 头文件。**同一份业务代码既能编译进 MCU，也能编译进主机当纯逻辑跑，这是整个测试体系成立的前提。**测试靠 `MockDriver` 捕获发送：`send()` 不上总线，只 `sent.push_back(frame)`，于是断言发送次数与帧内容成为可能。

### 2.9 门控：有什么，没什么

把仓库中所有"防止乱发帧"的机制列一遍：

| 门控 | 位置 | 性质 |
| --- | --- | --- |
| 编译期选型失败即中止 | `include/app.h:24` `#error` | 配错无法编译 |
| 硬件过滤器 | `include/app.h:54` | 无关帧不进 CPU |
| UI 勾选位作为开关 | `handlers.h:64`、`:136`、`:259` | 仅控制 mux 0 分支 |
| HW3 的 mux 2 受缓存约束 | `handlers.h:165` | HW4 的 mux 2 不受（`:276`） |
| 读改写掩码与越界护栏 | `can_helpers.h:31-34` | 不误伤相邻字段，不越界写 |
| ISA / 紧急车辆检测能力 | `RP2040CAN.ino:30-31` | 编译期宏，默认注释 |

grep 确认以下机制在该仓库中不存在：

- 没有滚动计数器（`grep rolling|alive|counter` 无源码命中）
- 没有统一的发送许可函数（无 `canSend` / `transmitAllowed` / `fsd_can_transmit`）
- 没有硬件只读模式（无 `ListenOnly`）
- 没有 OTA 进行中检测
- 没有 DBC 文件，也没有任何代码读取 DBC

把安全约束放在编译期与默认值上而非运行时，是它的取舍：好处是零开销、配错根本编译不过，坏处是运行时没有任何东西能拦住一次"配置正确但时机不对"的发送。第 5、6 节会看到另外两个仓库各有一道它没有的闸。

mux 1 分支不看 `FSDEnabled` 缓存，三个 handler 都是如此——那一支的发送条件只有"收到 mux 1 帧"一条。源码未说明是否有意为之，测试断言了这个行为（`test_hw3_handler.cpp:137-143`），本文只记录不推断意图。

## 3. `flipper-tesla-fsd`：整个生态的重心

> **本节行号钉在 `ffbb24e`（`v2.16-beta.34`，2026-10-01 的 HEAD）。** 它的前一版 `6a3404f`（beta.33）与之相隔四个提交，全部发生在 2026-10-01：`esp32/.firmware/main.cpp` **+25 行**、`fsd_handler.cpp` 局部 **−1 行**。因此 `main.cpp` 里 nag killer 与预空那两处调用点由 `:1331`、`:1747` 移到 **`:1356`、`:1772`**，`fsd_handler.cpp` 的 ISA 分支由 `:453-460` 移到 **`:452-459`**；`fsd_logic/fsd_handler.c` 一个字节未变，1344 行照旧。

### 3.1 地图：一棵树，两份业务层，一套共享原语

| 位置 | 规模 | 职责 |
| --- | --- | --- |
| `fsd_logic/fsd_handler.c` | 58.7 KB，**1344 行 / 64 个函数** | 协议核心（C 版） |
| `esp32/.firmware/fsd_handler.cpp` | 1110 行 | **同一套业务的 ESP32 版（C++）** |
| `esp32/.firmware/main.cpp` | 1963 行 | 接收分发与运行时 |
| `fsd_logic/fsd_state.h` | `:23` → `:365` | 状态，**一个 343 行的 struct** |
| `fsd_logic/fsd_checksum.h`、`fsd_can_ops.h` | 33 行、63 行 | 两个平台共用的无状态原语 |
| `test/` | `test_fsd_core.c` 127.6 KB、`test_esp32_core.cpp` 31.9 KB | 宿主测试 |

**读法**：3.1 地图（两份业务层是理解本节的前提）→ 3.2/3.3/3.4 三层序列 → 3.5 nag killer → 3.6 横切面（相对第 2 节的差量）→ 3.8 测试；3.7 是独立案例，随时可跳读。

**第一个要看清的结构事实：业务层有两份。**`esp32/.firmware/fsd_handler.cpp:14-16` 的三条 include 把边界写得很明白：

```cpp
#include "../../fsd_logic/fsd_checksum.h"  // shared Tesla additive checksum (single impl, both platforms)
#include "../../fsd_logic/fsd_can_ops.h"   // shared stateless frame primitives (set_bit / mux / fsd-selected)
#include "../../fsd_logic/fsd_ota.h"       // shared 0x318 OTA-install detection (flag vs rolling counter)
```

共享的是无状态原语；判断逻辑各写一遍：`fsd_handle_autopilot_frame` 在 C 版是 `fsd_handler.c:191`、在 C++ 版是 `fsd_handler.cpp:265`，`fsd_detect_hw_version` 分别在 `:98` 与 `:123`。

直接后果是同一个 bug 要在两处各修一次，而两处的测试是分开的：`test_fsd_core` 编 `.c`，`test_esp32_core` 编 `.cpp`。8.1 那 827 条正是这么来的——648 条打 C 版，179 条打 C++ 版，**没有一条同时覆盖两者**。

### 3.2 第一层序列：启动

`fsd_logic/fsd_handler.c:7-32`：

```c
void fsd_state_init(FSDState* state, TeslaHWVersion hw) {
    memset(state, 0, sizeof(FSDState));
    state->hw_version = hw;
    if(hw == TeslaHW_HW4)
        state->speed_profile = 4;
    else if(hw == TeslaHW_Legacy)
        state->speed_profile = 1;
    else
        state->speed_profile = 2;
    state->op_mode = OpMode_Active;
    state->gtw_autopilot_tier = -1;
    state->das_hands_on_state = 0xFF; // unseen → nag killer echoes conservatively
```

与 2.2 节的 `appSetup()` 对照，形状完全不同：那边是硬件初始化序列，这边硬件初始化在平台层的 `main.cpp`，这一层只剩状态初始化。三处细节：

- `memset` 先清零，再**只把有默认值的字段写出来**，其余全靠零值语义。
- `das_hands_on_state = 0xFF` 是**"未见过"哨兵**。`:1262` 的注释写明 `0xFF = no DAS frame seen yet — echo conservatively as fallback`；用 0 就会被当成 `NOT_REQD`（`das == 0` 在 `:1269` 直接 return），门控语义整个反过来。
- `gtw_autopilot_tier = -1` 同理，用 −1 区分"没读到"和"第 0 档"。

**哨兵值是这个状态机最容易被改坏的地方，而它在初始化里就定死了。**

### 3.3 第二层序列：运行

`esp32/.firmware/main.cpp` 的接收回调按固定顺序跑。**分发业务之前有八道前置动作**：前四道只记录、不改帧，后四道各自拦截。

| 顺序 | 位置 | 做什么 | 会不会 `return` |
| --- | --- | --- | --- |
| 1 | `main.cpp:1127` | `blackbox_record` —— 关键 ID 落盘，**两种模式都记** | 否 |
| 2 | `:1132` | `capability_record` —— 接收窗口内计数，纯 RX | 否 |
| 3 | `:1134` | `can_dump_record` | 否 |
| 4 | `:1140` | `http_can_stream_record` —— **Active 模式也记**，注释写明是为了抓接合瞬间 | 否 |
| 5 | `:1149` | DLC 为 0 的帧丢弃 | 是 |
| 6 | `:1153` 起 | HW 自动识别（被动，命中即认车型） | 是 |
| 7 | `:1162-1168` | OTA 监控 | 是 |
| 8 | `:1185-1187` | BMS 只读嗅探（三个 ID 各一行、各自 `return`） | 是 |

顺序本身就是"先记录、后判断"：四道记录无论命中什么都往下走，四道判断命中即退。第 6、7 两类帧因此不进业务层。第 2.4 节那家没有这个结构——装好过滤器后命中帧一律直接进 `handleMessage()`。

并发。第 2.3 节 `appLoop()` 用 `volatile` 解决可见性问题，这里做法更重（`main.cpp:71-72`，`state_exit()` 在 `:75`）：

```cpp
static void state_enter() {
    portENTER_CRITICAL(&g_state_mux);
```

每次读写 `g_state` 前后进出临界区。代价是关中断，收益是状态从"单字段可见"变成"整体一致"——`fsd_state.h` 那 343 行是一个 struct，要么全看见、要么全看不见。

**发送许可：一个函数，三道条件，五处调用。**`fsd_logic/fsd_handler.c:41-48`——三行 `return false` 各管一件事，顺序即优先级：

```c
bool fsd_can_transmit(const FSDState* state) {
    if(state->op_mode == OpMode_ListenOnly) return false;
    // In-car Autopark (#180): pause every TX path for the episode. Not
    // overridable by ignore_ota — Autopark injection throws AEB/traction warnings.
    if(state->autopark_tx_block) return false;
    if(state->tesla_ota_in_progress) return false;
    return true;
}
```

| 第几道 | 条件 | 管什么 |
| --- | --- | --- |
| 1 | `op_mode == OpMode_ListenOnly` | 用户选了只听——任何发帧都不许 |
| 2 | `autopark_tx_block` | 车内自动泊车 episodes 期间全局停发。注释写明 `Not overridable by ignore_ota`，因为 Autopark 注入会触发 AEB / 牵引力告警 |
| 3 | `tesla_ota_in_progress` | OTA 期间停发（这一道是 `ignore_ota` 开关能放开的唯一一道） |

`main.cpp` 里每一条会发帧的路径都要先问它一次：`:287`（挡位序列）、`:876`、`:1276`、`:1356`（nag killer）、`:1772`（预空调用）。

**五处调用是这套机制的全部脆弱点**——加一条新路径忘了问它，那条路径就绕过了三道门。这是 2.9 节那张门控表最缺的实据：`tesla-open-can-mod` 里不存在这样一个函数，它的发送许可全在编译期宏里（6.2 会把这条与 ev-open 的结构化做法对照）。

### 3.4 第三层序列：业务，四道门在改任何比特之前

`fsd_logic/fsd_handler.c:191-208`，照原文行号录出：

```c
bool fsd_handle_autopilot_frame(FSDState* state, CANFRAME* frame, uint32_t now_ms) {
    if(frame->data_lenght < 8) return false;

    if(!fsd_ap_first_allows(state, now_ms)) return false;   // :197
    if(!fsd_soft_engage_allows(state)) return false;        // :200
    if(!fsd_abort_guard_allows(state)) return false;        // :203
    if(state->ap_first_minimal && state->ap_inject_count >= AP_MINIMAL_INJECT_FRAMES)
        return false;                                        // :207
```

**四道门各管一件事，从上往下依次是：**

| 门 | 管什么 | 出处 |
| --- | --- | --- |
| `fsd_ap_first_allows` | AP 是否真的接合且稳定 | `:197` |
| `fsd_soft_engage_allows` | 方向盘是否回正 | `:200` |
| `fsd_abort_guard_allows` | 本次接合是否进过 abort | `:203` |
| `ap_first_minimal` + `ap_inject_count` | 注入预算是否花完 | `:207` |

其中三道是 2026.14.x 之后才加的，注释挂着 issue 号（`#108`、`#100`），`:194-196` 还关联 `ev-open-can-tools#66 / v3.0.2-beta.2` 的一次转向顿挫。**2.9 节那份"没有什么"清单里，这四种一个都没有**——这是三仓在发送许可之外最大的一处差距。

过了门才是 mux 分发（`:210-214`）：

```c
uint8_t mux = fsd_read_mux_id(frame);
bool fsd_ui = fsd_is_selected_in_ui(frame, state->force_fsd);
bool modified = false;

if(mux == 0) state->fsd_enabled = fsd_ui;
```

随后按硬件代际分两支，形状与第 2.4 节三个 handler 的分支一致。**表里三行对应 mux 0/1/2，注意 mux 2 那一行的差别**：

| | HW3（`:228-274`） | HW4（`:275-324`） |
| --- | --- | --- |
| mux 0 | 算速度偏移 → `set_bit(frame, 46, true)`，写 byte6 速度档 | `set_bit(46)` + `set_bit(60)`，可选 `set_bit(59)` |
| mux 1 | 清 bit19，一串开关逐个写 48/50/47/46/…（`:241-267`） | 同一串开关（`:285-310`） |
| mux 2 | `if(mux == 2 && state->fsd_enabled)`（`:268`） | `if(mux == 2)`（`:311`） |

**第三行是全文最值得记住的一处跨仓库同构**：2.4 节记过的 `handlers.h:165` 对 `handlers.h:276`，这里原样重演——**两个仓库、两套语言、同样的不对称**。不像巧合，更像一份沿用了另一份的帧布局语义。我没有证据指认方向，只记下形态。

第二行的 bit47 走过一段路（它被误当成 nag 确认位），见 3.7。

### 3.5 nag killer：独立一支，且有自己的门

`fsd_handler.c:1239-1344`，进函数先过四道：

```c
if(!state->nag_killer) return false;                        // :1242 开关
if(!fsd_das_ctx_fresh(state, now_ms)) return false;         // :1244 DAS 来源新鲜度
if(state->nag_burst && nag_in_pause(now_ms)) return false;  // :1246 爆发/休息窗口
if(state->nag_epas_faithful) return nag_faithful_modec(...);// :1249 Mode-C 整体接管
```

然后才是"要不要回发"，三条判断：

```c
uint8_t hands_on = (frame->buffer[4] >> 6) & 0x03;  // :1255 EPAS 的 2 位
if(hands_on == 1) return false;                     // :1256 手确实搭着 → 不回发
...
if(das == 0 || das == 8) return false;              // :1269 DAS 已满足 / 已暂停 → 不回发
```

`:1251-1254` 的注释把一次历史修改钉住了：原来的守卫写成 `hands_on != 0` 就跳过，结果把 level 3（升级告警）也一起跳过了，改成"只在 level 1 时跳过"。门控条件写反导致功能静默失效的实例，被注释固定下来。

发出去的帧是整帧回读再改，不是凭空造（`:1320-1339`）：

```c
out->buffer[4] = (frame->buffer[4] & ~0xC0u) | 0x40u;   // 清掉 7:6 再置 level=1
...
uint8_t cnt = (frame->buffer[6] & 0x0F);
cnt = (cnt + 1) & 0x0F;
out->buffer[6] = (frame->buffer[6] & 0xF0) | cnt;        // counter + 1
```

`:1329` 的注释解释了为什么要先清：`OR-ing 0x40 without clearing leaves level=3 unchanged on escalated frames`——不先掩码就 OR，升级帧上 level 仍是 3。这与第 2.5 节 `setBit` 的"写绝对位号"是同一个问题的两种处理：带读-改-写语义的位操作忘了掩码，就会静默失效。

末尾重算校验和（`:1339`）：

```c
out->buffer[7] = tesla_additive_checksum(CAN_ID_EPAS_STATUS, out->buffer, 7);
```

### 3.6 横切面：与第 2 节是同一套词汇

位操作。 `fsd_handler.c:85-87` 只有一行转发 `tesla_set_bit(frame->buffer, bit, value)`，实现在 `fsd_logic/fsd_can_ops.h:19`，两个平台共用。第 2.5 节那四个原语在这里被压成一个带 `value` 参数的函数——语义等价，词汇量少一半。头文件那行注释叫它 `shared stateless frame primitives`，"无状态"就是这个抽象的全部要点。

**校验和。** `fsd_logic/fsd_checksum.h:28` 的 `tesla_additive_checksum(can_id, data, len)`：ISA / track / nag 放 byte 7、SCCM 左 CRC 放 byte 0（用法注释在 `:22-23`）。ISA 那一支（`fsd_handler.c:391-396`）与 2.6 节逐句对得上，`CAN_ID_ISA_SPEED` 就是 `0x399`——`921 == 0x399`。

差别只在封装：那边把循环内联进 handler，这边抽成 `static inline` 放共享头，ESP32 版还把字节位换成命名常量 `SIG_ISA_SOUND_ACTIVE_BYTE` / `_MASK`（`fsd_handler.cpp:452-459`）。

**这是收敛还是抄袭，我判定不了。**flipper 在别处会署名——`fsd_handler.c:50` 写着 `BMS read-only parsers (CAN frame templates from tuncasoftbildik/tesla-can-mod)`，多处注释指向 `ev-open-can-tools`——这一支却没有署名。我只能把行号并排放着，方向不猜。

（"只在自己起头发的帧上重算校验和"这个共同点，见 5.2。）

### 3.7 一句结论只活了 24 小时：bit47 的两次改口

这是全文最能说明"行号与结论都必须钉死在版本上"的一段。

`bit47` 是 EU Summon 的开关位。下表三行是它的完整改动史：**两次改口，都发生在本文写作的前两天**。

| 版本 | 状态 | 备注 |
| --- | --- | --- |
| `19ef738`（beta.29） | C 版 HW4 **无条件**置位，头顶一段自陈坦白注释：`// HW4 sets bit47 (summon enable) unconditionally here (pre-existing), so the summon_unlock toggle is effectively always-on for HW4 on this build. ... Reconciling this divergence is a follow-up.` | 本次钉出的原文 |
| `6a3404f`（beta.33，2026-09-30） | follow-up 做完：`:294-296` 变成 `if(state->summon_unlock) { fsd_set_bit(frame, 47, true); }`，坦白注释删掉，与 HW3 的 `:251-253` 对称 | 相隔 24 个提交，一个自陈的 TODO 归零 |
| `ffbb24e`（beta.34，2026-10-01） | C 版**没动**；改的是 ESP32 版：`esp32/.firmware/fsd_handler.cpp` 的 nag killer 分支**删掉了** `set_bit(frame, SIG_AP_HW4_NAG_CONFIRM_BIT, true); // HW4 nag-suppression confirmation bit` 这一行 | 本次重写新查 |

beta.34 的 `changelog.md` 开头就写明了理由（逐字）：

> **ESP32: the nag killer no longer sets 0x3FD bit47 on HW4.** bit47 is the Summon-enable bit (confirmed on-car in #163), not part of nag suppression — the nag killer works through the bit19 clear and the 0x370 EPAS echo. ... The misnamed constant is renamed to SIG_AP_SUMMON_ENABLE_BIT. No change to nag behaviour.

于是 `esp32/.firmware/can_signals.h:44` 从 `#define SIG_AP_HW4_NAG_CONFIRM_BIT 47` 变成 `#define SIG_AP_SUMMON_ENABLE_BIT 47`——**一个常量名骗了所有人：它叫"Nag 确认位"，其实是"Summon 使能位"。** 同一提交还加了 `config.h:165` 的 `SUMMON_DISABLE_SPEED_KPH 3.0f`，让 Summon 在车速超 3 km/h 时自动撤销（`main.cpp:1307-1321` 的 `0x257` = 十进制 599 速度分支；换算约定见 0.4）。

这一段的分量不在技术，而在结论的半衰期："bit47 常开"这一判断在上游 HEAD 上已然错误，"beta.33 修好了"这一判断隔日又错。**版本敏感的结论只能连同 commit 一起写。**

### 3.8 测试：827 条断言，分成互不覆盖的两套

第 8 节的 827 条并非一个测试工程的产物，而是两套彼此独立的宿主测试：`test_fsd_core.c`（127.6 KB）编 C 版 `fsd_logic/`，`test_esp32_core.cpp`（31.9 KB）编 ESP32 版 `.firmware/`，入口是 `make -C test check`（不是 PlatformIO，见 8.5）。648 条打前者、179 条打后者。

**没有一条断言同时覆盖两份实现**——这正是 3.1 结尾那个"同一个 bug 要在两处各修一次"的测试层对应物。C 版改了一行判断，C++ 版的断言不会变红，反之亦然。测试数量在这里证明的是覆盖广度，不是两份实现的行为一致性。

## 4. `ev-open-can-tools`：最像平台的一个

> **本节行号钉在 `6d37392`（`v4.0.0-beta.3`，2026-09-20），也就是 `dev` 分支。** 默认分支 `main` 停在 `338d276`（2026-08-05），两者在 `447049d` 分叉，`v4.0.0-beta.3` 这个 tag 不在 `main` 上——**按 `main` 推行号会整节错位**。两线在 `app.h`、`handlers.h`、`can_driver.h`、`main.cpp` 上均有改动，`app.h` 的发送许可由 `:110`/`:295` 移到 `:113`/`:324`。**下文全部是 `dev` 的行号。**

方法与前两节一致。**读法**：4.1 地图 → 4.2/4.3/4.4 三层序列 → 4.5 横切面（相对第 2 节的差量）→ 4.6 两处真故障 → 4.7 测试。最值得细读的是 4.2 的平台化选型与 4.5 末的发送许可回调（后者三家里唯一，见 6.2）。

### 4.1 地图

| 位置 | 规模 | 职责 |
| --- | --- | --- |
| `src/main.cpp` | 256 行 | 入口：`app_main` / `setup` / `loop` 三选一，转 `app_main_setup` + `app_main_loop` |
| `src/espidf_runtime.cpp` | 45.9 KB | ESP-IDF 侧 WiFi / HTTP / OTA 封装 |
| `include/app.h` | 458 行 | **选型 + 装配 + 运行循环**，三层全在这一个文件 |
| `include/handlers.h` | 1218 行 | **第三层序列**：五个 handler |
| `include/can_helpers.h` | 231 行 | 位操作与校验和原语 |
| `include/drivers/` | 7 个文件 | 七个驱动实现，共享一个接口 |
| `include/plugin_engine.h` | 1641 行 | 插件机制 |
| `include/injection_policy.h` | 231 行 | 注入的新鲜度、挡位、AP 状态判定 |
| `include/web/mcp2515_dashboard.h` | 4561 行 | 内嵌网页面板 |
| `test/` | **17 个套件目录** | native 测试 |
| `platformio.ini` | **21 个 env**（11 设备 + 10 native） | 构建矩阵 |
| `partitions_*.csv` | 3 份 | 4MB / 8MB / 16MB 三套 OTA 分区表 |
| `scripts/` | 6 个 Python | 构建同步、UI 生成、发布校验、日志分析 |
| `VERSION` | `4.0.0-beta.3` | — |

### 4.2 第一层序列：启动

入口在 `src/main.cpp:199-245`（ESP-IDF 路径），Arduino 路径是 `:247` 的 `setup()` 与 `:252` 的 `loop()`，两者都转到同一组函数：

```c
extern "C" void app_main(void)
{
    Serial.begin(115200);
    delay(50);
    RuntimeDiagnostics::begin();
    if (!GvretSerial::begin())
        Serial.println("[WARN] GVRET serial task failed to start");

    const esp_err_t nvsInitialErr = nvs_flash_init();
    ...
    RuntimeDiagnostics::noteNvsInitialization(nvsInitialErr, nvsErr, nvsRecovered);
    ESP_ERROR_CHECK(nvsErr);

    app_main_setup();
    while (true)
    {
        RuntimeDiagnostics::noteMainLoop();
        try { app_main_loop(); }
        catch (const std::bad_alloc &) { Serial.println("[ERR] Main loop out of memory"); delay(100); }
        ...
        RuntimeDiagnostics::logHeartbeat(appDriver.get());
        yield();
    }
}
```

（省略号处为 NVS 擦除重试与另两个 `catch` 分支，逐字对应原文。）

与前两节对照，启动序列里多了两样它们没有的东西：`nvs_flash_init()` 的失败自愈（无空闲页或版本不匹配就擦掉重来），以及主循环的三层 `catch`——`std::bad_alloc`、`std::exception`、`...` 各自兜住再继续。前两个仓库的主循环没有异常边界。

`app_main_setup()`（`src/main.cpp:84`）按驱动宏分四支，每支固定两步——`appPrepare<T>()` 再 `appStartDriver<T>()`。TWAI 那支的注释是关键：`// Load TWAI pins from NVS (survives OTA); fall back to compile-time defaults`——引脚从 NVS 读、OTA 之后不丢、编译期宏只是兜底，前两个仓库的引脚全在编译期。

车型选型在 `include/app.h:32-51`，比第 2.4 节多出两级：

```cpp
#if defined(ESP32_DASHBOARD)
#if DASH_DEFAULT_HW == 0
using SelectedHandler = LegacyHandler;
#elif DASH_DEFAULT_HW == 2
using SelectedHandler = HW4Handler;
#else
using SelectedHandler = HW3Handler;
#endif
#elif defined(SUMMON_UNLOCK_ONLY)
using SelectedHandler = SummonUnlockHandler;
#elif defined(NAG_KILLER)
using SelectedHandler = NagHandler;
#elif defined(HW4)
using SelectedHandler = HW4Handler;
#elif defined(HW3)
using SelectedHandler = HW3Handler;
#elif defined(LEGACY)
using SelectedHandler = LegacyHandler;
#else
#error "Define HW4, HW3, LEGACY, or NAG_KILLER in build_flags"
#endif
```

五个 handler，四条选型路径。 `ESP32_DASHBOARD` 那一支最值得看：`DASH_DEFAULT_HW` 是一个数值宏，网页面板构建时它优先于 `HW4`/`HW3`，因为网页要在运行时显示默认值。

### 4.3 第二层序列：运行

`include/app.h:376-` 的 `appLoop<Driver>()`。开头三件事：

```cpp
template <typename Driver>
static void appLoop()
{
    ...
    if (Update.isRunning())
    {
        delay(1);
        return;                      // app.h:391-395
    }

#if defined(DASH_INJECTION_TOGGLE_PIN)
    appPollInjectionToggleButton();
#endif
```

OTA 更新进行中，整个主循环直接停掉。这比第 3.3 节 flipper 的做法硬：flipper 是在 `fsd_can_transmit()` 里拒绝发送（`state->tesla_ota_in_progress`），业务层照常跑；这里是连读帧都不读。

然后是排空读取与广播：

```cpp
    CanFrame frame;
    uint8_t framesThisLoop = 0;
    while (appDriver->read(frame))
    {
        ...
        CanFrame original = frame;
#ifdef ESP_PLATFORM
        GvretSerial::broadcast(original);
#endif
        {
            AppHandlerGuard guard;
            CarManagerBase *h = appGetActiveHandler();
            if (!h)
                h = appHandler.get();
            if (h)
                ...
```

（对应 `include/app.h:426-429`，前后各处以 `…` 省略。）

先广播给上位机，再交给业务层——GVRET 是一套上位机协议，PC 端工具靠它看到原始帧。前两个仓库没有这个旁路。

### 4.4 第三层序列：业务

接口在 `include/handlers.h:346-350`，与第 2.4 节 `tesla-open-can-mod` 的 `CarManagerBase` 逐字相同（除了类型名）：

```cpp
    virtual void handleMessage(CanFrame &frame, CanDriver &driver) = 0;
    virtual const uint32_t *filterIds() const = 0;
    virtual uint8_t filterIdCount() const = 0;
    virtual ~CarManagerBase() = default;
};
```

五个派生类：`LegacyHandler`（`:352`）、`HW3Handler`（`:480`）、`HW4Handler`（`:691`）、`NagHandler`（`:1000`），外加 `SummonUnlockHandler`。"同一个类既声明听什么、又实现听到了怎么办"这个设计，三个仓库里有两个在用，而且连 `filterIds` 这个方法名都一样。

`LegacyHandler` 的过滤清单（`:356`）比第 2.4 节宽得多：

```cpp
        static constexpr uint32_t ids[] = {69, 280, 390, 599, 921, 1006, 1016};
```

7 个 ID，对比 `tesla-open-can-mod` 的 2 个。多出来的几个里，599 就是 3.7 提到的那个 Summon 车速帧。听得多，是因为它还要负责仪表、BMS、诊断这些只读功能——第 6 节的功能面对比会回到这一点。

### 4.5 横切面：同三个原语，多一道边界

位操作，`include/can_helpers.h:216-230`：

```cpp
inline void setBit(CanFrame &frame, int bit, bool value)
{
    if (bit < 0 || bit >= 64)
        return; // bounds guard: CanFrame.data is 8 bytes
    int byteIndex = bit / 8;
    int bitIndex = bit % 8;
    uint8_t mask = static_cast<uint8_t>(1U << bitIndex);
    if (value)
    {
        frame.data[byteIndex] |= mask;
    }
    else
    {
        frame.data[byteIndex] &= static_cast<uint8_t>(~mask);
    }
}
```

`bit / 8`、`bit % 8`、掩码读改写，连开头那道边界守卫都与 2.5 节逐字相同。flipper 的 `tesla_set_bit`（`fsd_can_ops.h:19-27`）同样带护栏（`:20`）——三家越界语义一致：都只在 `data[8]` 之内改写。

校验和，`include/can_helpers.h:199-214` 的 `computeVehicleChecksum(frame, checksumByteIndex = 7)`：ID 高低字节 + 数据字节累加（跳过校验字节自己）取低 8 位，外加一处 `dlc` 边界判断。与 2.6 节那段内联循环是同一段数学，只是抽成函数、累加顺序反过来。**三个仓库，三种封装，一个算法。**

驱动接口，`include/drivers/can_driver.h:7-47`。纯虚方法与 2.7 节完全一致（`init` / `setFilters` / `enableInterrupt` / `read` / `send`），但多了两个回调指针和一个许可函数：

```cpp
struct CanDriver
{
    void (*onSendFrame)(const CanFrame &, bool ok) = nullptr;
    bool (*allowSendFrame)(const CanFrame &) = nullptr;

    virtual bool init() = 0;
    virtual void setFilters(const uint32_t *ids, uint8_t count) = 0;
    ...
    bool sendAllowed(const CanFrame &frame) const
    {
        return !allowSendFrame || allowSendFrame(frame);
    }
```

这就是 2.9 节那个"不存在的东西"，在这里以接口成员的形式存在。实现在 `app.h:113-127`，`app.h:324` 装进驱动（`appDriver->allowSendFrame = appCanTransmitAllowed;`）。前两道问 `appInjectionReady()` 和 `summonOnlyInjectionRuntime`，第三道向 handler 要 `summonOnlyInjectionDecisionAt()` 的裁决。

**这是三家里把发送许可放在最靠近硬件位置的一个**——业务层根本没法绕过它。三者对比见 6.2。

### 4.6 实测到的两处真故障

**其一，`plugin_engine.h:747` 的 `strlcpy` 编不过。** 在 `main` 上跑 native 测试时，`native_plugin_engine` 直接编译失败：

```
include/plugin_engine.h:747:5: error: 'strlcpy' was not declared in this scope; did you mean 'strncpy'?
```

原文在 `dev` 上一模一样，一个字节没改：

```cpp
    strlcpy(out.name, name, sizeof(out.name));        // :747
    strlcpy(out.version, version, sizeof(out.version)); // :748
    strlcpy(out.author, author, sizeof(out.author));    // :749
```

`strlcpy` 是 BSD/newlib 函数，ESP-IDF 里有，本机的 MinGW g++ 没有；Linux 上 glibc 2.38 之后也有。所以这大概率是平台相关的——但在我这台 Windows 上，它的 native 套件只能过 7 个（详见 4.7 的分母说明）。从 `main` 到 `v4.0.0-beta.3` 跨了 17 天、14 个提交，这处没修。

**二、`scripts/minify_dashboard.py` 在中文 Windows 上因编码失败。** 报错 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa6`——脚本 `open()` 不带 `encoding=`，本机默认编码是 GBK。`set PYTHONUTF8=1` 可绕过。这类问题 README 里不可能写，只能实跑一次记录一次。

ev-open 对版本与车型的记载也几乎是空的（与第 9 节那张三仓表同源）：`2026.2.11` 全仓 0 处、`X179` 0 处；`HW4` 有 224 处——支持很扎实，只是没落到那个具体 OTA 版本。

### 4.7 测试：249 个用例，2 个套件在本机编不过

`test/` 下 **17 个套件目录**、`platformio.ini` **10 个 native env**，8.1 记的是 249 个用例、247 过。与前两节最大的不同是**测试粒度按功能切开**——光看 env 名就知道覆盖面：`native_bypass_tlssc_requirement`（1.1 那道选择位）、`native_nag`、`native_injection_after_ap`（1.4 的 AP-First）、`native_plugin_engine` 与 `native_plugin_engine_custom_key`（平台特征）、`native_dev_sim`、`native_mcp2515_recovery`、`native_log_buffer`、`native_dashboard`。这是"平台化"在测试层的投影：三仓里只有它把每个开关都做成一个可单独跑的套件。

代价是它对工具链更敏感——4.6 那个 `strlcpy` 一个 bug 就打掉两个套件：**9 个测试套件只编得过 7 个**（按用例算就是 8.1 的 247/249，同一轮的两把尺，分母不同别混）。

---

# 第三部分 · 一致性与区别

三份源码读完了。先看它们在哪一层其实是一份东西，再看它们在哪一层已经分化成三个不同的工具。**本部分只作对照与回指，不引入 2–4 节之外的新证据。**

## 5. 一致：同一个骨架

把三份源码的启动、运行、业务三层摆齐，会看到一张几乎能互相覆盖的表：

| 层 | `tesla-open-can-mod` | `flipper-tesla-fsd` | `ev-open-can-tools` |
| --- | --- | --- | --- |
| **选型** | `include/app.h:17-25` 编译期 `#if` | 菜单运行时选（`fsd_state.h` 存 `hw_version`） | `include/app.h:32-52` 编译期 `#if`，面板构建时另有 `DASH_DEFAULT_HW` |
| **驱动接口** | `drivers/can_driver.h:7-12` 六个纯虚/虚析构（全文 13 行，2.7） | 平台层各写各的 | `drivers/can_driver.h:7-47` 纯虚 + 两个回调 |
| **启动** | `appSetup()`：串口 → 驱动 → 过滤器 → 中断 | `fsd_state_init()`：只清状态，硬件在 `main.cpp` | `app_main_setup()`：NVS → 驱动 → 启动 |
| **运行** | `appLoop()` `while(read)` 排空 | `main.cpp` 六步：记录 → 丢弃 → 识别 → OTA → 嗅探 → 分发 | `appLoop()`：OTA 闸 → 排空 → 广播 → 分发 |
| **业务接口** | `CarManagerBase` 纯虚三方法 | `fsd_handle_autopilot_frame()` 函数式 | `CarManagerBase` 纯虚三方法 |
| **监听清单** | `filterIds()` 与 `handleMessage()` 同类绑定 | `fsd_can_rx_handler()` 表驱动 | `filterIds()` 与 `handleMessage()` 同类绑定 |
| **位操作** | `can_helpers.h:31-46` `setBit(bit/8, bit%8)` | `fsd_can_ops.h:19` `tesla_set_bit` | `can_helpers.h:216-230` `setBit(bit/8, bit%8)` |
| **校验和** | `handlers.h:134` 内联循环 | `fsd_checksum.h:28` 函数 | `can_helpers.h:199-214` 函数 |
| **mux 语义** | `readMuxID()` = `data[0] & 0x07` | `fsd_read_mux_id()` | `readMuxID()` |

**上面这张表里每一行都相同的地方，下面五小节逐条单说。**

### 5.1 绝对位号寻址是三家共用的方言

三份源码里都是 `setBit(frame, 46, true)` 这种字面量位号，没有任何一家的代码里存在 DBC 文件——DBC 的"起始位 + 长度 + 字节序"在这层已被手工展开成绝对位号。魔数最容易互相对齐，也最容易集体出错。

### 5.2 校验和只管自己起的头

三家都只在"自己是发送方"的帧上重算（`921`、`0x370`、track、ISA），"原地改 `0x3FD` 再回发"时都不重算——flipper 那 1344 行里一次 `tesla_additive_checksum` 都没有。三家一致，说明不是疏忽。

**这条纪律为什么是纪律，上游自己给过一次反面教材。**`ROADMAP.md:30` 记着一条已结案的失败：他们**破解了 `0x229 SCCM_rightStalk` 的 AUTOSAR-E2E 校验和**——脚本 `tools/crack_0x229.py`，两次全速率抓包、224/224 真实帧全部算对——然后试图靠往右转向杆注入一个"拉一下"的动作来启动 AP。

**结果是失败的，输在滚动计数器上**：一个自由运行的注入帧会与车端自己那条 SCCM 流**逐比特冲突**，滚动计数器的连续性被破坏，整条链路失效（issue `#95`、`#122`）。加上 Highland / Juniper 根本没有 `0x229` 这一帧——**这就是 `0x3C2` ScrollPress 之所以成为 HW4 唯一那条路的直接原因**（1.4）。

于是这一节的两句话合起来才完整：**校验和能破，但滚动计数器破不了**——前者是纯数学，后者要求你与车的实时发送节奏逐帧对齐。三家都选择只改"自己起的头"的帧，不是省事，是这条失败路径换来的结论。

### 5.3 `tesla-open-can-mod` 与 `ev-open` 的业务接口逐字相同

`CarManagerBase` 的三个纯虚方法名（`handleMessage` / `filterIds` / `filterIdCount`）一字不差——ev-open 的 README 明说它是从同族工具衍生的。

### 5.4 HW3 查 mux 2 的状态缓存、HW4 不查，两个仓库一模一样

2.4 节与 3.4 节各记过一次（`handlers.h:165` 对 `:276`、`fsd_handler.c:268` 对 `:311`），两边的测试也各自锁住了这个行为。

### 5.5 "先清再置"的读改写纪律是三家共识

2.5 节的掩码、3.5 节 `:1329` 的 `OR-ing 0x40 without clearing leaves level=3 unchanged`、4.5 节 `setBit` 的 `~mask`——三处注释、三种写法、同一个教训：忘了掩码，位操作会静默失效，方式是"看起来生效了一部分"。

## 6. 区别：五条维度

**差别比相似更能说明问题。**同样三个仓库，五条维度上已经分得很开。

### 6.1 维度一：选型发生在哪一层

| | 方式 | 代价 |
| --- | --- | --- |
| `tesla-open-can-mod` | 编译期 `#if`，`#error` 兜底 | 每种板 × 每种车都要编一次；改错编译不过 |
| `flipper-tesla-fsd` | 运行时菜单，存进 `fsd_state.h` 的 `hw_version` | 一次烧录覆盖全部；选错要重新进菜单 |
| `ev-open-can-tools` | 编译期 `#if`，但**面板构建另有 `DASH_DEFAULT_HW` 数值宏**；TWAI 引脚从 NVS 读 | 四条选型路径并存，最复杂；引脚 OTA 不丢 |

三者没有优劣，但代价的形态不同：`tesla-open-can-mod` 把代价放在编译期（配错即编不过），flipper 放在运行时（选错要手工回退）。ev-open 则同时铺在编译期与运行期两条路径上——编译期 `#if` 分出四个车型分支（4.2 节），网页面板构建又由 `DASH_DEFAULT_HW` 数值宏单独决定（4.2 节），两条路径彼此独立，这是它代价最复杂的原因。

### 6.2 维度二：发送许可放在哪一层

**这一条是三个仓库分化最深的地方。**同样一句"现在该不该发帧"，一家没写、两家写了但放的位置决定了它拦不拦得住：

| | 机制 | 位置 | 能否绕过 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | **不存在** | — | 业务层想发就发，只有编译期配置 |
| `flipper-tesla-fsd` | `fsd_can_transmit()` 三道条件 | `fsd_handler.c:41-48` | **业务层每条发送路径各调一次**（`:287` `:876` `:1276` `:1356` `:1772`）——容易漏 |
| `ev-open-can-tools` | `sendAllowed()` 回调 + `appCanTransmitAllowed()` | `drivers/can_driver.h:21-24`，实现在 `app.h:113-127`，`app.h:324` 挂进驱动 | **挂在驱动的回调上，业务层无法绕过** |

2.9 节列过 `tesla-open-can-mod` 的门控清单，它缺的正是这道统一许可。表中"能否绕过"一列就是本条维度的全部差别：靠自律的容易漏，靠结构的写不错。

两家的条件数不同、性质也不同：`ev-open` 那三道是注入就绪与 Summon-only 相关（清单见 4.5），`flipper` 那三道是 Listen-Only / Autopark / OTA。**ev-open 一条 OTA 许可都没有**——它的 OTA 处理不在许可函数里，而在主循环整体停摆（6.3）。

### 6.3 维度三：OTA 期间的行为

三个仓库对"OTA 进行中"的处理完全不在一个强度上：

- `tesla-open-can-mod`：**没有这个概念**，全仓 grep 无 OTA 检测。
- `flipper-tesla-fsd`：`fsd_can_transmit()` 第三道 `state->tesla_ota_in_progress` 返回 `false`——**只拦发送，业务层照常跑**，`main.cpp:1162-1168` 的 OTA 监控帧还会提前 `return`。
- `ev-open-can-tools`：`app.h:391-395` `if (Update.isRunning()) { delay(1); return; }`——**整个主循环停掉，连帧都不读**。

同一句"OTA 进行中不要发帧"，三种实现的边界从"业务层自律"一路推到"运行时整体停摆"。**ev-open 最保守，也最不容易出错**——但注意它的代价是**OTA 期间工具完全失明**（连抓帧都没有），而 flipper 至少还留着只读功能。

**这三条的排序不是优劣排序，是"闸门放在多靠里的位置"排序**：越靠里越拦得住，也越看不见外面。

### 6.4 维度四：功能面

| 功能 | `tesla-open-can-mod` | `flipper-tesla-fsd` | `ev-open-can-tools` |
| --- | --- | --- | --- |
| 速度档写入 | ✓ | ✓ | ✓ |
| HW4 自动识别 | ✗ | ✓（`main.cpp` 被动识别） | ✓（`handlers.h` 从 920 = `0x398` 帧；14.2 的 Auto-detect 同源） |
| 校验和重算 | ✓（内联） | ✓（共享函数） | ✓（共享函数） |
| 发送许可 | ✗ | ✓ | ✓（结构化） |
| OTA 检测 | ✗ | ✓ | ✓ |
| 滚动计数器 | ✗ | ✓（`:1329` 附近） | ✓ |
| 内嵌网页面板 | ✗ | ✗ | ✓（4561 行） |
| 插件机制 | ✗ | ✗ | ✓（`plugin_engine.h` 1641 行） |
| 仪表 / BMS 只读 | ✗ | ✓（`:1185-1187`） | ✓ |
| 异常边界（主循环 `catch`） | ✗ | ✗ | ✓（三层 `catch`） |
| 测试 | 99 断言 / 107 次执行 | 827 断言（648 C 版 + 179 C++ 版；另有 10 个板级 env） | 17 个套件目录 / 249 用例（2 个套件编译失败） |
| 代码规模 | 7 文件 / 301 行业务（`handlers.h`） | 1344 行业务 + 1110 行副本 | 1218 行业务 + 1641 行插件 |

**这个矩阵就是三个仓库的分野：**`tesla-open-can-mod` 是一个能跑通的最小实现，flipper 是一个带运行时治理的完整应用，ev-open 是一个带面板和插件的平台。功能面越宽，需要读的源码越多；功能面越窄，越容易完整判定它究竟发出的东西。

**最后一行与"测试"行的数字不能直接比大小**：三家的计数口径不同（断言 / 用例 / 套件，见 8.1 开篇），而且断言数会被一个用例里写几条断言放大。**这一列只说明各自的测试组织方式，不说明谁测得更充分。**

**读这张表要认它的判据。**上表每一格都是本文按下面三种依据之一判定的，不是"感觉"：

| 判据 | 含义 | 可靠性 |
| --- | --- | --- |
| **grep 确认** | 在钉死的 commit 上全仓搜索无命中（如"滚动计数器"在 `tesla-open-can-mod`） | 强，但只对"不存在"这类否定命题有效 |
| **代码读到** | 打开了那个文件、看到了那段逻辑（如"异常边界"） | 最强 |
| **文档自述** | 只有 README 说有，本文未见源码佐证 | 弱，本文会标出 |

**这个分级必须写出来，否则这张表会被当成事实清单而不是判断清单。**一个典型：`tesla-open-can-mod` 的"内嵌网页面板 ✗"是 grep 判的，而社区里的 `lenfien/tesla-open-can-mod-release`（1-v-1 的一个 fork）README 明确列出了实时图表网页面板、29 个 API 端点与 OTA 固件上传。**两者不矛盾——本表只覆盖 `1-v-1` @`815e000` 原仓，不含任何 fork**；读者拿 fork 对照时请记住这条边界。

### 6.5 维度五：许可证与发布

| | 许可证（打开 `LICENSE` 逐字核对） | 发布形态 | 末次提交 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | **GPL-3.0 全文**（35,145 B）+ `THIRD_PARTY_LICENSES` | 无 tag、无 release，直接 clone | 2026-04-02（**183 天没动**） |
| `flipper-tesla-fsd` | **GPL-3.0**——但 `LICENSE` 只有 **929 B**，是那段"如何套用本许可"的说明，不是许可全文 | `v2.16-beta.34`，tag 频繁 | **2026-10-01（当天）** |
| `ev-open-can-tools` | **GPL-3.0 全文**（35,819 B）+ `THIRD_PARTY_LICENSES` | `v4.0.0-beta.3` tag，`main` / `dev` 分叉 | `dev` 2026-09-20，`main` 2026-08-05 |

许可证是三者唯一完全收敛的地方——三家都是 GPL-3.0。但中间那一格暴露了一个方法陷阱：GitHub REST API 对 flipper 返回的 `license` 是 `NOASSERTION`，因为它的 `LICENSE` 只有 929 B、是那段"如何套用本许可"的说明而非全文。**只靠 API 做许可证清点的调研，会把星最多的那个（1094★）报告成"许可证未声明"**——而它明明白白写着 GPLv3。本表因此按文件本身统计。

发布节奏的分化才是真差异：**"这个仓库是否还在维护"和"代码质量如何"是两个独立问题**，前一个往往更致命。

## 7. 定位：三个仓库在哪一层

先看这张层图——它画的是**车辆软件的纵向分层**，三个仓库要放进里面：

![三层定位：模型层、决策与执行层、总线层](images/can-mod-teardown-2026/s03-layer-positioning.svg)

图 4｜三层定位：模型层、决策与执行层、总线层。总线工具改写的是决策与执行层的输出，不触及模型本身。

**三者都住在最下层的总线层**——直接对 CAN 总线收发帧，不参与感知、不参与规划、不决定"要往哪开"。它们在源码里那套收发动作，物理形态就是几组位掩码加一个时间窗口。

那差别在哪？**不在纵向的层，而在总线层内部各做了多少"发不发"的裁决。**从简到繁：

- `tesla-open-can-mod`：**只做转换**。收到帧、按业务规则改几个比特、发回同 ID，没有独立的发送裁决层（2.9 节那份"没有什么"清单）。
- `flipper-tesla-fsd`：自建了一道**运行时治理**——Listen-Only/Active 模式、AP 是否接合、注入预算、abort guard 四道门（3.4）。不替代车辆的决策层，只是在发帧前多做一轮"现在该不该发"。
- `ev-open-can-tools`：治理之外还有一整套**平台能力**——网页面板、插件机制、把发送许可做成驱动回调（6.2）。

**三者往上伸的都是总线层自己的"纵深"，不是进入了更高层。**读源码的收益也在这里：越往总线层内部纵深，越能读到"为什么这么做"而不只是"怎么做"——但再往上（模型、规划）就超出这三个仓库的范围了。

---

# 第四部分 · 实测与未知

数据全部按各自钉死的版本标注，报错原文按证据保留。

## 8. 实测汇总

本节两组实跑：宿主测试不碰硬件，板级构建真编固件；六条报错按性质分组，未做之事单列。

**这一节的看点不在"1181 过"，在失败项。** 三条根因、四处失败点：

| 根因 | 失败点 | 属于哪一层 |
| --- | --- | --- |
| 宿主缺 BSD 函数 `strlcpy` | `ev-open` 两个 native 套件编不过（4.6） | 宿主工具链 |
| 仓库配置里的包名失效 | `tesla-open-can-mod` 的 `feather_rp2040_can` 板级构建 404（8.3 B 组） | 仓库配置 + 上游依赖 |
| 中文 Windows 默认 GBK | `ev-open` `scripts/minify_dashboard.py` 解码崩溃（8.3 A 组） | 本机编码 |

**能报出这些，才说明这些数是真跑出来的。**

### 8.1 宿主测试（`native` / `platform = native`，不碰硬件）

**先说计数口径**：下表"用例"一列是**测试用例数**（每个 `RUN_TEST`／`TEST_CASE` 记一次），各家定义见 2.8、3.8、4.7。**断言数与用例数在 flipper 一家相等、在另外两家不等**（同一用例里有多条断言），所以横向只比量级，不比强弱。

| 仓库 | 版本 | 套件 | 用例 | 结果 |
| --- | --- | --- | --- | --- |
| `tesla-open-can-mod` | `815e000` | 8 次套件运行（3 个 env） | 107 | **107 过 / 0 失败** |
| `flipper-tesla-fsd` | **`6a3404f`**（beta.33，HEAD 的前一版，见下） | 2（`test/Makefile`，gcc/g++ 直调，非 PlatformIO） | 827 | **827/827 全过**（648 C 版 + 179 C++ 版） |
| `ev-open-can-tools` | `6d37392`（`dev`） | 10 个 env、19 次套件运行（PlatformIO native） | 249 | **247 过 / 2 个套件编译失败** |
| `JordanzhaoD/waveshare-single-can-firmware`（对照，不属三仓） | — | 19（PlatformIO native） | 650 | **650/650 全过** |
| **三仓小计**（上三行） | | | **1183** | **1181 过 / 2 个套件编译失败** |
| **含对照仓合计** | | | **1833** | **1831 过 / 2 个套件编译失败** |

**两个合计的区别要说明白**：全文多处引用的"1833"含第四个仓库 `JordanzhaoD` 的 650 例，它只作横向对照、不属本文解剖对象（见 15.1 那张表的末行）。**只看三个被解剖的仓库，宿主侧是 1183 例、1181 过。**

**这张表只有 flipper 一家不在 HEAD 上**：实跑落在 `6a3404f`（beta.33），比第 0 节钉死的 `ffbb24e` 早 4 个提交（8.4 已列）。另两家与第 0 节的 commit 一致（重跑日期与主机环境见 8.3）。第 2、3、4 节的全部 `file:line` 与本表同源，行号按 `ffbb24e`。

那 2 个失败是**真编译错误**，根因见 4.6：`plugin_engine.h:747` 在 MinGW 下缺 `strlcpy` 符号，同树的 `native_plugin_engine_custom_key` 一起挂——一个 bug 打掉两个套件。

### 8.2 板级构建（`pio run -e <env>`，真的编固件）

| 仓库 | 版本 | 实跑 env | 结果 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | `815e000` | `esp32_twai`、`m5stack-atomic-can-base`、`feather_m4_can`、`feather_rp2040_can` | **3/4**；`feather_rp2040_can` 因失效包名失败（见下 B 组第一条） |
| `JordanzhaoD` | — | `waveshare_single_can_standalone`（`esp32s3box`，16MB） | **SUCCESS**，RAM 15.3% / Flash 28.8% |
| `flipper-tesla-fsd` | **`6a3404f`**（beta.33，HEAD 的前一版） | `waveshare-s3-can` + 其余 9 个 | **10/10** |
| `ev-open-can-tools` | `6d37392`（`dev`） | `waveshare_ESP32_S3_RS485_CAN`、`esp32_ext_mcp2515`、`esp32_twai` | **3/3** |
| **合计** | | **18 次板级构建** | **17/18**，唯一失败是 `feather_rp2040_can` 的失效包名 |

各 env 的 RAM / Flash 占用率见 11.6 的对照表，此处不重复；本节只给"能不能编出来"这个结论。

**上表里出现过的 ESP32-S3 目标全部通过**，其中 `TX=GPIO15`、`RX=GPIO16` 这组引脚由 `flipper`（`esp32/README.md:159`）与 `ev-open`（`platformio.ini:163-164`）两家独立给出、交叉印证；`tesla-open-can-mod` 一个 S3 目标都没有（见 11.6，它的四个 env 是 ESP32、RP2040 与 SAME51）。这是"能编译通过"的最强证据——不是读 README 说的，是链接器和 esptool 说的。

### 8.3 环境与六条报错

环境：Windows 11，2026-09-30 至 2026-10-01，PlatformIO Core 6.2.0，Python 3.12.10（须 `PYTHONUTF8=1`，否则 `minify_dashboard.py` 因默认编码失败），主机编译器 MinGW-w64 GCC 16.2.0，代理 `http://127.0.0.1:10808`。8.1、8.2 两表于 2026-10-01 实跑，其中 flipper 停在 `6a3404f`、另两家停在第 0 节钉死的 commit（缺口见 8.4）。

六条报错按性质分两组。A 组四条是 onboarding / 环境类，照做就能过：

| 报错 | 出处 | 处理 |
| --- | --- | --- |
| `Missing platformio_profile.h` | `ev-open`、`JordanzhaoD` 共用同一套 onboarding | `copy platformio_profile.example.h platformio_profile.h` |
| `platformio_profile.h must enable exactly one driver define` | `JordanzhaoD`，示例默认解的是双 CAN 变体 | 双 CAN 的 env 要改成只解 `DRIVER_TWAI` |
| `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa6` | `ev-open` `scripts/minify_dashboard.py` | `set PYTHONUTF8=1` |
| `ModuleNotFoundError: No module named 'csscompressor'` / `'rjsmin'` | `JordanzhaoD` 网页压缩脚本没声明依赖 | `pip install csscompressor jsmin rjsmin` |

**六条报错里，四条落在对照仓或本机环境，只有 B 组那两条指向仓库自身。** A 组四条按"照做就能过"的性质归在一起，其中两条出自 `JordanzhaoD`（对照仓）、一条出自 `ev-open`、一条是本机编码——它们不构成对三仓质量的判断。

B 组两条，是仓库或环境自身有误，与操作无关。第一条是 `tesla-open-can-mod` 的失效包名——与第 12 节的 X179 矛盾、第 13 节的两处裂缝同类，都是文档/配置与现实对不上：

```
*** UnknownPackageError: Could not find the package with 'autowp/MCP2515' requirements
GET .../v3/packages/autowp/library/MCP2515  →  404 NotFound
GET .../v3/search?query=autowp             →  autowp/autowp-mcp2515  v1.3.1
```

`platformio.ini:7` 改成 `autowp/autowp-mcp2515` 后 `feather_rp2040_can` 立刻通过。第二条是 `ev-open` 的 `plugin_engine.h:747` 缺 `strlcpy`（详见 4.6）。另有 `Got the unrecognized status code '403'` 一条，是我下载工具链时的网络问题，配本地代理后恢复，与仓库无关。

### 8.4 没有做的事，以及"编译通过"的边界

**没做的四件**：没有烧录（`--target upload` 一条未执行）、没有连车、没有验证任何一帧在真实总线上会被接受；另有两项未跑——`dev` 的测试矩阵、flipper 的 `ffbb24e`（827 条在 `6a3404f` 上）。

**编译通过不等于能用。**编译只证明语法、模板、链接成立，不证明任何 CAN 帧语义正确；那一千多个用例断的是开发者自己写的预期——能证明"代码符合作者意图"，不能证明"作者的意图符合车端实际"。因此本文关于"车会怎么反应"的句子仍是社区回报，第 9 节的结论一个字都不用改。

### 8.5 复现本文所需的命令

本节把散在各处的操作收在一处。三仓的 commit 见第 0 节那张表——**行号只在这些 commit 上成立**，换 commit 需重新核对。

**通用前置**（Windows，我本机的配置）：

```powershell
$env:PYTHONUTF8 = "1"        # 否则 minify_dashboard.py 与部分脚本按 GBK 解码失败
pio --version                 # PlatformIO Core 6.2.0
python --version              # 3.12.10
```

**`1-v-1/tesla-open-can-mod`（`815e000`）——宿主测试与板级构建**

```bash
git clone https://github.com/1-v-1/tesla-open-can-mod.git && cd tesla-open-can-mod
git checkout 815e000
pio test -e native            # 107 次执行，99 条断言（2.8 节的表）
pio run -e esp32_twai         # 板级构建；原样 clone 会因 RP2040CAN.ino 未解驱动宏而失败（13.3）
```

**`hypery11/flipper-tesla-fsd`（`ffbb24e`）——宿主测试与板级构建**

```bash
git clone https://github.com/hypery11/flipper-tesla-fsd.git && cd flipper-tesla-fsd
git checkout ffbb24e
make -C test check            # 两个宿主套件：C 版 test_fsd_core + C++ 版 test_esp32_core
cd esp32 && pio run -e waveshare-s3-can                 # 板级构建：这条我真编过（8.2）
cd esp32 && pio run -e waveshare-s3-can -t upload -t monitor   # 烧录+看串口：这条我【未】实跑，照文档抄的
```

**`ev-open-can-tools/ev-open-can-tools`（`6d37392`，`dev` 分支）——宿主测试与板级构建**

```bash
git clone https://github.com/ev-open-can-tools/ev-open-can-tools.git && cd ev-open-can-tools
git checkout 6d37392
cp platformio_profile.example.h platformio_profile.h   # 不复制则所有 env 报 Missing platformio_profile.h
pio test -e native            # 10 个 native env，249 个用例；其中 2 个套件在本机 MinGW 下编不过（4.6 节）
pio run -e waveshare_ESP32_S3_RS485_CAN
```

**我只做了不接硬件的部分**：宿主测试全部在本机跑过，板级构建也真编了固件，但**没有对任何仓库执行过 `--target upload`**。上面代码块里凡带 `-t upload` 的都是照文档抄的未跑命令，其余为实跑（8.4）。

## 9. 兼容性：一个诚实的未知

这一节的问题本文无法作答；可复现的部分止于下一小节的 grep 结果。

问题：2025 款 Model 3（China HW4.0、OTA 2026.2.11）该编哪个宏？

### 9.1 先给 grep 结果（可复现）

对三个仓库的全部文本文件（`.md` / `.h` / `.c` / `.cpp` / `.ino` / `.ini` / `.py` / `.fam` / `.yml` / `.txt`）执行了三个关键字的扫描，扫描文件数分别是 31 / 117 / 103：

| 关键字 | `tesla-open-can-mod` | `flipper-tesla-fsd` | `ev-open-can-tools` |
| --- | --- | --- | --- |
| `2026.2.11` | **0** | **10** | **0** |
| `X179` | **17** | **104** | **0** |
| `China` | **0** | **51** | **1** |

这张表本身就是一个结论：只有 `flipper` 记录了这个版本号，也只有它和 `tesla-open-can-mod` 讲 X179。`ev-open` 三项近乎全空——它讲 OBD-II 与板载端子，`China` 那唯一一条是 `include/can_helpers.h:163` 的注释。

### 9.2 但 flipper 那 10 处，没有一处是这台车

**这 10 处全部落在文档与 issue 模板里，源码文件（`.c` / `.cpp` / `.h` / `.ino`）零命中。**这一点很重要：**文档记录版本，源码判断版本——而源码那半边不存在**。编译期写下 `HW4` 就是 `HW4`，程序不看车、不看 OTA、不看地区。

真正有信息量的是两条，**都是 Model Y**，外加 `.github/ISSUE_TEMPLATE/bug_report.yml:37` 把它当作版本号的 `placeholder`（被当成"典型的当前版本"写进了报障模板）：

```
README.md:285   | Model Y 2023 (China, MIC) | HW3 | 2026.2.11 | Community | FSD (Force FSD mode) |
changelog.md:243 ... @Tikernel + @ViPiMP (positive compat data: Model Y Juniper HW4 2026.2.11 China, HW4 2026.8.3 Germany).
```

**同一个 `2026.2.11` 在同一份文档里同时挂着 HW3 和 HW4。**不同车型、不同年款可以停在同一个 OTA 版本上——这恰恰说明版本号本身推不出硬件代际。而 **Model 3 这个车型，两条里一条都没有**。

### 9.3 那文档呢？文档只差一点就答上了

**全仓唯一一条带版本阈值的规则**在 `README.md:69`（`tesla-open-can-mod`），原文如下：

> **Note:** HW4 vehicles on firmware **2026.2.9.X** are on **FSD v14**. However, versions on the **2026.8.X** branch are still on **FSD v13**. If your vehicle is running FSD v13 (including the 2026.8.X branch or anything older than 2026.2.9), compile with `HW3` even if your vehicle has HW4 hardware.

照这条规则推：`2026.2.11` 不早于 `2026.2.9`，也不在 `2026.8.X` 分支上，所以该编 `HW4`。**但这是机械外推、不是结论**——下面两条推力足以掀翻它，10.1 节也因此提醒"硬件是 HW4"读不成"该编 HW4 宏"。

**其一，`2026.2.11` 不等于 `2026.2.9.X`。** README 写的是补丁位通配（`2026.2.9.11`），实车版本是次版本位（`2026.2.11`）。两者能否对上，README 未作说明，源码中也没有解析器完成该判定。

**其二，同族阈值互相打架，而且 flipper 自己的兼容表压根没有这台车的位置。** 按 `ffbb24e` 读它 `README.md:278-293`，相关的四行：

| 出处 | 内容 | 等级 |
| --- | --- | --- |
| `tesla-open-can-mod` `README.md:69` | `2026.2.9.X` 起是 FSD v14；`2026.8.X` 仍是 v13，跑 v13 就编 `HW3` | 一手（仓库文档原文） |
| `flipper` `README.md:286` | `\| Model 3/Y 2023+ \| HW4 \| **< 2026.2.9** \| ... \| FSD \|` | 一手（仓库文档原文） |
| `flipper` `README.md:293` | `2026.8.6 HW4` → HW4 注入路径坏掉 → 用 Force HW3 | 一手（仓库文档原文） |
| `flipper` `changelog.md:243` | `Model Y Juniper HW4 2026.2.11 China` 正面数据（车型是 Model Y） | 社区回报（`@Tikernel` + `@ViPiMP` 的实车回报） |

**四行的"等级"要分两层读。**前三行是我逐字读过的仓库文档（引文一手），但按仓库自己在 `esp32/README.md:422` 的声明，兼容性表来自 field reports，**底层依据仍是社区回报**；第四行连引文都是他人实车结论。**这张表是全文最容易被误读的地方**：它的形式像矩阵，但没有任何一行经过第三方仲裁。

**叠起来看，本文这台车正好卡在两条数据的中间，两条都不覆盖它**：flipper 唯一一条"Model 3 + HW4"的正面数据版本范围是 `< 2026.2.9`，这台车 `2026.2.11` 掉在范围外；唯一一条"HW4 + 2026.2.11"的车型却是 Model Y Juniper。**两个条件各有一条数据，没有一条同时覆盖两者的车型。**

外部项目的阈值还在流：`herrfrei`、`juamiso` 用 **2026.2.3** 作 FSDV14 分界，`jvanakker` 镜像标注 **2026.8.6 对 2026.2.9.x 及更高已失效**——同一条分界线上两个版本号在流，同一个 `2026.2.9.x` 一边"正常支持"一边"已失效"。未必矛盾（FSDV14 可能分批推），但对照着选宏的读者要吃下六个版本号的分歧。

另注：`jvanakker` 那条标注挂在 CanFeather 原始固件的镜像 README 上，**指涉对象不是本文第 2 节的样本代码**（见第 0.3 节）。

flipper 那三行我在 `ffbb24e` 上逐行读、可 grep 复现；其余三个按 URL 与页面日期记录、我没 clone 核验，都是一线用户的单点回报，无第三方仲裁。

**两个结论要分开。**可验证的：三仓源码里没有版本→宏的映射（`2026.2.11` 在 flipper 的 10 处命中全在文档里，源码文件 0 处），文档里有规则和兼容矩阵，但没有一条同时命中这台车的三个条件——任何人重跑都能复现。不可验证的：`2026.2.11` 该编哪个宏？我没有板子、线束、车，无法验证——这是第 0 节证据约定最后一行写的方法边界。

因此本篇只写到"仓库的指南到此为止"（第 14 节），不写"照这个编就能用"。

---

# 第五部分 · 一台具体配置的实践

前面三部分是通用的。从这一节起，所有判断挂在一个具体配置上：China、HW4.0、2025 款 Model 3、软件版本 2026.2.11。

## 10. 先把车钉死：这台车意味着什么

把四个词拆开，各自带出一条硬约束。

### 10.1 `HW4` 三个字，先排掉两个选项

**这一步只做减法。**2.6 节讲过校验和是 HW4 独有的一支，2.4 节的表也列了——三个宏只有 `LEGACY` / `HW3` / `HW4`。配置里"China HW4.0"这一项直接决定：**Legacy（HW1/HW2）那条路不相关，选型只在 HW3 与 HW4 之间二选一。**

**但减法做完不能顺手选 HW4。**第 9.3 节引的规则里，即使硬件是 HW4，车若跑在 FSD v13 上仍应编 `HW3`（`README.md:69`）——也就是说**宏的选择还取决于这车跑的是 v13 还是 v14**，而第 9 节查下来**没有任何一行正面数据能覆盖这台车的三个条件**。**硬件代际由配置给定，编译宏却未必**——这是 10.1 落到实践时最容易被跳过的一步，第 9 节整节不给出答案也是因为它。

### 10.2 2025 款 Model 3，第一件该确认的事是 OBD-II 口上是不是 CAN

`flipper` `HARDWARE.md:39`（`ffbb24e`）：

> **April 2024+ Juniper Model Y / refreshed Model 3 Highland (later builds)**: Tesla switched to **DoIP** (Diagnostic over IP) — the diagnostic port now carries 100 Mbps Ethernet, **not** CAN.

紧接着 `:38-42` 是一条 CAUTION，大意是不要把基于 CAN 的 OBD-II 适配器或诊断仪接到 DoIP 口上——电平不兼容，可能损坏车辆的诊断模块；2024+ 的车直接接 X179。

**结论直接落到动作上**：2025 款 Model 3 属于改款后的批次，**按 DoIP 处理，不要往 OBD-II 口插 CAN 适配器试**——这是仓库写在 CAUTION 里的判断顺序，不是我的推断。要接就走 X179（12.1 讲怎么找到它）。

同一节另有一个限定，读者别忽略：DoIP 迁移的分类轴是**生产日期与地区**，不是"改款与否"；适用范围仓库自陈 "not yet pinned down"。也就是说"2025 款"这三个字本身不足以判定，12.7 第 3 步的 Service Mode 对账才是最终判据。

### 10.3 X179 的 pin→bus 映射不固定，而唯一的确定判据在车机里

`HARDWARE.md:98`："The X179 pin→bus map is NOT fixed across builds — verify it on your own car." 至少存在四种电气配置，而且"按年款推断不可靠"。

**仓库给的确定判据只有一条**（`:104` 起）：车机的 Service Mode → CAN Port 页面，它按线束料号逐针列出所属总线。仓库举的例子是 harness `1933903-XX`（`:105`，Model Y Juniper RWD 2025，FW 2026.14.3）：`2/3 = Party`、`9/10 = Vehicle`、`13/14 = Chassis（绿线），不是"Bus 6"`、`20 = GND`。

**那是 Model Y，不是本文这台 Model 3——所以那个例子只能当格式样例，不能当答案。**这一节落到具体车辆上的第一步动作因此很具体：**先打开 Service Mode 的 CAN Port，把针号记下来，再动线**（12.7 第 3 步）。

### 10.4 生产日期早于 SOP10，但早于 SOP10 不等于 pre-April-2024

**先排除一档。**`HARDWARE.md:225` 的 SOP 时间线里，上海是 2026-03-25（SOP11），柏林 2026-04-01，奥斯汀 2025-12-04，弗里蒙特 2025-12-09。2025 年产的车在这条线之前，因此不属于 post-SOP10 那一档。

**但排除掉不等于落在另一张表上。**post-SOP10 那一档排除之后，"pre-April 2024"那张表也接不住——那张表要求的是 2021–2023 与 2024 早期批次。**2025 年产的车落在 post-April-2024 档，而那一档的实测数据是单点**（`:212`："This is a single empirical data point"）：

| Pin | 柏林产 EU Model Y 实测（`HARDWARE.md:204-210`） | 等级 |
| --- | --- | --- |
| 9 / 10 | DoIP（以太网），**不是 CAN** | 社区回报 |
| 12 / 13 | DoIP，**不是 CAN** | 社区回报 |
| **18 / 19** | **Vehicle CAN，唯一可用的 CAN 对** | 社区回报 |
| 15 | +12V（不变） | 社区回报 |
| 26 | GND（不变） | 社区回报 |

**五行全是"社区回报"的原因**：等级约定见 0.2 与 15 章开头。这张表全部来自 issue `#52` 一个人的示波器实测，仓库自己标注 "single empirical data point"——**这是全文证据等级最低的一张表，接线前务必以自己车的 Service Mode 为准。**

那台车是 `@0n3-70uch` 量的（issue `#52`，Berlin 产 pre-Juniper、post-April-2024，FW 2026.14.3）。仓库自己给的三条安全建议（`:220` 起）：接收发器前每一对都用示波器验一遍；13/14 的 120Ω 检查不过就改试 18/19；+12V（15）与 GND（26）跨 SOP 稳定。**这三条我一条都没执行**——板子、线束、示波器一样都没有（实测边界见 0.2）。

### 10.5 把四个词合成一句话

上面四小节各钉死一条约束，合起来就是本文全部选型前提：

| 词 | 推出什么 | 出处 |
| --- | --- | --- |
| **HW4.0** | 排掉 Legacy，只在 HW3 / HW4 之间选；且硬件代际 ≠ 编译宏 | 10.1 |
| **2025 款 Model 3** | OBD-II 口按 DoIP 处理，不插 CAN 适配器试 | 10.2 |
| **China** | 走 X179，针号以本车 Service Mode 为准 | 10.3 |
| **2026.2.11** | 目前唯一正面数据来自 Model Y，**本文不据此下结论** | 9.3 |

> **这台车的选型前提：HW4 走 HW4 路径；OBD-II 口默认按 DoIP 处理、直接接 X179；X179 先开 Service Mode → CAN Port 记针号，再接线；版本 2026.2.11 上目前唯一的正面数据来自同代际、同地区、同版本但不同车型（Model Y）的社区回报。**

## 11. 选什么、买什么

### 11.1 先说推荐

**主方案：`hypery11/flipper-tesla-fsd` 的 `waveshare-s3-can`**（微雪 ESP32-S3-RS485-CAN，即 11.2 那块板配它的固件）。三个理由，按可验证性递减：

1. **它是三家里唯一记录 `2026.2.11` 的**（10 处命中，另两家 0），而且 `HARDWARE.md` 对 DoIP / X179 / Service Mode 的记载最细（104 处 X179）。
2. **它的 ESP32 侧业务代码有独立的一套测试在跑**（179 条打 C++ 版，3.1、3.8），不是抽出来的副本。
3. **它在查询当天仍在提交**，而 `tesla-open-can-mod` 已经 183 天没动。

**但推荐一个东西必须同时写出它的代价：** 它的"Model 3 + HW4"记录版本范围不覆盖这台车（第 9.3 节的两个条件各有一条数据、型号还差一档）；而且它是三家里唯一明确记录 VIN 级封禁的（见第 14 节）。

### 11.2 主方案清单

| 项 | 内容 |
| --- | --- |
| **买哪一块** | 微雪 **ESP32-S3-RS485-CAN**。官方商城 `https://www.waveshare.net/shop/ESP32-S3-RS485-CAN.htm`；**该站有反爬，直接打开可能只返回一段 JS**，价格以页面实际显示为准 |
| 国际站同款 | `https://www.waveshare.com/esp32-s3-rs485-can.htm`（另有 `-U` 外置天线版） |
| 规格一手出处 | Wiki：`https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN` |
| 第三方同款参考价 | `https://www.spotpear.cn/shop/.../ESP32-S3-RS485-CAN.html` 标 **¥99**（页面日期 2025-08-14） |
| 对应构建目标 | `waveshare-s3-can`（`esp32/README.md:159` 明列，TX=15 / RX=16 / LED=46 / BTN=0）。**注意 flash 规格两处来源不一致**：上游按 **8MB flash/PSRAM** 配置该 env（`esp32/platformio.ini:185-189`），而厂商 wiki 标 **16MB Flash / 8MB PSRAM**（下一段）。按 8MB 配置在两种板子上都不会出错，按 16MB 配置则必须先确认手上这块的实测容量 |

**价格跨度很大，同一块板差近三倍。**2026-10-01 检索到的**电商商品页**报价（完整 URL 见 15.1）：

| 站点 | 报价 | 备注 |
| --- | --- | --- |
| Sunsky | **$19.46** | 2 件起 $19.30，全表最低 |
| MiOT | $22.79 | 未保留深链 |
| Amazon | $26.87 | — |
| eBay UK | $32.98 | — |
| Newegg | $53.99 | 未保留深链 |
| 微雪官方商城 | ¥99.99 | 2 件 ¥96.96；该站有反爬，可能只返回一段 JS |
| elty | €19.71 | 卖的是 `-U` 外置天线版，不是同一块板 |

**比价之前先按下一段的规格核对是不是同一块板**（flash / PSRAM 容量、是否带天线），否则价格不可比。

其余板子、降压模块与 Flipper 那一路的仓库原始链接集中在 15.1 那张表的「非一手」各行，此处不重复。

从 wiki 核实的规格（不是我推断的）：主控 ESP32-S3R8，LX7 双核 240MHz，2.4GHz WiFi + BLE 5；16MB Flash / 8MB PSRAM；板载隔离 CAN（端子 + TVS + 浪涌 + ESD + 指示灯）；120Ω 匹配电阻默认 `NC`（断开）、跳线帽使能——正好符合 `HARDWARE.md:633` 的"不要加第二个 120Ω"；端子供电 7V ~ 36V，另有 USB Type-C 5V；导轨式外壳 91.6 × 23.3 × 58.7 mm。

> ⚠️ **wiki FAQ 原文**："Can I power the board using both the terminal block and the USB interface simultaneously? **No, this may risk damaging the module.**"——螺丝端子供电与 USB **二选一**。

> ⚠️ **微雪自己的法律声明**（wiki「Warning」栏）：本产品仅用于合法的开发、学习、研究与工业用途，**严禁将任何 CAN 总线用于未经授权的破解、篡改、解锁或功能劫持**，否则可能构成违法、用户自负全部法律责任——厂商原话，我照译放在这儿。

### 11.3 线材与小件

| 件 | 用途 | 价格与链接 |
| --- | --- | --- |
| **USB-A → Type-C 数据线** | 烧录 + 5V 供电 | 必须是**数据线**（不带数据脚的充电线刷不进去）。仓库与微雪 wiki 都不给链接；微雪包装清单只含 4pin 线与小螺丝刀、**不含 USB-C 线**（Newegg 商品页 Package Content，**电商商品页**，访问 2026-10-01） |
| **X179 4 芯线束** | CAN-H / CAN-L / +12V / GND | 仓库只写 `"X179 pigtail cable (4-wire)"` 并计 `~$3-5`（`HARDWARE.md:396`、`:411`、`:422`、`:453`），**不给链接**；采购时按官方页的车端护套规格 `KSE K30M31014` 找对插端 |
| 万用表 | 量终结电阻、量 12V 是否常电 | `HARDWARE.md:646`、`:659` 都要求这一步 |
| （可选）示波器 | 验每一对是 CAN 还是 DoIP | `HARDWARE.md:220` 的第 1 条建议 |
| 一字螺丝刀 | 拧螺丝端子 | 微雪包装内附小螺丝刀 |

顺带记一个本文此前没提、但对新手最省事的入口：`ev-open` 另有一个独立的交互式引导站（`docs/onboarding.md:3` 指向的 GitHub Pages）。它按"一次只问一个决策"的方式走八步——选目标（观察 / 后续装插件 / SavvyCAN 记录 / 台架研究）→ 定车型年款与 Legacy/HW3/HW4 模式 → 比板 → 出配件清单 → 看安装区域示意 → **生成对应的 PlatformIO env 与构建命令** → 按安全顺序上电与观测 → 下载或打印个性化清单（`docs/onboarding.md:9-16`）。

它的边界也写得很清楚，值得一并知道：进度只存浏览器 `localStorage`、不联设备、不外传（`:18`）；那些插图**刻意不是连接器照片或引脚表**，因为连接器与总线归属会随车型、工厂与生产日期变化，接线前仍须以官方电气文档为准（`:22-24`）；整站只在 GitHub Pages 上、不属固件、也改不了设备配置（`:28`）。

### 11.4 不用买的东西

| 件 | 为什么不用 |
| --- | --- |
| **CAN 收发器** | 板载隔离 CAN，不用另配 |
| **120Ω 终端电阻** | `HARDWARE.md:633`：Tesla 的总线**已经终结**，别加第二个；微雪这块出厂就是断开的 |
| **降压模块** | 板子吃 7~36V，X179 的 12V 直接进端子 |

### 11.5 备选（`HARDWARE.md:386-563` 的五套，价格是仓库标出的美元）

| 方案 | 内容 | 仓库标价 | env |
| --- | --- | --- | --- |
| **A 最便宜全功能** | ESP32-C3-SuperMini / DevKitC + MCP2515(TJA1050) + X179 线 | `:388` ~$8–12 | `esp32-mcp2515` |
| **B 即插即用** | M5Stack ATOM Lite + ATOMIC CAN Base | `:405` ~$16–20 | `m5stack-atom` |
| **C 双 CAN** | LILYGO T-2CAN ESP32-S3 | `:417` ~$27–29 | `lilygo-t2can` |
| **D 带屏** | TTGO T-Display + MCP2515 + XY-3606 降压 | `:437` ~$17–26 | `ttgo-tdisplay` |
| **E 原版** | Flipper Zero + Electronic Cats CAN Add-On | `:541` ~$205–245 | `.fap`，走 `ufbt` |

**标价不是我查的**，是 `HARDWARE.md` 自己写的美元数（`:388`、`:405`、`:417`、`:437`、`:541`），下单前按各自的商品名另核一遍价。**方案 E 与本文主方案不是同一类东西**：它跑的是 Flipper 端固件（13.1 路线 B），不是 ESP32 固件，成本高一个数量级，买它是为了"原版手感"而非性价比。

方案 C 值得单独说：T-2CAN 是双路独立 CAN（原生 TWAI + 外挂 MCP2515）。第 10 节那张 post-April-2024 实测表显示"唯一可用的 CAN 对是 18/19"，而 `HARDWARE.md:278-286` 又指出 `0x3C2` 只在 9/10 或 OBD-II 6/14 上可见、13/14 上根本没有——单路板接错对就没辙，双路板可以一路接 X179 18/19、另一路留着。

### 11.6 三个仓库对 ESP32-S3 的支持实践

ESP32-S3 是这三家唯一共同支持的平台族，因此值得单独对照。下表全部来自三个仓库在第 0 节钉死 commit 上的 `platformio.ini` 与 `esp32/README.md`。

| | `tesla-open-can-mod` | `flipper-tesla-fsd`（`esp32/` 端口） | `ev-open-can-tools` |
| --- | --- | --- | --- |
| 框架 | Arduino（`platform = espressif32`，未锁版本） | Arduino-ESP32 **2.0.x**，锁 `espressif32@6.9.0`；`:61` 注释说明 3.x 会在经典 ESP32 上撑爆 dram0，故不升 | **ESP-IDF**（基线 env `espidf_dashboard`，`:19-22`） |
| S3 目标数 | **0** | **2**：`waveshare-s3-can`、`lilygo-t2can` | **4**：`waveshare_ESP32_S3_RS485_CAN`、`lilygo_t2can`、`esp32_ext_mcp2515`、`m5stack-atoms3-mini-can-base` |
| 其他代际 | RP2040（`feather_rp2040_can`）、SAME51（`feather_m4_can`） | 经典 ESP32 多个 env；`:162` 明写**没有 C3 env** | 另覆盖 **S2**（`:42`）与 **C6**（`:55`），代际最宽 |
| S3 的 board 映射 | 不适用 | `esp32-s3-devkitc-1`（通用 S3 开发板定义） | `esp32s3box` / `esp32-s3-devkitc-1` / `m5stack-atoms3`（用板型定义代替厂商定义） |
| flash 与分区 | **完全不声明** | 逐 env 显式：`waveshare-s3-can` 8MB + `default_8MB.csv`（`:185-189`）、`lilygo-t2can` 16MB + `default_16MB.csv`（`:130-134`） | 逐 env 显式 partitions，分 4MB / 8MB / 16MB 三档（`lilygo_t2can` 另设 `flash_size = 16MB`，NVS 64k） |
| 引脚策略 | 只有 `m5stack-atomic-can-base` 给了 TWAI 22/19，`esp32_twai` 一个引脚宏都没有，靠源码默认值 | 每 env 一套 build_flags；首启串口自检打印 `[CFG] pins: LED=.. BUTTON=.. CAN_TX=.. CAN_RX=..`（`esp32/README.md:170`） | 每 env 一套；MCP2515 走 SPI 四线并显式声明晶振（8MHz / 16MHz）、CS / INT / RST |
| 人机界面 | 串口打印 | Web 面板 + HTTP candump 流（端口 82）+ 物理按钮 + 首启引脚自检 + web OTA（15 秒确认、失败回滚） | 网页面板（4561 行）+ 插件引擎 + NVS 持久化引脚 |
| 实测占用 | `esp32_twai` RAM 14.6% / Flash 61.7%（**非 S3 目标**） | `waveshare-s3-can` RAM 37.4% / Flash 28.0% | `waveshare_ESP32_S3_RS485_CAN` RAM 22.6% / Flash 83.7%；`esp32_ext_mcp2515` RAM 22.7% / Flash 42.4% |

四条对读者最有用的结论：

1. **要 S3 只能在 `flipper` 与 `ev-open` 之间选。** 教学样本 `tesla-open-can-mod` 的 ESP32 目标 `board = esp32dev` 是初代 ESP32，与 S3 不是同一块芯片；要上 S3 得自己加 env，参照它 `m5stack-atomic-can-base`（`:27-30`）的写法改 `board` 与两个 `TWAI_*_PIN` 即可，业务代码不动。
2. **同一块微雪 ESP32-S3-RS485-CAN，两个项目给的 flash 预算差一个量级。** flipper 按 8MB 分区、实测占用 28.0%；ev-open 按 4MB OTA 分区、实测占用 83.7%。**选 ev-open 就意味着后续加功能前先算分区余量**。
3. **flash 容量以手上板子为准。** 上游 README 与 `platformio.ini` 按 8MB 配，厂商 wiki 标 16MB（11.2 已记录两处来源）；两套配置里 8MB 那套是保守解。
4. **跨代际覆盖是 ev-open 的独有优势。** 它同时给出 S3 四个、S2 一个、C6 一个；flipper 明说没有 C3 env（`esp32/README.md:162`）；tesla-open-can-mod 连 S3 都没有。

本节表内行号均指各仓库钉死 commit 的 `platformio.ini`：`tesla-open-can-mod` 为第 0 节第一行 commit，`flipper-tesla-fsd` 为 `esp32/platformio.ini`（`README.md` 行号未加前缀），`ev-open-can-tools` 为 `dev` 分支第 0 节第三行 commit。

## 12. 接线：从 X179 到螺丝端子

### 12.1 X179 在哪——三份文档，三种口径

![X179 在车上的位置：三份文档的三种口径](images/can-mod-teardown-2026/s04-x179-location.svg)

图 5｜X179 在车上的位置：`flipper` 给出了「怎么进去」的一步，另两份指南互相矛盾。

**先给本文采用的口径**（下节会说明为什么不能直接抄 `tesla-open-can-mod` 的）：`flipper` `HARDWARE.md:92` 的小标题是 `X179 — behind the rear center console (2021+ Model 3/Y)`，即**后排中控台后方**；`:94-95` 给出进入方式："Tesla's own service/diagnostic connector. Requires removing a trim panel behind the rear armrest." —— 拆掉后排扶手后方的饰板。`flipper` 根 `README.md:210` 同口径，且标为 recommended。外部有一处厂商目录页也站在这一侧（12.1 后半段）。

但 `tesla-open-can-mod` 的两份指南互相矛盾，这一处最"物理"——照错了连地方都找不到：

`guides/INSTALLATION_GUIDE_M4_CAN.md:57`：

> The Enhance Auto Gen 2 Cable plugs into the **X179 connector**, located behind the **driver's side trunk panel**.

`guides/WIRING_GUIDE.md:16`：

> The X179 connector is located on the **passenger side footwell**, behind the panel on the right.

一个说驾驶侧后备箱饰板后，一个说副驾脚部空间右侧饰板后——方向完全相反。三仓全量 grep `footwell|trunk panel` 命中 5 处：除上面两条外，`guides/WIRING_GUIDE.md:18` 的 `right-side footwell panel trim` 与第二条同源；`flipper` `HARDWARE.md:75` 与 `ev-open` `docs/onboarding.md:22` 两处都只给泛化区间、不构成独立口径。

**三条线索都指向"后排中控台"，但没有一条能仲裁那两份指南：**

1. **没有任何一处能仲裁**——连 `tesla-open-can-mod` 自己的 `README.md:301` 也只给 service.tesla.com 的 X179 文档链接，不写文字位置。
2. **外部有一处独立佐证站在这一侧**：PAC 的 `CP1-TSL1` 商品页把产品描述为 "For 26-Pin Connector at Back Of Center Console"（厂商目录页 `https://catalog.archive.pac-audio.com/catalog/can-integration/cp1-tsl1`，页面标价 $49.99，访问于 2026-10-01，**厂商商品页**）。但它是卖适配线的厂商，说的是自家产品的适配位置。
3. **Tesla 官方页管针脚、不管位置**：给出料号 `1849225-03-B`、护套 `KSE K30M31014`、色 `GY`、完整 pinout 表与一个 `Connector Location` 图示栏位（`https://service.tesla.com/docs/Model3/ElectricalReference/prog-233/connector/x179/`，**一手**）——pinout 可用来核对下一小节的引脚表，**位置文字仍然只能靠 Service Mode**。

而两份指南自称的车型还是一致的：`guides/INSTALLATION_GUIDE_M4_CAN.md:3` 写"2023 Tesla Model 3 with HW3"，`guides/WIRING_GUIDE.md:5` 写"Photos were taken on a 2023 Model 3 (non-Highland)"。同一台车，两个位置。

**这两类文档错误的代价完全不同，读者要区别对待。**13.3 那两处是"文档指向不存在的 API"——编译期就报错，当场发现，改一行就好；**这一处是"文档指向错误的物理位置"，没有任何编译器或 grep 会拦你**，后果是拆错饰板、耗时而无从定位。

两份指南都附了 Enhance Auto 的实拍视频，**实车动手前以视频为准，不要以文字为准**。

**所以本文接下来的操作一律按"后排中控台后方"走**（12.7 第 2 步）；真找不到再依次排除另两处说法。

### 12.2 引脚表（仓库原文，**不是实车实测**）

**这一节是全文最容易引错的一节**：下表按连接器分两批，**20-pin 与 26-pin 的针号完全不同、不可互换**（`HARDWARE.md:162` 原话 "They are not interchangeable."）。动手前必须先确认自己车上是哪一种——认错的代价是接错线，不是编译报错。

20-pin（2021–2023 Model 3/Y，`HARDWARE.md:130-158`，表体 `:140-150`）

| Pin | 信号 | 总线 | 等级 |
| --- | --- | --- | --- |
| **1** | **+12V** | 电源 | 一手（仓库文档原文） |
| 2 / 3 | CAN-H / CAN-L | Party CAN | 一手（仓库文档原文） |
| 9 / 10 | CAN-H / CAN-L | Vehicle CAN | 一手（仓库文档原文） |
| **13 / 14** | **CAN-H / CAN-L** | **Chassis CAN**（线束 `1933903-XX`；旧注作"Bus 6"） | 一手（仓库文档原文） |
| **15** | **+12V** | 电源（2mm² 线，pin 1 的替代） | 一手（仓库文档原文） |
| 18 / 19 | CAN-H / CAN-L | Chassis（EPAS/刹车） | 一手（仓库文档原文） |
| **20** | **GND** | 地 | 一手（仓库文档原文） |

**"一手"只指引文，不指事实。**我在 `HARDWARE.md` 原文上逐字读过这张表，所以引文可查；但仓库自己在 `esp32/README.md:422` 声明过这类表来自 field reports，因此底层依据仍是社区回报。两层要分开看：**引文可查，事实未验**——而且这张表讲的是 2021–2023 的 20-pin，本文这台 2025 款大概率是 26-pin，真正要照着接的是下面那一张。

**13/14 那一行要按原文纠正一个流传很广的说法：**它不是"网关转发出来的混合总线子集"。`HARDWARE.md:116-120`：

> This **relabels** the older "Bus 6 on pin 13/14" framing: on this harness 13/14 is Chassis CAN, which is why `0x370 EPAS3P` shows there at 100 Hz with full counter continuity (EPAS lives on Chassis) — it was never a gateway-forwarded subset. **`0x370` is on Chassis CAN, not Vehicle CAN** — if you tap Vehicle CAN (9/10) you will not see `0x370`.

`HARDWARE.md:252-256` 同样把「gateway-forwarded mix of buses」标为 Older notes，并给出这一对在 `1933903-XX` 线束上的 Service Mode 结论：Chassis CAN。原文补了一句 —— The pin→bus map varies, so check Service Mode → CAN Port on your own car.

**26-pin：本文这台车该看这一档。**`HARDWARE.md:159` 起分两批，`:162` 明确写着 `"They are not interchangeable."`：

| 批次 | 出处 | 内容 |
| --- | --- | --- |
| pre-April-2024 | `:176-183`（段落自 `:171` 起） | 仓库文档表，本文未逐条抄录 |
| **post-April-2024** | `:204-210` | 示波器实测，就是 10.4 那张表：9/10 与 12/13 是 **DoIP 不是 CAN**，`:208` 只留一句 "Vehicle CAN — only working CAN pair"（即 18/19） |

本文目标车是 2025 款，落在 post-April-2024 那一档，所以 10.4 的实测表才是该照着接的那一张——注意它和上面 20-pin 表的 9/10 含义**相反**（20-pin 的 9/10 是 Vehicle CAN，26-pin 的 9/10 是以太网）。

另一只连接器：`tesla-open-can-mod` `README.md:310-317` 另给 2020 年及更早、未配 X179 的 Model 3 一条备选——X652（官方 `prog-187` 页），pin 1 = CAN-H、pin 2 = CAN-L。`flipper` 的 `ffbb24e` 检出根 README 未出现 X652；本文目标车（2025 款）也不适用，记录备查。

### 12.3 四根线怎么接

![四根线怎么接：X179 到螺丝端子](images/can-mod-teardown-2026/s05-x179-wiring.svg)

图 6｜选一对 CAN 与固定电源地，四根线进微雪板的螺丝端子；下方三个红框是接车前必查项。

`HARDWARE.md:316-319` 的原文示意：

```
X179 Pin 13 → CAN-H ──┐
X179 Pin 14 → CAN-L ──┤── CAN module (MCP2515 / TWAI)
X179 Pin 15 → 12V ────┤── buck converter → 3.3V/5V
X179 Pin 20 → GND ────┘   (26-pin: use Pin 26 for GND)
```

对微雪这块板，右侧那半简化掉：12V 直接进螺丝端子（板子吃 7–36V），GND 进另一个端子，CAN-H / CAN-L 进 CAN 端子，不需要降压模块。

**接哪一对，取决于第 10 节记下来的 Service Mode 结果，不由本文决定。**仓库为不同功能点名了不同总线，我按出处列出——**注意这三条各自的适用车型不同，照抄针号很容易接错**：

| 要做的事 | 仓库点名的针号 | 出处 | 对本文这台车（26-pin / post-April-2024） |
| --- | --- | --- | --- |
| nag killer | Party CAN **2/3** | `:123`："For the nag killer, tap Party CAN (pins 2/3)." | **大概率不适用**——该说法出自 20-pin 表，26-pin 上 2/3 是什么未经核实 |
| 注入 `0x3C2`（ScrollPress AP，1.4） | **9/10** 或 OBD-II **6/14**；13/14 上根本没有这一帧 | `:280-286` | **9/10 在这台车上是以太网（10.4）**，所以这条对本文目标车基本走不通，只剩 OBD-II 6/14 一条未经核实的路 |
| 抓 `0x370`（EPAS 状态，nag 回声所在帧） | HW4-modern 上 `0x370` **不在 Vehicle CAN（9/10/11）** | `:299-305` | 两台车在 pin 9/10、10/11 上 60 秒内都是 0 帧，`0x370` 出现在 pin **13/14**；Service Mode 随后显示线束 `1933903-XX` 的 13/14 就是 **Chassis CAN** |

第三条原文还补了一句：把 nag echo 从 13/14 挪到 Vehicle CAN **够不着 EPAS**，对 HW4-modern 不可行。

**结论：这张表本身证明了一件事——针号必须以自己车的 Service Mode 为准。**同一份 `HARDWARE.md` 里，三个功能给出的三组针号互不相同，且其中两组按 20-pin 的口径写、本文这台 26-pin 车对不上。12.7 第 3 步就是为此设的。

### 12.4 终结电阻：不要加，并且要量一次

`HARDWARE.md:633`："Tesla's CAN buses are already terminated. Do not add a second 120 Ω terminator." 多数后装模块出厂带终结，接车之前先关掉——微雪这块出厂是 `NC`，不用动。

120 Ω 不是随手取的数：它是高速 CAN（ISO 11898）的**特性阻抗**，装在总线两端把接口阻抗匹配到线缆上，作用是抑制**信号反射**。反射叠加在有效电平上会变成误码，并直接推高错误帧计数——这正是第 12.6 节把"脱车量电阻"列为必查项的原因。

**怎么量（`:646` 的脱车量法）**：万用表打欧姆档，两支表笔分别碰 CAN-H 与 CAN-L。

| 读数 | 含义 | 动作 |
| --- | --- | --- |
| **~120 Ω** | 正常。车这一侧已经提供了终结 | 什么都不用做 |
| **~60 Ω** | 两个终结器并联了——外接模块自带的那个还开着 | 把模块上那个 120 Ω 断开（微雪这块出厂在 `NC`，不用动） |

**这一量法叫"脱车量"，意思是排除车这一侧的干扰、单独看板子加总线。**做法上就是把万用表两支表笔并到 CAN-H 与 CAN-L 上读欧姆（板子仍接在 X179 上，不需要拆线）。量出 60 Ω 说明板子上那个终结器还开着、把总线阻抗拉低了，继续接下去就会一直有错误帧。

### 12.5 供电三个坑

1. **OBD-II pin 16 是常电**，车锁了也供（`:653`）。ESP32 静态约 50mA × 12V ≈ **0.6W 持续**，几天能把 12V 电池放干。
2. **X179 pin 1/15 行为不一**（`:659`）：有的车随唤醒门控、有的常电，**仓库原话是"先用万用表测再依赖它"**。
3. **螺丝端子供电与 USB 不能同时**（微雪 wiki FAQ），二选一。

永久安装走深睡（`:665` 起）：5 分钟无帧 → 深睡约 10µA。

### 12.6 上电之前的静态检查

| 检查 | 依据 | 判据 |
| --- | --- | --- |
| 脱车量 CAN-H↔CAN-L | `HARDWARE.md:646` | ~120Ω 正常，~60Ω 要关终结器 |
| 万用表量 12V | `HARDWARE.md:659` | 确认 1/15 哪一路有电 |
| 示波器量每一对 | `HARDWARE.md:220` | 区分 CAN 与 DoIP |
| 服务模式记针号 | `HARDWARE.md:104-105` | CAN Port 页按料号列针 |
| 确认端子/USB 只走一路供电 | 微雪 wiki FAQ | 同时接可能损坏模块 |

### 12.7 端到端操作序列：十一步

**这一节是全文的操作入口。**上面六小节按主题拆开（找位置 / 认针号 / 接哪对 / 电阻 / 供电 / 静态检查），彼此有交叉、没法照着做；下面这一条按执行顺序合成一条线，每步给出动作、通过判据与出处。

**分界在第 5 步与第 6 步之间**：前五步不带电、可以反复重来；第六步起才带电，且**供电路径唯一**（12.5 第 3 条：端子与 USB 二选一）。第 9 步是整条链上唯一的 go / no-go 判据，第 11 步是最容易漏掉的一步。

![端到端操作序列：从选料到选硬件模式的十个步骤](images/can-mod-teardown-2026/s06-procedure.svg)

图 7｜十个步骤，前五步车外准备、后五步上电验证；第 9 步是整条链上唯一的 go / no-go 判据。（图里画的是十步，**表里多出的第 11 步——打开 FSD Unlock 主开关——见 14.2**。）

| 步 | 动作 | 通过判据 | 出处 |
| --- | --- | --- | --- |
| 1 | 备齐板、线束、万用表 | 板载 120Ω 跳线帽确认在 `NC` 位 | 第 11 节；微雪 wiki |
| 2 | 拆后排扶手后饰板，找 X179 | 认出是 20-pin 还是 26-pin | `HARDWARE.md:92`、`:94-95` |
| 3 | 车机 Service Mode → CAN Port 记针号 | 每针对应总线有名字，按线束料号列出 | `HARDWARE.md:104-105`、`:98` |
| 4 | CAN-H / CAN-L / +12V / GND 四线进螺丝端子 | 端子拧紧、无裸露铜丝 | `HARDWARE.md:316-319` |
| 5 | 脱车量 CAN-H↔CAN-L；万用表量 12V | ~120Ω 正常、~60Ω＝终结器开着；确认 1 / 15 哪路有电 | `:646`、`:659` |
| 6 | 烧录：Web Flasher、`ufbt` 装 FAP，或 `pio run -t upload` | 页面报成功 / 终端 `SUCCESS` | 第 13 节 |
| 7 | 上电：螺丝端子 7–36V 或 USB Type-C，二选一 | 指示灯起、板子不发热 | 微雪 wiki FAQ |
| 8 | 连板子自己起的 WiFi 热点（ESP32 的 access point，**不是车机 AP、也不是 Autopilot**），浏览器开 `192.168.4.1` | 页面能打开；首启为 Listen-Only，不发帧 | `esp32/README.md:132`、`:20` |
| 9 | **线路对账**（Wiring Check） | **`rx_count` 持续增长，且 CAN 错误计数为 0** | `esp32/README.md:131` |
| 10 | HW Override 选硬件模式 | 模式被接受，不用重烧 | `esp32/README.md:123` |
| **11** | **打开面板上的 FSD Unlock 主开关** | 开关从关变开 | `esp32/README.md:336`、`:112` |

**第 11 步是全文最容易漏的一步**：第 10 步做完只是"链路通了"，真正决定要不要往总线上注入 `0x3FD` 的是这个主开关，而它默认是关的。**漏掉它，前十步全白做。**14.2 整节讲它。

**第 9 步不通过时怎么退：**

| 现象 | 含义 | 回到哪一步 |
| --- | --- | --- |
| `rx_count` 不涨 | 收不到帧——线没接对、针号认错，或接到了非 CAN 对上 | 第 4 步（接线）、第 3 步（针号） |
| CAN 错误计数不为 0 | 能收到但收不对——速率或终结问题 | 第 5 步（量电阻） |

第 9 步通过也只证明一件事：收发链路是通的。它不证明任何功能生效——这一条与第 14.3 节的边界是同一句话。

本节判据转自文档与厂商规格，未做任何实测（全文的实测边界见 0.2 与 14.3）。

## 13. 烧录与上电：三条路

**三条路按"要不要装工具链"分：前两条拿现成产物，第三条自己编。**本节展开 12.7 那张表的第 6–7 步（烧录与首次上电）；第 8–10 步在 14.1 接上，第 11 步在 14.2。

### 13.1 两条预编译路径（不装任何工具链）

**选哪条取决于你手上是哪种硬件**——A 路刷进 ESP32 板（本文主方案），B 路装进 Flipper Zero：

| | 路线 A：ESP32 | 路线 B：Flipper Zero |
| --- | --- | --- |
| 装进什么 | 11.2 那块微雪 ESP32-S3-RS485-CAN | Flipper Zero（11.5 方案 E 的硬件） |
| 拿什么 | 托管 Web Flasher `https://hypery11.github.io/flipper-tesla-fsd/install/`，或 Releases 里的 `tesla-flasher.html`（`README.md:231`） | Releases 里的 `tesla_mod.fap`（`README.md:225`） |
| 怎么装 | **桌面版** Chrome / Edge / Opera 打开页面，按提示走（手机浏览器不行） | 把 `.fap` 复制到 SD 卡 `apps/GPIO/`（`README.md:227`） |
| 装完怎么进 | 连板子自己起的 WiFi 热点，浏览器开 `192.168.4.1`（14.1） | 机上 **Apps → GPIO → Tesla Mod**（`README.md:228`） |

两条路都不改固件源码，直接拿现成产物；下面 13.2 是需要自己编的第三条。

### 13.2 路三：自己编（**这一条我实跑了**）

```bash
git clone https://github.com/hypery11/flipper-tesla-fsd.git
cd flipper-tesla-fsd/esp32
pio run -e waveshare-s3-can
```

**这条我实跑过**（8.2 记的就是这一轮，停在 `6a3404f`）：`waveshare-s3-can` SUCCESS，RAM 37.4% / Flash 28.0%；同一棵树的其余 9 个 env 也全部 SUCCESS（10/10）。**加 `-t upload` 就是烧录——但那一步我没跑过**（8.4）。

Flipper 侧的本地构建是 `ufbt`（`README.md:248-249`），产物同样是 `dist/tesla_mod.fap`，放进 SD 卡 `apps/GPIO/` 即可——与 13.1 路线 B 的安装方式一致。

### 13.3 走 `tesla-open-can-mod` 的话，会撞两处裂缝

**先说适用性**：13.1、13.2 三条路都基于本文主方案（flipper）。这一节是给改用教学样本 `tesla-open-can-mod` 的人看的——那两处裂缝都在编译期或配置期，不改文档就会撞上。

**裂缝一：M4 指南里的宏在源码里不存在。** `guides/INSTALLATION_GUIDE_M4_CAN.md:29` 写着 `#define HW_TARGET TARGET_HW3  // Change to TARGET_LEGACY, TARGET_HW3, or TARGET_HW4`，全仓库 grep `HW_TARGET|TARGET_HW3|TARGET_LEGACY` **只有这一处命中**——没有任何代码读它。

真正生效的是 `RP2040CAN.ino:24-26` 的车型宏与 `include/app.h:17-25` 的条件编译。**照指南逐字执行，会定义一个没人读的宏，构建照样撞上 `include/app.h:24` 的 `#error`。** 指南其余部分（装库、选板、接线、验证）都对，只有选型这一行指向了不存在的 API。

**裂缝二：PlatformIO 路径缺一个车型定义——但上游用脚本堵上了。** `include/app.h:24` 的错误信息要求往 `build_flags` 写入 `HW4/HW3/LEGACY`，而 `platformio.ini` 四个板级 env 的 `build_flags` **只有驱动宏**（`:8`、`:16`、`:24`、`:30`）；README `:215-217` 又要求修改 `src/main.cpp` 中的"那行 define"——**用定冠词暗示它已经存在，实际上不存在**。

**实跑的结果和预想不同：失败点不在 `include/app.h:24`，而在更早一步。**原样 clone 直接 `pio run -e esp32_twai`，报的是驱动宏：

```
*** RP2040CAN.ino must enable exactly one driver define: DRIVER_MCP2515, DRIVER_SAME51, DRIVER_TWAI.
File "...\scripts\platformio_sync_ino_defines.py", line 29, in _pick_one
========================= [FAILED] Took 113.98 seconds =========================
```

在 `.ino` 里解开那两行驱动宏之后，同一条命令成功，脚本打印 `Synced RP2040CAN.ino defines for esp32_twai: HW4`。

**准确表述是**：填补 `include/app.h:24` 那个空缺的不是源码，而是 `scripts/platformio_sync_ino_defines.py` 把 `.ino` 的车型宏同步进 `build_flags`。**把 `extra_scripts` 从 `platformio.ini` 里去掉，那个空缺会原样暴露出来**——这才是"上游用脚本堵上了"的含义。

### 13.4 上电之后的第一状态：只听

`esp32/README.md:20`："The device boots in Listen-Only mode by default and will not transmit any CAN frames until the user explicitly switches to Active mode." `README.md:118` 补一句，这是 MCP2515 的硬件 listen-only 位，物理上不能 TX。

**上电 ≠ 会发帧。**而且这一层不是软件判断——6.3 那个"运行时治理"在这里落在了最靠近物理的地方（对照 12.7 第 8 步的判据与 14.2 第 1 行的 Mode 开关）。

## 14. 板子与车上的操作流程，以及仓库的指南到此为止

### 14.1 到 dashboard 为止的四步

**这里是 12.7 那张表的第 6–10 步，把每步的判据补细**；第 11 步（FSD Unlock 主开关）在下一小节 14.2。

1. **接线**（按第 12 节记下的针号）→ **上电**（端子或 USB，二选一）。
2. **连板子的 WiFi**，浏览器开 **`http://192.168.4.1`**（`esp32/README.md:132`）。
3. **先看接线对不对**：`esp32/README.md:131` 的 **Wiring Check = `rx_count` + CAN error monitoring**。这一步只读：**帧数在涨、CRC 错误为 0，说明收发对了；反过来先回第 12 节查线。**
4. **选硬件模式**：`esp32/README.md:123` 的 **HW Override = Auto-detect / Force HW4 / Force HW3 / Force Legacy**，运行时选择、不用重烧。

**这四步做完只是"链路通了"，还不是"FSD 在注入"。** 第 5 步在下一小节：**打开面板上的 FSD Unlock 主开关**——它默认是关的，不打开则前四步全部白做（14.2 开篇就是这条警告，12.7 的表里它是第 11 步）。

### 14.2 面板开关清单：哪些默认开、哪些默认关

**这一节是全文最容易让人白忙的地方，先说结论：FSD 的注入主开关默认是关的。**

> `esp32/README.md:336`：*Device starts in Listen-Only mode… Single click button → Active mode (TX on). **FSD injection also needs FSD Unlock switched on in the dashboard (off by default)***

也就是说，切到 Active 只让设备"可以发帧"；真正决定要不要往总线上注入 `0x3FD` 的，是另一个开关。`README.md:112` 把它列为 ESP32 独占的 **"master switch for the `0x3FD` FSD bits, off by default"**。同一个仓库里它还有另一个名字——`README.md:120` 的设置表把它写作 **Force FSD**，并给出与第 1 节三道门完全对应的说明：

> **Force FSD** — Bypass the `isFSDSelectedInUI` check. **Does not bypass Tesla's server-side entitlement — only affects local CAN frame flow.**

**这八个开关怎么读**：只有第 1 行决定"能不能发帧"，第 2 行决定"发不发 FSD 位"，其余六行都是第 2 行的修饰或边界——默认全关，逐个打开才生效。（ESP32 构建；Flipper 端把其中几项放进了主菜单。）

| 开关 | 默认 | 出处 | 作用 |
| --- | --- | --- | --- |
| **Mode** | **Listen-Only** | `README.md:118`、`esp32/README.md:130` | 首启只听；MCP2515 处于硬件 listen-only，物理上不能 TX。要发帧必须切 Active |
| **FSD Unlock / Force FSD** | **关** | `README.md:112`、`:120`；`esp32/README.md:336` | `0x3FD` 各 FSD 位的主开关。**不打开则切到 Active 也不会注入** |
| **China Mode** | 关 | `README.md:112` | 区域相关开关，仅 ESP32 分支存在；与 Force FSD 是两个独立开关（`web_dashboard.cpp:494-499`） |
| **Hardware** | Auto-detect | `esp32/README.md:123` | Auto / Force HW4 / HW3 / Legacy。自动识别需要 `0x398`，不少 Model 3/Y 不发这一帧，识别错了就手动钉住（`README.md:162`） |
| **AP-First (14.x)** | 关 | `README.md:123` | 把 `0x3FD` 注入推迟到 AP 已接合之后；README 标注 14.x 固件**需要**它 |
| **Ignore OTA** | 关 | `README.md:121` | 允许在检测到 `0x318` 报告 OTA 期间仍然发送 |
| **Abort Guard / Continuous AP** | 关 | `README.md:112` | ESP32 独占的额外保护与连续 AP 选项 |
| **TLSSC Restore / GTW Config Replay** | 关 | `README.md:122`、`:124` | 针对 VIN 级封禁的两个手段，作用范围与边界见 1.4。**注意 TLSSC Restore 单开不可靠，要与 bit 38 成对使用**（1.4） |

**上表第 2 行为什么挂着两个名字**：两份 README 对同一个开关用了 `FSD Unlock` 与 `Force FSD`，与 0.4 记录的那处 `DAS_autopilotControl` / `UI_autopilotControl` 属于同一类上游命名分歧。**检索时两个名字都要试。**

**第 4 行背后有第二段版本半衰期，值不值得知道。**`README.md:162` 说 Auto-detect 需要 `0x398`，而**很多 Model 3/Y 从不发这一帧**。上游为这个坑走过一次弯（据 Releases 页，钉在 `ffbb24e` 可见的 beta 线）：

1. `beta.20` 加了一条"看到合法的 `0x39B` 就从 HW3 升到 HW4"的补救——本意是帮那些总线上没有 `0x398` 的 HW4 车。
2. **它弄坏了本来好用的车**：在 HW3 路径本来就正常的车上，强制切到 HW4 会启用 HW4 的 DAS 解析器，而那个解析器的 byte0 锁存不上车——AP 状态卡在 "Waiting"，而且 HW4 式注入产生大量 TX 错误。有用户精确定位到"beta.18 正常，beta.19/20 坏"。
3. `beta.23` 把这条补救**回退**了，并恢复 beta.18 的行为。

**这条与 3.7 的 bit47 是同一个故事的两幕：结论的生命周期以天计。**区别在于 bit47 是被上游自己改掉的，这一次是被用户的实车日志改回去的——**这也说明为什么本文所有实测结论都标了 commit。**真正的解法放在 `beta.23` 加的 **Hardware 手动选择器**上（也就是上表第 4 行）：知道自己是什么车，就直接说，别让程序猜。

除开关之外，仓库还写下了两条运行约束（`README.md:19`）：**只读功能不依赖 FSD**（诊断、BMS 面板等不需要任何订阅），而 **FSD 功能需要有效权益**（本工具在 CAN 层使能，车辆仍需有效的 FSD 资格）。这两条正好对应 1.3 的第二道门。

**最后一条不是开关，是风险，且是本文推荐这个仓库时最该读的一条**——`README.md:22`：

> **Tesla has begun issuing VIN-level bans** (April 2026). Affected vehicles lose the TLSSC toggle silently — no OTA, no warning, persists across account transfers and re-subscriptions. The **TLSSC Restore** feature (v2.10+) can recover stop sign / traffic light control on banned Palladium and HW4 cars via 0x331 DAS config spoofing.

这是仓库自己的陈述（附 issue `#18`），我没有独立核实，也没有车可以核实——但它写在 HEAD 的 README 里，性质是项目方的风险自述，比"社区回报"高一级。机制细节（哪些位被改、主权益路径走以太网）见 1.4 引的 `SECURITY.md`。

**最值得一读的不是它的功能列表，是它自己划的边界。**`SECURITY.md:67` 起有一节 "What this project does NOT touch"，逐帧列出 TX 路径到底会写哪些位——`0x3FD` 是 bits 19 / 38 / 39 / 40-42 / 45 / 46 / 47 / 48 / 50 / 59 / 60，外加速度档字段（HW3 是 mux0 bits 49-50，HW4 是 mux2 bits 60-62，**特意留着 bit-63 的有效位不动**）与 HW3 的速度偏移字段（mux2 bits 6-13）（`:72-78`）；`0x370` 只发 counter+1 回声、转矩封顶 ±1.8 Nm，**不屏蔽 EPAS 的原始帧**（`:82-85`）。逐条的完整清单在 `SECURITY.md:72-100`。**一个负责任的 CAN 工具如何划定自己的边界，比它有多少个开关更能说明它值不值得用。**

> **一处订正**：本文上一版把这张"不碰什么"的清单标为 `SECURITY.md:67-76`（14.2 引语）与 `:85-110`（1.4 回指）。2026-10-01 复核 `ffbb24e` 检出后更正为：章节起于 `:67`，逐帧清单到 `:100`；`:85-110` 横跨的是 nag killer 的 EPAS 说明与 Track Mode 路线图，不是位级清单。

### 14.3 仓库的指南到此为止

**第 10–14 节全部是仓库文档与厂商规格的转述**：行号都给了，判据都列了，但我一条都没执行——没有板子、没有线束、没有车。

**这里也是仓库的指南到此为止。**再往前——上路之后 nag 是否真的不再出现、FSD 是否真的接合、某个开关在 2026.2.11 上有没有效果——不在本文范围内，仓库文档本身也没给出验证步骤，我不会替它编一份；任何关于规避检测、隐匿接入、移除车上通信模块的做法，本文一概不涉及。

我能担保到 `firmware.bin` 生成、到上面每一条引用的行号为止。烧录之后车会怎么反应，见第 9 节的"未核实"。

### 14.4 上车前后能做的两件事：抓帧与回放

这两项在 dashboard / Flipper 菜单里就能用，不需要任何外部工具（`README.md:97-98`）：

| 功能 | 行为 | 安全边界 |
| --- | --- | --- |
| **CAN Capture** | 把收到的每一帧录到 SD 卡 `apps_data/tesla_mod/captures/`，candump 格式 | **只读**，README 标注任何车上都可运行；录到的帧可喂给 `tools/tesla_crc_cracker.py` 做位与校验和分析 |
| **Send Test** | 从 SD 卡读一份自写的 `.cantest` 文本 profile，回放自己构造的帧 | **默认 dry-run**；真正发送被硬门控在**已停稳（P 挡）**，且每帧发送前重新判定（fail-closed） |

这也是本文方法论的延伸：要判断"某个开关在这台车上到底起没起作用"，比读文档更靠得住的做法是先抓一段帧，再看对应位有没有按预期变化。Capture 是上车前最后一个零风险动作，Send Test 则是唯一能主动验证自己判断的手段——两者都在仓库里，不需要另写代码。

---

# 第六部分 · 出处与总结

本部分给出全文引用的每一条外部出处与证据分层，以及四条判断与边界。

## 15. 参考与引用：本文用到的每一条外部出处

**三类性质请勿混用**：一手＝我能直接拿到原文；社区回报＝第三方在 issue/讨论里的单点陈述，我未独立核实；未核实＝我明确没有验证。访问日期除另注外均为 2026-10-01。下表按性质分层，每条都标了它在正文哪一节被用过。

**关于三个仓库本身**：URL 与 commit 见 0.1 那张表，全部用 `git ls-remote` / 本地 HEAD 复现。下表里标"未 clone"的那些（`herrfrei`、`juamiso`、`jvanakker`、两个镜像、`JordanzhaoD`）我按 URL 与页面日期记录，**没有做 `file:line` 核验**。

### 15.1 按性质分层的单一出处表

| 出处 | 性质 | 用在哪 |
| --- | --- | --- |
| 微雪 Wiki ESP32-S3-RS485-CAN `https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN` | 一手 | 11 节规格、120Ω 默认 NC、7–36V、双路供电警告、法律声明 |
| 微雪国际站商品页 `…/esp32-s3-rs485-can.htm` | 一手 | 型号 `-U` 外置天线版 |
| 微雪官方商城 `…/shop/ESP32-S3-RS485-CAN.htm` | 一手 | 11 节标价（**该站有反爬，未直接返回价格**） |
| Tesla 官方 X179 连接器页 `…/prog-233/connector/x179/`（料号 `1849225-03-B`、护套 `KSE K30M31014`、色 `GY`、完整 pinout 表与 `Connector Location` 栏位） | 一手 | 11 节线束规格、12.1 节 |
| Tesla Electrical Reference（Model Y 版） | 一手 | 仓库引用的官方文档入口 |
| PlatformIO / Flipper Zero 官网 | 一手 | 分别出自 `esp32/README.md` 与 `HARDWARE.md`，未另开页面 |
| Spotpear 同款 | 非一手 | 11.2 节 ¥99 参考价（页面日期 2025-08-14） |
| Sunsky 同款（板载天线版，含 $19.30 起阶梯价） | 非一手 | 11.2 节 $19.46 |
| Amazon / eBay UK 同款 | 非一手 | 11.2 节 $26.87 / $32.98 |
| M5Stack ATOM Lite、ATOMIC CAN Base；LILYGO T-2CAN、TTGO T-Display；AliExpress XY-3606；Electronic Cats CAN Add-On | 非一手 | 11.5 节方案 B–E，**URL 出自 `HARDWARE.md`，我没另开页面核对价格**；表中美元数字是仓库标的（`:388` `:405` `:417` `:437` `:541`） |
| MiOT $22.79、Newegg $53.99、elty €19.71 | 未核实 | 11.2 节比价表三处**当时未保留深链**，只有站点名与报价，证据等级低于上列各行 |
| PAC `CP1-TSL1` 目录页（"For 26-Pin Connector at Back Of Center Console"） | 一手（厂商页） | 12.1 节的独立佐证，标价 $49.99 |
| post-April-2024 26-pin 只有 18/19 是 CAN | 社区回报 | issue `#52`，`@0n3-70uch` 示波器实测，Berlin 产 EU Model Y，FW 2026.14.3；10、12 节 |
| `0x3C2` 在 9/10 可见、13/14 不可见 | 社区回报 | issue `#73`，`@JakNo` / `@jewelrylin`；10、12 节 |
| X179 pin→bus 的 Service Mode 实测表 | 社区回报 | issue `#100`，`@jewelrylin`，harness `1933903-XX`，Model Y Juniper RWD 2025，FW 2026.14.3；10 节 |
| post-SOP10 针位重排与 X177 | 社区回报 | discussion `#114`，`@mamixsystem`；10 节 |
| Nag killer 接 Party CAN 2/3 | 社区回报 | `@SkyRaax`，M3 HW4 2026.2.0，issue `#100`；12 节 |
| **VIN 级封禁研究** | 一手（仓库自述）+ 社区回报 | issue `#18`、仓库 `SECURITY.md`；转述见 `README.md:22`；1.4、14 节 |
| **HW4 + 2026.2.11 正面兼容数据** | 社区回报 | `changelog.md:243`，`@Tikernel` + `@ViPiMP`，**Model Y Juniper**；9、10 节 |
| 分版本兼容结论表 | 一手（仓库文档） | `README.md:280-293`；9 节 |
| Web Flasher `…/flipper-tesla-fsd/install/`、Releases 页 | 一手 | 13.1 节两条预编译路径 |
| FSD CAN Mod Hub 跟踪页 / 首页 `https://fsdcanmod.com/` | 未核实 | 0.3 节生态存档站；**2026-10-02 DNS 无法解析**，页面内容仅见检索快照，"Tesla DMCA"的定性归入未核实 |
| `jvanakker/tesla-fsd-can-mod`、`Karolynaz/waymo-fsd-can-mod` 两个镜像的 README（访问于 2026-10-02，未 clone） | 社区回报 | 0.3 节"removed / taken down" 的自陈 |
| `herrfrei`、`juamiso`、`jvanakker` 三个同族项目的阈值（2026.2.3、2026.8.6 失效标注） | 社区回报 | 9.3 节外部阈值分歧 |
| `JordanzhaoD/waveshare-single-can-firmware`（未 clone） | 社区回报 | 8.1、8.2 节的横向对照仓，不属解剖对象 |
| `flipper-tesla-fsd` issue `#119`（China HW4 / 2026.8.3.6 / 已购 FSD 但从未接合）、其引用的 `#117`、以及被指向为合并状态说明的 `#122` | 社区回报 | 1.3"banned vs never granted"与"档位由服务端状态重新推导"两条；**本文未 clone 核验 issue 页面，仅据检索快照** |
| `flipper-tesla-fsd` Releases 页（`beta.20` → `beta.23` 的 auto-detect 回归与回退） | 一手（仓库文档） | 14.2 Hardware 行背后的版本半衰期；钉在 `ffbb24e` 可见的 beta 线 |
| `lenfien/tesla-open-can-mod-release`（1-v-1 的 fork，README 检索快照） | 社区回报 | 6.4 用来界定"本表只覆盖 `1-v-1` @`815e000` 原仓、不含 fork"；它自称有网页面板、29 个 API 端点、OTA 固件上传 |
| `enhauto-re/COMMANDER_VS_TESLAMOD.md`（255 行对比文档，检索快照） | 社区回报 | 与 `SECURITY.md:30` 同向的另一条"ETH 不可达"佐证：171 个动作里约 40 个在以太网侧，MCP2515 物理够不着。**本文未采用为正式引用**，因其为项目方自述 |
| 中国试点叫停（工信部 / 市场监管总局新规）、完整版 FSD 截至 2026-05-21 未获批、2026-04 清理行动中逾 10 万辆 | **未核实（媒体报道）** | 1.4 开篇说明这道门的性质是监管而非技术。**本文不依赖它们得出任何操作结论** |

### 15.2 本文的证据分层

| 层 | 用在哪 | 可信度 |
| --- | --- | --- |
| 本地源码 `file:line` / 上游 `README.md:N` | 第 2–4 节、第 8、13 节 | **可 grep 复现**，行号与 commit 钉死在第 0 节那张表 |
| 本机实跑（编译、测试） | 第 8 节 | 输出可重跑，版本标注见表内 |
| 文件实读 / 关键字检索 | 第 6 节维度五的三个 `LICENSE`、第 9 节三行 grep | 打开读过、可复现（扫描文件数已标注） |
| 仓库文档转述 / 社区回报 / 未核实 | 第 10–14 节、上表"社区回报"各行、兼容性状态 | **行号可查，内容我没验或未独立核实；第 9 节的结论不变** |
| 生态下架与镜像关系 | 0.3 节 | flipper / jvanakker 的 README 为一手可复现；`fsdcanmod.com` 页面仅存检索快照、站点已无法解析，**DMCA 定性未核实** |

### 15.3 从结论回查：高频锚点索引

**这张表是上一张的倒排**——想追查某条结论时，先在左列找到那句话，再拿中列的锚点回到正文或仓库核。

| 它回答什么 | 锚点（钉在第 0 节 commit / 上游文档） | 证据层 |
| --- | --- | --- |
| **读哪一位、写哪一位** | **读 `0x3FD` mux0 bit 38（= `byte[4]` bit 6，"TLSSC flag"/`UI_fsdStopsControlEnabled`）、写 mux0 bit 46**（"enable FSD"）。**同一个 bit 38 上游有两个名字，这是本文最易读错处**（见 1.1）。交叉印证：`flipper` `README.md:315` 一行并列写出、`SECURITY.md:28`、`1-v-1` README 的 DBC 表 | 一手（源码 + 两仓文档） |
| FSD 选择位在哪一帧哪一位 | `UI_autopilotControl` `0x3FD`（1021），Legacy `0x3EE`（1006）；`can_helpers.h:21`、`fsd_can_ops.h:62`、`can_helpers.h:80` | 一手（源码） |
| **封禁为何总线解不了** | `SECURITY.md:30`（主权益路径走以太网，影子注入 `0x7FF` 无效）+ 同一行给的可用组合 **TLSSC Restore（`0x331`）+ bit 38 必须成对**；独立佐证见 issue `#119`（China HW4，档位由服务端状态重新推导） | 一手（仓库自述）+ 社区回报 |
| **校验和能破、滚动计数器破不了** | `ROADMAP.md:30`：`0x229` SCCM 的 AUTOSAR-E2E 校验和已被 `tools/crack_0x229.py` 破掉（两次抓包 224/224 帧全对），但注入仍因滚动计数器冲突而失败（`#95`、`#122`） | 一手（仓库文档，含可复现脚本） |
| 判定函数"宏→标志→帧位"三段式 | `isFSDSelectedInUI` `can_helpers.h:13-23`、`tesla_is_fsd_selected` `fsd_can_ops.h:55-63`、`isADSelectedInUI` `can_helpers.h:76-81` | 一手（源码） |
| 地域锁在哪一层、哪一版 | `esp32/README.md:429`、`:430`（off-CAN region lock）；`.catalog/README.md:7` | 一手（仓库文档） |
| 权益不由总线表达 | `CAN_DICTIONARY.md:73-74`（`UI_enableFullSelfDriving` / `UI_hasFullSelfDriving`） | 一手（仓库文档） |
| 注入总开关默认关 | `esp32/README.md:336`、`README.md:112`、`:120` | 一手（仓库文档） |
| HW4 速度档与 ISA 校验和 | `handlers.h:213-227`（921 / `0x399`）；`fsd_checksum.h:28` | 一手（源码） |
| mux 0 写缓存 / mux 2 复用 | `handlers.h:129-173`、`:165`、`:276`；`fsd_handler.c:268`、`:311` | 一手（源码） |
| bit47 实为 Summon 使能位 | `can_signals.h:44`；`README.md` beta.34 changelog、`esp32/README.md` 同记 | 一手（源码 + changelog） |
| VIN 级封禁与 TLSSC Restore | `README.md:22`；issue `#18`、`SECURITY.md`（机制拆到位：`0x7FF` mux2 byte[5] bits4:2 降档、`0x259 APP_fsdSuspendState`、**主权益路径走以太网**） | 一手（仓库自述）+ 社区回报（issue；`SECURITY.md` 自标 community research） |
| X179 在哪、怎么进 | `HARDWARE.md:92`、`:94-95`、`:98`、`:104-105`；`README.md:210` | 一手（仓库文档） |
| 26-pin 哪对是 CAN | `HARDWARE.md:204-210`（仅一句"only working CAN pair"）；issue `#52` 示波器实测 | 一手（仓库文档）+ 社区回报 |
| 终结电阻别加第二个 | `HARDWARE.md:633`（Tesla 总线已终结）、`:646`（脱车量法） | 一手（仓库文档） |
| 厂商规格（引脚/护套/料号） | 微雪 wiki、service.tesla.com `prog-233` 连接器页 | 一手（厂商页） |
| 三仓实测数据 | 本机 `pio test` / `make -C test check` / `pio run`，见 8.1、8.2（**三仓 1183 例；flipper 一家实跑停在 `6a3404f`，行号按 `ffbb24e`**） | 一手（本机可重跑） |
| 2026.2.11 该编哪个宏 | 三仓均无版本→宏映射；`changelog.md:243`（Model Y，非本车） | **不可判定**（见第 9 节） |

**这张表的用法**：想追查某条结论时，先在左列找到那句结论，再拿中列的锚点回到正文或仓库核。三个证据层的含义——标"一手（源码）"的，都能在第 0 节钉死的 commit 上按 `file:line` 逐字核到；标"社区回报"的只有单点来源、无第三方仲裁；标"不可判定"的，本文明确承认答不出、不给结论。

---

## 16. 总结

回到开篇那句话：车机上的"已勾选"只是一帧 CAN 报文里的一个比特，所有工具做的都是让固件不再去看它——而权益与地域围栏都不在这一帧里。三个仓库在**结构上**给出同一个答案：启动层 handler 均先于驱动建立，运行层均为"排空读取 + 逐帧转发"（差异在转发前垫入什么），业务层均为按 mux 分支、读状态、改比特、回发。横切面三家同源，见第 5 节。

**四条判断**：

**其一，`tesla-open-can-mod` 的工程成熟度高于同类工具的平均水准。**2.4 节那处 shadowing 回归测试完整走过"发现隐式耦合 → 修复 → 用测试锁死 → 把意图写进测试名"，随手编写的脚本不会具备这一形态。

**其二，"安全门控"的分化方向是放在哪一层，这是全文最核心的发现。** `tesla-open-can-mod` 没有统一的发送许可；flipper 放在业务层、每条路径各调一次（五处，易漏）；ev-open 挂在驱动回调上（业务层绕不过）。同一道闸，三家选了三个高度。

**其三，行号与文档必须钉死在具体版本上。**本文两次踩到：flipper 在写作当天前进 4 个提交、`HARDWARE.md` 每处引用随之漂移；ev-open 的 tag 不在默认分支上，clone 到的 `main` 落后 14 个提交。同一类问题的另一面是文档与代码的落差——`HW_TARGET` 无人读取、车型宏依赖脚本注入、两份指南对 X179 给出相反答案。**前两处在编译期终止，第三处只会导致拆错饰板，编译器与 grep 都不介入。**

**其四，"能不能编"与"能不能接"是两个独立问题，后者更硬。**前者已由 17/18 个板级环境、三仓 1183 个宿主用例（含对照仓 1833）给出答案；后者一条都未解决：X179 针号需进 Service Mode 才能确定，OBD-II 口是 CAN 还是 DoIP 取决于生产日期与地区，终结电阻需脱车测量，12V 是否常电需万用表验证。编译通过是本文在桌面上能给出的最强证据，它的边界是 USB 线。

**方法论上还有一条：社区数据的可迁移性取决于同一性，而非相似度。** `changelog.md:243` 那条数据在地区、硬件代际、软件版本上与本文配置完全一致，唯独车型是 Model Y。选型时该问的不是"哪个更好"，而是"哪一份的证据恰好落在我的配置上"。

最后是边界：仓库的指南到此为止。上路之后某个开关是否真的有效，既不在本文验证范围内，也不应由本文代仓库编写流程。本文能担保的是行号、编译输出与引用出处；再往前，需要读者自己的板子、自己的线、自己的车。


