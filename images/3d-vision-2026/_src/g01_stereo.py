#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s12-stereo-3d.svg —— 双目三角测量的真三维几何。

核心：把 ε_z = z²·ε_d /(b·f) 这条公式变成可以"看见"的几何。
两个相机中心、光心连线（基线）、两束视线交于工件上的点 P；
纵向放大率是 f/b，是常数 —— 所以同样的视差误差 ε_d，
在远处引起的深度误差被z 拉长，这就是 z² 的来源。
"""
import math
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from svg3d import *  # noqa
from fitcam import fit_camera

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 's12-stereo-3d.svg')

W, H = 1200, 700
fig = Fig(w=W, h=H,
          title="双目：把 z² 画成几何，而不是公式",
          sub="纵向放大率 f/b 是常数；同样的视差误差，在远处被 z 拉得更长")

# ---------- 相机与场景 ----------
# 工作单位：mm。基线 b=60，焦距 f=400，被测距离 z 变化。
B, F = 60.0, 400.0
L = v(-B / 2, 0, 0)
R = v(+B / 2, 0, 0)

CAM_CX, CAM_CY, CAM_VH = 392, 348, 600
FIG_W, FIG_H = 730, 500

_bnd = []
for _x in (-300, 300):
    for _z in (-90, 700):
        _bnd.append([_x, -90, _z])
for _z in (0, 150, 330, 560):
    _bnd.append([0, 90, _z])
# azim 取负，让深度轴（+Z）在画面上向右展开、相机落在左侧，符合阅读顺序
_eye, _tgt, _fov = fit_camera(np.array(_bnd), FIG_W, FIG_H, CAM_CX, CAM_CY,
                              CAM_VH, azim=-56, elev=23, pad=1.04, fov=30)
cam = Cam(eye=_eye, target=_tgt, fov=_fov, cx=CAM_CX, cy=CAM_CY, vh=CAM_VH)

z0 = cam.view(np.array([v(0, 0, z) for z in (0, 150, 330, 560)]))[:, 2]
dmin, dmax = float(z0.min()), float(z0.max())

fig.grid3(cam, -90, (-300, 300), (-90, 700), step=79, wdt=0.7, opacity=0.2,
          dmin=dmin, dmax=dmax)

# 相机机体
def cam_body(c):
    """简化相机机体：机身 + 朝 +Z 的镜筒，光心用小点标出。"""
    fig.box3(cam, c + v(0, 0, -30), v(52, 44, 54), BLUE, fill=BLUE,
             opacity=0.34, dmin=dmin, dmax=dmax, fade=0.4, wdt=1.3)
    fig.box3(cam, c + v(0, 0, 12), v(26, 26, 38), BLUE, fill=BLUE,
             opacity=0.46, dmin=dmin, dmax=dmax, fade=0.4, wdt=1.2)
    fig.dot3(cam, c, 3.0, FG, dmin=dmin, dmax=dmax, fade=0.2)

# 两个相机标签都放在机体下方，避开基线与视线
fig.label3(cam, L + v(0, -6, -34), "左相机", "lb", fill=BLUE,
           dx=-10, dy=18, anchor="end")
fig.label3(cam, R + v(0, -6, -34), "右相机", "lb", fill=BLUE,
           dx=10, dy=18, anchor="start")

cam_body(L)
cam_body(R)

# 光轴（沿 +Z）
for c, nm in ((L, "左相机"), (R, "右相机")):
    fig.line3(cam, c, c + v(0, 0, 760), mix(BLUE, BG, 0.35), 1.0, dash="5 4",
              dmin=dmin, dmax=dmax, fade=0.2)

# 基线（抬高到机��上方，标签再上移，与相机标签彻底分层）
fig.line3(cam, L + v(0, 74, 0), R + v(0, 74, 0), GOLD, 2.2,
          dmin=dmin, dmax=dmax, fade=0.0)
fig.label3(cam, v(0, 84, 0), "基线 b = 60 mm", "lb", fill=GOLD, dx=0, dy=-8,
           anchor="middle", mono=True)

# ---------- 三个距离上的工件点 ----------
DEPTHS = [(150.0, "z = 150 mm"), (330.0, "z = 330 mm"), (560.0, "z = 560 mm")]
ed = 0.5   # 视差误差，单位：px（示例值）
K = 6.0    # 误差棒放大倍数，便于观察

fig.text2(44, 112, "同一视差误差 ε_d = 0.5 px，在三个距离上给出的深度误差", "sm")

rows = []
for z, lbl in DEPTHS:
    P = v(0, 0, z)
    disp = F * B / z               # 视差 d = f·b / z  (px)
    eps_z = z * z * ed / (B * F)   # ε_z = z²·ε_d /(b·f)
    rows.append((z, lbl, disp, eps_z, P))

# 视线与误差棒
for z, lbl, disp, eps_z, P in rows:
    fig.line3(cam, L, P, mix(GOLD, BG, 0.25), 1.3, dmin=dmin, dmax=dmax, fade=0.15)
    fig.line3(cam, R, P, mix(GOLD, BG, 0.25), 1.3, dmin=dmin, dmax=dmax, fade=0.15)
    fig.line3(cam, P, P + v(0, 0, eps_z * K), RED, 3.0,
              dmin=dmin, dmax=dmax, fade=0.0)
    fig.dot3(cam, P, 4.0, GOLD, dmin=dmin, dmax=dmax, fade=0.15)
    fig.dot3(cam, P + v(0, 0, eps_z * K), 3.2, RED, ring=True, wdt=1.8,
             dmin=dmin, dmax=dmax, fade=0.0)

# 标签统一排布：距离标签抬到工件上方并横向错开；
# 误差数值用引线拉到网格上方空白带，彻底避开网格线与视线
for i, (z, lbl, disp, eps_z, P) in enumerate(rows):
    fig.label3(cam, P + v(0, 34, 0), lbl, "lb", fill=FG,
               dx=-14 + i * 6, dy=-14 - i * 20, anchor="middle", mono=True)

# 引线从误差棒末端出发，斜拉到统一标注车道；车道按屏幕横向错开，避免引线交叉
_tips = []
for z, lbl, disp, eps_z, P in rows:
    tx, ty, _, _ = cam.project(np.atleast_2d(P + v(0, 0, eps_z * K)))
    _tips.append((tx[0], ty[0], eps_z))

_lane = min(t[1] for t in _tips) - 96
for i, (tx, ty, eps_z) in enumerate(_tips):
    ly = _lane + i * 24
    lx = tx + 34 + i * 6
    fig.texts.append(
        f'<line x1="{fmt(tx)}" y1="{fmt(ty)}" x2="{fmt(lx - 4)}" '
        f'y2="{fmt(ly - 4)}" stroke="{mix(RED, BG, 0.3)}" stroke-width="1"/>')
    fig.text2(lx + 4, ly, f"ε_z {eps_z:.2f}", "xs", fill=RED, mono=True)

# ---------- 右栏：数字对照 ----------
x0 = 800
fig.rect2(x0 - 22, 96, 356, 214, fill="#14161c", stroke=GRAY, rx=10, wdt=1.2)
fig.text2(x0, 122, "误差棒长度已放大 6 倍", "xs", fill=DIM)
fig.text2(x0, 148, "距离 z", "xs")
fig.text2(x0 + 130, 148, "视差 d", "xs")
fig.text2(x0 + 250, 148, "ε_z", "xs")
fig.hline(x0, x0 + 320, 158, GRAY, 1, 0.35)

y = 180
for z, lbl, disp, eps_z, _P in rows:
    fig.text2(x0, y, f"{z:.0f} mm", "sm")
    fig.text2(x0 + 130, y, f"{disp:.0f} px", "mon", anchor="end")
    fig.text2(x0 + 250, y, f"{eps_z:.2f} mm", "mon", anchor="end", fill=RED)
    y += 26

fig.text2(x0, y + 6, "距离翻 2 倍，ε_z 变 4 倍", "sm", fill=GOLD)

# 为什么：纵向放大率是常数
fig.rect2(x0 - 22, 330, 356, 186, fill="#1a1712", stroke=GOLD, rx=10,
          wdt=1.2, opacity=0.5)
fig.text2(x0, 358, "为什么是二次的", "hd", fill=GOLD)
fig.text2(x0, 386, "纵向放大率 m_v = f / b = 400 / 60 ≈ 6.7", "mon")
fig.text2(x0, 410, "这是一个与距离无关的常数。", "sm")
fig.text2(x0, 436, "视差误差 ε_d 在像面上是固定的", "sm")
fig.text2(x0, 456, "→ 折算到纵向就是 ε_z = ε_d · z² /(b·f)", "sm", fill=GOLD)
fig.text2(x0, 482, "z 出现在平方里，因为它既缩短视差，", "xs", fill=MUT)
fig.text2(x0, 498, "又把这段纵向长度放大。", "xs", fill=MUT)

# ---------- 底部：四个变量里哪个能拧 ----------
fig.rect2(22, 556, 1134, 92, fill="#14161c", stroke=GRAY, rx=10, wdt=1.2)
fig.text2(44, 582, "误差公式里四个变量，只有两个真能拧", "hd")
cells = [("z 工作距离", "最大杠杆", "移远一倍 → 精度差 4 倍", RED),
         ("b 基线", "线性改善", "加宽基线是最直接的手段", GOLD),
         ("f 焦距", "线性改善", "但同时压窄视场", GOLD),
         ("ε_d 亚像素", "依赖亚像素算法", "现实里最难达标的一项", MUT)]
cx = 44
for name, kind, note, col in cells:
    fig.text2(cx, 606, name, "lb", fill=FG)
    fig.text2(cx, 624, kind, "xs", fill=col)
    fig.text2(cx + 92, 624, note, "xs", fill=DIM)
    cx += 282

fig.text2(44, 674,
          "几何按真实比例绘制：b = 60 mm，f = 400 px，工件沿光轴摆放；误差棒为便于观察放大 6 倍。",
          "foot")

fig.save(OUT)
print("wrote", OUT)
print(f"{'z':>8}{'d(px)':>10}{'eps_z':>10}")
for z, lbl, disp, eps_z, _P in rows:
    print(f"{z:8.0f}{disp:10.1f}{eps_z:10.3f}")
