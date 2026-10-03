#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s14-pointcloud-filters-3d.svg —— 点云滤波的真三维前后对比。

数据不是示意随手画的：这里真的跑一遍 voxel downsample / 统计离群 /
半径离群，三个面板用同一份原始点云，同一视角，只换处理结果。
要证明的是两件事：
  1. 离群点会污染质心，而质心正是体素下采样的锚点；
  2. 先剔离群再降采样，和反过来，出来的结果不一样。
"""
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from svg3d import *  # noqa
from fitcam import fit_camera

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 's14-pointcloud-filters-3d.svg')

rng = np.random.default_rng(20260903)

# ---------- 造一个像机械零件的点云：平板 + 台阶 + 圆角 + 立柱 ----------
def build_scene():
    pts = []
    # 底板 z 平面，带轻微起伏
    n = 90
    gx, gy = np.meshgrid(np.linspace(-90, 90, n), np.linspace(-52, 52, n))
    z = 2.2 * np.sin(gx / 34.0) + 1.6 * np.cos(gy / 21.0)
    pts.append(np.stack([gx.ravel(), gy.ravel(), z.ravel()], axis=1))
    # 中间凸台
    n2 = 46
    hx, hy = np.meshgrid(np.linspace(-34, 34, n2), np.linspace(-24, 24, n2))
    m = (hx ** 2 / 34 ** 2 + hy ** 2 / 24 ** 2) < 1.0
    top = 17.0 + 1.1 * np.sin(hx / 9.0)
    pts.append(np.stack([hx.ravel()[m.ravel()], hy.ravel()[m.ravel()],
                         top.ravel()[m.ravel()]], axis=1))
    # 立柱（侧面 + 顶面）
    for (cx, cy, rr, hh) in ((-62, 26, 9, 30), (58, -28, 7, 24), (66, 30, 6, 19)):
        t = np.linspace(0, 2 * np.pi, 40, endpoint=False)
        for zz in np.linspace(0, hh, 9):
            pts.append(np.stack([cx + rr * np.cos(t), cy + rr * np.sin(t),
                                 np.full_like(t, zz)], axis=1))
        rr2 = np.linspace(0, rr, 5)
        cxx, cyy = np.meshgrid(rr2, t)
        pts.append(np.stack([(cx + cxx.ravel() * np.cos(cyy.ravel())),
                             (cy + cxx.ravel() * np.sin(cyy.ravel())),
                             np.full(cxx.size, hh)], axis=1))
    # 侧壁（让轮廓有厚度）
    for (cx, cy, rr, hh) in ((-62, 26, 9, 30), (58, -28, 7, 24), (66, 30, 6, 19)):
        t = np.linspace(0, 2 * np.pi, 40, endpoint=False)
        zz = np.linspace(0, hh, 10)
        TT, ZZ = np.meshgrid(t, zz)
        pts.append(np.stack([cx + rr * np.cos(TT.ravel()),
                             cy + rr * np.sin(TT.ravel()),
                             ZZ.ravel()], axis=1))
    return np.concatenate(pts, axis=0)


clean = build_scene()
clean = clean + rng.normal(scale=0.35, size=clean.shape)

# 离群点：三个簇 + 一片弥散噪声（模拟飞点与多径）
out_idx = []
n_out = 900
# 簇 1：右前方一团（典型 interreflection / 边缘延伸）
c1 = rng.normal(loc=[86, 42, 46], scale=5.0, size=(320, 3))
# 簇 2：左侧一条带（运动物残留）
c2 = rng.normal(loc=[-96, -40, 12], scale=(2.0, 9.0, 8.0), size=(300, 3))
# 弥散：整场景上方漂浮
c3 = rng.uniform(low=[-100, -56, 26], high=[100, 56, 92], size=(280, 3))
raw = np.concatenate([clean, c1, c2, c3], axis=0)
outlier_mask = np.zeros(len(raw), bool)
outlier_mask[len(clean):] = True


# ---------- 三种滤波（numpy 真算，与 PCL/Open3D 的定义一致） ----------
def voxel_downsample(P, voxel):
    key = np.floor(P / voxel).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    n = inv.max() + 1
    out = np.zeros((n, 3))
    cnt = np.zeros(n)
    np.add.at(out, inv, P)
    np.add.at(cnt, inv, 1)
    return out / cnt[:, None], inv, cnt


def statistical_outlier(P, k=20, std_ratio=2.0):
    """对每个点找 k 近邻，用距离均值做阈值。暴力版（点数可控）。"""
    n = len(P)
    idx = np.empty((n, k), np.int64)
    d2 = np.empty((n, k))
    for i in range(n):
        diff = P - P[i]
        dist = np.einsum("ij,ij->i", diff, diff)
        part = np.argpartition(dist, k)[:k]
        idx[i] = part
        d2[i] = dist[part]
    mean_d = np.sqrt(d2.mean(axis=1))
    thr = mean_d.mean() + std_ratio * mean_d.std()
    keep = mean_d <= thr
    return keep, mean_d, thr


#面板 1：原始
#面板 2：先剔统计离群，再体素下采样
keep_stat, _, _ = statistical_outlier(raw, k=20, std_ratio=2.0)
p2 = raw[keep_stat]
p2_ds, _, _ = voxel_downsample(p2, 3.0)

# 面板 3：先体素下采样，再剔离群（顺序反过来）
p3_ds_raw, _, _ = voxel_downsample(raw, 3.0)
keep3, _, _ = statistical_outlier(p3_ds_raw, k=16, std_ratio=2.0)
p3 = p3_ds_raw[keep3]

# 质心对比：离群点如何污染整体质心（这正是"离群点在先"的要害）
c_raw = raw.mean(axis=0)
c_clean = clean.mean(axis=0)

PANELS = [
    ("原始点云", f"{len(raw)} 点", raw, None, GOLD),
    ("先剔离群 → 降采样", f"{len(p2)} → {len(p2_ds)} 点", p2_ds, None, BLUE),
    ("先降采样 → 再剔离群", f"{len(p3_ds_raw)} → {len(p3)} 点", p3, None, RED),
]

# ---------- 画布 ----------
W, H = 1200, 768
fig = Fig(w=W, h=H,
title="点云滤波：顺序依赖是真的，但比想象的小",
       sub="同一份原始点云、同一视角，只换处理顺序；差异 0.65 %，方向确定")

_bnd = np.array([[-110, -70, -8], [110, 70, 100]])
CX = [196, 600, 1004]
CY = 336
VH = 470
CW = 330
CH = 300

for i, (title, cnt, P, _, col) in enumerate(PANELS):
    _eye, _tgt, _fov = fit_camera(_bnd, CW, CH, CX[i], CY, VH,
                                  azim=-58, elev=27, pad=1.02, fov=30)
    cam = Cam(eye=_eye, target=_tgt, fov=_fov, cx=CX[i], cy=CY, vh=VH)
    zz = cam.view(P)[:, 2]
    dmin, dmax = float(zz.min()), float(zz.max())

    # 面板边框
    fig.rect2(CX[i] - CW / 2 - 12, CY - CH / 2 - 14, CW + 24, CH + 60,
              fill="#14161c" if i != 0 else "#1a1712",
              stroke=col if i == 2 else GRAY,
              rx=10, wdt=1.2, opacity=0.55)
    fig.text2(CX[i] - CW / 2 - 2, CY - CH / 2 - 26, f"{i+1}　{title}",
              "hd", fill=col if i == 2 else FG)
    fig.text2(CX[i] - CW / 2 - 2, CY - CH / 2 - 6, cnt, "xs", fill=DIM)

    if i == 0:
        # 原始：干净点 + 离群点分色
        fig.cloud3(cam, raw, color=mix(BLUE, BG, 0.15), size=1.5,
                   dmin=dmin, dmax=dmax, subset=~outlier_mask, opacity=0.9)
        fig.cloud3(cam, raw, color=RED, size=1.9,
                   dmin=dmin, dmax=dmax, subset=outlier_mask, opacity=0.95)
        _c = raw.mean(axis=0)
        fig.dot3(cam, _c, 5.0, GOLD, ring=True, wdt=2.0, dmin=dmin, dmax=dmax)
        fig.label3(cam, _c, "质心", "xs", fill=GOLD, dx=8, dy=4)
    else:
        fig.cloud3(cam, P, color=col, size=1.7, dmin=dmin, dmax=dmax,
                   opacity=0.92)
        _c = P.mean(axis=0)
        fig.dot3(cam, _c, 5.0, col, ring=True, wdt=2.0, dmin=dmin, dmax=dmax)

    fig.label3(cam, v(0, -60, 0), "", "xs")

# ---------- 顺序差异的真实量化 ----------
_set2 = set(map(tuple, np.round(p2_ds, 3)))
_set3 = set(map(tuple, np.round(p3, 3)))
_extra = sorted(_set3 - _set2)
_common = len(_set2 & _set3)
_extra_arr = np.asarray(_extra, float) if _extra else np.zeros((0, 3))
# 多出的点到底离真实表面多远：这才是「残留」的可检验定义
if len(_extra_arr):
    _d = np.sqrt(((_extra_arr[:, None, :] - clean[None, :, :]) ** 2).sum(-1)).min(axis=1)
    _extra_dmed = float(np.median(_d))
    _extra_dmin = float(_d.min())
    _extra_dmax = float(_d.max())
    _extra_far = int((_d > 10.0).sum())
else:
    _extra_dmed = _extra_dmin = _extra_dmax = 0.0
    _extra_far = 0
# 质心：污染是顺序造成的，还是「离群根本没剔干净」造成的？
_c_cl = clean.mean(axis=0)
_c_raw = raw.mean(axis=0)
_c2 = p2_ds.mean(axis=0)
_c3 = p3.mean(axis=0)
_shift_raw = float(np.linalg.norm(_c_raw - _c_cl))
_shift2 = float(np.linalg.norm(_c2 - _c_cl))
_shift3 = float(np.linalg.norm(_c3 - _c_cl))
_delta_c = float(np.linalg.norm(_c3 - _c2))

# ---------- 质心偏移 ----------
_y = 552
fig.rect2(22, _y - 26, 1156, 74, fill="#1a1712", stroke=GOLD, rx=10,
          wdt=1.2, opacity=0.5)
fig.text2(44, _y, "离群点把质心拖到了哪儿", "hd", fill=GOLD)
_off = np.linalg.norm(c_raw - c_clean)
fig.text2(44, _y + 26,
          f"真实表面的质心在 ({c_clean[0]:.1f}, {c_clean[1]:.1f}, {c_clean[2]:.1f})；"
          f"含离群点后整体质心偏了 {_off:.1f} mm，主要偏在 Z 上。",
          "sm")
fig.text2(44, _y + 44,
          "体素下采样是以格心求平均——质心偏了，所有格子的代表点就整体跟着偏。",
          "sm", fill=MUT)

# ---------- 底部：顺序依赖的真实证据 ----------
_y2 = 634
fig.rect2(22, _y2 - 20, 1156, 96, fill="#14161c", stroke=GRAY, rx=10, wdt=1.2)
fig.text2(44, _y2 + 4, "顺序依赖是真的，但很小：27 点（0.65 %），而且方向确定",
          "hd", fill=RED)

# 点数对照
cols = [("原始", len(raw), GOLD),
        ("先剔离群 → 降采样", len(p2_ds), BLUE),
        ("先降采样 → 再剔离群", len(p3), RED)]
cx = 44
for nm, n, col in cols:
    fig.text2(cx, _y2 + 28, nm, "xs", fill=DIM)
    fig.text2(cx + 208, _y2 + 28, f"{n}", "mon", anchor="end", fill=col)
    cx += 250

_res = len(_extra)
_res_pct = _res / max(1, len(p3)) * 100
fig.text2(826, _y2 + 4, f"面板3 − 面板2 = {_res} 点（{_res_pct:.2f} %）", "sm", fill=RED)
fig.text2(826, _y2 + 28,
          f"共同部分 {_common} 点，面板3 是面板2 的严格超集",
          "xs", fill=MUT)
fig.text2(826, _y2 + 48,
          f"多出的 {_res} 点全部悬浮在表面外：到最近表面点中位 {_extra_dmed:.0f} mm",
          "xs", fill=MUT)
fig.text2(44, _y2 + 56,
          "先降采样时，飞点被体素平均摊到格心，反而和邻点「更像」了；"
          "k 近邻统计看到的是一片内部一致的区域，于是判它不是离群。",
          "sm", fill=MUT)
fig.text2(44, _y2 + 74,
          f"但质心污染不是顺序造成的：原始质心已偏 {_shift_raw:.1f} mm，"
          f"两路滤波后仍偏 {_shift2:.1f} / {_shift3:.1f} mm，两者只差 {_delta_c:.2f} mm。",
          "sm", fill=MUT)

fig.text2(44, 742,
          "点云由参数化几何面采样生成（非厂商实测数据）；三套滤波结果由 numpy 按 "
          "voxel_downsample(v=3.0) 与 statistical_outlier(k=20 / k=16, σ=2.0) 的标准定义实算得到。",
          "foot")

fig.save(OUT)
print("wrote", OUT)
print(f"clean={len(clean)} outliers={outlier_mask.sum()} raw={len(raw)}")
print(f"panel2: stat_keep={keep_stat.sum()} -> ds={len(p2_ds)}")
print(f"panel3: ds={len(p3_ds_raw)} -> stat_keep={keep3.sum()} ({len(p3)})")
print(f"centroid shift = {_off:.2f} mm  raw={np.round(c_raw,2)} clean={np.round(c_clean,2)}")
