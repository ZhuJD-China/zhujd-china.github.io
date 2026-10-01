---
title: CAN 固件解剖：三个仓库最新版源码解读、一致性与区别，以及 2025 Model 3 HW4 / 2026.2.11 实践
date: 2026-10-01
tags: [自动驾驶, CAN总线, 嵌入式, 固件分析, 特斯拉, 源码分析]
album: 自动驾驶专栏
order: 3
excerpt: 围绕同一条 CAN 总线的三个仓库，我按 2026-10-01 的实际最新版重新钉死行号：tesla-open-can-mod 的 815e000、flipper-tesla-fsd 的 ffbb24e（v2.16-beta.34）、ev-open-can-tools 的 6d37392（v4.0.0-beta.3——它不在默认分支上，main 落后 14 个提交）。三份源码用同一套方法读：地图、启动/运行/业务三层序列、位操作与校验和横切面；再把三者的一致骨架和五条分化维度摊开对照；最后落到一台具体车上——China HW4.0、2025 款 Model 3、2026.2.11 的选型、购买、X179 接线与烧录，附实跑数据汇总与外部引用出处。
---

《自动驾驶专栏》第三篇。**2026-10-01 重写**：结构由 27 节压到 15 节，源码解读从两份补齐到三份，全部行号按当天的上游重新核过。

围绕同一条 CAN 总线，社区里长出的公开实现不止一个。本系列盯其中三个：PlatformIO 固件工程 `tesla-open-can-mod`、Flipper Zero 应用 `flipper-tesla-fsd`、ESP-IDF 固件平台 `ev-open-can-tools`。形态差得很远——编译期选型、运行时菜单、网页开关——但把三份源码摊开，操作序列藏在同一个地方，骨架也长得惊人地像。

## 0. 三个版本，先钉死

**行号不钉在版本上就没有意义。** 下面每一个 `file:line` 都对着这张表的某一格，换一格就要重推。这张表是 2026-10-01 当天用 `git ls-remote` 逐个问的：

| 仓库 | 我对着的 commit | 版本 | 说明 |
| --- | --- | --- | --- |
| [`1-v-1/tesla-open-can-mod`](https://github.com/1-v-1/tesla-open-can-mod) | `815e000`（构建与教程的 `上游 README.md:N`） | 无 tag、无 release | 最后 push 停在 **2026-04-02**，183 天没动。**第 1 节的 `file:line` 对着本地副本** `E:\tesla-open-can-mod-main`，两者差异见第 8 节 |
| [`hypery11/flipper-tesla-fsd`](https://github.com/hypery11/flipper-tesla-fsd) | **`ffbb24e`** | **`v2.16-beta.34`**（2026-10-01） | 当天仍在提交。文章初版钉的 `6a3404f`（beta.33）已前进 4 个提交，`esp32/.firmware/main.cpp` 因此 **+25 行** |
| [`ev-open-can-tools/ev-open-can-tools`](https://github.com/ev-open-can-tools/ev-open-can-tools) | **`6d37392`** | **`v4.0.0-beta.3`**（2026-09-20） | **不在默认分支上**：`main` 停在 `338d276`（2026-08-05，`VERSION` 写 3.1.1），`dev` 分支才是 `6d37392`。两线在 `447049d`（2026-07-31）分叉，`dev` 领先 14 个提交 |

第三行是这次重写新查出来的：**我原先把 API 的 `pushed_at`（2026-09-20）和 clone 拿到的 `main`（2026-08-05）当成了同一件事**——两条分支的 `VERSION` 分别写 `3.1.1` 与 `4.0.0-beta.3`。**第 3 节按 `dev` 重推了全部行号。**

**证据约定，按结论类型分档，不混用：**

| 结论类型 | 我的验证方式 |
| --- | --- |
| 某段代码在哪一行 / 文档与代码对不上 | 本地源码逐行读、双方各 grep 一次，可复现；每条标 `文件:行号` |
| 测试数量与断言 | 逐个 `RUN_TEST` 数过，并**实际执行** |
| 板级 env 能否编出固件 | 装 PlatformIO **真的构建**，输出见第 7 节 |
| HW4 / 某个 OTA 版本该编哪个宏 | 规则来自仓库 README，行号可复现；**上车效果未验证** |
| X179 引脚、哪对线上是哪条总线 | 仓库文档原文 + 出处行号；作者没接车、没量过示波器，**未实测** |
| star、日期、tag、价格、兼容性、行业事件 | `git ls-remote`、公开 API、网络检索，附 URL 与页面日期，可复现但未逐行核验 |
| 烧录之后车会怎么反应 | **完全不验证**——没有板子、没有线束、没有车辆，见第 13 节 |

**目录**：第一部分三节解剖三个仓库 → 第二部分三节讲一致性与区别 → 第三部分两节讲实跑与未知 → 第四部分五节是实践 → 收尾两节是参考与总结。

---

# 第一部分 · 逐仓库解剖

## 1. `tesla-open-can-mod`：最干净的教学样本

选它当第一个解剖对象有两个理由：三个变体里它的代码最工整、抽象层划得清楚；而且它能回答一个问题——所谓"操作序列"到底写在代码的哪里。

### 1.1 地图：七个文件

去掉许可证与图片，真正有信息量的文件是这七个（行数为本地副本实测）：

| 文件 | 行数 | 承担什么 |
| --- | --- | --- |
| `RP2040CAN.ino` | 62 | Arduino 入口：选板子、选车型、转发到 `app.h` |
| `src/main.cpp` | 45 | PlatformIO 入口，与 `.ino` 等价 |
| `include/app.h` | 63 | **第一、二层序列**：`appSetup()` 与 `appLoop()` |
| `include/handlers.h` | 177 | **第三层序列**：三个 handler 的 `handleMessage()` |
| `include/can_helpers.h` | 27 | 四个位操作原语 |
| `include/can_frame_types.h` | 10 | 可移植的 `CanFrame` 结构 |
| `include/drivers/*.h` | 5 个文件 | 四个驱动实现 + 一个抽象接口 |

这个分工本身就是设计：**车辆逻辑全部集中在 `handlers.h` 和 `app.h`，入口文件只做选型转发。** 换板子改 `platformio.ini`，换车型改一行宏，业务逻辑一行不动。

![三层序列的位置与分工](images/can-mod-teardown-2026/s01-three-layers.svg)

图 1｜三层序列各自住在哪个文件、由谁触发。

### 1.2 第一层序列：启动

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

handler 必须先于驱动建立，因为 `setFilters()` 那一行要从 handler 拿过滤器清单——**"听哪些 ID"的决定权因此在业务层**，驱动不知道自己在听什么，只负责执行。过滤器装在硬件层：控制器只把匹配的 ID 上报给 CPU，其余帧在芯片里就被丢了，车身总线每秒几百帧，全进中断会把主循环淹掉。

最后那句 `if constexpr` 是 C++17 的编译期分支，条件不成立的分支根本不被实例化——不支持中断的驱动，连 `frameReady` 检查的机器码都不会生成。

一个容易看漏的细节在 `app.h:26`：

```cpp
static volatile bool frameReady = true;
```

初值是 `true`。所以第一圈循环**无论有没有中断都会进一次**。这个设计让"等第一帧"变成无等待，代价是第一圈可能空转一次 `while(read)`。

### 1.3 第二层序列：运行

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

二十行，两处设计值得停一下。

`while(read)` 用的是排空模式。中断只是个"有活了"的信号，真正的读取靠主循环连续调用 `read()` 直到队列空。这样 ISR 只做一件事——置位一个布尔——耗时极短。

`volatile` 不是可选的：`frameReady` 由 ISR 写、主循环读，没有它编译器可能把它缓存在寄存器里，主循环永远看不到中断的写入。

### 1.4 第三层序列：业务与多路复用

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

`filterIds()` 和 `handleMessage()` 是一对：**同一个类既声明听什么，又实现听到了怎么办。** 过滤器和处理逻辑因此在代码上强制对齐，改一处不会漏另一处。

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

`using SelectedHandler = ...` 是**类型别名**，不是运行时变量——选型在编译期完成，运行时不存在"判断当前是哪款车"的分支，代价是每种车配每种板子都要单独编译。

**多路复用：一条 ID 三组语义。** 以 `HW3Handler` 为样本（`handlers.h:84-116`），ID 1021 上的处理按 `data[0]` 低 3 位分成三支：

```cpp
if (frame.id == 1021) {
    auto index = readMuxID(frame);
    if (index == 0) FSDEnabled = isFSDSelectedInUI(frame);
    if (index == 0 && FSDEnabled) {
        speedOffset = std::max(std::min(((uint8_t)((frame.data[3] >> 1) & 0x3F) - 30) * 5, 100), 0);
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

（引文删去了速度档 `switch` 与其后的 `#ifndef NATIVE_BUILD` 串口打印块，其余逐字对应 `handlers.h:84-116`。）

**mux 0 刷新状态，mux 2 应用缓存，mux 1 完全不理会缓存。** mux 2 那支带着 `&& FSDEnabled`，用 mux 0 存下的值；mux 1 那支**根本没引用 `FSDEnabled`**——收到 mux 1 帧就改比特回发。

这不是笔误，下一节会看到它被测试钉住了。三个 handler 的 mux 1 分支都这么写，但**三者的 mux 2 不一致**：HW3 检查缓存（`handlers.h:104`），HW4 不检查（`:165` 是光秃秃的 `if (index == 2)`），Legacy 没有 mux 2 这一支。

### 1.5 横切面一：位操作与读改写纪律

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

**`setSpeedProfileV12V13` 是读改写的纪律示范。** 掩码 `~0x06` 保留字节里其他位，只动自己该动的两比特。误伤相邻字段是这类工具最常见的 bug，掩码写法从结构上堵死了它。

**`setBit` 用绝对位号寻址。** `bit / 8` 定位字节、`bit % 8` 定位位内偏移——这解释了代码里为什么会出现 19、46、47、59、60 这些魔数：**DBC 的"起始位 + 长度"语义在这一层已被手工展开成绝对位号**（第 4 节第一条）。

### 1.6 一处被回归测试钉死的耦合

上一节那个"mux 2 复用 mux 0 缓存"的行为值得单独看，因为**它曾是个 bug**。

`test/test_native_hw3/test_hw3_handler.cpp:50` 的注释直接写着 `// --- FSD shadowing fix regression test ---`，测试本体在同文件 52-68 行：

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

"shadowing" 点出了原 bug 的性质：**mux 2 的帧自己带了一个 `data[4]`，早期实现若在每个分支重读 UI 位，这帧会把 mux 0 刚存下的状态覆盖掉**——语义上叫变量遮蔽。

修复方式是让读取只发生在 mux 0，并用回归测试锁死这个行为。HW4 那边有一份孪生测试（`test_native_hw4/test_hw4_handler.cpp:56`，注释同样写着 `FSD shadowing fix regression test`）。

![状态缓存的时序耦合](images/can-mod-teardown-2026/s02-state-latch.svg)

图 2｜mux 0 写入状态、mux 2 复用状态，mux 1 两者都不做。

**这件事的价值不在修复本身，而在于它展示了这个项目的成熟度**：发现隐式耦合 → 加测试锁死 → 把修复意图写进测试名。要说这类项目凭什么"值得读"，这就是具体证据。

### 1.7 横切面二：校验和，HW4 独有的一支

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

改了前 7 字节就必须重算第 8 字节，否则接收方校验失败、整帧被丢——丢帧在总线上表现成"偶发不生效"，排查极痛苦。校验和里还掺了 ID 的高低字节，让校验覆盖"这是哪条报文"，防止帧被换到别的 ID 上仍能通过。

末尾那个 `return` 提前退出，改完这帧就不再走后面的 FSD 逻辑。测试 `test_hw4_isa_suppress_returns_early_no_further_processing`（`test_hw4_handler.cpp:214`）专门断言了"只有一次发送"。

这个开关默认关，`handlers.h:14`：`constexpr bool DEFAULT_ISA_SPEED_CHIME_SUPPRESS = false;`——**需要显式改这个常量才启用**，是我在三个仓库里唯一一处"能力默认关闭且写死在编译期"。同文件 `handlers.h:13` 的 `enableEmergencyVehicleDetection = true` 则默认开启，两者对照。

### 1.8 横切面三：驱动抽象与过滤器掩码

`include/drivers/can_driver.h` 全文 12 行，接口就是 `init` / `setFilters` / `enableInterrupt` / `read` / `send` 五个纯虚方法加一个虚析构。

四个实现各自带一个 `kSupportsISR` 编译期常量：`MCP2515Driver`（SPI 外置）为 **true**，其余三个全是 false——**只有 SPI 外置控制器用中断，三个内置控制器全部走轮询**，理由留在 `same51_driver.h:35-37` 与 `twai_driver.h:53-56` 的注释里（寄存器读取无 SPI 开销、FreeRTOS 队列窥视不值得开专用任务），**是权衡后选了另一边，不是省事**。另外 `TWAIDriver`（`twai_driver.h:59-94`）在 `read()` / `send()` 失败时检查 `isBusOff()` 并 `recover()`——**总线错误累积到阈值会进 bus-off，不主动恢复就永久失联**，四个驱动里只有它实现了自恢复。

**过滤器掩码的数学。** MCP2515 有 6 个独立精确匹配槽位，TWAI 和 SAME51 **只有一个组合滤波器**，单滤波器要接受多个 ID 就得算掩码（`twai_driver.h:30-43`）：

```cpp
// Compute combined mask: bits that differ between any pair of IDs
// are "don't care" in the acceptance mask.
uint32_t differ = 0;
for (uint8_t i = 1; i < count; i++) {
    differ |= ids[0] ^ ids[i];
}
uint32_t base = ids[0] & ~differ;
f_config_.acceptance_code = base << 21;
f_config_.acceptance_mask = (differ << 21) | 0x001FFFFF;
```

逻辑是**任意两个 ID 异或，不同的位就是"不关心"位**；并起来当掩码，剩下的位必须匹配第一个 ID。副作用是**掩码越宽、接受的 ID 越多**——Legacy 的两个 ID（69 和 1006）差得远，掩码会放过一堆无关 ID，测试文件自己承认（`test_native_twai/test_twai_filter.cpp:118`：`// --- Legacy: wide gap means wider mask (false positives expected) ---`）。**这不是疏忽，是单滤波器的固有代价**：正确性由软件保证，`handleMessage()` 每支都先 `if (frame.id == ...)` 精确比对。**硬件过滤只负责省电省中断，不负责语义正确。**

### 1.9 测试：83 个断言

五组测试，我逐个 `RUN_TEST` 数过，后来**实际执行**并 83/83 通过：

| 测试组 | 断言数 | 覆盖对象 |
| --- | --- | --- |
| `test_native_helpers` | 18 | 四个位操作原语 |
| `test_native_legacy` | 12 | LegacyHandler |
| `test_native_hw3` | 13 | HW3Handler |
| `test_native_hw4` | 23 | HW4Handler（含 ISA 校验和） |
| `test_native_twai` | 17 | TWAI 过滤器掩码数学 |
| **合计** | **83** | |

`platformio.ini:29-32` 把它们跑在主机上，不碰硬件：`platform = native`、`build_flags = -std=c++17 -DNATIVE_BUILD`、`test_filter = test_native_*`。

`-DNATIVE_BUILD` 是关键开关：`app.h:9-11` 与 `handlers.h:9-11` 都用它隔离 Arduino 头文件。**同一份业务代码既能编译进 MCU，也能编译进主机当纯逻辑跑**——这是整个测试体系成立的前提。测试靠 `MockDriver` 捕获发送：`send()` 不上总线，只 `sent.push_back(frame)`，于是断言发送次数与帧内容变成可能。

### 1.10 门控：有什么，没什么

把仓库里所有"防止乱发帧"的机制列一遍：

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

**把安全约束放在编译期与默认值上，而不是运行时**——这是它的取舍：好处是零开销、配错根本编译不过，坏处是**运行时没有任何东西能拦住一次"配置正确但时机不对"的发送**。第 4、5 节会看到另外两个仓库各有一道它没有的闸。

顺带一提：**mux 1 分支不看 `FSDEnabled` 缓存，三个 handler 都是**——那一支的发送条件只有"收到 mux 1 帧"一条。是不是作者有意为之，源码没写，测试倒是断言了这个行为（`test_hw3_handler.cpp:126-131`）。我记下来，不替作者解释。

## 2. `flipper-tesla-fsd`：整个生态的重心

> **本节行号钉在 `ffbb24e`（`v2.16-beta.34`，2026-10-01 的 HEAD）。** 上一版钉的 `6a3404f`（beta.33）在我重写当天又被四个提交追过，全部发生在 2026-10-01：`esp32/.firmware/main.cpp` **+25 行**、`fsd_handler.cpp` 局部 **−1 行**。所以 `main.cpp` 里 nag killer 与预空那两处调用点从 `:1331`、`:1747` 漂到了 **`:1356`、`:1772`**，`fsd_handler.cpp` 的 ISA 分支从 `:453-460` 漂到 **`:452-459`**。`fsd_logic/fsd_handler.c` 一个字节没动，1344 行照旧。

### 2.1 地图：一棵树，两份业务层，一套共享原语

| 位置 | 规模 | 职责 |
| --- | --- | --- |
| `fsd_logic/fsd_handler.c` | 58.7 KB，**1344 行 / 64 个函数** | 协议核心（C 版） |
| `esp32/.firmware/fsd_handler.cpp` | 1110 行 | **同一套业务的 ESP32 版（C++）** |
| `esp32/.firmware/main.cpp` | 1963 行 | 接收分发与运行时 |
| `fsd_logic/fsd_state.h` | `:23` → `:365` | 状态，**一个 343 行的 struct** |
| `fsd_logic/fsd_checksum.h`、`fsd_can_ops.h` | 33 行、63 行 | 两个平台共用的无状态原语 |
| `test/` | `test_fsd_core.c` 127.6 KB、`test_esp32_core.cpp` 31.9 KB | 宿主测试 |

第一个要看清的结构事实：**业务层有两份。** `esp32/.firmware/fsd_handler.cpp:14-16` 的三条 include 把边界写得很明白：

```cpp
#include "../../fsd_logic/fsd_checksum.h"  // shared Tesla additive checksum (single impl, both platforms)
#include "../../fsd_logic/fsd_can_ops.h"   // shared stateless frame primitives (set_bit / mux / fsd-selected)
#include "../../fsd_logic/fsd_ota.h"       // shared 0x318 OTA-install detection (flag vs rolling counter)
```

共享的是**无状态原语**；**判断逻辑各写一遍**：`fsd_handle_autopilot_frame` 在 C 版是 `fsd_handler.c:191`、在 C++ 版是 `fsd_handler.cpp:265`，`fsd_detect_hw_version` 分别在 `:98` 与 `:123`。

直接后果是**同一个 bug 要在两处各修一次**，而两处的测试是分开的：`test_fsd_core` 编 `.c`，`test_esp32_core` 编 `.cpp`。第 7 节那 827 条正是这么来的——**648 条打 C 版，179 条打 C++ 版，没有一条同时覆盖两者**。

### 2.2 第一层序列：启动

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

与第 1.2 节的 `appSetup()` 对照，形状完全不同：那边是**硬件初始化序列**，这边硬件初始化在平台层的 `main.cpp`，**这一层只剩状态初始化**。三处细节：

- `memset` 先清零，再**只把有默认值的字段写出来**，其余全靠零值语义。
- `das_hands_on_state = 0xFF` 是**"未见过"哨兵**。`:1262` 的注释写明 `0xFF = no DAS frame seen yet — echo conservatively as fallback`；用 0 就会被当成 `NOT_REQD`（`das == 0` 在 `:1269` 直接 return），门控语义整个反过来。
- `gtw_autopilot_tier = -1` 同理，用 −1 区分"没读到"和"第 0 档"。

**哨兵值是这个状态机最容易被改坏的地方**，而它在初始化里就定死了。

### 2.3 第二层序列：运行

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

**先记录、后判断**，6 和 7 都提前 `return`，这两类帧不进业务层；第 1.4 节那家没有这个结构，装好过滤器后命中帧一律直接进 `handleMessage()`。

**并发。** 第 1.3 节 `appLoop()` 用 `volatile` 解决可见性问题，这里做法更重（`main.cpp:71-72`，`state_exit()` 在 `:75`）：

```cpp
static void state_enter() {
    portENTER_CRITICAL(&g_state_mux);
```

每次读写 `g_state` 前后进出临界区。**代价是关中断，收益是状态从"单字段可见"变成"整体一致"**——`fsd_state.h` 那 343 行是一个 struct，要么全看见、要么全看不见。

**发送许可：一个函数，三道条件，五处调用。** `fsd_logic/fsd_handler.c:41-48`：

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

`main.cpp` 里**每一条会发帧的路径**都要先问它一次：`:287`（挡位序列）、`:876`、`:1276`、`:1356`（nag killer）、`:1772`（预空调用）。

这是第 1.10 节那张门控表最缺的实据：**`tesla-open-can-mod` 里不存在这样一个函数**，它的发送许可全在编译期宏里。注释里 `Not overridable by ignore_ota` 还说明这个门是**分层**的——`ignore_ota` 能开的洞，Autopark 那层不给开。

### 2.4 第三层序列：业务，四道门在改任何比特之前

`fsd_logic/fsd_handler.c:191-208`，我按原文分行号贴：

```c
bool fsd_handle_autopilot_frame(FSDState* state, CANFRAME* frame, uint32_t now_ms) {
    if(frame->data_lenght < 8) return false;

    if(!fsd_ap_first_allows(state, now_ms)) return false;   // :197
    if(!fsd_soft_engage_allows(state)) return false;        // :200
    if(!fsd_abort_guard_allows(state)) return false;        // :203
    if(state->ap_first_minimal && state->ap_inject_count >= AP_MINIMAL_INJECT_FRAMES)
        return false;                                        // :207
```

四道门各管一件事：AP 是否真的接合且稳定、方向盘是否回正、本次接合是否进过 abort、注入预算花完没有。**三道是 2026.14.x 之后才加的**，注释挂着 issue 号（`#108`、`#100`），`:194-196` 还关联 `ev-open-can-tools#66 / v3.0.2-beta.2` 的一次转向顿挫。第 1.10 节那张门控清单里，这四种一个都没有。

过了门才是 mux 分发（`:210-214`）：

```c
uint8_t mux = fsd_read_mux_id(frame);
bool fsd_ui = fsd_is_selected_in_ui(frame, state->force_fsd);
bool modified = false;

if(mux == 0) state->fsd_enabled = fsd_ui;
```

随后按硬件代际分两支，形状与第 1.4 节三个 handler 的分支一致：

| | HW3（`:228-274`） | HW4（`:275-324`） |
| --- | --- | --- |
| mux 0 | 算速度偏移 → `set_bit(frame, 46, true)`，写 byte6 速度档 | `set_bit(46)` + `set_bit(60)`，可选 `set_bit(59)` |
| mux 1 | 清 bit19，一串开关逐个写 48/50/47/46/…（`:241-267`） | 同一串开关（`:285-310`） |
| mux 2 | `if(mux == 2 && state->fsd_enabled)`（`:268`） | `if(mux == 2)`（`:311`） |

**第三行是一个跨仓库的同构。** 第 1.4 节记过：`tesla-open-can-mod` 的 HW3 mux 2 检查缓存（`handlers.h:104`），HW4 那支是"光秃秃的 `if (index == 2)`"（`:165`）。flipper 这里**一模一样**——HW3 那支要 `state->fsd_enabled`，HW4 不要。两个仓库、两套语言、同样的不对称，不像巧合，更像一份沿用了另一份的帧布局语义。**我没有证据指认方向**，只记下形态。

第二行的 bit47 走过一段路，见第 2.7 节。

### 2.5 nag killer：独立一支，且有自己的门

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

`:1251-1254` 的注释把一次历史修改钉住了：原来的守卫写成 `hands_on != 0` 就跳过，**结果把 level 3（升级告警）也一起跳过了**，改成"只在 level 1 时跳过"。**门控条件写反导致功能静默失效**的实例，被注释固定下来。

发出去的帧是**整帧回读再改**，不是凭空造（`:1320-1339`）：

```c
out->buffer[4] = (frame->buffer[4] & ~0xC0u) | 0x40u;   // 清掉 7:6 再置 level=1
...
uint8_t cnt = (frame->buffer[6] & 0x0F);
cnt = (cnt + 1) & 0x0F;
out->buffer[6] = (frame->buffer[6] & 0xF0) | cnt;        // counter + 1
```

`:1329` 的注释解释了为什么要先清：`OR-ing 0x40 without clearing leaves level=3 unchanged on escalated frames`——**不先掩码就 OR，升级帧上 level 仍是 3**。这与第 1.5 节 `setBit` 的"写绝对位号"是同一个问题的两种处理：带读-改-写语义的位操作忘了掩码，就会静默失效。

末尾重算校验和（`:1339`）：

```c
out->buffer[7] = tesla_additive_checksum(CAN_ID_EPAS_STATUS, out->buffer, 7);
```

### 2.6 横切面：与第 1 节是同一套词汇

**位操作。** `fsd_handler.c:85-87` 只有一行转发 `tesla_set_bit(frame->buffer, bit, value)`，实现在 `fsd_logic/fsd_can_ops.h:19`，两个平台共用。**第 1.5 节那四个原语在这里被压成一个带 `value` 参数的函数**——语义等价，词汇量少一半。头文件那行注释叫它 `shared stateless frame primitives`，**"无状态"就是这个抽象的全部要点**。

**校验和。** `fsd_logic/fsd_checksum.h:28` 的 `tesla_additive_checksum(can_id, data, len)`：ISA / track / nag 放 byte 7、SCCM 左 CRC 放 byte 0（用法注释在 `:22-23`）。ISA 那一支（`fsd_handler.c:391-396`）与第 1.7 节逐句对得上，`CAN_ID_ISA_SPEED` 就是 `0x399`——**`921 == 0x399`**。差别只在封装：那边把循环内联进 handler，这边抽成 `static inline` 放共享头，ESP32 版还把字节位换成命名常量 `SIG_ISA_SOUND_ACTIVE_BYTE` / `_MASK`（`fsd_handler.cpp:452-459`）。

**这是收敛还是抄袭，我判定不了。** flipper 在别处会署名——`fsd_handler.c:50` 写着 `BMS read-only parsers (CAN frame templates from tuncasoftbildik/tesla-can-mod)`，多处注释指向 `ev-open-can-tools`——**这一支却没有署名**。我只能把行号并排放着，方向不猜。

（"只在自己起头发的帧上重算校验和"这个共同点，见第 4 节第二条。）

### 2.7 一句结论只活了 24 小时：bit47 的两次改口

**这是全文最能说明"行号与结论都必须钉死在版本上"的一段。**

`bit47` 是 EU Summon 的开关位，在四个版本上被改过三次：

| 版本 | 状态 | 备注 |
| --- | --- | --- |
| `19ef738`（beta.29） | C 版 HW4 **无条件**置位，头顶一段自陈坦白注释：`// HW4 sets bit47 (summon enable) unconditionally here (pre-existing), so the summon_unlock toggle is effectively always-on for HW4 on this build. ... Reconciling this divergence is a follow-up.` | 本次钉出的原文 |
| `6a3404f`（beta.33，2026-09-30） | follow-up 做完：`:294-296` 变成 `if(state->summon_unlock) { fsd_set_bit(frame, 47, true); }`，坦白注释删掉，与 HW3 的 `:251-253` 对称 | 相隔 24 个提交，一个自陈的 TODO 归零 |
| `ffbb24e`（beta.34，2026-10-01） | C 版**没动**；改的是 ESP32 版：`esp32/.firmware/fsd_handler.cpp` 的 nag killer 分支**删掉了** `set_bit(frame, SIG_AP_HW4_NAG_CONFIRM_BIT, true); // HW4 nag-suppression confirmation bit` 这一行 | 本次重写新查 |

beta.34 的 `changelog.md` 开头就把理由写明白了（我逐字抄）：

> **ESP32: the nag killer no longer sets 0x3FD bit47 on HW4.** bit47 is the Summon-enable bit (confirmed on-car in #163), not part of nag suppression — the nag killer works through the bit19 clear and the 0x370 EPAS echo. ... The misnamed constant is renamed to SIG_AP_SUMMON_ENABLE_BIT. No change to nag behaviour.

于是 `esp32/.firmware/can_signals.h:44` 从 `#define SIG_AP_HW4_NAG_CONFIRM_BIT 47` 变成 `#define SIG_AP_SUMMON_ENABLE_BIT 47`——**一个常量名骗了所有人：它叫"Nag 确认位"，其实是"Summon 使能位"。** 同一提交还加了 `config.h:165` 的 `SUMMON_DISABLE_SPEED_KPH 3.0f`，让 Summon 在车速超 3 km/h 时自动撤销（`main.cpp:1307-1321` 的 0x257 速度分支）。

这段的教训不是技术的：**如果我只写"bit47 常开"，这句话在上游 HEAD 上已经是错的；如果我只写"beta.33 修好了"，第二天它又错了。**

## 3. `ev-open-can-tools`：最像平台的一个

这一节补齐源码阅读，方法与前两节一致。

> **本节行号钉在 `6d37392`（`v4.0.0-beta.3`，2026-09-20），也就是 `dev` 分支。** 默认分支 `main` 停在 `338d276`（2026-08-05），两者在 `447049d` 分叉。我先 clone 到的是 `main`，读到一半才发现 tag 不在那条线上，重新建了 worktree 按 `dev` 推行号——两线在 `app.h`、`handlers.h`、`can_driver.h`、`main.cpp` 上都动过，`app.h` 的发送许可从 `:110`/`:295` 漂到 `:113`/`:324`。**下文全部是 `dev` 的行号。**

### 3.1 地图

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

### 3.2 第一层序列：启动

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

与前两节对照，**启动序列里多了两样它们没有的东西**：`nvs_flash_init()` 的失败自愈（无空闲页或版本不匹配就擦掉重来），以及主循环的**三层 `catch`**——`std::bad_alloc`、`std::exception`、`...` 各自兜住再继续。前两个仓库的主循环没有异常边界。

`app_main_setup()`（`src/main.cpp:84`）按驱动宏分四支，每支固定两步——`appPrepare<T>()` 再 `appStartDriver<T>()`。TWAI 那支的注释是关键：**`// Load TWAI pins from NVS (survives OTA); fall back to compile-time defaults`——引脚从 NVS 读、OTA 之后不丢、编译期宏只是兜底**，前两个仓库的引脚全在编译期。

车型选型在 `include/app.h:32-51`，比第 1.4 节多出两级：

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

**五个 handler，四条选型路径。** `ESP32_DASHBOARD` 那一支最值得看：`DASH_DEFAULT_HW` 是一个数值宏，网页面板构建时它优先于 `HW4`/`HW3`，因为网页要在运行时显示默认值。

### 3.3 第二层序列：运行

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

**OTA 更新进行中，整个主循环直接停掉。** 这比第 2.3 节 flipper 的做法硬：flipper 是在 `fsd_can_transmit()` 里拒绝发送（`state->tesla_ota_in_progress`），业务层照常跑；这里是**连读帧都不读**。

然后是排空读取与广播：

```cpp
    CanFrame frame;
    uint8_t framesThisLoop = 0;
    while (appDriver->read(frame))
    {
        ...
        CanFrame original = frame;
#ifdef ESP_PLATFORM
        GvretSerial::broadcast(original);      // app.h:426-429
#endif
        {
            AppHandlerGuard guard;
            CarManagerBase *h = appGetActiveHandler();
            if (!h)
                h = appHandler.get();
            if (h)
                ...
```

**先广播给上位机，再交给业务层**——GVRET 是一套上位机协议，PC 端工具靠它看到原始帧。前两个仓库没有这个旁路。

### 3.4 第三层序列：业务

接口在 `include/handlers.h:346-350`，与第 1.4 节 `tesla-open-can-mod` 的 `CarManagerBase` **逐字相同**（除了类型名）：

```cpp
    virtual void handleMessage(CanFrame &frame, CanDriver &driver) = 0;
    virtual const uint32_t *filterIds() const = 0;
    virtual uint8_t filterIdCount() const = 0;
    virtual ~CarManagerBase() = default;
};
```

五个派生类：`LegacyHandler`（`:352`）、`HW3Handler`（`:480`）、`HW4Handler`（`:691`）、`NagHandler`（`:1000`），外加 `SummonUnlockHandler`。**"同一个类既声明听什么、又实现听到了怎么办"这个设计，三个仓库里有两个在用**，而且连 `filterIds` 这个方法名都一样。

`LegacyHandler` 的过滤清单（`:356`）比第 1.4 节宽得多：

```cpp
        static constexpr uint32_t ids[] = {69, 280, 390, 599, 921, 1006, 1016};
```

7 个 ID，对比 `tesla-open-can-mod` 的 2 个。**听得多，是因为它还要负责仪表、BMS、诊断这些只读功能**——第 5 节的功能面对比会回到这一点。

### 3.5 横切面：同三个原语，多一道边界

**位操作**，`include/can_helpers.h:216-230`：

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

`bit / 8`、`bit % 8`、掩码读改写——**与第 1.5 节逐行同构**。唯一多出来的是开头那道边界守卫：**`bit` 越界直接返回，不越界写。** 另外两个仓库的 `setBit` 都没有这一行，越界会直接写到 `data[]` 之外。

**校验和**，`include/can_helpers.h:199-214` 的 `computeVehicleChecksum(frame, checksumByteIndex = 7)`：ID 高低字节 + 数据字节累加（跳过校验字节自己）取低 8 位，外加一处 `dlc` 边界判断。**同一个算法**——与第 1.7 节那段内联循环是同一段数学，只是抽成函数、累加顺序反过来。三个仓库，三种封装，一个算法。

**驱动接口**，`include/drivers/can_driver.h:7-47`。纯虚方法与第 1.8 节完全一致（`init` / `setFilters` / `enableInterrupt` / `read` / `send`），但**多了两个回调指针和一个许可函数**：

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

**这就是第 1.10 节那个"不存在的东西"，在这里以接口成员的形式存在。** 实现在 `app.h:113-127`，`app.h:324` 装进驱动（`appDriver->allowSendFrame = appCanTransmitAllowed;`）。前两道问 `appInjectionReady()` 和 `summonOnlyInjectionRuntime`，第三道向 handler 要 `summonOnlyInjectionDecisionAt()` 的裁决。

**这是三个仓库里把发送许可放在最靠近硬件位置的一个**——业务层根本没法绕过它。三者的对比见第 5 节维度二。

### 3.6 我实测到的两处真故障

**一、`plugin_engine.h:747` 的 `strlcpy` 编不过。** 我在 `main` 上跑 native 测试时，`native_plugin_engine` 直接编译失败：

```
include/plugin_engine.h:747:5: error: 'strlcpy' was not declared in this scope; did you mean 'strncpy'?
```

原文在 `dev` 上**一模一样，一个字节没改**：

```cpp
    strlcpy(out.name, name, sizeof(out.name));        // :747
    strlcpy(out.version, version, sizeof(out.version)); // :748
    strlcpy(out.author, author, sizeof(out.author));    // :749
```

`strlcpy` 是 BSD/newlib 函数，ESP-IDF 里有，本机的 MinGW g++ 没有；Linux 上 glibc 2.38 之后也有。**所以这大概率是平台相关的**——但在我这台 Windows 上，它的 native 套件只能过 7/9。**从 `main` 到 `v4.0.0-beta.3` 跨了 17 天、14 个提交，这处没修。**

**二、`scripts/minify_dashboard.py` 在中文 Windows 上撞 GBK。** 报错 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa6`——脚本 `open()` 不带 `encoding=`，本机默认编码是 GBK。`set PYTHONUTF8=1` 可绕过。这类问题 README 里不可能写，只能撞一次记一次。

**ev-open 对版本与车型的记载也几乎是空的**（与第 8 节那张三仓表同源）：`2026.2.11` 全仓 0 处、`X179` 0 处；`HW4` 有 224 处——支持很扎实，只是没落到那个具体 OTA 版本。

---

# 第二部分 · 一致性与区别

三份源码读完了。先看它们**在哪一层其实是一份东西**，再看它们**在哪一层已经分化成三个不同的工具**——这一部分不重复第一节的行号，只做对照。

## 4. 一致：同一个骨架

把三份源码的启动、运行、业务三层摆齐，会看到一张几乎能互相覆盖的表：

| 层 | `tesla-open-can-mod` | `flipper-tesla-fsd` | `ev-open-can-tools` |
| --- | --- | --- | --- |
| **选型** | `app.h:13-21` 编译期 `#if` | 菜单运行时选（`fsd_state.h` 存 `hw_version`） | `app.h:32-51` 编译期 `#if`，面板构建时另有 `DASH_DEFAULT_HW` |
| **驱动接口** | `drivers/can_driver.h` 12 行纯虚 | 平台层各写各的 | `drivers/can_driver.h:7-47` 纯虚 + 两个回调 |
| **启动** | `appSetup()`：串口 → 驱动 → 过滤器 → 中断 | `fsd_state_init()`：只清状态，硬件在 `main.cpp` | `app_main_setup()`：NVS → 驱动 → 启动 |
| **运行** | `appLoop()` `while(read)` 排空 | `main.cpp` 六步：记录 → 丢弃 → 识别 → OTA → 嗅探 → 分发 | `appLoop()`：OTA 闸 → 排空 → 广播 → 分发 |
| **业务接口** | `CarManagerBase` 纯虚三方法 | `fsd_handle_autopilot_frame()` 函数式 | `CarManagerBase` 纯虚三方法 |
| **监听清单** | `filterIds()` 与 `handleMessage()` 同类绑定 | `fsd_can_rx_handler()` 表驱动 | `filterIds()` 与 `handleMessage()` 同类绑定 |
| **位操作** | `can_helpers.h:14-27` `setBit(bit/8, bit%8)` | `fsd_can_ops.h:19` `tesla_set_bit` | `can_helpers.h:216-230` `setBit(bit/8, bit%8)` |
| **校验和** | `handlers.h:134` 内联循环 | `fsd_checksum.h:28` 函数 | `can_helpers.h:199-214` 函数 |
| **mux 语义** | `readMuxID()` = `data[0] & 0x07` | `fsd_read_mux_id()` | `readMuxID()` |

**五处一致性值得单说：**

**一、绝对位号寻址是三家共用的方言。** 三份源码里都是 `setBit(frame, 46, true)` 这种字面量位号，**没有任何一家的代码里存在 DBC 文件**——DBC 的"起始位 + 长度 + 字节序"在这层已被手工展开成绝对位号。魔数最容易互相对齐，也最容易集体出错。

**二、校验和只管自己起的头。** 三家都只在"自己是发送方"的帧上重算（`921`、`0x370`、track、ISA），"原地改 `0x3FD` 再回发"时都不重算——flipper 那 1344 行的 `fsd_handle_autopilot_frame` 里**一次 `tesla_additive_checksum` 都没有**。三家一致，说明不是疏忽。

**三、`tesla-open-can-mod` 与 `ev-open` 的业务接口逐字相同。** `CarManagerBase` 的三个纯虚方法名（`handleMessage` / `filterIds` / `filterIdCount`）一字不差——ev-open 的 README 明说它是从同族工具衍生的。

**四、HW3 查 mux 2 的状态缓存、HW4 不查，两个仓库一模一样。** 第 1.4 节 `handlers.h:104` 对 `:165`，第 2.4 节 `fsd_handler.c:268` 对 `:311`，同样的不对称，两边的测试也各自锁住了这个行为。

**五、"先清再置"的读改写纪律是三家共识。** 第 1.5 节的掩码、第 2.5 节 `:1329` 的 `OR-ing 0x40 without clearing leaves level=3 unchanged`、第 3.5 节 `setBit` 的 `~mask`——三处注释、三种写法、同一个教训：**忘了掩码，位操作会静默失效，方式是"看起来生效了一部分"。**

## 5. 区别：五条维度

差别比相似更能说明问题。同样三个仓库，五条维度上已经分得很开。

### 维度一：选型发生在哪一层

| | 方式 | 代价 |
| --- | --- | --- |
| `tesla-open-can-mod` | 编译期 `#if`，`#error` 兜底 | 每种板 × 每种车都要编一次；改错编译不过 |
| `flipper-tesla-fsd` | 运行时菜单，存进 `fsd_state.h` 的 `hw_version` | 一次烧录覆盖全部；选错要重新进菜单 |
| `ev-open-can-tools` | 编译期 `#if`，但**面板构建另有 `DASH_DEFAULT_HW` 数值宏**；TWAI 引脚从 NVS 读 | 四条选型路径并存，最复杂；引脚 OTA 不丢 |

三者没有优劣，但**代价的形态不同**：`tesla-open-can-mod` 把代价放在编译期（配错不让你过），flipper 放在运行时（选错要手工回退），ev-open 放在两条路径上（网页面板和固件各自决定）。

### 维度二：发送许可放在哪一层

这一条是三个仓库**分化最深**的地方：

| | 机制 | 位置 | 能否绕过 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | **不存在** | — | 业务层想发就发，只有编译期配置 |
| `flipper-tesla-fsd` | `fsd_can_transmit()` 三道条件 | `fsd_handler.c:41-48` | **业务层每条发送路径各调一次**（`:287` `:876` `:1276` `:1356` `:1772`）——容易漏 |
| `ev-open-can-tools` | `sendAllowed()` 回调 + `appCanTransmitAllowed()` | `drivers/can_driver.h:21-24`，实现在 `app.h:113-127`，`app.h:324` 挂进驱动 | **挂在驱动的回调上，业务层无法绕过** |

第 1.10 节我列过 `tesla-open-can-mod` 的门控清单，它缺一个统一发送许可。另外两个仓库的补法：**flipper 放在业务层每条路径上（靠自律），ev-open 放在驱动回调上（靠结构）**——后者更难写错。

`ev-open` 的许可函数只有两道：`appInjectionReady()` 不通过就 `false`，`summonOnlyInjectionRuntime` 关着就 `true`，否则问 handler 要 `summonOnlyInjectionDecisionAt()` 的裁决。flipper 那三道（Listen-Only / Autopark / OTA）ev-open 一条也没有，实现分在别处。

### 维度三：OTA 期间的行为

三个仓库对"OTA 进行中"的处理完全不在一个强度上：

- `tesla-open-can-mod`：**没有这个概念**，全仓 grep 无 OTA 检测。
- `flipper-tesla-fsd`：`fsd_can_transmit()` 第三道 `state->tesla_ota_in_progress` 返回 `false`——**只拦发送，业务层照常跑**，`main.cpp:1162-1168` 的 OTA 监监控帧还会提前 `return`。
- `ev-open-can-tools`：`app.h:391-395` `if (Update.isRunning()) { delay(1); return; }`——**整个主循环停掉，连帧都不读**。

同一句"OTA 进行中不要发帧"，三种实现的边界从"业务层自律"一路推到"运行时整体停摆"。**ev-open 最保守，也最不容易出错。**

### 维度四：功能面

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
| 测试 | 83 断言 | 827 断言（+ 10 个板级 env） | 17 套件 / 237 用例 |
| 代码规模 | 7 文件 / 177 行业务 | 1344 行业务 + 1110 行副本 | 1218 行业务 + 1641 行插件 |

**这个矩阵就是三个仓库的分野**：`tesla-open-can-mod` 是一个能跑通的最小实现，flipper 是一个带运行时治理的完整应用，ev-open 是一个带面板和插件的平台。**功能面越宽，需要读的源码越多；但功能面越窄，越容易一眼看全它到底发了什么。**

### 维度五：许可证与发布

| | 许可证（我打开 `LICENSE` 逐字看过） | 发布形态 | 末次提交 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | **GPL-3.0 全文**（35,145 B）+ `THIRD_PARTY_LICENSES` | 无 tag、无 release，直接 clone | 2026-04-02（**183 天没动**） |
| `flipper-tesla-fsd` | **GPL-3.0**——但 `LICENSE` 只有 **929 B**，是那段"如何套用本许可"的说明，不是许可全文 | `v2.16-beta.34`，tag 频繁 | **2026-10-01（当天）** |
| `ev-open-can-tools` | **GPL-3.0 全文**（35,819 B）+ `THIRD_PARTY_LICENSES` | `v4.0.0-beta.3` tag，`main` / `dev` 分叉 | `dev` 2026-09-20，`main` 2026-08-05 |

**许可证这一栏是三者唯一完全收敛的地方——三家都是 GPL-3.0。** 但中间那一格暴露了一个**方法陷阱**：GitHub 的 REST API 对 flipper 返回的 `license` 是 **`NOASSERTION`**，因为它的 `LICENSE` 只有 **929 B**、是那段"如何套用本许可"的说明而非许可全文。**任何只靠 API 做许可证清点的调研，都会把星最多的那个（1094★）报告成"许可证未声明"——而它明明白白写着 GPLv3。** 上一版我正是用 API 字段填的表，这一版改成打开文件读。

发布节奏的分化才是真差异：**`tesla-open-can-mod` 已经 183 天没动**，`flipper` 在我重写当天还在提交，`ev-open` 的默认分支比它的 tag 落后 14 个提交。**"这个仓库还活着吗"和"代码读起来怎么样"是两个独立问题，前一个往往更致命。**

## 6. 它在哪一层

把三个仓库放进同一张层图，位置就清楚了：

![三层定位：模型层、决策与执行层、总线层](images/can-mod-teardown-2026/s03-layer-positioning.svg)

图 3｜三层定位：模型层、决策与执行层、总线层。

它们**全部位于最下层**——直接对 CAN 总线收发帧，不参与感知、不参与规划、不决定"要往哪开"。**所谓"操作序列"的物理形态就是几组位掩码加一个时间窗口**，而非任何模型或决策层。

同一张图里 `tesla-open-can-mod` 最靠左（只有总线层），flipper 往上伸进决策与执行层（状态机、abort guard、策略裁决），ev-open 再往右伸一层（面板、插件、上位机协议）。**越往右上，读源码的收益越高——那里开始有"为什么这么做"而不只是"怎么做"。**

---

# 第三部分 · 我真跑了什么

数据全部按各自钉死的版本标注，报错原文按证据保留。

## 7. 实测汇总

**一、宿主测试（`native` / `platform = native`，不碰硬件）**

| 仓库 | 版本 | 套件 | 用例 | 结果 |
| --- | --- | --- | --- | --- |
| `tesla-open-can-mod`（上游） | `815e000` | 8 次套件运行（3 个 env） | 107 | **107 过 / 0 失败** |
| `tesla-open-can-mod`（本地副本） | `E:\` 快照 | 5 | 83 | **83 过 / 0 失败**（第 1.9 节那张表） |
| `JordanzhaoD/waveshare-single-can-firmware` | — | 19（PlatformIO native） | 650 | **650/650 全过** |
| `flipper-tesla-fsd` | `6a3404f`（beta.33） | 2（`test/Makefile`，gcc/g++ 直调，非 PlatformIO） | 827 | **827/827 全过**（648 C 版 + 179 C++ 版） |
| `ev-open-can-tools` | `338d276`（`main`） | 9（PlatformIO native） | 237 | **235 过 / 2 个套件编译失败** |
| **合计** | | | **1904** | **1902 过 / 2 个套件编译失败** |

上游比本地副本多出的 24 个用例来自两个新套件（`test_native_force_fsd`、`test_native_log_buffer`），本地副本连 `include/log_buffer.h` 都没有。**ev-open 那 2 个失败是真编译错误，根因就是第 3.6 节的 `strlcpy`**——`plugin_engine.h:747` 在 MinGW 下缺符号，同树另一个套件一起挂，**一个 bug 打掉两个套件**。

**我没有跑 `dev` 的测试**（那条线多出 `native_dev_sim`，共 21 env / 17 套件）——第 3 节行号按 `dev` 重推，测试数据仍标在 `main` 上，**两者不对应**。

**二、板级构建（`pio run -e <env>`，真的编固件）**

| 仓库 | 版本 | 实跑 env | 结果 |
| --- | --- | --- | --- |
| `tesla-open-can-mod` | `815e000` | `esp32_twai`、`m5stack-atomic-can-base`、`feather_m4_can`、`feather_rp2040_can` | **4/4 SUCCESS**（`esp32_twai` RAM 14.6% / Flash 61.7%，`feather_rp2040_can` 5.1% / 0.5%） |
| `JordanzhaoD` | — | `waveshare_single_can_standalone`（`esp32s3box`，16MB） | **SUCCESS**，RAM 15.3% / Flash 28.8% |
| `flipper-tesla-fsd` | `6a3404f`（beta.33） | `waveshare-s3-can` + 其余 9 个 | **10/10 SUCCESS**（`waveshare-s3-can` RAM 37.4% / Flash 28.0%） |
| `ev-open-can-tools` | `338d276`（`main`） | `waveshare_ESP32_S3_RS485_CAN`、`esp32_ext_mcp2515`、`esp32_twai` | **3/3 SUCCESS**（依次 RAM 21.9% / Flash 70.8%、22.0% / 35.9%、21.5% / 71.3%） |
| **合计** | | **18 次板级构建** | **18/18 SUCCESS** |

**四个 ESP32-S3 目标全部通过**，`TX=GPIO15`、`RX=GPIO16` 这组引脚是三个仓库各自独立给出的、交叉印证。**这是我能给的最强的"它能编译通过"的证据——不是读 README 说的，是链接器和 esptool 说的。**

**三、环境：Windows 11，2026-09-30 至 2026-10-01，PlatformIO Core 6.2.0，Python 3.12.10（`PYTHONUTF8=1`，否则 `minify_dashboard.py` 撞 GBK），主机编译器 MinGW-w64 GCC 16.2.0，代理 `http://127.0.0.1:10808`。**

**六条报错按性质分两组。A 组四条是 onboarding / 环境类，照做就能过：**

| 报错 | 出处 | 处理 |
| --- | --- | --- |
| `Missing platformio_profile.h` | `ev-open`、`JordanzhaoD` 共用同一套 onboarding | `copy platformio_profile.example.h platformio_profile.h` |
| `platformio_profile.h must enable exactly one driver define` | `JordanzhaoD`，示例默认解的是双 CAN 变体 | 双 CAN 的 env 要改成只解 `DRIVER_TWAI` |
| `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa6` | `ev-open` `scripts/minify_dashboard.py` | `set PYTHONUTF8=1` |
| `ModuleNotFoundError: No module named 'csscompressor'` / `'rjsmin'` | `JordanzhaoD` 网页压缩脚本没声明依赖 | `pip install csscompressor jsmin rjsmin` |

**B 组两条，是仓库或环境自己坏了，不是你操作错了。** 第一条是 `tesla-open-can-mod` 的死包名——**与第 11 节的 X179 矛盾、第 12 节的两处裂缝同类，都是文档/配置与现实对不上**：

```
*** UnknownPackageError: Could not find the package with 'autowp/MCP2515' requirements
GET .../v3/packages/autowp/library/MCP2515  →  404 NotFound
GET .../v3/search?query=autowp             →  autowp/autowp-mcp2515  v1.3.1
```

`platformio.ini:7` 改成 `autowp/autowp-mcp2515` 后 `feather_rp2040_can` 立刻通过。第二条是 `ev-open` 的源头级报错（完整解释见第 3.6 节）：

```
include/plugin_engine.h:747:5: error: 'strlcpy' was not declared in this scope; did you mean 'strncpy'?
-- native_plugin_engine:test_native_plugin_engine [ERRORED] --
```

`strlcpy` 是 BSD/newlib 函数，ESP-IDF 有、本机 MinGW g++ 没有，**大概率平台相关**（完整分析见第 3.6 节）——ev-open 的 9 个 native 套件我这台机器只能过 7 个。另有 `Got the unrecognized status code '403'` 一条，是我下载工具链时的网络问题，配本地代理后恢复，与仓库无关。

**我没有做的事：** 没有烧录（`--target upload` 一条未执行）、没有连车、没有验证任何一帧在真实总线上会被接受、没有跑 `dev` 的测试矩阵、没有对 flipper 的 `ffbb24e` 重跑（827 条在 `6a3404f` 上）。

**编译通过不等于能用。** 编译只证明语法、模板、链接成立，不证明任何 CAN 帧语义正确；1904 个断言断的是**开发者自己写的预期**——能证明"代码符合作者意图"，不能证明"作者的意图符合车端实际"。**因此本文关于"车会怎么反应"的句子仍是社区回报，第 8 节的结论一个字都不用改。**

## 8. 兼容性：一个诚实的未知

这是全文最需要说清楚的一节，因为它回答的问题我**无法**回答。

**问题：2025 款 Model 3（China HW4.0、OTA 2026.2.11）该编哪个宏？**

### 先给 grep 结果（可复现）

我对三个仓库的**全部**文本文件（`.md` / `.h` / `.c` / `.cpp` / `.ino` / `.ini` / `.py` / `.fam` / `.yml` / `.txt`）跑了三个关键字，扫描文件数分别是 31 / 117 / 103：

| 关键字 | `tesla-open-can-mod` | `flipper-tesla-fsd` | `ev-open-can-tools` |
| --- | --- | --- | --- |
| `2026.2.11` | **0** | **10** | **0** |
| `X179` | **17** | **104** | **0** |
| `China` | **0** | **51** | **1** |

**这张表本身就是一个结论**：只有 `flipper` 记录了你这个版本号，也只有它和 `tesla-open-can-mod` 讲 X179。`ev-open` 三项近乎全空——它讲 OBD-II 与板载端子，`China` 那唯一一条是 `include/can_helpers.h:163` 的注释。

### 但 flipper 那 10 处，没有一处是这台车

**10 处全部落在文档与 issue 模板里，源码文件（`.c` / `.cpp` / `.h` / `.ino`）零命中。** 这一点很重要：**文档记录版本，源码判断版本——而源码那半边不存在。** 你编 `HW4` 就是 `HW4`，编译期不看车、不看 OTA、不看地区。

其中真正有信息量的是两条，**都是 Model Y**，外加 `.github/ISSUE_TEMPLATE/bug_report.yml:37` 把它当作版本号的 `placeholder`（**被当成"典型的当前版本"写进了报障模板**）：

```
README.md:285   | Model Y 2023 (China, MIC) | HW3 | 2026.2.11 | Community | FSD (Force FSD mode) |
changelog.md:243 ... @Tikernel + @ViPiMP (positive compat data: Model Y Juniper HW4 2026.2.11 China, HW4 2026.8.3 Germany).
```

**同一个 `2026.2.11` 在同一份文档里同时挂着 HW3 和 HW4**——不同车型、不同年款可以停在同一个 OTA 版本上，这恰恰说明**版本号本身推不出硬件代际**。而 Model 3 这个车型，**两条里一条都没有**。

### 那文档呢？文档只差一点就答上了

`README.md:50`（本地副本，上游同位置）是全仓唯一一条带版本阈值的规则，我逐字抄：

> **Note:** HW4 vehicles on firmware **2026.2.9.X** are on **FSD v14**. However, versions on the **2026.8.X** branch are still on **FSD v13**. If your vehicle is running FSD v13 (including the 2026.8.X branch or anything older than 2026.2.9), compile with `HW3` even if your vehicle has HW4 hardware.

照这条规则推：`2026.2.11` 不早于 `2026.2.9`，也不在 `2026.8.X` 分支上，**所以该编 `HW4`**。推得出来，但有两处不舒服。

**一、`2026.2.11` 不等于 `2026.2.9.X`。** README 写的是**补丁位通配**（`2026.2.9.11`），你的版本号是**次版本位**（`2026.2.11`）。两者能不能对上，README 没说，源码里也没有解析器替你判断。

**二、同族阈值互相打架，而且 flipper 自己的兼容表压根没有这台车的位置。** 按 `ffbb24e` 读它 `README.md:278-293`，相关的四行：

| 出处 | 内容 |
| --- | --- |
| `tesla-open-can-mod` `README.md:50` | `2026.2.9.X` 起是 FSD v14；`2026.8.X` 仍是 v13，跑 v13 就编 `HW3` |
| `flipper` `README.md:286` | `\| Model 3/Y 2023+ \| HW4 \| **< 2026.2.9** \| ... \| FSD \|` |
| `flipper` `README.md:293` | `2026.8.6 HW4` → HW4 注入路径坏掉 → 用 Force HW3 |
| `flipper` `changelog.md:243` | `Model Y Juniper HW4 2026.2.11 China` 正面数据（车型是 Model Y） |

**叠起来看更难受**：flipper 唯一一条"Model 3 + HW4"的正面数据版本范围是 **`< 2026.2.9`**，这台车 `2026.2.11` **正好掉在范围外**；唯一一条"HW4 + 2026.2.11"的车型是 Model Y Juniper。**两个条件各有一条数据，没有一条同时覆盖两者的车型。**

外部项目的阈值还在流：`herrfrei`、`juamiso` 用 **2026.2.3** 作 FSDV14 分界，`jvanakker` 镜像标注 **2026.8.6 对 2026.2.9.x 及更高已失效**——**同一条分界线上两个版本号在流，同一个 `2026.2.9.x` 一边"正常支持"一边"已失效"**。未必矛盾（FSDV14 可能分批推），但对照着选宏的读者要吃下六个版本号的分歧。

**flipper 那三行我在 `ffbb24e` 上逐行读、可 grep 复现；其余三个按 URL 与页面日期记录、我没 clone 核验**，都是一线用户的单点回报，无第三方仲裁。

**两个结论要分开。可验证的**：三仓源码里没有版本→宏的映射（`2026.2.11` 在 flipper 的 10 处命中全在文档里，源码文件 0 处），文档里有规则和兼容矩阵，但**没有一条同时命中这台车的三个条件**——任何人重跑都能复现。**不可验证的**：**`2026.2.11` 该编哪个宏？** 我没有板子、线束、车，**无法验证**——这是第 0 节证据约定最后一行写的方法边界。

**因此本篇只写到"仓库的指南到此为止"**（第 13 节），不写"照这个编就能用"。

### 本地副本与上游的差异

第 1 节所有 `file:line` 对着 `E:\tesla-open-can-mod-main`。上游 `815e000` 的选型块在 `include/app.h:24`（本地 `:13-21`），**主要漂移就在 `app.h` 前几行**（上游多两行 `#include` 与一行注释），其余逐行对齐。

---

# 第四部分 · 一台具体配置的实践

前面三部分是通用的。从这一节起，所有判断挂在一个具体配置上：**China、HW4.0、2025 款 Model 3、软件版本 2026.2.11。**

## 9. 先把车钉死：这台车意味着什么

把四个词拆开，各自带出一条硬约束。

### 一、`HW4` 三个字，先排掉两个选项

第 1.7 节讲过，校验和是 HW4 独有的一支；第 1.4 节的表也列了，三个宏只有 `LEGACY` / `HW3` / `HW4`。所以配置里 HW4.0 这一项直接决定：**Legacy（HW1/HW2）那条路不相关**，选型时只需要在 HW3 与 HW4 之间确认，而答案已经由配置给出。

第 8 节已经把能查的都查了，结论是：**flipper 的兼容矩阵里，"Model 3 + HW4"那行的版本范围是 `< 2026.2.9`，这台车掉在外面**；唯一一条 `HW4 + 2026.2.11` 的正面数据是 Model Y Juniper。

### 二、2025 款 Model 3，第一件该确认的事是 OBD-II 口上是不是 CAN

`flipper` `HARDWARE.md:39`（`ffbb24e`）：

> **April 2024+ Juniper Model Y / refreshed Model 3 Highland (later builds)**: Tesla switched to **DoIP** (Diagnostic over IP) — the diagnostic port now carries 100 Mbps Ethernet, **not** CAN.

紧接着 `:38-42` 是一条 CAUTION，大意是**不要把基于 CAN 的 OBD-II 适配器或诊断仪接到 DoIP 口上**——电平不兼容，可能损坏车辆的诊断模块；2024+ 的车直接接 X179。

2025 款 Model 3 属于 Highland 改款后的批次，按这段描述**应当默认当作 DoIP 处理**，而不是先插上去试——这是仓库写在 CAUTION 里的判断顺序，不是我的推断。

同一节还留了一个限定，我照抄：DoIP 迁移的分类轴是**生产日期与地区，不是"改款与否"**；适用范围仓库自陈 **"not yet pinned down"**。

### 三、X179 的 pin→bus 映射不固定，而唯一的确定判据在车机里

`HARDWARE.md:98`：**"The X179 pin→bus map is NOT fixed across builds — verify it on your own car."** 至少存在四种电气配置，而且"按年款推断不可靠"。

仓库给的确定判据只有一条（`:104` 起）：**车机的 Service Mode → CAN Port 页面**，它按线束料号逐针列出所属总线。仓库举的例子是 harness `1933903-XX`（`:105`，Model Y Juniper RWD 2025，FW 2026.14.3）：`2/3 = Party`、`9/10 = Vehicle`、**`13/14 = Chassis（绿线），不是 "Bus 6"`**、`20 = GND`。

**那台是 Model Y，不是这台 Model 3。** 所以这一节落到你车上的第一步动作很具体：先打开 Service Mode 的 CAN Port，把针号记下来，再动线。

### 四、生产日期早于 SOP10，但早于 SOP10 不等于 pre-April-2024

`HARDWARE.md:225` 的 SOP 时间线里，**上海是 2026-03-25（SOP11）**，柏林 2026-04-01，奥斯汀 2025-12-04，弗里蒙特 2025-12-09。2025 年产的车在这条线之前，因此**不属于 post-SOP10 那一档**。

但 post-SOP10 排除掉，不等于就落在"pre-April 2024"那张表上——那张表要求的是 2021–2023 与 2024 早期批次。2025 年产的车落在 **post-April-2024 档**，而那一档的实测数据是单点（`:212`：**"This is a single empirical data point"**）：

| Pin | 柏林产 EU Model Y 实测（`HARDWARE.md:193-204`） |
| --- | --- |
| 9 / 10 | DoIP（以太网），**不是 CAN** |
| 12 / 13 | DoIP，**不是 CAN** |
| **18 / 19** | **Vehicle CAN，唯一可用的 CAN 对** |
| 15 | +12V（不变） |
| 26 | GND（不变） |

那台车是 `@0n3-70uch` 用**示波器**量的（issue `#52`，Berlin 产 pre-Juniper、post-April-2024 生产、FW 2026.14.3）。仓库自己给的三条安全建议（`:220` 起）：**接收发器前每一对都用示波器验一遍**；13/14 的 120Ω 检查不过就改试 18/19；+12V（15）与 GND（26）跨 SOP 稳定。**这三条我一条都没执行**——没有板子、没有线束、没有示波器。

### 五、把四个词合成一句话

> **这台车的选型前提：HW4 走 HW4 路径；OBD-II 口默认按 DoIP 处理、直接接 X179；X179 先开 Service Mode → CAN Port 记针号，再接线；版本 2026.2.11 上目前唯一的正面数据来自同代际、同地区、同版本但不同车型（Model Y）的社区回报。**

## 10. 选什么、买什么

### 先说推荐

**主方案：`hypery11/flipper-tesla-fsd` 的 `waveshare-s3-can`。** 三个理由，按可验证性递减：

1. **它是三家里唯一记录 `2026.2.11` 的**（10 处命中，另两家 0），而且 `HARDWARE.md` 对 DoIP / X179 / Service Mode 的记载最细（104 处 X179）。
2. **它的 ESP32 侧测试是原样编进测试的**（第 2.7 节），不是抽出的副本。
3. **它在我重写当天还在提交**，而 `tesla-open-can-mod` 已经 183 天没动。

**但推荐一个东西必须同时写出它的代价**：它的"Model 3 + HW4"记录版本范围是 `< 2026.2.9`（第 8 节），这台车在范围外；而且它是三家里唯一明确记录 VIN 级封禁的（见第 13 节）。

### 主方案清单

| 项 | 内容 |
| --- | --- |
| **微雪 ESP32-S3-RS485-CAN** | 官方商城 `https://www.waveshare.net/shop/ESP32-S3-RS485-CAN.htm`，我检索到的标价 **¥99.99**（2 件 ¥96.96）；**该站有反爬，直接打开可能只返回一段 JS**，价格请以页面实际显示为准 |
| 国际站同款 | `https://www.waveshare.com/esp32-s3-rs485-can.htm`（有 `-U` 外置天线版） |
| 规格一手出处 | Wiki：`https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN` |
| 第三方同款参考价 | `https://www.spotpear.cn/shop/.../ESP32-S3-RS485-CAN.html` 标 **¥99**（页面日期 2025-08-14） |
| 对应构建目标 | `waveshare-s3-can`（`esp32/README.md:159` 明列，TX=15 / RX=16 / LED=46 / BTN=0） |

**从 wiki 核实的规格**（不是我推断的）：主控 **ESP32-S3R8**，LX7 双核 240MHz，2.4GHz WiFi + BLE 5；**16MB Flash** / 8MB PSRAM；**板载隔离 CAN**（端子 + TVS + 浪涌 + ESD + 指示灯）；**120Ω 匹配电阻默认 `NC`（断开）、跳线帽使能**——正好符合 `HARDWARE.md:633` 的"不要加第二个 120Ω"；端子供电 **7V ~ 36V**，另有 USB Type-C 5V；导轨式外壳 91.6 × 23.3 × 58.7 mm。

> ⚠️ **wiki FAQ 原文**："Can I power the board using both the terminal block and the USB interface simultaneously? **No, this may risk damaging the module.**"——螺丝端子供电与 USB **二选一**。

> ⚠️ **微雪自己的法律声明**（wiki「Warning」栏）：本产品仅用于合法的开发、学习、研究与工业用途，**严禁将任何 CAN 总线用于未经授权的破解、篡改、解锁或功能劫持**，否则可能构成违法、用户自负全部法律责任——厂商原话，我照译放在这儿。

### 线材与小件

| 件 | 用途 | 价格与链接 |
| --- | --- | --- |
| **USB-A → Type-C 数据线** | 烧录 + 5V 供电 | 必须是**数据线**；我没有可验证的链接，**搜索「Type-C 数据线」** |
| **X179 4 芯线束** | CAN-H / CAN-L / +12V / GND | 我没有可验证的链接，**搜索「X179 线束 特斯拉」**；仓库只写 "4-wire pigtail" |
| 万用表 | 量终结电阻、量 12V 是否常电 | `HARDWARE.md:646`、`:659` 都要求这一步 |
| （可选）示波器 | 验每一对是 CAN 还是 DoIP | `HARDWARE.md:220` 的第 1 条建议 |
| 一字螺丝刀 / 杜邦线 | 螺丝端子接线 | 微雪板是螺丝端子 |

### 不用买的东西

| 件 | 为什么不用 |
| --- | --- |
| **CAN 收发器** | 板载隔离 CAN，不用另配 |
| **120Ω 终端电阻** | `HARDWARE.md:633`：Tesla 的总线**已经终结**，别加第二个；微雪这块出厂就是断开的 |
| **降压模块** | 板子吃 7~36V，X179 的 12V 直接进端子 |

### 备选（`HARDWARE.md:386-563` 的五套，价格是仓库标出的美元）

| 方案 | 内容 | 仓库标价 | env |
| --- | --- | --- | --- |
| **A 最便宜全功能** | ESP32-C3-SuperMini / DevKitC + MCP2515(TJA1050) + X179 线 | `:388` ~$8–12 | `esp32-mcp2515` |
| **B 即插即用** | M5Stack ATOM Lite + ATOMIC CAN Base | `:405` ~$16–20 | `m5stack-atom` |
| **C 双 CAN** | LILYGO T-2CAN ESP32-S3 | `:417` ~$27–29 | `lilygo-t2can` |
| **D 带屏** | TTGO T-Display + MCP2515 + XY-3606 降压 | `:437` ~$17–26 | `ttgo-tdisplay` |
| **E 原版** | Flipper Zero + Electronic Cats CAN Add-On | `:541` ~$205–245 | `.fap`，走 `ufbt` |

**方案 C 值得单独说**：T-2CAN 是双路独立 CAN（原生 TWAI + 外挂 MCP2515）。第 9 节那张 post-April-2024 实测表显示"唯一可用的 CAN 对是 18/19"，而 `HARDWARE.md:278-286` 又指出 **`0x3C2` 只在 9/10 或 OBD-II 6/14 上可见、13/14 上根本没有**——**单路板接错对就没辙，双路板可以一路接 X179 18/19、另一路留着**。

## 11. 接线：从 X179 到螺丝端子

### 一、X179 在哪——两份指南会给你两个相反的答案

`HARDWARE.md:92` 的小标题直接给了位置：**`X179 — behind the rear center console (2021+ Model 3/Y)`**（后排中控台后方）。

**但 `tesla-open-can-mod` 的两份指南互相矛盾，这一处最"物理"——照错了连地方都找不到：**

`guides/INSTALLATION_GUIDE_M4_CAN.md:57`：

> The Enhance Auto Gen 2 Cable plugs into the **X179 connector**, located behind the **driver's side trunk panel**.

`guides/WIRING_GUIDE.md:16`：

> The X179 connector is located on the **passenger side footwell**, behind the panel on the right.

一个说**驾驶侧后备箱饰板后**，一个说**副驾脚部空间右侧饰板后**——方向完全相反。我全仓库 grep `footwell|trunk panel`，只有 3 处命中，`README:260` 只给了 service.tesla.com 的文档链接，**没有第三份口径可以仲裁**。

而两份指南自称的车型还是一致的：`INSTALLATION_GUIDE:3` 写 "2023 Tesla Model 3 with HW3"，`WIRING_GUIDE:5` 写 "Photos were taken on a 2023 Model 3 (non-Highland)"。**同一台车，两个位置。**

**这一处的性质与下面两处不同**：那两处是"文档指向不存在的 API"，读者会在编译期撞墙、当场发现；这一处是"文档指向错误的物理位置"，只会让你拆错饰板浪费时间。

两份指南都附了 Enhance Auto 的实拍视频，**实车动手前以视频为准，不要以文字为准。**

### 二、引脚表（仓库原文，**不是你车的实测**）

**20-pin（2021–2023 Model 3/Y，`HARDWARE.md:130-158`，表体 `:140-150`）**

| Pin | 信号 | 总线 |
| --- | --- | --- |
| **1** | **+12V** | 电源 |
| 2 / 3 | CAN-H / CAN-L | Party CAN |
| 9 / 10 | CAN-H / CAN-L | Vehicle CAN |
| **13 / 14** | **CAN-H / CAN-L** | 网关转发的子集 |
| **15** | **+12V** | 电源（2mm² 线，pin 1 的替代） |
| 18 / 19 | CAN-H / CAN-L | Chassis（EPAS/刹车） |
| **20** | **GND** | 地 |

**26-pin 有两档，`HARDWARE.md:159` 起，且 `:162` 明确写着 `"They are not interchangeable."`**：pre-April-2024 表在 `:171-185`；post-April-2024 的示波器实测表就是第 9 节那张（`:193-204`），9/10 与 12/13 是 DoIP，只有 18/19 还是 CAN。

### 三、四根线怎么接

![四根线怎么接：X179 到螺丝端子](images/can-mod-teardown-2026/s04-x179-wiring.svg)

图 4｜选一对 CAN 与固定电源地，四根线进微雪板的螺丝端子；下方三个红框是接车前必查项。

`HARDWARE.md:399` 起的原文示意：

```
X179 Pin 13 → CAN-H ──┐
X179 Pin 14 → CAN-L ──┤── CAN module (MCP2515 / TWAI)
X179 Pin 15 → 12V ────┤── buck converter → 3.3V/5V
X179 Pin 20 → GND ────┘   (26-pin: use Pin 26 for GND)
```

对微雪这块板，右侧那半简化掉：**12V 直接进螺丝端子（板子吃 7–36V），GND 进另一个端子，CAN-H / CAN-L 进 CAN 端子**，不需要降压模块。

**接哪一对，取决于第 9 节记下来的 Service Mode 结果。** 仓库为不同功能点名了不同总线，我把出处一并列出：

- **`HARDWARE.md:123`**：**"For the nag killer, tap Party CAN (pins 2/3)."**
- **`:280-286`**：要注入 `0x3C2`，接 **9/10** 或 **OBD-II 6/14**；13/14 上根本没有这一帧
- **`:293`**：HW4-modern 上 `0x370` 不在 Vehicle CAN，剩下唯一可能的位置是 **Chassis 18/19**

### 四、终结电阻：不要加，并且要量一次

`HARDWARE.md:633`：**"Tesla's CAN buses are already terminated. Do not add a second 120 Ω terminator."** 多数后装模块出厂带终结，接车之前先关掉——微雪这块出厂是 `NC`，不用动。

`:646` 的验证法（**脱车**量）：CAN-H ↔ CAN-L **~120Ω = 正常**（车提供终结）；**~60Ω = 你模块自己的终结器开着**，关掉。

### 五、供电三个坑

1. **OBD-II pin 16 是常电**，车锁了也供（`:653`）。ESP32 静态约 50mA × 12V ≈ **0.6W 持续**，几天能把 12V 电池放干。
2. **X179 pin 1/15 行为不一**（`:659`）：有的车随唤醒门控、有的常电，**仓库原话是"先用万用表测再依赖它"**。
3. **螺丝端子供电与 USB 不能同时**（微雪 wiki FAQ），二选一。

永久安装走深睡（`:665` 起）：5 分钟无帧 → 深睡约 10µA。

### 六、上电之前的静态检查

| 检查 | 依据 | 判据 |
| --- | --- | --- |
| 脱车量 CAN-H↔CAN-L | `HARDWARE.md:646` | ~120Ω 正常，~60Ω 要关终结器 |
| 万用表量 12V | `HARDWARE.md:659` | 确认 1/15 哪一路有电 |
| 示波器量每一对 | `HARDWARE.md:220` | 区分 CAN 与 DoIP |
| 服务模式记针号 | `HARDWARE.md:104` | CAN Port 页按料号列针 |
| 确认端子/USB 只走一路供电 | 微雪 wiki FAQ | 同时接可能损坏模块 |

**这一节全部是仓库文档与厂商规格的转述，我一条都没实测。**

## 12. 烧录与上电：两条路

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

第 7 节记录的本机结果（在上游 `6a3404f` 上复跑）：`waveshare-s3-can` **SUCCESS，RAM 37.4% / Flash 28.0%**；同一棵树的其余 9 个 env 也全部 SUCCESS（**10/10**）。加 `-t upload` 就是烧录。

### 走 `tesla-open-can-mod` 的话，会撞两处裂缝

**裂缝一：M4 指南里的宏在源码里不存在。** `guides/INSTALLATION_GUIDE_M4_CAN.md:29` 写着 `#define HW_TARGET TARGET_HW3  // Change to TARGET_LEGACY, TARGET_HW3, or TARGET_HW4`，我全仓库 grep `HW_TARGET|TARGET_HW3|TARGET_LEGACY` **只有这一处命中**——没有任何代码读它，真正生效的是 `RP2040CAN.ino:24-26` 的车型宏与 `app.h:13-21` 的条件编译。**照指南逐字执行，会定义一个没人读的宏，构建照样撞上 `app.h:20` 的 `#error`。** 指南其余部分（装库、选板、接线、验证）都对，只有选型这一行指向了不存在的 API。

**裂缝二：PlatformIO 路径缺一个车型定义——但上游用脚本堵上了。** `app.h:20` 的错误信息让你往 `build_flags` 加 `HW4/HW3/LEGACY`，而 `platformio.ini` 五个环境的 `build_flags` **只有驱动宏**；README `:215-217` 又让你改 `src/main.cpp` 里"那行 define"——**用定冠词暗示它已经存在，实际上不存在**。

**实跑之后分两种情况。** 原样 clone 直接 `pio run -e esp32_twai` **失败，但失败点不在 `app.h:20`**：

```
*** RP2040CAN.ino must enable exactly one driver define: DRIVER_MCP2515, DRIVER_SAME51, DRIVER_TWAI.
File "...\scripts\platformio_sync_ino_defines.py", line 29, in _pick_one
========================= [FAILED] Took 113.98 seconds =========================
```

解开两行后同一命令**成功**，脚本打印 `Synced RP2040CAN.ino defines for esp32_twai: HW4`。所以准确表述是：**本地副本（缺 `platformio_sync_ino_defines.py`）撞 `app.h:20`，上游只要脚本在原位就走不到——堵住这个洞的是构建流程，不是源码。** 把 `extra_scripts` 去掉，洞会原样露出来。

**上电之后的第一状态：只听。** `esp32/README.md:20`：**"The device boots in Listen-Only mode by default and will not transmit any CAN frames until the user explicitly switches to Active mode."** `README.md:118` 补一句，这是 MCP2515 的**硬件** listen-only 位，物理上不能 TX。**上电 ≠ 会发帧**，而且这一层不是软件判断——第 5 节维度三那个"运行时治理"，在这里落在了最靠近物理的地方。

## 13. 板子与车上的操作流程，以及仓库的指南到此为止

### 一、到 dashboard 为止的四步

1. **接线**（按第 11 节记下的针号）→ **上电**（端子或 USB，二选一）。
2. **连板子的 WiFi**，浏览器开 **`http://192.168.4.1`**（`esp32/README.md:132`）。
3. **先看接线对不对**：`esp32/README.md:131` 的 **Wiring Check = `rx_count` + CAN error monitoring**。这一步只读：**帧数在涨、CRC 错误为 0，说明收发对了；反过来先回第 11 节查线。**
4. **选硬件模式**：`esp32/README.md:123` 的 **HW Override = Auto-detect / Force HW4 / Force HW3 / Force Legacy**，运行时选择、不用重烧。

### 二、仓库自己写下的几条运行约束

| 约束 | 出处 | 内容 |
| --- | --- | --- |
| OTA 检测 | `esp32/README.md:128` | 检测到 OTA 更新会**自动停止 TX**（`0x318`），除非显式开 Ignore OTA |
| 只读功能不依赖 FSD | `README.md:19` | 仓库原话：非 FSD 功能（诊断、BMS 面板等）不需要任何订阅 |
| FSD 功能需要有效权益 | `README.md:19` | 仓库原话：本工具在 CAN 层使能，**车辆仍需有效的 FSD 资格** |
| Listen-Only 首启默认 | `esp32/README.md:130` | 首次启动只听，模式保存、恢复出厂回到只听 |

**还有一条必须单独拎出来，因为它是我这一轮才读到的**——`README.md:22`：

> **Tesla has begun issuing VIN-level bans** (April 2026). Affected vehicles lose the TLSSC toggle silently — no OTA, no warning, persists across account transfers and re-subscriptions. The **TLSSC Restore** feature (v2.10+) can recover stop sign / traffic light control on banned Palladium and HW4 cars via 0x331 DAS config spoofing.

**这是仓库自己的陈述（附 issue `#18`），我没有独立核实，也没有车可以核实**——但它写在 HEAD 的 README 里，性质是**项目方的风险自述**，比"社区回报"高一级。

### 三、仓库的指南到此为止

**以上全部是仓库文档与厂商规格的转述，行号都给了，我一条都没执行**——没有板子、没有线束、没有车。

**这里也是仓库的指南到此为止。** 再往前——上路之后 nag 是否真的不再出现、FSD 是否真的接合、某个开关在 2026.2.11 上有没有效果——**不在本文范围内，仓库文档本身也没给出验证步骤**，我不会替它编一份；任何关于规避检测、隐匿接入、移除车上通信模块的做法，本文一概不涉及。

**我能担保到 `firmware.bin` 生成、到上面每一条引用的行号为止。** 烧录之后车会怎么反应，见第 8 节的"未核实"。

---

## 14. 参考与引用：本文用到的每一条外部出处

三类性质请勿混用：**一手**＝我能直接拿到原文；**社区回报**＝第三方在 issue/讨论里的单点陈述，我未独立核实；**未核实**＝我明确没有验证。访问日期除另注外均为 **2026-10-01**。

### 一、三个仓库本身

三行的 URL 与 commit 见第 0 节那张表，全部用 `git ls-remote` / 本地 HEAD 复现。

**第 8 节引用的同族项目**（`herrfrei`、`juamiso`、`jvanakker`）与**第 7 节计入测试总数的** `JordanzhaoD/waveshare-single-can-firmware`，我按 URL 与页面日期记录，**未 clone 下来做 `file:line` 核验**。

### 二、厂商文档（一手）

| 出处 | URL | 用在哪 |
| --- | --- | --- |
| 微雪 Wiki ESP32-S3-RS485-CAN | `https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN` | 第 10 节规格、120Ω 默认 NC、7–36V、双路供电警告、法律声明 |
| 微雪国际站商品页 | `https://www.waveshare.com/esp32-s3-rs485-can.htm` | 型号 `-U` 外置天线版 |
| 微雪官方商城 | `https://www.waveshare.net/shop/ESP32-S3-RS485-CAN.htm` | 第 10 节标价（**该站有反爬，页面未直接返回价格**） |
| PlatformIO | `https://platformio.org/` | 出自 `esp32/README.md`，未另开页面 |
| Flipper Zero | `https://flipper.net/` | 出自 `HARDWARE.md`，未另开页面 |

### 三、第三方价格（非一手）

| 出处 | URL | 页面日期 | 用在哪 |
| --- | --- | --- | --- |
| Spotpear 同款 | `https://www.spotpear.cn/shop/ESP32-S3-IOT-RS485-CAN-WIFI-Bluetooth/ESP32-S3-RS485-CAN.html` | 2025-08-14 | 第 10 节 ¥99 参考价 |
| M5Stack ATOM Lite | `https://shop.m5stack.com/products/atom-lite-esp32-development-kit` | 仓库引用 | 方案 B |
| M5Stack ATOMIC CAN Base | `https://shop.m5stack.com/products/atomic-can-base` | 仓库引用 | 方案 B |
| LILYGO T-2CAN | `https://lilygo.cc/products/t-2can` | 仓库引用 | 方案 C |
| LILYGO TTGO T-Display | `https://lilygo.cc/products/lilygo%C2%AE-ttgo-t-display-1-14-inch-lcd-esp32-control-board` | 仓库引用 | 方案 D |
| AliExpress XY-3606 降压 | `https://www.aliexpress.com/wholesale-xy3606.html` | 仓库引用 | 方案 D |
| Electronic Cats CAN Add-On | `https://electroniccats.com/store/flipper-addon-canbus/` | 仓库引用 | 方案 E |

**"仓库引用"指 URL 出自 `hypery11/flipper-tesla-fsd/HARDWARE.md`，我没另开页面核对价格**；第 10 节表里的美元数字是**仓库标的**（`:388` `:405` `:417` `:437` `:541`），不是我查的。

### 四、社区回报（issue / discussion，我未独立核实）

| 内容 | 出处 | 用在哪 |
| --- | --- | --- |
| post-April-2024 26-pin 只有 18/19 是 CAN | issue `#52`，`@0n3-70uch` 示波器实测，Berlin 产 EU Model Y，FW 2026.14.3 | 第 9、11 节 |
| `0x3C2` 在 9/10 可见、13/14 不可见 | issue `#73`，`@JakNo` / `@jewelrylin` | 第 9、11 节 |
| X179 pin→bus 的 Service Mode 实测表 | issue `#100`，`@jewelrylin`，harness `1933903-XX`，Model Y Juniper RWD 2025，FW 2026.14.3 | 第 9 节 |
| post-SOP10 针位重排与 X177 | discussion `#114`，`@mamixsystem` | 第 9 节 |
| Nag killer 接 Party CAN 2/3 | `@SkyRaax`，M3 HW4 2026.2.0，issue `#100` | 第 11 节 |
| **VIN 级封禁研究** | issue `#18`、仓库 `SECURITY.md`；转述见 `README.md:22` | 第 13 节 |
| **HW4 + 2026.2.11 正面兼容数据** | `changelog.md:243`，`@Tikernel` + `@ViPiMP`，**Model Y Juniper** | 第 8、9 节 |
| 分版本兼容结论表 | `README.md:280-293` | 第 8 节 |

### 五、工具与可复现入口

| 内容 | URL |
| --- | --- |
| Web Flasher | `https://hypery11.github.io/flipper-tesla-fsd/install/` |
| Releases | `https://github.com/hypery11/flipper-tesla-fsd/releases` |
| FSD CAN Mod Hub 跟踪页（README 徽章指向） | `https://fsdcanmod.com/project/hypery11-flipper-zero` |
| Tesla Electrical Reference（仓库引用的官方文档） | `https://service.tesla.com/docs/ModelY/ElectricalReference/` |

### 六、本文的证据分层

| 层 | 用在哪 | 可信度 |
| --- | --- | --- |
| 本地源码 `file:line` / 上游 `README.md:N` | 第 1–3 节、第 7、12 节 | **可 grep 复现**，行号与 commit 钉死在第 0 节那张表 |
| 本机实跑（编译、测试） | 第 7 节 | 输出可重跑，版本标注见表内 |
| 文件实读 / 关键字检索 | 第 5 节维度五的三个 `LICENSE`、第 8 节三行 grep | 打开读过、可复现（扫描文件数已标注） |
| 仓库文档转述 / 社区回报 / 未核实 | 第 9–13 节、本节第四组、兼容性状态 | **行号可查，内容我没验或未独立核实；第 8 节的结论不变** |

---

## 15. 总结

回到开头那个问题：**操作序列写在代码里，在哪三层。** 三个仓库给的是同一个答案，形状只差在放哪——**启动**上 handler 都必须先于驱动建立，**运行**上都是"排空读取 + 逐帧转发"、只差转发前垫了什么，**业务**上都是按 mux 分支、读状态、改比特、回发。横切面三家同源，展开见第 4 节。

读完三份源码，四条判断值得摆出来。

**第一条，`tesla-open-can-mod` 的成熟度高于这类工具的平均水准**——第 1.6 节那个 shadowing 回归测试：发现隐式耦合、修复、用测试锁死、把意图写进测试名。随手一写的脚本不会这样。

**第二条，"安全门控"分化的方向是"往哪一层放"，这是全文最核心的发现。** `tesla-open-can-mod` **根本没有统一发送许可**，flipper 放在**业务层每条路径各调一次**（五处，容易漏），ev-open 挂在**驱动回调**上（业务层绕不过去）。**同一道闸，三家选了三个高度。**

**第三条，行号和文档都必须钉死在具体版本上。** 这次被自己证了两回：flipper 在我重写当天前进 4 个提交、`HARDWARE.md` 每处引用都漂了；ev-open 的 tag 根本不在默认分支上，clone 到的 `main` 落后 14 个提交。同一类问题的另一面是文档与代码的落差——`HW_TARGET` 没人读、车型宏靠脚本注入、两份指南对 X179 给出相反答案。**前两处编译期炸掉，第三处只会让你拆错饰板，编译器和 grep 都不替你拦。**

**第四条，"能不能编"和"能不能接"是两个独立问题，后者更硬。** 前者已用 **18 个板级环境、1904 个用例**给了答案；后者一条都没解决：X179 针号要进 Service Mode 才知道，OBD-II 口是 CAN 还是 DoIP 要看生产日期与地区，终结电阻要脱车量，12V 是否常电要万用表测。**编译通过是我在桌面上能给的最强证据，它到 USB 线为止。**

再加一条方法论：**社区数据的可迁移性取决于同一性，不取决于相似度。** `changelog.md:243` 那条数据在地区、硬件代际、软件版本上与这台车完全一致，唯独车型是 Model Y——**这一项差在哪里我没有数据**。**选型时该问的不是"哪个更好"，而是"哪一份的证据恰好落在我的配置上"。**

**最后是边界：仓库的指南到此为止。** 往前的每一步——上路之后某个开关到底有没有效果——既不在我验过的范围内，也不该由我替仓库编一份流程。我能担保的是行号、编译输出、引用出处；再往前，需要读者自己的板子、自己的线、自己的车，和一份愿意承认"我不知道"的记录。

---

**下一篇**我打算回到网络架构本身：经典 CAN、CAN FD、以太网骨干各自承载什么，以及为什么一家车企的网络选型会直接决定它的功能迭代速度。


