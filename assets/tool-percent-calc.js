/* =========================================================================
   Panel alat: Kalkulator Persen (Percent Calculator)
   Angka dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('percent-calc-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('percent-calc-title'),
    limits: document.getElementById('percent-calc-limits'),
    note: document.getElementById('percent-calc-note'),
    close: document.getElementById('percent-calc-close'),
    mode: document.getElementById('percent-calc-mode'),
    labelA: document.getElementById('percent-calc-label-a'),
    inputA: document.getElementById('percent-calc-input-a'),
    labelB: document.getElementById('percent-calc-label-b'),
    inputB: document.getElementById('percent-calc-input-b'),
    hint: document.getElementById('percent-calc-hint'),
    status: document.getElementById('percent-calc-status'),
    clear: document.getElementById('percent-calc-clear'),
    submit: document.getElementById('percent-calc-submit'),
    results: document.getElementById('percent-calc-results'),
    resultHint: document.getElementById('percent-calc-result-hint'),
    outputWrap: document.getElementById('percent-calc-output-wrap'),
    heroValue: document.getElementById('percent-calc-hero-value'),
    heroSymbol: document.getElementById('percent-calc-hero-symbol'),
    sentence: document.getElementById('percent-calc-sentence'),
    formula: document.getElementById('percent-calc-formula'),
    copy: document.getElementById('percent-calc-copy'),
    download: document.getElementById('percent-calc-download')
  };

  var FALLBACK_MODES = [
    {
      value: 'persen_dari',
      label: 'Berapa persen dari sebuah angka',
      a_label: 'Persen (%)',
      b_label: 'Angka',
      hasil_satuan: '',
      contoh: { a: '20', b: '150' }
    },
    {
      value: 'berapa_persen',
      label: 'Sebuah angka itu berapa persen dari angka lain',
      a_label: 'Bagian',
      b_label: 'Total',
      hasil_satuan: '%',
      contoh: { a: '45', b: '180' }
    },
    {
      value: 'perubahan',
      label: 'Naik atau turun berapa persen',
      a_label: 'Angka awal',
      b_label: 'Angka akhir',
      hasil_satuan: '%',
      contoh: { a: '200', b: '250' }
    },
    {
      value: 'tambah_persen',
      label: 'Angka ditambah persen',
      a_label: 'Persen (%)',
      b_label: 'Angka dasar',
      hasil_satuan: '',
      contoh: { a: '10', b: '150' }
    },
    {
      value: 'kurang_persen',
      label: 'Angka dikurangi persen (diskon)',
      a_label: 'Persen (%)',
      b_label: 'Angka dasar',
      hasil_satuan: '',
      contoh: { a: '15', b: '200' }
    }
  ];

  var state = {
    modes: FALLBACK_MODES,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    downloadUrl: null
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

  function getModeData(modeVal) {
    for (var i = 0; i < state.modes.length; i++) {
      if (state.modes[i].value === modeVal) {
        return state.modes[i];
      }
    }
    return state.modes[0] || null;
  }

  function updateModeLabels() {
    if (!el.mode) return;
    var modeData = getModeData(el.mode.value);
    if (!modeData) return;
    if (el.labelA) el.labelA.textContent = modeData.a_label;
    if (el.labelB) el.labelB.textContent = modeData.b_label;
    if (el.inputA && modeData.contoh) el.inputA.placeholder = 'Mis. ' + modeData.contoh.a;
    if (el.inputB && modeData.contoh) el.inputB.placeholder = 'Mis. ' + modeData.contoh.b;
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.heroSymbol) el.heroSymbol.textContent = '';
    if (el.sentence) el.sentence.textContent = '';
    if (el.formula) el.formula.textContent = '';
    state.lastResult = null;
    revokeDownload();
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }
  }

  function updateControls() {
    var valA = el.inputA ? el.inputA.value.trim() : '';
    var valB = el.inputB ? el.inputB.value.trim() : '';
    var hasVal = (valA.length > 0 && valB.length > 0);
    var hasAnyVal = (valA.length > 0 || valB.length > 0);
    var hasOutput = !!(state.lastResult);

    if (el.submit) {
      el.submit.disabled = state.busy || !hasVal;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAnyVal && !hasOutput);
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/percent-calc/limits', { headers: { credentials: 'same-origin', Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data && Array.isArray(data.modes) && data.modes.length > 0) {
          state.modes = data.modes;
          if (el.mode) {
            var currentVal = el.mode.value;
            el.mode.innerHTML = '';
            for (var i = 0; i < data.modes.length; i++) {
              var m = data.modes[i];
              var opt = document.createElement('option');
              opt.value = m.value;
              opt.textContent = m.label;
              if (m.value === currentVal) opt.selected = true;
              el.mode.appendChild(opt);
            }
          }
        }
        state.limitsLoaded = true;
        updateModeLabels();
      })
      .catch(function () {
        updateModeLabels();
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.heroValue) el.heroValue.textContent = data.hasil.teks;
    if (el.heroSymbol) el.heroSymbol.textContent = data.hasil.satuan || '';

    if (el.sentence) el.sentence.textContent = data.kalimat;
    if (el.formula) el.formula.textContent = data.rumus;
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
          message = 'Layanan kalkulator persen belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Nilai di luar jangkauan yang didukung (maksimum 10¹⁵).';
        } else if (response.status === 422) {
          message = 'Pembagian dengan angka nol tidak bisa dihitung.';
        } else {
          message = 'Terjadi kendala saat memproses perhitungan (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitCalc() {
    if (state.busy) return;

    var valA = el.inputA ? el.inputA.value.trim() : '';
    var valB = el.inputB ? el.inputB.value.trim() : '';

    if (!valA || !valB) {
      setStatus('Masukkan kedua angka terlebih dahulu.', 'error');
      if (!valA && el.inputA) {
        el.inputA.focus();
      } else if (!valB && el.inputB) {
        el.inputB.focus();
      }
      return;
    }

    var modeVal = el.mode ? el.mode.value : 'persen_dari';

    var form = new FormData();
    form.append('mode', modeVal);
    form.append('a', valA);
    form.append('b', valB);

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung...', 'busy');

    fetch(serverBase + '/api/percent-calc', { method: 'POST', body: form })
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
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
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
    var textToCopy = d.kalimat + ' (' + d.rumus + ')';

    function notify(ok) {
      if (ok) {
        setStatus('Hasil disalin.', 'ok');
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

  function downloadResult() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var lines = [
      'Kalkulator Persen: ' + d.mode_label,
      '----------------------------------------',
      'Kalimat : ' + d.kalimat,
      'Rumus   : ' + d.rumus,
      'Hasil   : ' + d.hasil.teks + (d.hasil.satuan ? ' ' + d.hasil.satuan : ''),
      '',
      'Angka diproses di memori lalu dibuang, tidak disimpan.'
    ];

    var content = lines.join('\n');
    revokeDownload();
    var blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    state.downloadUrl = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = 'hitung-persen.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function resetAll() {
    if (el.inputA) el.inputA.value = '';
    if (el.inputB) el.inputB.value = '';
    resetResults();
    setStatus('Pilih mode, masukkan angka, lalu tekan "Hitung".', '');
    updateControls();
    if (el.inputA) el.inputA.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="percent-calc"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'percent-calc-panel');
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
    } catch (e) { /* abaikan */ }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    if (el.inputA) {
      setTimeout(function () { el.inputA.focus(); }, 100);
    }
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    syncTriggers(false);
    revokeDownload();
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

  if (el.mode) {
    el.mode.addEventListener('change', function () {
      updateModeLabels();
      resetResults();
      setStatus('Pilih mode, masukkan angka, lalu tekan "Hitung".', '');
      updateControls();
      if (el.inputA) el.inputA.focus();
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var valA = el.inputA ? el.inputA.value.trim() : '';
      var valB = el.inputB ? el.inputB.value.trim() : '';
      if (valA.length > 0 && valB.length > 0) {
        submitCalc();
      } else if (!valA && el.inputA) {
        el.inputA.focus();
      } else if (!valB && el.inputB) {
        el.inputB.focus();
      }
    }
  }

  if (el.inputA) {
    el.inputA.addEventListener('input', updateControls);
    el.inputA.addEventListener('keydown', onInputKeydown);
  }

  if (el.inputB) {
    el.inputB.addEventListener('input', updateControls);
    el.inputB.addEventListener('keydown', onInputKeydown);
  }

  if (el.submit) el.submit.addEventListener('click', submitCalc);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

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
        submitCalc();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel supaya kartu Kalkulator Persen bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['percent-calc'] = toggle;

  // Inisialisasi bawaan
  updateModeLabels();
  updateControls();
})();
