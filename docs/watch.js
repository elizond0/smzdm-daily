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

  function parse(txt) {
    return txt.split('\n')
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s && s.charAt(0) !== '#'; });
  }

  // 入口上的「N 个关键词」是服务端生成时烙进去的，用户改完词不会自动更新，
  // 这里跟着实时校正；读不到数据就藏起来，绝不显示一个不准的数字。
  function updateCount(words) {
    var el = document.getElementById('wishCount');
    if (!el) return;
    el.style.display = '';
    el.textContent = words.length + ' 个关键词';
  }

  function apply(words) {
    updateCount(words);
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
      var el = document.getElementById('wishCount');
      if (el) el.style.display = 'none';
      if (window.console) {
        console.warn('[watch] 关键词读取失败，已隐藏计数');
      }
    });
})();
