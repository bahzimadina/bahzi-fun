/* =========================================================================
   Panel alat: Hitung Keramik Lantai
   Angka dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('keramik-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('keramik-close'),
    modeRuangan: document.getElementById('keramik-mode-ruangan'),
    modeLuas: document.getElementById('keramik-mode-luas'),
    groupRuangan: document.getElementById('keramik-group-ruangan'),
    groupLuas: document.getElementById('keramik-group-luas'),
    inputPanjang: document.getElementById('keramik-input-panjang'),
    inputLebar: document.getElementById('keramik-input-lebar'),
    inputLuas: document.getElementById('keramik-input-luas'),
    ukuran: document.getElementById('keramik-ukuran'),
    groupKustom: document.getElementById('keramik-group-kustom'),
    inputUkuranPanjang: document.getElementById('keramik-ukuran-panjang'),
    inputUkuranLebar: document.getElementById('keramik-ukuran-lebar'),
    inputCadangan: document.getElementById('keramik-cadangan'),
    inputIsiDus: document.getElementById('keramik-isi-dus'),
    inputHargaDus: document.getElementById('keramik-harga-dus'),
    status: document.getElementById('keramik-status'),
    clear: document.getElementById('keramik-clear'),
    submit: document.getElementById('keramik-submit'),
    results: document.getElementById('keramik-results'),
    resultHint: document.getElementById('keramik-result-hint'),
    outputWrap: document.getElementById('keramik-output-wrap'),
    heroValue: document.getElementById('keramik-hero-value'),
    heroSymbol: document.getElementById('keramik-hero-symbol'),
    summaryText: document.getElementById('keramik-summary-text'),
    statTerpasang: document.getElementById('keramik-stat-terpasang'),
    statCadangan: document.getElementById('keramik-stat-cadangan'),
    statDibeli: document.getElementById('keramik-stat-dibeli'),
    statSisa: document.getElementById('keramik-stat-sisa'),
    statBiayaTotal: document.getElementById('keramik-stat-biaya-total'),
    statBiayaM2: document.getElementById('keramik-stat-biaya-m2'),
    statOrientasi: document.getElementById('keramik-stat-orientasi'),
    itemOrientasi: document.getElementById('keramik-item-orientasi'),
    itemBiayaTotal: document.getElementById('keramik-item-biaya-total'),
    itemBiayaM2: document.getElementById('keramik-item-biaya-m2'),
    notesList: document.getElementById('keramik-notes-list'),
    copy: document.getElementById('keramik-copy'),
    download: document.getElementById('keramik-download')
  };

  var state = {
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

  function getActiveMode() {
    if (el.modeLuas && el.modeLuas.checked) {
      return 'luas';
    }
    return 'ruangan';
  }

  function formatRibuan(n) {
    if (n === null || n === undefined) return '-';
    var num = Math.round(Number(n));
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function updateModeVisibility() {
    var mode = getActiveMode();
    if (mode === 'luas') {
      if (el.groupRuangan) el.groupRuangan.hidden = true;
      if (el.groupLuas) el.groupLuas.hidden = false;
    } else {
      if (el.groupRuangan) el.groupRuangan.hidden = false;
      if (el.groupLuas) el.groupLuas.hidden = true;
    }
    updateControls();
  }

  function updateUkuranVisibility() {
    var isKustom = el.ukuran && el.ukuran.value === 'kustom';
    if (el.groupKustom) {
      el.groupKustom.hidden = !isKustom;
    }
    updateControls();
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.heroSymbol) el.heroSymbol.textContent = '';
    if (el.summaryText) el.summaryText.textContent = '';
    if (el.notesList) el.notesList.innerHTML = '';
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
    var mode = getActiveMode();
    var hasRequired = false;

    if (mode === 'ruangan') {
      var p = el.inputPanjang ? el.inputPanjang.value.trim() : '';
      var l = el.inputLebar ? el.inputLebar.value.trim() : '';
      hasRequired = (p.length > 0 && l.length > 0);
    } else {
      var luas = el.inputLuas ? el.inputLuas.value.trim() : '';
      hasRequired = (luas.length > 0);
    }

    if (el.ukuran && el.ukuran.value === 'kustom') {
      var kp = el.inputUkuranPanjang ? el.inputUkuranPanjang.value.trim() : '';
      var kl = el.inputUkuranLebar ? el.inputUkuranLebar.value.trim() : '';
      if (!kp || !kl) {
        hasRequired = false;
      }
    }

    var hasAny = false;
    if (el.inputPanjang && el.inputPanjang.value.trim()) hasAny = true;
    if (el.inputLebar && el.inputLebar.value.trim()) hasAny = true;
    if (el.inputLuas && el.inputLuas.value.trim()) hasAny = true;
    if (el.inputUkuranPanjang && el.inputUkuranPanjang.value.trim()) hasAny = true;
    if (el.inputUkuranLebar && el.inputUkuranLebar.value.trim()) hasAny = true;
    if (el.inputHargaDus && el.inputHargaDus.value.trim()) hasAny = true;
    if (el.inputIsiDus && el.inputIsiDus.value.trim()) hasAny = true;
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !hasRequired;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung kebutuhan';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAny && !hasOutput);
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/keramik/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data && Array.isArray(data.ukuran_pilihan) && el.ukuran) {
          var currentVal = el.ukuran.value || '40x40';
          el.ukuran.innerHTML = '';
          for (var i = 0; i < data.ukuran_pilihan.length; i++) {
            var item = data.ukuran_pilihan[i];
            var opt = document.createElement('option');
            opt.value = item.kode;
            opt.textContent = item.label;
            if (item.kode === currentVal) {
              opt.selected = true;
            }
            el.ukuran.appendChild(opt);
          }
          if (!el.ukuran.value && data.ukuran_pilihan.length > 0) {
            el.ukuran.value = data.ukuran_pilihan[0].kode;
          }
        }
        state.limitsLoaded = true;
        updateUkuranVisibility();
      })
      .catch(function () {
        updateUkuranVisibility();
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.heroValue) el.heroValue.textContent = data.dus;
    if (el.heroSymbol) el.heroSymbol.textContent = 'dus (' + data.keping_dibeli + ' keping)';

    var sisaTeks = data.sisa_keping + ' keping (' + data.sisa_persen.toString().replace('.', ',') + '%)';
    var ringkasan = 'Total luas lantai ' + data.luas_m2.toString().replace('.', ',') + ' m². ' +
      'Kebutuhan ' + data.keping_dasar + ' keping, ditambah cadangan ' + data.cadangan_persen +
      '% menjadi ' + data.keping_cadangan + ' keping.';
    if (data.isi_dus_perkiraan) {
      ringkasan += ' Isi per dus memakai perkiraan ' + data.isi_dus + ' keping.';
    }
    if (el.summaryText) el.summaryText.textContent = ringkasan;

    if (el.statTerpasang) el.statTerpasang.textContent = data.keping_dasar + ' keping';
    if (el.statCadangan) el.statCadangan.textContent = data.keping_cadangan + ' keping (' + data.cadangan_persen + '%)';
    if (el.statDibeli) el.statDibeli.textContent = data.keping_dibeli + ' keping (' + data.dus + ' dus)';
    if (el.statSisa) el.statSisa.textContent = sisaTeks;

    if (el.itemOrientasi) {
      if (data.orientasi) {
        el.itemOrientasi.hidden = false;
        if (el.statOrientasi) el.statOrientasi.textContent = data.orientasi;
      } else {
        el.itemOrientasi.hidden = true;
      }
    }

    if (el.itemBiayaTotal) {
      if (data.biaya_total !== null && data.biaya_total !== undefined) {
        el.itemBiayaTotal.hidden = false;
        if (el.statBiayaTotal) el.statBiayaTotal.textContent = 'Rp ' + formatRibuan(data.biaya_total);
      } else {
        el.itemBiayaTotal.hidden = true;
      }
    }

    if (el.itemBiayaM2) {
      if (data.biaya_per_m2 !== null && data.biaya_per_m2 !== undefined) {
        el.itemBiayaM2.hidden = false;
        if (el.statBiayaM2) el.statBiayaM2.textContent = 'Rp ' + formatRibuan(data.biaya_per_m2) + ' / m²';
      } else {
        el.itemBiayaM2.hidden = true;
      }
    }

    if (el.notesList) {
      el.notesList.innerHTML = '';
      if (Array.isArray(data.catatan)) {
        for (var i = 0; i < data.catatan.length; i++) {
          var li = document.createElement('li');
          li.textContent = data.catatan[i];
          el.notesList.appendChild(li);
        }
      }
    }
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed) {
          if (parsed.error && parsed.error.message) {
            message = parsed.error.message;
          } else if (parsed.detail && parsed.detail.message) {
            message = parsed.detail.message;
          } else if (typeof parsed.detail === 'string') {
            message = parsed.detail;
          }
        }
      } catch (err) { /* diabaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan hitung keramik belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Jumlah kebutuhan keramik melebihi batas yang didukung.';
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

    var mode = getActiveMode();
    var formData = new FormData();
    formData.append('mode', mode);

    if (mode === 'ruangan') {
      var p = el.inputPanjang ? el.inputPanjang.value.trim() : '';
      var l = el.inputLebar ? el.inputLebar.value.trim() : '';
      if (!p || !l) {
        setStatus('Masukkan panjang dan lebar ruangan terlebih dahulu.', 'error');
        if (!p && el.inputPanjang) el.inputPanjang.focus();
        else if (!l && el.inputLebar) el.inputLebar.focus();
        return;
      }
      formData.append('panjang', p);
      formData.append('lebar', l);
    } else {
      var luas = el.inputLuas ? el.inputLuas.value.trim() : '';
      if (!luas) {
        setStatus('Masukkan luas lantai terlebih dahulu.', 'error');
        if (el.inputLuas) el.inputLuas.focus();
        return;
      }
      formData.append('luas', luas);
    }

    var ukuranVal = el.ukuran ? el.ukuran.value : '40x40';
    formData.append('ukuran', ukuranVal);

    if (ukuranVal === 'kustom') {
      var kp = el.inputUkuranPanjang ? el.inputUkuranPanjang.value.trim() : '';
      var kl = el.inputUkuranLebar ? el.inputUkuranLebar.value.trim() : '';
      if (!kp || !kl) {
        setStatus('Masukkan panjang dan lebar keramik kustom terlebih dahulu.', 'error');
        if (!kp && el.inputUkuranPanjang) el.inputUkuranPanjang.focus();
        else if (!kl && el.inputUkuranLebar) el.inputUkuranLebar.focus();
        return;
      }
      formData.append('ukuran_panjang', kp);
      formData.append('ukuran_lebar', kl);
    }

    var cadanganVal = el.inputCadangan ? el.inputCadangan.value.trim() : '';
    if (cadanganVal) {
      formData.append('cadangan', cadanganVal);
    }

    var isiDusVal = el.inputIsiDus ? el.inputIsiDus.value.trim() : '';
    if (isiDusVal) {
      formData.append('isi_dus', isiDusVal);
    }

    var hargaDusVal = el.inputHargaDus ? el.inputHargaDus.value.trim() : '';
    if (hargaDusVal) {
      formData.append('harga_dus', hargaDusVal);
    }

    state.busy = true;
    updateControls();
    setStatus('Menghitung kebutuhan keramik...', 'busy');

    fetch(serverBase + '/api/keramik', {
      method: 'POST',
      body: formData,
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) {
          return readServerError(response);
        }
        return response.json();
      })
      .then(function (data) {
        state.busy = false;
        renderResults(data);
        setStatus('Perhitungan selesai. ' + data.dus + ' dus diperlukan.', 'success');
        updateControls();
      })
      .catch(function (err) {
        state.busy = false;
        resetResults();
        var msg = (err && err.pesanLayanan)
          ? err.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
        updateControls();
      });
  }

  function buildResultSummaryText(data) {
    if (!data) return '';
    var lines = [];
    lines.push('Hitung Keramik Lantai - bahzi.fun');
    lines.push('----------------------------------------');
    if (data.mode === 'ruangan') {
      lines.push('Mode: Ukuran ruangan (panjang x lebar)');
    } else {
      lines.push('Mode: Luas lantai m2');
    }
    lines.push('Luas total: ' + data.luas_m2.toString().replace('.', ',') + ' m2');
    lines.push('Ukuran keramik: ' + data.ukuran.panjang_cm + ' x ' + data.ukuran.lebar_cm + ' cm (' + data.ukuran.luas_keping_m2.toString().replace('.', ',') + ' m2/keping)');
    if (data.orientasi) {
      lines.push('Orientasi susunan: ' + data.orientasi);
    }
    lines.push('Kebutuhan keping dasar: ' + data.keping_dasar + ' keping');
    lines.push('Cadangan: ' + data.cadangan_persen + '% (' + data.keping_cadangan + ' keping)');
    lines.push('Isi per dus: ' + data.isi_dus + ' keping' + (data.isi_dus_perkiraan ? ' (perkiraan)' : ''));
    lines.push('Jumlah dus dibeli: ' + data.dus + ' dus');
    lines.push('Total keping dibeli: ' + data.keping_dibeli + ' keping');
    lines.push('Sisa keping: ' + data.sisa_keping + ' keping (' + data.sisa_persen.toString().replace('.', ',') + '%)');
    if (data.biaya_total !== null && data.biaya_total !== undefined) {
      lines.push('Perkiraan biaya total: Rp ' + formatRibuan(data.biaya_total));
    }
    if (data.biaya_per_m2 !== null && data.biaya_per_m2 !== undefined) {
      lines.push('Perkiraan biaya per m2: Rp ' + formatRibuan(data.biaya_per_m2) + ' / m2');
    }
    if (Array.isArray(data.catatan) && data.catatan.length > 0) {
      lines.push('Catatan:');
      for (var i = 0; i < data.catatan.length; i++) {
        lines.push('- ' + data.catatan[i]);
      }
    }
    lines.push('----------------------------------------');
    lines.push('Hitungan memakai susunan lurus dan keping utuh. Pola dipotong miring atau ruangan bersudut banyak perlu tambahan.');
    return lines.join('\n');
  }

  function copyResult() {
    if (!state.lastResult) return;
    var text = buildResultSummaryText(state.lastResult);
    if (!text) return;

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text).then(function () {
        setStatus('Hasil berhasil disalin ke papan klip.', 'success');
      }).catch(function () {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try {
      var ok = document.execCommand('copy');
      if (ok) {
        setStatus('Hasil berhasil disalin ke papan klip.', 'success');
      } else {
        setStatus('Gagal menyalin hasil.', 'error');
      }
    } catch (e) {
      setStatus('Gagal menyalin hasil.', 'error');
    }
    document.body.removeChild(ta);
  }

  function downloadResult() {
    if (!state.lastResult) return;
    revokeDownload();

    var text = buildResultSummaryText(state.lastResult);
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    state.downloadUrl = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = 'hitung-keramik-lantai.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatus('Berkas ringkasan .txt berhasil diunduh.', 'success');
  }

  function resetAll() {
    if (el.modeRuangan) el.modeRuangan.checked = true;
    if (el.modeLuas) el.modeLuas.checked = false;
    if (el.inputPanjang) el.inputPanjang.value = '';
    if (el.inputLebar) el.inputLebar.value = '';
    if (el.inputLuas) el.inputLuas.value = '';
    if (el.ukuran) el.ukuran.value = '40x40';
    if (el.inputUkuranPanjang) el.inputUkuranPanjang.value = '';
    if (el.inputUkuranLebar) el.inputUkuranLebar.value = '';
    if (el.inputCadangan) el.inputCadangan.value = '5';
    if (el.inputIsiDus) el.inputIsiDus.value = '';
    if (el.inputHargaDus) el.inputHargaDus.value = '';

    updateModeVisibility();
    updateUkuranVisibility();
    resetResults();
    setStatus('Pilih mode dan ukuran, masukkan dimensi, lalu tekan "Hitung kebutuhan".', '');
    updateControls();
    if (el.inputPanjang) el.inputPanjang.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="keramik"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'keramik-panel');
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

    if (el.inputPanjang) {
      setTimeout(function () { el.inputPanjang.focus(); }, 100);
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

  function onModeChange() {
    resetResults();
    updateModeVisibility();
  }
  if (el.modeRuangan) el.modeRuangan.addEventListener('change', onModeChange);
  if (el.modeLuas) el.modeLuas.addEventListener('change', onModeChange);

  if (el.ukuran) {
    el.ukuran.addEventListener('change', function () {
      updateUkuranVisibility();
      resetResults();
      updateControls();
    });
  }

  function onOptionChange() {
    if (state.lastResult) {
      resetResults();
    }
    updateControls();
  }
  if (el.inputCadangan) el.inputCadangan.addEventListener('change', onOptionChange);
  if (el.inputIsiDus) el.inputIsiDus.addEventListener('change', onOptionChange);
  if (el.inputHargaDus) el.inputHargaDus.addEventListener('change', onOptionChange);

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var mode = getActiveMode();
      var valid = false;
      if (mode === 'ruangan') {
        var p = el.inputPanjang ? el.inputPanjang.value.trim() : '';
        var l = el.inputLebar ? el.inputLebar.value.trim() : '';
        valid = (p.length > 0 && l.length > 0);
      } else {
        var luas = el.inputLuas ? el.inputLuas.value.trim() : '';
        valid = (luas.length > 0);
      }
      if (valid) {
        submitCalc();
      }
    }
  }

  var inputs = [
    el.inputPanjang,
    el.inputLebar,
    el.inputLuas,
    el.inputUkuranPanjang,
    el.inputUkuranLebar,
    el.inputCadangan,
    el.inputIsiDus,
    el.inputHargaDus
  ];

  for (var i = 0; i < inputs.length; i++) {
    if (inputs[i]) {
      inputs[i].addEventListener('input', updateControls);
      inputs[i].addEventListener('keydown', onInputKeydown);
    }
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

  // Daftarkan panel supaya kartu Hitung keramik lantai bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['keramik'] = toggle;

  // Inisialisasi bawaan
  updateModeVisibility();
  updateUkuranVisibility();
  updateControls();
})();
