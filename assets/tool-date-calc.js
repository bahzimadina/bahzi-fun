/* =========================================================================
   Panel alat: Kalkulator Tanggal (Date Calculator)
   Data dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada tanggal yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('date-calc-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('date-calc-title'),
    limits: document.getElementById('date-calc-limits'),
    note: document.getElementById('date-calc-note'),
    close: document.getElementById('date-calc-close'),
    mode: document.getElementById('date-calc-mode'),
    datesRow: document.getElementById('date-calc-dates-row'),
    fieldA: document.getElementById('date-calc-field-a'),
    labelA: document.getElementById('date-calc-label-a'),
    inputA: document.getElementById('date-calc-input-a'),
    fieldB: document.getElementById('date-calc-field-b'),
    labelB: document.getElementById('date-calc-label-b'),
    inputB: document.getElementById('date-calc-input-b'),
    today: document.getElementById('date-calc-today'),
    tambahKurangRow: document.getElementById('date-calc-tambah-kurang-row'),
    amountGroup: document.getElementById('date-calc-amount-group'),
    labelAmount: document.getElementById('date-calc-label-amount'),
    amount: document.getElementById('date-calc-amount'),
    unitGroup: document.getElementById('date-calc-unit-group'),
    labelUnit: document.getElementById('date-calc-label-unit'),
    unit: document.getElementById('date-calc-unit'),
    directionGroup: document.getElementById('date-calc-direction-group'),
    labelDirection: document.getElementById('date-calc-label-direction'),
    direction: document.getElementById('date-calc-direction'),
    status: document.getElementById('date-calc-status'),
    clear: document.getElementById('date-calc-clear'),
    submit: document.getElementById('date-calc-submit'),
    results: document.getElementById('date-calc-results'),
    resultHint: document.getElementById('date-calc-result-hint'),
    outputWrap: document.getElementById('date-calc-output-wrap'),
    heroValue: document.getElementById('date-calc-hero-value'),
    heroSymbol: document.getElementById('date-calc-hero-symbol'),
    sentence: document.getElementById('date-calc-sentence'),
    formula: document.getElementById('date-calc-formula'),
    catatan: document.getElementById('date-calc-catatan'),
    details: document.getElementById('date-calc-details'),
    copy: document.getElementById('date-calc-copy'),
    download: document.getElementById('date-calc-download')
  };

  var state = {
    modes: [],
    units: [],
    directions: [],
    today: '',
    minYear: 1900,
    maxYear: 2100,
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

  function updateModeUI() {
    if (!el.mode) return;
    var modeVal = el.mode.value || 'selisih';
    var modeData = getModeData(modeVal);

    if (modeVal === 'selisih') {
      if (el.fieldA) el.fieldA.hidden = false;
      if (el.fieldB) el.fieldB.hidden = false;
      if (el.tambahKurangRow) el.tambahKurangRow.hidden = true;
      if (el.today) el.today.hidden = true;
      if (el.labelA) el.labelA.textContent = (modeData && modeData.a_label) || 'Tanggal awal';
      if (el.labelB) el.labelB.textContent = (modeData && modeData.b_label) || 'Tanggal akhir';
    } else if (modeVal === 'tambah_kurang') {
      if (el.fieldA) el.fieldA.hidden = false;
      if (el.fieldB) el.fieldB.hidden = true;
      if (el.tambahKurangRow) el.tambahKurangRow.hidden = false;
      if (el.today) el.today.hidden = true;
      if (el.labelA) el.labelA.textContent = (modeData && modeData.a_label) || 'Tanggal acuan';
    } else if (modeVal === 'hari_apa') {
      if (el.fieldA) el.fieldA.hidden = false;
      if (el.fieldB) el.fieldB.hidden = true;
      if (el.tambahKurangRow) el.tambahKurangRow.hidden = true;
      if (el.today) el.today.hidden = true;
      if (el.labelA) el.labelA.textContent = (modeData && modeData.a_label) || 'Tanggal';
    } else if (modeVal === 'usia') {
      if (el.fieldA) el.fieldA.hidden = false;
      if (el.fieldB) el.fieldB.hidden = false;
      if (el.tambahKurangRow) el.tambahKurangRow.hidden = true;
      if (el.today) el.today.hidden = false;
      if (el.labelA) el.labelA.textContent = (modeData && modeData.a_label) || 'Tanggal lahir';
      if (el.labelB) el.labelB.textContent = (modeData && modeData.b_label) || 'Tanggal acuan (kosong = hari ini)';
    }

    updateControls();
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.heroSymbol) el.heroSymbol.textContent = '';
    if (el.sentence) el.sentence.textContent = '';
    if (el.formula) {
      el.formula.hidden = true;
      el.formula.textContent = '';
    }
    if (el.catatan) {
      el.catatan.hidden = true;
      el.catatan.textContent = '';
    }
    if (el.details) el.details.innerHTML = '';
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
    var modeVal = el.mode ? el.mode.value : 'selisih';
    var valA = el.inputA ? el.inputA.value.trim() : '';
    var valB = el.inputB ? el.inputB.value.trim() : '';
    var valAmt = el.amount ? el.amount.value.trim() : '';

    var valid = false;
    if (modeVal === 'selisih') {
      valid = valA.length > 0 && valB.length > 0;
    } else if (modeVal === 'tambah_kurang') {
      var num = parseInt(valAmt, 10);
      valid = valA.length > 0 && !isNaN(num) && num >= 0 && num <= 100000;
    } else if (modeVal === 'hari_apa') {
      valid = valA.length > 0;
    } else if (modeVal === 'usia') {
      valid = valA.length > 0;
    }

    var hasAnyInput = valA.length > 0 || valB.length > 0 || (valAmt.length > 0 && valAmt !== '7');
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !valid;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAnyInput && !hasOutput);
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/date-calc/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (!data) return;
        if (data.today) state.today = data.today;
        if (data.min_year) state.minYear = data.min_year;
        if (data.max_year) state.maxYear = data.max_year;

        var minStr = state.minYear + '-01-01';
        var maxStr = state.maxYear + '-12-31';
        if (el.inputA) {
          el.inputA.min = minStr;
          el.inputA.max = maxStr;
        }
        if (el.inputB) {
          el.inputB.min = minStr;
          el.inputB.max = maxStr;
        }

        if (Array.isArray(data.modes) && data.modes.length > 0) {
          state.modes = data.modes;
          if (el.mode) {
            var curMode = el.mode.value;
            el.mode.innerHTML = '';
            for (var i = 0; i < data.modes.length; i++) {
              var m = data.modes[i];
              var opt = document.createElement('option');
              opt.value = m.value;
              opt.textContent = m.label;
              if (m.value === curMode) opt.selected = true;
              el.mode.appendChild(opt);
            }
          }
        }

        if (Array.isArray(data.units) && data.units.length > 0) {
          state.units = data.units;
          if (el.unit) {
            el.unit.innerHTML = '';
            for (var j = 0; j < data.units.length; j++) {
              var u = data.units[j];
              var uOpt = document.createElement('option');
              uOpt.value = u.value;
              uOpt.textContent = u.label;
              el.unit.appendChild(uOpt);
            }
          }
        }

        if (Array.isArray(data.directions) && data.directions.length > 0) {
          state.directions = data.directions;
          if (el.direction) {
            el.direction.innerHTML = '';
            for (var k = 0; k < data.directions.length; k++) {
              var d = data.directions[k];
              var dOpt = document.createElement('option');
              dOpt.value = d.value;
              dOpt.textContent = d.label;
              el.direction.appendChild(dOpt);
            }
          }
        }

        state.limitsLoaded = true;
        updateModeUI();
      })
      .catch(function () {
        updateModeUI();
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.heroValue && data.hasil) {
      el.heroValue.textContent = data.hasil.teks;
    }
    if (el.heroSymbol && data.hasil) {
      el.heroSymbol.textContent = data.hasil.satuan || '';
    }

    if (el.sentence) {
      el.sentence.textContent = data.kalimat || '';
    }

    if (el.formula) {
      if (data.rumus) {
        el.formula.hidden = false;
        el.formula.textContent = data.rumus;
      } else {
        el.formula.hidden = true;
        el.formula.textContent = '';
      }
    }

    if (el.catatan) {
      if (data.catatan) {
        el.catatan.hidden = false;
        el.catatan.textContent = data.catatan;
      } else {
        el.catatan.hidden = true;
        el.catatan.textContent = '';
      }
    }

    if (el.details && Array.isArray(data.rincian)) {
      el.details.innerHTML = '';
      for (var i = 0; i < data.rincian.length; i++) {
        var item = data.rincian[i];
        var card = document.createElement('div');
        card.className = 'dc__stat-card';

        var labelSpan = document.createElement('span');
        labelSpan.className = 'dc__stat-label';
        labelSpan.textContent = item.label;

        var valueSpan = document.createElement('span');
        valueSpan.className = 'dc__stat-value';
        valueSpan.textContent = item.nilai;

        card.appendChild(labelSpan);
        card.appendChild(valueSpan);
        el.details.appendChild(card);
      }
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
          message = 'Layanan kalkulator tanggal belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Tanggal atau jumlah di luar batas yang didukung.';
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

    var modeVal = el.mode ? el.mode.value : 'selisih';
    var valA = el.inputA ? el.inputA.value.trim() : '';
    var valB = el.inputB ? el.inputB.value.trim() : '';
    var valAmt = el.amount ? el.amount.value.trim() : '7';
    var valUnit = el.unit ? el.unit.value : 'hari';
    var valDir = el.direction ? el.direction.value : 'maju';

    if (!valA) {
      setStatus('Masukkan tanggal terlebih dahulu.', 'error');
      if (el.inputA) el.inputA.focus();
      return;
    }

    if (modeVal === 'selisih' && !valB) {
      setStatus('Masukkan tanggal akhir terlebih dahulu.', 'error');
      if (el.inputB) el.inputB.focus();
      return;
    }

    if (modeVal === 'tambah_kurang' && !valAmt) {
      setStatus('Masukkan jumlah penambahan atau pengurangan.', 'error');
      if (el.amount) el.amount.focus();
      return;
    }

    var form = new FormData();
    form.append('mode', modeVal);
    form.append('a', valA);

    if (modeVal === 'selisih') {
      form.append('b', valB);
    } else if (modeVal === 'tambah_kurang') {
      form.append('amount', valAmt);
      form.append('unit', valUnit);
      form.append('direction', valDir);
    } else if (modeVal === 'usia') {
      if (valB) {
        form.append('b', valB);
      }
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung...', 'busy');

    fetch(serverBase + '/api/date-calc', { method: 'POST', body: form })
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
    var parts = [d.kalimat];
    if (d.rumus) parts.push('Rumus: ' + d.rumus);
    if (d.catatan) parts.push('Catatan: ' + d.catatan);
    var textToCopy = parts.join('\n');

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
      'Kalkulator Tanggal: ' + (d.mode_label || d.mode),
      '----------------------------------------',
      'Kalimat : ' + d.kalimat
    ];
    if (d.rumus) lines.push('Rumus   : ' + d.rumus);
    if (d.catatan) lines.push('Catatan : ' + d.catatan);

    if (Array.isArray(d.rincian) && d.rincian.length > 0) {
      lines.push('');
      lines.push('Rincian :');
      for (var i = 0; i < d.rincian.length; i++) {
        lines.push('  - ' + d.rincian[i].label + ': ' + d.rincian[i].nilai);
      }
    }

    lines.push('');
    lines.push('Perhitungan dilakukan di memori lalu dibuang, tidak disimpan di disk.');

    var content = lines.join('\n');
    revokeDownload();
    var blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    state.downloadUrl = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = 'hasil-kalkulator-tanggal.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function resetAll() {
    if (el.inputA) el.inputA.value = '';
    if (el.inputB) el.inputB.value = '';
    if (el.amount) el.amount.value = '7';
    resetResults();
    setStatus('Pilih mode, masukkan tanggal, lalu tekan "Hitung".', '');
    updateControls();
    if (el.inputA) el.inputA.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="date-calc"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'date-calc-panel');
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
      updateModeUI();
      resetResults();
      setStatus('Pilih mode, masukkan tanggal, lalu tekan "Hitung".', '');
      updateControls();
      if (el.inputA) el.inputA.focus();
    });
  }

  if (el.today) {
    el.today.addEventListener('click', function () {
      if (el.inputB) {
        el.inputB.value = state.today || new Date().toISOString().slice(0, 10);
        updateControls();
        el.inputB.focus();
      }
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitCalc();
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

  if (el.amount) {
    el.amount.addEventListener('input', updateControls);
    el.amount.addEventListener('keydown', onInputKeydown);
  }

  if (el.unit) {
    el.unit.addEventListener('change', updateControls);
  }

  if (el.direction) {
    el.direction.addEventListener('change', updateControls);
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

  // Daftarkan panel supaya kartu Date Calculator bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['date-calc'] = toggle;

  // Inisialisasi awal
  loadLimits();
  updateModeUI();
  updateControls();
})();
