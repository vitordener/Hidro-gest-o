'use strict';
(async function boot() {
  try {
    const d = await GET('/api/me');
    applyMe(d);
    if (d.user) startApp(); else showLogin();
  } catch (e) {
    $('#app').innerHTML = `<div class="errbox" style="margin:40px">${esc(e.message)}</div>`;
  }
})();
