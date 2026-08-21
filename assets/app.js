/* ============================================================
   观澜阁 · 博客引擎
   机制：通过 GitHub Contents API 自动发现 posts/ 下所有 .md 文章
   你只需往 posts/ 目录添加 .md 文件并推送，博客自动更新
   ============================================================ */

(function () {
  "use strict";

  /* ---------- 配置 ---------- */
  var CONFIG = {
    owner: "ZhuJD-China",
    repo: "zhujd-china.github.io",
    branch: "master",
    postsDir: "posts",
    // API 失败时（本地预览 / 限流）使用的兜底清单
    // 该清单由 .github/workflows/update-manifest.yml 在推送时自动更新
    fallbackManifest: "posts/index.json",
    cacheKey: "guanlan_posts_cache_v2",
    cacheTTL: 3 * 60 * 1000, // 3 分钟
  };

  /* ---------- 工具 ---------- */
  function $(sel) { return document.querySelector(sel); }
  function $all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------- Frontmatter 解析 ----------
     格式：
     ---
     title: 文章标题
     date: 2026-08-21
     tags: [随笔, 技术]
     excerpt: 一句话摘要
     ---
  ------------------------------------------------ */
  function parsePost(raw, filename) {
    var meta = {};
    var body = raw;
    var m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
    if (m) {
      m[1].split(/\r?\n/).forEach(function (line) {
        var kv = line.match(/^([a-zA-Z_]+)\s*:\s*(.*)$/);
        if (!kv) return;
        var key = kv[1].toLowerCase(), val = kv[2].trim();
        if (key === "tags") {
          val = val.replace(/^\[|\]$/g, "");
          meta.tags = val.split(",").map(function (t) { return t.trim(); }).filter(Boolean);
        } else {
          meta[key] = val;
        }
      });
      body = m[2];
    }
    // 兜底：无 frontmatter 时从文件名与正文推断
    if (!meta.title) {
      meta.title = filename
        .replace(/\.md$/i, "")
        .replace(/[-_]/g, " ");
    }
    if (!meta.excerpt) {
      var plain = body.replace(/[#>*`\[\]()!-]/g, "").replace(/\s+/g, " ").trim();
      meta.excerpt = plain.slice(0, 90) + (plain.length > 90 ? "…" : "");
    }
    if (!meta.tags) meta.tags = [];
    meta.file = filename;
    meta.body = body;
    meta.words = countWords(body);
    meta.readTime = Math.max(1, Math.round(meta.words / 400));
    return meta;
  }

  function countWords(text) {
    var cjk = (text.match(/[\u4e00-\u9fa5]/g) || []).length;
    var en = (text.replace(/[\u4e00-\u9fa5]/g, " ").match(/[a-zA-Z]+/g) || []).length;
    return cjk + en;
  }

  function formatDate(str) {
    if (!str) return "";
    var d = new Date(str);
    if (isNaN(d.getTime())) return str;
    var pad = function (n) { return n < 10 ? "0" + n : "" + n; };
    return d.getFullYear() + "." + pad(d.getMonth() + 1) + "." + pad(d.getDate());
  }

  /* ---------- 文章发现 ---------- */
  // 获取文章列表：优先 GitHub API（生产环境自动发现），失败则用兜底清单
  function discoverPosts() {
    var cached = readCache();
    if (cached) return Promise.resolve(cached);

    var apiUrl = "https://api.github.com/repos/" + CONFIG.owner + "/" + CONFIG.repo +
      "/contents/" + CONFIG.postsDir + "?ref=" + CONFIG.branch + "&t=" + Date.now();

    return fetch(apiUrl, { headers: { Accept: "application/vnd.github.v3+json" } })
      .then(function (res) {
        if (!res.ok) throw new Error("API " + res.status);
        return res.json();
      })
      .then(function (files) {
        var mdFiles = files
          .filter(function (f) { return f.type === "file" && /\.md$/i.test(f.name) && f.name !== "index.json"; })
          .map(function (f) { return f.name; });
        writeCache(mdFiles);
        return mdFiles;
      })
      .catch(function () {
        // 兜底：本地预览或 API 限流
        return fetch(CONFIG.fallbackManifest + "?t=" + Date.now())
          .then(function (r) { return r.ok ? r.json() : []; })
          .then(function (list) { return (list.posts || []).map(function (p) { return p.file; }); })
          .catch(function () { return []; });
      });
  }

  // 拉取单篇文章内容（同源 fetch，本地与线上均可用）
  function fetchPost(filename) {
    return fetch(CONFIG.postsDir + "/" + encodeURIComponent(filename) + "?t=" + Date.now())
      .then(function (r) {
        if (!r.ok) throw new Error("fetch " + filename + " " + r.status);
        return r.text();
      });
  }

  function loadAllPosts() {
    return discoverPosts().then(function (names) {
      if (!names.length) return [];
      return Promise.all(
        names.map(function (n) {
          return fetchPost(n)
            .then(function (raw) { return parsePost(raw, n); })
            .catch(function () { return null; });
        })
      ).then(function (posts) {
        return posts.filter(Boolean).sort(function (a, b) {
          return new Date(b.date || 0) - new Date(a.date || 0);
        });
      });
    });
  }

  /* ---------- 缓存（应对 API 限流） ---------- */
  function readCache() {
    try {
      var c = JSON.parse(localStorage.getItem(CONFIG.cacheKey) || "null");
      if (c && Date.now() - c.time < CONFIG.cacheTTL) return c.files;
    } catch (e) {}
    return null;
  }
  function writeCache(files) {
    try { localStorage.setItem(CONFIG.cacheKey, JSON.stringify({ time: Date.now(), files: files })); } catch (e) {}
  }

  /* ============================================================
     首页逻辑
     ============================================================ */
  function initHome() {
    var grid = $("#articleGrid");
    if (!grid) return;

    var allPosts = [];
    var activeTag = "全部";
    var keyword = "";

    loadAllPosts().then(function (posts) {
      allPosts = posts;
      renderTags();
      render();
      revealObserve();
      if (!posts.length) showError();
    });

    // 搜索
    var searchInput = $("#searchInput");
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        keyword = this.value.trim().toLowerCase();
        render();
        revealObserve();
      });
    }

    function renderTags() {
      var box = $("#tagFilter");
      if (!box) return;
      var tags = {};
      allPosts.forEach(function (p) { p.tags.forEach(function (t) { tags[t] = true; }); });
      var list = ["全部"].concat(Object.keys(tags));
      box.innerHTML = list.map(function (t) {
        return '<button class="tag-pill' + (t === activeTag ? " active" : "") + '" data-tag="' +
          escapeHTML(t) + '">' + escapeHTML(t) + "</button>";
      }).join("");
      box.addEventListener("click", function (e) {
        var btn = e.target.closest(".tag-pill");
        if (!btn) return;
        activeTag = btn.dataset.tag;
        $all(".tag-pill").forEach(function (b) { b.classList.toggle("active", b === btn); });
        render();
        revealObserve();
      });
    }

    function filtered() {
      return allPosts.filter(function (p) {
        var okTag = activeTag === "全部" || p.tags.indexOf(activeTag) !== -1;
        var okKey = !keyword ||
          p.title.toLowerCase().indexOf(keyword) !== -1 ||
          (p.excerpt || "").toLowerCase().indexOf(keyword) !== -1 ||
          p.tags.join(",").toLowerCase().indexOf(keyword) !== -1;
        return okTag && okKey;
      });
    }

    function render() {
      var posts = filtered();
      var empty = $("#emptyState");
      if (empty) empty.hidden = posts.length > 0;
      grid.innerHTML = posts.map(cardHTML).join("");
    }

    function showError() {
      var empty = $("#emptyState");
      if (empty) {
        empty.hidden = false;
        empty.querySelector("p").textContent = "暂无文章 · 请将 Markdown 文件放入 posts/ 目录";
      }
    }
  }

  function cardHTML(p) {
    var tagsHTML = p.tags.map(function (t) {
      return '<span class="card-tag">' + escapeHTML(t) + "</span>";
    }).join("");
    return (
      '<a class="article-card" href="post.html?file=' + encodeURIComponent(p.file) + '">' +
      '<div class="card-meta"><span class="card-date">' + escapeHTML(formatDate(p.date)) +
      '</span><span>' + p.readTime + " 分钟读完</span></div>" +
      '<h3 class="card-title">' + escapeHTML(p.title) + "</h3>" +
      '<p class="card-excerpt">' + escapeHTML(p.excerpt) + "</p>" +
      '<div class="card-tags">' + tagsHTML + "</div>" +
      '<div class="card-read"><span>阅读全文</span>' +
      '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14m-6-6 6 6-6 6"/></svg>' +
      "</div></a>"
    );
  }

  /* ============================================================
     文章页逻辑
     ============================================================ */
  function initPost() {
    var shell = $("#postShell");
    if (!shell) return;

    var file = new URLSearchParams(location.search).get("file") || "";
    // 安全校验：仅允许 posts/ 下的 .md 文件
    if (!/^[\w\u4e00-\u9fa5.-]+\.md$/i.test(file)) {
      renderError(shell, "文章不存在");
      return;
    }

    fetchPost(file).then(function (raw) {
      var post = parsePost(raw, file);
      document.title = post.title + " · Norris Zhu";
      renderPost(shell, post);
      observeProgress();
    }).catch(function () {
      renderError(shell, "文章加载失败，请稍后重试");
    });
  }

  function renderPost(shell, post) {
    if (window.marked) {
      marked.setOptions({
        breaks: true,
        highlight: function (code, lang) {
          if (window.hljs && lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
          }
          return window.hljs ? hljs.highlightAuto(code).value : code;
        },
      });
    }
    var bodyHTML = window.marked ? marked.parse(post.body) : "<pre>" + escapeHTML(post.body) + "</pre>";

    var tagsHTML = post.tags.map(function (t) {
      return '<span class="card-tag">' + escapeHTML(t) + "</span>";
    }).join("");

    shell.innerHTML =
      '<header class="post-header">' +
      '<h1 class="post-title">' + escapeHTML(post.title) + "</h1>" +
      '<div class="post-meta">' +
      '<span>' + escapeHTML(formatDate(post.date)) + "</span>" +
      '<span class="dot">·</span>' +
      "<span>" + post.readTime + " 分钟读完</span>" +
      '<span class="dot">·</span>' +
      "<span>约 " + post.words + " 字</span>" +
      "</div>" +
      '<div class="post-tags">' + tagsHTML + "</div>" +
      "</header>" +
      '<div class="post-body">' + bodyHTML + "</div>";
  }

  function renderError(shell, msg) {
    shell.innerHTML =
      '<div class="post-loading"><div class="empty-glyph">憾</div><p>' +
      escapeHTML(msg) + '</p></div>';
  }

  /* ---------- 阅读进度条 ---------- */
  function observeProgress() {
    var bar = $("#readingProgress");
    if (!bar) return;
    var onScroll = function () {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      bar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + "%";
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ---------- 通用：导航滚动态 & 入场动画 ---------- */
  function initCommon() {
    var nav = $("#nav");
    var onScroll = function () {
      if (nav) nav.classList.toggle("scrolled", window.scrollY > 40);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    revealObserve();
  }

  var observed = false;
  function revealObserve() {
    if (!("IntersectionObserver" in window)) {
      $all(".reveal, .article-card").forEach(function (el) { el.classList.add("visible"); });
      return;
    }
    if (!observed) {
      observed = true;
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            en.target.classList.add("visible");
            io.unobserve(en.target);
          }
        });
      }, { threshold: 0.08 });
      window.__revealIO = io;
    }
    $all(".reveal:not(.visible), .article-card:not(.visible)").forEach(function (el) {
      window.__revealIO.observe(el);
    });
  }

  /* ---------- 启动 ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    initCommon();
    initHome();
    initPost();
  });
})();
