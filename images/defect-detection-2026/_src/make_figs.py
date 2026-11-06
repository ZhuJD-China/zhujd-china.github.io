#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate SVGs for the defect-detection article (dark site theme)."""
from __future__ import annotations

import html
import os

BG = "#0b0b10"
FG = "#e8e4dc"
MUT = "#a09b8d"
DIM = "#6b675c"
GOLD = "#c9a96a"
BLUE = "#7aa2c8"
RED = "#cf5a50"
GREEN = "#8fbf7a"
GRAY = "#8a8578"
SERIF = "'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif"
MONO = "'JetBrains Mono',Consolas,monospace"

STYLE = f"""
.bg{{fill:{BG}}}
.ttl{{fill:{FG};font:600 26px {SERIF}}}
.sub{{fill:{MUT};font:400 15px {SERIF}}}
.hd{{fill:{FG};font:600 16px {SERIF}}}
.lb{{fill:{FG};font:400 13px {SERIF}}}
.sm{{fill:{MUT};font:400 12px {SERIF}}}
.xs{{fill:{DIM};font:400 11px {SERIF}}}
.foot{{fill:{DIM};font:400 12px {SERIF}}}
.mono{{fill:{GOLD};font:600 13px {MONO}}}
.moc{{fill:{BLUE};font:600 13px {MONO}}}
.mor{{fill:{RED};font:600 13px {MONO}}}
.ar{{fill:none;stroke:{GRAY};stroke-width:1.6}}
"""


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def t(x, y, s, cls="lb", fill=None, anchor=None, size=None, weight=None):
    a = f' text-anchor="{anchor}"' if anchor else ""
    st = ""
    if fill:
        st += f' fill="{fill}"'
    if size:
        st += f' font-size="{size}px"'
    if weight:
        st += f' font-weight="{weight}"'
    return f'<text class="{cls}" x="{x}" y="{y}"{a}{st}>{esc(s)}</text>'


def rect(x, y, w, h, fill, stroke=None, sw=1.3, rx=10, op=1.0):
    s = f' fill="{fill}" fill-opacity="{op}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-opacity=".55" stroke-width="{sw}"'
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"{s}/>'


def line(x1, y1, x2, y2, stroke=GRAY, sw=1.4, dash=None, op=0.8):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-opacity="{op}" stroke-width="{sw}"{d}/>'


def arrow(x1, y1, x2, y2, stroke=GRAY, sw=1.6):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{sw}" marker-end="url(#ah)"/>')


def poly(points, stroke=GRAY, sw=1.6):
    p = " ".join(f"{x},{y}" for x, y in points)
    return f'<polyline points="{p}" fill="none" stroke="{stroke}" stroke-width="{sw}" marker-end="url(#ah)"/>'


def svg(w, h, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{esc(title)}">
<style>{STYLE}</style>
<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{GRAY}"/></marker></defs>
<rect class="bg" x="0" y="0" width="{w}" height="{h}" rx="14"/>
{body}
</svg>
"""


def footer(h, s):
    return t(44, h - 18, s, "foot")


# ---------------------------------------------------------------- s01
def s01():
    w, h = 1200, 640
    b = []
    b.append(t(44, 50, "同一个 99%，在 0.3% 的缺陷率下还剩多少", "ttl"))
    b.append(t(44, 78, "示例：10,000 件产品，缺陷率 0.3%，召回 90%，特异度 99%。准确率 98.97%，精确率 21.3%。", "sub"))

    # confusion matrix
    x1, x2, y1, y2 = 190, 390, 210, 330
    cw, ch = 190, 110
    b.append(t(285, 192, "实际 NG", "sm", anchor="middle"))
    b.append(t(485, 192, "实际 OK", "sm", anchor="middle"))
    b.append(t(178, 270, "判 NG", "sm", anchor="end"))
    b.append(t(178, 390, "判 OK", "sm", anchor="end"))
    cells = [
        (x1, y1, "TP 27", "检出", GOLD, "#1a1712"),
        (x2, y1, "FP 100", "误报", BLUE, "#14161c"),
        (x1, y2, "FN 3", "漏检", RED, "#1d1414"),
        (x2, y2, "TN 9,870", "正确放行", GRAY, "#17171a"),
    ]
    for x, y, big, small, col, fill in cells:
        b.append(rect(x, y, cw, ch, fill, col))
        b.append(t(x + cw / 2, y + 48, big, "hd", fill=col, anchor="middle", size="24px"))
        b.append(t(x + cw / 2, y + 76, small, "sm", anchor="middle"))
    b.append(t(70, 480, "缺陷 30 件；99% 特异度在 9,970 件良品上产生 100 件误报。", "sm"))
    b.append(t(70, 506, "准确率被大量真阴性撑高，精确率才反映 NG 判定里有多少是真的。", "xs"))

    # right panel
    b.append(rect(650, 150, 500, 370, "#121216", GOLD))
    b.append(t(680, 190, "三个数看同一件事", "hd"))
    rows = [
        ("98.97%", "准确率", "被 9,870 件真阴性撑高", GRAY),
        ("21.3%", "精确率", "127 件判 NG，只有 27 件是真缺陷", GOLD),
        ("10.0", "每千件误报", "复检台的直接负担", BLUE),
    ]
    yy = 235
    for big, lab, note, col in rows:
        b.append(t(680, yy, big, "hd", fill=col, size="30px"))
        b.append(t(820, yy - 2, lab, "lb", fill=FG))
        b.append(t(820, yy + 20, note, "xs"))
        yy += 78
    # stacked bar
    b.append(t(680, 470, "被判 NG 的 127 件", "sm"))
    bx, by, bw, bh = 680, 482, 430, 18
    tpw = bw * 27 / 127
    b.append(rect(bx, by, tpw, bh, GOLD, rx=4))
    b.append(rect(bx + tpw, by, bw - tpw, bh, BLUE, rx=4))
    b.append(t(bx + tpw / 2, by + 14, "27", "xs", anchor="middle", fill=BG))
    b.append(t(bx + tpw + (bw - tpw) / 2, by + 14, "100", "xs", anchor="middle", fill=BG))

    b.append(t(70, 566, "「全部放行」的准确率是 99.7%，比这个模型还高——所以准确率不能当验收指标。", "lb", fill=GOLD))
    b.append(t(70, 594, "30 个缺陷零漏检，95% 置信上限仍是 10%；要证明漏检率低于 1%，需要约 300 个缺陷样本。", "sm"))
    b.append(footer(h, "数据：示例算例，二分类混淆矩阵｜置信上限按 rule of three 估算"))
    return svg(w, h, "同一个 99% 在 0.3% 缺陷率下的混淆矩阵与精确率", "\n".join(b))


# ---------------------------------------------------------------- s02
def s02():
    w, h = 1200, 620
    b = []
    b.append(t(44, 50, "缺陷的四个家族，对应四类算法", "ttl"))
    b.append(t(44, 78, "先用物理信号定义缺陷，再选算法；反过来做，就会拿划痕检测器去抓漏装。", "sub"))

    cards = [
        ("外观类", GOLD, "#1a1712", ["划痕 / 脏污 / 凹坑", "气泡 / 裂纹 / 异物"], "局部反射率、纹理",
         ["经典阈值 / 纹理", "+ 无监督 AD"], "像素 / 区域"),
        ("尺寸类", BLUE, "#14161c", ["缺料 / 多料", "毛刺 / 变形"], "几何、轮廓",
         ["3D 测量", "边缘 / 模板"], "µm / mm"),
        ("装配类", GREEN, "#181a14", ["错装 / 漏装", "反装 / 偏移"], "目标存在、位姿",
         ["监督检测 / 分割", "YOLO / U-Net"], "目标 / 图像"),
        ("逻辑类", RED, "#1d1414", ["数量不对 / 顺序不对", "搭配不对"], "目标间关系",
         ["规则 + 检测", "+ 视觉语言模型"], "图像 / 批次"),
    ]
    x = 40
    for title, col, fill, examples, signal, alg, metric in cards:
        b.append(rect(x, 120, 250, 400, fill, col))
        b.append(rect(x, 120, 250, 44, col, rx=10, op=0.18))
        b.append(t(x + 16, 148, title, "hd", fill=col))
        yy = 195
        b.append(t(x + 16, yy, "典型缺陷", "xs", fill=DIM)); yy += 24
        for e in examples:
            b.append(t(x + 16, yy, e, "lb")); yy += 21
        yy += 18
        b.append(t(x + 16, yy, "物理信号", "xs", fill=DIM)); yy += 24
        for s in signal.split("、"):
            b.append(t(x + 16, yy, s, "sm")); yy += 20
        yy += 18
        b.append(t(x + 16, yy, "首选算法", "xs", fill=DIM)); yy += 24
        for a in alg:
            b.append(t(x + 16, yy, a, "lb", fill=col)); yy += 21
        yy += 18
        b.append(t(x + 16, yy, "判定单位", "xs", fill=DIM)); yy += 24
        b.append(t(x + 16, yy, metric, "sm"))
        x += 290

    b.append(t(44, 570, "前两类靠「看」，后两类靠「数」和「关系」。逻辑类缺陷的像素可以全部正常，重建误差为零。", "lb", fill=GOLD))
    b.append(footer(h, "分类依据：物理信号与判定单位｜MVTec LOCO 把结构异常与逻辑异常分开评测"))
    return svg(w, h, "缺陷的四个家族与对应算法", "\n".join(b))


# ---------------------------------------------------------------- s03
def s03():
    w, h = 1200, 740
    b = []
    b.append(t(44, 50, "只有良品时，四条无监督路线", "ttl"))
    b.append(t(44, 78, "共同前提：训练集只含良品；差异在于「异常」被定义成什么。", "sub"))

    panels = [
        (40, 120, "① 重建 · reconstruction", "异常 = 重建误差大",
         "AE/VAE · DRAEM · RD · Dinomaly", "直观、可定位", "锐利纹理也重建不好"),
        (620, 120, "② 嵌入密度 · embedding", "异常 = 离正常特征远",
         "SPADE · PaDiM · PatchCore", "强基线、少样本友好", "特征偏差、内存成本"),
        (40, 400, "③ 学生-教师 · student-teacher", "异常 = 学生预测误差大",
         "STPM · EfficientAD", "快、精度高", "学生太强会学会异常"),
        (620, 400, "④ 归一化流 · normalizing flow", "异常 = 似然低",
         "FastFlow", "密度可解释、推理快", "高维密度估计难"),
    ]
    for x, y, title, core, examples, strong, weak in panels:
        b.append(rect(x, y, 540, 250, "#121216", GRAY))
        b.append(t(x + 20, y + 34, title, "hd", fill=GOLD))
        b.append(t(x + 20, y + 64, core, "lb", fill=FG))
        b.append(t(x + 20, y + 94, examples, "sm", fill=BLUE))
        b.append(t(x + 20, y + 132, "强项  " + strong, "sm"))
        b.append(t(x + 20, y + 158, "失效  " + weak, "sm", fill=RED))
        b.append(t(x + 20, y + 196, "训练数据：良品", "xs"))
        b.append(t(x + 20, y + 216, "推理：异常分数 + 阈值", "xs"))

    # glyph: reconstruction bottleneck (panel 1)
    gx, gy = 420, 178
    b.append(rect(gx, gy, 36, 58, "#1a1712", GOLD, rx=4))
    b.append(rect(gx + 90, gy, 36, 58, "#1a1712", GOLD, rx=4))
    b.append(f'<path d="M {gx+36} {gy+10} L {gx+66} {gy+22} L {gx+66} {gy+36} L {gx+36} {gy+48}" fill="none" stroke="{GOLD}" stroke-width="1.2"/>')
    b.append(f'<path d="M {gx+90} {gy+10} L {gx+66} {gy+22} L {gx+66} {gy+36} L {gx+90} {gy+48}" fill="none" stroke="{GOLD}" stroke-width="1.2"/>')

    # glyph: embedding dots + outlier (panel 2)
    dots = [(1000, 190), (1020, 212), (1045, 195), (1060, 222), (1010, 232), (1035, 242)]
    for dx, dy in dots:
        b.append(f'<circle cx="{dx}" cy="{dy}" r="3.5" fill="{BLUE}" fill-opacity=".8"/>')
    b.append(f'<circle cx="1092" cy="210" r="5" fill="{RED}"/>')

    # glyph: student-teacher (panel 3)
    b.append(rect(440, 482, 40, 30, "#181a14", GREEN, rx=4))
    b.append(t(460, 502, "T", "sm", fill=GREEN, anchor="middle"))
    b.append(rect(510, 482, 40, 30, "#1a1712", GOLD, rx=4))
    b.append(t(530, 502, "S", "sm", fill=GOLD, anchor="middle"))
    b.append(arrow(482, 497, 507, 497, GRAY, 1.2))

    # glyph: normalizing flow funnel (panel 4)
    b.append(f'<path d="M 1010 482 L 1100 482 L 1075 520 L 1035 520 Z" fill="none" stroke="{BLUE}" stroke-width="1.3"/>')
    b.append(line(1055, 520, 1055, 540, BLUE, 1.2))

    b.append(t(44, 690, "四条路线都需要覆盖正常波动的良品样本；「不需要缺陷样本」不等于「不需要数据」。", "lb", fill=GOLD))
    b.append(footer(h, "方法年份：SPADE 2019 / FastFlow 2021 / PaDiM 2021 / PatchCore 2022 / DRAEM 2021 / RD 2022 / EfficientAD 2024 / Dinomaly 2024"))
    return svg(w, h, "四类无监督异常检测范式", "\n".join(b))


# ---------------------------------------------------------------- s04
def s04():
    w, h = 1200, 640
    b = []
    b.append(t(44, 50, "榜单上的 99%，换一个数据集就不到 60%", "ttl"))
    b.append(t(44, 78, "指标口径不同，不能逐项比较；但方向一致：受控 lab → 真实产线，掉 10 到 40 个点。", "sub"))

    # legend
    b.append(rect(900, 96, 12, 12, GOLD, rx=3))
    b.append(t(920, 107, "图像级 AUROC", "xs"))
    b.append(rect(1030, 96, 12, 12, RED, rx=3))
    b.append(t(1050, 107, "平均 AU-PRO", "xs"))

    # axes
    for v in (0, 20, 40, 60, 80, 100):
        y = 480 - v * 3
        b.append(line(90, y, 1140, y, GRAY, 1, dash="3 5", op=0.25))
        b.append(t(78, y + 4, str(v), "xs", anchor="end"))

    bars = [
        (160, 99.1, GOLD, "MVTec AD", "PatchCore · 图像 AUROC"),
        (390, 98.7, GOLD, "VisA", "Dinomaly · 多类图像 AUROC"),
        (620, 89.3, GOLD, "Real-IAD", "Dinomaly · 多类图像 AUROC"),
        (850, 59.0, RED, "MVTec AD 2", "SOTA · 平均 AU-PRO <60"),
    ]
    for x, v, col, lab1, lab2 in bars:
        bh = v * 3
        y = 480 - bh
        b.append(rect(x, y, 130, bh, col, rx=4, op=0.22))
        b.append(f'<rect x="{x}" y="{y}" width="130" height="4" fill="{col}"/>')
        b.append(t(x + 65, y - 10, f"{v:.1f}" if v > 60 else "<60", "hd", fill=col, anchor="middle", size="18px"))
        b.append(t(x + 65, 506, lab1, "lb", anchor="middle"))
        b.append(t(x + 65, 526, lab2, "xs", anchor="middle"))

    # 60 line
    b.append(line(90, 300, 1140, 300, RED, 1.2, dash="6 5", op=0.7))
    b.append(t(1128, 292, "60%", "xs", fill=RED, anchor="end"))

    # arrow annotation
    b.append(t(160, 140, "约 40 个点", "sm", fill=RED))
    b.append(arrow(300, 150, 850, 150, RED, 1.4))

    b.append(t(44, 570, "同一根轴只表示数值，不代表同一指标；MVTec AD 2 的低分是「换到真实场景」后的结果。", "lb", fill=GOLD))
    b.append(footer(h, "数据：PatchCore 论文均值 99.1；Dinomaly 多类 98.7 / 89.3；MVTec AD 2 论文 SOTA <60% 平均 AU-PRO"))
    return svg(w, h, "榜单分数与真实场景的落差", "\n".join(b))


# ---------------------------------------------------------------- s05
def s05():
    w, h = 1200, 560
    b = []
    b.append(t(44, 50, "上线前要过的三道门", "ttl"))
    b.append(t(44, 78, "跳过任何一道，模型都会在产线上用误报和漏检教你做事。", "sub"))

    gates = [
        ("① 离线留出集", GOLD, [
            "测试集来自产线分布", "不是公开数据集",
            "分类型召回", "固定阈值误报 / 千件",
            "置信区间与样本量", "阈值按成本定",
        ]),
        ("② 影子运行", BLUE, [
            "模型推理，不接 PLC", "与复检台对比",
            "2–4 周，覆盖班次", "收集边界样本",
            "校准阈值", "暴露集成问题",
        ]),
        ("③ 冠军-挑战者", GREEN, [
            "同线、同光、同相机", "交替批次",
            "成本 / 千件", "漏检与逃逸",
            "版本与回滚", "上线后持续监控",
        ]),
    ]
    x = 45
    for title, col, items in gates:
        b.append(rect(x, 130, 350, 300, "#121216", col))
        b.append(t(x + 20, 168, title, "hd", fill=col))
        yy = 205
        for it in items:
            b.append(t(x + 20, yy, "· " + it, "sm")); yy += 32
        x += 390
    # arrows
    b.append(arrow(400, 280, 425, 280, GRAY, 1.6))
    b.append(arrow(780, 280, 805, 280, GRAY, 1.6))

    b.append(t(44, 500, "最常见的错误：第 1 道门用公开集刷到 99%，第 2 道门直接跳过，然后把模型接到 PLC。", "lb", fill=RED))
    b.append(footer(h, "三道门顺序不可交换｜任何一道失败都不该进入下一道"))
    return svg(w, h, "上线前要过的三道门", "\n".join(b))


# ---------------------------------------------------------------- s06
def s06():
    w, h = 1200, 760
    b = []
    b.append(t(44, 50, "先问数据，再问模型", "ttl"))
    b.append(t(44, 78, "选型的第一问不是「哪个模型最强」，而是「你有哪些数据、缺陷怎么定义、节拍多少」。", "sub"))

    def qbox(x, y, text):
        b.append(rect(x, y, 400, 76, "#121216", GOLD))
        b.append(t(x + 200, y + 44, text, "hd", anchor="middle", size="15px"))

    qbox(400, 120, "缺陷能否用明确规则或几何描述？")
    qbox(400, 270, "每类缺陷是否有数百张像素级标注？")
    qbox(400, 420, "是否有覆盖正常波动的良品样本？")

    def ans(x, y, title, lines, col):
        b.append(rect(x, y, 300, 140, "#121216", col))
        b.append(t(x + 16, y + 30, title, "hd", fill=col))
        yy = y + 58
        for ln in lines:
            b.append(t(x + 16, yy, ln, "sm")); yy += 22

    ans(60, 300, "经典算法", ["阈值 / 形态学 / blob", "模板匹配 / 3D 测量", "确定性、微秒级、可解释"], GOLD)
    ans(840, 300, "监督检测 / 分割", ["YOLO / U-Net", "Mask R-CNN", "需要固定缺陷类型"], BLUE)
    ans(60, 570, "无监督异常检测", ["PatchCore / EfficientAD", "Dinomaly"], GREEN)
    ans(840, 570, "零样本 / 少样本", ["WinCLIP / AnomalyDINO", "先收集数据再蒸馏"], RED)

    # Q1 yes left
    b.append(poly([(400, 158), (210, 158), (210, 296)]))
    b.append(t(300, 150, "是", "sm", fill=GOLD))
    # Q1 no down
    b.append(arrow(600, 196, 600, 266, GRAY, 1.6))
    b.append(t(612, 236, "否", "sm"))
    # Q2 yes right, into the left edge of the supervised card
    b.append(arrow(800, 308, 836, 308, GRAY, 1.6))
    b.append(t(818, 300, "是", "sm", fill=BLUE))
    # Q2 no down
    b.append(arrow(600, 346, 600, 416, GRAY, 1.6))
    b.append(t(612, 386, "否", "sm"))
    # Q3 yes left
    b.append(poly([(400, 458), (210, 458), (210, 566)]))
    b.append(t(300, 450, "是", "sm", fill=GREEN))
    # Q3 no right
    b.append(poly([(800, 458), (990, 458), (990, 566)]))
    b.append(t(900, 450, "否", "sm", fill=RED))

    b.append(t(44, 726, "混合是常态：经典对齐 + 无监督检出 + 监督分类 + 规则判逻辑。", "lb", fill=GOLD))
    b.append(footer(h, "决策依据：数据状况 × 缺陷类型 × 节拍｜先定义缺陷，再看数据，最后选模型"))
    return svg(w, h, "缺陷检测选型决策树", "\n".join(b))


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..")
    figs = {
        "s01-four-metrics.svg": s01(),
        "s02-defect-taxonomy.svg": s02(),
        "s03-unsupervised-families.svg": s03(),
        "s04-benchmark-gap.svg": s04(),
        "s05-eval-gates.svg": s05(),
        "s06-selection-tree.svg": s06(),
    }
    for name, content in figs.items():
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print("wrote", name, len(content))
