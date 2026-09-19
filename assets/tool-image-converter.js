/* =========================================================================
   Panel alat: Konversi gambar
   Gambar dikirim ke server lewat multipart/form-data, dikonversi di memori
   (Pillow), lalu hasilnya diunduh langsung. Tidak ada berkas disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('image-converter-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('image-converter-close'),
    limits: document.getElementById('image-converter-limits'),
    drop: document.getElementById('image-converter-drop'),
    input: document.getElementById('image-converter-input'),
    empty: document.getElementById('image-converter-empty'),
    info: document.getElementById('image-converter-info'),
    filename: document.getElementById('image-converter-filename'),
    meta: document.getElementById('image-converter-meta'),
    controls: document.getElementById('image-converter-controls'),
    format: document.getElementById('image-converter-format'),
    qualityField: document.getElementById('image-converter-quality-field'),
    quality: document.getElementById('image-converter-quality'),
    qualityValue: document.getElementById('image-converter-quality-value'),
    widthField: null,
    width: null,
    status: document.getElementById('image-converter-status'),
    clear: document.getElementById('image-converter-clear'),
    submit: document.getElementById('image-converter-submit'),
    download: document.getElementById('image-converter-download')
  };

  var FALLBACK_LIMITS = {
    max_files: 1,
    max_total_mb: 15,
    max_bytes: 15728640,
    quality_min: 10,
    quality_max: 100,
    quality_default: 85,
    svgMaxWidth: 4000,
    svgDefaultWidth: 1024
  };

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    file: null,
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    busy: false,
    downloadUrl: null,
    lastFocus: null
  };

  // --- Pembantu -----------------------------------------------------------
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
  }

  function updateControls() {
    var hasFile = !!state.file;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasFile;
      el.submit.textContent = state.busy ? 'Mengonversi…' : 'Konversi gambar';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || !hasFile;
    }
  }

  function updateQualityVisibility() {
    if (!el.qualityField || !el.format) return;
    var fmt = el.format.value;
    // Format PNG tidak memakai kualitas kompresi lossy
    el.qualityField.hidden = (fmt === 'png');
  }

  function isSvgFile(file) {
    if (!file) return false;
    if (file.type === 'image/svg+xml') return true;
    return /\.svg$/i.test(file.name || '');
  }

  // --- Kolom "Lebar hasil (px)" — hanya tampil & relevan untuk masukan SVG --
  function buildWidthField() {
    if (el.widthField || !el.controls) return;
    var row = el.controls.querySelector('.imgres__row');
    if (!row) return;

    var field = document.createElement('div');
    field.className = 'field';
    field.id = 'image-converter-width-field';
    field.hidden = true;

    var label = document.createElement('label');
    label.setAttribute('for', 'image-converter-width');
    label.textContent = 'Lebar hasil (px)';

    var input = document.createElement('input');
    input.type = 'number';
    input.id = 'image-converter-width';
    input.inputMode = 'numeric';
    input.min = '16';
    input.max = String(state.limits.svgMaxWidth || FALLBACK_LIMITS.svgMaxWidth);
    input.placeholder = 'Ukuran asli';

    field.appendChild(label);
    field.appendChild(input);
    row.appendChild(field);

    el.widthField = field;
    el.width = input;
  }

  function updateWidthVisibility() {
    if (!el.widthField) return;
    el.widthField.hidden = !isSvgFile(state.file);
  }

  // --- Aturan dari server -------------------------------------------------
  function describeLimits(online) {
    if (!el.limits) return;
    var mb = state.limits.max_total_mb || FALLBACK_LIMITS.max_total_mb;
    var text = 'Maks 1 berkas, total ' + mb + ' MB (PNG, JPG, WebP, atau SVG)';
    el.limits.textContent = text + (online ? ', aturan dari server' : ', aturan bawaan');
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/image/convert/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_files: data.max_files || FALLBACK_LIMITS.max_files,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_total_mb: data.max_total_mb || FALLBACK_LIMITS.max_total_mb,
          quality_min: data.quality_min || FALLBACK_LIMITS.quality_min,
          quality_max: data.quality_max || FALLBACK_LIMITS.quality_max,
          quality_default: data.quality_default || FALLBACK_LIMITS.quality_default,
          svgMaxWidth: data.svgMaxWidth || FALLBACK_LIMITS.svgMaxWidth,
          svgDefaultWidth: data.svgDefaultWidth || FALLBACK_LIMITS.svgDefaultWidth
        };
        state.limitsLoaded = true;
        if (el.width) el.width.max = String(state.limits.svgMaxWidth);
        describeLimits(true);
      })
      .catch(function () {
        describeLimits(false);
      });
  }

  // --- Pemilihan berkas ---------------------------------------------------
  function handleFile(file) {
    if (!file) return;

    var validTypes = ['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml'];
    var nameLower = (file.name || '').toLowerCase();
    var hasValidExt = nameLower.endsWith('.png') || nameLower.endsWith('.jpg') ||
                      nameLower.endsWith('.jpeg') || nameLower.endsWith('.webp') ||
                      nameLower.endsWith('.svg');

    if (validTypes.indexOf(file.type) === -1 && !hasValidExt) {
      setStatus('Berkas bukan gambar yang didukung. Pilih berkas PNG, JPG, WebP, atau SVG.', 'error');
      return;
    }

    var maxByteSize = state.limits.max_bytes || FALLBACK_LIMITS.max_bytes;
    if (file.size > maxByteSize) {
      var limitMb = state.limits.max_total_mb || FALLBACK_LIMITS.max_total_mb;
      setStatus('Ukuran gambar ' + formatBytes(file.size) + ' melebihi batas ' + limitMb + ' MB.', 'error');
      return;
    }

    resetResultUi();
    state.file = file;

    if (el.filename) el.filename.textContent = file.name || 'Gambar';
    if (el.meta) el.meta.textContent = formatBytes(file.size);

    if (el.info) el.info.hidden = false;
    if (el.controls) el.controls.hidden = false;
    if (el.empty) el.empty.hidden = true;

    updateQualityVisibility();
    updateWidthVisibility();
    updateControls();
    setStatus('Gambar dipilih. Tentukan format tujuan lalu tekan "Konversi gambar".', '');
  }

  // --- Reset --------------------------------------------------------------
  function resetAll() {
    state.file = null;
    state.busy = false;

    resetResultUi();
    if (el.info) el.info.hidden = true;
    if (el.controls) el.controls.hidden = true;
    if (el.empty) el.empty.hidden = false;
    if (el.input) el.input.value = '';

    if (el.format) el.format.value = 'jpeg';
    var defQuality = state.limits.quality_default || FALLBACK_LIMITS.quality_default;
    if (el.quality) el.quality.value = String(defQuality);
    if (el.qualityValue) el.qualityValue.textContent = String(defQuality);
    if (el.width) el.width.value = '';
    updateQualityVisibility();
    updateWidthVisibility();
    updateControls();
    setStatus('Panel dikosongkan. Pilih gambar untuk mulai konversi.', '');
  }

  // --- Kirim dan konversi -------------------------------------------------
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
          message = 'Layanan konversi belum tersambung ke server. Coba lagi nanti.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }
      throw new Error(message);
    });
  }

  function downloadFilename(response, targetFmt) {
    var disposition = response.headers.get('Content-Disposition') || '';
    var match = /filename="?([^";]+)"?/.exec(disposition);
    if (match && match[1]) return match[1];
    var ext = targetFmt === 'png' ? 'png' : (targetFmt === 'webp' ? 'webp' : 'jpg');
    return 'hasil.' + ext;
  }

  function submitConvert() {
    if (state.busy || !state.file) return;

    var targetFmt = el.format ? el.format.value : 'jpeg';
    var qualityVal = el.quality ? el.quality.value : '85';
    var svgInput = isSvgFile(state.file);
    var widthVal = (svgInput && el.width) ? el.width.value.trim() : '';

    if (widthVal) {
      var widthNum = parseInt(widthVal, 10);
      var minW = 16;
      var maxW = state.limits.svgMaxWidth || FALLBACK_LIMITS.svgMaxWidth;
      if (!/^\d+$/.test(widthVal) || widthNum < minW || widthNum > maxW) {
        setStatus('Lebar hasil harus berupa angka bulat antara ' + minW + ' dan ' + maxW + ' piksel.', 'error');
        return;
      }
    }

    var form = new FormData();
    form.append('files', state.file, state.file.name);
    form.append('format', targetFmt);
    if (targetFmt !== 'png') {
      form.append('quality', qualityVal);
    }
    if (widthVal) {
      form.append('width', widthVal);
    }

    state.busy = true;
    updateControls();
    resetResultUi();
    setStatus('Mengirim gambar ke server dan memproses konversi…', 'busy');

    fetch(serverBase + '/api/image/convert', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.blob().then(function (blob) {
          return {
            blob: blob,
            filename: downloadFilename(response, targetFmt),
            inFmt: response.headers.get('X-Input-Format'),
            outFmt: response.headers.get('X-Output-Format'),
            pixels: response.headers.get('X-Pixels'),
            processingMs: response.headers.get('X-Processing-Ms'),
            scaledDown: response.headers.get('X-Scaled-Down') === 'true'
          };
        });
      })
      .then(function (res) {
        state.downloadUrl = URL.createObjectURL(res.blob);
        if (el.download) {
          el.download.href = state.downloadUrl;
          el.download.download = res.filename;
          el.download.hidden = false;
        }

        var inLabel = (res.inFmt || 'gambar').toUpperCase();
        var outLabel = (res.outFmt || targetFmt).toUpperCase();
        if (outLabel === 'JPEG') outLabel = 'JPG';

        var sizeText = formatBytes(res.blob.size);
        var msg = 'Selesai: ' + inLabel + ' → ' + outLabel + ' (' + sizeText + '). Tekan "Unduh hasil" untuk menyimpan berkas.';
        if (res.scaledDown) {
          msg += ' Catatan: ukuran hasil diperkecil otomatis karena melebihi batas piksel yang diizinkan.';
        }
        setStatus(msg, 'ok');
        if (el.download) el.download.focus();
      })
      .catch(function (error) {
        var errText = error && error.message ? error.message : 'Gagal mengonversi gambar.';
        setStatus(errText, 'error');
      })
      .then(function () {
        state.busy = false;
        updateControls();
      });
  }

  // --- Buka dan tutup panel -----------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="image-converter"]');
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
        setStatus('Pilih berkas gambar PNG, JPG, WebP, atau SVG untuk mulai konversi.');
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
  buildWidthField();

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

  if (el.format) {
    el.format.addEventListener('change', updateQualityVisibility);
  }

  if (el.quality) {
    el.quality.addEventListener('input', function () {
      if (el.qualityValue) {
        el.qualityValue.textContent = el.quality.value;
      }
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitConvert);
  if (el.clear) el.clear.addEventListener('click', resetAll);

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel supaya kartu "Image Converter" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['image-converter'] = toggle;
})();
