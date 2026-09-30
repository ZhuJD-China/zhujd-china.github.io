---
title: CAN 固件解剖研究：从逐行读源码到 2025 Model 3 HW4 / 2026.2.11 的接线、烧录与选型
date: 2026-09-30
tags: [自动驾驶, CAN总线, 嵌入式, 固件分析, 特斯拉, 源码分析]
album: 自动驾驶专栏
order: 3
excerpt: 我把 tesla-open-can-mod 的完整源码拉到本地逐行读完，用 file:line 定位它真正的三层操作序列；再把 GitHub 与 GitLab 上能查到的十几个同类仓库按 API 元数据逐个清点、横向比对，并在本机把单元测试、18 个板级环境与 38 个测试套件（1904 个用例）真的跑了出来；最后再用同一套方法，把我最终推荐的 flipper-tesla-fsd 也从头读了一遍——落到一台具体车上：China HW4.0、2025 款 Model 3、软件 2026.2.11，该买什么硬件、怎么接 X179、怎么烧录，以及全部仓库链接与引用出处的逐条说明。
---

《自动驾驶专栏》第三篇。

围绕同一条 CAN 总线，社区里长出的公开实现不止一个。本系列盯的是其中三个：PlatformIO 固件工程 `tesla-open-can-mod`、Flipper Zero 应用 `flipper-tesla-fsd`、ESP-IDF 固件平台 `ev-open-can-tools`。形态差得很远，操作序列却都藏在同一个地方——源码里。

这一篇分六部分：**解剖**（1–12）、**横向对照与实跑**（13–16）、**边界与评估**（17–19）、**动手**（20–24）、**补读**（25）、**收尾**（26–27）。每部分做了什么、它的证据到哪里为止，各用一句话写在下面的目录里，这里不重复一遍。

**先看这张表**——每一类结论我用什么方式验证，决定了你该用多大力度相信我：

| 结论类型 | 我的验证方式 |
| --- | --- |
| 某段代码在哪一行 | 本地源码逐行读，可 grep 复现 |
| 文档与代码对不上 | 双方各 grep 一次，交叉验证 |
| 测试数量与断言 | 逐个 `RUN_TEST` 数过 |
| 本仓库的单元测试能否通过 | 本机装 PlatformIO 后**实际执行**，输出见第 16 节 |
| 同族仓库是否真的编得过 | **实际构建**：18 个板级 env 成功（含 4 个 ESP32-S3）+ 38 个测试套件 / 1904 个用例，见第 16、19 节 |
| 同族仓库的 star、创建与最后提交日期 | GitHub / GitLab **公开 API 直接查询**，可复现，见第 13 节 |
| HW4 / 某个 OTA 版本该编哪个宏 | **规则来自仓库 README**，行号可复现；该版本上车后的实际效果**未验证** |
| X179 引脚、哪对线上是哪条总线 | **仓库文档原文 + 出处行号**，作者本人没接车、没量过示波器，**未实测** |
| 硬件购买链接与价格 | **打开页面抓取**，附 URL 与页面日期；抓不到就写明抓不到 |
| 板子上电之后的页面操作流程 | **仓库文档原文**，没有板子，**未执行** |
| 烧录之后车会怎么反应 | **完全不验证**——没有板子、没有线束、没有车辆，见第 24 节的边界 |
| 同族仓库的兼容性口径、行业事件、时间线 | **网络检索**，按 URL 与页面日期记录，未做本地逐行核验 |
| 兼容性/漏洞是否已被 OTA 修复 | **未核实**，见第 17 节 |
| 行号以外的外部事实 | 只在我能拿到一手文本时才写，拿不到就标注为"社区回报" |

**三份源码都要用到，先分清楚：**

- 本地副本 `E:\tesla-open-can-mod-main\tesla-open-can-mod-main`——**第 1 至 11 节所有 `file:line` 都对着它**，仓库为 GPL-3.0。
- 网络上游 `https://github.com/1-v-1/tesla-open-can-mod`，commit `815e000`（2026-04-02）——**第 12、16 节的构建与教程对着它**，行号写成 `上游 README.md:N`。
- `https://github.com/hypery11/flipper-tesla-fsd`，commit **`6a3404f`**（2026-09-30 的 HEAD）——**第 25 节的全部行号，以及 flipper 的每一条构建与测试数字，都对着它**。这一份要特别钉死：这个仓库当天仍在提交，我写作过程中两次核对，HEAD 就换了两次（`19ef738` → `e18026e` → `6a3404f`，两次变动都发生在 2026-09-30 当天）。

前两者不是同一份代码，差 12 个文件、26 个共同文件内容不同，第 17 节会把差别列全。上游若更新，行号会漂移，但结构关系不会。不带 `file:line` 的外部引用，出处写在句子里——它们和行号不是同一类证据，别混着用。

---

## 目录

**上篇 · 解剖一个仓库（第 1 至 12 节）**

把 `tesla-open-can-mod` 的完整源码逐行读完，用 `file:line` 定位每一条结论。选它当解剖对象有两个原因：三个变体里它的代码最工整、抽象层划得清楚；而且它能回答一个具体问题——所谓"操作序列"到底写在代码的哪里。

1. 为什么单独解剖这一个
2. 仓库地图：七个文件的分工
3. 第一层序列：启动
4. 第二层序列：运行
5. 第三层序列：业务
6. 位操作：四个原语
7. 一处被回归测试钉死的耦合
8. 校验和：HW4 独有的一支
9. 驱动抽象：四个实现，一个接口
10. 过滤器掩码的数学
11. 测试：83 个断言覆盖了什么
12. 构建与连接：仓库自己怎么记载

**中篇 · 横向对照与实跑（第 13 至 16 节）**

先用 GitHub 与 GitLab 的公开 API 把能查到的同类仓库逐个拉元数据——谁还在提交、谁冻结了、谁改了名、谁归档了；再按硬件、选型方式、门控、兼容性口径、文档质量、许可证横向对照，**差别比相似更能说明问题**。最后把工具链装上**真的编译**，每条报错留原文。

13. 同类仓库清点：谁还在更新
14. 逐项对照：它们彼此差在哪
15. 门控清单：有什么，没什么
16. 我真的跑了：构建与测试执行记录

**下篇 · 边界与评估（第 17 至 19 节）**

收三样：兼容性这个"诚实的未知"、同类仓库的逐个评估、以及全部 git 链接。**本篇回答"选哪一份"，不回答"怎么用"。**

17. 兼容性：一个诚实的未知
18. 它在哪一层
19. 全部仓库链接与逐个评估

**动手篇 · 一台具体配置：China HW4.0 / 2025 Model 3 / 2026.2.11（第 20 至 24 节）**

唯一面向一台具体车写的部分，硬件前提是手上一块 ESP32-S3、还没有 CAN 收发器。从"先把车钉死"开始，依次是选型与购买清单（含链接与价格）、X179 接线、烧录两条路，以及板子上电之后的页面操作流程——**它到哪里为止，第 24 节末尾写得很明确。**

20. 先把车钉死：这台车意味着什么
21. 选型与购买：清单、价格、链接
22. 接线：从 X179 到螺丝端子
23. 烧录与上电：两条路
24. 板子与车上的操作流程，以及仓库的指南到此为止

**补篇 · 同一套方法，换一个仓库（第 25 节）**

前十一节读的是 `tesla-open-can-mod`，而我最终把推荐给了 `flipper-tesla-fsd`——**推荐了一个自己没读过的仓库**。这一节把欠的补上，用同一套方法（地图 → 三层序列 → 横切面）从头读一遍。

25. 同一套方法，换一个仓库：`flipper-tesla-fsd` 源码解剖

**收尾（第 26 至 27 节）**

外部引用按"一手 / 社区回报 / 未核实"三类列全，逐条给 URL 与页面日期；然后收束全文。

26. 参考与引用：本文用到的每一条外部出处
27. 总结

---

## 1. 为什么单独解剖这一个

说"操作序列"，给结构描述容易，给位置难——知道它分三层是一回事，知道它落在哪几行是另一回事。这一篇给位置。

一个嵌入式固件的"操作序列"通常不在一个函数里，而是**分层**的：上电跑什么、每圈循环跑什么、收到一帧之后跑什么——这三层各自独立，改一层不影响另一层。搞混这三层是读嵌入式代码最常见的坑：有人以为改了 `setup()` 就能改变帧处理行为，其实处理逻辑在另一个文件里。

`tesla-open-can-mod` 把这三层分得很干净，正好当教材。

---

## 2. 仓库地图：七个文件的分工

去掉许可证与图片，真正有信息量的文件是这七个：

| 文件 | 行数 | 承担什么 |
| --- | --- | --- |
| `RP2040CAN.ino` | 62 | Arduino 入口：选板子、选车型、转发到 `app.h` |
| `src/main.cpp` | 45 | PlatformIO 入口，与 `.ino` 等价 |
| `include/app.h` | 63 | **第一、二层序列**：`appSetup()` 与 `appLoop()` |
| `include/handlers.h` | 177 | **第三层序列**：三个 handler 的 `handleMessage()` |
| `include/can_helpers.h` | 27 | 四个位操作原语 |
| `include/can_frame_types.h` | 10 | 可移植的 `CanFrame` 结构 |
| `include/drivers/*.h` | 5 个文件 | 四个驱动实现 + 一个抽象接口 |

测试在 `test/` 下分五组，`guides/` 下有三份人工文档。

这个分工本身就是设计：**车辆逻辑全部集中在 `handlers.h` 和 `app.h`，入口文件只做选型转发。** 换板子改 `platformio.ini`，换车型改一行宏，业务逻辑一行不动。

![三层序列的位置与分工](images/can-mod-teardown-2026/s01-three-layers.svg)

图 1｜三层序列各自住在哪个文件、由谁触发。

---

## 3. 第一层序列：启动

`include/app.h:29-48`：

```cpp
template<typename Driver>
static void appSetup(std::unique_ptr<Driver> drv, const char* readyMsg) {
    appHandler = std::make_unique<SelectedHandler>();
    delay(1500);
    Serial.begin(115200);
    unsigned long t0 = millis();
    while (!Serial && millis() - t0 < 1000) {}

    appDriver = std::move(drv);
    if (!appDriver->init()) {
        Serial.println("CAN init failed");
    }

    appDriver->setFilters(appHandler->filterIds(), appHandler->filterIdCount());
    if constexpr (Driver::kSupportsISR) {
        appDriver->enableInterrupt(canISR);
    }

    Serial.println(readyMsg);
}
```

顺序是固定的，而且顺序本身有含义。

handler 必须先于驱动建立，因为 `setFilters()` 那一行要从 handler 拿过滤器清单。这个依赖把"听哪些 ID"的决定权交给了业务层——驱动不知道自己在听什么，只负责执行。

过滤器装在硬件层。控制器只把匹配的 ID 上报给 CPU，其余帧在芯片里就被丢了。这是省实时性的关键：车身总线上每秒几百帧，全进中断会把主循环淹掉。

最后那句 `if constexpr` 是 C++17 的编译期分支，条件不成立的分支根本不会被实例化——不支持中断的驱动，连 `frameReady` 检查的机器码都不会生成。这比运行时 `if` 更彻底，也比宏可读。

（上面引文与源码逐字一致；下面两处同理。）

一个容易看漏的细节在 `app.h:26`：

```cpp
static volatile bool frameReady = true;
```

初值是 `true`。所以第一圈循环**无论有没有中断都会进一次**。这个设计让"等第一帧"变成无等待，代价是第一圈可能空转一次 `while(read)`。

---

## 4. 第二层序列：运行

`include/app.h:50-63`：

```cpp
template<typename Driver>
static void appLoop() {
    if constexpr (Driver::kSupportsISR) {
        if (!frameReady) return;
        frameReady = false;
    }

    CanFrame frame;
    while (appDriver->read(frame)) {
        digitalWrite(PIN_LED, LOW);
        appHandler->handleMessage(frame, *appDriver);
    }
    digitalWrite(PIN_LED, HIGH);
}
```

这段只有二十行，但有两处设计值得停下来看。

`while(read)` 用的是排空模式。中断只是个"有活了"的信号，真正的读取靠主循环连续调用 `read()` 直到队列空。这样 ISR 只做一件事——置位一个布尔——耗时极短，不会打断别的中断。

`volatile` 也不是可选的：`frameReady` 由 ISR 写、主循环读，没有它编译器可能把它缓存在寄存器里，主循环永远看不到中断的写入。这是嵌入式并发最常见的坑，写对了说明作者踩过。

`PIN_LED` 在读取期间拉低、空闲时拉高——板载灯是"正在工作"指示，不是状态灯。

---

## 5. 第三层序列：业务

`include/handlers.h` 是真正干活的地方。三个 handler 结构高度一致，都继承 `CarManagerBase`（`handlers.h:16-24`）：

```cpp
struct CarManagerBase {
    int speedProfile = 1;
    bool FSDEnabled = false;
    bool enablePrint = true;
    virtual void handleMessage(CanFrame& frame, CanDriver& driver) = 0;
    virtual const uint32_t* filterIds() const = 0;
    virtual uint8_t filterIdCount() const = 0;
    virtual ~CarManagerBase() = default;
};
```

`filterIds()` 和 `handleMessage()` 是一对：**同一个类既声明听什么，又实现听到了怎么办。** 这让过滤器和处理逻辑在代码上强制对齐，改一处不会漏另一处——第一层序列里 `setFilters()` 那一步拿的就是这个。

三个派生类监听的 ID 各不同：

| Handler | 行范围 | 监听 ID |
| --- | --- | --- |
| `LegacyHandler` | `handlers.h:26-62` | 69、1006 |
| `HW3Handler` | `handlers.h:64-118` | 1016、1021 |
| `HW4Handler` | `handlers.h:120-177` | 921、1016、1021 |

选型发生在编译期，`include/app.h:13-21`：

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

`using SelectedHandler = ...` 是**类型别名**，不是运行时变量。三个 handler 的选型在编译期完成，运行时不存在"判断当前是哪款车"的分支。代价是每种车配每种板子都要单独编译一次——对一个要在几毫秒内完成一次总线轮询的 MCU，这个取舍是对的。

### 多路复用：一条 ID 三组语义

以 `HW3Handler` 为样本（`handlers.h:84-116`），ID 1021 上的处理按 `data[0]` 低 3 位分成三支：

```cpp
if (frame.id == 1021) {
    auto index = readMuxID(frame);
    if (index == 0) FSDEnabled = isFSDSelectedInUI(frame);
    if (index == 0 && FSDEnabled) {
        speedOffset = std::max(std::min(((uint8_t)((frame.data[3] >> 1) & 0x3F) - 30) * 5, 100), 0);
        auto off = (uint8_t)((frame.data[3] >> 1) & 0x3F) - 30;
        switch (off) {
            case 2: speedProfile = 2; break;
            case 1: speedProfile = 1; break;
            case 0: speedProfile = 0; break;
            default: break;
        }
        setBit(frame, 46, true);
        setSpeedProfileV12V13(frame, speedProfile);
        driver.send(frame);
    }
    if (index == 1) {
        setBit(frame, 19, false);
        driver.send(frame);
    }
    if (index == 2 && FSDEnabled) {
        frame.data[0] &= ~(0b11000000);
        frame.data[1] &= ~(0b00111111);
        frame.data[0] |= (speedOffset & 0x03) << 6;
        frame.data[1] |= (speedOffset >> 2);
        driver.send(frame);
    }
}
```

（引文删去了其后的 `#ifndef NATIVE_BUILD` 串口打印块，其余逐字对应 `handlers.h:84-116`。）

**mux 0 负责刷新状态，mux 2 负责应用缓存，mux 1 则完全不理会缓存。** 具体到 `HW3Handler`：mux 2 那支带着 `&& FSDEnabled`，用的是 mux 0 存下的值；而 mux 1 那支**根本没有引用 `FSDEnabled`**——它既不重读 UI，也不查缓存，只要收到 mux 1 帧就改比特回发。

这不是笔误，下一节会看到它被测试专门钉住了。三个 handler 的 mux 1 分支都是这个写法，但**三者的 mux 2 并不一致**：HW3 的 mux 2 检查缓存（`handlers.h:104`），HW4 的 mux 2 不检查（`handlers.h:165` 是光秃秃的 `if (index == 2)`），Legacy 则没有 mux 2 这一支。第 15 节会把这个差异列进门控表。

---

## 6. 位操作：四个原语

`include/can_helpers.h` 全文 27 行，是整个项目的词汇表：

```cpp
inline uint8_t readMuxID(const CanFrame& frame) {
    return frame.data[0] & 0x07;
}

inline bool isFSDSelectedInUI(const CanFrame& frame) {
    return (frame.data[4] >> 6) & 0x01;
}

inline void setSpeedProfileV12V13(CanFrame& frame, int profile) {
    frame.data[6] &= ~0x06;
    frame.data[6] |= (profile << 1);
}

inline void setBit(CanFrame& frame, int bit, bool value) {
    int byteIndex = bit / 8;
    int bitIndex = bit % 8;
    uint8_t mask = static_cast<uint8_t>(1U << bitIndex);
    if (value) {
        frame.data[byteIndex] |= mask;
    } else {
        frame.data[byteIndex] &= static_cast<uint8_t>(~mask);
    }
}
```

（逐字对应 `can_helpers.h:5-27`，即全文除 `#pragma once` 与一条 `#include` 之外的全部内容。）

**`setSpeedProfileV12V13` 是读改写的纪律示范。** 掩码 `~0x06` 保留字节里其他位，只动自己该动的两比特。误伤相邻字段是这类工具最常见的 bug，而掩码写法从结构上堵死了它。

**`setBit` 用绝对位号寻址。** `bit / 8` 定位字节、`bit % 8` 定位位内偏移。这也解释了代码里为什么会出现 19、46、47、59、60 这些魔数——**DBC 的"起始位 + 长度"语义在这一层已经被手工展开成绝对位号**。魔数是信号定义的手工复制品，这一点第 14 节会回到。

---

## 7. 一处被回归测试钉死的耦合

上一节那个"mux 2 复用 mux 0 缓存"的行为，值得单独看，因为**它曾是个 bug**。

`test/test_native_hw3/test_hw3_handler.cpp:50` 的注释直接写着：

```cpp
// --- FSD shadowing fix regression test ---
```

测试本体（同文件 52-68 行）：

```cpp
void test_hw3_fsd_enabled_only_set_on_mux0() {
    // Step 1: mux 0 with FSD bit set -> FSDEnabled should become true
    CanFrame f0 = { .id = 1021 };
    f0.data[0] = 0x00; // mux 0
    f0.data[4] = 0x40; // FSD selected
    handler.handleMessage(f0, mock);
    TEST_ASSERT_TRUE(handler.FSDEnabled);

    // Step 2: mux 2 with FSD bit NOT set -> FSDEnabled should STAY true
    mock.reset();
    CanFrame f2 = { .id = 1021 };
    f2.data[0] = 0x02; // mux 2
    f2.data[4] = 0x00; // FSD bit not set in this frame
    handler.handleMessage(f2, mock);
    TEST_ASSERT_TRUE(handler.FSDEnabled);
    TEST_ASSERT_EQUAL(1, mock.sent.size()); // mux 2 should still send because FSDEnabled is latched
}
```

（逐字对应，未删一字。）

"shadowing"这个词点出了原 bug 的性质：**mux 2 的帧自己带了一个 `data[4]`，早期实现若在每个分支都重读 UI 位，mux 2 那帧的 `data[4]` 会把 mux 0 刚存下的状态覆盖掉**——语义上叫变量遮蔽，结果是状态被错误的帧冲掉。

修复方式是让读取只发生在 mux 0，并用回归测试锁死这个行为。HW4 那边有一份孪生测试，`test_native_hw4/test_hw4_handler.cpp:56` 注释同样写着 `FSD shadowing fix regression test`。

![状态缓存的时序耦合](images/can-mod-teardown-2026/s02-state-latch.svg)

图 2｜mux 0 写入状态、mux 2 复用状态，mux 1 两者都不做。mux 2 帧自带的 `data[4]` 若参与读取，就会覆盖真实状态，也就是回归测试防的那个东西。

**这件事的价值不在修复本身，而在于它展示了这个项目的成熟度**：发现隐式耦合 → 加测试锁死 → 把修复意图写进测试名。要说这类项目凭什么"值得读"，这就是具体证据。

---

## 8. 校验和：HW4 独有的一支

`HW4Handler` 监听的 `921` 走一条别的 handler 没有的路径（`handlers.h:130-138`）：

```cpp
if (isaSpeedChimeSuppress && frame.id == 921) {
    frame.data[1] |= 0x20;
    uint8_t sum = 0;
    for (int i = 0; i < 7; i++) sum += frame.data[i];
    sum += (921 & 0xFF) + (921 >> 8);
    frame.data[7] = sum & 0xFF;
    driver.send(frame);
    return;
}
```

三个细节。

改了前 7 字节就必须重算第 8 字节，不算的话接收方校验失败、整帧被丢——丢帧在总线上表现成"偶发不生效"，排查起来极痛苦。

校验和里掺了 ID 的高低字节，这让校验覆盖"这是哪条报文"，防止帧被换到别的 ID 上仍能通过。

末尾那个 `return` 提前退出，改完这帧就不再走后面的 FSD 逻辑。测试 `test_hw4_isa_suppress_returns_early_no_further_processing`（`test_hw4_handler.cpp:214`）专门断言了"只有一次发送"。

这个开关默认是关的，`handlers.h:14`：

```cpp
constexpr bool DEFAULT_ISA_SPEED_CHIME_SUPPRESS = false;
```

**需要显式改这个常量才会启用**——这是我在三个仓库里见到的唯一一处"能力默认关闭且写死在编译期"。同一文件 `handlers.h:13` 的 `enableEmergencyVehicleDetection = true` 则默认开启，两者形成对照。

---

## 9. 驱动抽象：四个实现，一个接口

`include/drivers/can_driver.h` 全文 12 行，接口本身就是这几行：

```cpp
struct CanDriver {
    virtual bool init() = 0;
    virtual void setFilters(const uint32_t* ids, uint8_t count) = 0;
    virtual bool enableInterrupt(void (*onReady)()) = 0;
    virtual bool read(CanFrame& frame) = 0;
    virtual void send(const CanFrame& frame) = 0;
    virtual ~CanDriver() = default;
};
```

四个实现各自带一个 `kSupportsISR` 编译期常量：

| 驱动 | 文件 | 控制器 | `kSupportsISR` |
| --- | --- | --- | --- |
| `MCP2515Driver` | `mcp2515_driver.h` | SPI 外置 MCP2515 | **true** |
| `SAME51Driver` | `same51_driver.h` | 芯片内置 MCAN | false |
| `TWAIDriver` | `twai_driver.h` | ESP32 内置 TWAI | false |
| `MockDriver` | `mock_driver.h` | 测试桩 | false |

**只有 SPI 外置控制器用中断**，三个内置控制器全部走轮询。源码里留了理由，`same51_driver.h:35-37`：

```cpp
// SAME51 uses register reads (no SPI overhead) and an 8-deep HW FIFO.
// The library's onReceive() consumes frames inside the ISR, which is
// incompatible with our "flag + drain" pattern. Keep polling with HW filters.
```

TWAI 那边的理由在 `twai_driver.h:53-56`：FreeRTOS 队列有 32 深，`twai_receive(&msg, 0)` 是一次廉价的队列窥视，为它开一个专用任务"增加复杂度而无实际收益"。

**两条注释都不是省事，是权衡后选了另一边。** 这比无注释的默认选择有价值得多——下一个维护者能知道为什么不能"顺手改成中断"。

`TWAIDriver` 还有一处独有设计（`twai_driver.h:59-94`）：`read()` 和 `send()` 失败时都会检查 `isBusOff()` 并调 `recover()` 重装驱动。**CAN 控制器在总线错误累积到阈值后会进入 bus-off 状态，不主动恢复就永久失联。** 四个驱动里只有 TWAI 实现了自恢复——另外三个在同样条件下会静默停止工作。

---

## 10. 过滤器掩码的数学

`appSetup()` 里 `setFilters()` 那一步把过滤器装进硬件，但四个驱动的过滤能力完全不同：MCP2515 有 6 个独立精确匹配槽位，TWAI 和 SAME51 **只有一个组合滤波器**。单滤波器要接受多个 ID，就得算掩码。

TWAI 的实现（`twai_driver.h:27-51`）：

```cpp
// Compute combined mask: bits that differ between any pair of IDs
// are "don't care" in the acceptance mask.
uint32_t differ = 0;
for (uint8_t i = 1; i < count; i++) {
    differ |= ids[0] ^ ids[i];
}
// TWAI standard-frame single-filter layout:
//   acceptance_code bits [31:21] = standard ID [10:0]
//   acceptance_mask: 1 = don't care, 0 = must match
//   Lower 21 bits set to 1 (don't care about RTR, data bytes)
uint32_t base = ids[0] & ~differ;
f_config_.acceptance_code = base << 21;
f_config_.acceptance_mask = (differ << 21) | 0x001FFFFF;
```

（逐字对应 `twai_driver.h:30-43`；后面的 `twai_stop()` / 重装 / `twai_start()` 段落是重装驱动，与掩码数学无关，此处略去。）

逻辑是：**任意两个 ID 异或，不同的位就是"不关心"位。** 把所有不关心位并起来当掩码，剩下的位必须匹配第一个 ID。SAME51 用同一套思路，只是位序不同（`same51_driver.h:21-33`）。

这里有个必然的副作用：**掩码越宽，接受的 ID 越多。** Legacy 的两个 ID（69 和 1006）差得很远，算出来的掩码会放过一堆无关 ID。测试文件自己承认了这点，`test_native_twai/test_twai_filter.cpp:118` 的分节注释写着：

```cpp
// --- Legacy: wide gap means wider mask (false positives expected) ---
```

**false positives expected**——预期会有误接受。这不是疏忽，是单滤波器的固有代价，而**真正的正确性由软件保证**：`handleMessage()` 每支都先 `if (frame.id == ...)` 精确比对，误接受的帧进来也会被丢掉。硬件过滤只负责省电省中断，不负责语义正确。

测试把这个数学单独抽出来验：`test_twai_filter.cpp:4-5` 的注释写明原因，紧接着 11-23 行是把 `setFilters()` 的计算逻辑原样复制的一份：

```cpp
// Extracted filter computation logic from TWAIDriver::setFilters() so we can
// unit-test the math without the ESP-IDF TWAI hardware API.
```

其中最漂亮的一个断言是 `test_twai_filter_hw4_mask_bits`（145-152 行）——**手工算出期望掩码再比对**：

```cpp
// 921 ^ 1016 = 0x061, 921 ^ 1021 = 0x064, 1016 ^ 1021 = 0x005
// differ = 0x061 | 0x064 | 0x005 = 0x065
uint32_t expected_mask = (0x065u << 21) | 0x001FFFFF;
TEST_ASSERT_EQUAL_HEX32(expected_mask, f.acceptance_mask);
```

注意它的代价：**逻辑被复制了一份，实现改了测试不会跟着改。** 这是把硬件依赖剥离去测的常见权衡，好处是能在主机上跑，代价是测试和实现可能漂移。这个仓库选了后者，我认为选得对——能跑的错测试比跑不了的对测试有用。

---

## 11. 测试：83 个断言覆盖了什么

五组测试，我逐个 `RUN_TEST` 数过：

| 测试组 | 断言数 | 覆盖对象 |
| --- | --- | --- |
| `test_native_helpers` | 18 | 四个位操作原语 |
| `test_native_legacy` | 12 | LegacyHandler |
| `test_native_hw3` | 13 | HW3Handler |
| `test_native_hw4` | 23 | HW4Handler（含 ISA 校验和） |
| `test_native_twai` | 17 | TWAI 过滤器掩码数学 |
| **合计** | **83** | |

`platformio.ini:29-32` 把它们跑在主机上，不碰硬件：

```ini
[env:native]
platform = native
build_flags = -std=c++17 -DNATIVE_BUILD
test_filter = test_native_*
```

`-DNATIVE_BUILD` 是关键开关：`app.h:9-11` 与 `handlers.h:9-11` 都用它隔离 Arduino 头文件，串口打印也被 `#ifndef NATIVE_BUILD` 包起来（如 `handlers.h:111-115`）。**同一份业务代码既能编译进 MCU，也能编译进主机当纯逻辑跑**——这是整个测试体系成立的前提。

测试靠 `MockDriver`（`mock_driver.h`）捕获发送：`send()` 不上总线，只 `sent.push_back(frame)`，于是断言发送次数与帧内容变成可能。

`test_native_helpers` 里有一组测试特别值得看（104-130 行）——它验证的是**掩码不误伤**：

```cpp
void test_setSpeedProfileV12V13_preserves_other_bits() {
    CanFrame f = {};
    f.data[6] = 0xF9; // bits 1-2 clear, rest set
    setSpeedProfileV12V13(f, 1);
    TEST_ASSERT_EQUAL_HEX8(0xFB, f.data[6]);
}
```

**上一节说的"读改写纪律"，在这里被量化成了断言。**

必须说清楚的是：写这一节的时候我**还没有运行这些测试**——本机尚未装 PlatformIO。当时做的是逐个 `RUN_TEST` 计数、逐个读断言内容，数量是准的，通过与否我不能背书。**第 16 节补上了真实执行：本地副本 83/83 通过，与这里的计数完全一致。**

---

## 12. 构建与连接：仓库自己怎么记载

这一节转述仓库自带文档，讲**这个系统如何被组装起来**——它是理解架构的一部分，不是执行清单。所有内容来自 `README.md` 与 `guides/`，我只是复述并标注位置。

顺序是：**选板子 → 选车型（HW4 车要多过一道版本判断）→ 构建烧录 → 接线 → 供电 → 验证。** 前四小节是各自要查的资料，最后一小节 **完整步骤** 把它们串成一条能照着走的线。

### 两层选型

选型发生在两个地方，且都在编译期：

**板子**（`RP2040CAN.ino:16-20`）：

```cpp
#define DRIVER_MCP2515   // Adafruit Feather RP2040 CAN (MCP2515 over SPI)
//#define DRIVER_SAME51  // Adafruit Feather M4 CAN Express (native ATSAME51 CAN)
//#define DRIVER_TWAI    // ESP32 boards with built-in TWAI (CAN) peripheral
```

仓库把支持矩阵写在 `README.md:100-105`，是**四**行——比我上面那三个宏多一行：

| 板子 | 驱动宏 | 库 / 接口 | 每板特有的前提 | 仓库标注状态 |
| --- | --- | --- | --- | --- |
| Feather RP2040 CAN | `DRIVER_MCP2515` | autowp `mcp2515.h`（SPI） | 需 `PIN_CAN_CS` 等四个引脚（`README.md:112-116`） | **Tested** |
| Feather M4 CAN Express | `DRIVER_SAME51` | `Adafruit_CAN`（`CANSAME5x`） | 需 `PIN_CAN_BOOSTEN`，3V→5V 电平升压（`:118-120`） | Compiles, needs on-vehicle testing |
| ESP32 + 外接收发器 | `DRIVER_TWAI` | 内核自带 `driver/twai.h` | 必须外接收发器，默认 `GPIO_NUM_5`/`4`（`:122-125`） | Compiles, needs on-vehicle testing |
| M5Stack [Atomic CAN Base](https://docs.m5stack.com/en/atom/Atomic%20CAN%20Base) | `DRIVER_TWAI`（复用） | CA-IS3050G over ESP32 TWAI | — | **Tested** |

四行对三个宏，原因是**第四块板骑在 `DRIVER_TWAI` 上**：`platformio.ini:24-27` 的 `env:m5stack-atomic-can-base` 写的是 `extends = env:esp32_twai`——连驱动宏都是继承来的，只额外注入了 LED 与两个 TWAI 引脚。想加第五块板，先判断它落进哪个宏，而不是先加宏。

**状态那一列值得看两眼。** 四块板里只有 RP2040 与 M5Stack 标了 `Tested`；**M4 与 ESP32 明写着 `Compiles, needs on-vehicle testing`**——编得过、没上过车。而本节那套操作步骤与两份指南，恰恰是围着 M4 那块写的。仓库没把这件事藏起来，它就摆在表格里。

**ESP32 那行有个陷阱**：TWAI 只是控制器，不含收发器——不外接 transceiver，物理上就发不出去。四块板里只有它"板子本身不完整"。

**车型**（`RP2040CAN.ino:22-26`）：

```cpp
#define LEGACY // HW4, HW3, or LEGACY
//#define HW3
//#define HW4
```

PlatformIO 走 `platformio.ini` 的 `build_flags`，五个环境各自带上驱动宏：

```ini
[env:feather_rp2040_can]   build_flags = -DDRIVER_MCP2515
[env:feather_m4_can]       build_flags = -DDRIVER_SAME51 -std=gnu++14
[env:esp32_twai]           build_flags = -DDRIVER_TWAI
[env:m5stack-atomic-can-base]  extends = env:esp32_twai
                            build_flags = ... -DTWAI_TX_PIN=GPIO_NUM_22 -DTWAI_RX_PIN=GPIO_NUM_19
[env:native]               build_flags = -std=c++17 -DNATIVE_BUILD
```

M5Stack 那行说明**引脚也能从构建参数注入**——同一份 TWAI 驱动换块板子只需改两个宏，不动代码。（上面这块为了对齐把每个环境压成一行，是缩写拼贴而非 `platformio.ini` 原文；逐条读请见 `platformio.ini:1-32`。）

### HW4 车与 OTA 版本：该选哪个宏

这是最容易选错的一处，因为**决定编译参数的不是硬件型号，而是车上软件对应的 FSD 版本。**

三个宏对应的收听 ID 与能力（`README.md:44-48`）：

| 宏 | 目标 | 收听 CAN ID | 说明 |
| --- | --- | --- | --- |
| `LEGACY` | HW3 改装车 | 1006、69 | 用跟随距离拨杆控制速度档位，并置位 FSD 使能位 |
| `HW3` | HW3 车型 | 1016、1021 | 与 `LEGACY` 同等能力 |
| `HW4` | HW4 车型 | 1016、1021 | 速度档位扩展到 5 级 |

注意 **`HW3` 与 `HW4` 收听的 ID 完全相同**，差别只在速度档位的取值范围——这两个之间选错，不会"听不到"，而是档位范围与车上软件的预期对不上。若在 HW3/HW4 车上选了 `LEGACY`，则是 ID 整个不重合，一条也收不到。

`README.md:50` 是全仓库唯一一处把 OTA 分支和编译参数绑起来的地方：

> **Note:** HW4 vehicles on firmware **2026.2.9.X** are on **FSD v14**. However, versions on the **2026.8.X** branch are still on **FSD v13**. If your vehicle is running FSD v13 (including the 2026.8.X branch or anything older than 2026.2.9), compile with `HW3` even if your vehicle has HW4 hardware.

翻成人话：**HW4 硬件 ≠ 编译 `HW4`。** 版本号看着更大的 `2026.8.X` 反而要选 `HW3`，因为 OTA 分支不是线性推进的——2026.8.X 这条支线还停在 v13。判断顺序是**先看硬件，再看软件版本落在哪条分支，两者冲突时以软件版本为准。**

硬件型号从车机上读（`README.md:52-56`）：**Controls → Software → Additional Vehicle Information**。显示 HW4 即 HW4；竖屏 + HW3 属 Legacy，横屏 + HW3 属 HW3（上游 `README.md:74-75` 是同一个说法）。

#### 把判断落到一个具体版本：HW4 + 2026.2.11

我按上面那条规则把你最常问的那种情况走一遍，顺便说明为什么它比别的版本号好判断。

| 你的条件 | 判断过程 | 该编哪个宏 |
| --- | --- | --- |
| 硬件 HW4，OTA **2026.2.11** | `2026.2.11` **不早于** `2026.2.9`，也**不在** `2026.8.X` 支线 → 落在 FSD v14 | **`HW4`** |

关键在于 **2026.2.11 同时高过两个有争议的阈值**。社区里一直在吵 v14 到底从 `2026.2.3` 起还是从 `2026.2.9` 起（`herrfrei`、`juamiso` 报 2026.2.3，仓库自己的 `README.md:69` 写 2026.2.9），差六个小版本号。**但 2026.2.11 比两个都大，两种口径给出同一个答案：`HW4`。** 这一类"阈值之争"只在你的版本号卡在两个阈值中间时才会真正咬人。

同理，`2026.8.6`、`2026.14.x` 这些**版本号更大**的车反而要编 `HW3`——OTA 分支是岔开的，不是一条直线往上走。

*证据强度：弱。`README.md:69` 的行号可复现，但 2026.2.11 上车实跑我做不到，没有板子也没有车；社区那两个阈值都是单点回报。*

选完之后宏放到哪一行：**Arduino IDE 与 PlatformIO 现在读的是同一处**——`RP2040CAN.ino` 顶部的选型区（上游 `README.md:207`、`:215`）。这一处的上游实现和我手上这份本地副本不一样，第 14 节末尾、第 16 节和第 17 节会把差别摊开讲。

### 物理连接

`README.md:260-276` 与 `guides/WIRING_GUIDE.md` 记载的连接点是车身网络连接器，逻辑信号是经典 CAN 的两根线：

| 连接器 | CAN-H | CAN-L |
| --- | --- | --- |
| X179 | pin 13 | pin 14 |
| X652（2020 及更早） | pin 1 | pin 2 |

`WIRING_GUIDE.md` 另外给了成品线束方案与直连方案两条路，并在 `WIRING_GUIDE.md:49` 写了一条硬性约束：

> **Important:** If your board or CAN module has an onboard 120 Ohm termination resistor, **cut or remove it** before connecting.

这条约束的原理值得记：CAN 总线两端各需一个 120Ω 终端电阻形成匹配阻抗，**车身已经装好了**。再并一个上去会把阻抗拉错，导致信号反射与通信错误——这正是 README 那句"adding a second resistor will cause communication errors"的物理含义。

### 验证方式

`guides/INSTALLATION_GUIDE_M4_CAN.md:65-74` 记载的验证是**开串口看输出**：115200 波特率下应看到 handler 打印的 FSD 状态与当前 profile，例如：

```
HW3Handler: FSD: 1, Profile: 2, Offset: 0
```

这些打印来自 `handlers.h` 里被 `#ifndef NATIVE_BUILD` 包住的分支，由 `enablePrint` 控制（默认 `true`，`handlers.h:19`）。

### 完整步骤：把上面几节串成一条线（已实测）

> **先说一句版本。** 这一节以 **GitHub 上的 `1-v-1/tesla-open-can-mod`（commit `815e000`，2026-04-02）** 为准，不用我手上那份本地副本——第 17 节会列出差多少，简单说：本地副本缺一个关键脚本，照它做会白折腾一轮。下面凡是标了 `上游 README.md:N` 的行号都对着刚 clone 下来的仓库。

**① 取源码。** 用网络版：

```bash
git clone https://github.com/1-v-1/tesla-open-can-mod.git
cd tesla-open-can-mod
```

**② 装工具链**（Windows，我实际用的版本）：

| 工具 | 用途 | 我的版本 | 装法 |
| --- | --- | --- | --- |
| Python | PlatformIO 运行时 | 3.12.10 | — |
| PlatformIO CLI | 构建与测试 | 6.2.0 | `pip install platformio` |
| MinGW-w64 GCC | **仅** `pio test -e native` 需要 | 16.2.0 | `winget install BrechtSanders.WinLibs.POSIX.UCRT` |

> 装完 MinGW 要**重启终端**，`g++` 才进 PATH。交叉编译到板子用 PlatformIO 自带的工具链，**不需要** MinGW（上游 `README.md:211`）。首次构建会下载几十 MB 到几百 MB 工具链，等它跑完。

**③ 改 `RP2040CAN.ino`。** 这是网络版和本地副本最大的一处差别：**网络版出厂状态下，驱动宏和车型宏全部是注释掉的**，必须由你解开，而且只能各解开一个。

上游 `README.md:207` 与 `:215` 的要求是两步，改完长这样（**下例是 ESP32 + HW4 的最终状态**，三选一处只动你那两行）：

```cpp
// 第 1 步：解开你那块板（三选一）
//#define DRIVER_MCP2515   // Adafruit Feather RP2040 CAN (MCP2515 over SPI)
//#define DRIVER_SAME51    // Adafruit Feather M4 CAN Express (native ATSAME51 CAN)
#define DRIVER_TWAI        // ESP32 boards with built-in TWAI (CAN) peripheral

// 第 2 步：解开你的车（三选一）
//#define LEGACY           // HW3 改装
//#define HW3              // HW3
#define HW4                // HW4
```

**HW4 + 2026.2.11 的车，这里就是解开 `DRIVER_TWAI`（换板就换成那块板的那行）和 `HW4` 两行**，其余保持注释。

**别忘了可选的两个宏**——同一区域还有 `ISA_SPEED_CHIME_SUPPRESS` 和 `EMERGENCY_VEHICLE_DETECTION`，默认也是注释的。它们不像前两组那样"必须恰一个"，脚本会把**你解开的全部**一起注入（`platformio_sync_ino_defines.py:72`、`:98-101`）。不关心就都留着注释，缺省即关。

为什么前两组"只能解开一个"：脚本会逐行扫 `RP2040CAN.ino`，只认行首为 `#define` 的行（`:14-23`，`//#define` 不算），两组各数出一个（`:70-71`），**少了多了都直接报错**。它再校验你的 `-e` 环境的驱动宏是否与之一致（`:85-90`），最后把车型宏追加进编译命令（`:98-101`）。**这一步就是本地副本缺的那一环**——所以"得自己往 `build_flags` 加 `-DHW3`"的坑在网络版上不存在了，代价是多了一条硬约束。

**④ 构建。** env 选板子，`.ino` 选车，两者必须对得上：

```bash
pio run -e esp32_twai             # ESP32 + 外接收发器（SN65HVD230 等）
pio run -e m5stack-atomic-can-base # M5Stack ATOM + Atomic CAN Base
pio run -e feather_m4_can         # Feather M4 CAN Express
pio run -e feather_rp2040_can     # Feather RP2040 CAN
pio test -e native                # 主机跑单测，需 MinGW
```

**四块板我都真跑过，结果如下**（2026-09-30，Windows 11，PlatformIO 6.2.0）：

| env | 结果 | 关键输出 |
| --- | --- | --- |
| `esp32_twai` | **SUCCESS** | `Synced RP2040CAN.ino defines for esp32_twai: HW4`；RAM 14.6%、Flash 61.7% |
| `m5stack-atomic-can-base` | **SUCCESS** | RAM 14.6%、Flash 61.7% |
| `feather_m4_can` | **SUCCESS** | `Synced ... feather_m4_can: HW4`；RAM 3.7%、Flash 6.0% |
| `feather_rp2040_can` | **SUCCESS**（改一处后） | `Synced ... feather_rp2040_can: HW4`；RAM 5.1%、Flash 0.5% |
| `native` 三套共 8 个套件 | **107/107 PASSED** | — |

**路上我会撞的三个坑，都是我真撞的，附原始报错：**

| # | 报错原文 | 原因 | 怎么过 |
| --- | --- | --- | --- |
| 1 | `RP2040CAN.ino must enable exactly one driver define: DRIVER_MCP2515, DRIVER_SAME51, DRIVER_TWAI.` | 出厂全注释，一个都没解 | 按 ③ 解开驱动宏和 `HW4` |
| 2 | `RP2040CAN.ino selects DRIVER_TWAI, but PlatformIO env 'feather_m4_can' is configured for DRIVER_SAME51.` | `.ino` 写 ESP32，却编 M4 的 env | 两者改到一致；**这条不是 bug，是脚本在拦你** |
| 3 | `UnknownPackageError: Could not find the package with 'autowp/MCP2515' requirements` | registry 上那个包已经改名 | `platformio.ini` 里把 `lib_deps = autowp/MCP2515` 改成 `autowp/autowp-mcp2515` |

坑 3 我查过 registry API 才确认：`https://api.registry.platformio.org/v3/packages/autowp/library/MCP2515` 返回 **404**，而 `search?query=autowp` 返回的是 **`autowp/autowp-mcp2515`**（v1.3.1）。**这是仓库自身的失修，不是你的环境问题**——只有 RP2040 那个 env 中招，另外三块板不受影响。

烧录（**我没有板子，未执行**，转述上游 `README.md:272-289`）：

```bash
pio run -e esp32_twai --target upload
pio run -e feather_rp2040_can --target upload   # Feather 没识别就双击 Reset 进 UF2
pio run -e feather_m4_can --target upload
pio run -e m5stack-atomic-can-base --target upload
```

**走 Arduino IDE 的话**（上游 `README.md:203-227`）：装 IDE → Board Manager URL（`README.md:141-165`：RP2040 填 earlephilhower 那条、M4 填 adafruit 那条、ESP32 填 espressif 那条）→ 装板卡包 → 装库（`README.md:167-173`，**ESP32 一个都不用装**）→ 同样在 `RP2040CAN.ino` 里解开两行 → 选板 → Upload。

> 指南第 5 步那行 `#define HW_TARGET TARGET_HW3` 是裂缝一——**源码里没有这个宏**，跳过它，用 ③ 的写法。

**⑤ 接线。** 两条路：

- **成品线束**（Enhance Auto Gen 2，线序见 `WIRING_GUIDE.md:33-39`）：红 → DC/DC IN+，黑 → DC/DC IN−，带条纹 → CAN-H，纯黑 → CAN-L，**剩下那对黑线不接**
- **直连**：X179 **pin 13 / 14**，或 X652 **pin 1 / 2**（2020 及更早）

> ⚠️ **X179 到底在哪，两份指南说法相反**：`INSTALLATION_GUIDE:57` 说在 *"driver's side trunk panel"*，`WIRING_GUIDE:16` 说在 *"passenger side footwell"*。同一台 2023 Model 3 不可能两处都是。**照任何一份动手前，先按你车的实际布局确认**——两份指南都附了 Enhance Auto 的实拍视频，以视频为准。

> ⚠️ 接线前**剪掉板上的 120Ω 终端电阻**（`WIRING_GUIDE:49`），车身已有终端，并一个上去会引发通信错误。

**⑥ 供电。** DC/DC 把 12V 转 5V USB-C 接红、黑两根；验证阶段改用笔记本 USB 供电。

**⑦ 功能验证**（依 `INSTALLATION_GUIDE_M4_CAN.md:65-74`）：

1. 拔掉 DC/DC，改接笔记本 USB
2. 串口 115200，应见 `HW3Handler: FSD: 1, Profile: 2, Offset: 0`
3. 若未开，在 Autopilot 设置里打开 **Traffic Light and Stop Sign Control**
4. 拨动跟随距离拨杆，确认串口里的 `Profile` 值跟着变
5. 确认无误后断开笔记本、接回 DC/DC

串口里那个 `Profile: N` 怎么读——`README.md:287-293` 给了拨杆档位到速度档位的映射，**HW3 与 HW4 的范围不同**：

| 拨杆档位 | Profile (HW3) | Profile (HW4) |
| --- | --- | --- |
| 2 | ⚡ Hurry | 🔥 Max |
| 3 | 🟢 Normal | ⚡ Hurry |
| 4 | ❄️ Chill | 🟢 Normal |
| 5 | — | ❄️ Chill |
| 6 | — | 🐢 Sloth |

**HW4 整体右移一格，多出 `Max` 与 `Sloth` 两档**——步骤② 里"`HW4` 宏速度档位扩展到 5 级"说的就是这一格。反过来用：如果你在 HW4 车上看到 `Profile: 5` 或 `6` 却编的是 `HW3` 宏，说明档位解读已经错位。

### 不对劲时查哪里

按症状回溯，线索全在源码里：

| 症状 | 可能原因 | 出处 |
| --- | --- | --- |
| 编译报 `must enable exactly one driver define` | `RP2040CAN.ino` 里驱动/车型宏一个都没解开 | 上游 `README.md:207`、`:215`（**已实测**） |
| 编译报 `selects DRIVER_TWAI, but ... configured for DRIVER_SAME51` | `.ino` 的驱动宏与 `-e` env 不匹配 | `scripts/platformio_sync_ino_defines.py:85-90`（**已实测**） |
| 编译报 `Could not find the package with 'autowp/MCP2515'` | registry 包已改名，只有 RP2040 env 中招 | `platformio.ini:7` 改成 `autowp/autowp-mcp2515`（**已实测**） |
| 编译报 `#error "Define HW4, HW3 or LEGACY in build_flags"` | 只存在于**本地副本**：它没有 sync 脚本，见第 14 节裂缝二 | 本地 `app.h:20` |
| 完全没有串口输出 | 波特率不是 115200，或 `enablePrint` 被置为 `false` | `README.md:297`、`handlers.h:19` |
| 串口打印 `CAN init failed` | 控制器初始化失败：SPI/CS 接线，或驱动宏与实际板子不符 | `app.h:38-39` |
| 有输出但**一个帧都收不到** | 车型宏选错，过滤器 ID 与车上实际不符 | `handlers.h:28`（Legacy 69/1006）、`:68`（HW3 1016/1021）、`:124`（HW4 921/1016/1021） |
| 总线通信错误、帧偶发丢 | 板上 120Ω 终端电阻没剪 | `WIRING_GUIDE.md:49` |
| ESP32 收得到发不出 | 没外接 CAN 收发器，或 TX/RX GPIO 宏没配对 | `README.md:306`、`platformio.ini:27` |
| 板子完全不亮 | DC/DC 没接，或 12V 极性反了 | `WIRING_GUIDE.md:35-36` |

仓库自己记载的全部操作流程就到这里。它到"Profile 值随拨杆变化"为止——指南里没有比这更进一步的验证步骤。

至于我这一侧，边界得划清楚。**编译这一段我已经真跑了**：工具链装了、四块板的固件都出了 `firmware.bin`、83+107 个单测都过了，上面表格里的 SUCCESS 与三条报错都是我机器上的原始输出。**烧录、接线、上电之后的一切，我没有做**——我没有板子、没有线束、没有车辆。所以：仓库说这样做会打印这些，我转述；帧是否真的被上位机接受、车机上是否真的多出那个开关，我不作担保，也不会替你担保。

仓库的指南到此为止，我也到此为止。

---

## 13. 同类仓库清点：谁还在更新

解剖讲完了，把镜头拉远。同一条总线上公开躺着的实现，远不止前面那三个。这一节把能查到的逐个列出来，只报数字，不下判断——判断留给第 14 节。

### 我怎么查的

三个公开接口，2026-09-30 当天查询：

- GitHub REST `GET /repos/{owner}/{repo}` → star、fork、created_at、pushed_at、license、open_issues
- GitHub REST `GET /repos/{owner}/{repo}/releases` → tag 与发布日期
- GitLab REST `GET /api/v4/projects/{url-encoded-id}` → star、last_activity_at、archived

未认证调用，配额 60 次/小时，我实际用了 42 次。表里每个数字都能用同样的请求复现；这也是本文唯一一类**不靠人转述、直接问托管平台**的外部结论。

**2026-10-01 我把这张表整张复核了一遍**——配额没恢复，改用 `git ls-remote`、`releases.atom` 与页面抓取逐项重问：**18 个 star 数对上 17 个**（`tuncasoftbildik` 从 41 涨到 43）；五个主干里四个的本地克隆与上游 HEAD 完全一致，**它们的构建与测试数据因此仍然有效**；**两处判错已订正**——flipper 最新 release 已走到 `v2.16-beta.33`，`JordanzhaoD` 不是"无 release"而是有 10 个。唯一真的移动过的仓库是 `hypery11/flipper-tesla-fsd`，它让我付的代价记在第 25 节。

查询中遇到一件事值得先说：GitLab 的项目接口会把旧路径 302 到新路径。我拿 `Starmixcraft/tesla-fsd-can-mod` 去查，返回的 `path_with_namespace` 却是别的值——这条后面单独讲。

### 主干：五个还在动的

| 仓库 | 最后 push | ★ | 最新版本（发布日） | 许可证 |
| --- | --- | --- | --- | --- |
| `hypery11/flipper-tesla-fsd` | 2026-09-30（API 限流后改用 `git ls-remote` + 本地 fetch 复核） | 1094 | `v2.16-beta.33`（2026-09-30，打在 `6a3404f` 上） | NOASSERTION |
| `ev-open-can-tools/ev-open-can-tools` | 2026-09-20 | 174 | `v4.0.0-beta.3`（2026-09-20）／正式版 `v3.1.1`（2026-08-03） | GPL-3.0 |
| `JordanzhaoD/waveshare-single-can-firmware` | 2026-09-22 | 17 | `v1.20.1-atlas-single-can`（2026-09-22，全表 10 个 release） | GPL-3.0 |
| `dzid26/ESP32-DualCAN` | 2026-09-21 | 40 | `hw-v1.1`（2026-09-03） | CERN-OHL-W-2.0 |
| `babico/TeslaCANModder` | 2026-09-10 | 5 | `v1.5.0`（2026-06-22） | WTFPL |

另有几个"半活跃"：`tuncasoftbildik/tesla-can-mod`（2026-08-23，43★，无 release）、`06066060606060/nag-killer`（2026-09-15，12★）、`06066060606060/Summon-Unlock`（2026-09-03，12★）、`ev-open-can-tools/ev-open-can-tools-app`（2026-08-16，1★）。同组织的 `ev-open-can-tools-plugins` 停在 2026-05-04，27★。

### 冻结：跟本文这个副本同一时期停下的

| 仓库 | 最后 push | ★ | 备注 |
| --- | --- | --- | --- |
| **`1-v-1/tesla-open-can-mod`** | **2026-04-02** | 27 | **本文所有 `file:line` 的上游**；无 tag、无 release |
| `jvanakker/tesla-fsd-can-mod` | 2026-04-08 | 142 | CanFeather 镜像，README 自带失效警告 |
| `mert574/tesla-fsd-can-mod` | 2026-04-05 | 0 | |
| `Karolynaz/waymo-fsd-can-mod` | 2026-04-08 | 2 | `fork=true` |
| `qmwdy/tesla-fsd-can-mod` | 2026-04-08 | 0 | `fork=true` |
| `iubns/tesla-fsd-can-mod` | 2026-03-30 | 16 | GPL-3.0 |
| `Xingheee/tesla-fsd-can-mod` | 2026-03-29 | 1 | `fork=true` |
| `davidgrylls825/tesla-fsd-can-mod` | 2026-03-30 | 0 | `fork=true` |
| `herrfrei/tesla-fsd-canbus-esp32` | 2026-03-29 | 1 | ESP32-S2/S3/C3/PICO 移植，README 自称 unofficial port |
| `juamiso/tesla-fsd-can-enabler` | 2026-03-30 | 0 | |
| `JelloEa/tesla-fsd-controller` | 2026-03-31 | 36 | ESP32 WiFi Web 版，README 提"支持中国模式" |
| `JelloEa/Tesla-Open-CAN-Mod` | 2026-03-31 | 10 | GPL-3.0 |
| `dongho74s/tesla-open-can-mod` | 2026-03-31 | 2 | GPL-3.0 |
| `superpositiontime/tesla-fsd-comma4` | 2026-03-29 | 15 | |
| `lenfien/tesla-open-can-mod-release` | 2026-04-17 | 5 | GPL-3.0 |
| `tumik/S3XY-candump` | 2025-04-17 | 16 | 商业件 S3XY Commander 的配套 Python 工具，比整件事还早一年 |

这一栏里最该注意的是第一行：**本文的解剖对象，上游最后一次 push 停在 2026-04-02，到写作日已经 181 天没动过，而且从来没打过 tag。** 第 17 节会讲这件事对"行号保质期"意味着什么。

### 查不到的

同一批查询里，这几个返回 404：

| 路径 | 说明 |
| --- | --- |
| `github.com/linesoft2/tesla-fsd-can-mod-fork` | 曾有 29★，中文 README 写着中国区 Gateway 禁用那句。全名搜索接口已不再返回它 |
| `github.com/niccolodevries/tesla-fsd-can-enabler` | 搜索 `tesla-fsd-can-enabler` 只剩 `juamiso` 一个 |
| `github.com/mikegapinski/tesla-can-explorer` | 见下 |
| `github.com/mikegapinski/tesla-android-diagnostic-tool` | 见下 |

**最后两个连在一起，值得单独说。** 本地副本 `README.md:96` 写着信号名的出处来自 `mikegapinski/tesla-can-explorer`。我查了这个账号：公开仓库还剩 8 个（编码器、Home Assistant 集成、AOSP 相关），**没有一个叫 tesla-can-explorer 或 tesla-android-diagnostic-tool**。

也就是说，本文所有"这条帧是什么信号"的判断所挂靠的那条外部链条，**源头仓库目前已经不在公开网络上了**。我没有删掉这个引用——`README.md:96` 确实这么写着，行号证据不受影响——但读者应该知道，顺着它点过去是 404。

GitHub 的 `404` 同时覆盖"删除"和"转私有"两种情况，我无法分辨是哪一种。这条同样是查询结果，不是推测。

### 名字没变，仓库变了：GitLab 那条链

这是本次清点里唯一一条我用接口**直接证实**、而不是转述别人的结论。

四个不同的旧路径，查出来是同一个项目：

| 我请求的路径 | 接口返回的 `path_with_namespace` |
| --- | --- |
| `Starmixcraft/tesla-fsd-can-mod` | `ev-open-can-tools/ev-open-can-mod` |
| `Tesla-OPEN-CAN-MOD/tesla-open-can-mod` | `ev-open-can-tools/ev-open-can-mod` |
| `ev-open-can-tools/tesla-open-can-mod` | `ev-open-can-tools/ev-open-can-mod` |
| `Tesla-OPEN-CAN-MOD/tesla-fsd-can-mod` | `ev-open-can-tools/ev-open-can-mod` |

GitLab 的路径重定向把整条改名链串起来了：最初叫 `Starmixcraft/tesla-fsd-can-mod`，中途改名 `Tesla-OPEN-CAN-MOD/tesla-open-can-mod`，最后变成 `ev-open-can-tools/ev-open-can-mod`。再查组织 `ev-open-can-tools` 下的项目列表，返回一条：

```
ev-open-can-tools/ev-open-can-mod | stars=163 | last_activity=2026-04-25 | archived=true
```

结论是：**它没有被删除，它是被改名两次之后归档了。** `archived=true` 意味着 GitLab 上仍能完整克隆、仍保留 163 颗星与全部历史，只是不再接受新的 push。

这跟坊间"原版被 DMCA 下架"的说法不完全是一回事。我只能说接口显示的是什么——`archived` 是仓库主自己点的开关，跟平台强制删除是两个不同的字段。下架原因、谁点的归档按钮，接口不告诉我，我也不打算替它编一个。

同一时期确实有过真的 404（上面那张表），GitLab 上 `slxslx/tesla-open-can-mod-slx-repo` 也还在（2026-04-04 建，2026-04-12 最后活动，12★ / 21 fork），但**"原版已经消失"这个印象，至少对 GitLab 那个仓库是不准确的。**

### "现在还能不能成功"

这是所有同类仓库的 issue 区吵得最凶的问题。我把能拿到的一手文本按时间排了一下，只报社区说过什么：

- `README.md:50`（本地副本，行号可复现）在讨论 `2026.2.9.X` 与 `2026.8.X` 两个分支的 FSD v13/v14 差异，要求读者按软件版本选编译宏。
- `hypery11/flipper-tesla-fsd` 的 tracker issue 里，有人给出了分版本的结论表：FSD 解锁在 2026.14.x 及之后属于**未解决**，nag 相关功能在部分测试者机器上可用，TLSSC、BMS、诊断这类不碰 AP 帧的功能不受影响。同一批 issue 里也有反向回报——某个版本上"仍然正常"。两边都是单点回报，样本量不明。
- 还有 issue 记录到 2026.14.x 新增了一层 preflight 检查，以及一条把发送行为与"是否监听到特定帧"挂钩的观测。这些是一线用户在自己车上的记录，没有第三方仲裁。

以上全部是社区回报，**我一条都没有独立验证。** 本文第 17 节的立场不变：兼容性状态未核实。

顺带交代一类不进表的东西：Enhance Auto S3XY Commander、Ingenext 这类商业方案是闭源的，不在 git 清点范围内；`commaai/opendbc`（3451★，2026-09-29 仍在更新）是通用信号数据库，不是这类固件，但它是很多项目信号定义的上游。这三样我都只提一句，不展开。

---

## 14. 逐项对照：它们彼此差在哪

清点是名单，这一节是对照。同一条总线、同一个目标，六条维度上它们走得相当不一样。**差异比相似更能说明这类项目在往哪个方向分化。**

先说一句证据强度：本节第 1–5 小节依据的是各仓库 README、目录结构与托管平台 API 的公开文本，按 URL 与检索日期（2026-09-30）记录，**我没有把它们 clone 下来做 `file:line` 核验**；只有第 6 小节——文档与代码的落差——是我自己 grep 过的，行号对本地副本成立。

### 一、接在哪：硬件与 CAN 控制器

| 项目 | 主控 | CAN 怎么来 | 可选板 |
| --- | --- | --- | --- |
| `tesla-open-can-mod`（本文副本） | RP2040 / ATSAME51 / ESP32 | MCP2515 走 SPI、原生 MCAN、原生 TWAI 三条驱动 | 4 个 PlatformIO env |
| `flipper-tesla-fsd` | Flipper Zero / ESP32 | Flipper 上是 MCP2515；ESP32 走 TWAI 或外挂 MCP2515 | `m5stack-atom`、`esp32-lilygo`、`waveshare-s3-can`、`esp32-mcp2515` |
| `ev-open-can-tools` | RP2040 / ATSAME51 / ESP32 | 同上三条，另加 Adafruit ESP32 Feather V2 + CAN FeatherWing | 5 块板，README 全标 Tested |
| `herrfrei/tesla-fsd-canbus-esp32` | ESP32-S2 / S3 / C3 / PICO | 只走 MCP2515 | 引脚按芯片在编译期自动选 |
| `tuncasoftbildik/tesla-can-mod` | ESP32-C6 | TWAI | 单板：Waveshare ESP32-C6-LCD-1.47 |
| `babico/TeslaCANModder` | ESP32-S DevKit | MCP2515 | 浏览器一键烧录 |
| `dzid26/ESP32-DualCAN` | ESP32 | **双路 CAN** | 连板子设计图一起开源（CERN-OHL-W-2.0） |

第一处真差异在这张表的最后一列：**本文副本把板卡支持做成了抽象接口的四个实现**（第 9 节），代价是每块板都要一个 env；**Flipper 版和 `dzid26` 走的是双路 CAN**——一路读驾驶辅助状态、一路注入。这个硬件差别是后面几节反复出现的分水岭：单路意味着读和写共用一条线，能读到什么、能写什么，被同一条布线同时限制住。

### 二、怎么选车型：编译期、菜单、还是网页

这是最核心的一处分歧，因为它决定了"换台车/换个版本"要付出什么代价。

| 项目 | 选型方式 | 换车要做什么 |
| --- | --- | --- |
| `tesla-open-can-mod` | **纯编译期**。`RP2040CAN.ino:24-26` 三选一，或 PlatformIO `build_flags` 加 `-D` | 改宏、重新编译、重新烧录 |
| `flipper-tesla-fsd` | **纯运行时**。设置菜单里 Force FSD / Force HW3 Mode / Auto Detect 等 | 车机菜单里点一下 |
| `ev-open-can-tools` | **两段式**。`sketch_config.h` 编译期定变体，Web 界面运行时开关功能 | 变体重编，功能网页开关 |
| `tuncasoftbildik/tesla-can-mod` | 编译期 `-D HW4`，功能开关走 WiFi 面板 | 变体重编，功能面板开关 |
| `herrfrei` / CanFeather 一族 | `#define HW` 写在 `.ino` 顶部 | 改宏重烧 |

本文副本在这一栏选了最省运行时开销的一种，也选了最不方便的一种：**没有串口命令、没有按键、没有网页，改任何一个开关都等于重烧一遍固件。** 第 15 节会看到，这个选择同时意味着它把所有安全约束也压在了编译期。

### 三、功能范围：谁有谁没有

下表是各仓库 README 的**自述**，不是我的测试结果：

| 能力 | 本文副本 | Flipper 版 | ev-open |
| --- | --- | --- | --- |
| FSD 使能位改写 | ✅ `handlers.h` | ✅ | ✅（走插件） |
| 拖杆速度档映射 | ✅ `can_helpers.h` | ✅ | ✅ |
| 驾驶员注意力提示抑制 | ❌ | ✅（README 列为核心卖点） | 未在 README 主表列出 |
| 车身/舒适类注入 | ❌ | ✅（30+ handler） | 内置 handler 只观测 |
| BMS / 仪表读取 | 串口打印 | ✅ 实时面板 | ✅ |
| Web 界面 / OTA 升级 | ❌ | ✅（ESP32 版） | ✅（分区表里直接放了四份 OTA 分区） |
| 运行时开关 | ❌ | ✅ | ✅ |
| 只听模式 | ❌ | ✅（首启默认） | README 称有运行时发送门控 |
| 单元测试 | ✅ 5 组 83 断言 | 有 `test/` 目录 | `pio test` 三套 env + CI |
| 插件机制 | ❌ | ❌ | ✅ 独立 plugins 仓库 |

这张表最刺眼的一列是第一列：**本文副本在功能面上是最窄的。** 它只做 FSD 使能位与速度档这两件事，其余一律没有。窄有窄的好处——第 15 节会看到它的门控结构因此特别容易读完；但如果读者期待的是"一个全能工具"，这份清单会让他失望，而另外两个仓库卖的正是这个。

### 四、代码组织与构建系统

| 项目 | 入口 | 构建 | 测试 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | 双入口：`src/main.cpp` 与 `RP2040CAN.ino` | PlatformIO + Arduino IDE 双通道 | `test/` 下 5 个 native 套件 |
| `flipper-tesla-fsd` | `application.fam` + `tesla_fsd_app.c` | `ufbt`（Flipper），另起 `esp32/` 一棵 PlatformIO 树 | `test/`、`fsd_logic/` 单独抽出 |
| `ev-open-can-tools` | ESP-IDF 风格：`CMakeLists.txt`、`sdkconfig.defaults`、三份分区表 | CMake + PlatformIO 并存，另有 `legacy-arduino/` 兜老用户 | `pio test` 三个 env + GitLab CI |
| `babico/TeslaCANModder` | JS monorepo：`client/`、`firmware/`、`packages/` | npm + docker-compose + 浏览器烧录 | jest + eslint + prettier |
| `tuncasoftbildik/tesla-can-mod` | 单 `src/main.cpp` | PlatformIO | 无独立 test 目录，附 `tools/teslacan_client.py` |

`ev-open-can-tools` 的目录结构说明它已经不是"一个固件"了：OTA 分区表、`onboarding/`、插件仓、CI 三层验证——这是平台化的形状。`babico` 那个更极端，整个是 Web 工程的做法，`.opencode/`、`AGENTS.md`、`opencode.json` 都在仓库里。

相对地，本文副本的结构停在"一个固件工程"的形状：七个有信息量的文件（第 2 节），一棵 include 树，没有插件、没有 OTA、没有 Web。

### 五、许可证：有、没有、和"没有"意味着什么

| 仓库 | GitHub API 返回的 license 字段 |
| --- | --- |
| `1-v-1/tesla-open-can-mod` | GPL-3.0 |
| `ev-open-can-tools/ev-open-can-tools` | GPL-3.0 |
| `tuncasoftbildik/tesla-can-mod` | MIT |
| `babico/TeslaCANModder` | WTFPL |
| `dzid26/ESP32-DualCAN` | CERN-OHL-W-2.0（硬件） |
| `hypery11/flipper-tesla-fsd` | NOASSERTION |
| `herrfrei`、`jvanakker`、`Xingheee`、`davidgrylls825`、`Karolynaz`、`qmwdy` 等一批镜像 | `null` |

`null` 就是**没有许可证**。没有许可证不等于"随便用"，法律上默认是保留全部权利——这跟 GPL-3.0 的"可以商用、可以改、但要开源"是两回事。所以"fork 一个镜像下来自己改"这个动作，在这一栏里比看上去危险。

这一栏还有个反直觉的地方：**星最多的那个（`hypery11`，1094★）返回的是 NOASSERTION**，也就是 GitHub 没能识别它的 LICENSE 文件；而本文副本这个几乎没人用的（27★），许可证字段干干净净是 GPL-3.0。star 数和许可证清晰度之间没有关系。

### 六、文档与代码的落差（本仓库）

前面五条都是横向的，这一条回到纵向：**本文副本自己的文档，有多少条能对上代码。** 三处对不上，全部用 grep 双向验证过。

#### 裂缝一：M4 指南里的宏在源码里不存在

`guides/INSTALLATION_GUIDE_M4_CAN.md:29` 写着：

```cpp
#define HW_TARGET TARGET_HW3  // Change to TARGET_LEGACY, TARGET_HW3, or TARGET_HW4
```

我在整个仓库 grep `HW_TARGET|TARGET_HW3`——**只有这一处命中**，源码里没有任何代码读它。

真正生效的机制是 `RP2040CAN.ino:24-26` 的车型宏（当前 24 行 `#define LEGACY` 生效，25、26 行的 `//#define HW3`、`//#define HW4` 被注释掉），以及 `app.h:13-21` 的 `#if defined(HW3)` 这类条件编译。

**照 M4 指南逐字执行，会定义一个没人读的宏，构建照样撞上 `app.h:20` 的 `#error`。** 指南开头的步骤 5 因此是失效的——这份指南的其余部分（装库、选板、接线、验证）都对，只有选型这一行指向了不存在的 API。

#### 裂缝二：PlatformIO 路径缺一个车型定义

`app.h:20` 的错误信息说得很明确：

```cpp
#error "Define HW4, HW3 or LEGACY in build_flags"
```

但 `platformio.ini` 的五个环境里，`build_flags` **只有驱动宏，没有任何一个带 `-DHW3`/`-DHW4`/`-DLEGACY`**。而 `src/main.cpp` 全文 45 行也没有 `#define HW3` 这类定义——grep 证实 `#define LEGACY` 只出现在 `RP2040CAN.ino` 和 README 里。

所以我**静态推断**：干净 clone 后直接 `pio run -e feather_rp2040_can` 会走到 `app.h:20` 的 `#error`。写这一段的时候本机还没装 PlatformIO，结论来自"三处定义各缺一环"这个事实链，而非一次真实编译输出——**第 16 节把这次实跑补上了，并把结论拆成了两种情况。**

README `:215-217` 的措辞是"editing the define near the top of `src/main.cpp`"——**用定冠词暗示那行已经存在，实际上不存在，得自己加。** 错误信息让你往 `build_flags` 加，README 让你往 `src/main.cpp` 加，两个地方说法还不同。

**补记（2026-09-30）：上游已经改口了，而且我 clone 下来逐行对过。** 当前 GitHub 上的 README 写的是 PlatformIO reads the active vehicle and optional feature defines from `RP2040CAN.ino`。我核了上游三处：`src/main.cpp:24` 的驱动 `#error` 还在（与 `:8` `:16` `:24` 三个 env 的驱动宏对得上）、`include/app.h:24` 的车型 `#error` 也还在（本地副本是 `app.h:20`，行号漂了 4 行）、`platformio.ini` 的 `build_flags` **依然一个车型宏都没有**。

换句话说：上游自己并没有删掉那条 `#error`，**堵住这个洞的是 `scripts/platformio_sync_ino_defines.py`**——车型宏在构建时被它临时注入，`platformio.ini` 里始终是空的。所以裂缝二对本地副本成立，对上游"如果缺了这个脚本"同样成立；上游真正多出来的是那个脚本本身。**实测输出见第 16 节。**

#### 裂缝三：X179 的位置，两份指南互相矛盾

这一处最"物理"——照错了连地方都找不到。

`guides/INSTALLATION_GUIDE_M4_CAN.md:57`：

> The Enhance Auto Gen 2 Cable plugs into the **X179 connector**, located behind the driver's side trunk panel.

`guides/WIRING_GUIDE.md:16`：

> The X179 connector is located on the **passenger side footwell**, behind the panel on the right.

一个说**驾驶侧后备箱饰板后**，一个说**副驾脚部空间右侧饰板后**——方向完全相反。我全仓库 grep `footwell|trunk panel|located`，只有这两处命中；`README:260` 只给了 service.tesla.com 的文档链接，没给位置，**没有第三份口径可以仲裁**。

而两份指南自称的车型还是一致的：`INSTALLATION_GUIDE:3` 写 "2023 Tesla Model 3 with HW3"，`WIRING_GUIDE:5` 写 "Photos were taken on a 2023 Model 3 (non-Highland)"。同一台车，两个位置。

**这处的性质与前两处不同。** 前两处是"文档指向不存在的 API"，读者会在编译期撞墙、当场发现；这一处是"文档指向错误的物理位置"，读者会拆错饰板浪费时间，**而编译器和 grep 都不会替你拦住它**——它是三处里唯一需要靠人对账的一处。

两份指南都附了 Enhance Auto 的实拍视频（`INSTALLATION_GUIDE:63`、`WIRING_GUIDE:23`），实车动手前以视频为准。

这三处裂缝合起来说明两件事。**其一，前两处同源**：`RP2040CAN.ino` 路径（Arduino IDE）是被完整走通过的，PlatformIO 路径的文档滞后于代码。其二，第三处暴露的是另一个问题——两份接线指南是各写各的，没人对过位置。对一个靠社区逐版本回报维护的项目，这类漂移是常态而非例外——但它确实会卡住第一个照着做的读者。

### 小结：分化发生在哪几个方向

把六条维度摞在一起看，这批仓库的分化很清楚。硬件上，双路 CAN 是分水岭——它决定你能不能一边读状态一边注入。选型方式上，一边往编译期压（省运行时、换车要重烧），一边往运行时菜单放（换车点一下、门控可以做得更细）。功能面上，本文副本主动选了最窄的一条，另外两个往"工具箱"方向长。工程形态上，`ev-open` 已经平台化、`babico` 已经 Web 化，本文副本还停在单固件。

没有哪一条是明显错的，但每一条都要付代价。而代价在哪一天显现，取决于车端固件怎么变——那是第 17 节的事。

---

## 15. 门控清单：有什么，没什么

把仓库里所有"防止乱发帧"的机制列一遍，有五条：

| 门控 | 位置 | 性质 |
| --- | --- | --- |
| 编译期选型失败即中止 | `app.h:20` `#error` | 配错无法编译 |
| 硬件过滤器 | `app.h:42` | 无关帧不进 CPU |
| UI 勾选位作为开关 | `handlers.h:86`、`:45`、`:151` | 仅控制 **mux 0** 分支 |
| HW3 的 mux 2 受缓存约束 | `handlers.h:104` | HW4 的 mux 2 不受（`:165`） |
| 读改写掩码 | `can_helpers.h:14` | 不误伤相邻字段 |
| ISA 能力默认关闭 | `handlers.h:14` | 编译期常量，显式启用 |

同时，**我 grep 确认以下机制在这个仓库里完全不存在**：

- 没有滚动计数器（`grep rolling|alive|counter` 无源码命中）
- 没有统一的发送许可函数（无 `canSend` / `transmitAllowed` / `fsd_can_transmit`）
- 没有硬件只听模式（无 `ListenOnly`）
- 没有 OTA 进行中检测
- 没有 DBC 文件，也没有任何代码读取 DBC

这是一组关键的对照，而且不是我拍脑袋列的：同门另外两个变体各自带一道这个仓库没有的闸——

- **Flipper 版**（`hypery11/flipper-tesla-fsd`）把安全默认写进了设置项本身：`Mode` 分 `Active` / `Listen-Only` / `Service` 三档，而 **Listen-Only 是首启默认值**——MCP2515 进硬件只听模式，物理上发不出去，得用户手动切到 Active 才开始干活。它另有一条 OTA 门控设置，用来处理车机上报"OTA 正在进行"时的发送许可。
- **ev-open**（`ev-open-can-tools/ev-open-can-tools`）把这件事写进了 README 原文：固件"**transmit only when the configured runtime gates permit it**"；内置 handler 只做观测，注入要靠启用插件才走——**观测与注入是两条路**。

这两条出自公开 README 与 SECURITY 文本，按 URL 与页面日期记录（ev-open 组织建于 2026-04-08，Flipper 版中文 README 页面日期 2026-09-25），**我没有为它们重做 `file:line` 核验**——本地副本只有 `tesla-open-can-mod`，本文的行号纪律只对它成立。

对照之下，这个仓库的选择很清楚：**把安全约束放在编译期与默认值上，而不是放在运行时。**

两种取舍都有道理。编译期门控的好处是零运行时开销、配错根本编译不过；坏处是**运行时没有任何东西能拦住一次"编译配置正确但时机不对"的发送**。如果你关心的是后者，这个仓库提供的保护比另外两个少。

顺带一提，第 5 节那个细节在这里有了新含义：**mux 1 分支不看 `FSDEnabled` 缓存，三个 handler 都是。** 这意味着那一支的发送条件只有"收到 mux 1 帧"这一条。是不是作者有意为之，源码没写，测试倒是断言了这个行为（`test_hw3_handler.cpp:126-131`）。我把它记下来，不替作者解释。

---

## 16. 我真的跑了：构建与测试执行记录

开头那张验证表里有一行原本写着"未执行，本机没有 PlatformIO"。这一节把它补上——**全部命令与输出都产生于 2026-09-30，Windows 11，PlatformIO Core 6.2.0，Python 3.12.10，MinGW-w64 GCC 16.2.0。** 能复现，不能复现的部分我标出来。

### 一、两份代码，两套测试

同一条命令，对两份代码各跑一次：

```bash
pio test -e native          # 本地副本 E:\tesla-open-can-mod-main
pio test -e native -e native_force_fsd -e native_log_buffer   # 上游 clone
```

| 对象 | 套件数 | 结果 |
| --- | --- | --- |
| 本地副本（`E:\tesla-open-can-mod-main`） | 5 | **83 test cases: 83 succeeded** |
| 上游 `1-v-1/tesla-open-can-mod` @ `815e000` | 8 次套件运行（3 个 env） | **107 test cases: 107 succeeded** |

本地副本那 83 个，和我之前在第 11 节**逐个 `RUN_TEST` 数出来的**数字完全一致——那是一个纯静态计数，现在被一次真实执行印证了。

多出来的 24 个来自上游新增的两个套件：`test_native_force_fsd`（配 `native_force_fsd` env，`-DFORCE_FSD`）和 `test_native_log_buffer`。本地副本连 `include/log_buffer.h` 这个文件都没有。

**两套全绿，这个仓库的测试没有一个是摆设。** 后来我把同一条命令推到同类仓库，结果分三档：

| 仓库 | 测试套件 | 用例 | 结果 |
| --- | --- | --- | --- |
| `JordanzhaoD/waveshare-single-can-firmware` | 19（PlatformIO native） | **650** | **650/650 全过** |
| `hypery11/flipper-tesla-fsd` | 2（`test/Makefile`，gcc/g++ 直调） | **827** | **827/827 全过** |
| `ev-open-can-tools/ev-open-can-tools` | 9（PlatformIO native） | 237 | **235 过、2 个套件编译失败** |
| `1-v-1/tesla-open-can-mod` | 3（PlatformIO native） | 107 | 107/107 |
| 本地副本 | 5（PlatformIO native） | 83 | 83/83 |

`hypery11` 那一行**不是 PlatformIO native**，要单独说：它把测试放在 `test/` 下，用 `test/Makefile` 直接调编译器，CI 里对应 `Host unit tests (protocol core)` 这个 job。我照 `Makefile` 抄出两条命令手工跑的——本机 WinLibs 的 MinGW 有 `gcc`/`g++` 但**没有 `make`**：

> **flipper 这一行的数字在上游 HEAD 复核过。** 我第一遍跑的是 `19ef738`（`v2.16-beta.29`），得 695；换到 `6a3404f` 重跑得 **827**，本表与第 19、23、25 节一律以 HEAD 为准。同一棵树的 10 个板级 env 也重新编了一遍，**10/10**。

```bash
# 与 test/Makefile 逐字一致（CFLAGS = -std=c11 -Wall -Wextra -O0 -g）
gcc -std=c11 -Wall -Wextra -O0 -g -I../fsd_logic \
    test_fsd_core.c ../fsd_logic/fsd_handler.c ../fsd_logic/fsd_profile.c \
    -o test_fsd_core -lm                    # → 648 passed, 0 failed
g++ -std=c++17 -Wall -Wextra -O0 -g -I../esp32/.firmware -I../fsd_logic \
    test_esp32_core.cpp ../esp32/.firmware/fsd_handler.cpp \
    -o test_esp32_core                      # → 179 passed, 0 failed
```

**后一条的意义不一样**：它把 `esp32/.firmware/fsd_handler.cpp` **原样编进测试**——也就是第 23 节要烧进板子的那份 handler，不是抽出来的副本。所以"宿主测过"和"固件编过"在 flipper 这里指向同一份源文件。两条合计 **827 passed, 0 failed，`-Wall -Wextra` 零警告**。

我第一次照抄 Makefile 时把 `-I../fsd_logic` 漏了，编译当场 `fatal error: fsd_can_ops.h: No such file or directory`——**上表里"695 → 827"这个变化也是这么发现的**：我在上游 HEAD 重跑，想沿用旧命令，结果数字对不上，才回头去看 Makefile。两次都以 Makefile 原文为准。

我先前把这一格填成"`ufbt` 未装所以没测"，是拿 Flipper 主机那一半去否定 `esp32/` 这一半——**两个是分开编译的，这个推断不成立**。

`ev-open` 那两个失败是真编译错误，不是断言失败：

```
include/plugin_engine.h:747:5: error: 'strlcpy' was not declared in this scope; did you mean 'strncpy'?
*** [.pio\build\native_plugin_engine\...\test_plugin_engine.o] Error 1
-- native_plugin_engine:test_native_plugin_engine [ERRORED] --
```

`strlcpy` 是 BSD/newlib 函数，ESP-IDF 里有，本机的 MinGW g++ 没有。Linux 上 glibc 2.38 之后也有，所以这**大概率是平台相关**——但在我这台机器上，它的 9 个 native 套件只能过 7 个。

### 二、四块板的固件，一个一个编出来

```bash
pio run -e esp32_twai
pio run -e m5stack-atomic-can-base
pio run -e feather_m4_can
pio run -e feather_rp2040_can
```

| env | 结果 | RAM / Flash | 备注 |
| --- | --- | --- | --- |
| `esp32_twai` | SUCCESS | 14.6% / 61.7% | 生成 `firmware.bin` |
| `m5stack-atomic-can-base` | SUCCESS | 14.6% / 61.7% | `extends` 自上一个 env |
| `feather_m4_can` | SUCCESS | 3.7% / 6.0% | 需 `.ino` 改 `DRIVER_SAME51` |
| `feather_rp2040_can` | SUCCESS | 5.1% / 0.5% | 需改 `lib_deps` 包名 |

四块板的固件镜像全部产出。**这是我能给出的最强的一条"它能编译通过"的证据**——不是读 README 说的，是链接器和 esptool 说的。

后来我有了明确的硬件目标（手上一块 ESP32-S3，还没有 CAN 收发器），于是把矩阵横向推到同类仓库，专门找 S3 目标：

| 仓库 | env | `board` | 声明 flash | TX/RX | 结果 |
| --- | --- | --- | --- | --- | --- |
| `JordanzhaoD` | `waveshare_single_can_standalone` | `esp32s3box` | **16MB** | 15 / 16 | SUCCESS，RAM 15.3% / Flash 28.8% |
| `hypery11` | `waveshare-s3-can` | `esp32-s3-devkitc-1` | 8MB | 15 / 16 | SUCCESS，RAM 37.4% / Flash 28.0% |
| `ev-open` | `waveshare_ESP32_S3_RS485_CAN` | `esp32s3box` | 4MB 分区 | 15 / 16 | SUCCESS，RAM 21.9% / Flash 70.8% |
| `ev-open` | `esp32_ext_mcp2515` | `esp32-s3-devkitc-1` | 8MB 分区 | SPI 外接 | SUCCESS，RAM 22.0% / Flash 35.9% |
| `ev-open` | `esp32_twai` | `esp32dev` | — | — | SUCCESS，RAM 21.5% / Flash 71.3% |
| `hypery11` | 其余 9 个 env | `esp32dev` / `m5stack-atom` / `lilygo-t2can` / … | — | — | **9/9 全部 SUCCESS** |

**ESP32-S3 的四个目标，四个全过。** 而且 `TX=GPIO15`、`RX=GPIO16` 这组引脚是三个仓库各自独立给出的，交叉印证。

这一轮还撞出四条新报错，全部留了原文：

| 报错 | 出处 | 处理 |
| --- | --- | --- |
| `Missing platformio_profile.h` | `ev-open`、`JordanzhaoD` 共用同一套 onboarding | `copy platformio_profile.example.h platformio_profile.h` |
| `platformio_profile.h must enable exactly one driver define: … DRIVER_T2CAN_DUAL` | `JordanzhaoD`，示例默认解的是双 CAN 变体 | 单 CAN 的 env 要改成**只解 `DRIVER_TWAI`** |
| `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa6` | `ev-open` `scripts/minify_dashboard.py` 用系统默认编码 | `set PYTHONUTF8=1` |
| `ModuleNotFoundError: No module named 'csscompressor'` / `'rjsmin'` | `JordanzhaoD` 的网页压缩脚本没声明依赖 | `pip install csscompressor jsmin rjsmin` |

第三条是**只有在中文 Windows 上才会出现**的故障——脚本直接 `open()` 不带 `encoding=`，本机默认是 GBK。这类问题 README 里不可能写，只能撞一次记一次。

### 三、裂缝二的实测裁定

第 14 节裂缝二原本的写法是："我**静态推断**会撞 `app.h:20` 的 `#error`，我没有实际运行。"现在有实际运行了，而且结论比我原来写的更细——**分两种情况：**

**情况一：原样 clone，直接 `pio run -e esp32_twai`。失败。** 但失败点**不在** `app.h:20`：

```
*** RP2040CAN.ino must enable exactly one driver define: DRIVER_MCP2515, DRIVER_SAME51, DRIVER_TWAI.
File "...\scripts\platformio_sync_ino_defines.py", line 29, in _pick_one
========================= [FAILED] Took 113.98 seconds =========================
```

**情况二：按 ③ 解开两行后，同一命令。成功**，并且脚本打印：

```
Synced RP2040CAN.ino defines for esp32_twai: HW4
```

把这两条放在一起，裂缝二的准确表述应该是：

> **本地副本**（缺 `platformio_sync_ino_defines.py`）：车型宏无处可来，`platformio.ini` 也没带 → 撞 `app.h:20` 的 `#error`。我用本机 `g++ -std=c++17 -DNATIVE_BUILD -Iinclude -fsyntax-only` 直接触发过这条错误，输出是 `include/app.h:20:2: error: #error "Define HW4, HW3 or LEGACY in build_flags"`；换成 `-DHW3` 后这条错误消失。**结论成立。**
>
> **上游**（有脚本）：车型宏从 `RP2040CAN.ino` 被脚本注入编译命令。**上游并没有删掉那条 `#error`**——它还在，只是行号漂到了 `include/app.h:24`（本地副本是 `app.h:20`），而且 `platformio.ini` 的 `build_flags` 至今一个车型宏都没带。也就是说，**堵洞的是脚本，不是源码**。有了脚本，那条 `#error` 就走不到，于是"得自己往 `build_flags` 加 `-DHW3`"这条指引在上游作废；取而代之的是两条新约束：`.ino` 里驱动与车型宏各只能解一个、且驱动必须与 `-e` 匹配。

所以裂缝二**对本地副本成立；对上游，只要 `scripts/platformio_sync_ino_defines.py` 还在原位，就不成立。** 我原本那句"我不能担保上游是否也这样"，现在可以换成确定的答案了——连带一个推论：**把 `platformio.ini` 里那行 `extra_scripts = pre:scripts/platformio_sync_ino_defines.py` 去掉，或者换一个不读 `.ino` 的构建入口，洞会原样露出来。** 它在源码层面从来没有被填过，被填的是"构建流程"这一层。这也解释了为什么本地副本会中招——它整份拷贝里就没有这个脚本。

### 四、`1-v-1` 的另外两条报错原文

```
# 驱动宏与 env 不匹配（这不是 bug，是脚本在拦）
*** RP2040CAN.ino selects DRIVER_TWAI, but PlatformIO env 'feather_m4_can'
    is configured for DRIVER_SAME51. Pick the matching 'pio run -e ...'
    environment or update RP2040CAN.ino.
File "...\scripts\platformio_sync_ino_defines.py", line 86, in <module>

# 库包名失效
UnknownPackageError: Could not find the package with 'autowp/MCP2515' requirements
```

第二条我追到了 registry API：

```
GET https://api.registry.platformio.org/v3/packages/autowp/library/MCP2515   → 404 NotFound
GET https://api.registry.platformio.org/v3/search?query=autowp               → autowp/autowp-mcp2515  v1.3.1
```

`platformio.ini:7` 写的 `autowp/MCP2515` 已经是个死包名。**这是本文发现的第四处"文档/配置与现实对不上"**，性质与裂缝一同类：不是你操作错了，是仓库自己失修了。改成 `autowp/autowp-mcp2515` 后 `feather_rp2040_can` 立刻通过。

（另注：交叉编译工具链最初从 GitHub Releases 下载时报 `Got the unrecognized status code '403'`，给 `git` 与构建过程配了本地代理后恢复正常。这是我的网络环境问题，不是仓库的问题，记在这里免得别人误判。）

### 五、这些结果没有改变什么

必须把话说清楚，**编译通过不等于能用**：

- 编译通过只证明**语法、模板、链接关系**成立，不证明任何 CAN 帧语义正确。
- 107 个测试断言的是**开发者自己写的预期**，包括那些被第 7 节那个回归测试锁死的行为——它们能证明"代码符合作者意图"，不能证明"作者的意图符合车端实际"。
- **烧录、接线、上电，我一次都没做。** `--target upload` 我一条都没执行过，因为我没有板子。
- 因此本文所有关于"车会怎么反应"的句子，性质仍然是社区回报，**第 17 节的结论一个字都不用改。**

---

## 17. 兼容性：一个诚实的未知

你在别处可能看到"这个漏洞已被最新 OTA 修复"的说法。**我没有核实过，本文也不这么写。**

原因很直接：

1. **我无法验证。** 没有车辆、没有当前固件版本、没有总线访问。任何"已修复"或"仍有效"的断言，我拿不出证据。
2. **仓库自己的证据指向"状态未定"。** `README.md:50` 还在讨论 `2026.2.9.X` 与 `2026.8.X` 两个分支的 FSD v13/v14 差异，并要求读者按软件版本选择编译配置。一个仍在维护兼容性说明的项目，状态是活跃的。
3. **写"已修复"会让免责声明变成假担保。** 读者信的是那句话本身，不是我的推理；万一它不成立，代价由读者承担。

下面是我为这句"未核实"做的功课，分三层。证据强度依次递减，我逐层标注。

### 一、同族项目互相打架

把几个同源仓库的公开说明横向对了一遍，结论不是谁对，是它们对不上：

| 来源 | 对 HW4 / 固件版本的口径 |
| --- | --- |
| 本地副本 `README.md:50` | `2026.2.9.X` 起是 FSD v14；`2026.8.X` 分支仍是 v13，跑 v13 就编 `HW3` |
| `herrfrei/tesla-fsd-canbus-esp32` | HW4 自 **2026.2.3** 起才是 FSDV14，更早的 HW4 车编 `HW3` |
| `juamiso/tesla-fsd-can-enabler` | 同一口径：firmware older than 2026.2.3 不走 FSDV14 |
| `jvanakker/tesla-fsd-can-mod`（镜像） | **2026.8.6 与 2026.2.9.x（及更高）报告已失效**，2026.8.3 大概率也在内 |
| `hypery11/flipper-tesla-fsd` 兼容表 | `2026.2.9.x` → Auto / Supported；`2026.8.6` → 强制走 HW3 |

最刺眼的是最后两行：同一个 `2026.2.9.x`，一边标"正常支持"，一边标"报告已失效"。阈值本身也有 `2026.2.3` 与 `2026.2.9` 两个版本号在流——未必矛盾，FSDV14 可能是分批推的；但对一个要照着选编译宏的读者，差六个版本号的分歧是实打实的。

这些文字按 URL 与页面日期记录，我没有做本地逐行核验。它们都是一线用户在自己那台车上的回报，没有第三方仲裁。

*证据强度：弱。单点回报，样本量不明。*

### 二、2026 年 4 月，一次公开的收网

| 日期 | 事件 |
| --- | --- |
| 2026-03-30 | `1-v-1/tesla-open-can-mod` 在 GitHub 建立 |
| 2026-03-31 约 21:00 | 一个中国区 fork 在 README 写下：中国国内的车辆会被远程下发配置从芯片底层（aka Gateway）禁用 FSD 相关功能，本项目已失效 |
| 2026-04-09 | Electrek、Teslarati、PiunikaWeb、Drive Tesla Canada 同日报道：特斯拉开始远程关闭装有第三方 CAN 模块车辆的 FSD |
| 2026-04-09 起 | `hypery11/flipper-tesla-fsd` issue #18 开始记录封禁在总线上的表现 |
| 2026-04-12 | 该仓库提交 upstream moved to GitHub ev-open-can-tools，把迁徙链写进 SECURITY.md |
| 2026-04-13 | 把 VIN 级封禁警示写进 README 与 SECURITY.md |
| 2026-04-16 | 加入 `0x7FF` 快照比对，后改名 GTW Config Replay |
| 2026-09-25 | 中文版 README 记录 2026.14.x 新增的 preflight 检查 |

车主收到的提示，多家媒体引的是同一句：

> Your vehicle has detected an unauthorized third-party device. As a precaution, some driver assistance functions have been disabled for safety reasons.

覆盖范围的报道口径是欧洲、韩国、中国、日本、土耳其、英国。"仅中国区超过 10 万台"这个数字被 Teslarati、autoevolution、Yahoo 等多家转引，源头是社区统计，我无法独立核对。韩国方面，多家媒体转述国土交通部按《汽车管理法》处理，最高两年监禁或 2000 万韩元罚款。

issue #18 里那段总线观测值得单独记一笔：被封车辆的 `0x3FD` mux0 bit38（"交通信号灯与停车标志控制"开关位）被清零，写回不生效。**封禁发生在网关那一侧，你的固件还在跑，只是没人听它的了。**

*证据强度：中。多源交叉，但关键数字仍是二手。*

### 三、本地副本已经不是上游了

这一层是我亲手比的，最强，也最能说明"行号会漂移"到底是什么意思。

2026-09-30 拉取的上游 README 是 **405 行**，本地副本是 **370 行**。差异不止一处：

| 项 | 本地副本 | 当前上游 |
| --- | --- | --- |
| 标题 | `CanFeather – Tesla FSD CAN Bus Enabler`（`README.md:3`） | `Tesla Open Can Mod` |
| FSD 订阅警告 | 无 | 顶部新增 Ban 警告块 |
| 板卡状态 | M4 与 ESP32 为 `Compiles, needs on-vehicle testing` | 四块全 `Tested` |
| PlatformIO 车型宏 | "editing the define near the top of `src/main.cpp`"（`README.md:215`） | "reads the active vehicle and optional feature defines from `RP2040CAN.ino`" |
| 可选宏 | 无 | 新增 `EMERGENCY_VEHICLE_DETECTION` |

**第四行直接影响第 14 节的裂缝二：上游 README 已经改口了。** 而且我后来真去 clone 了上游——结论写在第 16 节，比"不能担保"要确定得多。

我之所以把行号钉死在一份具体副本上，道理就在这里：钉死了才谈得上被推翻。钉不死的那类说法，我已经在开头的验证表里标成"未核实"了。

*证据强度：强。两份 README 直接比对，差异可复现。*

### 谱系

顺带交代血统。本地副本标题还叫 CanFeather，与仓库名对不上，是上游 GitLab 时代的残留。README 保留了最初的动机声明（`README.md:5`）：作者认为 500 € 的同类方案"massively overpriced"，板子成本约 20 €，算上工时的合理价格"no more than 50 €"。

信号名的出处也写在 README 里（`README.md:96`）：来自 `mikegapinski/tesla-can-explorer`。`UI_autopilotControl`、`DAS_status` 这些命名不是本仓库起的，是社区逆向成果的再利用。**本文所有"这条帧是什么"的判断，最终都挂在这条外部链条上**，我没有为它做过独立验证。

同一时期，GitLab 上的原版 `Starmixcraft/tesla-fsd-can-mod` 与其后继命名空间 `Tesla-OPEN-CAN-MOD` 相继下架。迁徙链在 2026-04-12 那次提交里写得很清楚：GitLab 后继 → `slxslx/tesla-open-can-mod-slx-repo`（归档中）→ `github.com/ev-open-can-tools/ev-open-can-tools`，并顺手去掉了仓库名里的特斯拉商标。下架原因没有公开，同类项目 SECURITY.md 的原话是不清楚具体触发原因，工作假设为"这类项目面临的可见法律压力正在变大"。`fsdcanmod.com` 自称是 pre-DMCA snapshot 的自动同步镜像——这个站点的存在本身，就是那条断链的证据。

### 结论仍是那句话

**截至本文写作，兼容性状态未核实，且随车辆软件版本持续变动。** 协议里没有版本协商层，布局随 OTA 漂移是这类项目的固有属性，不是做得不好——第 14 节那三处文档裂缝，就是同一种漂移在文档侧的表现。

要判断某个具体版本，只有两条路：看仓库 issue 与兼容性表里有没有该版本的回报，或者在能观测总线的环境里自己验。**相信任何一方的单方面断言都不够，包括我这份。**

---

## 18. 它在哪一层

前两节讲的是固件自身的结构，最后回到它在车里的位置——这也是"能不能破解 FSD"最关键的一问。

FSD 的感知与规划跑在域控制器内部：8 路相机输入经视频基础模型到占据特征与任务头，再到规划控制，v14 起叠加强化学习。这些计算发生在车载算力上，权重是编译进固件或者存在分区里的二进制，它从来不出现在 CAN 总线上。

总线跑的是另一类东西。500 kbit/s 的车身网络承载状态与意图：转向角、纵向加速度请求、档位、故障码，以及驾驶辅助系统自己写入的少量策略配置。摄像头画面、点云、神经网络中间层都不在这里。

那么这个固件改的是什么？读完源码可以说得更精确：它不产生任何新信号。全部工作就是收一帧、按位改几个比特、以同一 ID 发回去，第 5 节那三支 `handleMessage` 分支构成这个动作的全部。

能力上限因此被两件事锁死。一是被改那条帧原本承载什么语义，帧里没有的东西改不出来；二是接收方是否接受改动，校验、计数、时序任何一项不过，帧就被丢掉。

用模型层与总线层的分层框架说，它是在规划输出之后、执行之前插入一段改写，模型本身照常运行、照常输出，既不改占据网络，也不改端到端规划。

![三层定位：模型层、决策与执行层、总线层](images/can-mod-teardown-2026/s03-layer-positioning.svg)

图 3｜作用层定位。总线工具位于决策与执行之间，不触及模型层。

这也解释了两件方向相反的事。这类工具的实践成功率不低，因为它绕过的恰恰是感知层校验——改的不是传感器读数，而是系统内部已经算好的量。风险性质却因此和传感器攻击完全不同：它不欺骗模型，它截获模型的输出。

---

## 19. 全部仓库链接与逐个评估

第 13 节给的是数字，这一节给判断，最后把链接一次列全。**评估口径：clone 下来看目录、用 API 查元数据、能编的编一遍；三样都没做的我会写明。**

### 一、我 clone 并尝试构建的

全部 `git clone --depth 1`，时间 2026-09-30。

| 仓库 | 最后提交 | 构建系统 | 我的实测 | 一句话评估 |
| --- | --- | --- | --- | --- |
| [`1-v-1/tesla-open-can-mod`](https://github.com/1-v-1/tesla-open-can-mod) | 2026-04-02 | PlatformIO，7 env | **107/107 测试通过；4 块板固件全出** | 本文解剖对象的上游。**工程最干净、我验证得最彻底的一个**，但已冻结近半年、无运行时开关、RP2040 env 的库包名失修 |
| [`hypery11/flipper-tesla-fsd`](https://github.com/hypery11/flipper-tesla-fsd) | 2026-09-30 | `ufbt` + `esp32/` PlatformIO（10 env）+ `test/` Makefile | **板级 10/10 全过**（含 S3 `waveshare-s3-can`）+ **宿主 827/827**（648 条协议 + 179 条编译 `esp32/.firmware/fsd_handler.cpp`）；`ufbt` 那半未编（Flipper 本体，与 ESP32 无关） | **整个生态的重心**：1094★、**2026-09-30 当天仍在提交**（当天 HEAD 两次变动，写作中从 `19ef738` 一路走到 `6a3404f`）、中英双 README、Web Flasher 免工具链、运行时菜单免重编。**`changelog.md:215` 是全表唯一的 HW4 + 2026.2.11 实车正面数据**。欠着：许可证只有 929 B 的 GPL 声明（GitHub 给 NOASSERTION）、S3 env 按 8MB 分区（真板 16MB，浪费不致命）、三处兼容口径不一致 |
| [`ev-open-can-tools/ev-open-can-tools`](https://github.com/ev-open-can-tools/ev-open-can-tools) | 2026-08-05 | PlatformIO（21 env）+ CMake | **板级 3 个全成**（含 2 个 S3）；native **235/237**，2 套件编译失败 | **最像"平台"的一个**：OTA 分区表、Web、插件仓、CI 三套 native 验证、5 块板标 Tested、GPL-3.0。但本机有两处真故障：`plugin_engine.h:747` 的 `strlcpy` 编不过、`minify_dashboard.py` 在中文 Windows 上撞 GBK 编码 |
| [`ev-open-can-tools/ev-open-can-mod`](https://gitlab.com/ev-open-can-tools/ev-open-can-mod)（GitLab） | 2026-04-25 | — | — | **只有 2 个文件**，README 第一行 `🚨 PROJECT MOVED TO GITHUB 🚨`。是跳转存根，不是代码库 |
| [`JordanzhaoD/waveshare-single-can-firmware`](https://github.com/JordanzhaoD/waveshare-single-can-firmware) | 2026-09-22 | PlatformIO（1 env **S3** + 19 native） | **650/650 测试全过；S3 固件产出** | **测试拆得最细也最多的一个**（`native_nag`、`native_abort_guard`、`native_wheel_dnd` 各自独立），且 `waveshare_single_can_standalone` 是**专为微雪 ESP32-S3-RS485-CAN 写的 profile**，GPL-3.0 完整正文 35,819 B，HEAD `75ac7e7` 是一次精确回滚。**空缺：全仓没有一处 `2026.2.11`**，实车记录是 CN 2026.8.3.6 单车样本，`CHANGELOG.md:301`/`:316` 自述尚无道路闭环确认 |
| [`tuncasoftbildik/tesla-can-mod`](https://github.com/tuncasoftbildik/tesla-can-mod) | 2026-08-23 | PlatformIO，env `esp32c6` | 未编 | MIT、自带 LCD + WiFi 面板 + Flipper 伴侣 + Python 客户端，定位"独立优先"。功能面宽但没有独立 test 目录 |
| [`dzid26/ESP32-DualCAN`](https://github.com/dzid26/ESP32-DualCAN) | 2026-09-21 | Makefile + `firmware/` + `webui/` | 未编 | **唯一把板子设计也开源的**（CERN-OHL-W-2.0），含 `dbc/` 目录。297 个文件，硬件+固件+网页一体 |
| [`babico/TeslaCANModder`](https://github.com/babico/TeslaCANModder) | 2026-06-23 | npm monorepo + `firmware/` PlatformIO | 未编 | **Web 工程的做法**：jest/eslint/docker/浏览器烧录，WTFPL。20 个 open issue，`legacy/` 里挂着大量外部参考仓 |
| [`JelloEa/tesla-fsd-controller`](https://github.com/JelloEa/tesla-fsd-controller) | 2026-03-31 | PlatformIO，env `esp32` | 未编 | ESP32 WiFi 网页控制、README 提"支持中国模式"。36★ 但已停更 |
| [`herrfrei/tesla-fsd-canbus-esp32`](https://github.com/herrfrei/tesla-fsd-canbus-esp32) | 2026-03-29 | 纯 Arduino（`.ino`） | 未编 | **唯一给 ESP32-S2/S3/C3/PICO 做引脚自动选型的移植**，README 自称 unofficial port 并把原作者署名放最前。**没有 LICENSE 文件** |
| [`jvanakker/tesla-fsd-can-mod`](https://github.com/jvanakker/tesla-fsd-can-mod) | 2026-04-08 | 纯 Arduino | 未编 | 142★ 的原版镜像，README 顶部就挂着失效警告。**没有 LICENSE 文件** |
| [`iubns/tesla-fsd-can-mod`](https://github.com/iubns/tesla-fsd-can-mod) | 2026-03-30 | 纯 Arduino | 未编 | 16★，GPL-3.0，附韩文接线说明 |

### 二、只查了元数据、没有 clone 的

判断依据仅是 API 字段与 README 自述，**没编、没读代码**，评估力度天然更弱：

| 仓库 | ★ | 最后 push | 评估 |
| --- | --- | --- | --- |
| [`slxslx/tesla-open-can-mod-slx-repo`](https://gitlab.com/slxslx/tesla-open-can-mod-slx-repo)（GitLab） | 12 | 2026-04-12 | 迁徙链中间站，自称要改成通用 CAN 工具，再无下文 |
| [`lenfien/tesla-open-can-mod-release`](https://github.com/lenfien/tesla-open-can-mod-release) | 5 | 2026-04-17 | ESP32/S3 打包版，GPL-3.0 |
| [`J0811/flipper-tesla-fsd`](https://github.com/J0811/flipper-tesla-fsd) | 19 | 2026-04-07 | Flipper 版的早期分叉 |
| [`zilviaimbalanced664/flipper-tesla-fsd`](https://github.com/zilviaimbalanced664/flipper-tesla-fsd) | 9 | **2026-09-30** | **写作当天还在动的镜像**，防删备份性质 |
| [`GeAlan/tesla-fsd-controller-wjsall`](https://github.com/GeAlan/tesla-fsd-controller-wjsall) | 12 | 2026-04-20 | 与 JelloEa 同源的网页版 |
| [`superpositiontime/tesla-fsd-comma4`](https://github.com/superpositiontime/tesla-fsd-comma4) | 15 | 2026-03-29 | 走 comma 4 路线，另一条技术路线 |
| [`06066060606060/nag-killer`](https://github.com/06066060606060/nag-killer) / [`Summon-Unlock`](https://github.com/06066060606060/Summon-Unlock) | 12 / 12 | 2026-09-15 / 09-03 | 单一功能小工具，仍在更新 |
| [`ev-open-can-tools-plugins`](https://github.com/ev-open-can-tools/ev-open-can-tools-plugins) / [`-app`](https://github.com/ev-open-can-tools/ev-open-can-tools-app) | 27 / 1 | 2026-05-04 / 08-16 | 主仓的插件与 App 侧 |
| [`mert574/tesla-fsd-can-mod`](https://github.com/mert574/tesla-fsd-can-mod)、[`Karolynaz/waymo-fsd-can-mod`](https://github.com/Karolynaz/waymo-fsd-can-mod)、[`qmwdy`](https://github.com/qmwdy/tesla-fsd-can-mod)、[`davidgrylls825`](https://github.com/davidgrylls825/tesla-fsd-can-mod)、[`Xingheee`](https://github.com/Xingheee/tesla-fsd-can-mod)、[`dongho74s`](https://github.com/dongho74s/tesla-open-can-mod)、[`JelloEa/Tesla-Open-CAN-Mod`](https://github.com/JelloEa/Tesla-Open-CAN-Mod)、[`alanng2017/FFd`](https://github.com/alanng2017/FFd) | 0–10 | 2026-03~05 | **一批冻结的原版快照**，彼此 README 高度雷同，评估价值低 |
| [`tumik/S3XY-candump`](https://github.com/tumik/S3XY-candump) | 16 | 2025-04-17 | 商业件 S3XY Commander 的配套 Python 工具，比这件事整早一年 |
| [`commaai/opendbc`](https://github.com/commaai/opendbc) | 3451 | 2026-09-29 | 通用信号数据库，很多项目信号定义的上游，不是这类固件 |

**已经 404、只能从别人 README 里看到名字的**：`linesoft2/tesla-fsd-can-mod-fork`、`niccolodevries/tesla-fsd-can-enabler`、`mikegapinski/tesla-can-explorer`、`mikegapinski/tesla-android-diagnostic-tool`。最后一个尤其值得记——本地 `README.md:96` 把信号名的出处指向它，**而它现在点不开**。详见第 13 节。

### 三、我的推荐：HW4 + 2026.2.11

先交代硬件前提：我这轮实际接的场景是**手上有 ESP32-S3、还没有 CAN 收发器**。把能买到的板子和能编的固件对上之后，结论很具体。

#### 完整构建矩阵（全部实跑，2026-09-30）

| 仓库 | 板级固件 | native 单测 |
| --- | --- | --- |
| `1-v-1/tesla-open-can-mod` | **4/4**：`esp32_twai`、`m5stack-atomic-can-base`、`feather_m4_can`、`feather_rp2040_can` | 107/107（3 env） |
| `hypery11/flipper-tesla-fsd`（`esp32/`） | **10/10**，含 `waveshare-s3-can`（**S3**） | **827 passed / 0 failed**（Makefile 宿主测试，不是 PlatformIO native） |
| `ev-open-can-tools` | **3/10**：`esp32_twai`、`esp32_ext_mcp2515`（**S3**）、`waveshare_ESP32_S3_RS485_CAN`（**S3**） | **235 succeeded / 237**，2 个套件编译失败 |
| `JordanzhaoD/waveshare-single-can-firmware` | `waveshare_single_can_standalone`（**S3**） | **650/650**（19 env） |

**四个 S3 目标，四个全过**——各家的构建输出原样留在第 16 节。

#### 面向 ESP32-S3 的四个 env，谁对得上你要买的板

板子是**微雪 ESP32-S3-RS485-CAN，¥99.99**（规格见第 21 节）。四个 env 的编译数据在第 16 节那张表里，这里只留两条**对着要买的板**才有意义的差别：

1. **只有 `JordanzhaoD` 的 flash 声明和真板一致**——它按 `16MB` + `partitions_16mb_ota_4096k` 规划，另外两家一个按 `default_8MB.csv`、一个按 4MB 分区。三者镜像都能烧进去、都能跑，差别在**可用面积**：8MB 那份是**浪费 9.4MB**（`Flash: 28.0% (… from 3342336 bytes)` 报的 `0x330000` 是 app0 分区，不是整片，我初版据此说"硬伤"是读错了），4MB 那份则把可用面积砍到四分之一、OTA 槽最挤（Flash 已占 70.8%）。
2. `JordanzhaoD` 那个 env 的注释直接写着 `; Waveshare ESP32-S3-RS485-CAN standalone product profile.`——**它是专门为这块板写的**，不是碰巧能编。

#### 推荐：`hypery11/flipper-tesla-fsd` 的 `waveshare-s3-can` + 微雪 ESP32-S3-RS485-CAN

**这一段我改写过一次，初版把 `JordanzhaoD` 排在第一。** 初版把 flipper 压下去的三条——"宿主测试没跑"、"8MB flash 是硬伤"、"许可证 NOASSERTION"——**第一条是我查错了，后两条被后续实测降级**；初版还写 `650/650` 是"三个仓库里最多、比第二名多一倍"，flipper 补跑宿主测试后得 827，这句也就不成立了。过程留在下面和第 16 节，这里直接给改写后的结论。

1. **它是唯一给出 HW4 + 2026.2.11 实车正面数据的仓库。** `changelog.md:215`（v2.15 致谢）原文：`@Tikernel + @ViPiMP (positive compat data: Model Y Juniper HW4 2026.2.11 China, HW4 2026.8.3 Germany)`。我在 `JordanzhaoD` 全仓 grep `2026.2.11`，**一处都没有**；它的实车记录是 CN 2026.8.3.6 的单车样本，且 `CHANGELOG.md:301` 自述"实车自动偏移修复仍需发布后道路闭环确认"、`:316` 自述"尚未进行实车道路闭环验证"。
2. **微雪这块板是它 README 明列的支持目标**（`README.md:194`，build target `waveshare-s3-can`），不是碰巧能编。
3. **宿主测试 827 passed / 0 failed**（上游 `6a3404f` 实跑），其中 `test_esp32_core` 的 **179 条直接编译 `esp32/.firmware/fsd_handler.cpp`**——就是你要烧进板子的那份 handler。测试由 `test/Makefile` 用 gcc/g++ 跑（对应 CI 的 `Host unit tests (protocol core)`），不是 PlatformIO native env。我初版标"ufbt 未装所以没测"，是拿 Flipper 那半当理由否定 ESP32 这半，**不成立**。
4. **Web Flasher 一键烧录，零工具链**；首启 `Listen-Only`，物理上不能发帧，要在 dashboard 里开 Active。
5. **HW 检测有三信号 fallback**（`0x398` 不在被接总线上时退回 `0x3FD`/`0x399`/`0x3EE`，`README:51`），另有运行时 Auto Detect / Force HW4 / Force HW3 / Force Legacy，判错当场换、不用重烧。
6. **今天还在提交**（2026-09-30 当天，写作过程中 HEAD 就从 `19ef738` 一路走到 `6a3404f`，我最后核到 `6a3404f`），1094★，出问题最可能搜到答案。

**它欠着的四条，我不替它遮掩：**

| 问题 | 我的判断 |
| --- | --- |
| `waveshare-s3-can` 声明 8MB，真板 16MB | **我初版写成"硬伤"，说重了。** `default_8MB.csv` 的 app0 是 `0x330000`，`Flash: 28.0% (… from 3342336 bytes)` 报的是分区不是整片；烧到 16MB 板上能跑，**是浪费 9.4MB，不是不可用** |
| 三处兼容口径不一致 | `README:278` 写 HW4 `< 2026.2.9`、`esp32/README.md:403` 写 `≤ 2026.2.x` ✅、`:404` 写 `2026.2.9.x` HW4 broken、`changelog:215` 有正面数据。**README 那行是过时的**，没把 v2.15 拿到的数据更新进去；不一致的方向是**低估**不是高估 |
| ESP32 端口只实车验证过 HW3 | `esp32/README.md:11` 原文 `TESTED ON VEHICLE (Model 3 2022 HW3)`。`changelog:215` 那条 HW4 数据**没写明是 Flipper 还是 ESP32 端**，我不替它补 |
| `LICENSE` 只有 929 字节 | 是 GPL-3.0 的开头声明，所以 GitHub 给 `NOASSERTION`；**声明本身写明了 GPL-3.0**。我初版把它当主理由也说重了——`JordanzhaoD` 是完整 35,819 字节，确实更干净，但差一档不是差一类 |

#### 备选 `JordanzhaoD/waveshare-single-can-firmware`：仍然成立的三条

- **专板专用**：env 注释直接点名 `; Waveshare ESP32-S3-RS485-CAN standalone product profile.`，**16MB 分区与真板完全一致**（微雪 wiki「Onboard Resources ⑨」就是 16MB Flash），三个仓库里唯一对得上的。
- **650/650 native 测试**（19 个 PlatformIO env），完整 GPLv3 正文 35,819 字节，中文文档，2026-09-22 还在提交。
- **干净的维护闭环**：HEAD `75ac7e7`（`v1.20.1`）是一次**精确回滚**——`v1.19.3`/`v1.19.4`/`v1.20.0` 在真车上出过问题，它把 JITTER 核心退回 `v1.19.2` 的实车验证形态、保留 v1.20.0 的 UI 与电源改动，commit message 里留着 `296 pytest + 879 subtests, native 104/104` 的自证；我实跑 native 正好 104 条全过，与它自称对上。

另有一条背景：**微雪官方 wiki 的「Project Resources」把 `JordanzhaoD` 列为本板的开源固件**。厂商这条背书是真的，也是我初版把排第一的隐含依据——但它回答的是"板子归谁写"，不是"哪份代码最接近你的车"。

**Auto 怎么落到 HW4**——机制和 flipper 是同一个信号（`handlers.h:226`）：

```cpp
// Auto hardware detection from GTW_carConfig (CAN 920)
uint8_t das_hw = (frame.data[0] >> 6) & 0x03;
if (das_hw == 2)      hwDetected = 1; // HW3
else if (das_hw == 3) hwDetected = 2; // HW4
```

`CAN 920` 就是 `0x398 GTW_carConfig`。单测 `test_hw3_auto_detect_hw4_from_can920`（`test_hw3_handler.cpp:368`）在那 650 个通过的用例里。选它要知道三件事。

#### 三个要知道的点

**一、profile 里的 `HW4` 是生效的，但生效方式很绕——不走 C 预处理器，走一个 SCons 脚本。**

这里我先得出过一个错误结论，值得把推理过程也留着：初读 `include/app.h:29-40`，只要定义了 `ESP32_DASHBOARD` 就**先看 `DASH_DEFAULT_HW`**，`#elif defined(HW4)` 那一支根本轮不到：

```cpp
#if defined(ESP32_DASHBOARD)
#if DASH_DEFAULT_HW == 0
using SelectedHandler = LegacyHandler;
#elif DASH_DEFAULT_HW == 2
using SelectedHandler = HW4Handler;
#else
using SelectedHandler = HW3Handler;
#endif
#elif defined(HW4)          // ← dashboard build 确实走不到这里
```

加上 `platformio.ini` 里搜不到 `-DDASH_DEFAULT_HW`、`mcp2515_dashboard.h:78-79` 又兜底成 `1`，我据此写下"profile 选 `HW4` 是无效的、Auto 会回落到 HW3"。**结论错了。** 我漏看了 `scripts/platformio_sync_profile.py` 的后半段：

```python
# :178
_DASH_HW_MAP = {"LEGACY": 0, "HW3": 1, "HW4": 2}
# :183  _pick_dashboard_default(active, VEHICLE_DEFINES, "HW3")
# :230-231
dash_hw_val = _DASH_HW_MAP[selected_vehicle]
_set_cppdefine(env, "DASH_DEFAULT_HW", dash_hw_val)
```

**`DASH_DEFAULT_HW` 根本不是人写的，是脚本从 profile 的 `HW4` 算出来注入的。** 实跑时它会打印这行，我抓到了原文：

```
Synced platformio_profile.h defines for waveshare_single_can_standalone: DASH_DEFAULT_HW=2 (HW4)
```

**反证也做了**：把 build_flag 手改成 `-DDASH_DEFAULT_HW=9`，立刻炸出 `<command-line>: error: 'DASH_DEFAULT_HW' redefined [-Werror]`——说明脚本注入的 `=2` 和我手写的值在同一条命令里打架，宏确实进到了编译器；改回 `=2` 后同值不重复注入，恢复 SUCCESS。

所以完整链路是：

```
platformio_profile.h 里的 #define HW4
        ↓  platformio_sync_profile.py:230
   -DDASH_DEFAULT_HW=2
        ↓  app.h:31-34
   SelectedHandler = HW4Handler          ← 编译期定死
        ↓  mcp2515_dashboard.h:79 / :1784
   NVS 默认值 = 2、Auto 回落值 = 2        ← 运行期都跟着是 HW4
```

**并且 `platformio_profile.example.h` 出厂就把 `#define HW4` 解开了。** 我 diff 过 example 与我实际编译用的 profile，**唯一差异是驱动那一行**（`DRIVER_T2CAN_DUAL` → `DRIVER_TWAI`），车型、行为开关、凭据一字未动。

> 顺带记一个安全网的反面：`#ifndef DASH_DEFAULT_HW / #define DASH_DEFAULT_HW 1` 是兜底值。**哪天脚本没跑，它会静默落到 HW3——不报错，只是行为不对。** 兜底值恰好是错的那个，是这类问题里最难查的一种。

**二、Auto 的检测只认 920，没有备选——但对 HW4 车这恰好不是风险。**

`updateHwDetectedFrom920`（`handlers.h:226`）只匹配 `frame.id == 920`，没有 fallback。`flipper` 的 README 写明它在 `0x398` 不在被接的那条总线上时会退回用 `0x3FD`/`0x399`/`0x3EE` 判（`README:51`）。

我原本把它写成"会一直停在 HW3Handler"——**在第一点纠正之后这句话不成立了**，因为 NVS 默认已经是 HW4。准确的说法是分情况：

| 你的车 | 上电（920 还没到） | 920 到了之后 |
| --- | --- | --- |
| HW4（**你的情况**） | `HW4Handler`，**正确** | `das_hw == 3` → 确认 HW4 |
| HW3 | `HW4Handler`，**错** | `das_hw == 2` → 纠正成 HW3 |
| 920 根本不在被接的总线上 | 保持默认值 | 不切换 |

**所以对 HW4 + 2026.2.11，缺 fallback 是个空风险**：默认值就已经是 HW4，检测触不触发结果都对。真正会踩坑的是"不确定自己是 HW3 还是 HW4"的人——那种情况下 flipper 的三信号 fallback 更稳。

**三、构建依赖没写在 README 里。**

缺什么我一个个撞出来的，全都要手动补：

| 报错 | 处理 |
| --- | --- |
| `Missing platformio_profile.h` | `copy platformio_profile.example.h platformio_profile.h` |
| `platformio_profile.h must enable exactly one driver define` | 示例文件默认解的是 `DRIVER_T2CAN_DUAL`（双 CAN 变体），单 CAN 的这个 env 要改成**只解 `DRIVER_TWAI`** |
| `ModuleNotFoundError: No module named 'csscompressor'` / `'rjsmin'` | `pip install csscompressor jsmin rjsmin` |
| `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa6`（`ev-open`） | `set PYTHONUTF8=1`，脚本用了系统默认编码 |
| `'strlcpy' was not declared in this scope`（`ev-open` `native_plugin_engine`） | **上游 bug**，`plugin_engine.h:747`，Windows/MinGW 下无法编译 |

前四条都能绕过，第五条是仓库自己的问题——它的 9 个 native 套件在本机只能过 7 个。

#### 其余三条路，以及它们的取舍

**A. `JordanzhaoD/waveshare-single-can-firmware` 的 `waveshare_single_can_standalone`** —— 16MB 分区与真板一致、650/650 native 测试、完整 GPLv3、中文文档，且微雪 wiki 把它列进本板的 Project Resources。代价是构建依赖最重（要复制 profile、把 `DRIVER_T2CAN_DUAL` 换成 `DRIVER_TWAI`、装 `csscompressor`/`jsmin`/`rjsmin` 三个 pip 包），`DASH_DEFAULT_HW` 走 SCons 脚本注入这个绕路，以及**全仓没有一处 `2026.2.11`**。

**B. `1-v-1/tesla-open-can-mod` 的 `esp32_twai`** —— 全链路最短、我验得最彻底（4 板 + 107 测试），但 `board = esp32dev` **是经典 ESP32 不是 S3**，要改板型才能烧到你手上这块；且改任何开关都要重烧，仓库冻结在 2026-04-02。

**C. `ev-open-can-tools`** —— 平台化最强（plugin_api、平台注册表、测试计数 235/237）、有 OTA 主动停止与 SD 文档，**恰好也单列了 `waveshare_ESP32_S3_RS485_CAN`**。代价是本机两个 native 套件编译失败（`plugin_engine.h:747` 的 `strlcpy`），`scripts/minify_dashboard.py` 在 Windows 上撞 GBK，分区按 4MB 规划。

**如果只说一句**：买微雪那块 **¥99.99**，用 **`hypery11/flipper-tesla-fsd` 的 `waveshare-s3-can`**——`pio run -e waveshare-s3-can`，或者干脆用 Web Flasher 一键烧，然后连板子 WiFi 开 `http://192.168.4.1`。想要 16MB 分区严格对齐或完整 GPLv3 正文时，再切 `JordanzhaoD`（那套 `pio run -e waveshare_single_can_standalone` 的前置步骤见上一节的坑三）。

#### 边界

**我能担保到 `firmware.bin` 生成为止。烧录之后会发生什么，我没有板子也没有车，一个字都不担保**——包括 CAN 920 是否在你的车上、是否在你接的那条总线上、Auto 是否真的会切到 HW4Handler、以及 HW4 + 2026.2.11 上是否真的出现那个开关。**上一段所有关于"哪份更接近你的车"的比较，依据是三个仓库各自写下的实车记录与自述，不是我验出来的**：flipper 的依据是 `changelog.md:215` 那条社区数据，`JordanzhaoD` 的依据是它自己的 CHANGELOG 自述，两者我都标了行号、也都标明了它们各自的空缺。第 17 节的"未核实"在这一节之后依然成立。

**本节只回答"选哪一份"。买什么、多少钱、线怎么接、固件怎么烧、上电之后点哪里，写在第 20 至 24 节。**

### 四、链接平铺

**主干（还在动）**

```
https://github.com/hypery11/flipper-tesla-fsd
https://github.com/ev-open-can-tools/ev-open-can-tools
https://github.com/ev-open-can-tools/ev-open-can-tools-plugins
https://github.com/ev-open-can-tools/ev-open-can-tools-app
https://github.com/JordanzhaoD/waveshare-single-can-firmware
https://github.com/dzid26/ESP32-DualCAN
https://github.com/babico/TeslaCANModder
https://github.com/tuncasoftbildik/tesla-can-mod
https://github.com/06066060606060/nag-killer
https://github.com/06066060606060/Summon-Unlock
https://github.com/zilviaimbalanced664/flipper-tesla-fsd
```

**本文的解剖对象**

```
https://github.com/1-v-1/tesla-open-can-mod          # 本文所有 file:line 的上游（冻结 2026-04-02）
本地副本  E:\tesla-open-can-mod-main\tesla-open-can-mod-main   # 比上游旧，缺 12 个文件
```

**原版与迁徙链**

```
https://gitlab.com/ev-open-can-tools/ev-open-can-mod # 原 Starmixcraft/tesla-fsd-can-mod，已归档，仅存跳转 README
https://gitlab.com/slxslx/tesla-open-can-mod-slx-repo # 迁徙中间站
```

**CanFeather 一族（冻结快照）**

```
https://github.com/jvanakker/tesla-fsd-can-mod
https://github.com/iubns/tesla-fsd-can-mod
https://github.com/herrfrei/tesla-fsd-canbus-esp32
https://github.com/mert574/tesla-fsd-can-mod
https://github.com/Karolynaz/waymo-fsd-can-mod
https://github.com/qmwdy/tesla-fsd-can-mod
https://github.com/davidgrylls825/tesla-fsd-can-mod
https://github.com/Xingheee/tesla-fsd-can-mod
https://github.com/dongho74s/tesla-open-can-mod
https://github.com/JelloEa/Tesla-Open-CAN-Mod
https://github.com/lenfien/tesla-open-can-mod-release
https://github.com/alanng2017/FFd
```

**其余**

```
https://github.com/JelloEa/tesla-fsd-controller
https://github.com/GeAlan/tesla-fsd-controller-wjsall
https://github.com/J0811/flipper-tesla-fsd
https://github.com/superpositiontime/tesla-fsd-comma4
https://github.com/tumik/S3XY-candump
https://github.com/commaai/opendbc
```

**已 404（写在这儿是为了让链接清单完整，也为了说明它们曾经存在）**

```
https://github.com/linesoft2/tesla-fsd-can-mod-fork
https://github.com/niccolodevries/tesla-fsd-can-enabler
https://github.com/mikegapinski/tesla-can-explorer
https://github.com/mikegapinski/tesla-android-diagnostic-tool
```

---

## 20. 先把车钉死：这台车意味着什么

前面十九节是通用的。从这一节开始，所有判断都挂在一个具体配置上：**China、HW4.0、2025 款 Model 3、软件版本 2026.2.11。** 把这四个词拆开，各自带出一条硬约束。

### 一、`HW4` 三个字，先排掉两个选项

第 8 节讲过，校验和是 HW4 独有的一支；第 14 节的表也列了，本文副本只有 `LEGACY` / `HW3` / `HW4` 三个宏。所以配置里 HW4.0 这一项直接决定：**Legacy（HW1/HW2）那条路不相关**，选型时只需要在 HW3 与 HW4 之间确认，而答案已经由配置给出。

第 19 节的推荐正是基于这一点：`hypery11/flipper-tesla-fsd` 的 `waveshare-s3-can`，因为它在 `changelog.md:215` 留着一条 **`Model Y Juniper HW4 2026.2.11 China`** 的正面兼容数据——**地区、硬件代际、软件版本三项与这台车一致，车型不一致**（那是 Model Y，不是 Model 3）。这个 gap 我不替它补，第 19 节的表格里也标了。

同一节还有一个反向事实：`JordanzhaoD` 全仓 grep `2026.2.11` **一处都没有**。所以"哪一份最接近这台车"这个问题，两家给的是不同性质的证据，不是强弱之分。

### 二、2025 款的 Model 3，第一件该确认的事是 OBD-II 口上是不是 CAN

`hypery11/flipper-tesla-fsd/HARDWARE.md:34`：

> **April 2024+ Juniper Model Y / refreshed Model 3 Highland (later builds)**: Tesla switched to **DoIP** (Diagnostic over IP) — the diagnostic port now carries 100 Mbps Ethernet, **not** CAN.

紧接着 `HARDWARE.md:38-42` 是一条 CAUTION，原文大意是：**不要把基于 CAN 的 OBD-II 适配器或诊断仪接到 DoIP 口上**——电平不兼容，把 J1962-on-CAN 设备插进 DoIP-only 口**可能损坏车辆的诊断模块**；如果你是 2024+ 的车，直接接 X179。

2025 款 Model 3 属于 Highland 改款后的批次，按这段描述**应当默认当作 DoIP 处理**，而不是先插上去试。这不是我的推断，是仓库自己写在 CAUTION 里的判断顺序。

同一节还留了一个限定，我照抄：DoIP 迁移的分类轴是**生产日期与地区，不是"改款与否"**（`HARDWARE.md:189-191`）；适用范围"**not yet pinned down**"（`HARDWARE.md:184-185`）。

### 三、X179 的 pin→bus 映射不固定，而唯一的确定判据在车机里

`HARDWARE.md:93`：**"The X179 pin→bus map is NOT fixed across builds — verify it on your own car."** 至少存在四种电气配置，而且"按年款推断不可靠"（`HARDWARE.md:97`）。

仓库给的确定判据只有一条（`HARDWARE.md:99-102`）：**车机的 Service Mode → CAN Port 页面**，它按线束料号逐针列出所属总线。仓库举的例子是 harness `1933903-XX`（Model Y Juniper RWD 2025，FW 2026.14.3）：`2/3 = Party`、`9/10 = Vehicle`、**`13/14 = Chassis（绿线），不是"Bus 6"`**、`20 = GND`（`HARDWARE.md:104-109`）。

**那台是 Model Y，不是这台 Model 3。** 所以这一节落到你车上的第一步动作很具体：先打开 Service Mode 的 CAN Port，把针号记下来，再动线。仓库另外还给了一条物理判据（`HARDWARE.md:236-238`）：新线束 `4–5` 是**紫色**且已插、`13–14` 空；老线束正好相反。

### 四、生产日期早于 SOP10，但早于 SOP10 不等于 pre-April-2024

`HARDWARE.md:235` 给的 SOP 时间线里，**上海是 2026-03-25（SOP11）**，柏林 2026-04-01，奥斯汀 2025-12-04，弗里蒙特 2025-12-09。2025 年生产的车在这条线之前，因此**不属于 post-SOP10 那一档**（第三对 CAN 从 13/14 挪到 4/5、Chassis 搬到左侧 X177 的变化，`HARDWARE.md:227-233`）。

但 post-SOP10 排除掉，不等于就落在 `HARDWARE.md:169-176` 那张"pre-April 2024"表上——那张表要求的是 2021–2023 与 2024 早期批次。2025 年产的车落在**post-April-2024 档**，而那一档的实测数据是单点（`HARDWARE.md:205`：**"This is a single empirical data point"**）：

| Pin | 柏林产 EU Model Y 实测（`HARDWARE.md:197-203`） |
| --- | --- |
| 9 / 10 | DoIP（以太网），**不是 CAN** |
| 12 / 13 | DoIP，**不是 CAN** |
| **18 / 19** | **Vehicle CAN，唯一可用的 CAN 对** |
| 15 | +12V（不变） |
| 26 | GND（不变） |

那台车是 `@0n3-70uch` 用**示波器**量的（issue `#52`，Berlin 产 pre-Juniper、post-April-2024 生产、FW 2026.14.3）。仓库自己给的三条安全建议（`HARDWARE.md:213-216`）是：

1. **接收发器之前，每一对都用示波器验一遍**；
2. 如果 13/14 的 120Ω 差分信号检查不通过，这一对多半是 DoIP，改试 18/19；
3. +12V（15）与 GND（26）跨 SOP 稳定。

**这三条建议本身我一条都没执行**——没有板子、没有线束、没有示波器。它们是仓库写下的操作，我在这里标了出处和行号。

### 五、把四个词合成一句话

> **这台车的选型前提：HW4 走 HW4 路径；OBD-II 口默认按 DoIP 处理、直接接 X179；X179 先开 Service Mode → CAN Port 记针号，再接线；版本 2026.2.11 上目前唯一一条正面数据来自同代际、同地区、同版本但不同车型的社区回报。**

接下来四节把这句话变成购物车、线、固件和页面。

---

## 21. 选型与购买：清单、价格、链接

### 一、主方案

| 项 | 内容 |
| --- | --- |
| **微雪 ESP32-S3-RS485-CAN** | 官方商城 `https://www.waveshare.net/shop/ESP32-S3-RS485-CAN.htm`，我检索到的标价 **¥99.99**（2 件 ¥96.96）；**该站有反爬，直接打开可能只返回一段 JS**，价格请以页面实际显示为准 |
| 国际站同款 | `https://www.waveshare.com/esp32-s3-rs485-can.htm`（有 `-U` 外置天线版） |
| 规格一手出处 | Wiki：`https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN` |
| 第三方同款参考价 | `https://www.spotpear.cn/shop/ESP32-S3-IOT-RS485-CAN-WIFI-Bluetooth/ESP32-S3-RS485-CAN.html` 标 **¥99**（页面日期 2025-08-14） |
| 对应构建目标 | `waveshare-s3-can`（`README.md:194` 明列支持，`esp32/platformio.ini` 里 TX=15 / RX=16 / LED=46 / BTN=0） |

**从 wiki 核实的规格**（不是我推断的）：

- 主控 **ESP32-S3R8**，Xtensa LX7 双核 240MHz，2.4GHz WiFi + BLE 5 (LE)
- **16MB Flash**（wiki「Onboard Resources ⑨」）／8MB PSRAM
- **板载隔离 CAN**：接线端子、TVS + 浪涌 + ESD 保护、CAN 指示灯
- **120Ω 匹配电阻：默认 `NC`（断开），跳线帽使能** ← 正好符合 `HARDWARE.md:619` 的"不要加第二个 120Ω"
- 端子供电 **7V ~ 36V**，另有 USB Type-C 5V
- 导轨式保护外壳 **91.6 × 23.3 × 58.7 mm**，BOOT + RESET 键

> ⚠️ **wiki FAQ 原文**："Can I power the board using both the terminal block and the USB interface simultaneously? **No, this may risk damaging the module.**"——螺丝端子供电与 USB **二选一**。

> ⚠️ **微雪自己的法律声明**（wiki「Warning」栏）：本产品仅用于合法的开发、学习、研究与工业用途；**严禁将任何 CAN 总线用于未经授权的破解、篡改、解锁或功能劫持**，此类行为可能构成违法，用户自负全部法律责任。这是厂商写下的原话，我照译放在这儿。

### 二、线材与小件

| 件 | 用途 | 价格与链接 |
| --- | --- | --- |
| **USB-A → Type-C 数据线** | 烧录 + 5V 供电 | 必须是**数据线**；我没有可验证的链接，**搜索「Type-C 数据线」** |
| **X179 4 芯线束** | CAN-H / CAN-L / +12V / GND | 我没有可验证的链接，**搜索「X179 线束 特斯拉」**；仓库只写"4-wire pigtail" |
| 万用表 | 量终结电阻、量 12V 是否常电 | `HARDWARE.md:629`、`:646` 都要求这一步 |
| （可选）示波器 | 验每一对是不是 CAN 还是 DoIP | `HARDWARE.md:213` 的第 1 条建议 |
| 杜邦线 / 螺丝刀 | 端子接线 | 微雪板是螺丝端子，需要一字螺丝刀 |

### 三、不用买的东西

| 件 | 为什么不用 |
| --- | --- |
| **CAN 收发器** | 板载隔离 CAN，不用另配 |
| **120Ω 终端电阻** | `HARDWARE.md:619-621`：Tesla 的总线**已经终结**，别加第二个；微雪这块出厂就是断开的 |
| **降压模块** | 板子吃 7~36V，X179 的 12V 直接进端子 |

### 四、备选方案（`HARDWARE.md:377-550` 的四套，价格是仓库标出的美元）

| 方案 | 内容 | 仓库标价 | env |
| --- | --- | --- | --- |
| **A 最便宜全功能** | ESP32-C3-SuperMini / DevKitC + MCP2515(TJA1050) + X179 线 | ~$8–12 | `esp32-mcp2515` |
| **B 即插即用** | [M5Stack ATOM Lite](https://shop.m5stack.com/products/atom-lite-esp32-development-kit) + [ATOMIC CAN Base](https://shop.m5stack.com/products/atomic-can-base) | ~$16–20 | `m5stack-atom` |
| **C 双 CAN** | [LILYGO T-2CAN ESP32-S3](https://lilygo.cc/products/t-2can) | ~$27–29 | `lilygo-t2can` |
| **D 带屏** | [TTGO T-Display](https://lilygo.cc/products/lilygo%C2%AE-ttgo-t-display-1-14-inch-lcd-esp32-control-board) + MCP2515 + [XY-3606 降压](https://www.aliexpress.com/wholesale-xy3606.html) | ~$17–26 | `ttgo-tdisplay` |
| **E 原版** | [Flipper Zero $199](https://flipper.net/) + [Electronic Cats CAN Add-On $35](https://electroniccats.com/store/flipper-addon-canbus/) | ~$239–244 | `.fap`，走 `ufbt` |

**方案 C 值得单独说**：T-2CAN 是双路独立 CAN（原生 TWAI + 外挂 MCP2515），`HARDWARE.md:414-417` 说 `lilygo-t2can` 这个 env 同时驱动两路。第 20 节那张 post-April-2024 实测表显示"唯一可用的 CAN 对是 18/19"，而 `HARDWARE.md:278-286` 又指出 **`0x3C2` 只在 9/10 或 OBD-II 6/14 上可见、13/14 上根本没有**——**单路板接错对就没辙，双路板可以一路接 X179 18/19、另一路留着**。`README:75` 也把"接错总线"写成 HW4 上功能没反应的常见原因。

---

## 22. 接线：从 X179 到螺丝端子

### 一、X179 在哪

**后排中央扶手后面的饰板后面**（2021+ Model 3/Y，`HARDWARE.md:87`）。仓库说它比 OBD-II 好，原因是"提供更多信号，且自带 12V"（`HARDWARE.md:20-21`）。

### 二、引脚表（仓库原文，**不是你车的实测**）

**20-pin（Model 3/Y，`HARDWARE.md:135-147`）**

| Pin | 信号 | 总线 |
| --- | --- | --- |
| **1** | **+12V** | 电源 |
| 2 / 3 | CAN-H / CAN-L | Bus 4（诊断/转发） |
| 9 / 10 | CAN-H / CAN-L | Bus 2（Vehicle CAN） |
| **13 / 14** | **CAN-H / CAN-L** | **Bus 6（网关混合转发）** |
| **15** | **+12V** | 电源（2mm² 线，pin 1 的替代） |
| 18 / 19 | CAN-H / CAN-L | Bus 3（Chassis：EPAS/刹车） |
| **20** | **GND** | 地 |

`HARDWARE.md:149-150`：一个接插件上**4 对独立 CAN**，13/14（bus 6）是后装产品接的地方。

**26-pin，pre-April 2024（`HARDWARE.md:169-176`）**

| Pin | 信号 | 线色 |
| --- | --- | --- |
| **13 / 14** | **CAN-H / CAN-L**（Bus 6） | — |
| **15** | **+12V** | 红，2mm² |
| 18 / 19 | CAN-H / CAN-L（Vehicle CAN） | 蓝 / 黄 |
| **26** | **GND** | 黑，2mm² |

**26-pin，post-April 2024（示波器实测，`HARDWARE.md:197-203`）** —— 见第 20 节第四节，9/10 与 12/13 是 DoIP，只有 18/19 还是 CAN。

> `HARDWARE.md:154-155`：这两档 **"They are not interchangeable."**；`HARDWARE.md:185-187` 的原话是**不要假设你的 26-pin 还是 pre-April 2024 布局，接收发器上电前先用示波器验**。

### 三、四根线怎么接

`HARDWARE.md:305-310` 的原文示意：

```
X179 Pin 13 → CAN-H ──┐
X179 Pin 14 → CAN-L ──┤── CAN module (MCP2515 / TWAI)
X179 Pin 15 → 12V ────┤── buck converter → 3.3V/5V
X179 Pin 20 → GND ────┘   (26-pin: use Pin 26 for GND)
```

对微雪这块板，右侧那半简化掉：**12V 直接进螺丝端子（板子吃 7–36V），GND 进另一个端子，CAN-H / CAN-L 进 CAN 端子**，不需要降压模块。

**接哪一对，取决于第 20 节记下来的 Service Mode 结果。** 仓库为不同功能点名了不同总线，我把出处一并列出：

- **`HARDWARE.md:118`**：**"For the nag killer, tap Party CAN (pins 2/3)."**（同一处还引了 `@SkyRaax` 在 M3 HW4 2026.20 上的双路接法）
- **`HARDWARE.md:278-282`**：要注入 `0x3C2`，接 **9/10** 或 **OBD-II 6/14**；13/14 上根本没有这一帧（`@JakNo` 在 Highland HW4 上确认正例，`@jewelrylin` 确认 13/14 的反例，issue `#73`）
- **`HARDWARE.md:296-298`**：HW4-modern 上 `0x370` 不在 Vehicle CAN，剩下唯一可能的位置是 **Chassis 18/19**

### 四、终结电阻：不要加，并且要量一次

`HARDWARE.md:619-621`：**"Tesla's CAN buses are already terminated. Do not add a second 120 Ω terminator."** 多数后装模块出厂带终结，接车之前先关掉——微雪这块出厂是 `NC`，不用动。

`HARDWARE.md:629-631` 的验证法（**脱车**量）：CAN-H ↔ CAN-L **~120Ω = 正常**（车提供终结）；**~60Ω = 你模块自己的终结器开着**，关掉。

### 五、供电三个坑

1. **OBD-II pin 16 是常电**，车锁了也供（`HARDWARE.md:639-641`）。ESP32 静态约 50mA × 12V ≈ **0.6W 持续**，几天能把 12V 电池放干。
2. **X179 pin 1/15 行为不一**（`HARDWARE.md:645-647`）：有的车随唤醒门控、有的常电，**仓库原话是"先用万用表测再依赖它"**。
3. **螺丝端子供电与 USB 不能同时**（微雪 wiki FAQ），二选一。

永久安装走深睡（`HARDWARE.md:649-659`）：5 分钟无帧 → 深睡约 10µA。

### 六、上电之前的静态检查

| 检查 | 依据 | 判据 |
| --- | --- | --- |
| 脱车量 CAN-H↔CAN-L | `HARDWARE.md:629` | ~120Ω 正常，~60Ω 要关终结器 |
| 万用表量 12V | `HARDWARE.md:646` | 确认 1/15 哪一路有电 |
| 示波器量每一对 | `HARDWARE.md:213` | 区分 CAN 与 DoIP |
| 服务模式记针号 | `HARDWARE.md:99` | CAN Port 页按料号列针 |
| 确认端子/USB 只走一路供电 | 微雪 wiki FAQ | 同时接可能损坏模块 |

**这一节全部是仓库文档与厂商规格的转述，我一条都没实测。**

---

## 23. 烧录与上电：两条路

### 路一：Web Flasher（零工具链）

| | |
| --- | --- |
| Flasher | `https://hypery11.github.io/flipper-tesla-fsd/install/` |
| 或 Releases 里下 `tesla-flasher.html` | `https://github.com/hypery11/flipper-tesla-fsd/releases` |
| 浏览器 | 桌面版 **Chrome / Edge / Opera** |
| 自己编译 | `esp32/README.md` 给的是 `pio run -e waveshare-s3-can` |

### 路二：自己编（**这一条我实跑了**）

```bash
git clone https://github.com/hypery11/flipper-tesla-fsd.git
cd flipper-tesla-fsd/esp32
pio run -e waveshare-s3-can
```

第 16 节记录的本机结果（在上游 `6a3404f` 上复跑）：`waveshare-s3-can` **SUCCESS，RAM 37.4% / Flash 28.0%，`firmware.bin` 934,672 字节**；同一棵树的其余 9 个 env 也全部 SUCCESS（**10/10**，2 分 47 秒）。加 `-t upload` 就是烧录。

同一块板在三个仓库里的四个 S3 env，编译数据都在第 16 节那张表里（`TX=GPIO15 / RX=GPIO16` 是三家各自独立给出的同一组值）——**烧哪一份由第 19 节的推荐决定，这里不列第三遍**。

### 上电之后的第一状态：只听

- `esp32/README.md:119`：**Listen-Only Mode — Default on boot, passive monitoring only**
- `README:227`：板子启动后是 Listen-Only，**要用户手动切到 Active 才开始发送**

也就是：**上电 ≠ 会发帧**。这是仓库把安全默认写进启动路径的结果，第 15 节列过同一个结构。

---

## 24. 板子与车上的操作流程，以及仓库的指南到此为止

### 一、到 dashboard 为止的四步

1. **接线**（按第 22 节记下的针号）→ **上电**（端子或 USB，二选一）。
2. **连板子的 WiFi**，浏览器开 **`http://192.168.4.1`**（`esp32/README.md:121`：WiFi Dashboard，实时网页 UI）。
3. **先看接线对不对**：`esp32/README.md:120` 的 **Wiring Check = `rx_count` + CRC error monitoring**。这一步只读，对应第 15 节里的 Listen-Only：**帧数在涨、CRC 错误为 0，说明收发对了；反过来先回第 22 节查线。**
4. **选硬件模式**：`esp32/README.md:114` 的 **HW Override = Auto-detect / Force HW4 / Force HW3 / Force Legacy**，运行时选择、不用重烧。

### 二、仓库自己写下的几条运行约束

| 约束 | 出处 | 内容 |
| --- | --- | --- |
| OTA 检测 | `esp32/README.md:117` | 检测到 OTA 更新会**自动停止 TX**，除非显式开 Ignore OTA |
| Autopark 暂停 | `README:95` | 车内 Autopark 期间**全部 TX 停止** |
| 只读功能不依赖 FSD | `README:20` | 仓库原话：非 FSD 功能（诊断、BMS 面板等）不需要任何订阅 |
| FSD 功能需要有效权益 | `README:20` | 仓库原话：本工具在 CAN 层使能，**车辆仍需有效的 FSD 资格** |

### 三、仓库的指南到此为止

**以上全部是仓库文档与厂商规格的转述，行号都给了，我一条都没执行**——没有板子、没有线束、没有车。

**这里也是仓库的指南到此为止。** 再往前走的那几步——上路之后 nag 是否真的不再出现、FSD 是否真的接合、某个开关在 2026.2.11 上到底有没有效果——**不在本文范围内，仓库文档本身也没有给出验证步骤**，我不会替它编一份。同样地，任何关于规避检测、隐匿接入、移除车上通信模块之类的做法，本文一概不涉及。

**我能担保到 `firmware.bin` 生成、到上面每一条引用的行号为止。** 烧录之后车会怎么反应，见第 19 节的边界段与第 17 节的"未核实"。

---

## 25. 同一套方法，换一个仓库：`flipper-tesla-fsd` 源码解剖

**先认账。** 第 1 至 11 节逐行读的是 `tesla-open-can-mod`，而第 19 节把推荐给了 `hypery11/flipper-tesla-fsd`——**推荐了一个我没读过的仓库**。全文对它的源码引用只有 6 处，全是构建命令、测试数字和文件名，没有一行是它的逻辑。这一节把欠的补上，方法与前面一致：先画地图，再分三层，最后看横切面。

> **本节行号钉在上游 `6a3404f`（2026-09-30 的 HEAD）。** 我第一遍读的是 `19ef738`（`v2.16-beta.29`，2026-09-24），核对时发现上游已往前走了 24 个提交：**函数行号从 `fsd_handle_legacy_stalk` 起 +1、从 `nag_faithful_modec` 起 −12**，总行数 1356 → 1344，`fsd_build_steering_tune_frame` 被整个删掉（函数 65 → 64），宿主测试 695 → 827。所以这一节的每个行号都对着 HEAD 重新 grep 过一遍，**第四小节记了一处因为这 24 个提交而整个失效的结论**，第八小节把它从"代价"里撤了出去——两处合起来，正好是第 27 节"行号必须钉死在具体版本上"的一次自我演示。

### 一、地图：一棵树，两份业务层，一套共享原语

| 位置 | 规模 | 职责 |
| --- | --- | --- |
| `fsd_logic/fsd_handler.c` | 58.7 KB，**1344 行 / 64 个函数** | 协议核心（C 版） |
| `esp32/.firmware/fsd_handler.cpp` | 51.8 KB | **同一套业务的 ESP32 版（C++）** |
| `esp32/.firmware/main.cpp` | 79.2 KB | 接收分发与运行时 |
| `fsd_logic/fsd_state.h` | `:23` → `:365` | 状态，**一个 343 行的 struct** |
| `fsd_logic/fsd_checksum.h`、`fsd_can_ops.h` | — | 两个平台共用的无状态原语 |
| `test/` | `test_fsd_core.c` 127.6 KB、`test_esp32_core.cpp` 31.9 KB | 宿主测试，即第 16 节那 827 条 |

第一个要看清的结构事实：**业务层有两份。** `esp32/.firmware/fsd_handler.cpp:14-16` 的三条 include 把边界写得很明白：

```cpp
#include "../../fsd_logic/fsd_checksum.h"  // shared Tesla additive checksum (single impl, both platforms)
#include "../../fsd_logic/fsd_can_ops.h"   // shared stateless frame primitives (set_bit / mux / fsd-selected)
#include "../../fsd_logic/fsd_ota.h"       // shared 0x318 OTA-install detection (flag vs rolling counter)
```

共享的是**无状态原语**；**判断逻辑各写一遍**：`fsd_handle_autopilot_frame` 在 C 版是 `fsd_handler.c:191`、在 C++ 版是 `fsd_handler.cpp:265`，`fsd_detect_hw_version` 分别在 `:98` 与 `:123`。这两个数字在 24 个提交之后**一个都没动**——C++ 那侧与共享头整段没变，动的是 C 版与 `main.cpp`。

直接后果是**同一个 bug 要在两处各修一次**，而两处的测试是分开的：`test_fsd_core` 编 `.c`，`test_esp32_core` 编 `.cpp`。第 16 节那 827 条正是这么来的——**648 条打 C 版，179 条打 C++ 版，没有一条同时覆盖两者**。

### 二、第一层序列：启动

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

与第 3 节的 `appSetup()` 对照，形状完全不同：那边是**硬件初始化序列**（串口、CAN、过滤器、中断），这边硬件初始化在平台层的 `main.cpp`，**这一层只剩状态初始化**。三处细节：

- `memset` 先清零，再**只把有默认值的字段写出来**，其余全靠零值语义。
- `das_hands_on_state = 0xFF` 是**"未见过"哨兵**。`:1262` 的注释写明 `0xFF = no DAS frame seen yet — echo conservatively as fallback`；用 0 就会被当成 `NOT_REQD`（`das == 0` 在 `:1269` 直接 return），门控语义整个反过来。
- `gtw_autopilot_tier = -1` 同理，用 -1 区分"没读到"和"第 0 档"。

**哨兵值是这个状态机最容易被改坏的地方**，而它在初始化里就定死了。

### 三、第二层序列：运行

`esp32/.firmware/main.cpp` 的接收回调按固定顺序跑，**分发业务之前先做四件与业务无关的事**：

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

**先记录、后判断**，而且 6 和 7 都提前 `return`——这两类帧不会流进业务层。第 5 节讲 `tesla-open-can-mod` 时没有这个结构：它在初始化装好过滤器（第 10 节）之后，命中帧一律直接进 `handleMessage()`。

#### 并发：`portENTER_CRITICAL` 对上第 4 节的 `volatile`

第 4 节说 `appLoop()` 用 `volatile` 解决中断与主循环的可见性问题。这里的做法更重：

```cpp
static void state_enter() {
    portENTER_CRITICAL(&g_state_mux);
```

`main.cpp:71-72`，配套 `state_exit()` 在 `:75`；每次读写 `g_state` 前后进出临界区，`:1162` 与 `:1168` 就是一对。**代价是关中断，收益是状态从"单字段可见"变成"整体一致"**——`fsd_state.h` 那 343 行是一个 struct，读者要么全看见、要么全看不见。

#### 发送许可：一个函数，三道条件，五处调用

`fsd_logic/fsd_handler.c:41-48`：

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

`main.cpp` 里**每一条会发帧的路径**都要先问它一次：`:287`（挡位序列）、`:876`、`:1276`、`:1331`（nag killer）、`:1747`（预空调用）。

这是第 15 节那张门控表最缺的实据：**`tesla-open-can-mod` 里不存在这样一个函数**，它的发送许可全在编译期宏里，运行时没有一处"统一问一次"的地方。注释里那句 `Not overridable by ignore_ota` 还说明这个门是**分层**的——`ignore_ota` 能开的洞，Autopark 那一层不给开。

### 四、第三层序列：业务

`fsd_logic/fsd_handler.c:191-331`，一个函数，四道门在改任何比特之前：

```c
bool fsd_handle_autopilot_frame(FSDState* state, CANFRAME* frame, uint32_t now_ms) {
    if(frame->data_lenght < 8) return false;

    if(!fsd_ap_first_allows(state, now_ms)) return false;   // :197
    if(!fsd_soft_engage_allows(state)) return false;        // :200
    if(!fsd_abort_guard_allows(state)) return false;        // :203
    if(state->ap_first_minimal && state->ap_inject_count >= AP_MINIMAL_INJECT_FRAMES)
        return false;                                        // :207
```

四道门各管一件事：AP 是否真的接合且稳定（`:150-161`）、方向盘是否回正（`:163-175`）、本次接合是否进过 abort（`:177-189`）、这次接合的注入预算花完没有（`:207`）。**有三道是 2026.14.x 之后才加的**，注释里直接挂着 issue 号（`#108`、`#100`）。第 15 节列的 `tesla-open-can-mod` 门控清单里，这四种一个都没有。

过了门才是 mux 分发（`:210-214`）：

```c
uint8_t mux = fsd_read_mux_id(frame);
bool fsd_ui = fsd_is_selected_in_ui(frame, state->force_fsd);
bool modified = false;

if(mux == 0) state->fsd_enabled = fsd_ui;
```

随后按硬件代际分两支，形状与第 5 节三个 handler 的分支一致：

| | HW3（`:228-274`） | HW4（`:275-324`） |
| --- | --- | --- |
| mux 0 | 算速度偏移 → `set_bit(frame, 46, true)`，写 byte6 速度档（`:229-240`） | `set_bit(46)` + `set_bit(60)`，可选 `set_bit(59)`（`:277-284`） |
| mux 1 | 清 bit19，一串开关逐个写 48/50/47/46/…（`:241-267`） | 同一串开关（`:285-310`） |
| mux 2 | `if(mux == 2 && state->fsd_enabled)`（`:268`） | `if(mux == 2)`（`:311`） |

**第三行是一个跨仓库的同构。** 第 5 节记过：`tesla-open-can-mod` 的 HW3 mux 2 检查缓存（`handlers.h:104`），HW4 的 mux 2 是"光秃秃的 `if (index == 2)`"（`handlers.h:165`）。flipper 这里**一模一样**——HW3 那支要 `state->fsd_enabled`，HW4 那支不要。两个仓库、两套语言、同样的不对称，不像巧合，更像其中一份沿用了另一份的帧布局语义。**我没有证据指认方向**，只把这个形态记下来；24 个提交之后它仍在原处。

**第二行曾经不是这样，这是本节唯一一处"我第一遍读到的结论在上游已经失效"。** 在我的分析副本 `19ef738` 上，HW4 的 `bit47` 是**无条件**置位的，头上压着仓库自己写的一段坦白（原文 `:294-297`）：

```c
// HW4 sets bit47 (summon enable) unconditionally here (pre-existing),
// so the summon_unlock toggle is effectively always-on for HW4 on this
// build. The toggle's real effect is on the HW3 path above; ESP32 gates
// both HW3 and HW4. Reconciling this divergence is a follow-up.
```

一个"opt-in 默认关"的开关，在 HW4 那一支其实是常开的——注释写明了，也写了待办。**等我换到上游 HEAD 重读，这个 follow-up 已经做完了**，`:294-296` 现在是：

```c
if(state->summon_unlock) {
    fsd_set_bit(frame, 47, true);   // summon enable (ev-open-can-tools summon-eu-unlock)
}
```

与 HW3 的 `:251-253` 完全对称，那段坦白注释也删了。**24 个提交，一个自陈的 TODO 归零**——这既是我该给 flipper 的分（注释比 README 诚实，而且说到做到，正是第 14 节批评文档落差时欠它的那一分），也是本节必须钉死 commit 的理由：**如果我只写"bit47 常开"，这句话在上游 HEAD 上已经是错的。**

### 五、nag killer：独立一支，且有自己的门

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

`:1251-1254` 的注释把一次历史修改钉住了：原来的守卫写成 `hands_on != 0` 就跳过，**结果把 level 3（升级告警）也一起跳过了**，改成"只在 level 1 时跳过"。**一个门控条件写反导致功能静默失效**的实例，被注释固定下来。

发出去的帧是**整帧回读再改**，不是凭空造（`:1320-1339`）：

```c
out->buffer[4] = (frame->buffer[4] & ~0xC0u) | 0x40u;   // 清掉 7:6 再置 level=1
...
uint8_t cnt = (frame->buffer[6] & 0x0F);
cnt = (cnt + 1) & 0x0F;
out->buffer[6] = (frame->buffer[6] & 0xF0) | cnt;        // counter + 1
```

`:1328-1329` 解释了为什么要先清：`OR-ing 0x40 without clearing leaves level=3 unchanged on escalated frames`——**不先掩码就 OR，升级帧上 level 仍是 3**。这与第 6 节 `setBit` 的"写绝对位号"是同一个问题的两种处理：位操作一旦带读-改-写语义，忘了掩码就会静默失效。

末尾重算校验和（`:1339`）：

```c
out->buffer[7] = tesla_additive_checksum(CAN_ID_EPAS_STATUS, out->buffer, 7);
```

### 六、横切面一：位操作

`fsd_handler.c:85-87` 只有一行转发：

```c
void fsd_set_bit(CANFRAME* frame, int bit, bool value) {
    tesla_set_bit(frame->buffer, bit, value);
}
```

实现在 `fsd_logic/fsd_can_ops.h:19` 的 `tesla_set_bit`，两个平台共用。**第 6 节那四个原语（`setBit`/`clearBit`/`readBit`/掩码写）在这里被压成一个带 `value` 参数的函数**——语义等价，词汇量少一半。头文件那行注释叫它 `shared stateless frame primitives`，**"无状态"就是这个抽象的全部要点**。

### 七、横切面二：校验和——与第 8 节是同一帧、同一串操作

`fsd_logic/fsd_checksum.h:28` 的 `tesla_additive_checksum(can_id, data, len)`，用法写在 `:22-23`：

```
 *   ISA/track/nag : tesla_additive_checksum(ID, frame_bytes, 7)  -> goes in byte 7
 *   SCCM left CRC : tesla_additive_checksum(0x249, &bytes[1], 2)  -> goes in byte 0
```

其中 ISA 那一支（`fsd_handler.c:391-396`）：

```c
bool fsd_handle_isa_speed_chime(CANFRAME* frame) {
    if(frame->data_lenght < 8) return false;
    frame->buffer[1] |= 0x20;
    frame->buffer[7] = tesla_additive_checksum(CAN_ID_ISA_SPEED, frame->buffer, 7);
    return true;
}
```

**和第 8 节逐句对得上。** 那边是 `frame.data[1] |= 0x20` → 累加前 7 字节 → 加 ID 高低字节 → 写 `data[7]`；这边是 `buffer[1] |= 0x20` → `tesla_additive_checksum(CAN_ID_ISA_SPEED, buffer, 7)` → 写 `buffer[7]`。`CAN_ID_ISA_SPEED` 就是 `0x399`，而 **`921 == 0x399`**——第 8 节讲的那帧，正是这里这帧。

差别只在封装：`tesla-open-can-mod` 把循环**内联**在 handler 里，flipper 抽成 `static inline` 放进共享头；ESP32 版（`fsd_handler.cpp:453-460`）还把字节位换成了命名常量 `SIG_ISA_SOUND_ACTIVE_BYTE` / `_MASK`。

**这是收敛还是抄袭，我判定不了。** flipper 在别处是会署名的——`fsd_handler.c:50` 写着 `BMS read-only parsers (CAN frame templates from tuncasoftbildik/tesla-can-mod)`，多处注释指向 `ev-open-can-tools`，**这一支却没有署名**。我只能把行号并排放着，方向不猜。

**另一个共同点更重要**：两边都**只在自己起头发的帧上重算校验和**（`921`、`0x370`、track、ISA），**在原地改 `0x3FD` 再回发时都不重算**。第 5 节讲 `handleMessage()` 改 `0x3FD` 时没提校验和，这里 `fsd_handle_autopilot_frame`（`:191-331`）里也**一次都没有调用** `tesla_additive_checksum`——1344 行中，这个函数内部没有任何校验和调用。

### 八、读完之后，第 19 节的推荐要不要改

**改理由，不改结论。**

原来那四条理由全部来自 README 和 changelog——实车数据、板子明列、宿主测试、Web Flasher。**四条一条都没变**，但它们都是"别人说自己做过什么"。读完源码，现在多了三条**我自己看过**的：

1. **统一发送许可真实存在**（`:41-48`，五处调用点），第 15 节那张表 flipper 那一列从"README 说有"变成"我看过"。
2. **四道前置门在改任何比特之前**（`:197-207`），`tesla-open-can-mod` 一个都没有。
3. **状态是一个 343 行 struct 配真临界区**（`fsd_state.h:23-365`、`main.cpp:71-75`），比第 5 节那种"三个 handler 各存一份全局"更不易读到中间态。

同时也看到两条**该写进去的代价**：

1. **业务层有两份**，bug 要修两次，827 条测试没有一条同时覆盖两者。
2. **mux2 不对称**与 `tesla-open-can-mod` 同形（`:268` vs `:311`），两个仓库各自带着同一个毛病。

**原本还有第三条——HW4 mux1 的 bit47 常开（`:294-297`）——它在我换到上游 HEAD 重读时已经不成立了**，全过程记在第四小节。这条从代价里撤掉，但换了个位置：**它变成"24 个提交就能让一句结论过期"的实例**，而这个风险由写文章的人承担，不由仓库承担。

所以：**推荐维持，理由换掉。** 原来那四条是社区证据，这三条是源码证据——后者与第 1 至 11 节用的是同一套标准，可以按同样的力度相信。

**但第 20 节那句话必须留着**：`changelog.md:215` 那条数据是 Model Y 不是 Model 3，**源码读得再细也补不上这个 gap**。

### 九、这一节的边界

行号可 grep 复现，64 个函数与 1344 行是我数的，827 条测试是我跑的——**这一节的三样数字全部钉在上游 `6a3404f`（2026-09-30）**。**但它在车上会怎样，依然一个字没验**——第 17 节的"未核实"与第 24 节的"仓库的指南到此为止"在这里同样成立。

另有两处开关我按第 24 节划的线**不展开**，只留行号供自行查证：`fsd_handler.c:247-250`、`:290-293`。

---

## 26. 参考与引用：本文用到的每一条外部出处

第 19 节第四小节列的是**全部 git 仓库链接**；这一节列**仓库之外**的每一处外部引用，按性质分组，每条给 URL 与页面日期（或访问日期 2026-09-30）。三类性质请勿混用：**一手**＝我能直接拿到原文；**社区回报**＝第三方在 issue/讨论里的单点陈述，我未独立核实；**未核实**＝我明确没有验证。

### 一、厂商文档（一手）

| 出处 | URL | 日期 | 用在哪 |
| --- | --- | --- | --- |
| 微雪 Wiki ESP32-S3-RS485-CAN | `https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN` | 访问 2026-09-30 | 第 21 节规格、120Ω 默认 NC、7–36V、双路供电警告、法律声明 |
| 微雪国际站商品页 | `https://www.waveshare.com/esp32-s3-rs485-can.htm` | 访问 2026-09-30 | 型号 `-U` 外置天线版 |
| 微雪官方商城 | `https://www.waveshare.net/shop/ESP32-S3-RS485-CAN.htm` | 访问 2026-09-30 | 第 21 节标价（**该站有反爬，页面未直接返回价格**） |
| PlatformIO | `https://platformio.org/` | 出自 `esp32/README.md`，未另开页面 | 第 23 节工具链 |
| Flipper Zero | `https://flipper.net/` | 出自 `HARDWARE.md`，未另开页面 | 第 21 节方案 E |

### 二、第三方价格（第三方页面，非一手）

| 出处 | URL | 页面日期 | 用在哪 |
| --- | --- | --- | --- |
| Spotpear 同款 | `https://www.spotpear.cn/shop/ESP32-S3-IOT-RS485-CAN-WIFI-Bluetooth/ESP32-S3-RS485-CAN.html` | 2025-08-14 | 第 21 节 ¥99 参考价 |
| M5Stack ATOM Lite | `https://shop.m5stack.com/products/atom-lite-esp32-development-kit` | 仓库引用 | 第 21 节方案 B |
| M5Stack ATOMIC CAN Base | `https://shop.m5stack.com/products/atomic-can-base` | 仓库引用 | 第 21 节方案 B |
| LILYGO T-2CAN | `https://lilygo.cc/products/t-2can` | 仓库引用 | 第 21 节方案 C |
| LILYGO TTGO T-Display | `https://lilygo.cc/products/lilygo%C2%AE-ttgo-t-display-1-14-inch-lcd-esp32-control-board` | 仓库引用 | 第 21 节方案 D |
| AliExpress XY-3606 降压 | `https://www.aliexpress.com/wholesale-xy3606.html` | 仓库引用 | 第 21 节方案 D |
| Electronic Cats CAN Add-On | `https://electroniccats.com/store/flipper-addon-canbus/` | 仓库引用 | 第 21 节方案 E |

**"仓库引用"指这一条 URL 出自 `hypery11/flipper-tesla-fsd/HARDWARE.md`，我没有另开页面核对价格**；第 21 节表里的美元数字是**仓库标的**，不是我查的。

### 三、社区回报（issue / discussion，我未独立核实）

| 内容 | 出处 | 用在哪 |
| --- | --- | --- |
| post-April-2024 26-pin 只有 18/19 是 CAN | issue `#52`，`@0n3-70uch` 示波器实测，Berlin 产 EU Model Y，FW 2026.14.3 | 第 20、22 节 |
| `0x3C2` 在 9/10 可见、13/14 不可见 | issue `#73`，`@JakNo` / `@jewelrylin` | 第 20、22 节 |
| X179 pin→bus 的 Service Mode 实测表 | issue `#100`，`@jewelrylin`，harness `1933903-XX`，Model Y Juniper RWD 2025，FW 2026.14.3 | 第 20 节 |
| post-SOP10 针位重排与 X177 | discussion `#114`，`@mamixsystem` | 第 20 节 |
| Nag killer 接 Party CAN 2/3 | `@SkyRaax`，M3 HW4 2026.20，issue `#100` | 第 22 节 |
| VIN 封禁研究 | issue `#18`、仓库 `SECURITY.md` | 第 17 节 |
| HW4 + 2026.2.11 正面兼容数据 | `changelog.md:215`，`@Tikernel` + `@ViPiMP`，**Model Y Juniper** | 第 19、20 节 |
| 分版本兼容结论表 | `hypery11/flipper-tesla-fsd` tracker issue | 第 17 节 |

### 四、工具与可复现入口

| 内容 | URL |
| --- | --- |
| Web Flasher | `https://hypery11.github.io/flipper-tesla-fsd/install/` |
| Releases | `https://github.com/hypery11/flipper-tesla-fsd/releases` |
| FSD CAN Mod Hub 跟踪页（README 徽章指向） | `https://fsdcanmod.com/project/hypery11-flipper-zero` |
| Tesla Model Y Electrical Reference（仓库引用的官方文档） | `https://service.tesla.com/docs/ModelY/ElectricalReference/` |

### 五、本文的证据分层

| 层 | 例子 | 可信度 |
| --- | --- | --- |
| 本地源码 `file:line` | 第 1–11 节全部 | 可 grep 复现 |
| 上游 `README.md:N` | 第 12、16 节 | 钉死在 commit `815e000` |
| 本机实际执行 | 第 16 节的编译与测试输出 | 可重跑 |
| API 直接查询 | 第 13 节元数据 | 可复现（API 限流后改用 `git ls-remote` 的已在表内注明） |
| 仓库文档转述 | 第 20–24 节大部分 | **出处行号可查，内容我没验** |
| 社区回报 | 本节第三组 | **未独立核实** |
| 未核实 | 兼容性状态 | **第 17 节的结论不变** |

---

## 27. 总结

回到开头那个问题：操作序列写在代码里，在哪三层。

- **启动序列** → `include/app.h:29-48` 的 `appSetup()`：建 handler → 延时 → 开串口 → 初始化 CAN → 装过滤器 → 挂中断。顺序有依赖，handler 必须先建，因为过滤器清单在它手上。
- **运行序列** → `include/app.h:50-63` 的 `appLoop()`：中断置位 → 排空读取 → 逐帧转发给 handler。`volatile` 与 `if constexpr` 各解决一个并发问题。
- **业务序列** → `include/handlers.h` 的三个 `handleMessage()`：按 mux 索引分支，读状态、改比特、回发。所有车辆行为的决定都在这一层。

三层之外还有两个横切面：`can_helpers.h` 那 27 行位操作原语是词汇，`drivers/` 下一个接口四个实现是 IO。选型全部在编译期，运行时零分支。

读完这个仓库，有三条判断值得摆出来。

第一条，它的成熟度高于这类工具的平均水准。第 7 节那个 shadowing 回归测试是具体证据：发现隐式耦合、修复、用测试锁死、把意图写进测试名。维护良好的项目才会有这样的做派，随手一写的脚本不会这样。

第二条，"安全门控"的分布很不均。说三个仓库都有安全设计并不错，但具体到这个仓库，它选的是编译期门控而非运行时门控（第 15 节）：没有滚动计数、没有统一发送许可、没有只听模式。如果你关心的场景是"编译对了但时机不对"，它提供的保护比另外两个少。

第三条是这次横向调研才暴露出来的：我手上的副本已经不是上游了。第 17 节把两份 README 的差异逐项列了出来，其中 PlatformIO 车型宏那条直接改写了第 14 节裂缝二的适用范围。对一篇按行号写作的文章，这决定了每条结论的保质期——行号必须钉死在某个具体版本上，否则将来连"我错在哪"都说不清。

文档侧的三处裂缝（第 14 节）指向同一件事：开源工具链的可信度不能只看代码质量，还要看文档是否跟得上代码。代码是干净的，Arduino IDE 路径是通的，但 PlatformIO 路径、M4 指南的选型行、两份接线指南对 X179 位置的互相矛盾，各有一处会让第一个照做的人卡住。

兼容性（第 17 节）我保持未核实，但把 2026 年上半年发生的事按日期和来源写进去了。那只能算背景，不构成对任何具体版本的判断——能验证的我写了并给了 grep 方法，不能验证的我说了不能验证。

第四条是动手篇（第 20 至 24 节）带来的，也是这一版新学到的：**"能不能编"和"能不能接"是两个独立问题，而且后者更硬。** 前者我已经用 18 个板级环境、38 个测试套件、1904 个用例给了答案——四个 ESP32-S3 目标全部 SUCCESS。后者一条都没解决：X179 的针号要进车机 Service Mode 才知道，OBD-II 口上是 CAN 还是 DoIP 要看生产日期与地区，终结电阻要脱车量，12V 是否常电要万用表测。**编译通过是我在桌面上能给的最强证据，它到 USB 线为止。**

第五条是这一版把结论落到一台具体配置上之后才看清的：**社区数据的可迁移性取决于同一性，而不取决于相似度。** `changelog.md:215` 那条数据在地区、硬件代际、软件版本上与这台 China HW4.0 / 2026.2.11 的 2025 款 Model 3 完全一致，唯独车型是 Model Y——这一项差在哪里，我没有数据，所以第 20 节把这个 gap 单独写了出来，而不是让它在"同版本"三个字里被抹掉。反过来说，`JordanzhaoD` 全仓没有一处 `2026.2.11`，也不等于它不合适，只是它给的证据类型不同。**选型时该问的不是"哪个更好"，而是"哪一份的证据恰好落在我的配置上"。**

第六条是补读（第 25 节）逼出来的：**推荐一个仓库和读一个仓库是两件事，我做反了。** 把 `flipper-tesla-fsd` 排第一的时候，我手上只有它的 README 和 changelog——那是"别人说自己做过什么"；读完源码才拿到"我看过"级别的证据：统一发送许可、四道前置门、真临界区都在，业务层写两份这个代价也真在。更难堪的是**同一节里有一条结论在我换到上游 HEAD 后整个失效**（bit47 那处分歧，仓库自己在这 24 个提交里修掉了）。推荐换了理由，第三条那个抽象提醒也变成了一次具体事故——**先下推荐、再补源码，顺序错了要还。**

最后是边界。第 24 节末尾那句话在全文要重复一次：**仓库的指南到此为止。** 往前的每一步——上路之后某个开关到底有没有效果、功能是否真的接合——既不在我验过的范围内，也不该由我替仓库编一份流程。我能担保的是行号、是编译输出、是引用出处；再往前，需要的是读者自己的板子、自己的线、自己的车，和一份愿意承认"我不知道"的记录。

---

**下一篇**我打算回到网络架构本身：经典 CAN、CAN FD、以太网骨干各自承载什么，以及为什么一家车企的网络选型会直接决定它的功能迭代速度。那个题目会比这篇更接近日常工程。
