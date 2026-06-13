([wantLabel, wantKind]) => {
  const lab = (e) => {
    const al = e.getAttribute('aria-label'); if (al) return al;
    if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l && l.innerText.trim()) return l.innerText; }
    const cl = e.closest('label'); if (cl && cl.innerText.trim()) return cl.innerText;
    let n = e.closest('div,fieldset');
    for (let i = 0; i < 3 && n; i++) { const lb = n.querySelector('label,legend,.text,[class*=application-label]'); if (lb && lb.innerText.trim()) return lb.innerText; n = n.parentElement; }
    return e.placeholder || e.name || '';
  };
  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 300);
  for (const e of document.querySelectorAll('input, textarea, select')) {
    const tag = e.tagName.toLowerCase(), typ = (e.type || 'text').toLowerCase();
    const kind = typ === 'file' ? 'file' : tag === 'select' ? 'select' : tag === 'textarea' ? 'textarea'
      : ({ checkbox: 'checkbox', email: 'email', tel: 'tel', radio: 'radio' }[typ] || 'text');
    if (kind !== wantKind && !(wantKind === 'radio-group' && kind === 'radio')) continue;
    let L = norm(lab(e));
    if (wantKind === 'file') {
      let n = e.closest('div,section,fieldset');
      for (let i = 0; i < 4 && n; i++) { const t = (n.innerText || '').slice(0, 120); if (/resume|cv|cover/i.test(t)) { L = norm(t); break; } n = n.parentElement; }
    }
    if (L === wantLabel || (wantKind === 'file' && (L.startsWith(wantLabel.slice(0, 20)) || wantLabel.startsWith(L.slice(0, 20))))) {
      window.__aa = (window.__aa || 0) + 1; e.dataset.aa = String(window.__aa); return window.__aa;
    }
  }
  return null;
}
