// Leonida Desk client script: provider-independent analytics events, sharing, newsletter form.
// No cookies and no third-party code. Events go to window.ldEvents and, only if the build set an
// analytics endpoint, to that endpoint via sendBeacon.
(function () {
  var cfg = document.documentElement.dataset;
  window.ldEvents = window.ldEvents || [];
  function track(name, props) {
    var e = { event: name, path: location.pathname, ts: new Date().toISOString(), props: props || {} };
    window.ldEvents.push(e);
    if (cfg.analytics && navigator.sendBeacon) {
      navigator.sendBeacon(cfg.analytics, new Blob([JSON.stringify(e)], { type: 'application/json' }));
    }
  }
  window.ldTrack = track;
  track('page_view', { referrer: document.referrer || null });

  // scroll depth (25/50/75/100) and engaged time (visible seconds, sent when the page is hidden)
  var marks = {}, start = Date.now(), engaged = 0, visible = !document.hidden;
  addEventListener('scroll', function () {
    var h = document.documentElement, pct = Math.round(((h.scrollTop + innerHeight) / h.scrollHeight) * 100);
    [25, 50, 75, 100].forEach(function (m) { if (pct >= m && !marks[m]) { marks[m] = 1; track('scroll_depth', { percent: m }); } });
  }, { passive: true });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { if (visible) engaged += Date.now() - start; visible = false; track('engaged_time', { seconds: Math.round(engaged / 1000) }); }
    else { visible = true; start = Date.now(); }
  });

  // any element with data-track="event_name" reports a click, with its other data-* values
  document.addEventListener('click', function (ev) {
    var el = ev.target.closest && ev.target.closest('[data-track]');
    if (!el) return;
    var props = {}; Object.keys(el.dataset).forEach(function (k) { if (k !== 'track') props[k] = el.dataset[k]; });
    track(el.dataset.track, props);
    if (el.dataset.copy) {
      ev.preventDefault();
      navigator.clipboard && navigator.clipboard.writeText(el.dataset.copy).then(function () { el.textContent = 'Link copied'; });
    }
  });

  // affiliate impressions: once per block, when it scrolls into view
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { track('affiliate_impression', { product: en.target.dataset.product }); io.unobserve(en.target); } });
    }, { threshold: 0.5 });
    document.querySelectorAll('[data-affiliate-block]').forEach(function (el) { io.observe(el); });
  }

  // newsletter forms
  document.querySelectorAll('form[data-newsletter]').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var status = form.querySelector('[data-status]'), endpoint = form.dataset.endpoint;
      var data = new FormData(form);
      if (data.get('website')) return;                       // honeypot
      if (!endpoint) { status.textContent = 'Sign-ups are not open yet.'; return; }
      if (!data.get('consent')) { status.textContent = 'Please tick the box to confirm.'; return; }
      var payload = {
        email: data.get('email'), consent_at: new Date().toISOString(), signup_source: form.dataset.source,
        preferred_games: data.getAll('games'), topic_interests: data.getAll('topics'),
      };
      status.textContent = 'Sending...';
      fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        .then(function (r) {
          if (!r.ok) throw new Error(r.status);
          status.textContent = 'Thanks. Check your inbox to confirm.'; form.reset();
          track('newsletter_signup', { source: form.dataset.source });
        })
        .catch(function () { status.textContent = 'That did not go through. Please try again later.'; });
    });
  });
})();
