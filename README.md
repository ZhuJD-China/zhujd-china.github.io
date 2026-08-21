# zhujd.github.io · 观澜阁

Norris Zhu（祝）的个人博客 —— 数据科学与人工智能学者，基于 GitHub Pages 纯静态搭建。

**线上地址**：<https://zhujd.github.io>

## 写新文章（只需两步）

1. 在 `posts/` 目录新建 `.md` 文件，开头写上头部信息：

```markdown
---
title: 文章标题
date: 2026-08-21
tags: [标签1, 标签2]
excerpt: 一句话摘要
---

正文（Markdown）……
```

2. 提交并推送：

```bash
git add posts/你的文章.md
git commit -m "发布新文章"
git push
```

推送后约 1 分钟，文章自动出现在首页。**无需修改任何其他文件。**

## 目录结构

```
├── index.html      # 主页（文章列表）
├── post.html       # 文章阅读页
├── assets/         # 样式与脚本
│   ├── style.css
│   └── app.js      # 博客引擎（自动发现文章）
└── posts/          # ← 博客文章（Markdown）
```

## 工作原理

- 首页通过 GitHub Contents API 自动发现 `posts/` 下所有 `.md` 文章
- 文章在浏览器端用 marked.js 实时渲染，代码高亮由 highlight.js 提供
- `posts/index.json` 仅为本地预览兜底，线上可忽略

## 本地预览

```bash
# 任选一种方式启动静态服务器
python -m http.server 8000
# 或 npx serve .

# 浏览器打开 http://localhost:8000
```
