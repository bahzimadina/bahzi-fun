/* =========================================================================
   Panel alat: Prime Number Generator (Hasilkan bilangan prima)
   Data dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu langsung dibuang setelah selesai. Tidak ada yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('prime-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('prime-title'),
    limits: document.getElementById('prime-limits'),
    note: document.getElementById('prime-note'),
    close: document.getElementById('prime-close'),
    mode: document.getElementById('prime-mode'),
    groupDeret: document.getElementById('prime-group-deret'),
    inputJumlah: document.getElementById('prime-input-jumlah'),
    groupRentang: document.getElementById('prime-group-rentang'),
    inputDari: document.getElementById('prime-input-dari'),
    inputSampai: document.getElementById('prime-input-sampai'),
    groupPeriksa: document.getElementById('prime-group-periksa'),
    inputAngka: document.getElementById('prime-input-angka'),
    status: document.getElementById('prime-status'),
    clear: document.getElementById('prime-clear'),
    submit: document.getElementById('prime-submit'),
    results: document.getElementById('prime-results'),
    resultHint: document.getElementById('prime-result-hint'),
    outputWrap: document.getElementById('prime-output-wrap'),
    statBanyak: document.getElementById('prime-stat-banyak'),
    statTerbesar: document.getElementById('prime-stat-terbesar'),
    statWaktu: document.getElementById('prime-stat-waktu'),
    outputText: document.getElementById('prime-output-text'),
    copy: document.getElementById('prime-copy'),
    download: document.getElementById('prime-download')
  };

  var FALLBACK_MODES = [
    { id: 'deret', label: 'Deret bilangan prima pertama' },
    { id: 'rentang', label: 'Cari prima dalam rentang' },
    { id: 'periksa', label: 'Periksa satu angka' }
  ];

  var state = {
    mode: 'deret',
    modes: FALLBACK_MODES,
    limitsLoaded: false,
    limitsLoading: false,
    busy: false,
    lastFocus: null,
    lastResultText: '',
    downloadUrl: null
  };

  var nf = new Intl.NumberFormat('id-ID');

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

  function updateModeUI() {
    var modeVal = el.mode ? el.mode.value : 'deret';
    if (modeVal !== 'deret' && modeVal !== 'rentang' && modeVal !== 'periksa') {
      modeVal = 'deret';
    }
    state.mode = modeVal;

    if (el.groupDeret) el.groupDeret.hidden = modeVal !== 'deret';
    if (el.groupRentang) el.groupRentang.hidden = modeVal !== 'rentang';
    if (el.groupPeriksa) el.groupPeriksa.hidden = modeVal !== 'periksa';

    updateControls();
  }

  function updateControls() {
    var hasValidInput = false;
    if (state.mode === 'deret') {
      hasValidInput = el.inputJumlah && el.inputJumlah.value.trim().length > 0;
    } else if (state.mode === 'rentang') {
      var dari = el.inputDari ? el.inputDari.value.trim() : '';
      var sampai = el.inputSampai ? el.inputSampai.value.trim() : '';
      hasValidInput = dari.length > 0 && sampai.length > 0;
    } else if (state.mode === 'periksa') {
      hasValidInput = el.inputAngka && el.inputAngka.value.trim().length > 0;
    }

    if (el.submit) el.submit.disabled = state.busy || !hasValidInput;
    if (el.clear) el.clear.disabled = state.busy;
  }

  function resetResults() {
    revokeDownload();
    state.lastResultText = '';
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.outputText) el.outputText.value = '';
    if (el.statBanyak) el.statBanyak.textContent = '0';
    if (el.statTerbesar) el.statTerbesar.textContent = '0';
    if (el.statWaktu) el.statWaktu.textContent = '0 ms';
  }

  function resetAll() {
    if (state.mode === 'deret') {
      if (el.inputJumlah) {
        el.inputJumlah.value = '100';
        el.inputJumlah.focus();
      }
    } else if (state.mode === 'rentang') {
      if (el.inputDari) el.inputDari.value = '2';
      if (el.inputSampai) {
        el.inputSampai.value = '100';
        el.inputSampai.focus();
      }
    } else if (state.mode === 'periksa') {
      if (el.inputAngka) {
        el.inputAngka.value = '97';
        el.inputAngka.focus();
      }
    }
    resetResults();
    updateControls();
    setStatus('Pilih mode, masukkan angka, lalu tekan "Hitung".', '');
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      try {
        URL.revokeObjectURL(state.downloadUrl);
      } catch (e) {
        /* abaikan */
      }
      state.downloadUrl = null;
    }
  }

  function loadLimits() {
    if (state.limitsLoaded || state.limitsLoading) return;
    state.limitsLoading = true;

    fetch(serverBase + '/api/prime/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsLoading = false;
        if (!data || typeof data !== 'object') return;
        state.limitsLoaded = true;

        if (Array.isArray(data.modes) && data.modes.length > 0) {
          state.modes = data.modes;
          if (el.mode) {
            var currentVal = el.mode.value;
            el.mode.textContent = '';
            data.modes.forEach(function (m) {
              var opt = document.createElement('option');
              opt.value = m.id;
              opt.textContent = m.label;
              if (m.id === currentVal) opt.selected = true;
              el.mode.appendChild(opt);
            });
          }
        }
      })
      .catch(function () {
        state.limitsLoading = false;
        /* mode cadangan tetap dipakai */
      });
  }

  function submitCalc() {
    if (state.busy) return;

    var mode = state.mode;
    var formData = new FormData();
    formData.append('mode', mode);

    if (mode === 'deret') {
      var jumlah = el.inputJumlah ? el.inputJumlah.value.trim() : '';
      if (!jumlah) {
        setStatus('Jumlah bilangan prima wajib diisi.', 'error');
        if (el.inputJumlah) el.inputJumlah.focus();
        return;
      }
      formData.append('jumlah', jumlah);
    } else if (mode === 'rentang') {
      var dari = el.inputDari ? el.inputDari.value.trim() : '';
      var sampai = el.inputSampai ? el.inputSampai.value.trim() : '';
      if (!dari) {
        setStatus('Batas awal rentang wajib diisi.', 'error');
        if (el.inputDari) el.inputDari.focus();
        return;
      }
      if (!sampai) {
        setStatus('Batas akhir rentang wajib diisi.', 'error');
        if (el.inputSampai) el.inputSampai.focus();
        return;
      }
      formData.append('dari', dari);
      formData.append('sampai', sampai);
    } else if (mode === 'periksa') {
      var angka = el.inputAngka ? el.inputAngka.value.trim() : '';
      if (!angka) {
        setStatus('Angka yang akan diperiksa wajib diisi.', 'error');
        if (el.inputAngka) el.inputAngka.focus();
        return;
      }
      formData.append('angka', angka);
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung bilangan prima...', 'busy');

    fetch(serverBase + '/api/prime', {
      method: 'POST',
      body: formData
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, status: res.status, data: data };
        });
      })
      .then(function (resObj) {
        state.busy = false;
        updateControls();

        if (!resObj.ok) {
          var msg = (resObj.data && resObj.data.error && resObj.data.error.message)
            ? resObj.data.error.message
            : 'Perhitungan gagal diproses.';
          setStatus(msg, 'error');
          return;
        }

        displayResults(resObj.data);
      })
      .catch(function () {
        state.busy = false;
        updateControls();
        setStatus('Koneksi ke layanan gagal. Coba lagi sebentar lagi.', 'error');
      });
  }

  function displayResults(data) {
    if (!data) return;

    var resultText = '';
    var banyakStr = '0';
    var terbesarStr = '0';
    var waktuStr = (typeof data.waktu_ms === 'number' && data.waktu_ms < 1)
      ? '< 1 ms'
      : nf.format(Math.round(data.waktu_ms || 0)) + ' ms';

    if (data.mode === 'periksa') {
      var nFormatted = nf.format(data.angka);
      if (data.prima) {
        resultText = nFormatted + ' adalah bilangan prima.\nFaktorisasi prima: ' + data.faktorisasi;
        banyakStr = '1 (prima)';
        terbesarStr = nFormatted;
      } else {
        resultText = nFormatted + ' bukan bilangan prima.\nFaktorisasi prima: ' + data.faktorisasi;
        var totalFaktor = Array.isArray(data.faktor) ? data.faktor.length : 0;
        banyakStr = nf.format(totalFaktor) + ' faktor prima';
        var maxFaktor = 0;
        if (Array.isArray(data.faktor)) {
          data.faktor.forEach(function (f) {
            if (f.prima > maxFaktor) maxFaktor = f.prima;
          });
        }
        terbesarStr = maxFaktor > 0 ? nf.format(maxFaktor) : '-';
      }
    } else {
      var list = Array.isArray(data.daftar) ? data.daftar : [];
      resultText = list.join(', ');
      banyakStr = nf.format(data.banyak || list.length);
      terbesarStr = data.terbesar ? nf.format(data.terbesar) : (list.length > 0 ? nf.format(list[list.length - 1]) : '-');
    }

    state.lastResultText = resultText;

    if (el.statBanyak) el.statBanyak.textContent = banyakStr;
    if (el.statTerbesar) el.statTerbesar.textContent = terbesarStr;
    if (el.statWaktu) el.statWaktu.textContent = waktuStr;
    if (el.outputText) el.outputText.value = resultText;

    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    setStatus('Perhitungan selesai dalam ' + waktuStr + '.', 'success');
  }

  function copyResult() {
    if (!state.lastResultText) return;
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(state.lastResultText)
        .then(function () {
          setStatus('Hasil perhitungan berhasil disalin ke papan klip.', 'success');
        })
        .catch(function () {
          fallbackCopy();
        });
    } else {
      fallbackCopy();
    }
  }

  function fallbackCopy() {
    if (!el.outputText) return;
    try {
      el.outputText.select();
      document.execCommand('copy');
      setStatus('Hasil perhitungan berhasil disalin ke papan klip.', 'success');
    } catch (e) {
      setStatus('Gagal menyalin otomatis. Silakan salin teks di kotak hasil.', 'error');
    }
  }

  function downloadResult() {
    if (!state.lastResultText) return;
    revokeDownload();

    var blob = new Blob([state.lastResultText], { type: 'text/plain;charset=utf-8' });
    state.downloadUrl = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = 'hasil-bilangan-prima.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setStatus('Berkas hasil-bilangan-prima.txt berhasil diunduh.', 'success');
  }

  function syncTriggers(isOpen) {
    var triggers = document.querySelectorAll('[data-tool-action="prime"]');
    for (var i = 0; i < triggers.length; i++) {
      var t = triggers[i];
      if (t.tagName === 'BUTTON' || t.classList.contains('tool-card__open')) {
        t.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      }
      var card = t.closest ? t.closest('.tool-card') : null;
      if (card) {
        card.classList.toggle('tool-card--active', isOpen);
      }
    }
  }

  function open() {
    if (!panel.hidden) return;
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);
    loadLimits();

    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    setTimeout(function () {
      if (state.mode === 'deret' && el.inputJumlah) {
        el.inputJumlah.focus();
      } else if (state.mode === 'rentang' && el.inputDari) {
        el.inputDari.focus();
      } else if (state.mode === 'periksa' && el.inputAngka) {
        el.inputAngka.focus();
      }
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

  if (el.mode) {
    el.mode.addEventListener('change', function () {
      updateModeUI();
      resetResults();
      setStatus('Pilih mode, masukkan angka, lalu tekan "Hitung".', '');
      if (state.mode === 'deret' && el.inputJumlah) el.inputJumlah.focus();
      if (state.mode === 'rentang' && el.inputDari) el.inputDari.focus();
      if (state.mode === 'periksa' && el.inputAngka) el.inputAngka.focus();
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitCalc();
    }
  }

  [el.inputJumlah, el.inputDari, el.inputSampai, el.inputAngka].forEach(function (inp) {
    if (inp) {
      inp.addEventListener('input', updateControls);
      inp.addEventListener('keydown', onInputKeydown);
    }
  });

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

  // Daftarkan panel ke registry global OmniTools
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['prime'] = toggle;

  // Inisialisasi awal
  updateModeUI();
  updateControls();

  // Dukungan buka lewat parameter URL: ?alat=prime (boleh ditambah &mode=... &jumlah=... &dari=... &sampai=... &angka=...)
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('alat') !== 'prime') return;

      var paramMode = params.get('mode');
      if (paramMode && (paramMode === 'deret' || paramMode === 'rentang' || paramMode === 'periksa')) {
        if (el.mode) el.mode.value = paramMode;
      }

      if (params.get('jumlah') && el.inputJumlah) {
        el.inputJumlah.value = params.get('jumlah');
      }
      if (params.get('dari') && el.inputDari) {
        el.inputDari.value = params.get('dari');
      }
      if (params.get('sampai') && el.inputSampai) {
        el.inputSampai.value = params.get('sampai');
      }
      if (params.get('angka') && el.inputAngka) {
        el.inputAngka.value = params.get('angka');
      }

      updateModeUI();
      open();
      submitCalc();
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
