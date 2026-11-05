/* =========================================================================
   Panel alat: Hitung konsumsi acara
   Data dikirim ke server via multipart/form-data, dihitung murni di memori,
   lalu langsung dibuang. Tanpa penyimpanan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('konsumsi-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('konsumsi-close'),
    // Mode radio
    modeNasiKotak: document.getElementById('konsumsi-mode-nasi-kotak'),
    modePrasmanan: document.getElementById('konsumsi-mode-prasmanan'),
    modeSnack: document.getElementById('konsumsi-mode-snack'),
    // Group fields
    groupNasiKotak: document.getElementById('konsumsi-group-nasi-kotak'),
    groupPrasmanan: document.getElementById('konsumsi-group-prasmanan'),
    groupSnack: document.getElementById('konsumsi-group-snack'),
    // Common inputs
    inputTamu: document.getElementById('konsumsi-tamu'),
    inputCadangan: document.getElementById('konsumsi-cadangan'),
    // Nasi kotak inputs
    inputNkHargaPorsi: document.getElementById('konsumsi-nk-harga-porsi'),
    inputNkHargaAir: document.getElementById('konsumsi-nk-harga-air'),
    // Snack inputs
    inputSnackHargaPorsi: document.getElementById('konsumsi-snack-harga-porsi'),
    // Prasmanan inputs
    selectPrasJenisLauk: document.getElementById('konsumsi-pras-jenis-lauk'),
    inputPrasHargaBeras: document.getElementById('konsumsi-pras-harga-beras'),
    inputPrasHargaLauk: document.getElementById('konsumsi-pras-harga-lauk'),
    labelPrasHargaLauk: document.getElementById('konsumsi-label-harga-lauk'),
    inputPrasHargaSayur: document.getElementById('konsumsi-pras-harga-sayur'),
    inputPrasHargaTahuTempe: document.getElementById('konsumsi-pras-harga-tahu-tempe'),
    inputPrasHargaMinyak: document.getElementById('konsumsi-pras-harga-minyak'),
    inputPrasHargaAir: document.getElementById('konsumsi-pras-harga-air'),
    inputPrasHargaPerlengkapan: document.getElementById('konsumsi-pras-harga-perlengkapan'),
    // Status & buttons
    status: document.getElementById('konsumsi-status'),
    clear: document.getElementById('konsumsi-clear'),
    submit: document.getElementById('konsumsi-submit'),
    // Output area
    results: document.getElementById('konsumsi-results'),
    resultHint: document.getElementById('konsumsi-result-hint'),
    outputWrap: document.getElementById('konsumsi-output-wrap'),
    heroValue: document.getElementById('konsumsi-hero-value'),
    heroSymbol: document.getElementById('konsumsi-hero-symbol'),
    summaryText: document.getElementById('konsumsi-summary-text'),
    ringkasGrid: document.getElementById('konsumsi-ringkas-grid'),
    rincianTableBody: document.getElementById('konsumsi-rincian-tbody'),
    // Biaya
    biayaSection: document.getElementById('konsumsi-biaya-section'),
    biayaTotal: document.getElementById('konsumsi-biaya-total'),
    biayaPerTamu: document.getElementById('konsumsi-biaya-per-tamu'),
    biayaStatus: document.getElementById('konsumsi-biaya-status'),
    biayaList: document.getElementById('konsumsi-biaya-list'),
    // Patokan & catatan
    patokanList: document.getElementById('konsumsi-patokan-list'),
    catatanText: document.getElementById('konsumsi-catatan-text'),
    // Actions
    copy: document.getElementById('konsumsi-copy'),
    download: document.getElementById('konsumsi-download')
  };

  var state = {
    limitsLoaded: false,
    limitsData: null,
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
    if (el.modePrasmanan && el.modePrasmanan.checked) return 'prasmanan';
    if (el.modeSnack && el.modeSnack.checked) return 'snack';
    return 'nasi_kotak';
  }

  function formatRibuan(n) {
    if (n === null || n === undefined || isNaN(n)) return '-';
    var num = Math.round(Number(n));
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function formatDesimal(n) {
    if (n === null || n === undefined || isNaN(n)) return '-';
    var s = Number(n).toString();
    return s.replace('.', ',');
  }

  function formatRupiah(n) {
    if (n === null || n === undefined || isNaN(n)) return '-';
    return 'Rp ' + formatRibuan(n);
  }

  function updateModeVisibility() {
    var mode = getActiveMode();
    if (el.groupNasiKotak) el.groupNasiKotak.hidden = (mode !== 'nasi_kotak');
    if (el.groupPrasmanan) el.groupPrasmanan.hidden = (mode !== 'prasmanan');
    if (el.groupSnack) el.groupSnack.hidden = (mode !== 'snack');
    updateLaukLabel();
    resetResults();
    updateControls();
  }

  function updateLaukLabel() {
    if (!el.labelPrasHargaLauk || !el.selectPrasJenisLauk) return;
    var jenis = el.selectPrasJenisLauk.value || 'ayam';
    if (jenis === 'telur') {
      el.labelPrasHargaLauk.textContent = 'Harga telur ayam per butir (Rp)';
    } else if (jenis === 'ikan') {
      el.labelPrasHargaLauk.textContent = 'Harga ikan per kg (Rp)';
    } else if (jenis === 'daging') {
      el.labelPrasHargaLauk.textContent = 'Harga daging sapi per kg (Rp)';
    } else {
      el.labelPrasHargaLauk.textContent = 'Harga daging ayam per kg (Rp)';
    }
  }

  function resetResults() {
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.resultHint) el.resultHint.hidden = false;
    state.lastResult = null;
    revokeDownload();
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      try {
        URL.revokeObjectURL(state.downloadUrl);
      } catch (e) { /* abaikan */ }
      state.downloadUrl = null;
    }
  }

  function hasAnyInput() {
    return !!(el.inputTamu && el.inputTamu.value.trim());
  }

  function isFormComplete() {
    if (!el.inputTamu) return false;
    var val = el.inputTamu.value.trim();
    if (!val) return false;
    var n = parseInt(val, 10);
    return !isNaN(n) && n >= 1 && n <= 5000;
  }

  function updateControls() {
    var anyIn = hasAnyInput();

    if (el.clear) el.clear.disabled = (!anyIn && !state.lastResult) || state.busy;
    if (el.submit) el.submit.disabled = !anyIn || state.busy;
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    var url = serverBase + '/api/konsumsi/limits';
    fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('Status ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsData = data;
        state.limitsLoaded = true;
      })
      .catch(function () {
        /* Tetap berjalan dengan konfigurasi baku */
      });
  }

  function submitCalc() {
    if (state.busy) return;
    if (!isFormComplete()) {
      setStatus('Masukkan jumlah tamu yang valid antara 1 hingga 5.000 orang.', 'error');
      return;
    }

    var mode = getActiveMode();
    var fd = new FormData();
    fd.append('mode', mode);
    fd.append('tamu', el.inputTamu.value.trim());

    if (el.inputCadangan && el.inputCadangan.value.trim()) {
      fd.append('cadangan', el.inputCadangan.value.trim());
    }

    if (mode === 'nasi_kotak') {
      if (el.inputNkHargaPorsi && el.inputNkHargaPorsi.value.trim()) {
        fd.append('harga_porsi', el.inputNkHargaPorsi.value.trim());
      }
      if (el.inputNkHargaAir && el.inputNkHargaAir.value.trim()) {
        fd.append('harga_air', el.inputNkHargaAir.value.trim());
      }
    } else if (mode === 'snack') {
      if (el.inputSnackHargaPorsi && el.inputSnackHargaPorsi.value.trim()) {
        fd.append('harga_porsi', el.inputSnackHargaPorsi.value.trim());
      }
    } else if (mode === 'prasmanan') {
      if (el.selectPrasJenisLauk && el.selectPrasJenisLauk.value) {
        fd.append('jenis_lauk', el.selectPrasJenisLauk.value);
      }
      if (el.inputPrasHargaBeras && el.inputPrasHargaBeras.value.trim()) {
        fd.append('harga_beras', el.inputPrasHargaBeras.value.trim());
      }
      if (el.inputPrasHargaLauk && el.inputPrasHargaLauk.value.trim()) {
        fd.append('harga_lauk', el.inputPrasHargaLauk.value.trim());
      }
      if (el.inputPrasHargaSayur && el.inputPrasHargaSayur.value.trim()) {
        fd.append('harga_sayur', el.inputPrasHargaSayur.value.trim());
      }
      if (el.inputPrasHargaTahuTempe && el.inputPrasHargaTahuTempe.value.trim()) {
        fd.append('harga_tahu_tempe', el.inputPrasHargaTahuTempe.value.trim());
      }
      if (el.inputPrasHargaMinyak && el.inputPrasHargaMinyak.value.trim()) {
        fd.append('harga_minyak', el.inputPrasHargaMinyak.value.trim());
      }
      if (el.inputPrasHargaAir && el.inputPrasHargaAir.value.trim()) {
        fd.append('harga_air', el.inputPrasHargaAir.value.trim());
      }
      if (el.inputPrasHargaPerlengkapan && el.inputPrasHargaPerlengkapan.value.trim()) {
        fd.append('harga_perlengkapan', el.inputPrasHargaPerlengkapan.value.trim());
      }
    }

    state.busy = true;
    setStatus('Menghitung...', 'busy');
    updateControls();

    var url = serverBase + '/api/konsumsi';
    fetch(url, {
      method: 'POST',
      body: fd,
      headers: { 'Accept': 'application/json' }
    })
      .then(function (res) {
        return res.json().then(function (json) {
          return { ok: res.ok, status: res.status, data: json };
        }).catch(function () {
          return { ok: res.ok, status: res.status, data: null };
        });
      })
      .then(function (result) {
        state.busy = false;
        updateControls();

        if (!result.ok) {
          var msg = 'Gagal menghitung konsumsi acara.';
          if (result.data) {
            if (result.data.error && result.data.error.message) {
              msg = result.data.error.message;
            } else if (result.data.detail && result.data.detail.message) {
              msg = result.data.detail.message;
            } else if (typeof result.data.detail === 'string') {
              msg = result.data.detail;
            }
          }
          setStatus(msg, 'error');
          resetResults();
          return;
        }

        renderResult(result.data);
        setStatus('Selesai dihitung.', 'success');
      })
      .catch(function () {
        state.busy = false;
        updateControls();
        setStatus('Tidak bisa menghubungi server. Periksa koneksi internetmu.', 'error');
        resetResults();
      });
  }

  function renderResult(data) {
    state.lastResult = data;

    if (el.heroValue) el.heroValue.textContent = formatRibuan(data.porsi);
    if (el.heroSymbol) el.heroSymbol.textContent = (data.mode === 'prasmanan' ? 'porsi prasmanan' : 'kotak siap saji');

    if (el.summaryText) {
      el.summaryText.textContent = 'Total konsumsi untuk ' + formatRibuan(data.tamu) + ' tamu undangan (termasuk cadangan ' + data.cadangan_persen + '%).';
    }

    // Grid ringkasan
    if (el.ringkasGrid) {
      el.ringkasGrid.innerHTML = '';
      if (data.ringkas && data.ringkas.length) {
        for (var r = 0; r < data.ringkas.length; r++) {
          var item = data.ringkas[r];
          var card = document.createElement('div');
          card.className = 'kk__stat';

          var labelSpan = document.createElement('span');
          labelSpan.className = 'kk__stat-label';
          labelSpan.textContent = item.label;

          var valSpan = document.createElement('span');
          valSpan.className = 'kk__stat-value';
          valSpan.textContent = item.nilai + ' ' + (item.satuan || '');

          card.appendChild(labelSpan);
          card.appendChild(valSpan);
          el.ringkasGrid.appendChild(card);
        }
      }
    }

    // Tabel rincian bahan/barang
    if (el.rincianTableBody) {
      el.rincianTableBody.innerHTML = '';
      if (data.rincian && data.rincian.length) {
        for (var i = 0; i < data.rincian.length; i++) {
          var row = data.rincian[i];
          var tr = document.createElement('tr');

          var tdNama = document.createElement('td');
          tdNama.className = 'kk__td-nama';
          tdNama.textContent = row.nama;

          var tdJumlah = document.createElement('td');
          tdJumlah.className = 'kk__td-jumlah';
          tdJumlah.textContent = formatDesimal(row.jumlah);

          var tdSatuan = document.createElement('td');
          tdSatuan.className = 'kk__td-satuan';
          tdSatuan.textContent = row.satuan;

          tr.appendChild(tdNama);
          tr.appendChild(tdJumlah);
          tr.appendChild(tdSatuan);
          el.rincianTableBody.appendChild(tr);
        }
      }
    }

    // Biaya
    if (el.biayaSection) {
      var adaBiaya = !!(data.biaya && data.biaya.total !== null && data.biaya.total !== undefined);
      el.biayaSection.hidden = !adaBiaya;

      if (adaBiaya) {
        if (el.biayaTotal) el.biayaTotal.textContent = formatRupiah(data.biaya.total);
        if (el.biayaPerTamu) el.biayaPerTamu.textContent = formatRupiah(data.biaya.per_tamu) + ' / tamu';

        if (el.biayaStatus) {
          if (data.biaya.lengkap) {
            el.biayaStatus.textContent = 'Semua perkiraan harga terisi lengkap.';
            el.biayaStatus.className = 'kk__biaya-status kk__biaya-status--lengkap';
          } else {
            el.biayaStatus.textContent = 'Perkiraan sementara: baru sebagian harga yang kamu masukkan.';
            el.biayaStatus.className = 'kk__biaya-status kk__biaya-status--parsial';
          }
        }

        if (el.biayaList) {
          el.biayaList.innerHTML = '';
          if (data.biaya.rincian && data.biaya.rincian.length) {
            for (var b = 0; b < data.biaya.rincian.length; b++) {
              var br = data.biaya.rincian[b];
              var li = document.createElement('li');
              li.className = 'kk__biaya-item';

              var titleSpan = document.createElement('span');
              titleSpan.className = 'kk__biaya-item-title';
              titleSpan.textContent = br.nama + ' (' + br.keterangan + ')';

              var subSpan = document.createElement('span');
              subSpan.className = 'kk__biaya-item-subtotal';
              subSpan.textContent = formatRupiah(br.subtotal);

              li.appendChild(titleSpan);
              li.appendChild(subSpan);
              el.biayaList.appendChild(li);
            }
          }
        }
      }
    }

    // Patokan yang dipakai
    if (el.patokanList) {
      el.patokanList.innerHTML = '';
      if (data.patokan && data.patokan.length) {
        for (var p = 0; p < data.patokan.length; p++) {
          var pLi = document.createElement('li');
          pLi.className = 'kk__notes-item';
          pLi.textContent = data.patokan[p];
          el.patokanList.appendChild(pLi);
        }
      }
    }

    // Catatan
    if (el.catatanText) {
      el.catatanText.textContent = data.catatan || '';
    }

    if (el.outputWrap) el.outputWrap.hidden = false;
    if (el.resultHint) el.resultHint.hidden = true;
    updateControls();
  }

  function buildSummaryText(data) {
    if (!data) return '';
    var lines = [];
    lines.push('HITUNG KONSUMSI ACARA');
    lines.push('======================');
    lines.push('Mode: ' + data.mode.toUpperCase());
    lines.push('Jumlah tamu: ' + formatRibuan(data.tamu) + ' orang');
    lines.push('Cadangan: ' + data.cadangan_persen + '%');
    lines.push('Total porsi yang disiapkan: ' + formatRibuan(data.porsi) + ' porsi');
    lines.push('');

    lines.push('RINCIAN KEBUTUHAN:');
    if (data.rincian && data.rincian.length) {
      for (var i = 0; i < data.rincian.length; i++) {
        var r = data.rincian[i];
        lines.push('- ' + r.nama + ': ' + formatDesimal(r.jumlah) + ' ' + r.satuan);
      }
    }

    if (data.biaya) {
      lines.push('');
      lines.push('PERKIRAAN BIAYA:');
      lines.push('- Total: ' + formatRupiah(data.biaya.total));
      lines.push('- Per tamu: ' + formatRupiah(data.biaya.per_tamu));
      if (data.biaya.rincian && data.biaya.rincian.length) {
        for (var b = 0; b < data.biaya.rincian.length; b++) {
          var bi = data.biaya.rincian[b];
          lines.push('  * ' + bi.nama + ' (' + bi.keterangan + '): ' + formatRupiah(bi.subtotal));
        }
      }
    }

    if (data.patokan && data.patokan.length) {
      lines.push('');
      lines.push('PATOKAN PORSI:');
      for (var p = 0; p < data.patokan.length; p++) {
        lines.push('- ' + data.patokan[p]);
      }
    }

    if (data.catatan) {
      lines.push('');
      lines.push('CATATAN:');
      lines.push(data.catatan);
    }

    lines.push('');
    lines.push('Dihitung di bahzi.fun (OmniTools)');
    return lines.join('\n');
  }

  function copyResult() {
    if (!state.lastResult) return;
    var text = buildSummaryText(state.lastResult);

    function notifySuccess() {
      if (el.copy) {
        var prev = el.copy.textContent;
        el.copy.textContent = 'Tersalin!';
        setTimeout(function () { el.copy.textContent = prev; }, 1800);
      }
      setStatus('Rincian disalin ke papan klip.', 'success');
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(notifySuccess).catch(function () {
        fallbackCopy(text, notifySuccess);
      });
    } else {
      fallbackCopy(text, notifySuccess);
    }
  }

  function fallbackCopy(text, cb) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      if (cb) cb();
    } catch (e) {
      setStatus('Tidak bisa menyalin teks ke papan klip.', 'error');
    }
    document.body.removeChild(ta);
  }

  function downloadResult() {
    if (!state.lastResult) return;
    var text = buildSummaryText(state.lastResult);
    revokeDownload();
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    state.downloadUrl = url;

    var a = document.createElement('a');
    a.href = url;
    a.download = 'hitung-konsumsi-acara-' + Date.now() + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatus('Berkas .txt berhasil diunduh.', 'success');
  }

  function resetAll() {
    if (el.inputTamu) el.inputTamu.value = '';
    if (el.inputCadangan) el.inputCadangan.value = '10';

    if (el.inputNkHargaPorsi) el.inputNkHargaPorsi.value = '';
    if (el.inputNkHargaAir) el.inputNkHargaAir.value = '';
    if (el.inputSnackHargaPorsi) el.inputSnackHargaPorsi.value = '';

    if (el.selectPrasJenisLauk) el.selectPrasJenisLauk.value = 'ayam';
    if (el.inputPrasHargaBeras) el.inputPrasHargaBeras.value = '';
    if (el.inputPrasHargaLauk) el.inputPrasHargaLauk.value = '';
    if (el.inputPrasHargaSayur) el.inputPrasHargaSayur.value = '';
    if (el.inputPrasHargaTahuTempe) el.inputPrasHargaTahuTempe.value = '';
    if (el.inputPrasHargaMinyak) el.inputPrasHargaMinyak.value = '';
    if (el.inputPrasHargaAir) el.inputPrasHargaAir.value = '';
    if (el.inputPrasHargaPerlengkapan) el.inputPrasHargaPerlengkapan.value = '';

    if (el.modeNasiKotak) el.modeNasiKotak.checked = true;
    updateModeVisibility();
    resetResults();
    setStatus('Pilih mode, masukkan jumlah tamu, lalu tekan "Hitung kebutuhan".', '');
    updateControls();

    if (el.inputTamu) el.inputTamu.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="konsumsi"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'konsumsi-panel');
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

    if (el.inputTamu) {
      setTimeout(function () { el.inputTamu.focus(); }, 100);
    }
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    syncTriggers(false);
    revokeDownload();
    if (state.lastFocus && state.lastFocus !== document.body && typeof state.lastFocus.focus === 'function' && document.contains(state.lastFocus)) {
      state.lastFocus.focus();
    } else {
      var trigger = document.querySelector('.tool-card__open[data-tool-action="konsumsi"]');
      if (trigger && typeof trigger.focus === 'function') {
        trigger.focus();
      }
    }
    state.lastFocus = null;
  }

  function toggle() {
    if (panel.hidden) open();
    else close();
  }

  // Event listeners
  if (el.close) el.close.addEventListener('click', close);

  var modeRadios = [el.modeNasiKotak, el.modePrasmanan, el.modeSnack];
  for (var m = 0; m < modeRadios.length; m++) {
    if (modeRadios[m]) {
      modeRadios[m].addEventListener('change', updateModeVisibility);
    }
  }

  if (el.selectPrasJenisLauk) {
    el.selectPrasJenisLauk.addEventListener('change', function () {
      updateLaukLabel();
      resetResults();
      updateControls();
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (isFormComplete()) submitCalc();
    }
  }

  var inputs = [
    el.inputTamu, el.inputCadangan,
    el.inputNkHargaPorsi, el.inputNkHargaAir,
    el.inputSnackHargaPorsi,
    el.inputPrasHargaBeras, el.inputPrasHargaLauk, el.inputPrasHargaSayur,
    el.inputPrasHargaTahuTempe, el.inputPrasHargaMinyak, el.inputPrasHargaAir, el.inputPrasHargaPerlengkapan
  ];

  for (var i = 0; i < inputs.length; i++) {
    if (inputs[i]) {
      inputs[i].addEventListener('input', function () {
        resetResults();
        updateControls();
      });
      inputs[i].addEventListener('keydown', onInputKeydown);
    }
  }

  if (el.inputTamu) {
    el.inputTamu.addEventListener('blur', function () {
      if (hasAnyInput() && !isFormComplete()) {
        setStatus('Masukkan jumlah tamu yang valid antara 1 hingga 5.000 orang.', 'error');
      }
    });
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

  // Daftarkan panel supaya kartu Hitung konsumsi acara bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['konsumsi'] = toggle;

  // Inisialisasi bawaan
  updateModeVisibility();
  updateControls();
})();
