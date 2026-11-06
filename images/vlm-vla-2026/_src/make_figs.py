#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate six SVG figures for the VLM/VLA article."""
import math
import os
from html import escape

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FONT = "'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif"
MONO = "'JetBrains Mono',Consolas,monospace"

CSS = f"""
.bg{{fill:#0b0b10}}
.ttl{{fill:#e8e4dc;font:600 26px {FONT}}}
.sub{{fill:#a09b8d;font:400 15px {FONT}}}
.hd{{fill:#e8e4dc;font:600 16px {FONT}}}
.lb{{fill:#e8e4dc;font:400 13px {FONT}}}
.sm{{fill:#a09b8d;font:400 12px {FONT}}}
.xs{{fill:#6b675c;font:400 11px {FONT}}}
.foot{{fill:#6b675c;font:400 12px {FONT}}}
.mono{{fill:#c9a96a;font:600 13px {MONO}}}
.moc{{fill:#7aa2c8;font:600 13px {MONO}}}
.mor{{fill:#cf5a50;font:600 13px {MONO}}}
.ar{{fill:none;stroke:#8a8578;stroke-width:1.6}}
.grid{{stroke:#8a8578;stroke-width:1;stroke-opacity:.16}}
"""

DEFS = """<defs>
<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8a8578"/></marker>
<marker id="ahg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#c9a96a"/></marker>
</defs>"""


def svg(w, h, label, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(label)}">\n'
        f"<style>{CSS}</style>\n{DEFS}\n"
        f'<rect class="bg" x="0" y="0" width="{w}" height="{h}" rx="14"/>\n'
        f"{body}\n</svg>\n"
    )


def txt(x, y, s, cls="lb", anchor="start", fill=None, size=None, weight=None):
    attrs = f'x="{x}" y="{y}"'
    if anchor != "start":
        attrs += f' text-anchor="{anchor}"'
    style = []
    if fill:
        style.append(f"fill:{fill}")
    if size:
        style.append(f"font-size:{size}px")
    if weight:
        style.append(f"font-weight:{weight}")
    if style:
        attrs += f' style="{";".join(style)}"'
    return f'<text class="{cls}" {attrs}>{escape(str(s))}</text>'


def rect(x, y, w, h, fill="#14161c", stroke="#8a8578", sw=1.2, rx=10, op=1.0):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" fill-opacity="{op}" stroke="{stroke}" stroke-opacity=".55" stroke-width="{sw}"/>'
    )


def line(x1, y1, x2, y2, cls="ar", marker=False, dash=None):
    m = ' marker-end="url(#ah)"' if marker else ""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{m}{d}/>'


def dot(x, y, color, r=7):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" stroke="#0b0b10" stroke-width="2"/>'


# ---------------------------------------------------------------- s01
def s01():
    w, h = 1200, 640
    rows = [
        ("MMMU 2026 前沿 vs 人类专家", 83.8, "模型 83.8", 88.6, "人类 88.6", 4.8),
        ("BLINK 视觉感知（2023）", 51.26, "GPT-4V 51.3", 95.70, "人类 95.7", 44.4),
        ("LIBERO → LIBERO-PRO", 96.85, "π0.5 96.9", 38.0, "扰动后 38.0", 58.9),
        ("Gemini Robotics 2 任务", 89.6, "精密插装 89.6", 45.7, "地面拾取 45.7", 43.9),
    ]
    body = []
    body.append(txt(44, 50, "四组数字，四道落差", "ttl"))
    body.append(txt(44, 78, "榜单上的高分与部署中的现实之间，差的往往不是模型，而是分布与任务结构。", "sub"))
    body.append(f'<circle cx="846" cy="112" r="6" fill="#c9a96a"/>')
    body.append(txt(860, 117, "模型 / 结构化任务", "sm"))
    body.append(f'<circle cx="1000" cy="112" r="6" fill="#cf5a50"/>')
    body.append(txt(1014, 117, "参照 / 扰动场景", "sm"))
    for t in (0, 20, 40, 60, 80, 100):
        x = 190 + t * 8.9
        body.append(f'<line class="grid" x1="{x}" y1="140" x2="{x}" y2="545"/>')
        body.append(txt(x, 566, f"{t}", "xs", "middle"))
    ys = [190, 300, 410, 520]
    for (label, a, alab, b, blab, gap), y in zip(rows, ys):
        xa = 190 + a * 8.9
        xb = 190 + b * 8.9
        body.append(txt(44, y - 30, label, "sm"))
        body.append(f'<line x1="{min(xa,xb)}" y1="{y}" x2="{max(xa,xb)}" y2="{y}" stroke="#8a8578" stroke-width="2" stroke-opacity=".55"/>')
        body.append(dot(xa, y, "#c9a96a"))
        body.append(dot(xb, y, "#cf5a50"))
        if xa < xb:
            body.append(txt(xa - 10, y - 14, alab, "sm", "end"))
            body.append(txt(xb + 10, y - 14, blab, "sm", "start"))
        else:
            body.append(txt(xa + 10, y - 14, alab, "sm", "start"))
            body.append(txt(xb - 10, y - 14, blab, "sm", "end"))
        mid = (xa + xb) / 2
        body.append(txt(mid, y + 26, f"差 {gap:g} 个百分点", "xs", "middle", fill="#cf5a50"))
    body.append(txt(44, 600, "四个差距不是同一种差距：MMMU 差在感知，BLINK 差在细粒度，LIBERO 差在分布，Gemini 差在任务结构。", "foot"))
    body.append(txt(44, 620, "横轴统一按 0–100 绘制，仅用于并排比较；不同评测的分数不可直接换算。", "xs"))
    return svg(w, h, "四组评测分数与部署场景之间的落差", "\n".join(body))


# ---------------------------------------------------------------- s02
def s02():
    w, h = 1200, 640
    body = []
    body.append(txt(44, 50, "一张图要花多少 token", "ttl"))
    body.append(txt(44, 78, "以 14×14 patch、2×2 合并为例：每个视觉 token 覆盖 28×28 像素。", "sub"))
    body.append(txt(44, 112, "N = ceil(H / 28) × ceil(W / 28)", "mono"))
    # left panel
    body.append(rect(40, 140, 535, 330, "#101014", "#8a8578", 1.0))
    body.append(txt(64, 174, "单帧图像", "hd"))
    left = [("1280×720", 1196, "#c9a96a"), ("1920×1080", 2691, "#7aa2c8"), ("3840×2160", 10764, "#cf5a50")]
    maxl = 12000
    for i, (name, val, color) in enumerate(left):
        y = 220 + i * 78
        body.append(txt(64, y + 5, name, "lb"))
        bw = val / maxl * 360
        body.append(f'<rect x="190" y="{y - 15}" width="{bw:.1f}" height="30" rx="5" fill="{color}" fill-opacity=".82"/>')
        body.append(txt(200 + bw, y + 5, f"{val:,}", "sm", fill="#e8e4dc"))
    body.append(txt(64, 440, "720p 是 1.0×；4K 是 9.0×，不是 4×。", "xs"))
    # right panel
    body.append(rect(600, 140, 560, 330, "#101014", "#8a8578", 1.0))
    body.append(txt(624, 174, "60 秒 720p 视频", "hd"))
    right = [("1 fps · 60 帧", 71760, "#c9a96a"), ("2 fps · 120 帧", 143520, "#cf5a50")]
    maxr = 150000
    for i, (name, val, color) in enumerate(right):
        y = 235 + i * 92
        body.append(txt(624, y + 5, name, "lb"))
        bw = val / maxr * 355
        body.append(f'<rect x="760" y="{y - 17}" width="{bw:.1f}" height="34" rx="5" fill="{color}" fill-opacity=".82"/>')
        body.append(txt(770 + bw, y + 5, f"{val:,}", "sm", fill="#e8e4dc"))
    body.append(txt(624, 440, "1 fps 就是 7.2 万 token；2 fps 翻倍。", "xs"))
    body.append(txt(44, 510, "KV cache 也要跟着算：7B、32 层、32 头、head_dim 128、FP16，MHA 每 token 约 512 KiB，1,196 个 token 约 0.6 GB。", "foot"))
    body.append(txt(44, 534, "换成 8 个 KV 头的 GQA，约 0.16 GB；但视频上到 7 万 token，仍是 GB 级，并随并发线性增长。", "foot"))
    body.append(txt(44, 574, "注意力的两两交互随 token 数平方增长：10,764 与 1,196 相比，配对数差 81 倍。", "sm"))
    body.append(txt(44, 604, "所以「支持任意分辨率」和「任意分辨率都便宜」是两回事。", "sm", fill="#c9a96a"))
    return svg(w, h, "视觉 token 预算：分辨率与帧率如何把上下文吃满", "\n".join(body))


# ---------------------------------------------------------------- s03
def s03():
    w, h = 1200, 620
    body = []
    body.append(txt(44, 50, "动作头的四代做法", "ttl"))
    body.append(txt(44, 78, "同一个「看懂」，落到动作上要解决精度、多峰与延迟三个问题。", "sub"))
    cols = [
        ("离散 token", "#c9a96a", "RT-2 · 55B"),
        ("回归", "#7aa2c8", "RT-1 / OpenVLA · 7B"),
        ("扩散", "#8fbf7a", "Diffusion Policy"),
        ("流匹配", "#cf5a50", "π0 · 3.3B"),
    ]
    x0, cw, gap = 44, 264, 20
    for i, (name, color, rep) in enumerate(cols):
        x = x0 + i * (cw + gap)
        body.append(rect(x, 112, cw, 400, "#101014", color, 1.2))
        body.append(f'<rect x="{x}" y="112" width="{cw}" height="4" rx="2" fill="{color}"/>')
        body.append(txt(x + 18, 148, name, "hd", fill=color))
        body.append(txt(x + 18, 172, rep, "xs"))
    # col1 bins
    x = x0
    for r in range(2):
        for c in range(4):
            bx = x + 22 + c * 56
            by = 200 + r * 44
            body.append(rect(bx, by, 46, 30, "#1a1712", "#c9a96a", 0.9, 5))
            body.append(txt(bx + 23, by + 20, "bin", "xs", "middle", fill="#c9a96a"))
    body.append(txt(x + 18, 306, "256 bins × 8 维 → 8 个 token", "xs"))
    body.append(line(x + 18, 330, x + 18, 370, "ar", True))
    body.append(txt(x + 18, 396, "复用语言模型下一 token 预测", "xs"))
    body.append(txt(x + 18, 426, "精度被 bin 宽度锁死", "xs", fill="#cf5a50"))
    body.append(txt(x + 18, 452, "自回归 8 步，慢", "xs", fill="#cf5a50"))
    # col2 regression
    x = x0 + (cw + gap)
    body.append(rect(x + 18, 205, 72, 34, "#14161c", "#7aa2c8", 0.9, 6))
    body.append(txt(x + 54, 227, "obs", "xs", "middle", fill="#7aa2c8"))
    body.append(line(x + 94, 222, x + 130, 222, "ar", True))
    body.append(rect(x + 132, 205, 62, 34, "#14161c", "#7aa2c8", 0.9, 6))
    body.append(txt(x + 163, 227, "MLP", "xs", "middle", fill="#7aa2c8"))
    body.append(line(x + 196, 222, x + 228, 222, "ar", True))
    body.append(rect(x + 230, 205, 18, 34, "#1a2430", "#7aa2c8", 0.9, 6))
    body.append(txt(x + 18, 276, "连续动作向量（6–30 维）", "xs"))
    body.append(line(x + 18, 300, x + 18, 344, "ar", True))
    body.append(txt(x + 18, 370, "一步推理、实现简单", "xs", fill="#8fbf7a"))
    body.append(txt(x + 18, 400, "多峰被平均，容易撞中间", "xs", fill="#cf5a50"))
    body.append(txt(x + 18, 430, "代表：RT-1、OpenVLA", "xs"))
    # col3 diffusion
    x = x0 + 2 * (cw + gap)
    for k in range(4):
        cx = x + 34 + k * 54
        cy = 222
        rr = 15 - k * 3
        body.append(f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="#8fbf7a" fill-opacity="{0.18 + k * 0.18:.2f}" stroke="#8fbf7a" stroke-opacity=".7"/>')
    body.append(txt(x + 18, 262, "噪声 → 逐步去噪", "xs"))
    pts = [(x + 22, 330), (x + 70, 300), (x + 120, 324), (x + 170, 288), (x + 228, 310)]
    body.append('<polyline points="' + " ".join(f"{px},{py}" for px, py in pts) + '" fill="none" stroke="#8fbf7a" stroke-width="2.4"/>')
    body.append(txt(x + 18, 360, "生成一条动作序列", "xs"))
    body.append(txt(x + 18, 392, "能表达多峰、训练稳定", "xs", fill="#8fbf7a"))
    body.append(txt(x + 18, 422, "T 步去噪，推理慢", "xs", fill="#cf5a50"))
    body.append(txt(x + 18, 452, "难塞进高节拍产线", "xs", fill="#cf5a50"))
    # col4 flow
    x = x0 + 3 * (cw + gap)
    body.append(f'<path d="M {x+24} 330 C {x+70} 270, {x+120} 350, {x+210} 280" fill="none" stroke="#cf5a50" stroke-width="1.6" stroke-opacity=".5"/>')
    for k in range(4):
        px = x + 40 + k * 48
        py = 326 - 12 * math.sin(k / 3 * math.pi)
        body.append(f'<line x1="{px}" y1="{py + 26}" x2="{px + 8}" y2="{py}" stroke="#cf5a50" stroke-width="2" marker-end="url(#ah)"/>')
    body.append(txt(x + 18, 372, "学习从噪声到动作的速度场", "xs"))
    body.append(txt(x + 18, 402, "少步积分，50 Hz 可跑", "xs", fill="#8fbf7a"))
    body.append(txt(x + 18, 432, "训练目标更敏感", "xs", fill="#cf5a50"))
    body.append(txt(x + 18, 462, "代表：π0、π0.5", "xs"))
    body.append(txt(44, 548, "四条路没有绝对优劣：离散 token 复用语言栈，回归简单，扩散表达多峰，流匹配省步数。", "foot"))
    body.append(txt(44, 572, "2026 年的主流是流匹配 + 动作分块：一次预测 50 步，把推理延迟藏进开环执行。", "sm"))
    body.append(txt(44, 602, "分块的代价是反应变慢：50 步 @ 50 Hz 意味着 1 秒开环，这 1 秒里发生的事模型看不见。", "sm", fill="#c9a96a"))
    return svg(w, h, "动作头的四代做法：离散 token、回归、扩散与流匹配", "\n".join(body))


# ---------------------------------------------------------------- s04
def s04():
    w, h = 1200, 660
    body = []
    body.append(txt(44, 50, "机器人数据的金字塔", "ttl"))
    body.append(txt(44, 78, "越往上，动作标签越密、成本越高；越往下，规模越大、动作越少。", "sub"))
    layers = [
        # (y, height, half_bottom, half_top, color, title, detail)
        (470, 100, 470, 400, "#6b675c", "网页图文", "5.85B 对 · 无动作"),
        (370, 90, 390, 330, "#8fbf7a", "人类视频", "1,000h+ · 无关节角"),
        (278, 82, 320, 260, "#7aa2c8", "仿真", "230k 场景 · 有标签但有 gap"),
        (194, 74, 250, 190, "#c9a96a", "真机轨迹", "1M+ 条 / 10,000h · 最贵"),
    ]
    cx = 560
    for y, hh, hb, ht, color, title, detail in layers:
        pts = f"{cx-hb},{y+hh} {cx+hb},{y+hh} {cx+ht},{y} {cx-ht},{y}"
        body.append(f'<polygon points="{pts}" fill="{color}" fill-opacity=".16" stroke="{color}" stroke-opacity=".7" stroke-width="1.4"/>')
        body.append(txt(cx, y + hh / 2 - 4, title, "hd", "middle", fill=color))
        body.append(txt(cx, y + hh / 2 + 18, detail, "xs", "middle"))
    body.append(line(100, 530, 100, 210, "ar", True))
    body.append(txt(112, 360, "动作标签密度升高", "sm", fill="#c9a96a"))
    body.append(line(1040, 210, 1040, 530, "ar", True))
    body.append(txt(1028, 360, "规模与覆盖增大", "sm", "end", fill="#7aa2c8"))
    body.append(txt(44, 604, "一百万条轨迹买得到覆盖，买不到失败原因、接触力、语义边界和产线节拍。", "foot"))
    body.append(txt(44, 628, "最贵的不是数据量，是带动作、带失败、带时间戳的样本；公开数据集通常把失败片段裁掉了。", "sm"))
    return svg(w, h, "机器人数据的四个来源：网页、视频、仿真与真机轨迹", "\n".join(body))


# ---------------------------------------------------------------- s05
def s05():
    w, h = 1200, 640
    body = []
    body.append(txt(44, 50, "控制层级与延迟预算", "ttl"))
    body.append(txt(44, 78, "按对数轴排列：1 ms 的安全环，到 1 秒的动作分块。", "sub"))
    x0, x1 = 250, 1110

    def lx(t):
        return x0 + (math.log10(t) / 3.0) * (x1 - x0)

    for t, lab in [(1, "1 ms"), (10, "10 ms"), (100, "100 ms"), (1000, "1 s")]:
        xx = lx(t)
        body.append(f'<line class="grid" x1="{xx}" y1="130" x2="{xx}" y2="540"/>')
        body.append(txt(xx, 568, lab, "xs", "middle"))
    body.append(f'<line x1="{lx(20)}" y1="120" x2="{lx(20)}" y2="540" stroke="#cf5a50" stroke-width="1.4" stroke-dasharray="5 5" stroke-opacity=".8"/>')
    body.append(txt(lx(20) + 8, 142, "20 ms：50 Hz 控制周期", "xs", fill="#cf5a50"))
    rows = [
        ("安全环 1 kHz", 1, "#8fbf7a", "急停、力矩限制"),
        ("底层 S1 200 Hz", 5, "#7aa2c8", "关节伺服"),
        ("相机 60 Hz", 16.7, "#a09b8d", "曝光 + 传输"),
        ("π0.5 推理", 76, "#c9a96a", "RTX 4090，第三方"),
        ("策略 S2 10 Hz", 100, "#cf5a50", "视觉语言理解"),
        ("50 步分块", 1000, "#6b675c", "50 Hz 下开环 1 秒"),
    ]
    for i, (name, t, color, note) in enumerate(rows):
        y = 190 + i * 58
        body.append(txt(230, y + 5, name, "sm", "end"))
        bx = lx(t)
        body.append(f'<rect x="{x0}" y="{y - 13}" width="{max(bx - x0, 5):.1f}" height="26" rx="4" fill="{color}" fill-opacity=".55"/>')
        body.append(f'<circle cx="{bx}" cy="{y}" r="5" fill="{color}"/>')
        if bx > x1 - 120:
            body.append(txt(bx - 6, y - 20, note, "xs", "end", fill=color))
        else:
            body.append(txt(bx + 12, y + 5, note, "xs", fill=color))
    body.append(txt(44, 604, "76 ms 的推理塞不进 20 ms 的环路，所以策略层要么降频到 10–13 Hz，要么用动作分块把延迟藏进开环。", "foot"))
    body.append(txt(44, 628, "安全与底层控制不能用学习模型：1 kHz 和 200 Hz 的环必须是确定性的。", "sm"))
    return svg(w, h, "控制层级与延迟预算：1 kHz 安全环到 50 Hz 策略层", "\n".join(body))


# ---------------------------------------------------------------- s06
def s06():
    w, h = 1200, 800
    body = []
    body.append(txt(44, 50, "VLA 选型决策树", "ttl"))
    body.append(txt(44, 78, "先看任务结构和控制周期，再看模型大小。", "sub"))

    def box(x, y, bw, bh, title, sub, color):
        body.append(rect(x, y, bw, bh, "#101014", color, 1.3, 10))
        body.append(f'<rect x="{x}" y="{y}" width="4" height="{bh}" rx="2" fill="{color}"/>')
        body.append(txt(x + 18, y + 32, title, "lb", fill=color))
        if sub:
            body.append(txt(x + 18, y + 56, sub, "xs"))

    # decision spine
    body.append(rect(300, 100, 380, 68, "#14161c", "#c9a96a", 1.4, 10))
    body.append(txt(490, 130, "任务是否固定、物体是否已知？", "hd", "middle"))
    body.append(txt(490, 154, "固定工位、固定来料、固定光照", "xs", "middle"))

    body.append(rect(300, 232, 380, 68, "#14161c", "#7aa2c8", 1.4, 10))
    body.append(txt(490, 262, "是否需要多步、长程？", "hd", "middle"))
    body.append(txt(490, 286, "装配、整理、跨工位搬运", "xs", "middle"))

    body.append(rect(300, 364, 380, 68, "#14161c", "#8fbf7a", 1.4, 10))
    body.append(txt(490, 394, "环境是否开放？", "hd", "middle"))
    body.append(txt(490, 418, "新物体、新布局、有人协作", "xs", "middle"))

    # outcomes on the right
    box(740, 92, 410, 84, "经典视觉 + 规则", "VLM 只做复核与异常兜底", "#8fbf7a")
    box(740, 224, 410, 84, "单任务 VLA 微调", "100–500 条演示 + 力控/护栏", "#7aa2c8")
    box(740, 356, 410, 84, "双系统 VLA", "慢思考 + 快控制 + 任务编排", "#c9a96a")
    box(740, 474, 410, 84, "通用 VLA + 遥操作兜底", "开放世界、影子运行、人工接管", "#cf5a50")

    # arrows
    body.append(line(680, 134, 736, 134, "ar", True))
    body.append(txt(706, 124, "是", "sm", "middle", fill="#8fbf7a"))
    body.append(line(490, 168, 490, 228, "ar", True))
    body.append(txt(502, 202, "否", "sm", fill="#cf5a50"))

    body.append(line(680, 266, 736, 266, "ar", True))
    body.append(txt(706, 256, "否", "sm", "middle", fill="#7aa2c8"))
    body.append(line(490, 300, 490, 360, "ar", True))
    body.append(txt(502, 334, "是", "sm", fill="#c9a96a"))

    body.append(line(680, 398, 736, 398, "ar", True))
    body.append(txt(706, 388, "否", "sm", "middle", fill="#c9a96a"))
    body.append(f'<path d="M 490 432 L 490 516 L 736 516" fill="none" stroke="#8a8578" stroke-width="1.6" marker-end="url(#ah)"/>')
    body.append(txt(502, 466, "是", "sm", fill="#cf5a50"))

    # checklist strip
    body.append(rect(44, 590, 1112, 104, "#101014", "#8a8578", 1.0))
    body.append(txt(68, 620, "无论走哪条路，先过五关", "hd"))
    items = [
        "成功定义可测量",
        "p95 延迟满足节拍",
        "安全环独立于模型",
        "影子运行 ≥ 2 周",
        "报告置信区间，不报均值",
    ]
    xs = [68, 290, 512, 734, 956]
    for x, it in zip(xs, items):
        body.append(f'<circle cx="{x + 4}" cy="656" r="3.5" fill="#c9a96a"/>')
        body.append(txt(x + 18, 660, it, "sm"))
    body.append(txt(68, 682, "0 失败 ≠ 0 风险：10 次全成功的 95% 上界仍有 25.9%。", "xs", fill="#cf5a50"))

    # bottom notes
    body.append(txt(44, 738, "控制周期 < 20 ms：模型只能放慢环，快环交给控制器或 IK；想端到端，先把分块与异步推理算清楚。", "sm"))
    body.append(txt(44, 764, "这张树不替代试跑：它只帮你排除明显不合适的方案，剩下的答案在产线数据里。", "foot"))
    return svg(w, h, "VLA 选型决策树：从任务结构到部署形态", "\n".join(body))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    files = {
        "s01-four-gaps.svg": s01(),
        "s02-token-budget.svg": s02(),
        "s03-action-heads.svg": s03(),
        "s04-data-pyramid.svg": s04(),
        "s05-latency-ladder.svg": s05(),
        "s06-selection-tree.svg": s06(),
    }
    for name, content in files.items():
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"wrote {path} ({len(content)} bytes)")
