/* =========================================================================
   Panel alat: Hitung kebutuhan cat dinding
   Angka dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('cat-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('cat-close'),
    modeRuangan: document.getElementById('cat-mode-ruangan'),
    modeLuas: document.getElementById('cat-mode-luas'),
    groupRuangan: document.getElementById('cat-group-ruangan'),
    groupBukaan: document.getElementById('cat-group-bukaan'),
    groupLuas: document.getElementById('cat-group-luas'),
    inputPanjang: document.getElementById('cat-input-panjang'),
    inputLebar: document.getElementById('cat-input-lebar'),
    inputTinggi: document.getElementById('cat-input-tinggi'),
    inputPintu: document.getElementById('cat-input-pintu'),
    inputJendela: document.getElementById('cat-input-jendela'),
    inputLuas: document.getElementById('cat-input-luas'),
    lapis: document.getElementById('cat-lapis'),
    dayaSebar: document.getElementById('cat-daya-sebar'),
    kemasan: document.getElementById('cat-kemasan'),
    groupKustom: document.getElementById('cat-group-kustom'),
    kemasanKustom: document.getElementById('cat-kemasan-kustom'),
    harga: document.getElementById('cat-harga'),
    status: document.getElementById('cat-status'),
    clear: document.getElementById('cat-clear'),
    submit: document.getElementById('cat-submit'),
    results: document.getElementById('cat-results'),
    resultHint: document.getElementById('cat-result-hint'),
    outputWrap: document.getElementById('cat-output-wrap'),
    heroValue: document.getElementById('cat-hero-value'),
    heroSymbol: document.getElementById('cat-hero-symbol'),
    summaryText: document.getElementById('cat-summary-text'),
    statLuas: document.getElementById('cat-stat-luas'),
    statPerLapis: document.getElementById('cat-stat-per-lapis'),
    statKaleng: document.getElementById('cat-stat-kaleng'),
    statDibeli: document.getElementById('cat-stat-dibeli'),
    statSisa: document.getElementById('cat-stat-sisa'),
    statBiayaTotal: document.getElementById('cat-stat-biaya-total'),
    statBiayaM2: document.getElementById('cat-stat-biaya-m2'),
    itemBiayaTotal: document.getElementById('cat-item-biaya-total'),
    itemBiayaM2: document.getElementById('cat-item-biaya-m2'),
    notesList: document.getElementById('cat-notes-list'),
    copy: document.getElementById('cat-copy'),
    download: document.getElementById('cat-download')
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

  function formatDesimal(n) {
    if (n === null || n === undefined) return '-';
    return n.toString().replace('.', ',');
  }

  function updateModeVisibility() {
    var mode = getActiveMode();
    if (mode === 'luas') {
      if (el.groupRuangan) el.groupRuangan.hidden = true;
      if (el.groupBukaan) el.groupBukaan.hidden = true;
      if (el.groupLuas) el.groupLuas.hidden = false;
    } else {
      if (el.groupRuangan) el.groupRuangan.hidden = false;
      if (el.groupBukaan) el.groupBukaan.hidden = false;
      if (el.groupLuas) el.groupLuas.hidden = true;
    }
    updateControls();
  }

  function updateKemasanVisibility() {
    var isKustom = el.kemasan && el.kemasan.value === 'kustom';
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
      var t = el.inputTinggi ? el.inputTinggi.value.trim() : '';
      hasRequired = (p.length > 0 && l.length > 0 && t.length > 0);
    } else {
      var luas = el.inputLuas ? el.inputLuas.value.trim() : '';
      hasRequired = (luas.length > 0);
    }

    if (el.kemasan && el.kemasan.value === 'kustom') {
      var kk = el.kemasanKustom ? el.kemasanKustom.value.trim() : '';
      if (!kk) {
        hasRequired = false;
      }
    }

    var hasAny = false;
    if (el.inputPanjang && el.inputPanjang.value.trim()) hasAny = true;
    if (el.inputLebar && el.inputLebar.value.trim()) hasAny = true;
    if (el.inputTinggi && el.inputTinggi.value.trim()) hasAny = true;
    if (el.inputPintu && el.inputPintu.value.trim() && el.inputPintu.value !== '0') hasAny = true;
    if (el.inputJendela && el.inputJendela.value.trim() && el.inputJendela.value !== '0') hasAny = true;
    if (el.inputLuas && el.inputLuas.value.trim()) hasAny = true;
    if (el.dayaSebar && el.dayaSebar.value.trim()) hasAny = true;
    if (el.kemasanKustom && el.kemasanKustom.value.trim()) hasAny = true;
    if (el.harga && el.harga.value.trim()) hasAny = true;
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !hasRequired;
      el.submit.textContent = state.busy ? 'Menghitung…' : 'Hitung kebutuhan';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAny && !hasOutput);
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/cat/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data && Array.isArray(data.kemasan_pilihan) && el.kemasan) {
          var currentVal = el.kemasan.value || '5';
          el.kemasan.innerHTML = '';
          for (var i = 0; i < data.kemasan_pilihan.length; i++) {
            var item = data.kemasan_pilihan[i];
            var opt = document.createElement('option');
            opt.value = item.kode;
            opt.textContent = item.label;
            if (item.kode === currentVal) {
              opt.selected = true;
            }
            el.kemasan.appendChild(opt);
          }
          if (!el.kemasan.value && data.kemasan_pilihan.length > 0) {
            el.kemasan.value = data.kemasan_pilihan[0].kode;
          }
        }
        state.limitsLoaded = true;
        updateKemasanVisibility();
      })
      .catch(function () {
        updateKemasanVisibility();
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.heroValue) el.heroValue.textContent = formatDesimal(data.liter_total);
    if (el.heroSymbol) el.heroSymbol.textContent = 'Liter (' + data.kaleng + ' kaleng @ ' + formatDesimal(data.kemasan_liter) + ' L)';

    var ringkasan = 'Luas dinding ' + formatDesimal(data.luas_dinding_m2) + ' m² membutuhkan ' +
      formatDesimal(data.liter_total) + ' liter cat untuk ' + data.lapis + ' lapis. ' +
      'Disarankan membeli ' + data.kaleng + ' kaleng (total ' + formatDesimal(data.liter_dibeli) + ' liter).';
    if (el.summaryText) el.summaryText.textContent = ringkasan;

    if (el.statLuas) el.statLuas.textContent = formatDesimal(data.luas_dinding_m2) + ' m²';
    if (el.statPerLapis) el.statPerLapis.textContent = formatDesimal(data.liter_per_lapis) + ' L/lapis';
    if (el.statKaleng) el.statKaleng.textContent = data.kaleng + ' kaleng';
    if (el.statDibeli) el.statDibeli.textContent = formatDesimal(data.liter_dibeli) + ' L';
    if (el.statSisa) el.statSisa.textContent = formatDesimal(data.sisa_liter) + ' L';

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
          message = 'Layanan hitung kebutuhan cat belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Permintaan melebihi batas ukuran yang didukung.';
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
      var t = el.inputTinggi ? el.inputTinggi.value.trim() : '';
      if (!p || !l || !t) {
        setStatus('Masukkan panjang, lebar, dan tinggi dinding terlebih dahulu.', 'error');
        if (!p && el.inputPanjang) el.inputPanjang.focus();
        else if (!l && el.inputLebar) el.inputLebar.focus();
        else if (!t && el.inputTinggi) el.inputTinggi.focus();
        return;
      }
      formData.append('panjang', p);
      formData.append('lebar', l);
      formData.append('tinggi', t);

      var pintu = el.inputPintu ? el.inputPintu.value.trim() : '';
      if (pintu) formData.append('pintu', pintu);

      var jendela = el.inputJendela ? el.inputJendela.value.trim() : '';
      if (jendela) formData.append('jendela', jendela);
    } else {
      var luas = el.inputLuas ? el.inputLuas.value.trim() : '';
      if (!luas) {
        setStatus('Masukkan luas dinding terlebih dahulu.', 'error');
        if (el.inputLuas) el.inputLuas.focus();
        return;
      }
      formData.append('luas_dinding', luas);
    }

    if (el.lapis) {
      formData.append('lapis', el.lapis.value);
    }

    var ds = el.dayaSebar ? el.dayaSebar.value.trim() : '';
    if (ds) {
      formData.append('daya_sebar', ds);
    }

    var kemasanVal = el.kemasan ? el.kemasan.value : '5';
    formData.append('kemasan', kemasanVal);

    if (kemasanVal === 'kustom') {
      var kk = el.kemasanKustom ? el.kemasanKustom.value.trim() : '';
      if (!kk) {
        setStatus('Masukkan ukuran kemasan kustom terlebih dahulu.', 'error');
        if (el.kemasanKustom) el.kemasanKustom.focus();
        return;
      }
      formData.append('kemasan_kustom', kk);
    }

    var hargaVal = el.harga ? el.harga.value.trim() : '';
    if (hargaVal) {
      formData.append('harga', hargaVal);
    }

    state.busy = true;
    updateControls();
    setStatus('Menghitung…', 'busy');

    fetch(serverBase + '/api/cat', {
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
        setStatus('Perhitungan selesai. Butuh ' + formatDesimal(data.liter_total) + ' liter (' + data.kaleng + ' kaleng).', 'success');
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
    lines.push('Hitung Kebutuhan Cat - bahzi.fun');
    lines.push('----------------------------------------');
    if (data.mode === 'ruangan') {
      lines.push('Mode: Ukuran ruangan (panjang x lebar x tinggi)');
      lines.push('Luas dinding kotor: ' + formatDesimal(data.luas_kotor_m2) + ' m2');
      lines.push('Luas bukaan pintu/jendela: ' + formatDesimal(data.luas_bukaan_m2) + ' m2');
    } else {
      lines.push('Mode: Luas dinding bersih');
    }
    lines.push('Luas dinding bersih dicat: ' + formatDesimal(data.luas_dinding_m2) + ' m2');
    lines.push('Lapisan: ' + data.lapis + ' lapis');
    lines.push('Daya sebar: ' + formatDesimal(data.daya_sebar) + ' m2/liter/lapis');
    lines.push('Kebutuhan per lapis: ' + formatDesimal(data.liter_per_lapis) + ' liter');
    lines.push('Total kebutuhan cat: ' + formatDesimal(data.liter_total) + ' liter');
    lines.push('Kemasan: ' + formatDesimal(data.kemasan_liter) + ' liter/kaleng');
    lines.push('Jumlah kaleng dibeli: ' + data.kaleng + ' kaleng');
    lines.push('Total liter dibeli: ' + formatDesimal(data.liter_dibeli) + ' liter');
    lines.push('Perkiraan sisa cat: ' + formatDesimal(data.sisa_liter) + ' liter');
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
    lines.push('Hasil adalah perkiraan matematis. Daya sebar sebenarnya tergantung merek cat dan permukaan dinding.');
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
    a.download = 'hitung-kebutuhan-cat.txt';
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
    if (el.inputTinggi) el.inputTinggi.value = '';
    if (el.inputPintu) el.inputPintu.value = '0';
    if (el.inputJendela) el.inputJendela.value = '0';
    if (el.inputLuas) el.inputLuas.value = '';
    if (el.lapis) el.lapis.value = '2';
    if (el.dayaSebar) el.dayaSebar.value = '';
    if (el.kemasan) el.kemasan.value = '5';
    if (el.kemasanKustom) el.kemasanKustom.value = '';
    if (el.harga) el.harga.value = '';

    updateModeVisibility();
    updateKemasanVisibility();
    resetResults();
    setStatus('Pilih mode, masukkan ukuran dinding, lalu tekan "Hitung kebutuhan".', '');
    updateControls();
    if (el.inputPanjang) el.inputPanjang.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="cat"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'cat-panel');
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

  if (el.kemasan) {
    el.kemasan.addEventListener('change', function () {
      updateKemasanVisibility();
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
  if (el.lapis) el.lapis.addEventListener('change', onOptionChange);
  if (el.dayaSebar) el.dayaSebar.addEventListener('change', onOptionChange);
  if (el.harga) el.harga.addEventListener('change', onOptionChange);

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var mode = getActiveMode();
      var valid = false;
      if (mode === 'ruangan') {
        var p = el.inputPanjang ? el.inputPanjang.value.trim() : '';
        var l = el.inputLebar ? el.inputLebar.value.trim() : '';
        var t = el.inputTinggi ? el.inputTinggi.value.trim() : '';
        valid = (p.length > 0 && l.length > 0 && t.length > 0);
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
    el.inputTinggi,
    el.inputPintu,
    el.inputJendela,
    el.inputLuas,
    el.dayaSebar,
    el.kemasanKustom,
    el.harga
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

  // Daftarkan panel supaya kartu Hitung kebutuhan cat bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['cat'] = toggle;

  // Inisialisasi bawaan
  updateModeVisibility();
  updateKemasanVisibility();
  updateControls();
})();
