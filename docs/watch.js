/* 愿望单标签 · 浏览器端实时计算
 *
 * 服务端渲染时用的是「上次抓取那一刻」的关键词。用户在愿望单页面改完词，
 * 如果等服务端重新生成，要等到下一次抓取。这里改成页面加载后读一次最新的
 * 关键词，现场重算每个商品的标签，所以改完刷新就能看到。
 *
 * 数据来源按优先级：
 *   1. localStorage —— 同域名下共享，愿望单页保存时写进来的，本机改完立刻生效
 *   2. ./watchlist.txt —— Actions 每次运行同步到 docs/ 的副本，同域稳定，但滞后一轮
 *   3. GitHub API —— 实时；raw.githubusercontent 在国内常不可达，API 一般能通
 *
 * 全部失败时保留服务端渲染的标签，只是不更新，不会把标签抹掉。
 */
(function () {
  var meta = document.querySelector('meta[name="watch-src"]');
  if (!meta) return;

  var API_URL = meta.getAttribute('data-api') || '';
  var LOCAL_URL = './watchlist.txt';
  var CACHE_KEY = 'watch_words_cache';
  var PENDING_KEY = 'watch_pending';   // 日报页快捷关注、尚未保存到仓库的词

  function parse(txt) {
    return txt.split('\n')
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s && s.charAt(0) !== '#'; });
  }

  function toast(msg) {
    var t = document.getElementById('wchToast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'wchToast';
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

  /* 从展示标题提炼建议词：剥营销前缀，取前 12 个字符（与 block.js 同款） */
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

  /* 快捷「关注」按钮：点击后写入本机缓存并立即显示标签，
   * 保存到仓库仍要去愿望单页（那里有 Token），与屏蔽按钮同一套交互。 */
  function ensureWishButton(td, title) {
    if (td.querySelector('.wishbtn')) return;
    var btn = document.createElement('button');
    btn.className = 'wishbtn';
    /* 内联 SVG 星形代替 ⭐ emoji：不依赖系统彩色字体，各端一致 */
    btn.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true">'
      + '<path d="M8 2.2l1.75 3.55 3.92.57-2.84 2.77.67 3.9L8 11.16l-3.5 1.83.67-3.9L2.33 6.32l3.92-.57z"/></svg>';
    btn.title = '关注该商品（命中的会在日报打上愿望单标签，推送时优先）';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var word = prompt('要关注的关键词（标题包含它就打「愿望单」标签）：', suggestKeyword(title));
      if (!word || !word.trim()) return;
      word = word.trim();
      var words = currentWords.slice();
      if (words.indexOf(word) === -1) words.push(word);
      currentWords = words;
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ words: words, ts: Date.now() })); } catch (e2) {}
      addPending(word);
      apply(words);
      toast('已在本机关注「' + word + '」，去愿望单页面「保存到仓库」才对其他设备生效');
    });
    /* 锚点 = 最后一个标签/徽章，紧跟其后插入 → 不另起一行 */
    var spans = td.querySelectorAll('span.tag,span.newlow,span.atlow,span.first,span.wish');
    var anchor = spans.length ? spans[spans.length - 1] : td.querySelector('a');
    if (anchor) anchor.insertAdjacentElement('afterend', btn);
    else td.appendChild(btn);
  }

  var currentWords = [];

  // 入口上的数字是服务端生成时烙进去的，用户改完词不会自动更新，
  // 这里跟着实时校正；读不到数据时回退成服务端值，绝不显示一个不准的数字。
  function updateCount(words) {
    var el = document.getElementById('wishCount');
    if (!el) return;
    el.style.display = '';
    el.textContent = words.length;   /* 括号与「关注（）」文案在模板里，这里只填数字 */
  }

  function apply(words) {
    currentWords = words || [];
    updateCount(currentWords);
    var rows = document.querySelectorAll('td.name[data-t]');
    for (var i = 0; i < rows.length; i++) {
      var td = rows[i];
      var title = td.getAttribute('data-t') || '';
      var hit = words.some(function (w) { return title.indexOf(w) !== -1; });
      var badge = td.querySelector('.wish');

      if (hit && !badge) {
        var span = document.createElement('span');
        span.className = 'wish';
        span.textContent = '愿望单';
        var link = td.querySelector('a');
        if (link && link.parentNode === td) {
          link.insertAdjacentElement('afterend', span);
        } else {
          td.insertBefore(span, td.firstChild);
        }
      } else if (!hit && badge) {
        badge.parentNode.removeChild(badge);
      }
      ensureWishButton(td, title);
    }
  }

  // 1) 本机缓存：愿望单页保存时写入，最新
  try {
    var raw = localStorage.getItem(CACHE_KEY);
    if (raw) {
      var obj = JSON.parse(raw);
      if (obj && Object.prototype.toString.call(obj.words) === '[object Array]') {
        apply(obj.words);
        return;
      }
    }
  } catch (e) { /* localStorage 被禁用时忽略 */ }

  // 2) 同域副本：Actions 同步过来的，比 API 稳
  fetch(LOCAL_URL + '?t=' + Date.now(), { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
    .catch(function () {
      // 3) 最后再试 API
      if (!API_URL) return Promise.reject();
      var url = API_URL + (API_URL.indexOf('?') === -1 ? '?' : '&') + 't=' + Date.now();
      return fetch(url, {
        cache: 'no-store',
        headers: { Accept: 'application/vnd.github.raw' }
      }).then(function (r) { return r.ok ? r.text() : Promise.reject(); });
    })
    .then(function (txt) { apply(parse(txt)); })
    .catch(function () {
      /* 读不到就保持服务端渲染的原始数字，不去改成 0（0 会被误读成「没有关注」） */
      if (window.console) {
        console.warn('[watch] 关键词读取失败，沿用服务端计数');
      }
    });
})();
