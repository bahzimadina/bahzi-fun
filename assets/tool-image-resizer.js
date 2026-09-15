/* =========================================================================
   Panel alat: Ubah ukuran gambar
   Semua proses (baca dimensi, gambar ulang, encode) terjadi di perangkat
   pengunjung lewat <canvas>. Tidak ada berkas yang dikirim ke mana pun.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman (mengikuti pola panel Gabung PDF).
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('image-resizer-panel');
  if (!panel) return;

  var MAX_DIM = 8000;

  var el = {
    close: document.getElementById('image-resizer-close'),
    input: document.getElementById('image-resizer-input'),
    drop: document.getElementById('image-resizer-drop'),
    empty: document.getElementById('image-resizer-empty'),
    info: document.getElementById('image-resizer-info'),
    filename: document.getElementById('image-resizer-filename'),
    originalMeta: document.getElementById('image-resizer-original-meta'),
    controls: document.getElementById('image-resizer-controls'),
    width: document.getElementById('image-resizer-width'),
    height: document.getElementById('image-resizer-height'),
    ratio: document.getElementById('image-resizer-ratio'),
    presets: panel.querySelectorAll('.imgres__presets [data-percent]'),
    format: document.getElementById('image-resizer-format'),
    qualityField: document.getElementById('image-resizer-quality-field'),
    quality: document.getElementById('image-resizer-quality'),
    qualityValue: document.getElementById('image-resizer-quality-value'),
    result: document.getElementById('image-resizer-result'),
    resultMeta: document.getElementById('image-resizer-result-meta'),
    status: document.getElementById('image-resizer-status'),
    submit: document.getElementById('image-resizer-submit'),
    clear: document.getElementById('image-resizer-clear'),
    download: document.getElementById('image-resizer-download')
  };

  var state = {
    file: null,
    img: null,
    originalWidth: 0,
    originalHeight: 0,
    ratio: null,
    busy: false,
    downloadUrl: null,
    lastFocus: null
  };

  // --- Pembantu -----------------------------------------------------------
  function clampVal(n) {
    if (!isFinite(n) || n <= 0) return 1;
    return Math.max(1, Math.min(MAX_DIM, Math.round(n)));
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1).replace('.', ',') + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2).replace('.', ',') + ' MB';
  }

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

  function updateControls() {
    var hasImage = !!state.img;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasImage;
      el.submit.textContent = state.busy ? 'Memproses…' : 'Ubah ukuran';
    }
    if (el.clear) el.clear.disabled = state.busy || !state.file;
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      try { URL.revokeObjectURL(state.downloadUrl); } catch (err) { /* diabaikan */ }
      state.downloadUrl = null;
    }
  }

  // --- Format hasil & kualitas ---------------------------------------------
  function resolveOutputMime() {
    var choice = el.format ? el.format.value : 'same';
    if (choice !== 'same') return choice;
    var srcType = state.file ? state.file.type : '';
    if (srcType === 'image/jpeg' || srcType === 'image/png' || srcType === 'image/webp') return srcType;
    return 'image/png'; // GIF (dan tipe tak dikenal) dikeluarkan sebagai PNG: canvas tak bisa menulis GIF
  }

  function updateQualityVisibility() {
    if (!el.qualityField) return;
    var mime = resolveOutputMime();
    el.qualityField.hidden = !(mime === 'image/jpeg' || mime === 'image/webp');
  }

  // --- Dimensi & pintasan persentase --------------------------------------
  function applyPercent(pct) {
    if (!state.originalWidth || !state.originalHeight) return;
    var rawW = state.originalWidth * pct / 100;
    var rawH = state.originalHeight * pct / 100;
    var w = clampVal(rawW);
    var h = clampVal(rawH);
    if (el.width) el.width.value = String(w);
    if (el.height) el.height.value = String(h);
    if (rawW > MAX_DIM || rawH > MAX_DIM) {
      setStatus('Ukuran maksimal ' + MAX_DIM + ' px, nilai disesuaikan.', '');
    }
  }

  function onWidthInput() {
    var w = parseFloat(el.width.value);
    if (!isFinite(w) || w <= 0 || !state.ratio) return;
    if (el.ratio && el.ratio.checked) {
      el.height.value = String(clampVal(w / state.ratio));
    }
  }

  function onHeightInput() {
    var h = parseFloat(el.height.value);
    if (!isFinite(h) || h <= 0 || !state.ratio) return;
    if (el.ratio && el.ratio.checked) {
      el.width.value = String(clampVal(h * state.ratio));
    }
  }

  function finalizeDim(self, other, isWidth) {
    var v = parseFloat(self.value);
    if (!isFinite(v) || v <= 0) {
      v = isWidth ? state.originalWidth : state.originalHeight;
    }
    var clamped = clampVal(v);
    var wasClamped = clamped !== Math.round(v);
    self.value = String(clamped);
    if (el.ratio && el.ratio.checked && state.ratio) {
      var otherRaw = isWidth ? (clamped / state.ratio) : (clamped * state.ratio);
      other.value = String(clampVal(otherRaw));
    }
    if (wasClamped) setStatus('Ukuran maksimal ' + MAX_DIM + ' px, nilai disesuaikan.', '');
  }

  // --- Pemilihan berkas ----------------------------------------------------
  function fillInfo() {
    if (el.filename) el.filename.textContent = state.file.name || 'Gambar';
    if (el.originalMeta) {
      el.originalMeta.textContent = state.originalWidth + ' × ' + state.originalHeight + ' px · ' + formatBytes(state.file.size);
    }
  }

  function resetResultUi() {
    revokeDownload();
    if (el.download) el.download.hidden = true;
    if (el.result) el.result.hidden = true;
  }

  function handleFile(file) {
    if (!file || file.type.indexOf('image/') !== 0) {
      setStatus('Berkas yang dipilih bukan gambar. Pilih berkas JPG, PNG, WebP, atau GIF.', 'error');
      return;
    }

    resetResultUi();

    var url;
    try {
      url = URL.createObjectURL(file);
    } catch (err) {
      setStatus('Gagal membaca berkas gambar ini.', 'error');
      return;
    }

    var img = new Image();
    img.onload = function () {
      URL.revokeObjectURL(url);
      state.file = file;
      state.img = img;
      state.originalWidth = img.naturalWidth;
      state.originalHeight = img.naturalHeight;
      state.ratio = state.originalWidth / state.originalHeight;

      fillInfo();
      if (el.format) el.format.value = 'same';
      if (el.quality) el.quality.value = '85';
      if (el.qualityValue) el.qualityValue.textContent = '85';
      if (el.ratio) el.ratio.checked = true;
      applyPercent(100);
      updateQualityVisibility();

      if (el.controls) el.controls.hidden = false;
      if (el.info) el.info.hidden = false;
      if (el.empty) el.empty.hidden = true;
      setStatus('Gambar dimuat. Atur ukurannya, lalu tekan "Ubah ukuran".', '');
      updateControls();
    };
    img.onerror = function () {
      URL.revokeObjectURL(url);
      setStatus('Gagal membaca berkas gambar ini. Coba berkas lain.', 'error');
    };
    img.src = url;
  }

  // --- Proses ubah ukuran ---------------------------------------------------
  function submitResize() {
    if (state.busy || !state.img) return;

    var targetW = clampVal(parseFloat(el.width.value) || state.originalWidth);
    var targetH = clampVal(parseFloat(el.height.value) || state.originalHeight);

    state.busy = true;
    updateControls();
    resetResultUi();
    setStatus('Memproses gambar…', 'busy');

    // setTimeout memberi ruang ke browser untuk menggambar ulang tombol
    // nonaktif sebelum canvas mengunci thread utama sejenak.
    window.setTimeout(function () {
      var blobDone = function (blob) {
        state.busy = false;
        if (!blob) {
          setStatus('Gagal memproses gambar ini. Coba format lain.', 'error');
          updateControls();
          return;
        }

        revokeDownload();
        state.downloadUrl = URL.createObjectURL(blob);
        var mime = resolveOutputMime();
        var ext = mime === 'image/png' ? 'png' : (mime === 'image/webp' ? 'webp' : 'jpg');
        var baseName = (state.file.name || 'gambar').replace(/\.[^./\\]+$/, '');

        if (el.download) {
          el.download.href = state.downloadUrl;
          el.download.download = baseName + '-resize.' + ext;
          el.download.hidden = false;
        }

        var origSize = state.file.size;
        var newSize = blob.size;
        var pct = origSize > 0 ? Math.round((1 - newSize / origSize) * 100) : 0;
        var diffText = pct >= 0 ? ('menghemat ' + pct + '%') : ('bertambah ' + Math.abs(pct) + '% dari ukuran asli');
        if (pct >= 0) diffText += ' dari ukuran asli';

        if (el.resultMeta) {
          el.resultMeta.textContent = targetW + ' × ' + targetH + ' px · ' + formatBytes(newSize) + ' (' + diffText + ')';
        }
        if (el.result) el.result.hidden = false;
        setStatus('Selesai. Tekan "Unduh hasil" untuk menyimpan gambar.', 'ok');
        updateControls();
        if (el.download) el.download.focus();
      };

      try {
        var canvas = document.createElement('canvas');
        canvas.width = targetW;
        canvas.height = targetH;
        var ctx = canvas.getContext('2d');
        ctx.drawImage(state.img, 0, 0, targetW, targetH);
        var mime = resolveOutputMime();
        var supportsQuality = mime === 'image/jpeg' || mime === 'image/webp';
        var quality = supportsQuality ? (parseInt(el.quality.value, 10) / 100) : undefined;
        canvas.toBlob(blobDone, mime, quality);
      } catch (err) {
        state.busy = false;
        setStatus('Gagal memproses gambar di perangkat ini.', 'error');
        updateControls();
      }
    }, 20);
  }

  // --- Kosongkan -------------------------------------------------------------
  function resetAll() {
    state.file = null;
    state.img = null;
    state.originalWidth = 0;
    state.originalHeight = 0;
    state.ratio = null;
    state.busy = false;

    resetResultUi();
    if (el.controls) el.controls.hidden = true;
    if (el.info) el.info.hidden = true;
    if (el.empty) el.empty.hidden = false;
    if (el.width) el.width.value = '';
    if (el.height) el.height.value = '';
    if (el.ratio) el.ratio.checked = true;
    if (el.format) el.format.value = 'same';
    if (el.quality) el.quality.value = '85';
    if (el.qualityValue) el.qualityValue.textContent = '85';
    if (el.qualityField) el.qualityField.hidden = false;
    updateControls();
  }

  // --- Buka / tutup panel ------------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="image-resizer"]');
    triggers.forEach(function (trigger) {
      trigger.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
  }

  function open() {
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (panel.hidden) {
      state.lastFocus = document.activeElement;
      panel.hidden = false;
      syncTriggers(true);
      panel.focus({ preventScroll: true });
    }
    panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    resetResultUi();
    syncTriggers(false);
    if (state.lastFocus && typeof state.lastFocus.focus === 'function' && document.contains(state.lastFocus)) {
      state.lastFocus.focus();
    }
    state.lastFocus = null;
  }

  function toggle() {
    if (panel.hidden) open(); else close();
  }

  function onKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape' && panel.contains(document.activeElement)) {
      event.preventDefault();
      close();
    }
  }

  // --- Pemasangan event --------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('change', function () {
      if (el.input.files && el.input.files[0]) handleFile(el.input.files[0]);
      el.input.value = ''; // supaya berkas yang sama bisa dipilih ulang
    });
  }

  if (el.drop) {
    ['dragenter', 'dragover'].forEach(function (type) {
      el.drop.addEventListener(type, function (event) {
        event.preventDefault();
        el.drop.classList.add('is-dragover');
      });
    });
    ['dragleave', 'dragend'].forEach(function (type) {
      el.drop.addEventListener(type, function () { el.drop.classList.remove('is-dragover'); });
    });
    el.drop.addEventListener('drop', function (event) {
      event.preventDefault();
      el.drop.classList.remove('is-dragover');
      if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
        handleFile(event.dataTransfer.files[0]);
      }
    });
  }

  if (el.width) {
    el.width.addEventListener('input', onWidthInput);
    el.width.addEventListener('change', function () { finalizeDim(el.width, el.height, true); });
  }
  if (el.height) {
    el.height.addEventListener('input', onHeightInput);
    el.height.addEventListener('change', function () { finalizeDim(el.height, el.width, false); });
  }

  if (el.presets && el.presets.forEach) {
    el.presets.forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyPercent(parseInt(btn.dataset.percent, 10));
      });
    });
  }

  if (el.format) el.format.addEventListener('change', updateQualityVisibility);
  if (el.quality) {
    el.quality.addEventListener('input', function () {
      if (el.qualityValue) el.qualityValue.textContent = el.quality.value;
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitResize);
  if (el.clear) {
    el.clear.addEventListener('click', function () {
      resetAll();
      setStatus('Panel dikosongkan. Pilih gambar untuk mulai lagi.', '');
    });
  }

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel supaya kartu "Image Resizer" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['image-resizer'] = toggle;
})();
