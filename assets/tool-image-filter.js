/* =========================================================================
   Panel alat: Filter & efek gambar
   Gambar dikirim ke server lewat multipart/form-data, diproses di memori
   (Pillow), lalu hasilnya diunduh langsung. Tidak ada berkas disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('image-filter-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('image-filter-close'),
    limits: document.getElementById('image-filter-limits'),
    drop: document.getElementById('image-filter-drop'),
    input: document.getElementById('image-filter-input'),
    empty: document.getElementById('image-filter-empty'),
    origWrap: document.getElementById('image-filter-orig-wrap'),
    origImg: document.getElementById('image-filter-orig-img'),
    filename: document.getElementById('image-filter-filename'),
    origMeta: document.getElementById('image-filter-orig-meta'),
    controls: document.getElementById('image-filter-controls'),
    presets: document.getElementById('image-filter-presets'),
    kecerahan: document.getElementById('image-filter-kecerahan'),
    kecerahanVal: document.getElementById('image-filter-kecerahan-val'),
    kontras: document.getElementById('image-filter-kontras'),
    kontrasVal: document.getElementById('image-filter-kontras-val'),
    saturasi: document.getElementById('image-filter-saturasi'),
    saturasiVal: document.getElementById('image-filter-saturasi-val'),
    blur: document.getElementById('image-filter-blur'),
    blurVal: document.getElementById('image-filter-blur-val'),
    vignette: document.getElementById('image-filter-vignette'),
    vignetteVal: document.getElementById('image-filter-vignette-val'),
    resetAdjust: document.getElementById('image-filter-reset-adjust'),
    format: document.getElementById('image-filter-format'),
    qualityField: document.getElementById('image-filter-quality-field'),
    kualitas: document.getElementById('image-filter-kualitas'),
    qualityVal: document.getElementById('image-filter-quality-val'),
    result: document.getElementById('image-filter-result'),
    resultImg: document.getElementById('image-filter-result-img'),
    resultMeta: document.getElementById('image-filter-result-meta'),
    status: document.getElementById('image-filter-status'),
    clear: document.getElementById('image-filter-clear'),
    submit: document.getElementById('image-filter-submit'),
    download: document.getElementById('image-filter-download')
  };

  var FALLBACK_LIMITS = {
    max_mb: 15,
    max_bytes: 15728640,
    max_pixels: 40000000,
    max_side: 12000,
    presets: [
      { id: 'asli', label: 'Asli' },
      { id: 'hitam-putih', label: 'Hitam putih' },
      { id: 'sepia', label: 'Sepia' },
      { id: 'pudar', label: 'Pudar' },
      { id: 'hangat', label: 'Hangat' },
      { id: 'dingin', label: 'Dingin' }
    ],
    quality: {
      min: 10,
      max: 100,
      default: 90
    }
  };

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    file: null,
    origUrl: null,
    origWidth: null,
    origHeight: null,
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    busy: false,
    downloadUrl: null,
    lastFocus: null,
    suasana: 'asli'
  };

  // --- Pembantu -----------------------------------------------------------
  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1).replace('.', ',') + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2).replace('.', ',') + ' MB';
  }

  function formatLabel(kode) {
    var raw = (kode || '').toLowerCase();
    var map = {
      png: 'PNG',
      jpeg: 'JPG',
      jpg: 'JPG',
      webp: 'WebP'
    };
    return map[raw] || kode || '';
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

  function revokeOrigPreview() {
    if (state.origUrl) {
      try { URL.revokeObjectURL(state.origUrl); } catch (err) { /* diabaikan */ }
      state.origUrl = null;
    }
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      try { URL.revokeObjectURL(state.downloadUrl); } catch (err) { /* diabaikan */ }
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
    if (el.resultImg) {
      el.resultImg.src = '';
    }
    if (el.resultMeta) {
      el.resultMeta.textContent = '';
    }
  }

  function updateControls() {
    var hasFile = !!state.file;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasFile;
      el.submit.textContent = state.busy ? 'Memproses…' : 'Terapkan filter';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || !hasFile;
    }
  }

  function updateQualityVisibility() {
    if (!el.qualityField || !el.format) return;
    var fmt = el.format.value;
    if (fmt === 'png') {
      el.qualityField.hidden = true;
    } else if (fmt === 'jpeg' || fmt === 'webp') {
      el.qualityField.hidden = false;
    } else if (fmt === 'tetap') {
      var nameLower = (state.file && state.file.name ? state.file.name : '').toLowerCase();
      var isPng = (state.file && state.file.type === 'image/png') || nameLower.endsWith('.png');
      el.qualityField.hidden = isPng;
    }
  }

  function onControlChange() {
    if (state.downloadUrl) {
      resetResultUi();
      setStatus('Pengaturan berubah, tekan Terapkan filter lagi.', '');
    }
  }

  // --- Rendering chip suasana ---------------------------------------------
  function renderPresets(presetsList) {
    if (!el.presets) return;
    el.presets.innerHTML = '';
    var list = presetsList || FALLBACK_LIMITS.presets;
    list.forEach(function (preset) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chip' + (state.suasana === preset.id ? ' chip--active' : '');
      btn.textContent = preset.label;
      btn.dataset.presetId = preset.id;
      btn.setAttribute('aria-pressed', state.suasana === preset.id ? 'true' : 'false');
      btn.addEventListener('click', function () {
        if (state.suasana === preset.id) return;
        state.suasana = preset.id;
        var allChips = el.presets.querySelectorAll('.chip');
        allChips.forEach(function (c) {
          var active = (c.dataset.presetId === preset.id);
          c.classList.toggle('chip--active', active);
          c.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        onControlChange();
      });
      el.presets.appendChild(btn);
    });
  }

  // --- Aturan dari server -------------------------------------------------
  function describeLimits(online) {
    if (!el.limits) return;
    var mb = state.limits.max_mb || FALLBACK_LIMITS.max_mb;
    var text = 'Maks 1 berkas, total ' + mb + ' MB (PNG, JPG, atau WebP)';
    el.limits.textContent = text + (online ? ', aturan dari server' : ', aturan bawaan');
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/image/filter/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
          max_bytes: (data.max_mb ? data.max_mb * 1024 * 1024 : FALLBACK_LIMITS.max_bytes),
          max_pixels: data.max_pixels || FALLBACK_LIMITS.max_pixels,
          max_side: data.max_side || FALLBACK_LIMITS.max_side,
          presets: data.presets || FALLBACK_LIMITS.presets,
          quality: data.quality || FALLBACK_LIMITS.quality
        };
        state.limitsLoaded = true;
        describeLimits(true);
        renderPresets(state.limits.presets);
      })
      .catch(function () {
        describeLimits(false);
        renderPresets(FALLBACK_LIMITS.presets);
      });
  }

  // --- Pemilihan berkas ---------------------------------------------------
  function handleFile(file) {
    if (!file) return;

    var validTypes = ['image/png', 'image/jpeg', 'image/webp'];
    var nameLower = (file.name || '').toLowerCase();
    var hasValidExt = nameLower.endsWith('.png') || nameLower.endsWith('.jpg') ||
                      nameLower.endsWith('.jpeg') || nameLower.endsWith('.webp');

    if (validTypes.indexOf(file.type) === -1 && !hasValidExt) {
      setStatus('Berkas bukan gambar yang didukung. Pilih berkas PNG, JPG, atau WebP.', 'error');
      return;
    }

    var maxByteSize = state.limits.max_bytes || FALLBACK_LIMITS.max_bytes;
    if (file.size > maxByteSize) {
      var limitMb = state.limits.max_mb || FALLBACK_LIMITS.max_mb;
      setStatus('Ukuran gambar ' + formatBytes(file.size) + ' melebihi batas ' + limitMb + ' MB.', 'error');
      return;
    }

    resetResultUi();
    revokeOrigPreview();
    state.file = file;
    state.origUrl = URL.createObjectURL(file);

    if (el.origImg) {
      el.origImg.src = state.origUrl;
    }
    if (el.filename) {
      el.filename.textContent = file.name || 'Gambar';
    }
    if (el.origMeta) {
      el.origMeta.textContent = formatBytes(file.size);
    }

    var imgProbe = new Image();
    imgProbe.onload = function () {
      state.origWidth = imgProbe.naturalWidth || imgProbe.width;
      state.origHeight = imgProbe.naturalHeight || imgProbe.height;
      if (el.origMeta) {
        el.origMeta.textContent = state.origWidth + ' × ' + state.origHeight + ' piksel · ' + formatBytes(file.size);
      }
    };
    imgProbe.src = state.origUrl;

    if (el.origWrap) el.origWrap.hidden = false;
    if (el.controls) el.controls.hidden = false;
    if (el.empty) el.empty.hidden = true;

    updateQualityVisibility();
    updateControls();
    setStatus('Gambar dipilih. Tentukan suasana dan penyetelan lalu tekan "Terapkan filter".', '');
  }

  // --- Reset pengaturan ---------------------------------------------------
  function resetAdjustments() {
    state.suasana = 'asli';
    if (el.presets) {
      var allChips = el.presets.querySelectorAll('.chip');
      allChips.forEach(function (c) {
        var active = (c.dataset.presetId === 'asli');
        c.classList.toggle('chip--active', active);
        c.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
    }

    if (el.kecerahan) el.kecerahan.value = '0';
    if (el.kecerahanVal) el.kecerahanVal.textContent = '0';

    if (el.kontras) el.kontras.value = '0';
    if (el.kontrasVal) el.kontrasVal.textContent = '0';

    if (el.saturasi) el.saturasi.value = '0';
    if (el.saturasiVal) el.saturasiVal.textContent = '0';

    if (el.blur) el.blur.value = '0';
    if (el.blurVal) el.blurVal.textContent = '0';

    if (el.vignette) el.vignette.value = '0';
    if (el.vignetteVal) el.vignetteVal.textContent = '0';

    onControlChange();
  }

  function resetAll() {
    state.file = null;
    state.busy = false;
    state.origWidth = null;
    state.origHeight = null;

    resetResultUi();
    revokeOrigPreview();

    if (el.origWrap) el.origWrap.hidden = true;
    if (el.controls) el.controls.hidden = true;
    if (el.empty) el.empty.hidden = false;
    if (el.input) el.input.value = '';

    resetAdjustments();

    if (el.format) el.format.value = 'tetap';

    var defQuality = (state.limits.quality && state.limits.quality.default) || FALLBACK_LIMITS.quality.default;
    if (el.kualitas) el.kualitas.value = String(defQuality);
    if (el.qualityVal) el.qualityVal.textContent = String(defQuality);

    updateQualityVisibility();
    updateControls();
    setStatus('Panel dikosongkan. Pilih berkas gambar PNG, JPG, atau WebP untuk mulai menerapkan filter.', '');
  }

  // --- Kirim dan proses ---------------------------------------------------
  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) {
          message = parsed.error.message;
        }
      } catch (err) { /* respons bukan JSON */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan filter gambar belum tersambung ke server. Coba lagi nanti.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function downloadFilename(response, targetFmt) {
    var disposition = response.headers.get('Content-Disposition') || '';
    var match = /filename="?([^";]+)"?/.exec(disposition);
    if (match && match[1]) return match[1];
    var ext = targetFmt === 'png' ? 'png' : (targetFmt === 'webp' ? 'webp' : 'jpg');
    return 'hasil-filter.' + ext;
  }

  function submitFilter() {
    if (state.busy || !state.file) return;

    var suasanaVal = state.suasana || 'asli';
    var kecerahanVal = el.kecerahan ? el.kecerahan.value : '0';
    var kontrasVal = el.kontras ? el.kontras.value : '0';
    var saturasiVal = el.saturasi ? el.saturasi.value : '0';
    var blurVal = el.blur ? el.blur.value : '0';
    var vignetteVal = el.vignette ? el.vignette.value : '0';
    var formatVal = el.format ? el.format.value : 'tetap';
    var kualitasVal = el.kualitas ? el.kualitas.value : '90';

    var form = new FormData();
    form.append('file', state.file, state.file.name);
    form.append('suasana', suasanaVal);
    form.append('kecerahan', kecerahanVal);
    form.append('kontras', kontrasVal);
    form.append('saturasi', saturasiVal);
    form.append('blur', blurVal);
    form.append('vignette', vignetteVal);
    form.append('format', formatVal);
    form.append('kualitas', kualitasVal);

    state.busy = true;
    updateControls();
    resetResultUi();
    setStatus('Sedang memproses gambar…', 'busy');

    fetch(serverBase + '/api/image/filter', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.blob().then(function (blob) {
          return {
            blob: blob,
            filename: downloadFilename(response, formatVal),
            inFmt: response.headers.get('X-Input-Format'),
            outFmt: response.headers.get('X-Output-Format'),
            width: response.headers.get('X-Image-Width'),
            height: response.headers.get('X-Image-Height'),
            pixels: response.headers.get('X-Pixels'),
            processingMs: response.headers.get('X-Processing-Ms')
          };
        });
      })
      .then(function (res) {
        state.downloadUrl = URL.createObjectURL(res.blob);
        if (el.resultImg) {
          el.resultImg.src = state.downloadUrl;
        }

        var outLabel = formatLabel(res.outFmt || formatVal);
        var sizeText = formatBytes(res.blob.size);
        var dimText = (res.width && res.height) ? (res.width + ' × ' + res.height + ' piksel · ') : '';
        var durText = res.processingMs ? (' · ' + res.processingMs + ' ms') : '';

        if (el.resultMeta) {
          el.resultMeta.textContent = dimText + sizeText + ' · ' + outLabel + durText;
        }
        if (el.result) {
          el.result.hidden = false;
        }

        if (el.download) {
          el.download.href = state.downloadUrl;
          el.download.download = res.filename;
          el.download.hidden = false;
        }

        var msg = 'Selesai: ' + dimText + sizeText + ' · ' + outLabel + '. Tekan "Unduh hasil" untuk menyimpan berkas.';
        setStatus(msg, 'ok');
      })
      .catch(function (error) {
        var msg = (error && error.pesanLayanan === true && error.message)
          ? error.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
      })
      .then(function () {
        state.busy = false;
        updateControls();
      });
  }

  // --- Buka dan tutup panel -----------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="image-filter"]');
    triggers.forEach(function (trigger) {
      trigger.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
  }

  function open() {
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (panel.hidden) {
      state.lastFocus = document.activeElement;
      panel.hidden = false;
      loadLimits();
      describeLimits(state.limitsLoaded);
      syncTriggers(true);
      panel.focus({ preventScroll: true });
      if (!state.file) {
        setStatus('Pilih berkas gambar PNG, JPG, atau WebP untuk mulai menerapkan filter.');
      }
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

  // --- Pemasangan event ---------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('change', function () {
      if (el.input.files && el.input.files[0]) {
        handleFile(el.input.files[0]);
      }
      el.input.value = '';
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
      el.drop.addEventListener(type, function () {
        el.drop.classList.remove('is-dragover');
      });
    });
    el.drop.addEventListener('drop', function (event) {
      event.preventDefault();
      el.drop.classList.remove('is-dragover');
      if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
        handleFile(event.dataTransfer.files[0]);
      }
    });
  }

  function bindSlider(sliderEl, displayEl) {
    if (!sliderEl) return;
    sliderEl.addEventListener('input', function () {
      if (displayEl) {
        displayEl.textContent = sliderEl.value;
      }
      onControlChange();
    });
  }

  bindSlider(el.kecerahan, el.kecerahanVal);
  bindSlider(el.kontras, el.kontrasVal);
  bindSlider(el.saturasi, el.saturasiVal);
  bindSlider(el.blur, el.blurVal);
  bindSlider(el.vignette, el.vignetteVal);

  if (el.resetAdjust) {
    el.resetAdjust.addEventListener('click', resetAdjustments);
  }

  if (el.format) {
    el.format.addEventListener('change', function () {
      updateQualityVisibility();
      onControlChange();
    });
  }

  if (el.kualitas) {
    el.kualitas.addEventListener('input', function () {
      if (el.qualityVal) {
        el.qualityVal.textContent = el.kualitas.value;
      }
      onControlChange();
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitFilter);
  if (el.clear) el.clear.addEventListener('click', resetAll);

  window.addEventListener('beforeunload', function () {
    revokeOrigPreview();
    revokeDownload();
  });

  // Render chip suasana bawaan jika belum ter-load dari API
  renderPresets(FALLBACK_LIMITS.presets);

  // Daftarkan panel supaya kartu "Filter & efek gambar" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['image-filter'] = toggle;

  // Dukungan buka lewat parameter URL: ?alat=filter-gambar
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      var paramAlat = params.get('alat');
      if (paramAlat !== 'filter-gambar' && paramAlat !== 'image-filter') return;

      var trigger = document.querySelector('button.tool-card__open[data-tool-action="image-filter"]');
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
