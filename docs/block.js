/* 屏蔽词过滤 · 浏览器端实时执行
 *
 * 与 watch.js（愿望单标签）同一套路：服务端渲染时不做屏蔽，
 * 页面加载后读一次最新屏蔽词，现场把命中的行隐藏。
 * 数据库里照样有记录（爬取逻辑不变），删掉屏蔽词刷新即恢复。
 *
 * 数据来源按优先级：
 *   1. localStorage —— 本机缓存，屏蔽页保存后或日报页快捷屏蔽后立即生效
 *   2. ./blocklist.txt —— Actions 每次运行同步到 docs/ 的副本
 *   3. GitHub API —— 实时兜底
 *
 * 额外职责：给每行商品插入「屏蔽」按钮（服务端模板不动，
 * daily.py 渲染逻辑零改动）。
 */
(function () {
  var REPO = 'elizond0/smzdm-daily';
  var BRANCH = 'main';
  var FILE = 'blocklist.txt';
  var API_URL = 'https://api.github.com/repos/' + REPO + '/contents/' + FILE;
  var LOCAL_URL = './' + FILE;
  var CACHE_KEY = 'block_words_cache';
  var PENDING_KEY = 'block_pending';

  function parse(txt) {
    return txt.split('\n')
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s && s.charAt(0) !== '#'; });
  }

  function toast(msg) {
    var t = document.getElementById('blkToast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'blkToast';
      t.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%)'
        + ';background:#16181c;color:#fff;padding:10px 18px;border-radius:8px;font-size:13px'
        + ';opacity:0;transition:.25s;pointer-events:none;max-width:88vw;text-align:center;z-index:9';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = '1';
    t.style.transform = 'translateX(-50%) translateY(0)';
    clearTimeout(toast._t);
    toast._t = setTimeout(function () {
      t.style.opacity = '0';
      t.style.transform = 'translateX(-50%) translateY(20px)';
    }, 2600);
  }

  /* 从展示标题提炼一个建议屏蔽词：剥营销前缀，取前 12 个字符 */
  function suggestKeyword(title) {
    var t = (title || '').replace(
      /^(88VIP|今日必买|百亿补贴|国家补贴|PLUS会员|会员专享|白菜党|手慢无|必领神券|每日可领|绝对值|历史低价|过期|限时|售罄|淘金币[\d.]+元)[：:、\s]*/g, '');
    return t.slice(0, 12) || (title || '').slice(0, 12);
  }

  function addPending(word) {
    try {
      var arr = JSON.parse(localStorage.getItem(PENDING_KEY) || '[]');
      if (!Array.isArray(arr)) arr = [];
      if (arr.indexOf(word) === -1) arr.push(word);
      localStorage.setItem(PENDING_KEY, JSON.stringify(arr));
    } catch (e) {}
  }

  function insertButton(td, title) {
    if (td.querySelector('.blkbtn')) return;   // 幂等：fetch 回调会反复 apply
    var btn = document.createElement('button');
    btn.className = 'blkbtn';
    /* 内联 SVG 代替 🚫 emoji：emoji 依赖系统彩色字体，Windows 上偶发渲染成 □ */
    btn.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true">'
      + '<circle cx="8" cy="8" r="6.2"/><path d="M3.8 12.2 12.2 3.8"/></svg>';
    btn.title = '屏蔽该商品（命中标题即从日报隐藏，数据库照常记录）';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var word = prompt('要屏蔽的关键词（标题包含它就不再显示）：', suggestKeyword(title));
      if (!word || !word.trim()) return;
      word = word.trim();
      var words = currentWords.slice();
      if (words.indexOf(word) === -1) words.push(word);
      currentWords = words;
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ words: words, ts: Date.now() })); } catch (e2) {}
      addPending(word);
      apply(words);
      toast('已在本机屏蔽「' + word + '」，去屏蔽词页面「保存到仓库」才对其他设备生效');
    });
    /* 锚点 = 最后一个标签/徽章/⭐按钮，紧跟其后插入 → 不另起一行，且总排在 ⭐ 后面 */
    var spans = td.querySelectorAll('span.tag,span.newlow,span.atlow,span.first,span.wish,.wishbtn');
    var anchor = spans.length ? spans[spans.length - 1] : td.querySelector('a');
    if (anchor) anchor.insertAdjacentElement('afterend', btn);
    else td.appendChild(btn);
  }

  var currentWords = [];

  function updateCount(words) {
    var el = document.getElementById('blockCount');
    if (!el) return;
    el.style.display = '';
    el.textContent = words.length;   /* 括号与「屏蔽（）」文案在模板里，这里只填数字 */
  }

  function apply(words) {
    currentWords = words || [];
    updateCount(currentWords);
    var rows = document.querySelectorAll('td.name[data-t]');
    var hidden = 0;
    for (var i = 0; i < rows.length; i++) {
      var td = rows[i];
      var title = td.getAttribute('data-t') || '';
      var tr = td.closest ? td.closest('tr') : td.parentNode;
      var hit = currentWords.some(function (w) { return title.indexOf(w) !== -1; });
      insertButton(td, title);
      if (hit) {
        tr.style.display = 'none';
        hidden++;
      } else {
        tr.style.display = '';
      }
    }
    /* 「已屏蔽 N 条」提示条：0 条时彻底不渲染，不留痕迹 */
    var bar = document.getElementById('blockBar');
    if (hidden > 0) {
      if (!bar) {
        bar = document.createElement('div');
        bar.id = 'blockBar';
        var funnel = document.querySelector('.funnel');
        if (funnel) funnel.insertAdjacentElement('afterend', bar);
        else document.querySelector('.wrap').insertBefore(bar, document.querySelector('h2'));
      }
      bar.style.cssText = 'background:#fdecee;border:1px solid #f3c3c9;color:#a1404c;'
        + 'border-radius:8px;padding:9px 14px;font-size:12.5px;margin-bottom:16px';
      bar.innerHTML = '🚫 已按屏蔽词隐藏 <b>' + hidden + '</b> 条商品（数据仍在数据库中，'
        + '<a href="./blocklist.html" style="color:#a1404c">管理屏蔽词</a>）';
    } else if (bar) {
      bar.parentNode && bar.parentNode.removeChild(bar);
    }
  }

  /* 1) 本机缓存：立即生效，之后仍异步拉最新保持跨设备同步 */
  try {
    var raw = localStorage.getItem(CACHE_KEY);
    if (raw) {
      var obj = JSON.parse(raw);
      if (obj && Object.prototype.toString.call(obj.words) === '[object Array]') {
        apply(obj.words);
      }
    }
  } catch (e) { /* localStorage 被禁用时忽略 */ }

  /* 2) 同域副本 → 3) API；无论缓存是否命中都执行，谁成功用谁 */
  fetch(LOCAL_URL + '?t=' + Date.now(), { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
    .catch(function () {
      return fetch(API_URL + '?ref=' + BRANCH + '&t=' + Date.now(), {
        cache: 'no-store',
        headers: { Accept: 'application/vnd.github.raw' }
      }).then(function (r) { return r.ok ? r.text() : Promise.reject(); });
    })
    .then(function (txt) {
      var words = parse(txt);
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ words: words, ts: Date.now() })); } catch (e) {}
      apply(words);
    })
    .catch(function () {
      updateCount(currentWords);   /* 拉不到就维持现状（缓存或空），不报错 */
    });
})();
