/* =========================================================================
   Panel alat: Hitung biaya perjalanan
   Angka dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('biaya-perjalanan-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('biaya-perjalanan-close'),
    inputJarak: document.getElementById('biaya-perjalanan-jarak'),
    inputPP: document.getElementById('biaya-perjalanan-pp'),
    inputKonsumsi: document.getElementById('biaya-perjalanan-konsumsi'),
    inputHarga: document.getElementById('biaya-perjalanan-harga'),
    inputPenumpang: document.getElementById('biaya-perjalanan-penumpang'),
    inputBiayaLain: document.getElementById('biaya-perjalanan-biaya-lain'),
    status: document.getElementById('biaya-perjalanan-status'),
    clear: document.getElementById('biaya-perjalanan-clear'),
    submit: document.getElementById('biaya-perjalanan-submit'),
    results: document.getElementById('biaya-perjalanan-results'),
    resultHint: document.getElementById('biaya-perjalanan-result-hint'),
    outputWrap: document.getElementById('biaya-perjalanan-output-wrap'),
    heroValue: document.getElementById('biaya-perjalanan-hero-value'),
    summaryText: document.getElementById('biaya-perjalanan-summary-text'),
    statLiter: document.getElementById('biaya-perjalanan-stat-liter'),
    statBBM: document.getElementById('biaya-perjalanan-stat-bbm'),
    statPerOrang: document.getElementById('biaya-perjalanan-stat-per-orang'),
    statPerKm: document.getElementById('biaya-perjalanan-stat-per-km'),
    splitRows: document.getElementById('biaya-perjalanan-split-rows'),
    notesList: document.getElementById('biaya-perjalanan-notes-list'),
    copy: document.getElementById('biaya-perjalanan-copy'),
    download: document.getElementById('biaya-perjalanan-download')
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

  function formatRibuan(n) {
    if (n === null || n === undefined) return '-';
    var num = Math.round(Number(n));
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function formatDesimal(n) {
    if (n === null || n === undefined) return '-';
    var num = Number(n);
    if (isNaN(num)) return '-';
    var str = num.toString();
    return str.replace('.', ',');
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.summaryText) el.summaryText.textContent = '';
    if (el.splitRows) el.splitRows.innerHTML = '';
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
    var jarakVal = el.inputJarak ? el.inputJarak.value.trim() : '';
    var konsumsiVal = el.inputKonsumsi ? el.inputKonsumsi.value.trim() : '';
    var hargaVal = el.inputHarga ? el.inputHarga.value.trim() : '';
    var hasRequired = (jarakVal.length > 0 && konsumsiVal.length > 0 && hargaVal.length > 0);

    var hasAny = false;
    if (jarakVal.length > 0) hasAny = true;
    if (el.inputPP && el.inputPP.checked) hasAny = true;
    if (konsumsiVal.length > 0 && konsumsiVal !== '12') hasAny = true;
    if (hargaVal.length > 0) hasAny = true;
    if (el.inputPenumpang && el.inputPenumpang.value.trim() && el.inputPenumpang.value.trim() !== '1') hasAny = true;
    if (el.inputBiayaLain && el.inputBiayaLain.value.trim()) hasAny = true;
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !hasRequired;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung biaya';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAny && !hasOutput);
    }
  }

  function resetAll() {
    if (state.busy) return;
    if (el.inputJarak) el.inputJarak.value = '';
    if (el.inputPP) el.inputPP.checked = false;
    if (el.inputKonsumsi) el.inputKonsumsi.value = '12';
    if (el.inputHarga) el.inputHarga.value = '';
    if (el.inputPenumpang) el.inputPenumpang.value = '1';
    if (el.inputBiayaLain) el.inputBiayaLain.value = '';

    resetResults();
    setStatus('Masukkan jarak, konsumsi BBM, dan harga BBM, lalu tekan "Hitung biaya".', '');
    updateControls();
    if (el.inputJarak) el.inputJarak.focus();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/travel-cost/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function () {
        state.limitsLoaded = true;
      })
      .catch(function () {
        /* Bila gagal, konfigurasi bawaan frontend tetap berfungsi */
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.heroValue) {
      el.heroValue.textContent = 'Rp ' + formatRibuan(data.total_biaya);
    }

    var prefix = data.pulang_pergi ? 'Pulang pergi ' : 'Perjalanan ';
    var ringkasan = prefix + formatDesimal(data.jarak_total) + ' km butuh ' +
      formatDesimal(data.liter) + ' liter, sekitar Rp ' +
      formatRibuan(data.total_biaya) + ' untuk ' + data.penumpang + ' orang.';
    if (el.summaryText) {
      el.summaryText.textContent = ringkasan;
    }

    if (el.statLiter) el.statLiter.textContent = formatDesimal(data.liter) + ' liter';
    if (el.statBBM) el.statBBM.textContent = 'Rp ' + formatRibuan(data.biaya_bbm);
    if (el.statPerOrang) el.statPerOrang.textContent = 'Rp ' + formatRibuan(data.biaya_per_orang);
    if (el.statPerKm) el.statPerKm.textContent = 'Rp ' + formatRibuan(data.biaya_per_km);

    // Tabel patungan 1..6 orang
    if (el.splitRows) {
      el.splitRows.innerHTML = '';
      if (Array.isArray(data.tabel_patungan)) {
        for (var i = 0; i < data.tabel_patungan.length; i++) {
          var item = data.tabel_patungan[i];
          var tr = document.createElement('tr');

          var tdOrang = document.createElement('td');
          tdOrang.textContent = item.penumpang + ' orang';
          tr.appendChild(tdOrang);

          var tdBiaya = document.createElement('td');
          tdBiaya.className = 'bp__table-num';
          tdBiaya.textContent = 'Rp ' + formatRibuan(item.biaya_per_orang);
          tr.appendChild(tdBiaya);

          el.splitRows.appendChild(tr);
        }
      }
    }

    // Catatan kaki jujur dari server
    if (el.notesList) {
      el.notesList.innerHTML = '';
      if (Array.isArray(data.catatan)) {
        for (var j = 0; j < data.catatan.length; j++) {
          var li = document.createElement('li');
          li.textContent = data.catatan[j];
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
          message = 'Layanan hitung biaya perjalanan belum terhubung. Coba lagi sebentar lagi.';
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

    var jarakVal = el.inputJarak ? el.inputJarak.value.trim() : '';
    if (!jarakVal) {
      setStatus('Masukkan jarak perjalanan terlebih dahulu.', 'error');
      if (el.inputJarak) el.inputJarak.focus();
      return;
    }

    var konsumsiVal = el.inputKonsumsi ? el.inputKonsumsi.value.trim() : '';
    if (!konsumsiVal) {
      setStatus('Masukkan konsumsi bahan bakar terlebih dahulu.', 'error');
      if (el.inputKonsumsi) el.inputKonsumsi.focus();
      return;
    }

    var hargaVal = el.inputHarga ? el.inputHarga.value.trim() : '';
    if (!hargaVal) {
      setStatus('Masukkan harga bahan bakar per liter terlebih dahulu.', 'error');
      if (el.inputHarga) el.inputHarga.focus();
      return;
    }

    var formData = new FormData();
    formData.append('jarak', jarakVal);
    formData.append('pulang_pergi', el.inputPP && el.inputPP.checked ? 'true' : 'false');
    formData.append('konsumsi', konsumsiVal);
    formData.append('harga_bbm', hargaVal);

    var penumpangVal = el.inputPenumpang ? el.inputPenumpang.value.trim() : '';
    if (penumpangVal) {
      formData.append('penumpang', penumpangVal);
    }

    var biayaLainVal = el.inputBiayaLain ? el.inputBiayaLain.value.trim() : '';
    if (biayaLainVal) {
      formData.append('biaya_lain', biayaLainVal);
    }

    state.busy = true;
    updateControls();
    setStatus('Menghitung biaya perjalanan...', 'busy');

    fetch(serverBase + '/api/travel-cost', {
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
        setStatus('Biaya perjalanan berhasil diperkirakan.', 'success');
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
    lines.push('Hitung Biaya Perjalanan - bahzi.fun');
    lines.push('----------------------------------------');
    if (data.rincian) {
      lines.push('Jarak satu arah: ' + formatDesimal(data.rincian.jarak_satu_arah) + ' km');
      lines.push('Pulang pergi: ' + (data.pulang_pergi ? 'Ya (total ' + formatDesimal(data.jarak_total) + ' km)' : 'Tidak'));
      lines.push('Konsumsi BBM: ' + formatDesimal(data.rincian.konsumsi) + ' km/liter');
      lines.push('Harga BBM: Rp ' + formatRibuan(data.rincian.harga_bbm) + ' / liter');
      lines.push('Biaya BBM: Rp ' + formatRibuan(data.biaya_bbm) + ' (' + formatDesimal(data.liter) + ' liter)');
      lines.push('Biaya lain (tol, parkir, makan): Rp ' + formatRibuan(data.biaya_lain));
    }
    lines.push('----------------------------------------');
    lines.push('Total perkiraan biaya: Rp ' + formatRibuan(data.total_biaya));
    lines.push('Biaya per km: Rp ' + formatRibuan(data.biaya_per_km));
    lines.push('Biaya untuk ' + data.penumpang + ' orang: Rp ' + formatRibuan(data.biaya_per_orang) + ' / orang');

    if (Array.isArray(data.tabel_patungan) && data.tabel_patungan.length > 0) {
      lines.push('----------------------------------------');
      lines.push('Tabel patungan per orang:');
      for (var i = 0; i < data.tabel_patungan.length; i++) {
        var s = data.tabel_patungan[i];
        lines.push('- ' + s.penumpang + ' orang: Rp ' + formatRibuan(s.biaya_per_orang));
      }
    }

    if (Array.isArray(data.catatan) && data.catatan.length > 0) {
      lines.push('----------------------------------------');
      lines.push('Catatan:');
      for (var j = 0; j < data.catatan.length; j++) {
        lines.push('- ' + data.catatan[j]);
      }
    }
    lines.push('----------------------------------------');
    lines.push('Dihitung di https://bahzi.fun/ (OmniTools)');
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
    a.download = 'biaya-perjalanan.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatus('Berkas ringkasan .txt berhasil diunduh.', 'success');
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="biaya-perjalanan"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'biaya-perjalanan-panel');
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

    if (el.inputJarak) {
      setTimeout(function () { el.inputJarak.focus(); }, 100);
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

  function onFieldChange() {
    if (state.lastResult) {
      resetResults();
    }
    updateControls();
  }

  if (el.inputPP) el.inputPP.addEventListener('change', onFieldChange);

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var j = el.inputJarak ? el.inputJarak.value.trim() : '';
      var k = el.inputKonsumsi ? el.inputKonsumsi.value.trim() : '';
      var h = el.inputHarga ? el.inputHarga.value.trim() : '';
      if (j.length > 0 && k.length > 0 && h.length > 0) {
        submitCalc();
      }
    }
  }

  var inputs = [
    el.inputJarak,
    el.inputKonsumsi,
    el.inputHarga,
    el.inputPenumpang,
    el.inputBiayaLain
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

  // Daftarkan panel supaya kartu Hitung biaya perjalanan bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['biaya-perjalanan'] = toggle;

  // Inisialisasi status awal
  updateControls();
})();
