#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svg3d.py —— 真三维几何投影成 SVG 的最小渲染器。

设计目标：
  * 用 numpy 搭真实 3D 几何（点、线、盒、球、点云），自己做透视投影；
  * 画家算法按深度排序，正确处理遮挡；
  * 沿视线做深度雾化，远处元素自动变暗，立体感更强；
  * 输出与专栏现有配图同一套暗色风格（#0b0b10底+ 同一组语义色）；
  * 零JS 依赖，产出纯静态 SVG。

坐标系：右手系，+X 右，+Y 上，+Z 朝观察者。单位任意，调用方自己保证比例。
"""
from __future__ import annotations

import html
import math

import numpy as np

# ---------- 语义色（与专栏现有 33 张图完全一致） ----------
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


# ---------- 颜色与几何小工具 ----------
def mix(c1: str, c2: str, t: float) -> str:
    """按比例混两个 #rrggbb。t=0 取c1，t=1 取 c2。"""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(round(a[i] + (b[i] - a[i]) * t)):02x}" for i in range(3))


def v(*a) -> np.ndarray:
    return np.array(a, dtype=float)


def norm(x) -> np.ndarray:
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.where(n == 0, 1.0, n)


def rotx(deg) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return v(1, 0, 0), v(0, c, -s), v(0, s, c)


def roty(deg) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return v(c, 0, s), v(0, 1, 0), v(-s, 0, c)


def rotz(deg) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return v(c, -s, 0), v(s, c, 0), v(0, 0, 1)


def rot(ax, ay, az):
    """欧拉角 → 3x3 旋转矩阵（列向量约定，先 X 后 Y 后 Z）。"""
    Mx = np.column_stack(rotx(ax))
    My = np.column_stack(roty(ay))
    Mz = np.column_stack(rotz(az))
    return Mz @ My @ Mx


def look_basis(eye, target, up=v(0, 1, 0)):
    """返回相机正交基（行向量分别是 right / up / back）与相机位置。"""
    eye = np.asarray(eye, float)
    back = norm(eye - np.asarray(target, float))
    right = np.cross(np.asarray(up, float), back)
    if np.linalg.norm(right) < 1e-9:
        right = np.cross(v(0, 0, 1), back)
    right = norm(right)
    upv = np.cross(back, right)
    return right, upv, back, eye


# ---------- 文本宽度估算（与静态检查器同口径，用于自动避让） ----------
_NARROW = set("iljI.,:;|!'`")


def text_w(s: str, size: float, mono: bool = False) -> float:
    w = 0.0
    for ch in s:
        if ord(ch) > 0x2E80:
            w += 1.0
        elif mono:
            w += 0.60
        elif ch in _NARROW or ch == " ":
            w += 0.30
        elif ch.isupper():
            w += 0.66
        else:
            w += 0.55
    return w * size


STYLE = """\
.bg{fill:%(bg)s}
.ttl{fill:%(fg)s;font:600 26px %(serif)s}
.sub{fill:%(mut)s;font:400 15px %(serif)s}
.hd{fill:%(fg)s;font:600 16px %(serif)s}
.lb{fill:%(fg)s;font:400 13px %(serif)s}
.sm{fill:%(mut)s;font:400 12px %(serif)s}
.xs{fill:%(dim)s;font:400 11px %(serif)s}
.foot{fill:%(dim)s;font:400 12px %(serif)s}
.mon{fill:%(gold)s;font:600 13px %(mono)s}
.moc{fill:%(blue)s;font:600 13px %(mono)s}
.mor{fill:%(red)s;font:600 13px %(mono)s}
.mog{fill:%(green)s;font:600 13px %(mono)s}
.note{fill:%(mut)s;font:400 11.5px %(serif)s}
""" % {"bg": BG, "fg": FG, "mut": MUT, "dim": DIM,
       "gold": GOLD, "blue": BLUE, "red": RED, "green": GREEN,
       "serif": SERIF, "mono": MONO}


def fmt(x: float) -> str:
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


class Cam:
    """透视相机。fov 为竖直视场角（度）。cx/cy 为光轴落在屏幕上的像素位置。"""

    def __init__(self, eye, target, up=v(0, 1, 0), fov=32.0,
                 cx=600.0, cy=200.0, vh=400.0, zoom=1.0):
        """cx/cy：光轴落点（像素）。vh：视口名义高度（像素），决定焦距量纲。
        zoom：在vh 基础上的额外缩放。"""
        self.right, self.upv, self.back, self.eye = look_basis(eye, target, up)
        self.f = (vh / 2.0) / math.tan(math.radians(fov) / 2.0) * zoom
        self.cx = cx
        self.cy = cy

    def view(self, P):
        """世界坐标 → 相机坐标 (x右, y上, z向前/远离观察者)。"""
        P = np.atleast_2d(np.asarray(P, float))
        d = P - self.eye
        # back 指向"从目标看向相机"，故 -back 才是"从相机看向场景"的前进方向
        return np.stack([d @ self.right, d @ self.upv, d @ (-self.back)], axis=-1)

    def project(self, P):
        """相机坐标 → 屏幕像素（含视口居中与上下翻转）。只返回 z>eps 的点。"""
        C = self.view(P)
        z = C[:, 2]
        ok = z > 1e-6
        s = np.where(ok, self.f / np.where(ok, z, 1.0), 0.0)
        xs = self.cx + C[:, 0] * s
        ys = self.cy - C[:, 1] * s
        return xs, ys, z, ok


class Fig:
    """一张 SVG 图。几何按深度排序后统一输出。"""

    def __init__(self, w=1200, h=300, title="", sub="", pad=44):
        self.w = w
        self.h = h
        self.pad = pad
        self.title = title
        self.sub = sub
        self.items: list[tuple[float, str]] = []
        self.texts: list[str] = []
        self.defs: list[str] = []
        self._arrow_ids: dict[str, str] = {}

    # ---- 内部 ----
    def _push(self, depth, svg):
        self.items.append((float(depth), svg))

    def fog(self, color, depth, dmin, dmax, amount=0.55):
        t = 0.0 if dmax <= dmin else (depth - dmin) / (dmax - dmin)
        return mix(color, "#2a2a33", max(0.0, min(1.0, t)) * amount)

    def _arrow(self, color):
        """为某种颜色生成一个箭头 marker id。"""
        key = color
        if key not in self._arrow_ids:
            i = len(self._arrow_ids)
            mid = f"ar{i}"
            self._arrow_ids[key] = mid
            self.defs.append(
                f'<marker id="{mid}" markerWidth="7" markerHeight="7" refX="6.2" '
                f'refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7 z" fill="{color}"/></marker>'
            )
        return self._arrow_ids[key]

    # ---- 二维文字 ----
    def text2(self, x, y, s, cls="sm", fill=None, anchor="start", extra="", mono=False):
        a = f' fill="{fill}"' if fill else ""
        if mono:
            extra = f' font-family="{MONO}"' + extra
        self.texts.append(
            f'<text class="{cls}" x="{fmt(x)}" y="{fmt(y)}" text-anchor="{anchor}"{a}{extra}>{esc(s)}</text>'
        )

    def label3(self, cam, P, s, cls="xs", fill=None, dx=0, dy=0,
               anchor="start", mono=False):
        """给三维点加标签。dx/dy 为屏幕像素偏移。"""
        x, y, _, ok = cam.project(np.atleast_2d(P))
        if not ok[0]:
            return
        size = {"xs": 11, "sm": 12, "lb": 13, "hd": 16, "mon": 13, "note": 11.5}[cls]
        self.text2(x[0] + dx, y[0] + dy, s, cls, fill, anchor, mono=mono)

    # ---- 三维图元 ----
    def line3(self, cam, p0, p1, color=GRAY, wdt=1.4, dash=None, arrow=False,
              dmin=0, dmax=1, fade=0.0, depth_bias=0.0):
        C = cam.view(np.vstack([np.atleast_1d(p0), np.atleast_1d(p1)]))
        z = C[:, 2]
        if (z <= 1e-6).any():
            return
        xs, ys, _, ok = cam.project(np.vstack([np.atleast_1d(p0), np.atleast_1d(p1)]))
        if not ok.all():
            return
        col = self.fog(color, float(z.mean()), dmin, dmax, fade)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        mk = f' marker-end="url(#{self._arrow(col)})"' if arrow else ""
        self._push(float(z.mean()) + depth_bias,
                   f'<line x1="{fmt(xs[0])}" y1="{fmt(ys[0])}" x2="{fmt(xs[1])}" '
                   f'y2="{fmt(ys[1])}" stroke="{col}" stroke-width="{fmt(wdt)}"{d}{mk}/>')

    def poly3(self, cam, pts, color=GRAY, fill=None, opacity=1.0, wdt=1.2,
              dmin=0, dmax=1, fade=0.45, edge=None):
        P = np.asarray(pts, float)
        C = cam.view(P)
        z = C[:, 2]
        if (z <= 1e-6).any():
            return
        xs, ys, _, ok = cam.project(P)
        if not ok.all():
            return
        f = self.fog(fill or color, float(z.mean()), dmin, dmax, fade) if fill else "none"
        st = edge or self.fog(color, float(z.mean()), dmin, dmax, fade)
        self._push(float(z.mean()),
                   f'<polygon points="{" ".join(f"{fmt(a)},{fmt(b)}" for a, b in zip(xs, ys))}" '
                   f'fill="{f}" fill-opacity="{fmt(opacity)}" stroke="{st}" '
                   f'stroke-width="{fmt(wdt)}" stroke-opacity=".9"/>')

    def box3(self, cam, center, size, color=GRAY, fill=None, opacity=1.0,
             R=None, dmin=0, dmax=1, fade=0.45, wdt=1.2, faces=True):
        """带旋转的有向长方体。R 为 3x3 旋转矩阵（列=局部轴在世界系的方向）。"""
        c = np.asarray(center, float)
        s = np.asarray(size, float) / 2.0
        R = np.eye(3) if R is None else np.asarray(R, float)
        corners = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    corners.append(c + R @ v(sx * s[0], sy * s[1], sz * s[2]))
        C = np.array(corners)
        X = C @ R                       # 局部轴在世界系的投影长度，用于定面序
        order = [np.argsort(-X[:, i]) for i in range(3)]
        idx = {}
        k = 0
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    idx[(sx, sy, sz)] = k
                    k += 1
        if faces:
            quads = []
            for sg in (-1, 1):
                quads.append([idx[(sg, -1, -1)], idx[(sg, -1, 1)], idx[(sg, 1, 1)], idx[(sg, 1, -1)]])
                quads.append([idx[(-1, sg, -1)], idx[(-1, sg, 1)], idx[(1, sg, 1)], idx[(1, sg, -1)]])
                quads.append([idx[(-1, -1, sg)], idx[(-1, 1, sg)], idx[(1, 1, sg)], idx[(1, -1, sg)]])
            for q in quads:
                pts = C[list(q)]
                cc = pts.mean(axis=0)
                self.poly3(cam, pts, color, fill or color, opacity, wdt, dmin, dmax, fade)
        edges = [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
                 (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7)]
        for a, b in edges:
            self.line3(cam, C[a], C[b], color, wdt, dmin=dmin, dmax=dmax,
                       fade=fade * 0.7, depth_bias=-0.001)

    def _px_radius(self, cam, p, r):
        """世界半径 r 在 p 处的屏幕像素半径。"""
        z = cam.view(np.atleast_2d(p))[0, 2]
        if z <= 1e-6:
            return 0.0
        return r * cam.f / z

    def sphere3(self, cam, c, r, color=GOLD, dmin=0, dmax=1, fade=0.4,
                rings=5, segs=14, opacity=0.92, outline=True):
        """球体：先画实心圆盘（按深度排序），再叠一圈轮廓点。"""
        c = np.asarray(c, float)
        zc = cam.view(np.atleast_2d(c))[0, 2]
        if zc <= 1e-6:
            return
        xs, ys, _, _ = cam.project(np.atleast_2d(c))
        rr = r * cam.f / zc
        col = self.fog(color, zc, dmin, dmax, fade)
        # 球的透视投影轮廓恒为半径 r*f/z 的正圆，直接描边即可，无需采样
        self._push(zc, f'<circle cx="{fmt(xs[0])}" cy="{fmt(ys[0])}" r="{fmt(rr)}" '
                      f'fill="{col}" fill-opacity="{fmt(opacity)}"'
                      + (f' stroke="{mix(color, BG, 0.3)}" stroke-width="1.4"' if outline else "")
                      + "/>")

    def dot3(self, cam, p, r=3.4, color=GOLD, dmin=0, dmax=1, fade=0.3,
             ring=False, depth_bias=0.0, wdt=1.6):
        z = cam.view(np.atleast_1d(p))[0, 2]
        if z <= 1e-6:
            return
        xs, ys, _, _ = cam.project(np.atleast_2d(p))
        col = self.fog(color, z, dmin, dmax, fade)
        if ring:
            self._push(z + depth_bias,
                       f'<circle cx="{fmt(xs[0])}" cy="{fmt(ys[0])}" r="{fmt(r)}" '
                       f'fill="none" stroke="{col}" stroke-width="{fmt(wdt)}"/>')
        else:
            self._push(z + depth_bias,
                       f'<circle cx="{fmt(xs[0])}" cy="{fmt(ys[0])}" r="{fmt(r)}" fill="{col}"/>')

    def cloud3(self, cam, P, color=BLUE, size=1.5, dmin=0, dmax=1, fade=0.35,
               opacity=0.95, subset=None, fixed_radius=None):
        """点云。subset 为布尔数组时只画选中点（用于剔除前后对比）。

        fixed_radius 不为空时，每个点用该世界半径换算成屏幕半径（画球面用）。
        """
        P = np.asarray(P, float)
        if subset is not None:
            P = P[subset]
        if len(P) == 0:
            return
        C = cam.view(P)
        z = C[:, 2]
        ok = z > 1e-6
        xs, ys, _, _ = cam.project(P)
        order = np.argsort(-z)
        for i in order:
            if not ok[i]:
                continue
            t = 0.0 if dmax <= dmin else (z[i] - dmin) / (dmax - dmin)
            col = mix(color, "#2a2a33", max(0.0, min(1.0, t)) * fade)
            if fixed_radius:
                rr = max(0.6, fixed_radius * cam.f / z[i])
            else:
                rr = max(0.55, size * (0.7 + 0.5 * (z[i] / max(dmax, 1e-9))))
            self._push(z[i], f'<circle cx="{fmt(xs[i])}" cy="{fmt(ys[i])}" '
                             f'r="{fmt(rr)}" fill="{col}" fill-opacity="{fmt(opacity)}"/>')

    def grid3(self, cam, y, xs_range, zs_range, color=GRAY, step=None, wdt=0.8,
              opacity=0.25, dmin=0, dmax=1):
        x0, x1 = xs_range
        z0, z1 = zs_range
        step = step or (x1 - x0) / 8
        n = int((x1 - x0) / step) + 1
        m = int((z1 - z0) / step) + 1
        for i in range(n + 1):
            x = x0 + i * step
            self.line3(cam, v(x, y, z0), v(x, y, z1), color, wdt,
                       dmin=dmin, dmax=dmax, fade=0.3)
        for j in range(m + 1):
            z = z0 + j * step
            self.line3(cam, v(x0, y, z), v(x1, y, z), color, wdt,
                       dmin=dmin, dmax=dmax, fade=0.3)

    def rect2(self, x, y, w, h, fill=None, stroke=None, rx=0, wdt=1.2, opacity=1.0,
              extra=""):
        f = f'fill="{fill}"' if fill else 'fill="none"'
        s = f' stroke="{stroke}" stroke-width="{fmt(wdt)}"' if stroke else ""
        o = f' fill-opacity="{fmt(opacity)}"' if fill and opacity != 1 else ""
        self.texts.append(f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" '
                          f'height="{fmt(h)}" rx="{fmt(rx)}" {f}{o}{s}{extra}/>')

    def hline(self, x0, x1, y, color=GRAY, wdt=1, op=0.3, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.texts.append(f'<line x1="{fmt(x0)}" y1="{fmt(y)}" x2="{fmt(x1)}" y2="{fmt(y)}" '
                          f'stroke="{color}" stroke-width="{fmt(wdt)}" stroke-opacity="{fmt(op)}"{d}/>')

    # ---- 输出 ----
    def render(self) -> str:
        self.items.sort(key=lambda kv: -kv[0])
        head = []
        y = 48
        if self.title:
            head.append(f'<text class="ttl" x="{self.pad}" y="{y}">{esc(self.title)}</text>')
            y += 28
        if self.sub:
            head.append(f'<text class="sub" x="{self.pad}" y="{y}">{esc(self.sub)}</text>')
        body = [s for _, s in self.items] + self.texts
        defs = f'<defs>{"".join(self.defs)}</defs>' if self.defs else ""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="100%" '
            f'role="img" aria-label="{esc(self.title or self.sub)}">\n'
            f"  <style>\n{STYLE}  </style>\n{defs}\n"
            f'  <rect class="bg" x="0" y="0" width="{self.w}" height="{self.h}" rx="14"/>\n'
            + "".join("  " + s + "\n" for s in head + body)
            + "</svg>\n"
        )

    def save(self, path):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.render())
        return path
