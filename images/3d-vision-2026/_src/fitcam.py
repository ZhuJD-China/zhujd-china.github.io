#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""相机取景辅助：给定场景包围盒与视口，挑一个把所有点都框住的机位。"""
import numpy as np


def fit_camera(points, width, height, cx, cy, vh,
               azim=38.0, elev=26.0, pad=1.06, fov=30.0, up=(0, 1, 0)):
    """返回 (eye, target, fov)，使 points 的投影落在 width×height 内。

    azim/elev 为方位角与俯仰角（度）。做法：在球面上二分距离，
    每次用投影包围盒判断是否溢出，比盲调参数稳。
    """
    P = np.asarray(points, float)
    ctr = (P.min(axis=0) + P.max(axis=0)) / 2.0
    a, e = np.radians(azim), np.radians(elev)
    direction = np.array([np.cos(e) * np.sin(a), np.sin(e), np.cos(e) * np.cos(a)])
    upv = np.array(up, float)
    radius = float(np.linalg.norm(P - ctr, axis=1).max()) * pad

    def make(dist):
        eye = ctr + direction * dist
        return eye, ctr

    def proj_bbox(eye, target, f):
        fwd = target - eye
        fwd = fwd / np.linalg.norm(fwd)
        right = np.cross(fwd, upv)
        if np.linalg.norm(right) < 1e-9:
            right = np.array([1.0, 0.0, 0.0])
        right /= np.linalg.norm(right)
        up2 = np.cross(right, fwd)
        d = P - eye
        z = d @ fwd
        ok = z > 1e-6
        x = (d @ right)[ok] * f / z[ok]
        y = (d @ up2)[ok] * f / z[ok]
        if len(x) == 0:
            return 1e9, 1e9
        return (x.max() - x.min()), (y.max() - y.min())

    f_fixed = (vh / 2.0) / np.tan(np.radians(fov) / 2.0)
    # 找"能容下场景的最小距离"：装得下就往近试（hi=mid），装不下往远退（lo=mid）
    lo, hi = radius * 0.5, radius * 40.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        eye, target = make(mid)
        bw, bh = proj_bbox(eye, target, f_fixed)
        if bw <= width and bh <= height:
            hi = mid
        else:
            lo = mid
    eye, target = make(hi * 1.02)
    return eye, target, fov


if __name__ == "__main__":
    #自测
    pts = []
    for x in (-260, 260):
        for z in (-40, 660):
            pts.append([x, -90, z])
    for z in (0, 150, 330, 560):
        pts.append([0, 60, z])
    eye, tgt, fov = fit_camera(pts, 760, 560, 430, 330, 620,
                              azim=38, elev=26, pad=1.06, fov=30)
    print("eye", np.round(eye, 1), "target", np.round(tgt, 1), "fov", fov)