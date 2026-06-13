() => {
  const lab = (e) => {
    const al = e.getAttribute('aria-label'); if (al) return al;
    if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l && l.innerText.trim()) return l.innerText; }
    const cl = e.closest('label'); if (cl && cl.innerText.trim()) return cl.innerText;
    let n = e.closest('div,fieldset');
    for (let i = 0; i < 3 && n; i++) { const lb = n.querySelector('label,legend,.text,[class*=application-label]'); if (lb && lb.innerText.trim()) return lb.innerText; n = n.parentElement; }
    return e.placeholder || e.name || '';
  };
  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 300);
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
  const req = (e, L) => e.required || e.getAttribute('aria-required') === 'true' || /[*✱]/.test(L);
  window.__aa = window.__aa || 0;
  const out = [], radios = {};
  for (const e of document.querySelectorAll('input, textarea, select')) {
    const tag = e.tagName.toLowerCase(), typ = (e.type || 'text').toLowerCase();
    if (['hidden', 'submit', 'button', 'search'].includes(typ)) continue;
    if (typ !== 'file' && !vis(e)) continue;
    let L = norm(lab(e));
    if (typ === 'file') {
      let n = e.closest('div,section,fieldset'), sec = '';
      for (let i = 0; i < 4 && n; i++) { const t = (n.innerText || '').slice(0, 120); if (/resume|cv|cover/i.test(t)) { sec = t; break; } n = n.parentElement; }
      e.dataset.aa = ++window.__aa;
      out.push({ aa: window.__aa, kind: 'file', label: norm(sec) || 'resume', required: true, name: e.name || '', options: [] });
      continue;
    }
    if (typ === 'radio') {
      e.dataset.aa = ++window.__aa;
      (radios[e.name] = radios[e.name] || { kind: 'radio-group', label: '', required: false, name: e.name, options: [], aa: window.__aa })
        .options.push([L, window.__aa]);
      const fs = e.closest('fieldset'); const gl = fs && fs.querySelector('legend');
      radios[e.name].label = radios[e.name].label || norm(gl ? gl.innerText : '');
      radios[e.name].required = radios[e.name].required || req(e, L);
      continue;
    }
    e.dataset.aa = ++window.__aa;
    const f = { aa: window.__aa, kind: tag === 'select' ? 'select' : tag === 'textarea' ? 'textarea'
      : ({ checkbox: 'checkbox', email: 'email', tel: 'tel' }[typ] || 'text'),
      label: L, required: req(e, L), name: e.name || '', options: [] };
    if (tag === 'select') f.options = [...e.options].map(o => [o.text.trim(), o.value])
      .filter(([t]) => t && !/^(--|select|please)/i.test(t));
    out.push(f);
  }
  return out.concat(Object.values(radios));
}
