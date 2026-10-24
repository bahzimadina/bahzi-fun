/* =========================================================================
   Panel alat: Kompres gambar
   Gambar dikirim ke server lewat multipart/form-data, diproses di memori
   (Pillow), lalu hasilnya diunduh langsung. Tidak ada berkas disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('kompres-gambar-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('kompres-gambar-close'),
    limits: document.getElementById('kompres-gambar-limits'),
    drop: document.getElementById('kompres-gambar-drop'),
    input: document.getElementById('kompres-gambar-input'),
    empty: document.getElementById('kompres-gambar-empty'),
    origWrap: document.getElementById('kompres-gambar-orig-wrap'),
    origImg: document.getElementById('kompres-gambar-orig-img'),
    filename: document.getElementById('kompres-gambar-filename'),
    origMeta: document.getElementById('kompres-gambar-orig-meta'),
    controls: document.getElementById('kompres-gambar-controls'),
    target: document.getElementById('kompres-gambar-target'),
    shortcuts: document.getElementById('kompres-gambar-shortcuts'),
    format: document.getElementById('kompres-gambar-format'),
    suggestion: document.getElementById('kompres-gambar-suggestion'),
    suggestionText: document.getElementById('kompres-gambar-suggestion-text'),
    suggestionBtn: document.getElementById('kompres-gambar-suggestion-btn'),
    result: document.getElementById('kompres-gambar-result'),
    resultImg: document.getElementById('kompres-gambar-result-img'),
    resultMeta: document.getElementById('kompres-gambar-result-meta'),
    status: document.getElementById('kompres-gambar-status'),
    clear: document.getElementById('kompres-gambar-clear'),
    submit: document.getElementById('kompres-gambar-submit'),
    download: document.getElementById('kompres-gambar-download')
  };

  var FALLBACK_LIMITS = {
    max_mb: 15,
    max_bytes: 15728640,
    max_pixels: 40000000,
    max_side: 12000,
    target_kb: {
      min: 10,
      max: 5000,
      default: 200,
      shortcuts: [100, 200, 500, 1000]
    },
    formats: ['jpeg', 'webp']
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
    if (el.suggestion) {
      el.suggestion.hidden = true;
    }
  }

  function syncChips() {
    if (!el.shortcuts || !el.target) return;
    var currentVal = parseInt(el.target.value, 10);
    var chips = el.shortcuts.querySelectorAll('.chip');
    chips.forEach(function (chip) {
      var kb = parseInt(chip.getAttribute('data-kb'), 10);
      if (kb === currentVal) {
        chip.classList.add('is-active');
      } else {
        chip.classList.remove('is-active');
      }
    });
  }

  function updateActionButtons() {
    var hasFile = !!state.file;
    if (el.submit) el.submit.disabled = !hasFile || state.busy;
    if (el.clear) el.clear.disabled = !hasFile && !state.origUrl;
  }

  // --- Muat batas dari server ---------------------------------------------
  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/image/compress/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('Gagal memuat batas server');
        return res.json();
      })
      .then(function (data) {
        if (!data || typeof data !== 'object') return;
        state.limits = {
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
          max_bytes: (data.max_mb || FALLBACK_LIMITS.max_mb) * 1024 * 1024,
          max_pixels: data.max_pixels || FALLBACK_LIMITS.max_pixels,
          max_side: data.max_side || FALLBACK_LIMITS.max_side,
          target_kb: data.target_kb || FALLBACK_LIMITS.target_kb,
          formats: data.formats || FALLBACK_LIMITS.formats
        };
        state.limitsLoaded = true;

        if (el.limits) {
          el.limits.textContent = 'Maks 1 berkas, total ' + state.limits.max_mb + ' MB (PNG, JPG, atau WebP)';
        }
      })
      .catch(function () {
        /* Gunakan fallback jika gagal */
      });
  }

  // --- Penanganan berkas --------------------------------------------------
  function handleFile(file) {
    if (!file) return;

    var maxBytes = state.limits.max_bytes || FALLBACK_LIMITS.max_bytes;
    if (file.size > maxBytes) {
      var limitMb = Math.round(maxBytes / (1024 * 1024));
      setStatus('Ukuran berkas melebihi batas ' + limitMb + ' MB. Pilih berkas yang lebih kecil.', 'error');
      return;
    }

    var validTypes = ['image/png', 'image/jpeg', 'image/webp'];
    var name = (file.name || '').toLowerCase();
    var hasValidExt = name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.webp');

    if (file.type && validTypes.indexOf(file.type) === -1 && !hasValidExt) {
      setStatus('Format berkas tidak didukung. Pilih gambar PNG, JPG, atau WebP.', 'error');
      return;
    }

    state.file = file;
    resetResultUi();
    revokeOrigPreview();

    if (el.filename) el.filename.textContent = file.name || 'gambar';
    if (el.origMeta) el.origMeta.textContent = 'Memuat ukuran...';
    if (el.empty) el.empty.hidden = true;
    if (el.origWrap) el.origWrap.hidden = false;
    if (el.controls) el.controls.hidden = false;

    var url = URL.createObjectURL(file);
    state.origUrl = url;
    if (el.origImg) el.origImg.src = url;

    var probe = new Image();
    probe.onload = function () {
      state.origWidth = probe.naturalWidth;
      state.origHeight = probe.naturalHeight;
      if (el.origMeta) {
        el.origMeta.textContent = probe.naturalWidth + ' × ' + probe.naturalHeight + ' · ' + formatBytes(file.size);
      }
    };
    probe.onerror = function () {
      state.origWidth = null;
      state.origHeight = null;
      if (el.origMeta) {
        el.origMeta.textContent = formatBytes(file.size);
      }
    };
    probe.src = url;

    setStatus('Gambar siap dikompres. Tentukan target ukuran lalu tekan "Kompres gambar".');
    updateActionButtons();
  }

  function resetAll() {
    revokeOrigPreview();
    revokeDownload();
    state.file = null;
    state.origWidth = null;
    state.origHeight = null;
    state.busy = false;

    if (el.input) el.input.value = '';
    if (el.empty) el.empty.hidden = false;
    if (el.origWrap) el.origWrap.hidden = true;
    if (el.controls) el.controls.hidden = true;
    if (el.target) el.target.value = '200';
    if (el.format) el.format.value = 'jpeg';
    syncChips();

    resetResultUi();
    setStatus('Pilih berkas gambar PNG, JPG, atau WebP untuk mulai kompres.');
    updateActionButtons();
    if (el.input && typeof el.input.focus === 'function') {
      try { el.input.focus(); } catch (err) { /* diabaikan */ }
    }
  }

  // --- Kirim kompresi ke server -------------------------------------------
  function submitCompress() {
    if (!state.file || state.busy) return;

    var targetVal = parseInt(el.target ? el.target.value : '200', 10);
    if (isNaN(targetVal) || targetVal < 10 || targetVal > 5000) {
      setStatus('Target ukuran harus berupa angka antara 10 sampai 5000 KB.', 'error');
      if (el.target) el.target.focus();
      return;
    }

    var formatVal = (el.format ? el.format.value : 'jpeg') || 'jpeg';

    state.busy = true;
    updateActionButtons();
    setStatus('Sedang mengompres...', 'busy');
    resetResultUi();

    var formData = new FormData();
    formData.append('file', state.file);
    formData.append('target_kb', String(targetVal));
    formData.append('format', formatVal);

    fetch(serverBase + '/api/image/compress', {
      method: 'POST',
      body: formData
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () {
            return { error: { code: 'HTTP_' + res.status, message: 'Server menolak permintaan kompres gambar.' } };
          }).then(function (errBody) {
            var err = (errBody && errBody.error) || {};
            var errorObj = new Error(err.message || 'Gagal memproses gambar');
            errorObj.code = err.code || 'UNKNOWN';
            errorObj.min_kb = err.min_kb;
            throw errorObj;
          });
        }

        var headers = res.headers;
        var outW = headers.get('x-output-width');
        var outH = headers.get('x-output-height');
        var outBytesHeader = headers.get('x-output-bytes');
        var alreadySmall = headers.get('x-already-small') === 'true';

        var disp = headers.get('content-disposition') || '';
        var filenameMatch = /filename="?([^";]+)"?/i.exec(disp);
        var filename = filenameMatch ? filenameMatch[1] : ('hasil-kompres.' + (formatVal === 'webp' ? 'webp' : 'jpg'));

        return res.blob().then(function (blob) {
          return {
            blob: blob,
            filename: filename,
            width: outW,
            height: outH,
            bytes: outBytesHeader ? parseInt(outBytesHeader, 10) : blob.size,
            alreadySmall: alreadySmall
          };
        });
      })
      .then(function (resData) {
        state.busy = false;
        updateActionButtons();

        var blobUrl = URL.createObjectURL(resData.blob);
        state.downloadUrl = blobUrl;

        if (el.resultImg) el.resultImg.src = blobUrl;

        var origBytes = state.file ? state.file.size : resData.bytes;
        var outBytes = resData.bytes;

        var info = '';
        var dimStr = (resData.width && resData.height) ? (resData.width + ' × ' + resData.height + ' · ') : '';

        if (resData.alreadySmall) {
          info = dimStr + formatBytes(outBytes) + ' (sudah di bawah target ' + targetVal + ' KB)';
          setStatus('Berkas sudah di bawah target (tidak perlu dikompres).', 'success');
        } else {
          var pct = Math.max(0, Math.round((1 - (outBytes / origBytes)) * 100));
          info = dimStr + formatBytes(outBytes) + ' · dari ' + formatBytes(origBytes) + ' (' + pct + '% lebih kecil)';
          setStatus('Kompres gambar selesai.', 'success');
        }

        if (el.resultMeta) el.resultMeta.textContent = info;
        if (el.result) el.result.hidden = false;

        if (el.download) {
          el.download.href = blobUrl;
          el.download.download = resData.filename;
          el.download.hidden = false;
          el.download.focus();
        }
      })
      .catch(function (err) {
        state.busy = false;
        updateActionButtons();

        if (err.code === 'TARGET_UNREACHABLE') {
          if (el.suggestion && err.min_kb) {
            el.suggestionText.textContent = 'Target ' + targetVal + ' KB terlalu kecil untuk gambar ini. Ukuran terkecil yang bisa dicapai sekitar ' + err.min_kb + ' KB.';
            el.suggestion.hidden = false;
            if (el.suggestionBtn) {
              el.suggestionBtn.onclick = function () {
                if (el.target) {
                  el.target.value = err.min_kb;
                  syncChips();
                }
                el.suggestion.hidden = true;
                if (el.submit) el.submit.focus();
              };
            }
          }
          setStatus(err.message || 'Ukuran target terlalu kecil. Coba gunakan angka yang disarankan di atas.', 'error');
        } else {
          var friendlyMsg = err.message;
          if (!friendlyMsg || friendlyMsg.indexOf('Failed to fetch') !== -1) {
            friendlyMsg = 'Tidak dapat menghubungi server. Periksa koneksi internet Anda dan coba lagi.';
          }
          setStatus(friendlyMsg, 'error');
        }
      });
  }

  // --- Buka / Tutup panel -------------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('button.tool-card__open[data-tool-action="kompres-gambar"]');
    triggers.forEach(function (btn) {
      btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
  }

  function open() {
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);
    loadLimits();

    var focusTarget = el.input || el.close;
    if (focusTarget && typeof focusTarget.focus === 'function') {
      try { focusTarget.focus(); } catch (err) { /* diabaikan */ }
    }
  }

  function close() {
    panel.hidden = true;
    syncTriggers(false);
    var target = state.lastFocus;
    if (!target || target === document.body || (target.tagName && target.tagName.toUpperCase() === 'BODY') || !document.contains(target)) {
      target = document.querySelector('button.tool-card__open[data-tool-action="kompres-gambar"]');
    }
    if (target && typeof target.focus === 'function') {
      try { target.focus(); } catch (err) { /* diabaikan */ }
    }
    state.lastFocus = null;
  }

  function toggle() {
    if (panel.hidden) open(); else close();
  }

  function onKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape') {
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

  if (el.target) {
    el.target.addEventListener('input', syncChips);
    el.target.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        submitCompress();
      }
    });
  }

  if (el.shortcuts) {
    el.shortcuts.addEventListener('click', function (event) {
      var btn = event.target.closest('.chip');
      if (!btn) return;
      var kb = btn.getAttribute('data-kb');
      if (kb && el.target) {
        el.target.value = kb;
        syncChips();
      }
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitCompress);
  if (el.clear) el.clear.addEventListener('click', resetAll);

  window.addEventListener('beforeunload', function () {
    revokeOrigPreview();
    revokeDownload();
  });

  // Daftarkan panel supaya kartu "Kompres gambar" bisa membuka/menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['kompres-gambar'] = toggle;

  // Dukungan buka lewat parameter URL: ?alat=kompres-gambar
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      var paramAlat = params.get('alat');
      if (paramAlat !== 'kompres-gambar' && paramAlat !== 'image-compress') return;

      var trigger = document.querySelector('button.tool-card__open[data-tool-action="kompres-gambar"]');
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
