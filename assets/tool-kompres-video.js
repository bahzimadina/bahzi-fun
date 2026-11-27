/* =========================================================================
   Panel alat: Kompres video
   Video dikirim ke server lewat multipart/form-data, diproses di server
   lewat berkas sementara di /tmp (tmpfs) menggunakan ffmpeg, lalu hasilnya
   diunduh langsung. Berkas sementara langsung dibersihkan setelah proses.

   Skrip terpisah dari app.js supaya modul dapat berjalan independen.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('kompres-video-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('kompres-video-close'),
    limits: document.getElementById('kompres-video-limits'),
    note: document.getElementById('kompres-video-note'),
    drop: document.getElementById('kompres-video-drop'),
    input: document.getElementById('kompres-video-input'),
    pickBtn: document.getElementById('kompres-video-pick-btn'),
    empty: document.getElementById('kompres-video-empty'),
    origWrap: document.getElementById('kompres-video-orig-wrap'),
    filename: document.getElementById('kompres-video-filename'),
    origMeta: document.getElementById('kompres-video-orig-meta'),
    controls: document.getElementById('kompres-video-controls'),
    modeRadios: panel.querySelectorAll('input[name="kompres-video-mode"]'),
    presetGroup: document.getElementById('kompres-video-preset-group'),
    presetRadios: panel.querySelectorAll('input[name="kompres-video-preset"]'),
    targetGroup: document.getElementById('kompres-video-target-group'),
    targetMb: document.getElementById('kompres-video-target-mb'),
    kecilkan: document.getElementById('kompres-video-kecilkan'),
    result: document.getElementById('kompres-video-result'),
    resultSavings: document.getElementById('kompres-video-result-savings'),
    resultStats: document.getElementById('kompres-video-result-stats'),
    resultNote: document.getElementById('kompres-video-result-note'),
    status: document.getElementById('kompres-video-status'),
    clear: document.getElementById('kompres-video-clear'),
    submit: document.getElementById('kompres-video-submit'),
    download: document.getElementById('kompres-video-download')
  };

  var FALLBACK_LIMITS = {
    max_bytes: 25 * 1024 * 1024,
    max_duration_seconds: 120,
    allowed_formats: ['MP4', 'MOV', 'WEBM', 'MKV'],
    target_mb_min: 1,
    target_mb_max: 20,
    target_mb_default: 5
  };

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    file: null,
    videoDuration: null,
    videoWidth: null,
    videoHeight: null,
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    busy: false,
    downloadUrl: null,
    lastFocus: null
  };

  // --- Pembantu -----------------------------------------------------------
  function formatBytes(bytes) {
    if (typeof bytes !== 'number' || isNaN(bytes)) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) {
      return (bytes / 1024).toFixed(1).replace('.', ',') + ' KB';
    }
    return (bytes / (1024 * 1024)).toFixed(2).replace('.', ',') + ' MB';
  }

  function formatDuration(sec) {
    if (typeof sec !== 'number' || isNaN(sec) || sec < 0) return '-';
    var totalSec = Math.floor(sec);
    var m = Math.floor(totalSec / 60);
    var s = totalSec % 60;
    var sStr = (s < 10 ? '0' : '') + s;
    return m + ':' + sStr;
  }

  function setStatus(message, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      panel.setAttribute('aria-busy', 'true');
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    } else {
      panel.removeAttribute('aria-busy');
    }
    el.status.appendChild(document.createTextNode(message));
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      try { URL.revokeObjectURL(state.downloadUrl); } catch (err) { /* abaikan */ }
      state.downloadUrl = null;
    }
  }

  function resetResultUi() {
    revokeDownload();
    if (el.download) {
      el.download.hidden = true;
      el.download.href = '#';
    }
    if (el.result) {
      el.result.hidden = true;
    }
    if (el.resultSavings) {
      el.resultSavings.textContent = '-';
    }
    if (el.resultStats) {
      el.resultStats.innerHTML = '';
    }
    if (el.resultNote) {
      el.resultNote.hidden = true;
      el.resultNote.textContent = '';
    }
  }

  function updateActionButtons() {
    var hasFile = !!state.file;
    if (el.submit) el.submit.disabled = !hasFile || state.busy;
    if (el.clear) el.clear.disabled = (!hasFile && !state.downloadUrl) || state.busy;
  }

  function getSelectedMode() {
    for (var i = 0; i < el.modeRadios.length; i++) {
      if (el.modeRadios[i].checked) return el.modeRadios[i].value;
    }
    return 'kualitas';
  }

  function getSelectedPreset() {
    for (var i = 0; i < el.presetRadios.length; i++) {
      if (el.presetRadios[i].checked) return el.presetRadios[i].value;
    }
    return 'seimbang';
  }

  function syncModeUi() {
    var mode = getSelectedMode();
    if (mode === 'target') {
      if (el.presetGroup) el.presetGroup.hidden = true;
      if (el.targetGroup) el.targetGroup.hidden = false;
    } else {
      if (el.presetGroup) el.presetGroup.hidden = false;
      if (el.targetGroup) el.targetGroup.hidden = true;
    }
  }

  // --- Muat batas dari server ---------------------------------------------
  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/video/compress/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('Gagal memuat batas server');
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.max_bytes) return;
        state.limits = data;
        state.limitsLoaded = true;

        if (el.limits) {
          var maxMb = Math.round(data.max_bytes / (1024 * 1024));
          var maxMenit = Math.round(data.max_duration_seconds / 60);
          el.limits.textContent = 'Maks 1 berkas, ' + maxMb + ' MB, durasi hingga ' + maxMenit + ' menit (' + data.allowed_formats.join(', ') + ')';
        }

        if (el.targetMb && data.target_mb_min && data.target_mb_max) {
          el.targetMb.min = String(data.target_mb_min);
          el.targetMb.max = String(data.target_mb_max);
        }
      })
      .catch(function () {
        // Biarkan batas fallback tetap terlihat
      });
  }

  // --- Penanganan berkas ---------------------------------------------------
  function handleFile(file) {
    if (!file) return;

    resetResultUi();

    // Validasi ekstensi
    var name = file.name || '';
    var dotIdx = name.lastIndexOf('.');
    var ext = dotIdx >= 0 ? name.substring(dotIdx + 1).toLowerCase() : '';
    var allowedExts = ['mp4', 'mov', 'webm', 'mkv'];

    if (allowedExts.indexOf(ext) === -1) {
      setStatus('Format berkas "' + (ext || 'tidak dikenal') + '" belum didukung. Gunakan video MP4, MOV, WebM, atau MKV.', 'error');
      return;
    }

    if (file.size === 0) {
      setStatus('Berkas video kosong.', 'error');
      return;
    }

    if (file.size > state.limits.max_bytes) {
      var maxMb = Math.round(state.limits.max_bytes / (1024 * 1024));
      setStatus('Ukuran video melebihi batas ' + maxMb + ' MB. Pilih berkas yang lebih kecil.', 'error');
      return;
    }

    state.file = file;
    state.videoDuration = null;
    state.videoWidth = null;
    state.videoHeight = null;

    if (el.filename) el.filename.textContent = file.name;
    if (el.origMeta) el.origMeta.textContent = 'Ukuran: ' + formatBytes(file.size) + ' • Membaca info video…';
    if (el.empty) el.empty.hidden = true;
    if (el.origWrap) el.origWrap.hidden = false;
    if (el.controls) el.controls.hidden = false;

    updateActionButtons();
    setStatus('Video siap diproses. Pilih cara kompresi lalu tekan tombol Kompres video.', 'info');

    // Baca durasi dan resolusi via elemen <video> di browser
    try {
      var blobUrl = URL.createObjectURL(file);
      var tempVideo = document.createElement('video');
      tempVideo.preload = 'metadata';
      tempVideo.onloadedmetadata = function () {
        state.videoDuration = tempVideo.duration;
        state.videoWidth = tempVideo.videoWidth;
        state.videoHeight = tempVideo.videoHeight;
        URL.revokeObjectURL(blobUrl);

        var metaText = 'Ukuran: ' + formatBytes(file.size);
        if (state.videoDuration && !isNaN(state.videoDuration)) {
          metaText += ' • Durasi: ' + formatDuration(state.videoDuration);
        }
        if (state.videoWidth && state.videoHeight) {
          metaText += ' • Resolusi: ' + state.videoWidth + 'x' + state.videoHeight;
        }
        if (el.origMeta) el.origMeta.textContent = metaText;

        // Peringatan jika durasi melebihi batas
        if (state.videoDuration && state.videoDuration > state.limits.max_duration_seconds) {
          var batasMenit = Math.round(state.limits.max_duration_seconds / 60);
          setStatus('Peringatan: Durasi video (' + formatDuration(state.videoDuration) + ') melebihi batas ' + batasMenit + ' menit. Proses mungkin akan ditolak server.', 'error');
        }
      };
      tempVideo.onerror = function () {
        URL.revokeObjectURL(blobUrl);
        if (el.origMeta) el.origMeta.textContent = 'Ukuran: ' + formatBytes(file.size);
      };
      tempVideo.src = blobUrl;
    } catch (e) {
      if (el.origMeta) el.origMeta.textContent = 'Ukuran: ' + formatBytes(file.size);
    }
  }

  function resetAll() {
    state.file = null;
    state.videoDuration = null;
    state.videoWidth = null;
    state.videoHeight = null;
    if (el.input) el.input.value = '';
    if (el.empty) el.empty.hidden = false;
    if (el.origWrap) el.origWrap.hidden = true;
    if (el.controls) el.controls.hidden = true;
    resetResultUi();
    updateActionButtons();
    setStatus('Pilih berkas video MP4, MOV, WebM, atau MKV untuk mulai kompres.', '');
  }

  // --- Kirim kompresi ------------------------------------------------------
  function submitCompress() {
    if (!state.file || state.busy) return;

    var mode = getSelectedMode();
    var preset = getSelectedPreset();
    var targetMb = el.targetMb ? el.targetMb.value.trim() : '';
    var kecilkan = (el.kecilkan && el.kecilkan.checked) ? 'ya' : 'tidak';

    if (mode === 'target') {
      var numTarget = parseFloat(targetMb);
      if (isNaN(numTarget) || numTarget < 1 || numTarget > 20) {
        setStatus('Target ukuran harus berupa angka antara 1 sampai 20 MB.', 'error');
        if (el.targetMb) el.targetMb.focus();
        return;
      }
    }

    state.busy = true;
    updateActionButtons();
    resetResultUi();
    setStatus('Sedang mengompresi video di server… Proses ini dapat memakan waktu hingga 1–2 menit, mohon jangan tutup halaman.', 'busy');

    var fd = new FormData();
    fd.append('file', state.file);
    fd.append('mode', mode);
    fd.append('preset', preset);
    if (mode === 'target') {
      fd.append('target_mb', targetMb);
    }
    fd.append('kecilkan', kecilkan);

    var startedTime = Date.now();

    fetch(serverBase + '/api/video/compress', {
      method: 'POST',
      body: fd
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(
            function (errData) {
              var message = (errData && errData.error && errData.error.message) ||
                            (errData && errData.detail) ||
                            'Gagal mengompresi video. Kode respons: ' + res.status;
              throw new Error(message);
            },
            function () {
              throw new Error('Gagal mengompresi video. Kode respons: ' + res.status);
            }
          );
        }

        var inputBytes = parseInt(res.headers.get('X-Input-Bytes'), 10) || state.file.size;
        var outputBytes = parseInt(res.headers.get('X-Output-Bytes'), 10) || 0;
        var hematPercent = parseFloat(res.headers.get('X-Hemat-Percent')) || 0.0;
        var durasiDetik = parseFloat(res.headers.get('X-Duration-Seconds')) || 0.0;
        var resolusi = res.headers.get('X-Resolution') || '-';
        var processingMs = parseInt(res.headers.get('X-Processing-Ms'), 10) || (Date.now() - startedTime);

        // Ambil nama berkas dari Content-Disposition
        var outFilename = 'video-kompres.mp4';
        var disp = res.headers.get('Content-Disposition');
        if (disp) {
          var match = /filename\*?=['"]?(?:UTF-\d['"]*)?([^;\r\n"']*)['"]?/i.exec(disp);
          if (match && match[1]) {
            outFilename = decodeURIComponent(match[1]);
          }
        }

        return res.blob().then(function (blob) {
          return {
            blob: blob,
            filename: outFilename,
            inputBytes: inputBytes,
            outputBytes: outputBytes || blob.size,
            hematPercent: hematPercent,
            durasiDetik: durasiDetik,
            resolusi: resolusi,
            processingMs: processingMs
          };
        });
      })
      .then(function (result) {
        state.busy = false;
        updateActionButtons();

        state.downloadUrl = URL.createObjectURL(result.blob);

        if (el.download) {
          el.download.href = state.downloadUrl;
          el.download.download = result.filename;
          el.download.hidden = false;
        }

        if (el.resultSavings) {
          if (result.hematPercent > 0) {
            el.resultSavings.textContent = 'Hemat ' + result.hematPercent.toFixed(1).replace('.', ',') + '%';
          } else {
            el.resultSavings.textContent = 'Ukuran optimal (0% hemat)';
          }
        }

        if (el.resultStats) {
          el.resultStats.innerHTML = '';

          var stats = [
            { label: 'Ukuran awal', val: formatBytes(result.inputBytes) },
            { label: 'Ukuran hasil', val: formatBytes(result.outputBytes) },
            { label: 'Resolusi', val: result.resolusi },
            { label: 'Waktu proses', val: (result.processingMs / 1000).toFixed(1).replace('.', ',') + ' dtk' }
          ];

          for (var i = 0; i < stats.length; i++) {
            var li = document.createElement('li');
            var strong = document.createElement('strong');
            strong.textContent = stats[i].val;
            li.appendChild(document.createTextNode(stats[i].label + ': '));
            li.appendChild(strong);
            el.resultStats.appendChild(li);
          }
        }

        if (el.resultNote) {
          if (result.hematPercent <= 0) {
            el.resultNote.textContent = 'Ukuran video asal sudah sangat efisien, sehingga berkas asli dipertahankan agar kualitas tidak turun sia-sia.';
            el.resultNote.hidden = false;
          } else {
            el.resultNote.hidden = true;
          }
        }

        if (el.result) el.result.hidden = false;

        setStatus('Kompresi selesai! Video siap diunduh.', 'success');
      })
      .catch(function (err) {
        state.busy = false;
        updateActionButtons();
        setStatus(err.message || 'Terjadi kesalahan saat menghubungi server.', 'error');
      });
  }

  // --- Buka / Tutup panel --------------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('button.tool-card__open[data-tool-action="kompres-video"]');
    triggers.forEach(function (trigger) {
      trigger.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
  }

  function open() {
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);
    panel.focus();
    loadLimits();
  }

  function close() {
    panel.hidden = true;
    syncTriggers(false);
    if (state.lastFocus && typeof state.lastFocus.focus === 'function') {
      try { state.lastFocus.focus(); } catch (e) { /* abaikan */ }
    }
  }

  function toggle() {
    if (panel.hidden) {
      open();
    } else {
      close();
    }
  }

  // --- Event listeners -----------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  if (el.pickBtn) {
    el.pickBtn.addEventListener('click', function () {
      if (el.input) el.input.click();
    });
  }

  if (el.input) {
    el.input.addEventListener('change', function () {
      if (el.input.files && el.input.files[0]) {
        handleFile(el.input.files[0]);
      }
    });
  }

  if (el.drop) {
    el.drop.addEventListener('dragover', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.add('is-dragover');
    });

    el.drop.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('is-dragover');
    });

    el.drop.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('is-dragover');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleFile(e.dataTransfer.files[0]);
      }
    });
  }

  // Toggle mode & preset
  for (var m = 0; m < el.modeRadios.length; m++) {
    el.modeRadios[m].addEventListener('change', function () {
      syncModeUi();
      resetResultUi();
    });
  }

  for (var p = 0; p < el.presetRadios.length; p++) {
    el.presetRadios[p].addEventListener('change', resetResultUi);
  }

  if (el.targetMb) {
    el.targetMb.addEventListener('input', resetResultUi);
  }

  if (el.kecilkan) {
    el.kecilkan.addEventListener('change', resetResultUi);
  }

  if (el.submit) el.submit.addEventListener('click', submitCompress);
  if (el.clear) el.clear.addEventListener('click', resetAll);

  // Esc untuk menutup walau fokus ada di luar panel
  document.addEventListener('keydown', function (e) {
    if (panel.hidden === false && (e.key === 'Escape' || e.key === 'Esc')) {
      e.preventDefault();
      close();
    }
  });

  window.addEventListener('beforeunload', function () {
    revokeDownload();
  });

  // Daftarkan panel supaya kartu "Kompres video" bisa membuka/menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['kompres-video'] = toggle;

  // Dukungan buka lewat parameter URL: ?alat=kompres-video
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      var paramAlat = params.get('alat');
      if (paramAlat !== 'kompres-video' && paramAlat !== 'video-compress') return;

      var trigger = document.querySelector('button.tool-card__open[data-tool-action="kompres-video"]');
      if (trigger) {
        trigger.click();
      } else {
        open();
      }
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
