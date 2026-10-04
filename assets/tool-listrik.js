/* =========================================================================
   Panel alat: Kalkulator listrik
   Angka dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('listrik-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('listrik-title'),
    limits: document.getElementById('listrik-limits'),
    note: document.getElementById('listrik-note'),
    close: document.getElementById('listrik-close'),
    mode: document.getElementById('listrik-mode'),

    // Grup mode
    groupOhm: document.getElementById('listrik-group-ohm'),
    tegangan: document.getElementById('listrik-tegangan'),
    arus: document.getElementById('listrik-arus'),
    hambatan: document.getElementById('listrik-hambatan'),

    groupDaya: document.getElementById('listrik-group-daya'),
    dayaAlat: document.getElementById('listrik-daya-alat'),
    jam: document.getElementById('listrik-jam'),
    jumlah: document.getElementById('listrik-jumlah'),
    hari: document.getElementById('listrik-hari'),
    tarif: document.getElementById('listrik-tarif'),

    groupHambatan: document.getElementById('listrik-group-hambatan'),
    jenis: document.getElementById('listrik-jenis'),
    daftar: document.getElementById('listrik-daftar'),

    // Aksi & status
    status: document.getElementById('listrik-status'),
    btnContoh: document.getElementById('listrik-btn-contoh'),
    clear: document.getElementById('listrik-clear'),
    submit: document.getElementById('listrik-submit'),

    // Hasil
    results: document.getElementById('listrik-results'),
    resultHint: document.getElementById('listrik-result-hint'),
    outputWrap: document.getElementById('listrik-output-wrap'),
    heroLabel: document.getElementById('listrik-hero-label'),
    heroValue: document.getElementById('listrik-hero-value'),
    heroSymbol: document.getElementById('listrik-hero-symbol'),
    heroSub: document.getElementById('listrik-hero-sub'),
    stats: document.getElementById('listrik-stats'),
    stepsWrap: document.getElementById('listrik-steps-wrap'),
    steps: document.getElementById('listrik-steps'),
    noteBox: document.getElementById('listrik-note-box'),
    noteText: document.getElementById('listrik-note-text'),
    copy: document.getElementById('listrik-copy'),
    download: document.getElementById('listrik-download')
  };

  var FALLBACK_MODES = [
    {
      value: 'ohm',
      label: 'Hukum Ohm (V / I / R)',
      contoh: { tegangan: '', arus: '5', hambatan: '44' }
    },
    {
      value: 'daya',
      label: 'Perkiraan pemakaian dan biaya',
      contoh: {
        daya_alat: '350',
        jam_per_hari: '8',
        jumlah_alat: '2',
        hari: '30',
        tarif: '1444.7'
      }
    },
    {
      value: 'hambatan',
      label: 'Hambatan total rangkaian (seri / paralel)',
      contoh: {
        jenis: 'seri',
        daftar: '100\n220\n470'
      }
    }
  ];

  var state = {
    modes: FALLBACK_MODES,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    lastTextSummary: '',
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
    var mode = el.mode ? el.mode.value : 'ohm';

    if (el.groupOhm) el.groupOhm.hidden = (mode !== 'ohm');
    if (el.groupDaya) el.groupDaya.hidden = (mode !== 'daya');
    if (el.groupHambatan) el.groupHambatan.hidden = (mode !== 'hambatan');

    resetResults();
    setStatus('Pilih mode, masukkan angka, lalu tekan "Hitung".', '');
    updateControls();
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroLabel) el.heroLabel.textContent = 'Hasil Perhitungan';
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.heroSymbol) el.heroSymbol.textContent = '';
    if (el.heroSub) {
      el.heroSub.hidden = true;
      el.heroSub.textContent = '';
    }
    if (el.stats) {
      el.stats.hidden = true;
      el.stats.innerHTML = '';
    }
    if (el.stepsWrap) el.stepsWrap.hidden = true;
    if (el.steps) el.steps.innerHTML = '';
    if (el.noteBox) el.noteBox.hidden = true;
    if (el.noteText) el.noteText.textContent = '';

    state.lastResult = null;
    state.lastTextSummary = '';
    revokeDownload();
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }
  }

  function hasInputs() {
    var mode = el.mode ? el.mode.value : 'ohm';
    if (mode === 'ohm') {
      var v = el.tegangan ? el.tegangan.value.trim() : '';
      var i = el.arus ? el.arus.value.trim() : '';
      var r = el.hambatan ? el.hambatan.value.trim() : '';
      var count = (v ? 1 : 0) + (i ? 1 : 0) + (r ? 1 : 0);
      return count >= 1;
    } else if (mode === 'daya') {
      var da = el.dayaAlat ? el.dayaAlat.value.trim() : '';
      var j = el.jam ? el.jam.value.trim() : '';
      var jm = el.jumlah ? el.jumlah.value.trim() : '';
      var h = el.hari ? el.hari.value.trim() : '';
      var t = el.tarif ? el.tarif.value.trim() : '';
      return (da || j || jm || h || t);
    } else if (mode === 'hambatan') {
      var d = el.daftar ? el.daftar.value.trim() : '';
      return d.length > 0;
    }
    return false;
  }

  function updateControls() {
    var hasIn = hasInputs();
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasIn && !hasOutput);
    }
    if (el.btnContoh) {
      el.btnContoh.disabled = state.busy;
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/listrik/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data && Array.isArray(data.modes) && data.modes.length > 0) {
          state.modes = data.modes;
        }
        state.limitsLoaded = true;
      })
      .catch(function () {
        /* Gunakan fallback jika permintaan limits tidak berhasil */
      });
  }

  function isiContoh() {
    var mode = el.mode ? el.mode.value : 'ohm';
    var modeData = getModeData(mode);
    var contoh = (modeData && modeData.contoh) || {};

    if (mode === 'ohm') {
      if (el.tegangan) el.tegangan.value = contoh.tegangan !== undefined ? contoh.tegangan : '';
      if (el.arus) el.arus.value = contoh.arus || '5';
      if (el.hambatan) el.hambatan.value = contoh.hambatan || '44';
      if (el.arus) el.arus.focus();
    } else if (mode === 'daya') {
      if (el.dayaAlat) el.dayaAlat.value = contoh.daya_alat || '350';
      if (el.jam) el.jam.value = contoh.jam_per_hari || '8';
      if (el.jumlah) el.jumlah.value = contoh.jumlah_alat || '2';
      if (el.hari) el.hari.value = contoh.hari || '30';
      if (el.tarif) el.tarif.value = contoh.tarif || '1444.7';
      if (el.dayaAlat) el.dayaAlat.focus();
    } else if (mode === 'hambatan') {
      if (el.jenis) el.jenis.value = contoh.jenis || 'seri';
      if (el.daftar) el.daftar.value = contoh.daftar || '100\n220\n470';
      if (el.daftar) el.daftar.focus();
    }

    resetResults();
    setStatus('Contoh berhasil diisi. Tekan "Hitung" untuk melihat hasil.', '');
    updateControls();
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      var code = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error) {
          code = parsed.error.code || '';
          message = parsed.error.message || '';
        }
      } catch (err) {
        /* abaikan json parse error */
      }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan kalkulator listrik belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Ukuran data atau nilai masukan melebihi batas yang diizinkan.';
        } else {
          message = 'Terjadi kendala saat memproses perhitungan (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }

      var e = new Error(message);
      e.pesanLayanan = true;
      e.kodeLayanan = code;
      throw e;
    });
  }

  function submitCalc() {
    if (state.busy) return;

    var mode = el.mode ? el.mode.value : 'ohm';
    var form = new FormData();
    form.append('mode', mode);

    if (mode === 'ohm') {
      var v = el.tegangan ? el.tegangan.value.trim() : '';
      var i = el.arus ? el.arus.value.trim() : '';
      var r = el.hambatan ? el.hambatan.value.trim() : '';

      var count = (v ? 1 : 0) + (i ? 1 : 0) + (r ? 1 : 0);
      if (count < 2) {
        setStatus('Isi dua nilai dari tiga yang tersedia, biarkan satu kosong.', 'error');
        if (!v && el.tegangan) el.tegangan.focus();
        else if (!i && el.arus) el.arus.focus();
        else if (!r && el.hambatan) el.hambatan.focus();
        return;
      }
      if (count > 2) {
        setStatus('Isi tepat dua nilai, kosongkan satu supaya dihitung.', 'error');
        return;
      }

      form.append('tegangan', v);
      form.append('arus', i);
      form.append('hambatan', r);

    } else if (mode === 'daya') {
      var da = el.dayaAlat ? el.dayaAlat.value.trim() : '';
      var jamVal = el.jam ? el.jam.value.trim() : '';
      var jmlVal = el.jumlah ? el.jumlah.value.trim() : '';
      var hariVal = el.hari ? el.hari.value.trim() : '';
      var tarifVal = el.tarif ? el.tarif.value.trim() : '';

      if (!da || !jamVal || !jmlVal || !hariVal || !tarifVal) {
        setStatus('Lengkapi semua kolom perkiraan daya dan biaya terlebih dahulu.', 'error');
        return;
      }

      form.append('daya_alat', da);
      form.append('jam_per_hari', jamVal);
      form.append('jumlah_alat', jmlVal);
      form.append('hari', hariVal);
      form.append('tarif', tarifVal);

    } else if (mode === 'hambatan') {
      var d = el.daftar ? el.daftar.value.trim() : '';
      var jns = el.jenis ? el.jenis.value.trim() : 'seri';

      if (!d) {
        setStatus('Masukkan nilai hambatan terlebih dahulu (satu per baris).', 'error');
        if (el.daftar) el.daftar.focus();
        return;
      }

      form.append('daftar', d);
      form.append('jenis', jns);
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung...', 'busy');

    fetch(serverBase + '/api/listrik', { method: 'POST', body: form })
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
          : 'Koneksi ke layanan kalkulator listrik gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
      })
      .finally(function () {
        state.busy = false;
        updateControls();
      });
  }

  function createStatCard(label, value) {
    var card = document.createElement('div');
    card.className = 'listrik__stat-card';

    var lbl = document.createElement('span');
    lbl.className = 'listrik__stat-label';
    lbl.textContent = label;

    var val = document.createElement('span');
    val.className = 'listrik__stat-value';
    val.textContent = value;

    card.appendChild(lbl);
    card.appendChild(val);
    return card;
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    var summaryLines = [];
    summaryLines.push('Kalkulator listrik: ' + (data.mode_label || data.mode));
    summaryLines.push('----------------------------------------');

    if (data.mode === 'ohm') {
      if (el.heroLabel) el.heroLabel.textContent = (data.dihitung_label || 'Nilai Dihitung') + ' (' + data.hasil.satuan + ')';
      if (el.heroValue) el.heroValue.textContent = data.hasil.teks;
      if (el.heroSymbol) el.heroSymbol.textContent = data.hasil.satuan || '';

      if (el.heroSub) {
        el.heroSub.hidden = false;
        el.heroSub.textContent = 'Daya listrik yang dihasilkan: ' + data.daya.teks + ' W';
      }

      if (el.stats && data.rincian) {
        el.stats.hidden = false;
        el.stats.innerHTML = '';
        el.stats.appendChild(createStatCard('Tegangan (V)', data.rincian.tegangan.teks + ' V'));
        el.stats.appendChild(createStatCard('Arus (I)', data.rincian.arus.teks + ' A'));
        el.stats.appendChild(createStatCard('Hambatan (R)', data.rincian.hambatan.teks + ' Ω'));
        el.stats.appendChild(createStatCard('Daya (P)', data.rincian.daya.teks + ' W'));
      }

      summaryLines.push('Tegangan : ' + data.rincian.tegangan.teks + ' V');
      summaryLines.push('Arus     : ' + data.rincian.arus.teks + ' A');
      summaryLines.push('Hambatan : ' + data.rincian.hambatan.teks + ' Ω');
      summaryLines.push('Daya     : ' + data.rincian.daya.teks + ' W');

    } else if (data.mode === 'daya') {
      if (el.heroLabel) el.heroLabel.textContent = 'Perkiraan Total Biaya';
      if (el.heroValue) el.heroValue.textContent = data.hasil.biaya.teks;
      if (el.heroSymbol) el.heroSymbol.textContent = '';

      if (el.heroSub) {
        el.heroSub.hidden = false;
        el.heroSub.textContent = 'Total konsumsi energi: ' + data.hasil.kwh.teks + ' kWh';
      }

      if (el.stats && data.turunan) {
        el.stats.hidden = false;
        el.stats.innerHTML = '';
        el.stats.appendChild(createStatCard('Energi per hari', data.turunan.kwh_per_hari.teks + ' kWh'));
        el.stats.appendChild(createStatCard('Biaya per hari', data.turunan.biaya_per_hari.teks));
        el.stats.appendChild(createStatCard('Biaya per bulan (30 hari)', data.turunan.biaya_per_bulan.teks));
        el.stats.appendChild(createStatCard('Biaya per tahun (365 hari)', data.turunan.biaya_per_tahun.teks));
      }

      summaryLines.push('Total Energi : ' + data.hasil.kwh.teks + ' kWh');
      summaryLines.push('Total Biaya  : ' + data.hasil.biaya.teks);
      summaryLines.push('Biaya/Hari   : ' + data.turunan.biaya_per_hari.teks);
      summaryLines.push('Biaya/Bulan  : ' + data.turunan.biaya_per_bulan.teks);
      summaryLines.push('Biaya/Tahun  : ' + data.turunan.biaya_per_tahun.teks);

    } else if (data.mode === 'hambatan') {
      if (el.heroLabel) el.heroLabel.textContent = data.hasil.label || 'Hambatan Total';
      if (el.heroValue) el.heroValue.textContent = data.hasil.teks;
      if (el.heroSymbol) el.heroSymbol.textContent = data.hasil.satuan || 'Ω';

      if (el.heroSub) {
        el.heroSub.hidden = false;
        el.heroSub.textContent = 'Rangkaian ' + data.jenis + ' dengan ' + data.jumlah_komponen + ' komponen resistor.';
      }

      if (el.stats && Array.isArray(data.komponen)) {
        el.stats.hidden = false;
        el.stats.innerHTML = '';
        for (var i = 0; i < data.komponen.length; i++) {
          var komp = data.komponen[i];
          el.stats.appendChild(createStatCard('Resistor R' + komp.nomor, komp.teks + ' Ω'));
        }
      }

      summaryLines.push('Jenis Rangkaian   : ' + data.jenis);
      summaryLines.push('Jumlah Komponen   : ' + data.jumlah_komponen);
      summaryLines.push('Hambatan Total    : ' + data.hasil.teks + ' Ω');
    }

    // Render langkah perhitungan
    if (el.stepsWrap && el.steps && Array.isArray(data.langkah) && data.langkah.length > 0) {
      el.stepsWrap.hidden = false;
      el.steps.innerHTML = '';
      summaryLines.push('');
      summaryLines.push('Langkah perhitungan:');
      for (var s = 0; s < data.langkah.length; s++) {
        var stepLi = document.createElement('li');
        stepLi.textContent = data.langkah[s];
        el.steps.appendChild(stepLi);
        summaryLines.push((s + 1) + '. ' + data.langkah[s]);
      }
    } else if (el.stepsWrap) {
      el.stepsWrap.hidden = true;
    }

    // Render catatan jujur
    if (el.noteBox && el.noteText && data.catatan_jujur) {
      el.noteBox.hidden = false;
      el.noteText.textContent = data.catatan_jujur;
      summaryLines.push('');
      summaryLines.push('Catatan: ' + data.catatan_jujur);
    } else if (el.noteBox) {
      el.noteBox.hidden = true;
    }

    state.lastTextSummary = summaryLines.join('\n');
  }

  function copyResult() {
    if (!state.lastTextSummary) return;

    function notify(ok) {
      if (ok) {
        setStatus('Hasil disalin ke papan klip.', 'ok');
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
      navigator.clipboard.writeText(state.lastTextSummary).then(function () {
        notify(true);
      }).catch(function () {
        notify(false);
      });
    } else {
      var ta = document.createElement('textarea');
      ta.value = state.lastTextSummary;
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
    if (!state.lastTextSummary) return;

    revokeDownload();
    var blob = new Blob([state.lastTextSummary], { type: 'text/plain;charset=utf-8' });
    state.downloadUrl = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = 'hasil-listrik.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function resetAll() {
    if (el.tegangan) el.tegangan.value = '';
    if (el.arus) el.arus.value = '';
    if (el.hambatan) el.hambatan.value = '';

    if (el.dayaAlat) el.dayaAlat.value = '';
    if (el.jam) el.jam.value = '';
    if (el.jumlah) el.jumlah.value = '';
    if (el.hari) el.hari.value = '';
    if (el.tarif) el.tarif.value = '';

    if (el.daftar) el.daftar.value = '';

    resetResults();
    setStatus('Pilih mode, masukkan angka, lalu tekan "Hitung".', '');
    updateControls();

    var mode = el.mode ? el.mode.value : 'ohm';
    if (mode === 'ohm' && el.tegangan) el.tegangan.focus();
    else if (mode === 'daya' && el.dayaAlat) el.dayaAlat.focus();
    else if (mode === 'hambatan' && el.daftar) el.daftar.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="listrik"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'listrik-panel');
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
    } catch (e) {
      /* abaikan */
    }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    var mode = el.mode ? el.mode.value : 'ohm';
    setTimeout(function () {
      if (mode === 'ohm' && el.tegangan) el.tegangan.focus();
      else if (mode === 'daya' && el.dayaAlat) el.dayaAlat.focus();
      else if (mode === 'hambatan' && el.daftar) el.daftar.focus();
    }, 100);
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
  if (el.mode) el.mode.addEventListener('change', updateModeUI);
  if (el.btnContoh) el.btnContoh.addEventListener('click', isiContoh);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.submit) el.submit.addEventListener('click', submitCalc);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  var inputs = [
    el.tegangan, el.arus, el.hambatan,
    el.dayaAlat, el.jam, el.jumlah, el.hari, el.tarif,
    el.daftar
  ];
  for (var k = 0; k < inputs.length; k++) {
    if (inputs[k]) {
      inputs[k].addEventListener('input', updateControls);
    }
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
        submitCalc();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel ke registry global OmniTools
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['listrik'] = toggle;

  // Inisialisasi tampilan
  updateModeUI();
  updateControls();

  // Dukungan buka lewat parameter URL: ?alat=listrik atau ?alat=listrik&mode=<mode>
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('alat') !== 'listrik') return;

      var paramMode = params.get('mode');
      if (paramMode && (paramMode === 'ohm' || paramMode === 'daya' || paramMode === 'hambatan')) {
        if (el.mode) el.mode.value = paramMode;
      }
      updateModeUI();
      open();
    } catch (e) {
      /* abaikan */
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', handleUrlParam);
  } else {
    handleUrlParam();
  }
})();
