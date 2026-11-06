#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate SVG figures for the prompt-injection article (1000px canvas)."""
import os
from html import escape

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FONT = "'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif"
MONO = "'JetBrains Mono',Consolas,monospace"

CSS = f"""
.bg{{fill:#0b0b10}}
.ttl{{fill:#e8e4dc;font:600 34px {FONT}}}
.sub{{fill:#a09b8d;font:400 19px {FONT}}}
.hd{{fill:#e8e4dc;font:600 21px {FONT}}}
.lb{{fill:#e8e4dc;font:400 17px {FONT}}}
.sm{{fill:#a09b8d;font:400 15px {FONT}}}
.xs{{fill:#6b675c;font:400 13px {FONT}}}
.foot{{fill:#6b675c;font:400 14px {FONT}}}
.mono{{fill:#c9a96a;font:600 16px {MONO}}}
.moc{{fill:#7aa2c8;font:600 16px {MONO}}}
.mor{{fill:#cf5a50;font:600 16px {MONO}}}
.ar{{fill:none;stroke:#8a8578;stroke-width:1.8}}
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


# ---------------------------------------------------------------- s01
def s01():
    w, h = 1000, 580
    body = []
    body.append(txt(36, 48, "提示注入的完整链路", "ttl"))
    body.append(txt(36, 76, "每一步都是合法调用；合起来才是一次越权。", "sub"))

    boxes = [
        ("①", "不可信内容", "邮件/网页/Issue"),
        ("②", "进入上下文", "检索/工具返回"),
        ("③", "模型当成指令", "无来源、无优先级"),
        ("④", "调用工具", "读私有/写公开"),
        ("⑤", "组合成越权", "单次合法，序列越权"),
        ("⑥", "数据外发", "链接/图片/PR"),
    ]
    bw, bh, gap = 148, 114, 16
    x0, y0 = 16, 176
    for i, (num, title, sub) in enumerate(boxes):
        x = x0 + i * (bw + gap)
        fill = "#1a1416" if i == 0 else "#14161c"
        stroke = "#cf5a50" if i == 0 else "#8a8578"
        body.append(rect(x, y0, bw, bh, fill=fill, stroke=stroke))
        body.append(txt(x + 14, y0 + 28, num, "mono", fill="#c9a96a"))
        body.append(txt(x + 14, y0 + 56, title, "hd", size=19))
        body.append(txt(x + 14, y0 + 82, sub, "sm", size=13))
        if i < len(boxes) - 1:
            body.append(line(x + bw + 2, y0 + bh / 2, x + bw + gap - 4, y0 + bh / 2, marker=True))

    bx = x0 + bw + gap / 2
    body.append(line(bx, 122, bx, 330, cls="ar", dash="4 5"))
    body.append(txt(bx, 112, "信任边界", "xs", anchor="middle"))

    body.append(txt(x0 + bw / 2, 330, "攻击者写入", "sm", anchor="middle", fill="#cf5a50"))
    body.append(txt(x0 + bw + gap + bw + 4, 330, "系统上下文", "sm", anchor="middle"))
    body.append(txt(x0 + 4 * (bw + gap) + bw / 2, 330, "系统能力", "sm", anchor="middle"))

    body.append(rect(24, 384, 952, 84, fill="#121318"))
    body.append(txt(46, 416, "EchoLeak（CVE-2025-32711，CVSS 3.1 = 9.3）", "hd", fill="#cf5a50", size=20))
    body.append(txt(46, 446, "邮件 → Copilot 检索 → 指令被当成任务 → 生成带数据的链接 → 借 Teams 代理外发；用户零点击。", "sm", size=14))

    body.append(rect(24, 490, 952, 62, fill="#14161c"))
    body.append(txt(46, 518, "单点看：读邮件、生成链接、访问 Teams，都是合法操作。", "sm", size=14))
    body.append(txt(46, 542, "连起来看：一条从外部文本到内部数据的完整外发通道。", "sm", size=14, fill="#c9a96a"))
    return svg(w, h, "提示注入的完整链路", "\n".join(body))


# ---------------------------------------------------------------- s02
def s02():
    w, h = 1000, 600
    body = []
    body.append(txt(36, 48, "六条投递通道", "ttl"))
    body.append(txt(36, 76, "只防聊天框，等于只关了六扇门里的一扇。", "sub"))

    cards = [
        ("01", "直接输入", "当前用户", "提交时", "聊天框、表单、API 参数"),
        ("02", "间接内容", "网页 / 邮件 / 文档作者", "检索、读取时", "EchoLeak、Slack AI"),
        ("03", "持久化存储", "知识库 / 记忆写入者", "后续每次会话", "被污染的 RAG、恶意记忆"),
        ("04", "工具输出", "API / MCP / 代码输出", "工具返回时", "GitHub MCP、插件响应"),
        ("05", "多模态载体", "图片 / 音频上传者", "OCR、视觉编码时", "截图、发票、语音消息"),
        ("06", "供应链", "插件 / 权重 / 依赖作者", "安装、加载时", "恶意 MCP server、后门权重"),
    ]
    cw, ch, gx, gy = 300, 152, 20, 22
    x0, y0 = 30, 126
    for i, (num, title, who, when, example) in enumerate(cards):
        col, row = i % 3, i // 3
        x = x0 + col * (cw + gx)
        y = y0 + row * (ch + gy)
        body.append(rect(x, y, cw, ch))
        body.append(txt(x + 16, y + 28, num, "mono", fill="#c9a96a"))
        body.append(txt(x + 48, y + 29, title, "hd", size=19))
        body.append(txt(x + 16, y + 60, "写入者", "xs"))
        body.append(txt(x + 76, y + 60, who, "sm", size=14))
        body.append(txt(x + 16, y + 88, "触发点", "xs"))
        body.append(txt(x + 76, y + 88, when, "sm", size=14))
        body.append(txt(x + 16, y + 116, "典型", "xs"))
        body.append(txt(x + 76, y + 116, example, "sm", size=14))

    body.append(line(130, 500, 870, 500, marker=True))
    body.append(txt(130, 530, "离模型越近", "sm", anchor="middle"))
    body.append(txt(500, 530, "检测难度 →", "xs", anchor="middle"))
    body.append(txt(870, 530, "离权限越近", "sm", anchor="middle"))
    body.append(txt(36, 574, "越靠右，payload 越容易藏在正常业务里；越靠下，一次写入的影响越持久。", "foot"))
    return svg(w, h, "六条投递通道", "\n".join(body))


# ---------------------------------------------------------------- s03
def s03():
    w, h = 1000, 620
    body = []
    body.append(txt(36, 48, "三层防御，各管一段", "ttl"))
    body.append(txt(36, 76, "模型层降概率，系统层给边界，权限层限后果。", "sub"))

    layers = [
        ("模型层", "降低「数据被当成指令」的概率", ["指令层级", "Spotlighting", "SecAlign"], "剩下：被说服的概率", "#c9a96a"),
        ("系统层", "让不可信数据流不到敏感汇", ["双 LLM", "CaMeL", "污点追踪"], "剩下：策略覆盖不全", "#7aa2c8"),
        ("权限层", "让被骗之后的损失有上限", ["最小权限", "人工确认", "出网白名单"], "剩下：合法调用的组合", "#8fbf7a"),
    ]
    y = 126
    for name, goal, chips, residual, color in layers:
        body.append(rect(30, y, 940, 128, fill="#121318"))
        body.append(f'<rect x="30" y="{y}" width="8" height="128" rx="4" fill="{color}" fill-opacity=".8"/>')
        body.append(txt(56, y + 36, name, "hd", fill=color))
        body.append(txt(56, y + 62, goal, "sm", size=14))
        cx = 56
        for chip in chips:
            cw = 40 + len(chip) * 14
            body.append(rect(cx, y + 82, cw, 30, fill="#191b22", stroke=color, rx=8))
            body.append(txt(cx + cw / 2, y + 103, chip, "sm", anchor="middle", fill="#e8e4dc", size=14))
            cx += cw + 12
        body.append(txt(944, y + 56, residual, "sm", anchor="end", fill=color, size=14))
        y += 160

    body.append(line(500, 254, 500, 282, marker=True))
    body.append(line(500, 414, 500, 442, marker=True))

    body.append(rect(30, 576, 940, 32, fill="#14161c"))
    body.append(txt(500, 598, "57.7% → 7.95% 是模型层的成绩；7.95% 不再变成 9.3，是后两层的工作。", "sm", anchor="middle", fill="#c9a96a", size=14))
    return svg(w, h, "三层防御与各自残余风险", "\n".join(body))


# ---------------------------------------------------------------- s04
def s04():
    w, h = 1000, 580
    body = []
    body.append(txt(36, 48, "报告中的 ASR 与它没说的部分", "ttl"))
    body.append(txt(36, 76, "同一张图里的数字来自不同设置，只能看量级，不能排名。", "sub"))

    body.append(rect(30, 110, 600, 420, fill="#121318"))
    body.append(txt(52, 144, "攻击成功率（ASR，%）", "hd", size=20))
    bars = [
        ("GPT-4o 无防御", 57.7, "#cf5a50", "57.7"),
        ("+ 提示注入检测器", 7.95, "#c9a96a", "7.95"),
        ("+ 工具过滤器", 6.84, "#c9a96a", "6.84"),
        ("LLMail GPT-4o", 58.0, "#cf5a50", "58.0"),
        ("Spotlighting", 2.0, "#7aa2c8", "<2"),
        ("SecAlign", 10.0, "#7aa2c8", "<10"),
    ]
    x0, x1, maxv = 196, 590, 60.0
    y = 176
    for label, v, color, shown in bars:
        bw = max(3, (v / maxv) * (x1 - x0))
        body.append(txt(52, y + 16, label, "sm", size=14))
        body.append(rect(x0, y, bw, 24, fill=color, stroke=color, rx=4))
        body.append(txt(x0 + bw + 8, y + 17, shown, "sm", fill=color, size=14))
        y += 52

    body.append(txt(52, 490, "相对降幅 86.2%，绝对残余 7.95%。1,000 次攻击，仍有约 80 次成功。", "sm", size=13, fill="#c9a96a"))

    body.append(rect(650, 110, 320, 420, fill="#121318"))
    body.append(txt(672, 144, "任务完成率（%）", "hd", size=20))
    body.append(txt(672, 170, "CaMeL 的代价", "sm", size=14))
    ux0, ux1, umax = 748, 950, 100.0
    ubars = [("未防御", 84, "#8a8578"), ("CaMeL", 77, "#7aa2c8")]
    y = 216
    for label, v, color in ubars:
        bw = (v / umax) * (ux1 - ux0)
        body.append(txt(672, y + 18, label, "sm", size=14))
        body.append(rect(ux0, y, bw, 30, fill=color, stroke=color, rx=4))
        body.append(txt(ux0 + bw + 8, y + 21, str(v), "sm", fill=color, size=14))
        y += 76
    body.append(txt(672, 400, "可证明安全", "sm", fill="#7aa2c8", size=14))
    body.append(txt(672, 426, "不是零成本：策略要写全，", "xs", size=13))
    body.append(txt(672, 448, "开放式任务会掉点。", "xs", size=13))
    body.append(txt(672, 492, "AgentDojo，97 任务 / 629 用例", "xs", size=12))

    body.append(txt(36, 562, "注：Spotlighting、SecAlign 的数字来自各自论文设置；CaMeL 是任务完成率，不是 ASR。", "foot", size=13))
    return svg(w, h, "ASR 与任务完成率的报告口径", "\n".join(body))


# ---------------------------------------------------------------- s05
def s05():
    w, h = 1000, 690
    body = []
    body.append(txt(36, 48, "从任务结构到防御形态", "ttl"))
    body.append(txt(36, 76, "先问四个问题；答案决定你要做到哪一层。", "sub"))

    spine_x, spine_w = 180, 340
    qs = [
        ("Q1", "模型会读外部内容？", "邮件、网页、文档、工具输出"),
        ("Q2", "有会写数据的工具？", "发邮件、发公开内容、改文件"),
        ("Q3", "能触达敏感数据或外网？", "私有仓库、客户数据、任意 URL"),
        ("Q4", "动作不可逆或跨边界？", "转账、删除、授权、跨租户"),
    ]
    outs = [
        ("低风险", "输入隔离 + 输出审核", "#8fbf7a"),
        ("只读场景", "Spotlighting + 检测器 + 输出审核", "#7aa2c8"),
        ("中风险", "能力分离 + 全链路审计", "#c9a96a"),
        ("高风险", "最小权限 + 人工确认 + 出网白名单", "#cf5a50"),
    ]
    y = 120
    for i, (q, text, sub) in enumerate(qs):
        body.append(rect(spine_x, y, spine_w, 92, fill="#121318"))
        body.append(txt(spine_x + 16, y + 26, q, "mono", fill="#c9a96a"))
        body.append(txt(spine_x + 48, y + 27, text, "hd", size=19))
        body.append(txt(spine_x + 16, y + 58, sub, "sm", size=13))
        if i < 3:
            body.append(line(spine_x + spine_w / 2, y + 92, spine_x + spine_w / 2, y + 122, marker=True))
            body.append(txt(spine_x + spine_w / 2 + 8, y + 112, "是", "xs"))
        ox = 610
        body.append(line(spine_x + spine_w + 2, y + 46, ox - 6, y + 46, marker=True))
        body.append(txt(spine_x + spine_w + 12, y + 38, "否", "xs"))
        body.append(rect(ox, y, 360, 92, fill="#14161c", stroke=outs[i][2]))
        body.append(txt(ox + 16, y + 28, outs[i][0], "hd", fill=outs[i][2], size=19))
        body.append(txt(ox + 16, y + 56, outs[i][1], "sm", size=14))
        if i == 3:
            body.append(txt(ox + 16, y + 78, "前三条已成立，按高风险处理", "xs", size=12))
        y += 128

    body.append(line(spine_x + spine_w / 2, 632, spine_x + spine_w / 2, 654, marker=True))
    body.append(txt(spine_x + spine_w / 2 + 8, 648, "是", "xs"))
    body.append(rect(spine_x, 656, spine_w + 430, 24, fill="#1a1416", stroke="#cf5a50"))
    body.append(txt(spine_x + 14, 674, "四个都是「是」：最高风险，上双 LLM / CaMeL，先证明权限边界。", "sm", size=13, fill="#e8e4dc"))

    return svg(w, h, "从任务结构到防御形态", "\n".join(body))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    figs = {"s01-attack-chain.svg": s01, "s02-taxonomy.svg": s02,
            "s03-defense-stack.svg": s03, "s04-benchmark-gap.svg": s04,
            "s05-decision-flow.svg": s05}
    for name, fn in figs.items():
        p = os.path.join(OUT, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(fn())
        print("wrote", p, os.path.getsize(p), "bytes")
