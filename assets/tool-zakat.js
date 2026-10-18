/* =========================================================================
   Panel alat: Kalkulator Zakat (Zakat Calculator)
   Angka dikirim ke layanan lewat JSON, diproses di memori, lalu dibuang.
   Tidak ada data atau angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('zakat-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('zakat-close'),
    mode: document.getElementById('zakat-mode'),
    status: document.getElementById('zakat-status'),
    clear: document.getElementById('zakat-clear'),
    submit: document.getElementById('zakat-submit'),

    // Groups
    groupPenghasilan: document.getElementById('zakat-group-penghasilan'),
    groupMal: document.getElementById('zakat-group-mal'),
    groupFitrah: document.getElementById('zakat-group-fitrah'),

    // Inputs Penghasilan
    penghasilan: document.getElementById('zakat-penghasilan'),
    bonus: document.getElementById('zakat-bonus'),
    emasPenghasilan: document.getElementById('zakat-emas-penghasilan'),

    // Inputs Mal
    harta: document.getElementById('zakat-harta'),
    utang: document.getElementById('zakat-utang'),
    emasMal: document.getElementById('zakat-emas-mal'),
    haul: document.getElementById('zakat-haul'),

    // Inputs Fitrah
    jiwa: document.getElementById('zakat-jiwa'),
    hargaBeras: document.getElementById('zakat-harga-beras'),

    // Results
    results: document.getElementById('zakat-results'),
    resultHint: document.getElementById('zakat-result-hint'),
    outputWrap: document.getElementById('zakat-output-wrap'),
    statusBadge: document.getElementById('zakat-status-badge'),
    heroValue: document.getElementById('zakat-hero-value'),
    heroSub: document.getElementById('zakat-hero-sub'),
    summaryList: document.getElementById('zakat-summary-list'),
    catatan: document.getElementById('zakat-catatan'),
    copy: document.getElementById('zakat-copy')
  };

  var state = {
    busy: false,
    lastFocus: null,
    lastResult: null
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

  function getActiveMode() {
    return el.mode ? el.mode.value : 'penghasilan';
  }

  function formatRupiah(val) {
    if (typeof val !== 'number') {
      val = parseInt(val, 10) || 0;
    }
    var str = Math.round(val).toString();
    var formatted = str.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return 'Rp ' + formatted;
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.statusBadge) el.statusBadge.textContent = '';
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.heroSub) el.heroSub.textContent = '';
    if (el.summaryList) el.summaryList.innerHTML = '';
    if (el.catatan) el.catatan.textContent = '';
    state.lastResult = null;
  }

  function checkHasInput() {
    var mode = getActiveMode();
    if (mode === 'penghasilan') {
      var p = el.penghasilan ? el.penghasilan.value.trim() : '';
      var b = el.bonus ? el.bonus.value.trim() : '';
      var ep = el.emasPenghasilan ? el.emasPenghasilan.value.trim() : '';
      return {
        hasRequired: p.length > 0 && ep.length > 0,
        hasAny: p.length > 0 || b.length > 0 || ep.length > 0
      };
    } else if (mode === 'mal') {
      var h = el.harta ? el.harta.value.trim() : '';
      var u = el.utang ? el.utang.value.trim() : '';
      var em = el.emasMal ? el.emasMal.value.trim() : '';
      return {
        hasRequired: h.length > 0 && em.length > 0,
        hasAny: h.length > 0 || u.length > 0 || em.length > 0
      };
    } else if (mode === 'fitrah') {
      var j = el.jiwa ? el.jiwa.value.trim() : '';
      var hb = el.hargaBeras ? el.hargaBeras.value.trim() : '';
      return {
        hasRequired: j.length > 0 && hb.length > 0,
        hasAny: j.length > 0 || hb.length > 0
      };
    }
    return { hasRequired: false, hasAny: false };
  }

  function updateControls() {
    var check = checkHasInput();
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !check.hasRequired;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung zakat';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!check.hasAny && !hasOutput);
    }
  }

  function updateModeView() {
    var mode = getActiveMode();

    if (el.groupPenghasilan) el.groupPenghasilan.hidden = (mode !== 'penghasilan');
    if (el.groupMal) el.groupMal.hidden = (mode !== 'mal');
    if (el.groupFitrah) el.groupFitrah.hidden = (mode !== 'fitrah');

    // Salin harga emas antar kelompok bila salah satu sudah diisi
    if (mode === 'mal' && el.emasPenghasilan && el.emasMal && el.emasPenghasilan.value && !el.emasMal.value) {
      el.emasMal.value = el.emasPenghasilan.value;
    } else if (mode === 'penghasilan' && el.emasMal && el.emasPenghasilan && el.emasMal.value && !el.emasPenghasilan.value) {
      el.emasPenghasilan.value = el.emasMal.value;
    }

    resetResults();
    setStatus('Pilih jenis zakat, isi nilai yang diperlukan, lalu tekan "Hitung zakat".', '');
    updateControls();

    // Fokus ke input utama pada mode aktif
    var inputToFocus = null;
    if (mode === 'penghasilan') inputToFocus = el.penghasilan;
    else if (mode === 'mal') inputToFocus = el.harta;
    else if (mode === 'fitrah') inputToFocus = el.jiwa;

    if (inputToFocus) {
      setTimeout(function () { inputToFocus.focus(); }, 50);
    }
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    // Nilai besar
    if (el.heroValue) {
      el.heroValue.textContent = formatRupiah(data.zakat);
    }

    // Status badge
    if (el.statusBadge) {
      if (data.mode === 'fitrah') {
        el.statusBadge.textContent = 'Wajib ditunaikan';
        el.statusBadge.className = 'zk__badge zk__badge--ok';
      } else if (data.wajib) {
        el.statusBadge.textContent = 'Wajib zakat (2,5%)';
        el.statusBadge.className = 'zk__badge zk__badge--ok';
      } else {
        el.statusBadge.textContent = 'Belum mencapai nisab';
        el.statusBadge.className = 'zk__badge zk__badge--info';
      }
    }

    // Sub keterangan
    if (el.heroSub) {
      if (data.mode === 'fitrah') {
        el.heroSub.textContent = 'Setara dengan ' + (data.beras_kg ? data.beras_kg : '') + ' kg beras makanan pokok.';
      } else if (data.wajib) {
        el.heroSub.textContent = 'Nilai zakat dihitung 2,5% dari total yang memenuhi syarat.';
      } else {
        el.heroSub.textContent = 'Nilai belum mencapai batas minimal (nisab), jadi belum wajib mengeluarkan zakat.';
      }
    }

    // Rincian / ringkasan
    if (el.summaryList && Array.isArray(data.ringkasan)) {
      el.summaryList.innerHTML = '';
      for (var i = 0; i < data.ringkasan.length; i++) {
        var item = data.ringkasan[i];
        var dt = document.createElement('dt');
        dt.className = 'zk__summary-term';
        dt.textContent = item.label;

        var dd = document.createElement('dd');
        dd.className = 'zk__summary-desc';
        dd.textContent = item.nilai;

        el.summaryList.appendChild(dt);
        el.summaryList.appendChild(dd);
      }
    }

    // Catatan
    if (el.catatan) {
      el.catatan.textContent = data.catatan || '';
    }
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) {
          message = parsed.error.message;
        }
      } catch (err) { /* diabaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan kalkulator zakat belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Nilai masukan melebihi batas yang didukung.';
        } else {
          message = 'Terjadi kendala saat memproses perhitungan. Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitCalc() {
    if (state.busy) return;

    var mode = getActiveMode();
    var payload = { mode: mode };

    if (mode === 'penghasilan') {
      var p = el.penghasilan ? el.penghasilan.value.trim() : '';
      var b = el.bonus ? el.bonus.value.trim() : '';
      var ep = el.emasPenghasilan ? el.emasPenghasilan.value.trim() : '';

      if (!p || !ep) {
        setStatus('Isi penghasilan dan harga emas terlebih dahulu.', 'error');
        if (!p && el.penghasilan) el.penghasilan.focus();
        else if (!ep && el.emasPenghasilan) el.emasPenghasilan.focus();
        return;
      }

      payload.penghasilan = p;
      payload.bonus = b || '0';
      payload.emas = ep;
    } else if (mode === 'mal') {
      var h = el.harta ? el.harta.value.trim() : '';
      var u = el.utang ? el.utang.value.trim() : '';
      var em = el.emasMal ? el.emasMal.value.trim() : '';
      var haul = el.haul ? el.haul.checked : true;

      if (!h || !em) {
        setStatus('Isi total harta simpanan dan harga emas terlebih dahulu.', 'error');
        if (!h && el.harta) el.harta.focus();
        else if (!em && el.emasMal) el.emasMal.focus();
        return;
      }

      payload.harta = h;
      payload.utang = u || '0';
      payload.emas = em;
      payload.haul = haul;
    } else if (mode === 'fitrah') {
      var j = el.jiwa ? el.jiwa.value.trim() : '';
      var hb = el.hargaBeras ? el.hargaBeras.value.trim() : '';

      if (!j || !hb) {
        setStatus('Isi jumlah jiwa dan harga beras terlebih dahulu.', 'error');
        if (!j && el.jiwa) el.jiwa.focus();
        else if (!hb && el.hargaBeras) el.hargaBeras.focus();
        return;
      }

      payload.jiwa = j;
      payload.harga_beras = hb;
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung...', 'busy');

    fetch(serverBase + '/api/zakat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('Perhitungan selesai.', 'ok');
      })
      .catch(function (err) {
        resetResults();
        var msg = (err && err.pesanLayanan === true && err.message)
          ? err.message
          : 'Koneksi ke layanan perhitungan gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
      })
      .finally(function () {
        state.busy = false;
        updateControls();
      });
  }

  function copyResult() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var lines = [
      'Kalkulator Zakat: ' + (d.mode === 'penghasilan' ? 'Zakat Penghasilan' : (d.mode === 'mal' ? 'Zakat Harta' : 'Zakat Fitrah')),
      'Kewajiban Zakat: ' + formatRupiah(d.zakat),
      'Status: ' + (d.wajib ? 'Sudah mencapai nisab / wajib ditunaikan' : 'Belum mencapai nisab'),
      '----------------------------------------'
    ];

    if (Array.isArray(d.ringkasan)) {
      for (var i = 0; i < d.ringkasan.length; i++) {
        lines.push(d.ringkasan[i].label + ': ' + d.ringkasan[i].nilai);
      }
    }

    if (d.catatan) {
      lines.push('');
      lines.push('Catatan: ' + d.catatan);
    }

    var textToCopy = lines.join('\n');

    function notify(ok) {
      if (ok) {
        setStatus('Hasil perhitungan disalin.', 'ok');
      } else {
        setStatus('Gagal menyalin hasil.', 'error');
      }
      if (el.copy) {
        var orig = el.copy.textContent;
        el.copy.textContent = ok ? 'Tersalin!' : 'Gagal salin';
        setTimeout(function () {
          el.copy.textContent = orig;
        }, 1500);
      }
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(textToCopy).then(function () {
        notify(true);
      }).catch(function () {
        notify(false);
      });
    } else {
      var ta = document.createElement('textarea');
      ta.value = textToCopy;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        var ok = document.execCommand('copy');
        notify(ok);
      } catch (err) {
        notify(false);
      }
      document.body.removeChild(ta);
    }
  }

  function resetAll() {
    var mode = getActiveMode();
    if (mode === 'penghasilan') {
      if (el.penghasilan) el.penghasilan.value = '';
      if (el.bonus) el.bonus.value = '';
      if (el.emasPenghasilan) el.emasPenghasilan.value = '';
      if (el.penghasilan) el.penghasilan.focus();
    } else if (mode === 'mal') {
      if (el.harta) el.harta.value = '';
      if (el.utang) el.utang.value = '';
      if (el.emasMal) el.emasMal.value = '';
      if (el.haul) el.haul.checked = true;
      if (el.harta) el.harta.focus();
    } else if (mode === 'fitrah') {
      if (el.jiwa) el.jiwa.value = '';
      if (el.hargaBeras) el.hargaBeras.value = '';
      if (el.jiwa) el.jiwa.focus();
    }
    resetResults();
    setStatus('Pilih jenis zakat, isi nilai yang diperlukan, lalu tekan "Hitung zakat".', '');
    updateControls();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="zakat"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'zakat-panel');
    }
  }

  function open() {
    if (!panel.hidden) return;
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);

    var reduceMotion = false;
    try {
      reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { /* abaikan */ }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    updateModeView();
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    syncTriggers(false);
    if (state.lastFocus && typeof state.lastFocus.focus === 'function' && document.contains(state.lastFocus)) {
      state.lastFocus.focus();
    }
    state.lastFocus = null;
  }

  function toggle() {
    if (panel.hidden) {
      open();
    } else {
      close();
    }
  }

  // Event Listeners
  if (el.close) el.close.addEventListener('click', close);
  if (el.mode) el.mode.addEventListener('change', updateModeView);

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var check = checkHasInput();
      if (check.hasRequired) {
        submitCalc();
      }
    }
  }

  var inputs = [
    el.penghasilan,
    el.bonus,
    el.emasPenghasilan,
    el.harta,
    el.utang,
    el.emasMal,
    el.jiwa,
    el.hargaBeras
  ];

  for (var i = 0; i < inputs.length; i++) {
    if (inputs[i]) {
      inputs[i].addEventListener('input', updateControls);
      inputs[i].addEventListener('keydown', onInputKeydown);
    }
  }

  if (el.haul) {
    el.haul.addEventListener('change', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitCalc);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);

  function onGlobalKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape' && panel.contains(document.activeElement)) {
      event.preventDefault();
      close();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      if (panel.contains(document.activeElement)) {
        event.preventDefault();
        submitCalc();
      }
    }
  }
  document.addEventListener('keydown', onGlobalKeydown);

  // Daftarkan panel ke sistem pembuka kartu OmniTools
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['zakat'] = toggle;

  // Inisialisasi awal
  updateControls();
})();
