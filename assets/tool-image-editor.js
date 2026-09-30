/* =========================================================================
   Panel alat: Edit gambar
   Gambar dikirim ke server lewat multipart/form-data, diproses di memori
   (Pillow), lalu hasilnya diunduh langsung. Tidak ada berkas disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('image-editor-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('image-editor-close'),
    limits: document.getElementById('image-editor-limits'),
    drop: document.getElementById('image-editor-drop'),
    input: document.getElementById('image-editor-input'),
    empty: document.getElementById('image-editor-empty'),
    origWrap: document.getElementById('image-editor-orig-wrap'),
    origImg: document.getElementById('image-editor-orig-img'),
    filename: document.getElementById('image-editor-filename'),
    origMeta: document.getElementById('image-editor-orig-meta'),
    controls: document.getElementById('image-editor-controls'),
    putar: document.getElementById('image-editor-putar'),
    balik: document.getElementById('image-editor-balik'),
    rasio: document.getElementById('image-editor-rasio'),
    patokanField: document.getElementById('image-editor-patokan-field'),
    patokan: document.getElementById('image-editor-patokan'),
    orientasi: document.getElementById('image-editor-orientasi'),
    format: document.getElementById('image-editor-format'),
    qualityField: document.getElementById('image-editor-quality-field'),
    kualitas: document.getElementById('image-editor-kualitas'),
    qualityValue: document.getElementById('image-editor-quality-value'),
    result: document.getElementById('image-editor-result'),
    resultImg: document.getElementById('image-editor-result-img'),
    resultMeta: document.getElementById('image-editor-result-meta'),
    status: document.getElementById('image-editor-status'),
    clear: document.getElementById('image-editor-clear'),
    submit: document.getElementById('image-editor-submit'),
    download: document.getElementById('image-editor-download')
  };

  var FALLBACK_LIMITS = {
    max_mb: 15,
    max_bytes: 15728640,
    max_pixels: 40000000,
    quality_min: 10,
    quality_max: 100,
    quality_default: 90
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
    lastFocus: null
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
      el.submit.textContent = state.busy ? 'Sedang memproses…' : 'Proses gambar';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || !hasFile;
    }
  }

  function updateRatioVisibility() {
    if (!el.patokanField || !el.rasio) return;
    el.patokanField.hidden = (el.rasio.value === 'bebas');
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

  // --- Aturan dari server -------------------------------------------------
  function describeLimits(online) {
    if (!el.limits) return;
    var mb = state.limits.max_mb || FALLBACK_LIMITS.max_mb;
    var text = 'Maks 1 berkas, total ' + mb + ' MB (PNG, JPG, atau WebP)';
    el.limits.textContent = text + (online ? ', aturan dari server' : ', aturan bawaan');
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/image/edit/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_pixels: data.max_pixels || FALLBACK_LIMITS.max_pixels,
          quality_min: data.quality_min || FALLBACK_LIMITS.quality_min,
          quality_max: data.quality_max || FALLBACK_LIMITS.quality_max,
          quality_default: data.quality_default || FALLBACK_LIMITS.quality_default
        };
        state.limitsLoaded = true;
        describeLimits(true);
      })
      .catch(function () {
        describeLimits(false);
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

    updateRatioVisibility();
    updateQualityVisibility();
    updateControls();
    setStatus('Gambar dipilih. Tentukan pengaturan edit lalu tekan "Proses gambar".', '');
  }

  // --- Reset --------------------------------------------------------------
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

    if (el.putar) el.putar.value = '0';
    if (el.balik) el.balik.value = 'tidak';
    if (el.rasio) el.rasio.value = 'bebas';
    if (el.patokan) el.patokan.value = 'tengah';
    if (el.orientasi) el.orientasi.value = 'ya';
    if (el.format) el.format.value = 'tetap';

    var defQuality = state.limits.quality_default || FALLBACK_LIMITS.quality_default;
    if (el.kualitas) el.kualitas.value = String(defQuality);
    if (el.qualityValue) el.qualityValue.textContent = String(defQuality);

    updateRatioVisibility();
    updateQualityVisibility();
    updateControls();
    setStatus('Panel dikosongkan. Pilih berkas gambar PNG, JPG, atau WebP untuk mulai mengedit.', '');
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
          message = 'Layanan edit gambar belum tersambung ke server. Coba lagi nanti.';
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
    return 'hasil-edit.' + ext;
  }

  function submitEdit() {
    if (state.busy || !state.file) return;

    var putarVal = el.putar ? el.putar.value : '0';
    var balikVal = el.balik ? el.balik.value : 'tidak';
    var rasioVal = el.rasio ? el.rasio.value : 'bebas';
    var patokanVal = (rasioVal !== 'bebas' && el.patokan) ? el.patokan.value : 'tengah';
    var orientasiVal = el.orientasi ? el.orientasi.value : 'ya';
    var formatVal = el.format ? el.format.value : 'tetap';
    var kualitasVal = el.kualitas ? el.kualitas.value : '90';

    var form = new FormData();
    form.append('file', state.file, state.file.name);
    form.append('putar', putarVal);
    form.append('balik', balikVal);
    form.append('rasio', rasioVal);
    if (rasioVal !== 'bebas') {
      form.append('patokan', patokanVal);
    }
    form.append('orientasi', orientasiVal);
    form.append('format', formatVal);
    form.append('kualitas', kualitasVal);

    state.busy = true;
    updateControls();
    resetResultUi();
    setStatus('Sedang memproses gambar…', 'busy');

    fetch(serverBase + '/api/image/edit', { method: 'POST', body: form })
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
        if (el.resultMeta) {
          el.resultMeta.textContent = dimText + sizeText + ' · ' + outLabel;
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
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="image-editor"]');
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
        setStatus('Pilih berkas gambar PNG, JPG, atau WebP untuk mulai mengedit.');
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

  if (el.rasio) {
    el.rasio.addEventListener('change', updateRatioVisibility);
  }

  if (el.format) {
    el.format.addEventListener('change', updateQualityVisibility);
  }

  if (el.kualitas) {
    el.kualitas.addEventListener('input', function () {
      if (el.qualityValue) {
        el.qualityValue.textContent = el.kualitas.value;
      }
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitEdit);
  if (el.clear) el.clear.addEventListener('click', resetAll);

  window.addEventListener('beforeunload', function () {
    revokeOrigPreview();
    revokeDownload();
  });

  // Daftarkan panel supaya kartu "Image Editor" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['image-editor'] = toggle;

  // Dukungan buka lewat parameter URL: ?alat=image-editor
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('alat') !== 'image-editor') return;

      var trigger = document.querySelector('button.tool-card__open[data-tool-action="image-editor"]');
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
