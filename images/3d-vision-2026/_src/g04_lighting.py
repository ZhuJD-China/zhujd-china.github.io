#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s15-lighting-3d.svg —— 八种照明几何的真三维光路。

每种几何都是真的摆：相机、工件、光源三个刚体按该方式的定义放在三维空间里，
然后按定义算出光线怎么走。反射路径按各方式的物理机制决定：
  * 明场：光从相机同侧来，镜面反射进镜头
  * 暗场：光从相机异侧来，镜面反射 away，漫反射进镜头
  * 背光：光从工件背后穿过来
  * 同轴：光源与镜头共轴，靠半反半透
  * 环形：光源环绕镜头，同轴但无遮挡
  * 掠射：光源贴着表面、低入射角
  * 散射：光源大面积包围
  * 穹顶：光源整个罩住
"""
import math
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from svg3d import *  # noqa
from fitcam import fit_camera

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 's15-lighting-3d.svg')

W, H = 1200, 800
fig = Fig(w=W, h=H,
          title="八种照明几何：决定「哪束光能进镜头」",
          sub="相机、工件、光源三者的空间关系决定可见信息；换一种摆法，缺陷就换一种表现")

PAD = 26
COLS, ROWS = 4, 2
GAPX, GAPY = 14, 46
CELLW = (W - 2 * PAD - GAPX * (COLS - 1)) / COLS
CELLH = 250

# ---------- 几何预设：光源位置相对于「相机-工件」连线的描述 ----------
# 相机固定在 (0,0,-130)，工件在 (0,0,0)，相机看向 +Z
CAM_POS = v(0, 0, -130)
WORK = v(0, 0, 0)

PRESETS = [
    ("明场（正面）", "同侧入射 · 镜面反射进镜头", GOLD, "front"),
    ("暗场（掠射）", "异侧入射 · 镜面反射 away", RED, "dark"),
    ("背光 / 透射", "光在工件背后 · 只留剪影", GOLD, "back"),
    ("同轴（半反半透）", "光源与镜头共轴", BLUE, "coax"),
    ("环形（包围镜头）", "环绕镜头 · 无遮挡", BLUE, "ring"),
    ("低角度 / 掠射", "入射角接近切向", GOLD, "grazing"),
    ("散射 / 漫射", "大面积均匀包裹", BLUE, "diffuse"),
    ("穹顶 / Dome", "整个罩住工件", BLUE, "dome"),
]


def light_position(kind):
    """按方式返回光源位置（相机固定在 CAM_POS，工件在 WORK）。

    光源半径统一控制在 ±80 以内，避免某种方式把取景撑爆。
    """
    return {
        "front":   v(-58, 72, -30),
        "dark":    v(74, 70, -24),
        "back":    v(14, 58, 100),
        "coax":    v(0, 0, -132),
        "ring":    v(0, 0, -120),
        "grazing": v(-96, 20, 26),
        "diffuse": v(-44, 90, 32),
        "dome":    v(0, 100, 8),
    }[kind]


# ---------- 单格绘制 ----------
def draw_cell(idx, title, sub, col, kind):
    cx = PAD + (idx % COLS) * (CELLW + GAPX) + CELLW / 2
    cy = 130 + (idx // COLS) * (CELLH + GAPY) + CELLH / 2

    fig.rect2(cx - CELLW / 2 - 6, cy - CELLH / 2 - 6, CELLW + 12, CELLH + 12,
              fill="#14161c", stroke=GRAY, rx=9, wdt=1.1, opacity=0.5)
    fig.text2(cx - CELLW / 2 + 2, cy - CELLH / 2 + 14, f"{idx+1}　{title}",
              "lb", fill=col)
    fig.text2(cx - CELLW / 2 + 2, cy - CELLH / 2 + 30, sub, "xs", fill=DIM)

    L = light_position(kind)
    _bnd = np.array([CAM_POS + v(-46, -46, -46), CAM_POS + v(46, 46, 46),
                     WORK + v(-52, -40, -40), WORK + v(52, 40, 52),
                     L + v(-42, -42, -42), L + v(42, 42, 42)])
    _eye, _tgt, _fov = fit_camera(_bnd, CELLW - 16, CELLH - 58, cx, cy + 6, 300,
                                  azim=-56, elev=26, pad=1.0, fov=30)
    cam = Cam(eye=_eye, target=_tgt, fov=_fov, cx=cx, cy=cy + 6, vh=300)

    zz = cam.view(np.array([CAM_POS, WORK, L]))[:, 2]
    dmin, dmax = float(zz.min()), float(zz.max())

    # 工件
    fig.box3(cam, WORK, v(84, 30, 52), GRAY, fill=GRAY, opacity=0.22,
             dmin=dmin, dmax=dmax, fade=0.35, wdt=1.1)

    # 光源：按方式给不同外形（尺寸收敛在格子尺度内）
    if kind == "coax":
        fig.sphere3(cam, L, 14, BLUE, dmin=dmin, dmax=dmax, fade=0.2)
    elif kind == "ring":
        for k in range(7):
            a = 2 * math.pi * k / 7
            fig.sphere3(cam, L + v(20 * math.cos(a), 20 * math.sin(a), 0),
                        6, BLUE, dmin=dmin, dmax=dmax, fade=0.2)
        fig.dot3(cam, L, 3.4, FG, dmin=dmin, dmax=dmax, ring=True, wdt=1.4)
    elif kind == "dome":
        fig.box3(cam, L, v(112, 7, 90), BLUE, fill=BLUE, opacity=0.16,
                 dmin=dmin, dmax=dmax, fade=0.3, wdt=1.1)
    elif kind == "diffuse":
        fig.box3(cam, L, v(92, 52, 30), BLUE, fill=BLUE, opacity=0.20,
                 dmin=dmin, dmax=dmax, fade=0.3, wdt=1.1)
    else:
        fig.sphere3(cam, L, 14, BLUE, dmin=dmin, dmax=dmax, fade=0.2)

    # 相机
    fig.box3(cam, CAM_POS + v(0, 0, 26), v(46, 40, 46), FG, fill=FG,
             opacity=0.16, dmin=dmin, dmax=dmax, fade=0.3, wdt=1.1)
    fig.box3(cam, CAM_POS + v(0, 0, -20), v(26, 26, 32), FG, fill=FG,
             opacity=0.26, dmin=dmin, dmax=dmax, fade=0.3, wdt=1.0)

    # ---- 光路 ----
    def ray(a, b, c2, dash=None, wdt=1.5, fade=0.1):
        fig.line3(cam, a, b, c2, wdt, dash=dash, arrow=True,
                  dmin=dmin, dmax=dmax, fade=fade)

    if kind == "front":
        ray(L, WORK, mix(GOLD, BG, 0.1))
        ray(WORK, CAM_POS, mix(GOLD, BG, 0.1))
    elif kind == "dark":
        ray(L, WORK, mix(RED, BG, 0.1))
        # 镜面反射被弹开，长度收到格内，避免箭头冲出边框
        _n = norm(WORK - L)
        _ref = norm(_n + (CAM_POS - WORK) / np.linalg.norm(CAM_POS - WORK))
        ray(WORK, WORK + _ref * 92, mix(RED, BG, 0.35), wdt=1.3, fade=0.25)
        # 漫反射（散到各方向）里有一小部分进镜头，弱
        fig.line3(cam, WORK, CAM_POS, mix(RED, BG, 0.55), 1.1, dash="3 3",
                  dmin=dmin, dmax=dmax, fade=0.3)
    elif kind == "back":
        ray(L, WORK, mix(GOLD, BG, 0.1))
        # 穿过来的是背景，画面里只剩剪影：镜头看不到细节
        fig.line3(cam, WORK, CAM_POS, mix(GOLD, BG, 0.5), 1.2, dash="4 3",
                  dmin=dmin, dmax=dmax, fade=0.3)
    elif kind == "coax":
        ray(L, WORK, mix(BLUE, BG, 0.1))
        ray(WORK, CAM_POS, mix(BLUE, BG, 0.1))
    elif kind == "ring":
        for k in range(7):
            a = 2 * math.pi * k / 7
            src = L + v(24 * math.cos(a), 24 * math.sin(a), 0)
            ray(src, WORK, mix(BLUE, BG, 0.25), wdt=1.0, fade=0.25)
        ray(WORK, CAM_POS, mix(BLUE, BG, 0.1))
    elif kind == "grazing":
        ray(L, WORK, mix(GOLD, BG, 0.1))
        # 掠射下表面凸起处遮挡、凹陷处受光
        _top = WORK + v(0, 15, 0)
        ray(_top, CAM_POS, mix(GOLD, BG, 0.1))
    elif kind == "diffuse":
        for s in (v(-52, 0, 0), v(52, 0, 0), v(0, 0, 46), v(0, 0, -46)):
            ray(L + s, WORK + s * 0.5, mix(BLUE, BG, 0.3), wdt=1.0, fade=0.3)
        ray(WORK, CAM_POS, mix(BLUE, BG, 0.1))
    else:  # dome
        for s in (v(-64, 0, 0), v(64, 0, 0), v(0, 0, 54), v(0, 0, -54)):
            ray(L + s, WORK + s * 0.6, mix(BLUE, BG, 0.3), wdt=1.0, fade=0.3)
        ray(WORK, CAM_POS, mix(BLUE, BG, 0.1))

    # 图元说明：三个标签按各自屏幕方位分层放置，一律避开机体轮廓
    _lx, _ly, _, _ = cam.project(np.atleast_2d(L))
    _cx2, _cy2, _, _ = cam.project(np.atleast_2d(CAM_POS))
    _wx, _wy, _, _ = cam.project(np.atleast_2d(WORK))
    _half = (CELLW - 16) / 2
    # 光源：始终放在灯珠右侧，越界时才向左收
    _sx = _lx[0] + 14
    if _sx + 24 > cx + _half - 4:
        _sx = _lx[0] - 14
        _sa = "end"
    else:
        _sa = "start"
    fig.text2(_sx, _ly[0] + 4, "光源", "xs", fill=BLUE, anchor=_sa)
    # 相机：左上
    fig.text2(max(_cx2[0] - 12, cx - _half + 30), _cy2[0] - 8, "相机", "xs",
              fill=MUT, anchor="end")
    # 工件：右下
    fig.text2(min(_wx[0] + 14, cx + _half - 26), _wy[0] + 16, "工件", "xs",
              fill=MUT)


for i, (title, sub, col, kind) in enumerate(PRESETS):
    draw_cell(i, title, sub, col, kind)

# ---------- 底部：三句话 ----------
_y = 726
fig.rect2(PAD, _y - 26, W - 2 * PAD, 52, fill="#1a1712", stroke=GOLD, rx=10,
          wdt=1.2, opacity=0.5)
fig.text2(PAD + 20, _y + 2, "读这张图只需要记三件事", "hd", fill=GOLD)
notes = ["① 明场看镜面，暗场把镜面弹走、只留漫反射",
         "② 环形与同轴差别在有没有东西挡住灯",
         "③ 掠射与散射决定「起伏」还是「纹理」被看见"]
cx = PAD + 20
for n in notes:
    fig.text2(cx, _y + 22, n, "sm", fill=MUT)
    cx += 372

fig.text2(44, 792,
          "几何按定义摆放并按各自机制计算反射路径（非厂商光斑实测）；角度示意，非定量光通量。",
          "foot")

fig.save(OUT)
print("wrote", OUT)
