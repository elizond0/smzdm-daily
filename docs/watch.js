/* 愿望单标签 · 浏览器端实时计算
 *
 * 服务端渲染时用的是「上次抓取那一刻」的关键词。用户在愿望单页面改完词，
 * 如果等服务端重新生成，要等到下一次抓取。这里改成页面加载后读一次最新的
 * watchlist.txt，现场重算每个商品的标签，所以改完刷新就能看到。
 *
 * 两个数据源依次尝试：
 *   1. GitHub API —— 实时；raw.githubusercontent 在国内常不可达，API 通常能通
 *   2. 同域 watchlist.txt —— 由 Actions 每次运行复制到 docs/，滞后一轮但稳定
 *
 * 两个都失败时保留服务端渲染的标签，不会把标签全抹掉。
 */
(function () {
  var meta = document.querySelector('meta[name="watch-src"]');
  if (!meta) return;

  var API_URL = meta.getAttribute('data-api') || '';
  var LOCAL_URL = './watchlist.txt';

  function parse(txt) {
    return txt.split('\n')
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s && s.charAt(0) !== '#'; });
  }

  function apply(words) {
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

  function fetchApi() {
    if (!API_URL) return Promise.reject();
    var url = API_URL + (API_URL.indexOf('?') === -1 ? '?' : '&') + 't=' + Date.now();
    return fetch(url, {
      cache: 'no-store',
      headers: { Accept: 'application/vnd.github.raw' }
    }).then(function (r) {
      return r.ok ? r.text() : Promise.reject();
    });
  }

  function fetchLocal() {
    return fetch(LOCAL_URL + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(); });
  }

  fetchApi()
    .catch(fetchLocal)
    .then(function (txt) { apply(parse(txt)); })
    .catch(function () {
      if (window.console) {
        console.warn('[watch] 关键词读取失败，沿用页面里已有的标签');
      }
    });
})();
