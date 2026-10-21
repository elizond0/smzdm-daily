/* 愿望单标签 · 浏览器端实时计算
 *
 * 服务端渲染时用的是「上次抓取那一刻」的关键词。用户在愿望单页面改完词，
 * 如果等服务端重新生成，要等到下一次抓取。这里改成页面加载后读一次最新的
 * watchlist.txt，现场重算每个商品的标签，所以改完刷新就能看到。
 */
(function () {
  var meta = document.querySelector('meta[name="watch-src"]');
  if (!meta || !meta.content) return;

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

  fetch(meta.content + '?t=' + Date.now(), { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
    .then(function (txt) {
      var words = txt.split('\n')
        .map(function (s) { return s.trim(); })
        .filter(function (s) { return s && s.charAt(0) !== '#'; });
      apply(words);
    })
    .catch(function () { /* 读不到就保留服务端渲染的标签 */ });
})();
