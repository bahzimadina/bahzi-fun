/* =========================================================================
   Panel alat: Bandingkan teks (Text Diff)
   Dua versi teks dikirim ke server lewat multipart/form-data, diproses
   di memori dengan difflib.SequenceMatcher, lalu dibuang setelah selesai.
   Tidak ada teks yang disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('banding-teks-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('banding-teks-close'),
    limits: document.getElementById('banding-teks-limits'),
    note: document.getElementById('banding-teks-note'),
    teksA: document.getElementById('banding-teks-a'),
    teksB: document.getElementById('banding-teks-b'),
    spasi: document.getElementById('banding-teks-spasi'),
    huruf: document.getElementById('banding-teks-huruf'),
    status: document.getElementById('banding-teks-status'),
    reset: document.getElementById('banding-teks-reset'),
    submit: document.getElementById('banding-teks-submit'),
    result: document.getElementById('banding-teks-result'),
    ringkasan: document.getElementById('banding-teks-ringkasan'),
    daftar: document.getElementById('banding-teks-daftar'),
    copy: document.getElementById('banding-teks-copy'),
    download: document.getElementById('banding-teks-download')
  };

  var numberFmt = new Intl.NumberFormat('id-ID');

  var FALLBACK_LIMITS = {
    max_chars: 200000,
    max_bytes: 1000000,
    max_mb: 1,
    max_lines: 5000,
    defaults: {
      abaikan_spasi: true,
      peka_huruf: true
    }
  };

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    currentDiffText: ''
  };

  function setStatus(message, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(message));
  }

  function resetResults() {
    state.currentDiffText = '';
    if (el.result) el.result.hidden = true;
    if (el.ringkasan) el.ringkasan.innerHTML = '';
    if (el.daftar) el.daftar.innerHTML = '';
  }

  function updateControls() {
    var hasA = !!(el.teksA && el.teksA.value.length > 0);
    var hasB = !!(el.teksB && el.teksB.value.length > 0);
    var hasResult = !!(el.result && !el.result.hidden);

    if (el.submit) {
      el.submit.disabled = state.busy || (!hasA && !hasB);
      el.submit.textContent = state.busy ? 'Sedang membandingkan...' : 'Bandingkan';
    }
    if (el.reset) {
      el.reset.disabled = state.busy || (!hasA && !hasB && !hasResult);
    }
  }

  function describeLimits(online) {
    if (!el.limits) return;
    var chars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    var lines = state.limits.max_lines || FALLBACK_LIMITS.max_lines;
    var source = online ? 'aturan dari server' : 'aturan bawaan';
    el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter & ' + numberFmt.format(lines) + ' baris per teks, ' + source;
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/banding-teks/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_chars: data.max_chars || FALLBACK_LIMITS.max_chars,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
          max_lines: data.max_lines || FALLBACK_LIMITS.max_lines,
          defaults: data.defaults || FALLBACK_LIMITS.defaults
        };
        state.limitsLoaded = true;
        if (data.defaults) {
          if (typeof data.defaults.abaikan_spasi === 'boolean' && el.spasi) {
            el.spasi.checked = data.defaults.abaikan_spasi;
          }
          if (typeof data.defaults.peka_huruf === 'boolean' && el.huruf) {
            el.huruf.checked = data.defaults.peka_huruf;
          }
        }
        describeLimits(true);
      })
      .catch(function () {
        describeLimits(false);
      });
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      var code = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error) {
          message = parsed.error.message || '';
          code = parsed.error.code || '';
        }
      } catch (err) { /* diabaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan bandingkan teks belum tersambung ke server. Coba lagi nanti.';
        } else if (response.status === 413) {
          message = 'Teks terlalu panjang. Batasnya 200.000 karakter atau 5.000 baris per teks.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      } else if (code === 'TOO_LONG') {
        message += ' Silakan perpendek teks.';
      } else if (code === 'TOO_MANY_LINES') {
        message += ' Silakan kurangi jumlah baris.';
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function renderRingkasan(ringkasan) {
    if (!el.ringkasan) return;
    el.ringkasan.innerHTML = '';

    var cards = [
      { label: 'Baris lama', val: ringkasan.baris_a, classMod: '' },
      { label: 'Baris baru', val: ringkasan.baris_b, classMod: '' },
      { label: 'Sama', val: ringkasan.sama, classMod: 'banding-teks__stat--sama' },
      { label: 'Ditambah', val: ringkasan.tambah, classMod: 'banding-teks__stat--tambah' },
      { label: 'Dihapus', val: ringkasan.hapus, classMod: 'banding-teks__stat--hapus' },
      { label: 'Diubah', val: ringkasan.ubah, classMod: 'banding-teks__stat--ubah' },
      { label: 'Total beda', val: ringkasan.total_beda, classMod: ringkasan.total_beda > 0 ? 'banding-teks__stat--beda' : 'banding-teks__stat--sama' }
    ];

    var grid = document.createElement('div');
    grid.className = 'banding-teks__stats-grid';

    for (var i = 0; i < cards.length; i++) {
      var card = document.createElement('div');
      card.className = 'banding-teks__stat-card' + (cards[i].classMod ? ' ' + cards[i].classMod : '');

      var lbl = document.createElement('span');
      lbl.className = 'banding-teks__stat-label';
      lbl.textContent = cards[i].label;

      var num = document.createElement('span');
      num.className = 'banding-teks__stat-value';
      num.textContent = numberFmt.format(cards[i].val || 0);

      card.appendChild(lbl);
      card.appendChild(num);
      grid.appendChild(card);
    }

    el.ringkasan.appendChild(grid);

    if (ringkasan.identik) {
      var note = document.createElement('p');
      note.className = 'banding-teks__identik-note';
      note.textContent = 'Kedua versi teks identik. Tidak ada perbedaan susunan maupun baris.';
      el.ringkasan.appendChild(note);
    }
  }

  function renderLines(lines) {
    if (!el.daftar) return;
    el.daftar.innerHTML = '';

    var frag = document.createDocumentFragment();
    for (var i = 0; i < lines.length; i++) {
      var item = lines[i];
      var li = document.createElement('li');
      li.className = 'banding-teks__row banding-teks__row--' + item.jenis;
      li.setAttribute('data-jenis', item.jenis);

      var colA = document.createElement('span');
      colA.className = 'banding-teks__col-num banding-teks__col-num--a';
      colA.setAttribute('aria-label', item.nomor_a ? 'Baris lama ' + item.nomor_a : 'Bukan dari teks lama');
      colA.textContent = item.nomor_a ? String(item.nomor_a) : '';

      var colB = document.createElement('span');
      colB.className = 'banding-teks__col-num banding-teks__col-num--b';
      colB.setAttribute('aria-label', item.nomor_b ? 'Baris baru ' + item.nomor_b : 'Bukan dari teks baru');
      colB.textContent = item.nomor_b ? String(item.nomor_b) : '';

      var colSign = document.createElement('span');
      colSign.className = 'banding-teks__col-sign';
      var signChar = ' ';
      var signDesc = 'Sama';
      if (item.jenis === 'tambah') {
        signChar = '+';
        signDesc = 'Tambah';
      } else if (item.jenis === 'hapus') {
        signChar = '−';
        signDesc = 'Hapus';
      } else if (item.jenis === 'ubah') {
        signChar = '~';
        signDesc = 'Ubah';
      }
      colSign.textContent = signChar;
      colSign.setAttribute('aria-label', signDesc);
      colSign.setAttribute('title', signDesc);

      var colText = document.createElement('span');
      colText.className = 'banding-teks__col-text';

      if (item.jenis === 'ubah') {
        var oldWrap = document.createElement('del');
        oldWrap.className = 'banding-teks__inline-del';
        oldWrap.textContent = item.teks_a != null ? item.teks_a : '';

        var newWrap = document.createElement('ins');
        newWrap.className = 'banding-teks__inline-ins';
        newWrap.textContent = item.teks_b != null ? item.teks_b : '';

        colText.appendChild(oldWrap);
        colText.appendChild(document.createTextNode(' '));
        colText.appendChild(newWrap);
      } else if (item.jenis === 'hapus') {
        var delEl = document.createElement('del');
        delEl.textContent = item.teks != null ? item.teks : '';
        colText.appendChild(delEl);
      } else if (item.jenis === 'tambah') {
        var insEl = document.createElement('ins');
        insEl.textContent = item.teks != null ? item.teks : '';
        colText.appendChild(insEl);
      } else {
        colText.textContent = item.teks != null ? item.teks : '';
      }

      li.appendChild(colA);
      li.appendChild(colB);
      li.appendChild(colSign);
      li.appendChild(colText);
      frag.appendChild(li);
    }
    el.daftar.appendChild(frag);
  }

  function submitDiff() {
    if (state.busy) return;

    var valA = el.teksA ? el.teksA.value : '';
    var valB = el.teksB ? el.teksB.value : '';

    if (!valA.trim() && !valB.trim()) {
      setStatus('Masukkan setidaknya satu teks untuk dibandingkan.', 'error');
      if (el.teksA) el.teksA.focus();
      return;
    }

    var maxChars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (valA.length > maxChars || valB.length > maxChars) {
      setStatus('Teks terlalu panjang. Batasnya ' + numberFmt.format(maxChars) + ' karakter per teks.', 'error');
      return;
    }

    resetResults();

    var spasiVal = el.spasi ? el.spasi.checked : true;
    var hurufVal = el.huruf ? el.huruf.checked : true;

    var form = new FormData();
    form.append('teks_a', valA);
    form.append('teks_b', valB);
    form.append('abaikan_spasi', spasiVal ? 'true' : 'false');
    form.append('peka_huruf', hurufVal ? 'true' : 'false');

    state.busy = true;
    updateControls();
    setStatus('Sedang membandingkan teks...', 'busy');

    fetch(serverBase + '/api/banding-teks', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        state.currentDiffText = data.teks_selisih || '';
        renderRingkasan(data.ringkasan || {});
        renderLines(data.baris || []);
        if (el.result) el.result.hidden = false;

        var ringkasan = data.ringkasan || {};
        if (ringkasan.identik) {
          setStatus('Selesai. Kedua teks identik.', 'ok');
        } else {
          setStatus('Selesai. Ditemukan ' + numberFmt.format(ringkasan.total_beda || 0) + ' perbedaan baris.', 'ok');
        }
      })
      .catch(function (err) {
        if (el.result) el.result.hidden = true;
        var msg = (err && err.pesanLayanan === true && err.message)
          ? err.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
      })
      .then(function () {
        state.busy = false;
        updateControls();
      });
  }

  function copyResult() {
    if (!state.currentDiffText) {
      setStatus('Belum ada selisih teks untuk disalin.', 'error');
      return;
    }
    var text = state.currentDiffText;

    function fallbackCopy() {
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.top = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        var ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (ok) {
          setStatus('Selisih teks berhasil disalin.', 'ok');
        } else {
          setStatus('Tidak dapat menyalin selisih secara otomatis. Silakan salin manual.', 'error');
        }
      } catch (e) {
        setStatus('Tidak dapat menyalin selisih secara otomatis. Silakan salin manual.', 'error');
      }
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text)
        .then(function () {
          setStatus('Selisih teks berhasil disalin.', 'ok');
        })
        .catch(function () {
          fallbackCopy();
        });
    } else {
      fallbackCopy();
    }
  }

  function downloadResult() {
    if (!state.currentDiffText) {
      setStatus('Belum ada selisih teks untuk diunduh.', 'error');
      return;
    }
    var blob = new Blob([state.currentDiffText], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'selisih-teks.txt';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  }

  function resetAll() {
    if (state.busy) return;
    if (el.teksA) el.teksA.value = '';
    if (el.teksB) el.teksB.value = '';
    resetResults();
    setStatus('Masukkan dua teks, atur pilihan, lalu tekan "Bandingkan".', '');
    if (el.teksA) el.teksA.focus();
    updateControls();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="banding-teks"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
  }

  function open() {
    if (!panel.hidden) return;
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);
    loadLimits();

    var reduceMotion = false;
    try {
      reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { /* diabaikan */ }

    if (typeof panel.focus === 'function') {
      panel.focus({ preventScroll: true });
      if (el.teksA) {
        el.teksA.focus();
      }
      if ((!el.teksA || !el.teksA.value) && (!el.teksB || !el.teksB.value)) {
        setStatus('Masukkan dua teks, atur pilihan, lalu tekan "Bandingkan".', '');
      }
    }
    panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    syncTriggers(false);
    if (state.lastFocus && typeof state.lastFocus.focus === 'function' && document.contains(state.lastFocus)) {
      state.lastFocus.focus();
    } else {
      var trigger = document.querySelector('.tool-card__open[data-tool-action="banding-teks"]');
      if (trigger && typeof trigger.focus === 'function') {
        trigger.focus();
      }
    }
    state.lastFocus = null;
  }

  function toggle() {
    if (panel.hidden) open(); else close();
  }

  function onKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape' && panel.contains(document.activeElement)) {
      event.preventDefault();
      close();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      if (panel.contains(document.activeElement)) {
        event.preventDefault();
        submitDiff();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.teksA) el.teksA.addEventListener('input', updateControls);
  if (el.teksB) el.teksB.addEventListener('input', updateControls);

  if (el.submit) el.submit.addEventListener('click', submitDiff);
  if (el.reset) el.reset.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  // Daftarkan panel supaya kartu "Bandingkan teks" bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['banding-teks'] = toggle;

  updateControls();
})();
