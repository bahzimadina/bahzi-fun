/* =========================================================================
   Panel alat: Hitung Mundur (Countdown Timer)
   Data dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu hitungan berdetak di peramban. Tidak ada yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('countdown-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('countdown-title'),
    limits: document.getElementById('countdown-limits'),
    note: document.getElementById('countdown-note'),
    close: document.getElementById('countdown-close'),
    mode: document.getElementById('countdown-mode'),
    rowMomen: document.getElementById('countdown-row-momen'),
    tanggal: document.getElementById('countdown-tanggal'),
    jam: document.getElementById('countdown-jam'),
    btnBesok: document.getElementById('countdown-pakai-besok'),
    btnAkhirBulan: document.getElementById('countdown-pakai-akhir-bulan'),
    btnAkhirTahun: document.getElementById('countdown-pakai-akhir-tahun'),
    rowDurasi: document.getElementById('countdown-row-durasi'),
    jumlah: document.getElementById('countdown-jumlah'),
    satuan: document.getElementById('countdown-satuan'),
    status: document.getElementById('countdown-status'),
    clear: document.getElementById('countdown-clear'),
    submit: document.getElementById('countdown-submit'),
    results: document.getElementById('countdown-results'),
    resultHint: document.getElementById('countdown-result-hint'),
    outputWrap: document.getElementById('countdown-output-wrap'),
    hari: document.getElementById('countdown-card-hari'),
    menit: document.getElementById('countdown-card-menit'),
    detik: document.getElementById('countdown-card-detik'),
    sisaTeks: document.getElementById('countdown-sisa-teks'),
    targetLabel: document.getElementById('countdown-target-label'),
    progressWrap: document.getElementById('countdown-progress-wrap'),
    progress: document.getElementById('countdown-progress'),
    progressFill: document.getElementById('countdown-progress-fill'),
    details: document.getElementById('countdown-details'),
    copy: document.getElementById('countdown-copy'),
    share: document.getElementById('countdown-share'),
    download: document.getElementById('countdown-download')
  };

  var cardHari = document.getElementById('countdown-card-hari');
  var cardJam = document.getElementById('countdown-card-jam');
  var cardMenit = document.getElementById('countdown-card-menit');
  var cardDetik = document.getElementById('countdown-card-detik');

  var state = {
    modes: [],
    satuan: [],
    minYear: 1900,
    maxYear: 2100,
    limitsLoaded: false,
    limitsLoading: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    targetMs: null,
    durasiDetik: 0,
    mode: 'ke_momen',
    timerId: null
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

  function stopTimer() {
    if (state.timerId) {
      clearInterval(state.timerId);
      state.timerId = null;
    }
  }

  function setCardValues(h, j, m, d) {
    if (cardHari) cardHari.textContent = String(h);
    if (cardJam) cardJam.textContent = String(j);
    if (cardMenit) cardMenit.textContent = String(m);
    if (cardDetik) cardDetik.textContent = String(d);
  }

  function updateModeUI() {
    if (!el.mode) return;
    var modeVal = (el.mode && el.mode.value) ? el.mode.value : (state.mode || 'ke_momen');
    if (modeVal !== 'ke_momen' && modeVal !== 'dari_durasi') {
      modeVal = 'ke_momen';
    }
    state.mode = modeVal;

    if (modeVal === 'ke_momen') {
      if (el.rowMomen) el.rowMomen.hidden = false;
      if (el.rowDurasi) el.rowDurasi.hidden = true;
    } else {
      if (el.rowMomen) el.rowMomen.hidden = true;
      if (el.rowDurasi) el.rowDurasi.hidden = false;
    }
    updateControls();
  }

  function resetResults() {
    stopTimer();
    panel.removeAttribute('data-selesai');
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    setCardValues(0, 0, 0, 0);
    if (el.sisaTeks) el.sisaTeks.textContent = '';
    if (el.targetLabel) el.targetLabel.textContent = '';
    if (el.progressWrap) el.progressWrap.hidden = true;
    if (el.progressFill) el.progressFill.style.width = '0%';
    if (el.progress) el.progress.setAttribute('aria-valuenow', '0');
    if (el.details) el.details.innerHTML = '';
    state.lastResult = null;
    state.targetMs = null;
  }

  function updateControls() {
    var modeVal = (el.mode && el.mode.value) ? el.mode.value : (state.mode || 'ke_momen');
    if (modeVal !== 'ke_momen' && modeVal !== 'dari_durasi') {
      modeVal = 'ke_momen';
    }
    var valTgl = el.tanggal ? el.tanggal.value.trim() : '';
    var valJml = el.jumlah ? el.jumlah.value.trim() : '';

    var valid = false;
    if (modeVal === 'ke_momen') {
      valid = valTgl.length > 0;
    } else if (modeVal === 'dari_durasi') {
      var num = parseInt(valJml, 10);
      valid = valJml.length > 0 && !isNaN(num) && num >= 0 && num <= 100000;
    }

    var hasAnyInput = valTgl.length > 0 || (valJml.length > 0 && valJml !== '25');
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !valid;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAnyInput && !hasOutput);
    }
  }

  function padZero(n) {
    return n < 10 ? '0' + n : String(n);
  }

  function formatDateIso(d) {
    return d.getFullYear() + '-' + padZero(d.getMonth() + 1) + '-' + padZero(d.getDate());
  }

  function formatReadableDuration(sec) {
    var totalSec = Math.max(0, parseInt(sec, 10) || 0);
    if (totalSec === 0) return '0 detik';
    var hari = Math.floor(totalSec / 86400);
    var rem = totalSec % 86400;
    var jam = Math.floor(rem / 3600);
    rem = rem % 3600;
    var menit = Math.floor(rem / 60);
    var detik = rem % 60;

    var parts = [];
    if (hari > 0) parts.push(hari + ' hari');
    if (jam > 0) parts.push(jam + ' jam');
    if (menit > 0) parts.push(menit + ' menit');
    if (detik > 0 && hari === 0) parts.push(detik + ' detik');
    if (parts.length === 0 && detik > 0) parts.push(detik + ' detik');
    return (parts.length > 2 ? parts.slice(0, 2) : parts).join(' ') || '0 detik';
  }

  function loadLimits() {
    if (state.limitsLoaded || state.limitsLoading) return;
    state.limitsLoading = true;
    fetch(serverBase + '/api/countdown/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limitsLoading = false;
        if (!data) return;
        if (data.min_year) state.minYear = data.min_year;
        if (data.max_year) state.maxYear = data.max_year;

        if (el.limits) {
          el.limits.textContent = 'Rentang tahun ' + state.minYear + ' sampai ' + state.maxYear;
        }

        var minStr = state.minYear + '-01-01';
        var maxStr = state.maxYear + '-12-31';
        if (el.tanggal) {
          el.tanggal.min = minStr;
          el.tanggal.max = maxStr;
        }

        if (Array.isArray(data.modes) && data.modes.length > 0) {
          state.modes = data.modes;
          if (el.mode) {
            var curMode = (el.mode && el.mode.value) ? el.mode.value : (state.mode || 'ke_momen');
            el.mode.innerHTML = '';
            for (var i = 0; i < data.modes.length; i++) {
              var m = data.modes[i];
              var opt = document.createElement('option');
              opt.value = m.id;
              opt.textContent = m.label;
              if (m.id === curMode) opt.selected = true;
              el.mode.appendChild(opt);
            }
          }
        }

        if (Array.isArray(data.satuan) && data.satuan.length > 0) {
          state.satuan = data.satuan;
          if (el.satuan) {
            var curSatuan = el.satuan.value;
            el.satuan.innerHTML = '';
            for (var j = 0; j < data.satuan.length; j++) {
              var s = data.satuan[j];
              var sOpt = document.createElement('option');
              sOpt.value = s.id;
              sOpt.textContent = s.label;
              if (s.id === curSatuan) sOpt.selected = true;
              el.satuan.appendChild(sOpt);
            }
          }
        }

        state.limitsLoaded = true;
        updateModeUI();
      })
      .catch(function () {
        state.limitsLoading = false;
        updateModeUI();
      });
  }

  function tick() {
    if (!state.lastResult || state.targetMs === null || isNaN(state.targetMs)) return;
    var now = Date.now();
    var diffMs = state.targetMs - now;

    if (diffMs <= 0) {
      stopTimer();
      panel.setAttribute('data-selesai', 'true');
      setCardValues(0, 0, 0, 0);
      if (el.sisaTeks) {
        el.sisaTeks.textContent = (state.mode === 'ke_momen') ? 'Waktunya tiba.' : 'Hitungan selesai.';
      }
      if (state.mode === 'dari_durasi' && el.progress && el.progressFill) {
        el.progressFill.style.width = '100%';
        el.progress.setAttribute('aria-valuenow', '100');
      }
      return;
    }

    var totalSec = Math.floor(diffMs / 1000);
    var hari = Math.floor(totalSec / 86400);
    var rem = totalSec % 86400;
    var jam = Math.floor(rem / 3600);
    rem = rem % 3600;
    var menit = Math.floor(rem / 60);
    var detik = rem % 60;

    setCardValues(hari, jam, menit, detik);

    if (el.sisaTeks) {
      var parts = [];
      if (hari > 0) parts.push(hari + ' hari');
      if (jam > 0) parts.push(jam + ' jam');
      if (menit > 0) parts.push(menit + ' menit');
      if (detik > 0 && hari === 0) parts.push(detik + ' detik');
      if (parts.length === 0 && detik > 0) parts.push(detik + ' detik');
      var compact = parts.slice(0, 2).join(' ');
      el.sisaTeks.textContent = compact ? (compact + ' lagi') : 'kurang dari 1 detik lagi';
    }

    if (state.mode === 'dari_durasi' && state.durasiDetik > 0 && el.progress && el.progressFill) {
      var sisa = Math.max(0, totalSec);
      var pct = Math.min(100, Math.max(0, ((state.durasiDetik - sisa) / state.durasiDetik) * 100));
      el.progressFill.style.width = pct.toFixed(1) + '%';
      el.progress.setAttribute('aria-valuenow', Math.round(pct));
    }
  }

  function startTimer() {
    stopTimer();
    state.timerId = setInterval(tick, 1000);
  }

  function renderResults(data) {
    state.lastResult = data;
    state.mode = data.mode;
    state.durasiDetik = data.durasi_detik || 0;

    var parsedTarget = new Date(data.target);
    state.targetMs = parsedTarget.getTime();

    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.targetLabel) {
      if (data.lewat) {
        el.targetLabel.textContent = 'Sudah lewat: ' + data.target_label;
      } else {
        el.targetLabel.textContent = 'Menuju ' + data.target_label;
      }
    }

    if (data.mode === 'dari_durasi') {
      if (el.progressWrap) el.progressWrap.hidden = false;
      if (el.progressFill) {
        var initPct = 0;
        if (data.durasi_detik > 0) {
          initPct = Math.min(100, Math.max(0, ((data.durasi_detik - data.sisa_detik) / data.durasi_detik) * 100));
        }
        el.progressFill.style.width = initPct.toFixed(1) + '%';
      }
      if (el.progress) {
        el.progress.setAttribute('aria-valuenow', Math.round(initPct || 0));
      }
    } else {
      if (el.progressWrap) el.progressWrap.hidden = true;
    }

    // Grid rincian: total jam, total menit, total detik, jatuh pada hari, waktu server
    if (el.details) {
      el.details.innerHTML = '';
      var detikRow;
      if (data.lewat) {
        detikRow = {
          label: 'Sudah lewat',
          nilai: formatReadableDuration(data.lewat_detik)
        };
      } else {
        detikRow = {
          label: 'Total detik',
          nilai: (data.sisa_detik || 0).toLocaleString('id-ID') + ' detik'
        };
      }

      var rincianList = [
        { label: 'Total jam', nilai: (data.total_jam || 0).toLocaleString('id-ID') + ' jam' },
        { label: 'Total menit', nilai: (data.total_menit || 0).toLocaleString('id-ID') + ' menit' },
        detikRow,
        { label: 'Jatuh pada hari', nilai: data.target_hari },
        { label: 'Waktu server', nilai: (data.server_now || '').replace('T', ' ').replace('+07:00', ' WIB') }
      ];

      for (var i = 0; i < rincianList.length; i++) {
        var item = rincianList[i];
        var card = document.createElement('div');
        card.className = 'cd__stat-card';

        var labelSpan = document.createElement('span');
        labelSpan.className = 'cd__stat-label';
        labelSpan.textContent = item.label;

        var valueSpan = document.createElement('span');
        valueSpan.className = 'cd__stat-value';
        valueSpan.textContent = item.nilai;

        card.appendChild(labelSpan);
        card.appendChild(valueSpan);
        el.details.appendChild(card);
      }
    }

    if (data.lewat) {
      stopTimer();
      panel.setAttribute('data-selesai', 'true');
      setCardValues(0, 0, 0, 0);
      if (el.sisaTeks) el.sisaTeks.textContent = data.sisa_teks;
    } else {
      panel.removeAttribute('data-selesai');
      setCardValues(data.hari, data.jam, data.menit, data.detik);
      if (el.sisaTeks) el.sisaTeks.textContent = data.sisa_teks;
      startTimer();
      tick();
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
          message = 'Layanan hitung mundur belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Waktu atau jumlah di luar batas yang didukung.';
        } else {
          message = 'Terjadi kendala saat memproses hitungan mundur (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitCalc() {
    if (state.busy) return;

    var modeVal = (el.mode && el.mode.value) ? el.mode.value : (state.mode || 'ke_momen');
    if (modeVal !== 'ke_momen' && modeVal !== 'dari_durasi') {
      modeVal = 'ke_momen';
    }
    state.mode = modeVal;

    var valTgl = el.tanggal ? el.tanggal.value.trim() : '';
    var valJam = el.jam ? el.jam.value.trim() : '00:00';
    var valJml = el.jumlah ? el.jumlah.value.trim() : '25';
    var valSatuan = el.satuan ? el.satuan.value : 'menit';

    if (modeVal === 'ke_momen' && !valTgl) {
      setStatus('Masukkan tanggal target terlebih dahulu.', 'error');
      if (el.tanggal) el.tanggal.focus();
      return;
    }

    if (modeVal === 'dari_durasi' && !valJml) {
      setStatus('Masukkan jumlah durasi terlebih dahulu.', 'error');
      if (el.jumlah) el.jumlah.focus();
      return;
    }

    var form = new FormData();
    form.append('mode', modeVal);

    if (modeVal === 'ke_momen') {
      form.append('tanggal', valTgl);
      form.append('jam', valJam || '00:00');
    } else if (modeVal === 'dari_durasi') {
      form.append('jumlah', valJml);
      form.append('satuan', valSatuan);
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung...', 'busy');

    fetch(serverBase + '/api/countdown', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('Hitungan mundur aktif.', 'ok');
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

  function copyTextContent(text, btnElement, okMsg, errMsg) {
    function notify(ok) {
      setStatus(ok ? okMsg : errMsg, ok ? 'ok' : 'error');
      if (btnElement) {
        var orig = btnElement.textContent;
        btnElement.textContent = ok ? 'Tersalin!' : 'Gagal salin';
        setTimeout(function () {
          btnElement.textContent = orig;
        }, 1500);
      }
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text).then(function () {
        notify(true);
      }).catch(function () {
        notify(false);
      });
    } else {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
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

  function copyResult() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var lines = [
      'Hitung Mundur - bahzi.fun',
      'Target: ' + d.target_label,
      'Sisa waktu: ' + (el.sisaTeks ? el.sisaTeks.textContent : d.sisa_teks),
      'Hari: ' + (cardHari ? cardHari.textContent : d.hari) +
        ', Jam: ' + (cardJam ? cardJam.textContent : d.jam) +
        ', Menit: ' + (cardMenit ? cardMenit.textContent : d.menit) +
        ', Detik: ' + (cardDetik ? cardDetik.textContent : d.detik),
      'Total jam: ' + d.total_jam + ' jam',
      'Total menit: ' + d.total_menit + ' menit',
      'Jatuh pada: ' + d.target_hari,
      'Catatan: ' + d.catatan
    ];
    copyTextContent(lines.join('\n'), el.copy, 'Hasil disalin.', 'Gagal menyalin hasil.');
  }

  function copyShareLink() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var shareUrl = 'https://bahzi.fun/?alat=countdown&ke=' + encodeURIComponent(d.target_tanggal + 'T' + d.target_jam);
    copyTextContent(shareUrl, el.share, 'Tautan disalin ke clipboard.', 'Gagal menyalin tautan.');
  }

  function downloadResult() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var lines = [
      'Hitung Mundur - bahzi.fun',
      '========================================',
      'Target: ' + d.target_label,
      'Sisa waktu: ' + (el.sisaTeks ? el.sisaTeks.textContent : d.sisa_teks),
      'Rincian: ' + (cardHari ? cardHari.textContent : d.hari) + ' hari ' +
        (cardJam ? cardJam.textContent : d.jam) + ' jam ' +
        (cardMenit ? cardMenit.textContent : d.menit) + ' menit ' +
        (cardDetik ? cardDetik.textContent : d.detik) + ' detik',
      'Total jam: ' + d.total_jam + ' jam',
      'Total menit: ' + d.total_menit + ' menit',
      'Jatuh pada: ' + d.target_hari,
      'Waktu server: ' + d.server_now,
      'Catatan: ' + d.catatan
    ];
    var blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'hasil-hitung-mundur.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 100);
    setStatus('Hasil diunduh.', 'ok');
  }

  function resetAll() {
    stopTimer();
    if (el.tanggal) el.tanggal.value = '';
    if (el.jam) el.jam.value = '00:00';
    if (el.jumlah) el.jumlah.value = '25';
    resetResults();
    setStatus('Pilih mode, masukkan target waktu, lalu tekan "Hitung".', '');
    updateControls();
    if (el.mode && el.mode.value === 'ke_momen' && el.tanggal) {
      el.tanggal.focus();
    } else if (el.jumlah) {
      el.jumlah.focus();
    }
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="countdown"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'countdown-panel');
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

    if (el.tanggal) {
      setTimeout(function () { el.tanggal.focus(); }, 100);
    }
  }

  function close() {
    if (panel.hidden) return;
    stopTimer();
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

  // Pintasan chip (Besok, Akhir bulan, Akhir tahun)
  if (el.btnBesok) {
    el.btnBesok.addEventListener('click', function () {
      var d = new Date(Date.now() + 86400000);
      if (el.tanggal) el.tanggal.value = formatDateIso(d);
      if (el.jam) el.jam.value = '07:00';
      updateControls();
      if (el.tanggal) el.tanggal.focus();
    });
  }

  if (el.btnAkhirBulan) {
    el.btnAkhirBulan.addEventListener('click', function () {
      var now = new Date();
      var lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
      if (el.tanggal) el.tanggal.value = formatDateIso(lastDay);
      if (el.jam) el.jam.value = '23:59';
      updateControls();
      if (el.tanggal) el.tanggal.focus();
    });
  }

  if (el.btnAkhirTahun) {
    el.btnAkhirTahun.addEventListener('click', function () {
      var now = new Date();
      if (el.tanggal) el.tanggal.value = now.getFullYear() + '-12-31';
      if (el.jam) el.jam.value = '23:59';
      updateControls();
      if (el.tanggal) el.tanggal.focus();
    });
  }

  // Event Listeners
  if (el.close) el.close.addEventListener('click', close);

  if (el.mode) {
    el.mode.addEventListener('change', function () {
      updateModeUI();
      resetResults();
      setStatus('Pilih mode, masukkan target waktu, lalu tekan "Hitung".', '');
      updateControls();
      if (el.mode.value === 'ke_momen' && el.tanggal) {
        el.tanggal.focus();
      } else if (el.jumlah) {
        el.jumlah.focus();
      }
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitCalc();
    }
  }

  if (el.tanggal) {
    el.tanggal.addEventListener('input', updateControls);
    el.tanggal.addEventListener('keydown', onInputKeydown);
  }

  if (el.jam) {
    el.jam.addEventListener('input', updateControls);
    el.jam.addEventListener('keydown', onInputKeydown);
  }

  if (el.jumlah) {
    el.jumlah.addEventListener('input', updateControls);
    el.jumlah.addEventListener('keydown', onInputKeydown);
  }

  if (el.satuan) {
    el.satuan.addEventListener('change', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitCalc);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.share) el.share.addEventListener('click', copyShareLink);
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

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && !panel.hidden && state.timerId) {
      tick();
    }
  });

  window.addEventListener('pageshow', function () {
    if (!panel.hidden && state.timerId) {
      tick();
    }
  });

  // Daftarkan panel ke registry global
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['countdown'] = toggle;

  // Inisialisasi awal
  loadLimits();
  updateModeUI();
  updateControls();

  // Dukungan buka tautan berbagi: ?alat=countdown&ke=YYYY-MM-DDTHH:MM
  var shareCalculated = false;

  function applyShareTarget(ke) {
    if (shareCalculated) return;
    if (!ke || typeof ke !== 'string') return;
    var match = ke.match(/^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?$/);
    if (!match) return;

    shareCalculated = true;
    if (el.mode) el.mode.value = 'ke_momen';
    state.mode = 'ke_momen';
    updateModeUI();
    if (el.tanggal) el.tanggal.value = match[1];
    if (el.jam) el.jam.value = match[2] || '00:00';
    updateControls();
    submitCalc();
  }

  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('alat') !== 'countdown') return;

      var ke = params.get('ke');

      function waitForModeAndApply() {
        if (!ke || typeof ke !== 'string') return;

        var modeAttempts = 0;
        var maxModeAttempts = 20;
        var modeIntervalMs = 100;

        function checkMode() {
          var modeSelect = document.getElementById('countdown-mode');
          var hasOptions = !!(modeSelect && modeSelect.options && modeSelect.options.length > 0);

          if (hasOptions || modeAttempts >= maxModeAttempts) {
            applyShareTarget(ke);
            return;
          }

          modeAttempts++;
          setTimeout(checkMode, modeIntervalMs);
        }

        checkMode();
      }

      var maxCardAttempts = 10;
      var cardIntervalMs = 100;
      var cardAttempts = 0;

      function tryOpen() {
        var trigger = document.querySelector('button.tool-card__open[data-tool-action="countdown"]');
        if (trigger) {
          trigger.click();
          if (panel.hidden) open();
          waitForModeAndApply();
          return;
        }

        cardAttempts++;
        if (cardAttempts < maxCardAttempts) {
          setTimeout(tryOpen, cardIntervalMs);
        } else {
          open();
          waitForModeAndApply();
        }
      }

      tryOpen();
    } catch (e) {
      /* jangan gagal di konsol */
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', handleUrlParam);
  } else {
    handleUrlParam();
  }
})();
