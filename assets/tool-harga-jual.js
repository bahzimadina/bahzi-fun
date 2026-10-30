/* =========================================================================
   Panel alat: Hitung harga jual
   Angka dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('harga-jual-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('harga-jual-close'),
    modeMargin: document.getElementById('harga-jual-mode-margin'),
    modeMarkup: document.getElementById('harga-jual-mode-markup'),
    inputModal: document.getElementById('harga-jual-modal'),
    inputBiaya: document.getElementById('harga-jual-biaya'),
    inputPlatform: document.getElementById('harga-jual-platform'),
    inputTarget: document.getElementById('harga-jual-target'),
    pembulatan: document.getElementById('harga-jual-pembulatan'),
    status: document.getElementById('harga-jual-status'),
    clear: document.getElementById('harga-jual-clear'),
    submit: document.getElementById('harga-jual-submit'),
    results: document.getElementById('harga-jual-results'),
    resultHint: document.getElementById('harga-jual-result-hint'),
    outputWrap: document.getElementById('harga-jual-output-wrap'),
    heroValue: document.getElementById('harga-jual-hero-value'),
    summaryText: document.getElementById('harga-jual-summary-text'),
    statLabaUnit: document.getElementById('harga-jual-stat-laba-unit'),
    statLabaPersen: document.getElementById('harga-jual-stat-laba-persen'),
    statMarkup: document.getElementById('harga-jual-stat-markup'),
    statPotonganRp: document.getElementById('harga-jual-stat-potongan-rp'),
    statTitikBalik: document.getElementById('harga-jual-stat-titik-balik'),
    scenarioRows: document.getElementById('harga-jual-scenario-rows'),
    notesList: document.getElementById('harga-jual-notes-list'),
    copy: document.getElementById('harga-jual-copy'),
    download: document.getElementById('harga-jual-download')
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
    if (el.modeMarkup && el.modeMarkup.checked) {
      return 'markup';
    }
    return 'margin';
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

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.summaryText) el.summaryText.textContent = '';
    if (el.scenarioRows) el.scenarioRows.innerHTML = '';
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
    var modalVal = el.inputModal ? el.inputModal.value.trim() : '';
    var targetVal = el.inputTarget ? el.inputTarget.value.trim() : '';
    var hasRequired = (modalVal.length > 0 && targetVal.length > 0);

    var hasAny = false;
    if (modalVal.length > 0) hasAny = true;
    if (targetVal.length > 0 && targetVal !== '20') hasAny = true;
    if (el.inputBiaya && el.inputBiaya.value.trim()) hasAny = true;
    if (el.inputPlatform && el.inputPlatform.value.trim() && el.inputPlatform.value.trim() !== '0') hasAny = true;
    if (el.pembulatan && el.pembulatan.value !== '500') hasAny = true;
    if (el.modeMarkup && el.modeMarkup.checked) hasAny = true;
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !hasRequired;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung harga jual';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAny && !hasOutput);
    }
  }

  function resetAll() {
    if (state.busy) return;
    if (el.modeMargin) el.modeMargin.checked = true;
    if (el.modeMarkup) el.modeMarkup.checked = false;
    if (el.inputModal) el.inputModal.value = '';
    if (el.inputBiaya) el.inputBiaya.value = '';
    if (el.inputPlatform) el.inputPlatform.value = '0';
    if (el.inputTarget) el.inputTarget.value = '20';
    if (el.pembulatan) el.pembulatan.value = '500';

    resetResults();
    setStatus('Masukkan modal dan target laba, lalu tekan "Hitung harga jual".', '');
    updateControls();
    if (el.inputModal) el.inputModal.focus();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/harga-jual/limits', {
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
        /* Bila gagal, batas bawaan di frontend tetap berfungsi */
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.heroValue) {
      el.heroValue.textContent = 'Rp ' + formatRibuan(data.harga_jual);
    }

    var modeLabel = (data.mode === 'markup') ? 'dari modal' : 'dari harga jual';
    var ringkasan = 'Jual di Rp ' + formatRibuan(data.harga_jual) + ' supaya laba bersih Rp ' +
      formatRibuan(data.laba_per_unit) + ' per unit (' + formatDesimal(data.laba_persen) + '% ' + modeLabel + ').';
    if (el.summaryText) {
      el.summaryText.textContent = ringkasan;
    }

    if (el.statLabaUnit) el.statLabaUnit.textContent = 'Rp ' + formatRibuan(data.laba_per_unit);
    if (el.statLabaPersen) el.statLabaPersen.textContent = formatDesimal(data.laba_persen) + '%';
    if (el.statMarkup) el.statMarkup.textContent = formatDesimal(data.markup_persen) + '%';
    if (el.statPotonganRp) {
      var potRp = (data.rincian && data.rincian.potongan_platform !== undefined) ? data.rincian.potongan_platform : 0;
      el.statPotonganRp.textContent = 'Rp ' + formatRibuan(potRp);
    }
    if (el.statTitikBalik) el.statTitikBalik.textContent = 'Rp ' + formatRibuan(data.harga_titik_balik);

    // Tabel skenario target lain
    if (el.scenarioRows) {
      el.scenarioRows.innerHTML = '';
      if (Array.isArray(data.skenario)) {
        for (var i = 0; i < data.skenario.length; i++) {
          var item = data.skenario[i];
          var tr = document.createElement('tr');

          var tdTarget = document.createElement('td');
          tdTarget.textContent = item.target + '%';
          tr.appendChild(tdTarget);

          var tdHarga = document.createElement('td');
          tdHarga.className = 'hj__table-num';
          tdHarga.textContent = 'Rp ' + formatRibuan(item.harga_jual);
          tr.appendChild(tdHarga);

          var tdLabaUnit = document.createElement('td');
          tdLabaUnit.className = 'hj__table-num';
          tdLabaUnit.textContent = 'Rp ' + formatRibuan(item.laba_per_unit);
          tr.appendChild(tdLabaUnit);

          var tdLabaPersen = document.createElement('td');
          tdLabaPersen.className = 'hj__table-num';
          tdLabaPersen.textContent = formatDesimal(item.laba_persen) + '%';
          tr.appendChild(tdLabaPersen);

          el.scenarioRows.appendChild(tr);
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
          message = 'Layanan hitung harga jual belum terhubung. Coba lagi sebentar lagi.';
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
    var modalVal = el.inputModal ? el.inputModal.value.trim() : '';
    if (!modalVal) {
      setStatus('Masukkan modal per unit terlebih dahulu.', 'error');
      if (el.inputModal) el.inputModal.focus();
      return;
    }

    var targetVal = el.inputTarget ? el.inputTarget.value.trim() : '';
    if (!targetVal) {
      setStatus('Masukkan target laba terlebih dahulu.', 'error');
      if (el.inputTarget) el.inputTarget.focus();
      return;
    }

    var formData = new FormData();
    formData.append('mode', mode);
    formData.append('modal', modalVal);
    formData.append('target', targetVal);

    var biayaVal = el.inputBiaya ? el.inputBiaya.value.trim() : '';
    if (biayaVal) {
      formData.append('biaya_tambahan', biayaVal);
    }

    var platformVal = el.inputPlatform ? el.inputPlatform.value.trim() : '';
    if (platformVal) {
      formData.append('potongan_platform', platformVal);
    }

    if (el.pembulatan) {
      formData.append('pembulatan', el.pembulatan.value);
    }

    state.busy = true;
    updateControls();
    setStatus('Menghitung harga jual...', 'busy');

    fetch(serverBase + '/api/harga-jual', {
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
        setStatus('Harga jual berhasil dihitung.', 'success');
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
    lines.push('Hitung Harga Jual - bahzi.fun');
    lines.push('----------------------------------------');
    lines.push('Mode: ' + (data.mode === 'markup' ? 'Target laba dari modal (markup)' : 'Target laba dari harga jual (margin)'));
    if (data.rincian) {
      lines.push('Modal per unit: Rp ' + formatRibuan(data.rincian.modal));
      lines.push('Biaya tambahan: Rp ' + formatRibuan(data.rincian.biaya_tambahan));
      lines.push('Potongan marketplace: Rp ' + formatRibuan(data.rincian.potongan_platform));
      lines.push('Total biaya per unit: Rp ' + formatRibuan(data.rincian.total_biaya));
    }
    lines.push('Titik balik modal: Rp ' + formatRibuan(data.harga_titik_balik));
    lines.push('----------------------------------------');
    lines.push('Harga jual sebelum pembulatan: Rp ' + formatDesimal(data.harga_sebelum_pembulatan));
    lines.push('Rekomendasi harga jual: Rp ' + formatRibuan(data.harga_jual));
    lines.push('Laba bersih per unit: Rp ' + formatRibuan(data.laba_per_unit));
    lines.push('Persentase laba: ' + formatDesimal(data.laba_persen) + '%');
    lines.push('Persentase markup: ' + formatDesimal(data.markup_persen) + '%');
    lines.push('Pembulatan: ' + (data.pembulatan === 0 ? 'Tanpa pembulatan' : 'Kelipatan ' + data.pembulatan));

    if (Array.isArray(data.skenario) && data.skenario.length > 0) {
      lines.push('----------------------------------------');
      lines.push('Skenario target lain:');
      for (var i = 0; i < data.skenario.length; i++) {
        var s = data.skenario[i];
        lines.push('- Target ' + s.target + '%: Jual Rp ' + formatRibuan(s.harga_jual) + ' (Laba Rp ' + formatRibuan(s.laba_per_unit) + ' / ' + formatDesimal(s.laba_persen) + '%)');
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
    a.download = 'hitung-harga-jual.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatus('Berkas ringkasan .txt berhasil diunduh.', 'success');
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="harga-jual"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'harga-jual-panel');
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

    if (el.inputModal) {
      setTimeout(function () { el.inputModal.focus(); }, 100);
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
    if (state.lastResult) {
      resetResults();
    }
    updateControls();
  }
  if (el.modeMargin) el.modeMargin.addEventListener('change', onModeChange);
  if (el.modeMarkup) el.modeMarkup.addEventListener('change', onModeChange);

  if (el.pembulatan) {
    el.pembulatan.addEventListener('change', function () {
      if (state.lastResult) resetResults();
      updateControls();
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var m = el.inputModal ? el.inputModal.value.trim() : '';
      var t = el.inputTarget ? el.inputTarget.value.trim() : '';
      if (m.length > 0 && t.length > 0) {
        submitCalc();
      }
    }
  }

  var inputs = [
    el.inputModal,
    el.inputBiaya,
    el.inputPlatform,
    el.inputTarget
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

  // Daftarkan panel supaya kartu Hitung harga jual bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['harga-jual'] = toggle;

  // Inisialisasi status awal
  updateControls();
})();
