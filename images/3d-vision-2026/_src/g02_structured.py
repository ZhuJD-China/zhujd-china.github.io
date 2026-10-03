#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s13-structured-light-3d.svg —— 结构光三角测量的真三维几何。

要讲清的事：d = b·sinα / sin(α+β) 里，α 与 β 各自偏一点会把深度
推向不同方向；而且这个放大倍数随 β 增大而急剧变差。
把投射器、相机、工件摆成真实三角，用"角误差 → 深度误差"的箭头画出来。
"""
import math
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from svg3d import *  # noqa
from fitcam import fit_camera

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 's13-structured-light-3d.svg')

W, H = 1200, 724
fig = Fig(w=W, h=H,
          title="结构光：α 与 β 各偏一点，深度就跑到别处",
          sub="同一个三角，深度对两个角的敏感度差得很远——β 越大越糟")

# ---------- 几何参数（mm / 度） ----------
B = 300.0          # 投射器与相机的横向距离
ALPHA = 30.0       # 投射角（投射器相对基线法线）
BETA = 15.0        # 观察角（相机相对基线法线）
D = B * math.sin(math.radians(ALPHA)) / math.sin(math.radians(ALPHA + BETA))

# 工件点 P：位于深度 d 处、法线方向偏一个横向位置
Pj = v(-B / 2, 0, 0)      # 投射器
Cj = v(+B / 2, 0, 0)      # 相机
P = v(0.0, 0.0, D)
NORMAL = v(0, 1, 0)

# 表面法线：让工件看起来是一块斜面，法线朝上偏
SURF_R = rot(0, 0, -18)

CAM_CX, CAM_CY, CAM_VH = 372, 330, 600
FIG_W, FIG_H = 700, 480

_bnd = [Pj + v(-70, -70, -70), Pj + v(70, 70, 70),
        Cj + v(-70, -70, -70), Cj + v(70, 70, 70),
        P + v(-90, -90, -90), P + v(90, 90, 90)]
_eye, _tgt, _fov = fit_camera(np.array(_bnd), FIG_W, FIG_H, CAM_CX, CAM_CY,
                              CAM_VH, azim=-64, elev=34, pad=1.12, fov=30)
cam = Cam(eye=_eye, target=_tgt, fov=_fov, cx=CAM_CX, cy=CAM_CY, vh=CAM_VH)

_pts = np.array([Pj, Cj, P, P + v(120, 0, 0), P + v(-120, 0, 0)])
zz = cam.view(_pts)[:, 2]
dmin, dmax = float(zz.min()), float(zz.max())

fig.grid3(cam, -110, (-260, 260), (-60, 420), step=64, wdt=0.7, opacity=0.2,
          dmin=dmin, dmax=dmax)

# ---------- 工件：一块带条纹的斜板 ----------
def surface_point(u, w):
    """板面参数 (u 沿板宽, w 沿板法向) → 三维点。板中心在 P。"""
    local = v(u, w, 0)
    return P + SURF_R @ local

U0, U1 = -110, 110
W0, W1 = -46, 46
corners = [surface_point(U0, W0), surface_point(U1, W0),
           surface_point(U1, W1), surface_point(U0, W1)]
fig.poly3(cam, corners, GOLD, fill=GOLD, opacity=0.20, wdt=1.4,
          dmin=dmin, dmax=dmax, fade=0.35)

# 条纹：沿板面画一组平行线，说明"投射的是条纹而不是一束光"
for i in range(7):
    u = U0 + (U1 - U0) * (i + 0.5) / 7.0
    fig.line3(cam, surface_point(u, W0), surface_point(u, W1),
              mix(GOLD, BG, 0.35), 1.5, dmin=dmin, dmax=dmax, fade=0.25)

# 板面法线
fig.line3(cam, P, P + NORMAL * 110, GREEN, 1.6, dash="4 3",
          dmin=dmin, dmax=dmax, fade=0.2)

# ---------- 投射器与相机 ----------
def head(c, col, tag, tagdx, tagdy):
    # 机体做小，避免遮挡基线与两条视线
    fig.box3(cam, c + v(0, -4, 0), v(58, 50, 64), col, fill=col,
             opacity=0.30, dmin=dmin, dmax=dmax, fade=0.4, wdt=1.2)
    fig.box3(cam, c + v(0, 22, 0), v(28, 22, 30), col, fill=col,
             opacity=0.42, dmin=dmin, dmax=dmax, fade=0.4, wdt=1.1)
    fig.dot3(cam, c, 2.8, FG, dmin=dmin, dmax=dmax, fade=0.2)
    fig.label3(cam, c + v(0, -22, 0), tag, "lb", fill=col,
               dx=tagdx, dy=tagdy, anchor="middle")

head(Pj, GOLD, "结构光投射器", 0, 16)
head(Cj, BLUE, "相机", 0, 16)

# ---------- 两条视线 ----------
fig.line3(cam, Pj, P, mix(GOLD, BG, 0.15), 1.8, arrow=True,
          dmin=dmin, dmax=dmax, fade=0.1)
fig.line3(cam, Cj, P, mix(BLUE, BG, 0.15), 1.8, arrow=True,
          dmin=dmin, dmax=dmax, fade=0.1)
fig.dot3(cam, P, 4.4, FG, dmin=dmin, dmax=dmax, fade=0.1)

# 角标注：α 是"基线"与"投射器→工件"之间的夹角，β 同理。
# 所以角弧要画在各自光心处，参考边选基线方向，不是竖直参考线。
BASE_DIR_L = norm(P - Pj) + v(0, 0, 0)
# 竖直参考线只作视觉辅助，短一点，不与视线混淆
for c, tag, col, sgn in ((Pj, "α", GOLD, -1), (Cj, "β", BLUE, +1)):
    fig.line3(cam, c + v(0, 40, 0), c + v(0, 84, 0), GRAY, 1.0, dash="3 3",
              dmin=dmin, dmax=dmax, fade=0.25)
# α / β 的弧线：用基线方向与视线方向的实际夹角画一段圆弧
import math as _mm


def angle_arc(center, a_pt, b_pt, radius, color):
    """在center 处画 a→b 夹角的圆弧（用 12 段折线近似）。"""
    a = norm(np.asarray(a_pt, float) - np.asarray(center, float))
    b = norm(np.asarray(b_pt, float) - np.asarray(center, float))
    ang = _mm.acos(max(-1.0, min(1.0, float(a @ b))))
    if ang < 1e-3:
        return
    axis = norm(np.cross(a, b))
    if np.linalg.norm(axis) < 1e-9:
        return
    axis = norm(axis)
    pts = []
    for i in range(13):
        t = ang * i / 12.0
        # Rodrigues 旋转 a 绕 axis 角 t
        pts.append(np.asarray(center, float)
                   + radius * (a * _mm.cos(t)
                               + np.cross(axis, a) * _mm.sin(t)))
    for i in range(len(pts) - 1):
        fig.line3(cam, pts[i], pts[i + 1], color, 1.4,
                  dmin=dmin, dmax=dmax, fade=0.15)


# α / β 标签贴着各自圆弧中点放置（弧线在视线与基线法向之间）
angle_arc(Pj, v(-B / 2, 0, D), P, 96, GOLD)
angle_arc(Cj, v(+B / 2, 0, D), P, 96, BLUE)


def arc_mid(center, a_pt, b_pt, radius):
    a = norm(np.asarray(a_pt, float) - np.asarray(center, float))
    b = norm(np.asarray(b_pt, float) - np.asarray(center, float))
    ang = _mm.acos(max(-1.0, min(1.0, float(a @ b))))
    axis = np.cross(a, b)
    if np.linalg.norm(axis) < 1e-9:
        return None
    axis = norm(axis)
    t = ang / 2.0
    return (np.asarray(center, float)
            + radius * (a * _mm.cos(t) + np.cross(axis, a) * _mm.sin(t)))


_ma = arc_mid(Pj, v(-B / 2, 0, D), P, 96)
_mb = arc_mid(Cj, v(+B / 2, 0, D), P, 96)
if _ma is not None:
    fig.label3(cam, _ma, "α", "lb", fill=GOLD, dx=-8, dy=4, anchor="end")
if _mb is not None:
    fig.label3(cam, _mb, "β", "lb", fill=BLUE, dx=8, dy=4, anchor="start")

fig.label3(cam, v(0, 118, 0), "基线 b = 300 mm", "lb", fill=GRAY,
           dx=0, dy=-8, anchor="middle", mono=True)
fig.line3(cam, Pj + v(0, 118, 0), Cj + v(0, 118, 0), GRAY, 1.6,
          dmin=dmin, dmax=dmax, fade=0.0)
fig.label3(cam, P + v(0, 118, 0), "d = b·sinα / sin(α+β)", "lb", fill=GOLD,
           dx=0, dy=-10, anchor="middle", mono=True)

# ---------- 角误差 → 深度误差（右侧数值栏） ----------
x0 = 760
fig.rect2(x0 - 22, 96, 416, 250, fill="#14161c", stroke=GRAY, rx=10, wdt=1.2)
fig.text2(x0, 122, "角误差放大成深度误差", "hd", fill=FG)
fig.text2(x0, 144, f"基准：α = {ALPHA:.0f}°，β = {BETA:.0f}°，b = {B:.0f} mm，d = {D:.1f} mm", "xs", fill=DIM)

fig.text2(x0, 176, "角偏差", "xs")
fig.text2(x0 + 118, 176, "Δd", "xs")
fig.text2(x0 + 210, 176, "相对深度误差", "xs")
fig.hline(x0, x0 + 384, 186, GRAY, 1, 0.35)

y = 208
rows = []
# 注意：d_alpha / d_beta 是「度」，只在这里做一次度→弧度转换
for d_alpha in (-1.0, +1.0):
    # α 变时分母里的总夹角 α+β 也要跟着变，否则算成"只改分子"的假差分
    dd = (B * math.sin(math.radians(ALPHA + d_alpha))
          / math.sin(math.radians(ALPHA + d_alpha + BETA)) - D)
    rows.append((f"α {d_alpha:+.0f}°", dd, dd / D))
    fig.text2(x0, y, f"α {d_alpha:+.0f}°", "sm")
    fig.text2(x0 + 118, y, f"{dd:+.1f} mm", "mon", anchor="end")
    fig.text2(x0 + 210, y, f"{dd / D * 100:+.1f} %", "mon", anchor="end",
              fill=RED)
    y += 26
for d_beta in (-1.0, +1.0):
    dd = (B * math.sin(math.radians(ALPHA))
          / math.sin(math.radians(ALPHA + BETA + d_beta)) - D)
    rows.append((f"β {d_beta:+.0f}°", dd, dd / D))
    fig.text2(x0, y, f"β {d_beta:+.0f}°", "sm")
    fig.text2(x0 + 118, y, f"{dd:+.1f} mm", "mon", anchor="end")
    fig.text2(x0 + 210, y, f"{dd / D * 100:+.1f} %", "mon", anchor="end",
              fill=RED)
    y += 26

fig.hline(x0, x0 + 384, y - 12, GRAY, 1, 0.25)
sens_a = abs(rows[0][1])
sens_b = abs(rows[2][1])
fig.text2(x0, y + 12, f"同样 1° 角偏差：α 敏感度 {sens_a:.2f} mm，β 敏感度 {sens_b:.2f} mm",
          "sm", fill=GOLD)
fig.text2(x0, y + 34, f"在这组几何里，β 的影响是 α 的 {sens_b / sens_a:.1f} 倍",
          "sm", fill=RED)

# 数值自检：±1° 单侧差分与解析灵敏度对得上（允许二阶截断误差）
import math as _m
_an_a = (B * _m.sin(_m.radians(BETA))
         / _m.sin(_m.radians(ALPHA + BETA)) ** 2 * _m.radians(1.0))
_an_b = (B * _m.sin(_m.radians(ALPHA))
         * abs(_m.cos(_m.radians(ALPHA + BETA)))
         / _m.sin(_m.radians(ALPHA + BETA)) ** 2 * _m.radians(1.0))
#单侧 ±1° 差分有 1~2% 的二阶截断误差，取容差 4%
assert abs(sens_a - _an_a) < _an_a * 0.04, (sens_a, _an_a)
assert abs(sens_b - _an_b) < _an_b * 0.04, (sens_b, _an_b)

# 机理：相对灵敏度
fig.rect2(x0 - 22, 372, 416, 208, fill="#1a1712", stroke=GOLD, rx=10,
          wdt=1.2, opacity=0.5)
fig.text2(x0, 400, "相对灵敏度：α 与 β 不对称", "hd", fill=GOLD)
fig.text2(x0, 428, "把上表的 Δd/d 除以 1°（0.01745 rad），", "sm")
fig.text2(x0, 450, "得到每弧度的相对深度误差：", "sm")
fig.text2(x0, 476, "α：sinβ /(sinα·sin(α+β))", "mon", fill=BLUE)
fig.text2(x0, 498, "β：|cot(α+β)|", "mon", fill=GOLD)
fig.text2(x0, 524, "β 的表达式里没有 α，只看总夹角：", "xs", fill=MUT)
fig.text2(x0, 542, "α+β = 90° 时最稳，偏离越大越糟。", "xs", fill=MUT)
fig.text2(x0, 562, "所以真正难测的是「斜着看过去」的表面。", "sm", fill=RED)

# 底部：三段结论
fig.rect2(22, 596, 1134, 84, fill="#14161c", stroke=GRAY, rx=10, wdt=1.2)
fig.text2(44, 622, "结构光和双目共享同一个结论", "hd")
items = [("三角测量", "深度误差 ∝ 角误差", GOLD),
         ("角精度", "取决于相位/条纹解算，不是几何", BLUE),
         ("斜面工件", "α+β 偏离 90° 时 β 灵敏度飙升", RED)]
cx = 44
for a, b, col in items:
    fig.text2(cx, 650, a, "lb", fill=col)
    fig.text2(cx + 96, 650, b, "sm", fill=DIM)
    cx += 372

fig.text2(44, 700,
          "三角按真实比例绘制：b = 300 mm，α = 30°，β = 15°，得 d ≈ 212 mm；Δd 为角偏差 ±1° 时的解析结果。",
          "foot")

fig.save(OUT)
print("wrote", OUT)
print(f"D = {D:.2f} mm")
for nm, dd, rel in rows:
    print(f"  {nm}: dD={dd:+.2f} mm ({rel*100:+.2f}%)")
print(f"sens_a={sens_a:.3f} sens_b={sens_b:.3f} ratio={sens_b/sens_a:.2f}")
