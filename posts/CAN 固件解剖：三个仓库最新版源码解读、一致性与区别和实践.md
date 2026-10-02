---
title: CAN 固件解剖：在中国开启 FSD 的原理，与三个仓库的同构、分化与实测
date: 2026-10-01
tags: [自动驾驶, CAN总线, 嵌入式, 固件分析, 特斯拉, 源码分析]
album: 自动驾驶专栏
order: 3
excerpt: 三个公开仓库的最新版源码逐行解剖：钉死 commit 与行号后对照同一套骨架，讲清在中国"开启 FSD"的一条链路与三道门，再落到一台具体车——China HW4.0、2025 款Model 3 的选型、购买、X179 接线与烧录。附 1833 个宿主用例与 18 次板级构建的实测汇总。
---

《自动驾驶专栏》第三篇，2026-10-01。原理一句话先给：车机上的"已勾选"只是一帧 CAN 报文里的一个比特，所有工具做的事情都是让固件不再去看那一帧；而权益与地域围栏都不在这一帧里——这就是第 1 节的"一条链路、三道门"。围绕同一条 CAN 总线的公开实现不止一个，本文考察其中三个：PlatformIO 固件工程 `tesla-open-can-mod`、Flipper Zero 应用 `flipper-tesla-fsd`、ESP-IDF 固件平台 `ev-open-can-tools`——三者形态差异显著，分别采用编译期选型、运行时菜单与网页开关。三份源码作逐行解剖：并列后可以看到，收发序列集中于同一批文件，抽象骨架高度重合，分化集中在少数几条明确的维度上；最后落到一台具体车辆（China HW4.0、2025 款 Model 3、2026.2.11），完成选型、采购、接线与烧录的全过程记录。

**结论前置。**下表六行是全文的结论，先于证据给出，每一行标注可回查的章节：

| 议题 | 结论 | 详见 |
| --- | --- | --- |
| **版本** | 三个仓库分别钉死在 `815e000`、`ffbb24e`（`v2.16-beta.34`）、`6d37392`（`v4.0.0-beta.3`，在 `dev` 分支而非 `main`） | 第 0 节 |
| **一致性** | 启动、运行、业务三层序列落在同一批文件里；绝对位号寻址、"校验和只管自己起的头"、"先清再置"的读改写纪律三家一致；`tesla-open-can-mod` 与 `ev-open` 的业务接口三个纯虚方法名逐字相同 | 第 5 节 |
| **区别** | 五条维度：选型在哪一层、发送许可在哪一层、OTA 期间的行为、功能面、许可证与发布。**分化最深的是发送许可**——一家不存在，一家让业务层每条路径各调一次（靠自律），一家挂在驱动回调上（靠结构） | 第 6 节 |
| **在中国"开启"FSD 的原理** | 一条链路、三道门。车机把"用户已勾选"写进一帧 CAN 报文，固件的判定函数（先查编译期宏 → 再查运行时标志 → 最后读帧上的位）决定要不要注入——三家的覆写都落在这一个点上。另两道门不由固件动：权益在账号与服务端；地域围栏 `2026.14.x` 起位于总线之外（`esp32/README.md:430`） | 第 1 节 |
| **实测** | 18 个板级环境中 17 个可构建；1833 个宿主用例。**四条异常比"1831 过"更说明问题**：2 个 native 套件因宿主缺 `strlcpy` 编不过（不是代码错）、一个失效包名 404、一处中文 Windows 的 GBK 解码崩溃、最后一个 `feather_rp2040_can` 死在平台包名上——详见 4.6 与 8.3 | 第 8 节 |
| **边界** | 不烧录、不接车、不验证上车效果；仓库的指南到此为止 | 第 14 节 |

**三条读法，按你要的东西选：**

- **只想弄懂原理** → 0.4（帧 ID 与术语）→ 1.1（一条链路、三道门）→ 5、6（一致与分化）。这四节读完，勾选位、权益、地域锁的关系就清楚了。
- **只想马上动手** → 11.6（三家对 S3 的支持实践）→ 11.2（买什么）→ 12.7（十步操作序列）→ 13.1（两条预编译路径）→ 14.1、14.4（面板四步与抓帧回放）。
- **想核我的实测数据** → 8（宿主测试与板级构建）→ 0.2（证据分档约定）。第 2–4 节的所有 `file:line` 都与 8 的表同源。

---

## 目录

**第一部分 · 范围与关键分歧**

- **0. 三个版本，先钉死** —— 三个仓库的 commit / tag、全文的证据分档约定、样本冻结背后的生态下架、帧 ID 与术语对照
- **1. 在中国"开启"FSD：一条链路，三道门** —— 勾选位、权益与地域围栏三道门的可动性

**第二部分 · 逐仓库解剖**

- **2. `tesla-open-can-mod`：最干净的教学样本** —— 文件地图、三层序列、位操作与校验和、门控清单
- **3. `flipper-tesla-fsd`：整个生态的重心** —— 两份业务层、发送许可、nag killer 与 bit47 的两次改口
- **4. `ev-open-can-tools`：最像平台的一个** —— 平台化选型、OTA 闸、驱动回调许可与两处实测故障

**第三部分 · 一致性与区别**

- **5. 一致：同一个骨架** —— 三层序列对照表与五处跨仓库共识
- **6. 区别：五条维度** —— 选型、发送许可、OTA 期间行为、功能面、许可证与发布
- **7. 定位：三个仓库在哪一层** —— 三层定位图：三个仓库都住在总线层

**第四部分 · 实测与未知**

- **8. 实测汇总** —— 1833 个宿主用例、18 次板级构建与六条报错分组
- **9. 兼容性：一个诚实的未知** —— 2026.2.11 该编哪个宏，可验证与不可验证的分界

**第五部分 · 一台具体配置的实践**（China HW4.0 / 2025 款 Model 3 / 2026.2.11）

- **10. 先把车钉死：这台车意味着什么** —— HW4、DoIP、X179 针号、SOP 时间线四条硬约束
- **11. 选什么、买什么** —— 主方案与代价、清单、线材、五套备选与三家的 ESP32-S3 支持实践
- **12. 接线：从 X179 到螺丝端子** —— 位置口径、引脚表、终结电阻、供电与十步序列
- **13. 烧录与上电：三条路** —— 两条预编译路径（ESP32 / Flipper）与本地编译，以及两处文档裂缝
- **14. 板子与车上的操作流程，以及仓库的指南到此为止** —— dashboard 四步、面板开关清单、抓帧回放与边界

**第六部分 · 出处与总结**

- **15. 参考与引用：本文用到的每一条外部出处** —— 每一条外部出处、性质分层、高频锚点反查与证据分层
- **16. 总结** —— 四条判断、方法论与全文边界

---

# 第一部分 · 范围与关键分歧

本部分先交代版本与证据约定，再把三个仓库在 FSD 地域围栏这一个具体问题上先行对照。

## 0. 三个版本，先钉死

**行号只有钉在版本上才有意义，而钉住行号的前提是先钉住版本。**三行均于 2026-10-01 用 `git ls-remote` 实时查询。

### 0.1 三个仓库的 commit 与 tag

下表三格对应第 2–9 节的全部 `file:line`，换一格就要重推：

| 仓库 | commit | 版本 | 说明 |
| --- | --- | --- | --- |
| [`1-v-1/tesla-open-can-mod`](https://github.com/1-v-1/tesla-open-can-mod) | `815e000` | 无 tag、无 release | 最后一次 push 停在 2026-04-02，距查询日 183 天。第 2 节全部行号按该 commit 的检出逐条核对 |
| [`hypery11/flipper-tesla-fsd`](https://github.com/hypery11/flipper-tesla-fsd) | `ffbb24e` | `v2.16-beta.34`（2026-10-01） | 查询当天仍在提交；`esp32/.firmware/main.cpp` 在 beta.33 至 beta.34 之间移动 25 行 |
| [`ev-open-can-tools/ev-open-can-tools`](https://github.com/ev-open-can-tools/ev-open-can-tools) | `6d37392` | `v4.0.0-beta.3`（2026-09-20） | 不在默认分支：`main` 停在 `338d276`（2026-08-05，`VERSION` 写 3.1.1），须检出 `dev`。两线于 `447049d`（2026-07-31）分叉，`dev` 领先 14 个提交 |

第三行涉及一个容易混淆的区分：仓库接口返回的 `pushed_at` 记录 `dev` 的推送时间，默认 clone 拿到的却是 `main`，两者相差 46 天、`VERSION` 分别为 `3.1.1` 与 `4.0.0-beta.3`。若按 `main` 记行号，第 4 节会整节错位。

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

### 0.3 样本为什么停在 4 月：一次下架与三条延续线

第 0.1 表第一行的"无 tag、无 release、停在 2026-04-02"不是孤例。把各家 README 的自述拼起来（`flipper` 的两处行号来自 `ffbb24e` 检出，一手；`jvanakker` 的引文访问于 2026-10-02），这条线的来历是：

- **原始研究**：`Starmixcraft/tesla-fsd-can-mod`（CanFeather）。`flipper-tesla-fsd` `README.md:374` 称其"original CanFeather FSD research"，注明 **"GitLab repo removed"**，镜像指向 `Karolynaz/waymo-fsd-can-mod`；`jvanakker/tesla-fsd-can-mod` 的 README 开头自陈"This is a mirror. Credits for the original repo go to gitlab.com/Starmixcraft/tesla-fsd-can-mod"，并写 **"Original repo and it's successor (Tesla open CAN mod) are taken down according to https://fsdcanmod.com"**（该 README，访问于 2026-10-02）。
- **后续正统**：`ev-open-can-tools`。`flipper` `README.md:361` 的 Related projects 表称其为"The upstream community project"，并写 **"Formerly `Tesla-OPEN-CAN-MOD` on GitLab; that group was renamed to `ev-open-can-tools` and the GitLab repo is now dormant (0 open issues/MRs, last commit 2026-04-25)"**。第 4 节解剖的"最像平台"的仓库就是这条线的现存端——三家不是三个孤岛。
- **下架本身**：两个镜像把原因指向同一处存档站 `fsdcanmod.com`。**该域名在 2026-10-02 已无法解析**（DNS 查询失败，我复核两次）；它的页面内容我只在检索快照里读到，记为"Both GitLab repos taken down by Tesla DMCA (April 2026)"——**DMCA 的定性归入未核实**，可核实的只有上面两处仓库 README 的"removed / taken down"。

对本文有三个直接影响：

1. 教学样本 `1-v-1/tesla-open-can-mod` 最后一次 push 是 **2026-04-02**，与"April 2026" 的下架窗口重合。**时间重合不是因果**——我未查到 `1-v-1` 与 GitLab 原仓的 fork 关系证据（GitHub API 本次访问被限流）；但反过来，把"停更"直接读作"弃坑"同样没有依据。
2. 第 9 节引用的 `jvanakker` 失效标注（"2026.8.6 与 2026.2.9.x 及以上已不可用"）出自同一个镜像 README 的 `⚠️ UPDATE` 段，**指涉对象是 CanFeather 原始固件**，不是本文第 2 节样本的代码；证据等级维持社区回报。
3. flipper 把 ev-open 称作 upstream（`:361`），第 5 节那张"几乎能互相覆盖"的骨架表因此有了注脚：**同源，不是巧合**。

### 0.4 帧 ID 与术语对照

后文引用帧时，本文先给十进制（与三份源码里的 `frame.id == ...` 一致），再括注上游文档惯用的十六进制；两者是纯算术换算（`0x3FD` = 3×256 + 0xFD = 1021）。下表的信号名与方向逐条取自 `flipper` 的 CAN ID 表（`README.md:310-325`，钉在 `ffbb24e`），**行号于 2026-10-01 复核**——上游 README 会被改写，若你日后核不上，先确认时点。

| 十进制 | 十六进制 | 信号名 | 方向 | 本文出现处 |
| --- | --- | --- | --- | --- |
| 1021 | `0x3FD` | `UI_autopilotControl` | TX | 选择位所在帧，HW3/HW4（1.1、2.4） |
| 1006 | `0x3EE` | `UI_autopilotControl` | TX | 同上，Legacy HW1/HW2（2.4） |
| 921 | `0x399` | `ISA_speedLimit` / `DAS_status` | TX/RX | 按硬件代际分派：Legacy/HW3 读 DAS 状态，HW4 走 ISA 速度警告抑制（2.7） |
| 1016 | `0x3F8` | `UI_driverAssistControl` | TX | HW3/HW4 的第二条监听帧；telemetry-off 涉及的位在其中（2.4） |
| 962 | `0x3C2` | `VCLEFT_switchStatus` | TX | 工具写入以模拟转向柱按键（ScrollPress AP），并决定可见总线（11.5、12.3） |
| 880 | `0x370` | `EPAS3P_sysStatus` | TX | nag 回声所在的 Chassis CAN 帧（3.5、12.2） |
| 923 | `0x39B` | `DAS_status` | RX | HW4/Highland HW3 的 AP 状态，AP-First（14.x）读它判断 AP 是否已接合（1.4） |
| 792 | `0x318` | `GTW_carState` | RX | OTA 检测；新车上 byte6 是滚动计数器（6.3、14.2） |
| 817 | `0x331` | `DAS_autopilotConfig` | TX | TLSSC Restore（1.4、14.2） |
| 2047 | `0x7FF` | `GTW_carConfig` | TX | GTW Config Replay（1.4） |
| 787 | `0x313` | `UI_trackModeSettings` | TX | Track Mode：平衡/稳定/散热，重算校验和，走 Vehicle 总线 |

**方向列的 TX/RX 是"工具"视角**：TX＝工具发送、RX＝工具接收。同一 ID 在不同硬件代际下角色会互换——`0x399` 在 Legacy/HW3 上工具只读，在 HW4 上还要写 ISA 抑制位，这是 2.7 那段代码存在的理由。

**一处上游自身的命名分歧先记下来**：flipper 的源码注释把选择位所在帧写作 `DAS_autopilotControl`（`fsd_can_ops.h:55`），同一仓库的 README 信号表写作 `UI_autopilotControl`（`README.md:315`）——同一帧（`0x3FD` / `0x3EE`），两种叫法。读源码以注释为准，检索上游文档用后者。

读本文需要的七个术语：

| 术语 | 在本文与源码里的具体含义 |
| --- | --- |
| 仲裁 ID（arbitration ID） | CAN 帧的地址字段，代码里就是 `frame.id` |
| 数据长度码（DLC） | 帧的数据字节数，代码里 `frame.dlc`；多处用 `dlc < 5` / `< 8` 提前返回 |
| 多路复用（mux） | 一帧 ID 用 `data[0]` 低 3 位（`data[0] & 0x07`）区分用途，mux 0 / 1 / 2 各是一组语义 |
| 绝对位号 | 这一层没有 DBC 文件，"起始位 + 长度"已被手工展开成比特序号，如 `setBit(frame, 46, true)`（5.1） |
| 读-改-重发（read-modify-retransmit，RMR） | 三家工具的核心动作：收到帧 → 改若干比特 → 立即回发；因此发送方多为工具自己 |
| 滚动计数器（rolling counter） | 帧内逐帧递增的防伪字段；工具回发时必须跟着递增，否则车端判为无效帧 |
| 显性 / 隐性（dominant / recessive） | CAN 用单线上的两种电平表示逻辑 0 与 1，靠"线与"完成多节点仲裁，优先级由 ID 决定 |

---

## 1. 在中国"开启"FSD：一条链路，三道门

三个仓库都实现了同一条路径：绕过车机界面的勾选状态，在总线层直接判定 FSD 已选中；三者也都在各自文档中声明，这条路径不改变车辆权益。能被固件动的那一段是清楚的，动不了的那一段也同样清楚——中间隔着三道彼此独立的门。本节先讲完整链路，再逐道门给出三份源码的位置与差异。

### 1.1 一条链路，三道门

**先说链路。** 车机界面上 FSD 那个勾选框本身不改变车辆行为，它只是通过一帧 `UI_autopilotControl`（CAN ID `0x3FD`，即十进制 1021；Legacy 走 `0x3EE` = 1006，帧 ID 与信号名对照见 0.4）告诉车上的自动驾驶计算机"用户已经勾选"——这个状态落在 `data[4]` 的第 6 位（`can_helpers.h:21`、`fsd_can_ops.h:62`；`ev-open-can-tools` 读第 5 位、函数名 `isADSelectedInUI`）。

固件要做的只有一件事：读这个位，决定后续帧要不要按"已选中"处理。三个仓库都把它抽成一个无状态判定函数（逐字对照见 1.2）。**所有"在中国开启 FSD"的固件侧手段，动作都只有一个：让这个函数不看帧、直接返回 `true`**；随后的注入、改比特、解除 nag 都在这条分支的下游。

**再说三道门**，它们决定这条路径能走多远：

1. **选择位**——在总线上，可被固件覆写（1.2）。
2. **权益**——订阅与购买状态在账号与服务端，不由总线帧表达（1.3）。
3. **地域围栏**——2026.8.6 起是神经网络层的区域检查，2026.14.x 起明写位于总线之外（1.4）。

第一道门能动；第三道门连绕的入口都没有；夹在中间的权益门，工具能做的只是把读者引到官方流程上去。

![一条链路与三道门：勾选状态是一帧 CAN 报文里的一个比特](images/can-mod-teardown-2026/s00-fsd-chain.svg)

图 1｜一条链路与三道门：工具能动的只有第一道（选择位），权益与地域围栏都不在这一帧里。

### 1.2 第一道门：选择位——同一种形状，三种命名

第一道门就是 1.1 那条链路上的判定函数。三份源码的结构一致：一个无状态函数，先查编译期宏，再查运行时标志，最后读帧上的位。

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

该函数原本在两个 handler 中各有一份副本。仓库在文件头记录了合并原因（`fsd_can_ops.h:7-10`，逐字，行首 `*` 为原文注释符）：

```c
 * alike, with no frame-type coupling. They were duplicated in both handlers;
 * keeping one copy removes the drift (e.g. the ESP32 had a china_mode branch in
 * its FSD-selected check that the Flipper copy lacked — folded in here as a
 * parameter, so each platform keeps its own behavior while sharing the logic).
```

两处具体差异：

**其一，读的位不同。** 两个仓库取第 6 位、`ev-open-can-tools` 取第 5 位（`can_helpers.h:80`），且其函数名为 `isADSelectedInUI`，判定的并非同一个信号。本文不推断两者的信号映射。

**其二，只有 `flipper-tesla-fsd` 带有区域相关的独立开关。** `fsd_state.h:299` 的字段注释为 `bypass FSD UI selection check for China vehicles`；该开关只在 ESP32 分支存在，Flipper 分支传 `false`（`fsd_logic/fsd_handler.c:94`）。

这一平台差异由仓库自身记录于 `fsd_can_ops.h:7-10`，并由 `test/test_fsd_core.c:1274` 用一条断言覆盖了 Flipper 包装层到不了的路径。网页控制台上，`force_fsd` 与 `china_mode` 是两个独立开关（`esp32/.firmware/web_dashboard.cpp:494-499`）。

### 1.3 第二道门：权益在总线之外

固件改写的只是自身的判定输入，不产生车辆权益。四份文档的表述一致：

| 仓库 | 原文 | 出处 |
| --- | --- | --- |
| `tesla-open-can-mod` | Any attempt to bypass the purchase or subscription requirement for Full Self-Driving (FSD) will result in a permanent ban from Tesla services. | `README.md:10` |
| `tesla-open-can-mod` | **You must have an active FSD package on the vehicle** — either purchased or subscribed. This board enables the FSD functionality on the CAN bus level, but the vehicle still needs a valid FSD entitlement from Tesla. | `README.md:27` |
| `flipper-tesla-fsd` | A real FSD purchase or subscription is still required, and it does not unlock FSD on Tesla firmware 2026.14 and newer. | `.catalog/README.md:7` |
| `ev-open-can-tools` | This project is **not plug-and-play**. CAN connects vehicle computers, including safety-critical systems. | `README.md:9` |

信号层面的区分见 flipper 侧的字典：`enhauto-re/CAN_DICTIONARY.md:73` 与 `:74` 把 `UI_enableFullSelfDriving`（使能）与 `UI_hasFullSelfDriving`（权益校验）列为两个不同信号。第 1.2 节的覆写作用于前者，不及于后者。

`tesla-open-can-mod` 另有一份面向受限地区的账户操作指南 `guides/FSD_SUBSCRIPTION_GUIDE.md`，其自带免责声明位于 `:5`。本文记录该文件的存在与行号，不转述其步骤。

### 1.4 第三道门：地域围栏与版本分界

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

**第三条边界比上面两条更硬，来自另一份一手文件。** `SECURITY.md:19-32`（钉在 `ffbb24e`）把 VIN 封禁的机制拆到了位一级，并逐条标明证据来源（"community research, April 2026"，即社区研究、引用 issue `#18`）：

| 机制 | 位置 | 状态 |
| --- | --- | --- |
| `GTW_autopilot` 档位从 SELF_DRIVING(3) 降为 ENHANCED(2) | `0x7FF` mux=2 byte[5] bits 4:2 | 社区研究 |
| TLSSC 标志位被独立清零 | `0x3FD` mux=0 byte[4] bit 6（bit 38）；同字节 bit 7 是 Continue on Green，不是 TLSSC | 社区研究 |
| FSD 挂起状态置为 SUSPENDED | `0x259 APP_fsdSuspendState` | 社区研究 |
| **AP ECU 的主权益路径似乎是 Ethernet** | —— | 社区研究 |

`SECURITY.md:30` 那句是这一整节里最要紧的判断：**单靠影子注入 `0x7FF` 并不能解除封禁，因为主权益路径走的是以太网**——这正好从反面印证了第 1 节第二道门"权益不在总线上"。同一行的下半句又给出实测有效的组合：**TLSSC Restore（`0x331`）+ `0x3FD` mux0 bit38** 由 `@RoyRakete` 在被封的 HW3 / 2026.2.6 上确认能可靠恢复 AP/TACC（issue `#18` 楼中楼）。`SECURITY.md:31-32` 补了两条限定：TLSSC Restore 单独只能部分恢复停车标志/红绿灯、**不恢复完整 FSD**；且 Intel HW3 的封禁执行比 Palladium/HW4 更激进。

`SECURITY.md:23-24` 另记了一条操作面的事实：封禁**跨账号转移、FSD 重新订阅、乃至 Service 端重装软件都持续存在**，拔 SIM 卡只能降低、不能消除被检测的风险。这解释了为什么第 14 节把 VIN 封禁列为"项目方风险自述"里最高风险的一条。

### 1.5 本节结论

三道门的可动性各不相同。第一道门在总线上，三仓库的覆写能力高度同形，差异集中在是否提供区域相关的独立开关、编译期与运行时的取舍、以及判定所读的位；后两道门都不在总线上，三份文档口径一致——覆写产生不了权益，2026.14.x 起也够不着地域锁，只有 `flipper-tesla-fsd` 明确记出了这条版本分界。所以"开启 FSD"里能被工具推进的，只有从勾选位到注入之间的那一段，再往后是账号、服务端与激活预检的地界。第 5、6 节将把这一组对照纳入更大的一致性与分化维度中考察。

---

# 第二部分 · 逐仓库解剖

三份源码用同一套方法读：**文件地图 → 启动 / 运行 / 业务三层序列 → 横切面（位操作、校验和、驱动）→ 测试与实测**。三节的小节编号刻意同构，方便横向对照；每节末尾的小节编号若与其他节不同，是因为该仓在这条骨架上确有一块别家没有的内容（如 2.6 的回归测试、3.5 的 nag killer、3.7 的 bit47 改口、4.6 的两处真故障），我按事实标注而非强行拉齐。

| | 2 `tesla-open-can-mod` | 3 `flipper-tesla-fsd` | 4 `ev-open-can-tools` |
| --- | --- | --- | --- |
| 地图 | 2.1 | 3.1 | 4.1 |
| 启动 / 运行 / 业务 | 2.2 / 2.3 / 2.4 | 3.2 / 3.3 / 3.4 | 4.2 / 4.3 / 4.4 |
| 横切面 | 2.5 / 2.7 / 2.8 | 3.6 | 4.5 |
| 门控（本仓特有或前置） | 2.10 | 3.4 | 4.5 |
| 测试 | 2.9 | **3.8** | **4.7** |
| 独有内容 | 2.6 回归测试 | 3.5 nag killer、3.7 bit47 改口 | 4.6 两处真故障 |

每节开头都有一句钉住 commit 的说明；行号只在那个 commit 上成立。

## 2. `tesla-open-can-mod`：最干净的教学样本

> **本节行号与文件行数全部钉在 `815e000` 的检出上**（无 tag、无 release，最后一次 push 停在 2026-04-02，见第 0 节表的第一行）。

三个仓库中，该仓库的抽象分层最清晰、规模最小，适合作为第一个解剖对象。本节要回答的是：所谓"操作序列"在源码中的具体位置。

本节是全文最长的一节，也是后两节的基线：2.5/2.7/2.8 的三个横切面在这里逐字展开，第 3.6 与 4.5 只讲各自相对它的差量。**只想看原理可直接跳到 1.1 与第 5、6 节；只想看这台车怎么接，看第 11–14 节。** 若要通读本节，建议顺序为 2.1（地图）→ 2.2/2.3/2.4（三层序列）→ 2.5/2.7/2.8（横切面基线）→ 2.9/2.10（测试与门控）；2.6 是插在其中的一个完整案例，可独立阅读。

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

三个派生类监听的 ID 各不同（HW4 的 921 分支受编译期宏控制，见 2.7）：

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

这不是笔误——mux 0 → mux 2 锁存的回归测试见 2.6，mux 1 分支的断言见 2.10。三个 handler 的 mux 1 分支写法相同，但三者的 mux 2 不一致：HW3 检查缓存（`handlers.h:165`），HW4 不检查（`handlers.h:276` 为光秃秃的 `if (index == 2)`），Legacy 没有 mux 2 这一支。

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

`setBit` 用绝对位号寻址：`bit / 8` 定位字节、`bit % 8` 定位位内偏移，并在 `:33-34` 加了越界护栏。这解释了代码中 19、46、47、59、60 这些魔数的来历——DBC 的"起始位 + 长度"语义在这一层已被手工展开成绝对位号（第 5.1 节）。

### 2.6 一处被回归测试钉死的耦合

2.4 那个"mux 2 复用 mux 0 缓存"的行为值得单独看，因为它曾是个 bug。

`test/test_native_hw3/test_hw3_handler.cpp:55` 的注释直接写着 `// --- FSD shadowing fix regression test ---`，测试本体在同文件 57-74 行，逐字如下：

```cpp
void test_hw3_fsd_enabled_only_set_on_mux0()
{
    // Step 1: mux 0 with FSD bit set -> FSDEnabled should become true
    CanFrame f0 = {.id = 1021};
    f0.data[0] = 0x00; // mux 0
    f0.data[4] = 0x40; // FSD selected
    handler.handleMessage(f0, mock);
    TEST_ASSERT_TRUE(handler.FSDEnabled);

    // Step 2: mux 2 with FSD bit NOT set -> FSDEnabled should STAY true
    mock.reset();
    CanFrame f2 = {.id = 1021};
    f2.data[0] = 0x02; // mux 2
    f2.data[4] = 0x00; // FSD bit not set in this frame
    handler.handleMessage(f2, mock);
    TEST_ASSERT_TRUE(handler.FSDEnabled);
    TEST_ASSERT_EQUAL(1, mock.sent.size()); // mux 2 should still send because FSDEnabled is latched
}
```

"shadowing" 点出了原 bug 的性质：mux 2 的帧自己带了一个 `data[4]`，早期实现若在每个分支重读 UI 位，这帧会把 mux 0 刚存下的状态覆盖掉，语义上称为变量遮蔽。

修复方式是让读取只发生在 mux 0，并用回归测试锁死这个行为。HW4 有一份孪生测试（`test_native_hw4/test_hw4_handler.cpp:62`，注释同样写着 `FSD shadowing fix regression test`）。

![状态缓存的时序耦合](images/can-mod-teardown-2026/s02-state-latch.svg)

图 3｜mux 0 写入状态、mux 2 复用状态，mux 1 两者都不做。

修复本身不是重点，流程才是：发现隐式耦合、加测试锁死、把修复意图写进测试名。

### 2.7 横切面二：校验和，HW4 独有的一支

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

### 2.8 横切面三：驱动抽象与过滤器掩码

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

### 2.9 测试：99 条断言，107 次执行

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

实际执行按 env 分配：`[env:native]` 吸收前六组（`platformio.ini:35-36` 的 `test_ignore` 排除 `force_fsd`）得 93 次，`[env:native_force_fsd]` 得 6 次，`[env:native_log_buffer]` 再跑一次 `log_buffer` 得 8 次，合计 8 次套件运行、107 次执行。2026-10-01 实测 `107/107` 通过，0 失败。

`platformio.ini:32-36` 把它们跑在主机上：`platform = native`、`build_flags = -std=c++17 -DNATIVE_BUILD ...`、`test_filter = test_native_*`。主机编译器由 README `:239` 指定为 MinGW-w64 GCC。

`-DNATIVE_BUILD` 是关键开关：`include/app.h:9-11` 与 `include/handlers.h:11-13` 都用它隔离 Arduino 头文件。**同一份业务代码既能编译进 MCU，也能编译进主机当纯逻辑跑，这是整个测试体系成立的前提。**测试靠 `MockDriver` 捕获发送：`send()` 不上总线，只 `sent.push_back(frame)`，于是断言发送次数与帧内容成为可能。

### 2.10 门控：有什么，没什么

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

**读法**：3.1 地图（两份业务层是理解本节的前提）→ 3.2/3.3/3.4 三层序列 → 3.4 的四道门 → 3.5 nag killer → 3.6 横切面（相对第 2 节的差量）→ 3.8 测试；3.7 是独立案例，随时可跳读。

第一个要看清的结构事实：业务层有两份。 `esp32/.firmware/fsd_handler.cpp:14-16` 的三条 include 把边界写得很明白：

```cpp
#include "../../fsd_logic/fsd_checksum.h"  // shared Tesla additive checksum (single impl, both platforms)
#include "../../fsd_logic/fsd_can_ops.h"   // shared stateless frame primitives (set_bit / mux / fsd-selected)
#include "../../fsd_logic/fsd_ota.h"       // shared 0x318 OTA-install detection (flag vs rolling counter)
```

共享的是无状态原语；判断逻辑各写一遍：`fsd_handle_autopilot_frame` 在 C 版是 `fsd_handler.c:191`、在 C++ 版是 `fsd_handler.cpp:265`，`fsd_detect_hw_version` 分别在 `:98` 与 `:123`。

直接后果是同一个 bug 要在两处各修一次，而两处的测试是分开的：`test_fsd_core` 编 `.c`，`test_esp32_core` 编 `.cpp`。第 8 节那 827 条正是这么来的——648 条打 C 版，179 条打 C++ 版，没有一条同时覆盖两者。

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

与第 2.2 节的 `appSetup()` 对照，形状完全不同：那边是硬件初始化序列，这边硬件初始化在平台层的 `main.cpp`，这一层只剩状态初始化。三处细节：

- `memset` 先清零，再**只把有默认值的字段写出来**，其余全靠零值语义。
- `das_hands_on_state = 0xFF` 是**"未见过"哨兵**。`:1262` 的注释写明 `0xFF = no DAS frame seen yet — echo conservatively as fallback`；用 0 就会被当成 `NOT_REQD`（`das == 0` 在 `:1269` 直接 return），门控语义整个反过来。
- `gtw_autopilot_tier = -1` 同理，用 −1 区分"没读到"和"第 0 档"。

哨兵值是这个状态机最容易被改坏的地方，而它在初始化里就定死了。

### 3.3 第二层序列：运行

`esp32/.firmware/main.cpp` 的接收回调按固定顺序跑，分发业务之前先做四件与业务无关的事：

| 顺序 | 位置 | 做什么 |
| --- | --- | --- |
| 1 | `main.cpp:1127` | `blackbox_record` —— 关键 ID 落盘，**两种模式都记** |
| 2 | `:1132` | `capability_record` —— 接收窗口内计数，纯 RX |
| 3 | `:1134` | `can_dump_record` |
| 4 | `:1140` | `http_can_stream_record` —— **Active 模式也记**，注释写明是为了抓接合瞬间 |
| 5 | `:1149` | DLC 为 0 的帧丢弃 |
| 6 | `:1153` 起 | HW 自动识别（被动，命中即 `return`） |
| 7 | `:1162-1168` | OTA 监控（模式无关，命中即 `return`） |
| 8 | `:1185-1187` | BMS 只读嗅探（三个 ID 各一行、各自 `return`），然后才轮到业务分发 |

先记录、后判断，6 和 7 都提前 `return`，这两类帧不进业务层；第 2.4 节那家没有这个结构，装好过滤器后命中帧一律直接进 `handleMessage()`。

并发。第 2.3 节 `appLoop()` 用 `volatile` 解决可见性问题，这里做法更重（`main.cpp:71-72`，`state_exit()` 在 `:75`）：

```cpp
static void state_enter() {
    portENTER_CRITICAL(&g_state_mux);
```

每次读写 `g_state` 前后进出临界区。代价是关中断，收益是状态从"单字段可见"变成"整体一致"——`fsd_state.h` 那 343 行是一个 struct，要么全看见、要么全看不见。

发送许可：一个函数，三道条件，五处调用。 `fsd_logic/fsd_handler.c:41-48`：

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

`main.cpp` 里每一条会发帧的路径都要先问它一次：`:287`（挡位序列）、`:876`、`:1276`、`:1356`（nag killer）、`:1772`（预空调用）。

这是第 2.10 节那张门控表最缺的实据：`tesla-open-can-mod` 里不存在这样一个函数，它的发送许可全在编译期宏里。注释里 `Not overridable by ignore_ota` 还说明这个门是分层的——`ignore_ota` 能开的洞，Autopark 那层不给开。

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

四道门各管一件事：AP 是否真的接合且稳定、方向盘是否回正、本次接合是否进过 abort、注入预算花完没有。三道是 2026.14.x 之后才加的，注释挂着 issue 号（`#108`、`#100`），`:194-196` 还关联 `ev-open-can-tools#66 / v3.0.2-beta.2` 的一次转向顿挫。第 2.10 节那张门控清单里，这四种一个都没有。

过了门才是 mux 分发（`:210-214`）：

```c
uint8_t mux = fsd_read_mux_id(frame);
bool fsd_ui = fsd_is_selected_in_ui(frame, state->force_fsd);
bool modified = false;

if(mux == 0) state->fsd_enabled = fsd_ui;
```

随后按硬件代际分两支，形状与第 2.4 节三个 handler 的分支一致：

| | HW3（`:228-274`） | HW4（`:275-324`） |
| --- | --- | --- |
| mux 0 | 算速度偏移 → `set_bit(frame, 46, true)`，写 byte6 速度档 | `set_bit(46)` + `set_bit(60)`，可选 `set_bit(59)` |
| mux 1 | 清 bit19，一串开关逐个写 48/50/47/46/…（`:241-267`） | 同一串开关（`:285-310`） |
| mux 2 | `if(mux == 2 && state->fsd_enabled)`（`:268`） | `if(mux == 2)`（`:311`） |

第三行是一个跨仓库的同构。第 2.4 节记过：`tesla-open-can-mod` 的 HW3 mux 2 检查缓存（`handlers.h:165`），HW4 那支是"光秃秃的 `if (index == 2)`"（`handlers.h:276`）。flipper 这里一模一样——HW3 那支要 `state->fsd_enabled`，HW4 不要。两个仓库、两套语言、同样的不对称，不像巧合，更像一份沿用了另一份的帧布局语义。我没有证据指认方向，只记下形态。

第二行的 bit47 走过一段路，见第 3.7 节。

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

**校验和。** `fsd_logic/fsd_checksum.h:28` 的 `tesla_additive_checksum(can_id, data, len)`：ISA / track / nag 放 byte 7、SCCM 左 CRC 放 byte 0（用法注释在 `:22-23`）。ISA 那一支（`fsd_handler.c:391-396`）与第 2.7 节逐句对得上，`CAN_ID_ISA_SPEED` 就是 `0x399`——`921 == 0x399`。

差别只在封装：那边把循环内联进 handler，这边抽成 `static inline` 放共享头，ESP32 版还把字节位换成命名常量 `SIG_ISA_SOUND_ACTIVE_BYTE` / `_MASK`（`fsd_handler.cpp:452-459`）。

这是收敛还是抄袭，我判定不了。 flipper 在别处会署名——`fsd_handler.c:50` 写着 `BMS read-only parsers (CAN frame templates from tuncasoftbildik/tesla-can-mod)`，多处注释指向 `ev-open-can-tools`——这一支却没有署名。我只能把行号并排放着，方向不猜。

（"只在自己起头发的帧上重算校验和"这个共同点，见第 5.2 节。）

### 3.7 一句结论只活了 24 小时：bit47 的两次改口

这是全文最能说明"行号与结论都必须钉死在版本上"的一段。

`bit47` 是 EU Summon 的开关位，在四个版本上被改过三次：

| 版本 | 状态 | 备注 |
| --- | --- | --- |
| `19ef738`（beta.29） | C 版 HW4 **无条件**置位，头顶一段自陈坦白注释：`// HW4 sets bit47 (summon enable) unconditionally here (pre-existing), so the summon_unlock toggle is effectively always-on for HW4 on this build. ... Reconciling this divergence is a follow-up.` | 本次钉出的原文 |
| `6a3404f`（beta.33，2026-09-30） | follow-up 做完：`:294-296` 变成 `if(state->summon_unlock) { fsd_set_bit(frame, 47, true); }`，坦白注释删掉，与 HW3 的 `:251-253` 对称 | 相隔 24 个提交，一个自陈的 TODO 归零 |
| `ffbb24e`（beta.34，2026-10-01） | C 版**没动**；改的是 ESP32 版：`esp32/.firmware/fsd_handler.cpp` 的 nag killer 分支**删掉了** `set_bit(frame, SIG_AP_HW4_NAG_CONFIRM_BIT, true); // HW4 nag-suppression confirmation bit` 这一行 | 本次重写新查 |

beta.34 的 `changelog.md` 开头就写明了理由（逐字）：

> **ESP32: the nag killer no longer sets 0x3FD bit47 on HW4.** bit47 is the Summon-enable bit (confirmed on-car in #163), not part of nag suppression — the nag killer works through the bit19 clear and the 0x370 EPAS echo. ... The misnamed constant is renamed to SIG_AP_SUMMON_ENABLE_BIT. No change to nag behaviour.

于是 `esp32/.firmware/can_signals.h:44` 从 `#define SIG_AP_HW4_NAG_CONFIRM_BIT 47` 变成 `#define SIG_AP_SUMMON_ENABLE_BIT 47`——**一个常量名骗了所有人：它叫"Nag 确认位"，其实是"Summon 使能位"。** 同一提交还加了 `config.h:165` 的 `SUMMON_DISABLE_SPEED_KPH 3.0f`，让 Summon 在车速超 3 km/h 时自动撤销（`main.cpp:1307-1321` 的 `0x257` 速度分支）。

这一段的分量不在技术，而在结论的半衰期："bit47 常开"这一判断在上游 HEAD 上已然错误，"beta.33 修好了"这一判断隔日又错。**版本敏感的结论只能连同 commit 一起写。**

### 3.8 测试：827 条断言，分成互不覆盖的两套

第 8 节的 827 条并非一个测试工程的产物，而是两套彼此独立的宿主测试：`test_fsd_core.c`（127.6 KB）编 C 版 `fsd_logic/`，`test_esp32_core.cpp`（31.9 KB）编 ESP32 版 `.firmware/`，入口是 `make -C test check`（不是 PlatformIO，见 8.5）。648 条打前者、179 条打后者。

**没有一条断言同时覆盖两份实现**——这正是 3.1 结尾那个"同一个 bug 要在两处各修一次"的测试层对应物。C 版改了一行判断，C++ 版的断言不会变红，反之亦然。测试数量在这里证明的是覆盖广度，不是两份实现的行为一致性。

## 4. `ev-open-can-tools`：最像平台的一个

这一节补齐源码阅读，方法与前两节一致。**读法**：4.1 地图 → 4.2/4.3/4.4 三层序列 → 4.5 横切面（相对第 2 节的差量）→ 4.6 两处真故障 → 4.7 测试；其中 4.2 的平台化选型是本仓最值得细读的一段，4.4 的发送许可回调是三家里唯一的（见第 6 节维度二）。

> **本节行号钉在 `6d37392`（`v4.0.0-beta.3`，2026-09-20），也就是 `dev` 分支。** 默认分支 `main` 停在 `338d276`（2026-08-05），两者在 `447049d` 分叉，`v4.0.0-beta.3` 这个 tag 不在 `main` 上——按 `main` 推行号会整节错位。两线在 `app.h`、`handlers.h`、`can_driver.h`、`main.cpp` 上均有改动，`app.h` 的发送许可由 `:110`/`:295` 移到 `:113`/`:324`。**下文全部是 `dev` 的行号。**

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

7 个 ID，对比 `tesla-open-can-mod` 的 2 个。听得多，是因为它还要负责仪表、BMS、诊断这些只读功能——第 6 节的功能面对比会回到这一点。

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

`bit / 8`、`bit % 8`、掩码读改写，连开头那道边界守卫都与第 2.5 节逐字相同——`bit` 越界直接返回，不越界写。flipper 的 `tesla_set_bit`（`fsd_can_ops.h:19-27`）同样带护栏（`:20`），三家越界语义一致：都只在 `data[8]` 之内改写。

校验和，`include/can_helpers.h:199-214` 的 `computeVehicleChecksum(frame, checksumByteIndex = 7)`：ID 高低字节 + 数据字节累加（跳过校验字节自己）取低 8 位，外加一处 `dlc` 边界判断。同一个算法——与第 2.7 节那段内联循环是同一段数学，只是抽成函数、累加顺序反过来。三个仓库，三种封装，一个算法。

驱动接口，`include/drivers/can_driver.h:7-47`。纯虚方法与第 2.8 节完全一致（`init` / `setFilters` / `enableInterrupt` / `read` / `send`），但多了两个回调指针和一个许可函数：

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

这就是第 2.10 节那个"不存在的东西"，在这里以接口成员的形式存在。实现在 `app.h:113-127`，`app.h:324` 装进驱动（`appDriver->allowSendFrame = appCanTransmitAllowed;`）。前两道问 `appInjectionReady()` 和 `summonOnlyInjectionRuntime`，第三道向 handler 要 `summonOnlyInjectionDecisionAt()` 的裁决。

**这是三个仓库里把发送许可放在最靠近硬件位置的一个**——业务层根本没法绕过它。三者的对比见第 6 节维度二。

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

`strlcpy` 是 BSD/newlib 函数，ESP-IDF 里有，本机的 MinGW g++ 没有；Linux 上 glibc 2.38 之后也有。所以这大概率是平台相关的——但在我这台 Windows 上，它的 native 套件只能过 7/9。从 `main` 到 `v4.0.0-beta.3` 跨了 17 天、14 个提交，这处没修。

**二、`scripts/minify_dashboard.py` 在中文 Windows 上因编码失败。** 报错 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa6`——脚本 `open()` 不带 `encoding=`，本机默认编码是 GBK。`set PYTHONUTF8=1` 可绕过。这类问题 README 里不可能写，只能实跑一次记录一次。

ev-open 对版本与车型的记载也几乎是空的（与第 9 节那张三仓表同源）：`2026.2.11` 全仓 0 处、`X179` 0 处；`HW4` 有 224 处——支持很扎实，只是没落到那个具体 OTA 版本。

### 4.7 测试：249 个用例，2 个套件在本机编不过

`test/` 下 **17 个套件目录**、`platformio.ini` **10 个 native env**，第 8 节记的是 249 个用例、247 过。与前两节最大的不同是**测试粒度按功能切开**：光看 env 名就知道覆盖面——`native_bypass_tlssc_requirement`（第 1 节那道选择位）、`native_nag`、`native_injection_after_ap`（对应 1.4 的 AP-First）、`native_plugin_engine` 与 `native_plugin_engine_custom_key`（平台特征）、`native_dev_sim`、`native_mcp2515_recovery`、`native_log_buffer`、`native_dashboard`。这是"平台化"在测试层的投影：三仓里只有它把每个开关都做成一个可单独跑的套件。

代价是它对工具链更敏感——4.6 那个 `strlcpy` 一个 bug 就打掉两个套件（`native_plugin_engine` 与同树的 `native_plugin_engine_custom_key`），9 个 native 套件在本机只能过 7 个。**247/249 这个数字要这样读：不是代码错，是宿主编译环境缺一个 BSD 函数。**

---

# 第三部分 · 一致性与区别

三份源码读完了。先看它们在哪一层其实是一份东西，再看它们在哪一层已经分化成三个不同的工具——这一部分只作对照与回指，不引入第 2–4 节之外的新证据。

## 5. 一致：同一个骨架

把三份源码的启动、运行、业务三层摆齐，会看到一张几乎能互相覆盖的表：

| 层 | `tesla-open-can-mod` | `flipper-tesla-fsd` | `ev-open-can-tools` |
| --- | --- | --- | --- |
| **选型** | `include/app.h:17-25` 编译期 `#if` | 菜单运行时选（`fsd_state.h` 存 `hw_version`） | `include/app.h:32-52` 编译期 `#if`，面板构建时另有 `DASH_DEFAULT_HW` |
| **驱动接口** | `drivers/can_driver.h` 12 行纯虚 | 平台层各写各的 | `drivers/can_driver.h:7-47` 纯虚 + 两个回调 |
| **启动** | `appSetup()`：串口 → 驱动 → 过滤器 → 中断 | `fsd_state_init()`：只清状态，硬件在 `main.cpp` | `app_main_setup()`：NVS → 驱动 → 启动 |
| **运行** | `appLoop()` `while(read)` 排空 | `main.cpp` 六步：记录 → 丢弃 → 识别 → OTA → 嗅探 → 分发 | `appLoop()`：OTA 闸 → 排空 → 广播 → 分发 |
| **业务接口** | `CarManagerBase` 纯虚三方法 | `fsd_handle_autopilot_frame()` 函数式 | `CarManagerBase` 纯虚三方法 |
| **监听清单** | `filterIds()` 与 `handleMessage()` 同类绑定 | `fsd_can_rx_handler()` 表驱动 | `filterIds()` 与 `handleMessage()` 同类绑定 |
| **位操作** | `can_helpers.h:31-46` `setBit(bit/8, bit%8)` | `fsd_can_ops.h:19` `tesla_set_bit` | `can_helpers.h:216-230` `setBit(bit/8, bit%8)` |
| **校验和** | `handlers.h:134` 内联循环 | `fsd_checksum.h:28` 函数 | `can_helpers.h:199-214` 函数 |
| **mux 语义** | `readMuxID()` = `data[0] & 0x07` | `fsd_read_mux_id()` | `readMuxID()` |

**五处一致性值得单说：**

### 5.1 绝对位号寻址是三家共用的方言

三份源码里都是 `setBit(frame, 46, true)` 这种字面量位号，没有任何一家的代码里存在 DBC 文件——DBC 的"起始位 + 长度 + 字节序"在这层已被手工展开成绝对位号。魔数最容易互相对齐，也最容易集体出错。

### 5.2 校验和只管自己起的头

三家都只在"自己是发送方"的帧上重算（`921`、`0x370`、track、ISA），"原地改 `0x3FD` 再回发"时都不重算——flipper 那 1344 行的 `fsd_handle_autopilot_frame` 里一次 `tesla_additive_checksum` 都没有。三家一致，说明不是疏忽。

### 5.3 `tesla-open-can-mod` 与 `ev-open` 的业务接口逐字相同

`CarManagerBase` 的三个纯虚方法名（`handleMessage` / `filterIds` / `filterIdCount`）一字不差——ev-open 的 README 明说它是从同族工具衍生的。

### 5.4 HW3 查 mux 2 的状态缓存、HW4 不查，两个仓库一模一样

第 2.4 节 `handlers.h:165` 对 `handlers.h:276`，第 3.4 节 `fsd_handler.c:268` 对 `:311`，同样的不对称，两边的测试也各自锁住了这个行为。

### 5.5 "先清再置"的读改写纪律是三家共识

第 2.5 节的掩码、第 3.5 节 `:1329` 的 `OR-ing 0x40 without clearing leaves level=3 unchanged`、第 4.5 节 `setBit` 的 `~mask`——三处注释、三种写法、同一个教训：忘了掩码，位操作会静默失效，方式是"看起来生效了一部分"。

## 6. 区别：五条维度

差别比相似更能说明问题。同样三个仓库，五条维度上已经分得很开。

### 6.1 维度一：选型发生在哪一层

| | 方式 | 代价 |
| --- | --- | --- |
| `tesla-open-can-mod` | 编译期 `#if`，`#error` 兜底 | 每种板 × 每种车都要编一次；改错编译不过 |
| `flipper-tesla-fsd` | 运行时菜单，存进 `fsd_state.h` 的 `hw_version` | 一次烧录覆盖全部；选错要重新进菜单 |
| `ev-open-can-tools` | 编译期 `#if`，但**面板构建另有 `DASH_DEFAULT_HW` 数值宏**；TWAI 引脚从 NVS 读 | 四条选型路径并存，最复杂；引脚 OTA 不丢 |

三者没有优劣，但代价的形态不同：`tesla-open-can-mod` 把代价放在编译期（配错即编不过），flipper 放在运行时（选错要手工回退），ev-open 放在两条路径上（网页面板和固件各自决定）。

### 6.2 维度二：发送许可放在哪一层

**这一条是三个仓库分化最深的地方：**

| | 机制 | 位置 | 能否绕过 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | **不存在** | — | 业务层想发就发，只有编译期配置 |
| `flipper-tesla-fsd` | `fsd_can_transmit()` 三道条件 | `fsd_handler.c:41-48` | **业务层每条发送路径各调一次**（`:287` `:876` `:1276` `:1356` `:1772`）——容易漏 |
| `ev-open-can-tools` | `sendAllowed()` 回调 + `appCanTransmitAllowed()` | `drivers/can_driver.h:21-24`，实现在 `app.h:113-127`，`app.h:324` 挂进驱动 | **挂在驱动的回调上，业务层无法绕过** |

第 2.10 节列过 `tesla-open-can-mod` 的门控清单，它缺的正是这道统一许可。表中"能否绕过"一列就是本条维度的全部差别：靠自律的容易漏，靠结构的写不错。

`ev-open` 的许可函数只有两道，清单见第 4.5 节；`flipper` 那三道（Listen-Only / Autopark / OTA）ev-open 一条也没有，实现分在别处。

### 6.3 维度三：OTA 期间的行为

三个仓库对"OTA 进行中"的处理完全不在一个强度上：

- `tesla-open-can-mod`：**没有这个概念**，全仓 grep 无 OTA 检测。
- `flipper-tesla-fsd`：`fsd_can_transmit()` 第三道 `state->tesla_ota_in_progress` 返回 `false`——**只拦发送，业务层照常跑**，`main.cpp:1162-1168` 的 OTA 监控帧还会提前 `return`。
- `ev-open-can-tools`：`app.h:391-395` `if (Update.isRunning()) { delay(1); return; }`——**整个主循环停掉，连帧都不读**。

同一句"OTA 进行中不要发帧"，三种实现的边界从"业务层自律"一路推到"运行时整体停摆"。ev-open 最保守，也最不容易出错。

### 6.4 维度四：功能面

| 功能 | `tesla-open-can-mod` | `flipper-tesla-fsd` | `ev-open-can-tools` |
| --- | --- | --- | --- |
| 速度档写入 | ✓ | ✓ | ✓ |
| HW4 自动识别 | ✗ | ✓（`main.cpp` 被动识别） | ✓（`handlers.h` 从 920 帧） |
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

**这个矩阵就是三个仓库的分野：**`tesla-open-can-mod` 是一个能跑通的最小实现，flipper 是一个带运行时治理的完整应用，ev-open 是一个带面板和插件的平台。功能面越宽，需要读的源码越多；功能面越窄，越容易完整判定它究竟发出了什么。

### 6.5 维度五：许可证与发布

| | 许可证（打开 `LICENSE` 逐字核对） | 发布形态 | 末次提交 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | **GPL-3.0 全文**（35,145 B）+ `THIRD_PARTY_LICENSES` | 无 tag、无 release，直接 clone | 2026-04-02（**183 天没动**） |
| `flipper-tesla-fsd` | **GPL-3.0**——但 `LICENSE` 只有 **929 B**，是那段"如何套用本许可"的说明，不是许可全文 | `v2.16-beta.34`，tag 频繁 | **2026-10-01（当天）** |
| `ev-open-can-tools` | **GPL-3.0 全文**（35,819 B）+ `THIRD_PARTY_LICENSES` | `v4.0.0-beta.3` tag，`main` / `dev` 分叉 | `dev` 2026-09-20，`main` 2026-08-05 |

许可证这一栏是三者唯一完全收敛的地方——三家都是 GPL-3.0。但中间那一格暴露了一个方法陷阱：GitHub 的 REST API 对 flipper 返回的 `license` 是 `NOASSERTION`，因为它的 `LICENSE` 只有 929 B、是那段"如何套用本许可"的说明而非许可全文。任何只靠 API 做许可证清点的调研，都会把星最多的那个（1094★）报告成"许可证未声明"——而它明明白白写着 GPLv3。本表因此按文件本身统计，不采信 API 字段。

发布节奏的分化才是真差异——表右两列逐格都写着："这个仓库是否还在维护"和"代码质量如何"是两个独立问题，前一个往往更致命。

## 7. 定位：三个仓库在哪一层

把三个仓库放进同一张层图，位置就清楚了：

![三层定位：模型层、决策与执行层、总线层](images/can-mod-teardown-2026/s03-layer-positioning.svg)

图 4｜三层定位：模型层、决策与执行层、总线层。

**它们全部位于最下层**——直接对 CAN 总线收发帧，不参与感知、不参与规划、不决定"要往哪开"。所谓"操作序列"的物理形态就是几组位掩码加一个时间窗口，而非任何模型或决策层。

同一张图里 `tesla-open-can-mod` 最靠左（只有总线层），flipper 往上伸进决策与执行层（状态机、abort guard、策略裁决），ev-open 再往右伸一层（面板、插件、上位机协议）。越往右上，读源码的收益越高——那里开始有"为什么这么做"而不只是"怎么做"。

---

# 第四部分 · 实测与未知

数据全部按各自钉死的版本标注，报错原文按证据保留。

## 8. 实测汇总

本节两组实跑：宿主测试不碰硬件，板级构建真编固件；六条报错按性质分组，未做之事单列。

**这一节的看点不在"1831 过"，在四条失败。** 宿主与平台各留下一条真问题：ev-open 的两个 native 套件因本机缺 `strlcpy` 编不过（4.6）、一个 PlatformIO 包名 404、一个中文 Windows 的 GBK 解码崩溃、`feather_rp2040_can` 最终死在同一个包名上——它们分别指向工具链、仓库配置、本机编码与上游依赖四个不同层面。**能报出这四条，才说明这些数是真跑出来的。**

### 8.1 宿主测试（`native` / `platform = native`，不碰硬件）

| 仓库 | 版本 | 套件 | 用例 | 结果 |
| --- | --- | --- | --- | --- |
| `tesla-open-can-mod` | `815e000` | 8 次套件运行（3 个 env） | 107 | **107 过 / 0 失败** |
| `flipper-tesla-fsd` | `ffbb24e`（v2.16-beta.34） | 2（`test/Makefile`，gcc/g++ 直调，非 PlatformIO） | 827 | **827/827 全过**（648 C 版 + 179 C++ 版） |
| `ev-open-can-tools` | `6d37392`（`dev`） | 10 个 env、19 次套件运行（PlatformIO native） | 249 | **247 过 / 2 个套件编译失败** |
| `JordanzhaoD/waveshare-single-can-firmware`（对照） | — | 19（PlatformIO native） | 650 | **650/650 全过** |
| **合计** | | | **1833** | **1831 过 / 2 个套件编译失败** |

三仓数据与第 0 节钉死的三个 commit 一致（重跑日期与主机环境见 8.3）；第 2、3、4 节的全部 `file:line` 与本表同源。

ev-open 那 2 个失败是真编译错误，根因就是 4.6 节的 `strlcpy`：`plugin_engine.h:747` 在 MinGW 下缺符号，同树的 `native_plugin_engine_custom_key` 套件一起挂——一个 bug 打掉两个套件。倒数第二行的 `waveshare-single-can-firmware` 不在三仓之内，列出只作横向对照。

### 8.2 板级构建（`pio run -e <env>`，真的编固件）

| 仓库 | 版本 | 实跑 env | 结果 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | `815e000` | `esp32_twai`、`m5stack-atomic-can-base`、`feather_m4_can`、`feather_rp2040_can` | **3/4**；`feather_rp2040_can` 因失效包名失败（见下 B 组第一条） |
| `JordanzhaoD` | — | `waveshare_single_can_standalone`（`esp32s3box`，16MB） | **SUCCESS**，RAM 15.3% / Flash 28.8% |
| `flipper-tesla-fsd` | `ffbb24e`（v2.16-beta.34） | `waveshare-s3-can` + 其余 9 个 | **10/10** |
| `ev-open-can-tools` | `6d37392`（`dev`） | `waveshare_ESP32_S3_RS485_CAN`、`esp32_ext_mcp2515`、`esp32_twai` | **3/3** |
| **合计** | | **18 次板级构建** | **17/18**，唯一失败是 `feather_rp2040_can` 的失效包名 |

各 env 的 RAM / Flash 占用率见 11.6 的对照表，此处不重复；本节只给"能不能编出来"这个结论。四个 ESP32-S3 目标全部通过，`TX=GPIO15`、`RX=GPIO16` 这组引脚由 `flipper`（`esp32/README.md:159`）与 `ev-open`（`platformio.ini:163-164`）两家独立给出、交叉印证；`tesla-open-can-mod` 没有 S3 目标（见 11.6）。这是"能编译通过"的最强证据——不是读 README 说的，是链接器和 esptool 说的。

### 8.3 环境与六条报错

环境：Windows 11，2026-09-30 至 2026-10-01，PlatformIO Core 6.2.0，Python 3.12.10（须 `PYTHONUTF8=1`，否则 `minify_dashboard.py` 因默认编码失败），主机编译器 MinGW-w64 GCC 16.2.0，代理 `http://127.0.0.1:10808`。上表全部于 2026-10-01 在第 0 节钉死的三个 commit 上重跑。

六条报错按性质分两组。A 组四条是 onboarding / 环境类，照做就能过：

| 报错 | 出处 | 处理 |
| --- | --- | --- |
| `Missing platformio_profile.h` | `ev-open`、`JordanzhaoD` 共用同一套 onboarding | `copy platformio_profile.example.h platformio_profile.h` |
| `platformio_profile.h must enable exactly one driver define` | `JordanzhaoD`，示例默认解的是双 CAN 变体 | 双 CAN 的 env 要改成只解 `DRIVER_TWAI` |
| `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa6` | `ev-open` `scripts/minify_dashboard.py` | `set PYTHONUTF8=1` |
| `ModuleNotFoundError: No module named 'csscompressor'` / `'rjsmin'` | `JordanzhaoD` 网页压缩脚本没声明依赖 | `pip install csscompressor jsmin rjsmin` |

B 组两条，是仓库或环境自身有误，与操作无关。第一条是 `tesla-open-can-mod` 的失效包名——与第 12 节的 X179 矛盾、第 13 节的两处裂缝同类，都是文档/配置与现实对不上：

```
*** UnknownPackageError: Could not find the package with 'autowp/MCP2515' requirements
GET .../v3/packages/autowp/library/MCP2515  →  404 NotFound
GET .../v3/search?query=autowp             →  autowp/autowp-mcp2515  v1.3.1
```

`platformio.ini:7` 改成 `autowp/autowp-mcp2515` 后 `feather_rp2040_can` 立刻通过。第二条是 `ev-open` 的源头级报错：`plugin_engine.h:747` 缺 `strlcpy`（详见第 4.6 节）。另有 `Got the unrecognized status code '403'` 一条，是我下载工具链时的网络问题，配本地代理后恢复，与仓库无关。

### 8.4 没有做的事，以及"编译通过"的边界

没有烧录（`--target upload` 一条未执行）、没有连车、没有验证任何一帧在真实总线上会被接受；另有两项未做：没有跑 `dev` 的测试矩阵、没有对 flipper 的 `ffbb24e` 重跑（827 条在 `6a3404f` 上）。

**编译通过不等于能用。**编译只证明语法、模板、链接成立，不证明任何 CAN 帧语义正确；1833 个用例断的是开发者自己写的预期——能证明"代码符合作者意图"，不能证明"作者的意图符合车端实际"。因此本文关于"车会怎么反应"的句子仍是社区回报，第 9 节的结论一个字都不用改。

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
pio test -e native            # 107 次执行，99 条断言（2.9 节的表）
pio run -e esp32_twai         # 板级构建；原样 clone 会因 RP2040CAN.ino 未解驱动宏而失败（13.3）
```

**`hypery11/flipper-tesla-fsd`（`ffbb24e`）——宿主测试与板级构建**

```bash
git clone https://github.com/hypery11/flipper-tesla-fsd.git && cd flipper-tesla-fsd
git checkout ffbb24e
make -C test check            # 两个宿主套件：C 版 test_fsd_core + C++ 版 test_esp32_core
cd esp32 && pio run -e waveshare-s3-can -t upload -t monitor
```

**`ev-open-can-tools/ev-open-can-tools`（`6d37392`，`dev` 分支）——宿主测试与板级构建**

```bash
git clone https://github.com/ev-open-can-tools/ev-open-can-tools.git && cd ev-open-can-tools
git checkout 6d37392
cp platformio_profile.example.h platformio_profile.h   # 不复制则所有 env 报 Missing platformio_profile.h
pio test -e native            # 10 个 native env，249 个用例；其中 2 个套件在本机 MinGW 下编不过（4.6 节）
pio run -e waveshare_ESP32_S3_RS485_CAN
```

三条容易踩的坑，各对应一节：驱动宏与车型宏的关系（13.3）、`PYTHONUTF8=1` 与 GBK（8.3）、`strlcpy` 的平台相关失败（4.6）。

**我只做了不接硬件的部分**——宿主测试全部在本机跑过，板级构建也真编了固件，但**没有对任何仓库执行过 `--target upload`**，所以上面 ESP32 一节的烧录命令是照仓库文档写的、未实跑（8.4）。

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

10 处全部落在文档与 issue 模板里，源码文件（`.c` / `.cpp` / `.h` / `.ino`）零命中。这一点很重要：文档记录版本，源码判断版本——而源码那半边不存在。编译期写下 `HW4` 就是 `HW4`，不看车、不看 OTA、不看地区。

其中真正有信息量的是两条，都是 Model Y，外加 `.github/ISSUE_TEMPLATE/bug_report.yml:37` 把它当作版本号的 `placeholder`（被当成"典型的当前版本"写进了报障模板）：

```
README.md:285   | Model Y 2023 (China, MIC) | HW3 | 2026.2.11 | Community | FSD (Force FSD mode) |
changelog.md:243 ... @Tikernel + @ViPiMP (positive compat data: Model Y Juniper HW4 2026.2.11 China, HW4 2026.8.3 Germany).
```

同一个 `2026.2.11` 在同一份文档里同时挂着 HW3 和 HW4——不同车型、不同年款可以停在同一个 OTA 版本上，这恰恰说明版本号本身推不出硬件代际。而 Model 3 这个车型，两条里一条都没有。

### 9.3 那文档呢？文档只差一点就答上了

`README.md:69` 是全仓唯一一条带版本阈值的规则，原文如下：

> **Note:** HW4 vehicles on firmware **2026.2.9.X** are on **FSD v14**. However, versions on the **2026.8.X** branch are still on **FSD v13**. If your vehicle is running FSD v13 (including the 2026.8.X branch or anything older than 2026.2.9), compile with `HW3` even if your vehicle has HW4 hardware.

照这条规则推：`2026.2.11` 不早于 `2026.2.9`，也不在 `2026.8.X` 分支上，所以该编 `HW4`。推得出来，但有两处不舒服。

**其一，`2026.2.11` 不等于 `2026.2.9.X`。** README 写的是补丁位通配（`2026.2.9.11`），实车版本是次版本位（`2026.2.11`）。两者能否对上，README 未作说明，源码中也没有解析器完成该判定。

**其二，同族阈值互相打架，而且 flipper 自己的兼容表压根没有这台车的位置。** 按 `ffbb24e` 读它 `README.md:278-293`，相关的四行：

| 出处 | 内容 | 等级 |
| --- | --- | --- |
| `tesla-open-can-mod` `README.md:69` | `2026.2.9.X` 起是 FSD v14；`2026.8.X` 仍是 v13，跑 v13 就编 `HW3` | 一手（仓库文档原文） |
| `flipper` `README.md:286` | `\| Model 3/Y 2023+ \| HW4 \| **< 2026.2.9** \| ... \| FSD \|` | 一手（仓库文档原文） |
| `flipper` `README.md:293` | `2026.8.6 HW4` → HW4 注入路径坏掉 → 用 Force HW3 | 一手（仓库文档原文） |
| `flipper` `changelog.md:243` | `Model Y Juniper HW4 2026.2.11 China` 正面数据（车型是 Model Y） | 社区回报（`@Tikernel` + `@ViPiMP` 的实车回报） |

**四行的"等级"要分两层读。**前三行是我逐字读过的仓库文档（引文一手），但按仓库自己在 `esp32/README.md:422` 的声明，兼容性表来自 field reports，**底层依据仍是社区回报**；第四行连引文都是他人实车结论。**这张表是全文最容易被误读的地方**：它的形式像矩阵，但没有任何一行经过第三方仲裁。

叠起来看更难受：flipper 唯一一条"Model 3 + HW4"的正面数据版本范围是 `< 2026.2.9`，这台车 `2026.2.11` 正好掉在范围外；唯一一条"HW4 + 2026.2.11"的车型是 Model Y Juniper。两个条件各有一条数据，没有一条同时覆盖两者的车型。

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

第 2.7 节讲过，校验和是 HW4 独有的一支；第 2.4 节的表也列了，三个宏只有 `LEGACY` / `HW3` / `HW4`。所以配置里 HW4.0 这一项直接决定：Legacy（HW1/HW2）那条路不相关，选型时只需要在 HW3 与 HW4 之间确认，而答案已经由配置给出。

剩下的 `HW3` 与 `HW4` 之间怎么选，第 9 节已经把能查的都查了：没有任何一行正面数据同时覆盖这台车的三个条件（详第 9.3 节）。

### 10.2 2025 款 Model 3，第一件该确认的事是 OBD-II 口上是不是 CAN

`flipper` `HARDWARE.md:39`（`ffbb24e`）：

> **April 2024+ Juniper Model Y / refreshed Model 3 Highland (later builds)**: Tesla switched to **DoIP** (Diagnostic over IP) — the diagnostic port now carries 100 Mbps Ethernet, **not** CAN.

紧接着 `:38-42` 是一条 CAUTION，大意是不要把基于 CAN 的 OBD-II 适配器或诊断仪接到 DoIP 口上——电平不兼容，可能损坏车辆的诊断模块；2024+ 的车直接接 X179。

2025 款 Model 3 属于 Highland 改款后的批次，按这段描述应当默认当作 DoIP 处理，而不是先插上去试——这是仓库写在 CAUTION 里的判断顺序，不是我的推断。

同一节另有一个限定：DoIP 迁移的分类轴是生产日期与地区，不是"改款与否"；适用范围仓库自陈"not yet pinned down"。

### 10.3 X179 的 pin→bus 映射不固定，而唯一的确定判据在车机里

`HARDWARE.md:98`："The X179 pin→bus map is NOT fixed across builds — verify it on your own car." 至少存在四种电气配置，而且"按年款推断不可靠"。

仓库给的确定判据只有一条（`:104` 起）：车机的 Service Mode → CAN Port 页面，它按线束料号逐针列出所属总线。仓库举的例子是 harness `1933903-XX`（`:105`，Model Y Juniper RWD 2025，FW 2026.14.3）：`2/3 = Party`、`9/10 = Vehicle`、`13/14 = Chassis（绿线），不是"Bus 6"`、`20 = GND`。

那台是 Model Y，不是这台 Model 3。所以这一节落到具体车辆上的第一步动作很具体：先打开 Service Mode 的 CAN Port，把针号记下来，再动线。

### 10.4 生产日期早于 SOP10，但早于 SOP10 不等于 pre-April-2024

`HARDWARE.md:225` 的 SOP 时间线里，上海是 2026-03-25（SOP11），柏林 2026-04-01，奥斯汀 2025-12-04，弗里蒙特 2025-12-09。2025 年产的车在这条线之前，因此不属于 post-SOP10 那一档。

但 post-SOP10 排除掉，不等于就落在"pre-April 2024"那张表上——那张表要求的是 2021–2023 与 2024 早期批次。2025 年产的车落在 post-April-2024 档，而那一档的实测数据是单点（`:212`："This is a single empirical data point"）：

| Pin | 柏林产 EU Model Y 实测（`HARDWARE.md:204-210`） | 等级 |
| --- | --- | --- |
| 9 / 10 | DoIP（以太网），**不是 CAN** | 社区回报 |
| 12 / 13 | DoIP，**不是 CAN** | 社区回报 |
| **18 / 19** | **Vehicle CAN，唯一可用的 CAN 对** | 社区回报 |
| 15 | +12V（不变） | 社区回报 |
| 26 | GND（不变） | 社区回报 |

（等级列的约定见 0.2：**一手**＝我能直接拿到原文；**社区回报**＝第三方单点陈述、我未独立核实；**未核实**＝我明确没有验证。这张表全部来自 issue `#52` 一个人的示波器实测，仓库自己标注 "single empirical data point"，因此五行全是社区回报——这是全文证据等级最低的一张表，接线前务必以自己车的 Service Mode 为准。）

那台车是 `@0n3-70uch` 用示波器量的（issue `#52`，Berlin 产 pre-Juniper、post-April-2024 生产、FW 2026.14.3）。仓库自己给的三条安全建议（`:220` 起）：接收发器前每一对都用示波器验一遍；13/14 的 120Ω 检查不过就改试 18/19；+12V（15）与 GND（26）跨 SOP 稳定。**这三条我一条都没执行**——板子、线束、示波器一样都没有（全文的实测边界见 0.2）。

### 10.5 把四个词合成一句话

> **这台车的选型前提：HW4 走 HW4 路径；OBD-II 口默认按 DoIP 处理、直接接 X179；X179 先开 Service Mode → CAN Port 记针号，再接线；版本 2026.2.11 上目前唯一的正面数据来自同代际、同地区、同版本但不同车型（Model Y）的社区回报。**

## 11. 选什么、买什么

### 11.1 先说推荐

**主方案：`hypery11/flipper-tesla-fsd` 的 `waveshare-s3-can`。**三个理由，按可验证性递减：

1. **它是三家里唯一记录 `2026.2.11` 的**（10 处命中，另两家 0），而且 `HARDWARE.md` 对 DoIP / X179 / Service Mode 的记载最细（104 处 X179）。
2. **它的 ESP32 侧测试是原样编进测试的**（第 3.7 节），不是抽出的副本。
3. **它在查询当天仍在提交**，而 `tesla-open-can-mod` 已经 183 天没动。

**但推荐一个东西必须同时写出它的代价：** 它的"Model 3 + HW4"记录版本范围不覆盖这台车（第 9.3 节的两个条件各有一条数据、型号还差一档）；而且它是三家里唯一明确记录 VIN 级封禁的（见第 14 节）。

### 11.2 主方案清单

| 项 | 内容 |
| --- | --- |
| **微雪 ESP32-S3-RS485-CAN** | 官方商城 `https://www.waveshare.net/shop/ESP32-S3-RS485-CAN.htm`，检索到的标价 **¥99.99**（2 件 ¥96.96）；**该站有反爬，直接打开可能只返回一段 JS**，价格以页面实际显示为准 |
| 国际站同款 | `https://www.waveshare.com/esp32-s3-rs485-can.htm`（另有 `-U` 外置天线版） |
| 规格一手出处 | Wiki：`https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN` |
| 第三方同款参考价 | `https://www.spotpear.cn/shop/.../ESP32-S3-RS485-CAN.html` 标 **¥99**（页面日期 2025-08-14） |
| 第三方比价（2026-10-01 检索，**电商商品页**） | Sunsky **$19.46**（`https://www.sunsky-online.com/p/TBD0607022302/Waveshare-Industrial-ESP32-S3-Control-Board-With-RS485-And-CAN-Communication-Interfaces-Onboard-Ante.htm`，2 件起 $19.30）· Amazon **$26.87**（`https://www.amazon.com/dp/B0FNCWZ3D1`）· eBay **$32.98**（`https://www.ebay.co.uk/itm/267437528758`）；另检索到 MiOT **$22.79**、Newegg **$53.99**、elty **€19.71**（卖的是 `-U` 外置天线版）三处，当时未保留深链。**同一块板在不同站点差近三倍，买前先按下一行的规格核对** |
| 对应构建目标 | `waveshare-s3-can`（`esp32/README.md:159` 明列，TX=15 / RX=16 / LED=46 / BTN=0）。**注意 flash 规格两处来源不一致**：上游按 **8MB flash/PSRAM** 配置该 env（`esp32/platformio.ini:185-189`），而厂商 wiki 标 **16MB Flash / 8MB PSRAM**（下一段）。按 8MB 配置在两种板子上都不会出错，按 16MB 配置则必须先确认手上这块的实测容量 |

其余板子、降压模块与 Flipper 那一路的仓库原始链接集中在第 15.2 节「厂商文档（一手）」与第 15.3 节「第三方价格（非一手）」，此处不重复。

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

`HARDWARE.md:92` 的小标题直接给了位置：`X179 — behind the rear center console (2021+ Model 3/Y)`（后排中控台后方），`:94-95` 接着给出进入方式："Tesla's own service/diagnostic connector. Requires removing a trim panel behind the rear armrest." —— 拆掉后排扶手后方的饰板。`flipper` 根 `README.md:210` 同口径，且标为 recommended。

但 `tesla-open-can-mod` 的两份指南互相矛盾，这一处最"物理"——照错了连地方都找不到：

`guides/INSTALLATION_GUIDE_M4_CAN.md:57`：

> The Enhance Auto Gen 2 Cable plugs into the **X179 connector**, located behind the **driver's side trunk panel**.

`guides/WIRING_GUIDE.md:16`：

> The X179 connector is located on the **passenger side footwell**, behind the panel on the right.

一个说驾驶侧后备箱饰板后，一个说副驾脚部空间右侧饰板后——方向完全相反。三仓全量 grep `footwell|trunk panel` 命中 5 处：除上面两条外，`guides/WIRING_GUIDE.md:18` 的 `right-side footwell panel trim` 与第二条同源；`flipper` `HARDWARE.md:75` 与 `ev-open` `docs/onboarding.md:22` 两处都只给泛化区间、不构成独立口径。

**没有任何一处能仲裁这两条互相矛盾的指南**——连 `tesla-open-can-mod` 自己的 `README.md:301` 也只给 service.tesla.com 的 X179 文档链接，不写文字位置。

外部有一处独立佐证站在「后排中控台」这一侧。PAC 的 `CP1-TSL1` 商品页把产品描述为 "For 26-Pin Connector at Back Of Center Console"（厂商目录页 `https://catalog.archive.pac-audio.com/catalog/can-integration/cp1-tsl1`，页面标价 $49.99，访问于 2026-10-01，**厂商商品页**）。

Tesla 官方的 X179 页给出料号 `1849225-03-B`、护套 `KSE K30M31014`、色 `GY`、完整 pinout 表与一个 `Connector Location` 图示栏位（`https://service.tesla.com/docs/Model3/ElectricalReference/prog-233/connector/x179/`，**一手**）。官方页管针脚、不管位置文字——pinout 可以拿来核对下一小节的引脚表，位置仍然只能靠 Service Mode。

而两份指南自称的车型还是一致的：`guides/INSTALLATION_GUIDE_M4_CAN.md:3` 写"2023 Tesla Model 3 with HW3"，`guides/WIRING_GUIDE.md:5` 写"Photos were taken on a 2023 Model 3 (non-Highland)"。同一台车，两个位置。

这一处的性质与下面两处不同：那两处是"文档指向不存在的 API"，读者会在编译期即报错、当场发现；这一处是"文档指向错误的物理位置"，后果是拆错饰板、耗时而无从定位。

两份指南都附了 Enhance Auto 的实拍视频，实车动手前以视频为准，不要以文字为准。

### 12.2 引脚表（仓库原文，**不是实车实测**）

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

这张表的等级是"一手"——指我逐字读了 `HARDWARE.md` 原文，不是说我验证过车；但**仓库自己也声明过这张表来自 field reports**（`esp32/README.md:422`），所以它的底层依据仍是社区回报。两层要分开看：**引文可查，事实未验**。

**13/14 那一行要按原文纠正一个流传很广的说法：**它不是"网关转发出来的混合总线子集"。`HARDWARE.md:116-120`：

> This **relabels** the older "Bus 6 on pin 13/14" framing: on this harness 13/14 is Chassis CAN, which is why `0x370 EPAS3P` shows there at 100 Hz with full counter continuity (EPAS lives on Chassis) — it was never a gateway-forwarded subset. **`0x370` is on Chassis CAN, not Vehicle CAN** — if you tap Vehicle CAN (9/10) you will not see `0x370`.

`HARDWARE.md:252-256` 同样把「gateway-forwarded mix of buses」标为 Older notes，并给出这一对在 `1933903-XX` 线束上的 Service Mode 结论：Chassis CAN。原文补了一句 —— The pin→bus map varies, so check Service Mode → CAN Port on your own car.
26-pin 有两档，`HARDWARE.md:159` 起，且 `:162` 明确写着 `"They are not interchangeable."`：pre-April-2024 表在 `:176-183`（段落自 `:171` 起）；post-April-2024 的示波器实测表就是第 10 节那张（`:204-210`），9/10 与 12/13 是 DoIP，`:208` 只留一句"Vehicle CAN — only working CAN pair"。

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

接哪一对，取决于第 10 节记下来的 Service Mode 结果。仓库为不同功能点名了不同总线，我把出处一并列出：

- **`HARDWARE.md:123`**：**"For the nag killer, tap Party CAN (pins 2/3)."**
- **`:280-286`**：要注入 `0x3C2`，接 **9/10** 或 **OBD-II 6/14**；13/14 上根本没有这一帧
- **`:299-305`**：HW4-modern 上 `0x370` **不在 Vehicle CAN（9/10/11）** —— 两台车的抓包在 pin 9/10、10/11 上 60 秒内都是 0 帧，`0x370` 出现在 pin **13/14**；Service Mode 随后显示线束 `1933903-XX` 的 13/14 就是 **Chassis CAN**。原文另有一句：把 nag echo 从 13/14 挪到 Vehicle CAN **够不着 EPAS**，对 HW4-modern 不可行

### 12.4 终结电阻：不要加，并且要量一次

`HARDWARE.md:633`："Tesla's CAN buses are already terminated. Do not add a second 120 Ω terminator." 多数后装模块出厂带终结，接车之前先关掉——微雪这块出厂是 `NC`，不用动。

120 Ω 不是随手取的数：它是高速 CAN（ISO 11898）的**特性阻抗**，装在总线两端把接口阻抗匹配到线缆上，作用是抑制**信号反射**。反射叠加在有效电平上会变成误码，并直接推高错误帧计数——这正是第 12.6 节把"脱车量电阻"列为必查项的原因。

`:646` 的验证法（脱车量）：CAN-H ↔ CAN-L ~120Ω = 正常（车提供终结）；~60Ω = 外接模块自带的终结器开着，关掉。

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

### 12.7 端到端操作序列：十步

上面六小节是按主题拆开的；下面这一条按执行顺序合起来，每步给出通过判据与出处。前五步不带电、可以反复重来，后五步才带电，且供电路径唯一。

![端到端操作序列：从选料到选硬件模式的十个步骤](images/can-mod-teardown-2026/s06-procedure.svg)

图 7｜十个步骤，前五步车外准备、后五步上电验证；第 9 步是整条链上唯一的 go / no-go 判据。

| 步 | 动作 | 通过判据 | 出处 |
| --- | --- | --- | --- |
| 1 | 备齐板、线束、万用表 | 板载 120Ω 跳线帽确认在 `NC` 位 | 第 11 节；微雪 wiki |
| 2 | 拆后排扶手后饰板，找 X179 | 认出是 20-pin 还是 26-pin | `HARDWARE.md:92`、`:94-95` |
| 3 | 车机 Service Mode → CAN Port 记针号 | 每针对应总线有名字，按线束料号列出 | `HARDWARE.md:104-105`、`:98` |
| 4 | CAN-H / CAN-L / +12V / GND 四线进螺丝端子 | 端子拧紧、无裸露铜丝 | `HARDWARE.md:316-319` |
| 5 | 脱车量 CAN-H↔CAN-L；万用表量 12V | ~120Ω 正常、~60Ω＝终结器开着；确认 1 / 15 哪路有电 | `:646`、`:659` |
| 6 | 烧录：Web Flasher、`ufbt` 装 FAP，或 `pio run -t upload` | 页面报成功 / 终端 `SUCCESS` | 第 13 节 |
| 7 | 上电：螺丝端子 7–36V 或 USB Type-C，二选一 | 指示灯起、板子不发热 | 微雪 wiki FAQ |
| 8 | 连板子的 AP，浏览器开 `192.168.4.1` | 页面能打开；首启为 Listen-Only，不发帧 | `esp32/README.md:132`、`:20` |
| 9 | **线路对账**（Wiring Check） | **`rx_count` 持续增长，且 CAN 错误计数为 0** | `esp32/README.md:131` |
| 10 | HW Override 选硬件模式 | 模式被接受，不用重烧 | `esp32/README.md:123` |

第 9 步不通过的回退路径：`rx_count` 不涨＝收不到帧，回第 4、3 步查接线与针号；CAN 错误计数不为 0＝速率或终结问题，回第 5 步量电阻。

第 9 步通过也只证明一件事：收发链路是通的。它不证明任何功能生效——这一条与第 14.3 节的边界是同一句话。

本节判据转自文档与厂商规格，未做任何实测（全文的实测边界见 0.2 与 14.3）。

## 13. 烧录与上电：三条路

本节展开第 12.7 节图 7 的第 6–7 步（烧录与首次上电），第 8–10 步在 14.1 接上。

### 13.1 两条预编译路径（不装任何工具链）

| | 路线 A：ESP32 | 路线 B：Flipper Zero |
| --- | --- | --- |
| 拿什么 | 托管 Web Flasher `https://hypery11.github.io/flipper-tesla-fsd/install/`，或 Releases 里的 `tesla-flasher.html`（`README.md:231`） | Releases 里的 `tesla_mod.fap`（`README.md:225`） |
| 怎么装 | 桌面版 **Chrome / Edge / Opera** 打开页面，按提示走 | 把 `.fap` 复制到 SD 卡 `apps/GPIO/`（`README.md:227`） |
| 装完怎么进 | 连板子 AP，浏览器开 `192.168.4.1`（第 14.1 节） | 机上 **Apps → GPIO → Tesla Mod**（`README.md:228`） |

两条路都不改固件源码；下面 13.2 是需要自己编的第三条。

### 13.2 路三：自己编（**这一条我实跑了**）

```bash
git clone https://github.com/hypery11/flipper-tesla-fsd.git
cd flipper-tesla-fsd/esp32
pio run -e waveshare-s3-can
```

第 8 节记录的本机结果（在上游 `6a3404f` 上复跑）：`waveshare-s3-can` SUCCESS，RAM 37.4% / Flash 28.0%；同一棵树的其余 9 个 env 也全部 SUCCESS（10/10）。加 `-t upload` 就是烧录。

Flipper 侧的本地构建是 `ufbt`（`README.md:248-249`），产物同样是 `dist/tesla_mod.fap`，放进 SD 卡 `apps/GPIO/` 即可——与 13.1 路线 B 的安装方式一致。

### 13.3 走 `tesla-open-can-mod` 的话，会撞两处裂缝

**裂缝一：M4 指南里的宏在源码里不存在。** `guides/INSTALLATION_GUIDE_M4_CAN.md:29` 写着 `#define HW_TARGET TARGET_HW3  // Change to TARGET_LEGACY, TARGET_HW3, or TARGET_HW4`，全仓库 grep `HW_TARGET|TARGET_HW3|TARGET_LEGACY` **只有这一处命中**——没有任何代码读它。

真正生效的是 `RP2040CAN.ino:24-26` 的车型宏与 `include/app.h:17-25` 的条件编译。**照指南逐字执行，会定义一个没人读的宏，构建照样撞上 `include/app.h:24` 的 `#error`。** 指南其余部分（装库、选板、接线、验证）都对，只有选型这一行指向了不存在的 API。

**裂缝二：PlatformIO 路径缺一个车型定义——但上游用脚本堵上了。** `include/app.h:24` 的错误信息要求往 `build_flags` 写入 `HW4/HW3/LEGACY`，而 `platformio.ini` 四个板级 env 的 `build_flags` **只有驱动宏**（`:8`、`:16`、`:24`、`:30`）；README `:215-217` 又要求修改 `src/main.cpp` 中的"那行 define"——**用定冠词暗示它已经存在，实际上不存在**。

实跑之后分两种情况。原样 clone 直接 `pio run -e esp32_twai` 失败，但失败点不在 `include/app.h:24`：

```
*** RP2040CAN.ino must enable exactly one driver define: DRIVER_MCP2515, DRIVER_SAME51, DRIVER_TWAI.
File "...\scripts\platformio_sync_ino_defines.py", line 29, in _pick_one
========================= [FAILED] Took 113.98 seconds =========================
```

解开两行后同一命令成功，脚本打印 `Synced RP2040CAN.ino defines for esp32_twai: HW4`。准确表述是：填补 `include/app.h:24` 这个空缺的不是源码，而是 `scripts/platformio_sync_ino_defines.py` 把 `.ino` 的车型宏同步进 `build_flags`；把 `extra_scripts` 从 `platformio.ini` 里去掉，该空缺会原样暴露。

**上电之后的第一状态：只听。** `esp32/README.md:20`："The device boots in Listen-Only mode by default and will not transmit any CAN frames until the user explicitly switches to Active mode." `README.md:118` 补一句，这是 MCP2515 的硬件 listen-only 位，物理上不能 TX。

**上电 ≠ 会发帧**，而且这一层不是软件判断——第 6 节维度三那个"运行时治理"，在这里落在了最靠近物理的地方。

## 14. 板子与车上的操作流程，以及仓库的指南到此为止

### 14.1 到 dashboard 为止的四步

这四步是第 12.7 节图 7 的第 6–10 步，此处只补判据。

1. **接线**（按第 12 节记下的针号）→ **上电**（端子或 USB，二选一）。
2. **连板子的 WiFi**，浏览器开 **`http://192.168.4.1`**（`esp32/README.md:132`）。
3. **先看接线对不对**：`esp32/README.md:131` 的 **Wiring Check = `rx_count` + CAN error monitoring**。这一步只读：**帧数在涨、CRC 错误为 0，说明收发对了；反过来先回第 12 节查线。**
4. **选硬件模式**：`esp32/README.md:123` 的 **HW Override = Auto-detect / Force HW4 / Force HW3 / Force Legacy**，运行时选择、不用重烧。

### 14.2 面板开关清单：哪些默认开、哪些默认关

**这一节是全文最容易让人白忙的地方，先说结论：FSD 的注入主开关默认是关的。**

> `esp32/README.md:336`：*Device starts in Listen-Only mode… Single click button → Active mode (TX on). **FSD injection also needs FSD Unlock switched on in the dashboard (off by default)***

也就是说，切到 Active 只让设备"可以发帧"；真正决定要不要往总线上注入 `0x3FD` 的，是另一个开关。`README.md:112` 把它列为 ESP32 独占的 **"master switch for the `0x3FD` FSD bits, off by default"**。同一个仓库里它还有另一个名字——`README.md:120` 的设置表把它写作 **Force FSD**，并给出与第 1 节三道门完全对应的说明：

> **Force FSD** — Bypass the `isFSDSelectedInUI` check. **Does not bypass Tesla's server-side entitlement — only affects local CAN frame flow.**

三家的开关对照（ESP32 构建；Flipper 端把其中几项放进了主菜单）：

| 开关 | 默认 | 出处 | 作用 |
| --- | --- | --- | --- |
| **Mode** | **Listen-Only** | `README.md:118`、`esp32/README.md:130` | 首启只听；MCP2515 处于硬件 listen-only，物理上不能 TX。要发帧必须切 Active |
| **FSD Unlock / Force FSD** | **关** | `README.md:112`、`:120`；`esp32/README.md:336` | `0x3FD` 各 FSD 位的主开关。**不打开则切到 Active 也不会注入** |
| **China Mode** | 关 | `README.md:112` | 区域相关开关，仅 ESP32 分支存在；与 Force FSD 是两个独立开关（`web_dashboard.cpp:494-499`） |
| **Hardware** | Auto-detect | `esp32/README.md:123` | Auto / Force HW4 / HW3 / Legacy。自动识别需要 `0x398`，不少 Model 3/Y 不发这一帧，识别错了就手动钉住（`README.md:162`） |
| **AP-First (14.x)** | 关 | `README.md:123` | 把 `0x3FD` 注入推迟到 AP 已接合之后；README 标注 14.x 固件**需要**它 |
| **Ignore OTA** | 关 | `README.md:121` | 允许在检测到 `0x318` 报告 OTA 期间仍然发送 |
| **Abort Guard / Continuous AP** | 关 | `README.md:112` | ESP32 独占的额外保护与连续 AP 选项 |
| **TLSSC Restore / GTW Config Replay** | 关 | `README.md:122`、`:124` | 针对 VIN 级封禁的两个手段，作用范围与边界见 1.4 |

两份 README 对同一个开关用了 `FSD Unlock` 与 `Force FSD` 两个名字，与 0.4 记录的那处 `DAS_autopilotControl` / `UI_autopilotControl` 属于同一类上游命名分歧。

除开关之外，仓库还写下了两条运行约束（`README.md:19`）：**只读功能不依赖 FSD**（诊断、BMS 面板等不需要任何订阅），而 **FSD 功能需要有效权益**（本工具在 CAN 层使能，车辆仍需有效的 FSD 资格）。这两条正好对应 1.3 的第二道门。

**另有一条须单独拿出来**——`README.md:22`：

> **Tesla has begun issuing VIN-level bans** (April 2026). Affected vehicles lose the TLSSC toggle silently — no OTA, no warning, persists across account transfers and re-subscriptions. The **TLSSC Restore** feature (v2.10+) can recover stop sign / traffic light control on banned Palladium and HW4 cars via 0x331 DAS config spoofing.

这是仓库自己的陈述（附 issue `#18`），我没有独立核实，也没有车可以核实——但它写在 HEAD 的 README 里，性质是项目方的风险自述，比"社区回报"高一级。机制细节（哪些位被改、主权益路径走以太网）见 1.4 引的 `SECURITY.md`，逐条位级清单在该文件 `SECURITY.md:85-110`。

同一份文件另有一段值得单独摘出——它列明这个项目**主动不去碰**什么（`SECURITY.md:67-76`）：不动 `0x370` 里 EPAS 的原始帧、不动 brake 相关位、不越过 bit-63 的有效标志。读懂"一个负责任的 CAN 工具如何划定自己的边界"，比读它的功能列表更能判断它值不值得用。

### 14.3 仓库的指南到此为止

以上全部是仓库文档与厂商规格的转述，行号都给了，我一条都没执行——没有板子、没有线束、没有车。

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

三类性质请勿混用：一手＝我能直接拿到原文；社区回报＝第三方在 issue/讨论里的单点陈述，我未独立核实；未核实＝我明确没有验证。访问日期除另注外均为 2026-10-01。**15.2–15.5 按性质分类列出每一条出处，15.7 反过来按"读者想追查的结论"给出锚点索引。**

### 15.1 三个仓库本身

三行的 URL 与 commit 见第 0 节那张表，全部用 `git ls-remote` / 本地 HEAD 复现。

第 9 节引用的同族项目（`herrfrei`、`juamiso`、`jvanakker`）与第 8 节计入测试总数的 `JordanzhaoD/waveshare-single-can-firmware`，我按 URL 与页面日期记录，**未 clone 下来做 `file:line` 核验**。

第 0.3 节额外引用 `jvanakker/tesla-fsd-can-mod` 与 `Karolynaz/waymo-fsd-can-mod` 两个镜像的 README 陈述（访问于 2026-10-02），同样未 clone 核验；`fsdcanmod.com` 的页面内容仅见检索快照。

### 15.2 厂商文档（一手）

| 出处 | URL | 用在哪 |
| --- | --- | --- |
| 微雪 Wiki ESP32-S3-RS485-CAN | `https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN` | 第 11 节规格、120Ω 默认 NC、7–36V、双路供电警告、法律声明 |
| 微雪国际站商品页 | `https://www.waveshare.com/esp32-s3-rs485-can.htm` | 型号 `-U` 外置天线版 |
| 微雪官方商城 | `https://www.waveshare.net/shop/ESP32-S3-RS485-CAN.htm` | 第 11 节标价（**该站有反爬，页面未直接返回价格**） |
| PlatformIO | `https://platformio.org/` | 出自 `esp32/README.md`，未另开页面 |
| Flipper Zero | `https://flipper.net/` | 出自 `HARDWARE.md`，未另开页面 |
| Tesla 官方 X179 连接器页：料号 `1849225-03-B`、护套 `KSE K30M31014`、色 `GY`，附完整 pinout 表与 `Connector Location` 图示栏位 | `https://service.tesla.com/docs/Model3/ElectricalReference/prog-233/connector/x179/` | 第 11 节线束规格、第 12.1 节 |

### 15.3 第三方价格（非一手）

| 出处 | URL | 页面日期 | 用在哪 |
| --- | --- | --- | --- |
| Spotpear 同款 | `https://www.spotpear.cn/shop/ESP32-S3-IOT-RS485-CAN-WIFI-Bluetooth/ESP32-S3-RS485-CAN.html` | 2025-08-14 | 第 11 节 ¥99 参考价 |
| M5Stack ATOM Lite | `https://shop.m5stack.com/products/atom-lite-esp32-development-kit` | 仓库引用 | 方案 B |
| M5Stack ATOMIC CAN Base | `https://shop.m5stack.com/products/atomic-can-base` | 仓库引用 | 方案 B |
| LILYGO T-2CAN | `https://lilygo.cc/products/t-2can` | 仓库引用 | 方案 C |
| LILYGO TTGO T-Display | `https://lilygo.cc/products/lilygo%C2%AE-ttgo-t-display-1-14-inch-lcd-esp32-control-board` | 仓库引用 | 方案 D |
| AliExpress XY-3606 降压 | `https://www.aliexpress.com/wholesale-xy3606.html` | 仓库引用 | 方案 D |
| Electronic Cats CAN Add-On | `https://electroniccats.com/store/flipper-addon-canbus/` | 仓库引用 | 方案 E |
| Sunsky 同款（板载天线版，含 $19.30 起阶梯价） | `https://www.sunsky-online.com/p/TBD0607022302/Waveshare-Industrial-ESP32-S3-Control-Board-With-RS485-And-CAN-Communication-Interfaces-Onboard-Ante.htm` | 2026-10-01 | 第 11 节 $19.46 |
| Amazon 同款 | `https://www.amazon.com/dp/B0FNCWZ3D1` | 2026-10-01 | 第 11 节 $26.87 |
| eBay UK 同款 | `https://www.ebay.co.uk/itm/267437528758` | 2026-10-01 | 第 11 节 $32.98 |
| PAC `CP1-TSL1` 厂商目录页，产品描述"For 26-Pin Connector at Back Of Center Console" | `https://catalog.archive.pac-audio.com/catalog/can-integration/cp1-tsl1` | 2026-10-01 | 第 12.1 节的独立佐证，页面标价 $49.99 |

"仓库引用"指 URL 出自 `hypery11/flipper-tesla-fsd/HARDWARE.md`，我没另开页面核对价格；第 11 节表里的美元数字是仓库标的（`:388` `:405` `:417` `:437` `:541`），不是我查的。

### 15.4 社区回报（issue / discussion，我未独立核实）

| 内容 | 出处 | 用在哪 |
| --- | --- | --- |
| post-April-2024 26-pin 只有 18/19 是 CAN | issue `#52`，`@0n3-70uch` 示波器实测，Berlin 产 EU Model Y，FW 2026.14.3 | 第 10、12 节 |
| `0x3C2` 在 9/10 可见、13/14 不可见 | issue `#73`，`@JakNo` / `@jewelrylin` | 第 10、12 节 |
| X179 pin→bus 的 Service Mode 实测表 | issue `#100`，`@jewelrylin`，harness `1933903-XX`，Model Y Juniper RWD 2025，FW 2026.14.3 | 第 10 节 |
| post-SOP10 针位重排与 X177 | discussion `#114`，`@mamixsystem` | 第 10 节 |
| Nag killer 接 Party CAN 2/3 | `@SkyRaax`，M3 HW4 2026.2.0，issue `#100` | 第 12 节 |
| **VIN 级封禁研究** | issue `#18`、仓库 `SECURITY.md`；转述见 `README.md:22` | 第 14 节 |
| **HW4 + 2026.2.11 正面兼容数据** | `changelog.md:243`，`@Tikernel` + `@ViPiMP`，**Model Y Juniper** | 第 9、10 节 |
| 分版本兼容结论表 | `README.md:280-293` | 第 9 节 |

### 15.5 工具与可复现入口

| 内容 | URL |
| --- | --- |
| Web Flasher | `https://hypery11.github.io/flipper-tesla-fsd/install/` |
| Releases | `https://github.com/hypery11/flipper-tesla-fsd/releases` |
| FSD CAN Mod Hub 跟踪页（README 徽章指向） | `https://fsdcanmod.com/project/hypery11-flipper-zero` |
| FSD CAN Mod Hub 首页（生态存档站；2026-10-02 DNS 无法解析） | `https://fsdcanmod.com/` |
| Tesla Electrical Reference（仓库引用的官方文档） | `https://service.tesla.com/docs/ModelY/ElectricalReference/` |

### 15.6 本文的证据分层

| 层 | 用在哪 | 可信度 |
| --- | --- | --- |
| 本地源码 `file:line` / 上游 `README.md:N` | 第 2–4 节、第 8、13 节 | **可 grep 复现**，行号与 commit 钉死在第 0 节那张表 |
| 本机实跑（编译、测试） | 第 8 节 | 输出可重跑，版本标注见表内 |
| 文件实读 / 关键字检索 | 第 6 节维度五的三个 `LICENSE`、第 9 节三行 grep | 打开读过、可复现（扫描文件数已标注） |
| 仓库文档转述 / 社区回报 / 未核实 | 第 10–14 节、第 15.4 节、兼容性状态 | **行号可查，内容我没验或未独立核实；第 9 节的结论不变** |
| 生态下架与镜像关系 | 第 0.3 节 | flipper / jvanakker 的 README 为一手可复现；`fsdcanmod.com` 页面仅存检索快照、站点已无法解析，**DMCA 定性未核实** |

### 15.7 从结论回查：高频锚点索引

| 它回答什么 | 锚点（钉在第 0 节 commit / 上游文档） | 证据层 |
| --- | --- | --- |
| FSD 选择位在哪一帧哪一位 | `UI_autopilotControl` `0x3FD`（1021），Legacy `0x3EE`（1006）；`can_helpers.h:21`、`fsd_can_ops.h:62`、`can_helpers.h:80` | 一手（源码） |
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
| 三仓实测数据 | 本机 `pio test` / `make -C test check` / `pio run`，见 8.1、8.2 | 一手（本机可重跑） |
| 2026.2.11 该编哪个宏 | 三仓均无版本→宏映射；`changelog.md:243`（Model Y，非本车） | **不可判定**（见第 9 节） |

任一行里标"一手（源码）"的，都能在第 0 节钉死的 commit 上按 `file:line` 逐字核到；标"社区回报"的只有单点来源、无第三方仲裁；标"不可判定"的，本文明确承认答不出、不给结论。

---

## 16. 总结

本文开头提出的问题是"操作序列写在代码里，在哪三层"。三个仓库给出同一个答案，差异只在放置位置：启动层 handler 均先于驱动建立，运行层均为"排空读取 + 逐帧转发"、差异在转发前垫入的内容，业务层均为按 mux 分支、读状态、改比特、回发。横切面三家同源，展开见第 5 节。

四条判断。

**其一，`tesla-open-can-mod` 的工程成熟度高于同类工具的平均水准。**第 2.6 节的 shadowing 回归测试完整走过"发现隐式耦合 → 修复 → 用测试锁死 → 把意图写进测试名"的流程，随手编写的脚本不会具备这一形态。

**其二，"安全门控"的分化方向是放在哪一层，这是全文最核心的发现。** `tesla-open-can-mod` 没有统一的发送许可；flipper 放在业务层、每条路径各调一次（五处，易漏）；ev-open 挂在驱动回调上（业务层绕不过）。同一道闸，三家选了三个高度。

**其三，行号与文档必须钉死在具体版本上。**本文两次遇到该问题：flipper 在写作当天前进 4 个提交、`HARDWARE.md` 每处引用随之漂移；ev-open 的 tag 不在默认分支上，clone 到的 `main` 落后 14 个提交。同一类问题的另一面是文档与代码的落差——`HW_TARGET` 无人读取、车型宏依赖脚本注入、两份指南对 X179 给出相反答案。前两处在编译期终止，第三处只会导致拆错饰板，编译器与 grep 都不介入。

**其四，"能不能编"与"能不能接"是两个独立问题，后者更硬。**前者已由 17/18 个板级环境、1833 个用例给出答案；后者一条都未解决：X179 针号需进 Service Mode 才能确定，OBD-II 口是 CAN 还是 DoIP 取决于生产日期与地区，终结电阻需脱车测量，12V 是否常电需万用表验证。编译通过是本文在桌面上能给出的最强证据，它的边界是 USB 线。

方法论上还有一条：**社区数据的可迁移性取决于同一性，而非相似度。** `changelog.md:243` 那条数据在地区、硬件代际、软件版本上与本文所用配置完全一致，唯独车型是 Model Y，差在何处无数据可依。选型时该问的不是"哪个更好"，而是"哪一份的证据恰好落在我的配置上"。

最后是边界：仓库的指南到此为止。上路之后某个开关是否真的有效，既不在本文验证范围内，也不应由本文代仓库编写流程。本文能担保的是行号、编译输出与引用出处；再往前，需要读者自己的板子、自己的线、自己的车。


