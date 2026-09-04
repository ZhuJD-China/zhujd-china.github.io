# zhujd-china.github.io · 观澜阁

> 观水有术，必观其澜。—— 《孟子·尽心上》

Norris Zhu（祝）的个人博客 —— 数据科学与人工智能学者，基于 GitHub Pages 纯静态搭建。

**线上地址**：<https://zhujd-china.github.io>

## 写新文章（只需两步）

1. 在 `posts/` 目录新建 `.md` 文件，开头写上头部信息：

```markdown
---
title: 文章标题
date: 2026-08-21
tags: [标签1, 标签2]
excerpt: 一句话摘要
album: 深度学习专栏   # 可选：所属专辑，相同名称自动归为一辑
order: 1             # 可选：在专辑中的序号，用于连载排序
---

正文（Markdown）……
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| title | 建议 | 文章标题 |
| date | 建议 | 发布日期，首页按它排序 |
| tags | 可选 | 标签数组，自动生成筛选器 |
| excerpt | 可选 | 摘要；不写则自动截取正文 |
| album | 可选 | 所属专辑名称，相同名称自动成辑 |
| order | 可选 | 在专辑中的序号，用于连载排序 |

单篇文章不写 `album` 字段即可，保持独立发布。

2. 提交并推送（推送前先 `git pull` 同步自动生成的清单更新）：

```bash
git pull
git add posts/你的文章.md
git commit -m "发布新文章"
git push
```

推送后约 1~2 分钟，文章自动出现在首页。**无需修改任何其他文件。**

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
- `posts/index.json` 由 GitHub Action 自动维护：当 GitHub API 限流时作为兜底，保证文章列表永不丢失
- `.nojekyll` 用于禁用 GitHub Pages 默认的 Jekyll 构建（否则带 frontmatter 的 .md 会被转换而无法直接访问）

## 本地预览

```bash
# 任选一种方式启动静态服务器
python -m http.server 8000
# 或 npx serve .

# 浏览器打开 http://localhost:8000
```
