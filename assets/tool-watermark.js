/* Panel alat: Beri tanda air pada foto (Watermark)
   Pengunjung mengunggah satu foto, lalu membubuhi teks tanda air
   di satu posisi terpilih atau bermotif miring berulang.
   Diproses sepenuhnya di memori server dan hasilnya langsung diunduh tanpa tulis ke disk.
*/
(function () {
  'use strict';

  var panel = document.getElementById('watermark-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('watermark-close'),
    limits: document.getElementById('watermark-limits'),
    drop: document.getElementById('watermark-drop'),
    input: document.getElementById('watermark-input'),
    pickBtn: document.getElementById('watermark-pick-btn'),
    empty: document.getElementById('watermark-empty'),
    origWrap: document.getElementById('watermark-orig-wrap'),
    origImg: document.getElementById('watermark-orig-img'),
    filename: document.getElementById('watermark-filename'),
    origMeta: document.getElementById('watermark-orig-meta'),
    controls: document.getElementById('watermark-controls'),
    text: document.getElementById('watermark-text'),
    charCount: document.getElementById('watermark-char-count'),
    posField: document.getElementById('watermark-position-field'),
    size: document.getElementById('watermark-size'),
    sizeVal: document.getElementById('watermark-size-val'),
    opacity: document.getElementById('watermark-opacity'),
    opacityVal: document.getElementById('watermark-opacity-val'),
    angle: document.getElementById('watermark-angle'),
    angleVal: document.getElementById('watermark-angle-val'),
    result: document.getElementById('watermark-result'),
    resultImg: document.getElementById('watermark-result-img'),
    resultStats: document.getElementById('watermark-result-stats'),
    status: document.getElementById('watermark-status'),
    reset: document.getElementById('watermark-reset'),
    submit: document.getElementById('watermark-submit'),
    download: document.getElementById('watermark-download')
  };

  var FALLBACK_LIMITS = {
    max_mb: 15,
    max_bytes: 15 * 1024 * 1024,
    max_pixels: 40000000,
    max_side: 8000,
    text_max: 60,
    size: { min: 2, max: 30 },
    opacity: { min: 5, max: 100 },
    angle: { min: -90, max: 90 }
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
    userChangedAngle: false
  };

  function getRadioValue(name) {
    var checked = panel.querySelector('input[name="' + name + '"]:checked');
    return checked ? checked.value : null;
  }

  function setRadioValue(name, value) {
    var radios = panel.querySelectorAll('input[name="' + name + '"]');
    for (var i = 0; i < radios.length; i++) {
      radios[i].checked = (radios[i].value === value);
    }
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
    if (el.resultStats) {
      el.resultStats.innerHTML = '';
    }
  }

  function updateActionButtons() {
    var hasFile = !!state.file;
    if (el.submit) el.submit.disabled = !hasFile || state.busy;
    if (el.reset) el.reset.disabled = !hasFile && !state.origUrl && !state.downloadUrl;
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/watermark/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('Gagal memuat batas server');
        return res.json();
      })
      .then(function (data) {
        if (!data || typeof data !== 'object') return;
        state.limits = {
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_mb: Math.round((data.max_bytes || FALLBACK_LIMITS.max_bytes) / (1024 * 1024)),
          max_pixels: data.max_pixels || FALLBACK_LIMITS.max_pixels,
          max_side: data.max_side || FALLBACK_LIMITS.max_side,
          text_max: data.text_max || FALLBACK_LIMITS.text_max,
          size: data.size || FALLBACK_LIMITS.size,
          opacity: data.opacity || FALLBACK_LIMITS.opacity,
          angle: data.angle || FALLBACK_LIMITS.angle
        };
        state.limitsLoaded = true;
        if (el.limits) {
          el.limits.textContent = 'Maks ' + state.limits.max_mb + ' MB, JPG/PNG/WebP. Teks tanda air hingga ' + state.limits.text_max + ' karakter.';
        }
        if (el.text && state.limits.text_max) {
          el.text.setAttribute('maxlength', String(state.limits.text_max));
        }
      })
      .catch(function () {
        /* Tetap gunakan batas bawaan */
      });
  }

  function handleFile(file) {
    if (!file) return;

    var maxBytes = state.limits.max_bytes || FALLBACK_LIMITS.max_bytes;
    if (file.size > maxBytes) {
      var limitMb = Math.round(maxBytes / (1024 * 1024));
      setStatus('Ukuran berkas melebihi batas ' + limitMb + ' MB. Pilih foto yang lebih kecil.', 'error');
      return;
    }

    var validTypes = ['image/jpeg', 'image/png', 'image/webp'];
    var name = (file.name || '').toLowerCase();
    var hasValidExt = name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.png') || name.endsWith('.webp');

    if (file.type && validTypes.indexOf(file.type) === -1 && !hasValidExt) {
      setStatus('Format berkas tidak didukung. Pilih foto JPG, PNG, atau WebP.', 'error');
      return;
    }

    state.file = file;
    resetResultUi();
    revokeOrigPreview();

    if (el.filename) el.filename.textContent = file.name || 'foto';
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
        el.origMeta.textContent = probe.naturalWidth + ' × ' + probe.naturalHeight + ' px · ' + formatBytes(file.size);
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

    setStatus('Foto siap. Ketik teks tanda air lalu tekan "Beri tanda air".');
    updateActionButtons();
    if (el.text && !el.text.value) {
      try { el.text.focus(); } catch (err) { /* diabaikan */ }
    }
  }

  function resetAll() {
    revokeOrigPreview();
    revokeDownload();
    state.file = null;
    state.origWidth = null;
    state.origHeight = null;
    state.busy = false;
    state.userChangedAngle = false;

    if (el.input) el.input.value = '';
    if (el.empty) el.empty.hidden = false;
    if (el.origWrap) el.origWrap.hidden = true;
    if (el.controls) el.controls.hidden = true;

    if (el.text) {
      el.text.value = '';
    }
    if (el.charCount) {
      el.charCount.textContent = '0/60';
    }

    setRadioValue('watermark-mode', 'single');
    setRadioValue('watermark-pos', 'br');
    setRadioValue('watermark-color', 'light');
    setRadioValue('watermark-format', 'jpeg');

    if (el.posField) el.posField.hidden = false;

    if (el.size) {
      el.size.value = '7';
      if (el.sizeVal) el.sizeVal.textContent = '7%';
    }
    if (el.opacity) {
      el.opacity.value = '45';
      if (el.opacityVal) el.opacityVal.textContent = '45%';
    }
    if (el.angle) {
      el.angle.value = '0';
      if (el.angleVal) el.angleVal.textContent = '0°';
    }

    resetResultUi();
    setStatus('Pilih foto untuk mulai memberi tanda air.');
    updateActionButtons();
    if (el.pickBtn && typeof el.pickBtn.focus === 'function') {
      try { el.pickBtn.focus(); } catch (err) { /* diabaikan */ }
    }
  }

  function onModeChange() {
    var mode = getRadioValue('watermark-mode') || 'single';
    if (el.posField) {
      el.posField.hidden = (mode === 'tile');
    }
    if (!state.userChangedAngle && el.angle) {
      var defaultAngle = (mode === 'tile') ? 30 : 0;
      el.angle.value = String(defaultAngle);
      if (el.angleVal) el.angleVal.textContent = defaultAngle + '°';
    }
    resetResultUi();
  }

  function submitWatermark() {
    if (!state.file || state.busy) return;

    var textVal = el.text ? el.text.value.trim() : '';
    if (!textVal) {
      setStatus('Ketik teks tanda air terlebih dahulu.', 'error');
      if (el.text) el.text.focus();
      return;
    }

    var maxLen = (state.limits && state.limits.text_max) || 60;
    if (textVal.length > maxLen) {
      setStatus('Teks tanda air maksimal ' + maxLen + ' karakter.', 'error');
      if (el.text) el.text.focus();
      return;
    }

    var modeVal = getRadioValue('watermark-mode') || 'single';
    var posVal = getRadioValue('watermark-pos') || 'br';
    var sizeVal = el.size ? el.size.value : '7';
    var opacityVal = el.opacity ? el.opacity.value : '45';
    var colorVal = getRadioValue('watermark-color') || 'light';
    var angleVal = el.angle ? el.angle.value : (modeVal === 'tile' ? '30' : '0');
    var formatVal = getRadioValue('watermark-format') || 'jpeg';

    state.busy = true;
    updateActionButtons();
    setStatus('Sedang memberi tanda air pada foto...', 'busy');
    resetResultUi();

    var formData = new FormData();
    formData.append('file', state.file);
    formData.append('text', textVal);
    formData.append('mode', modeVal);
    if (modeVal === 'single') {
      formData.append('position', posVal);
    }
    formData.append('size', sizeVal);
    formData.append('opacity', opacityVal);
    formData.append('color', colorVal);
    formData.append('angle', angleVal);
    formData.append('format', formatVal);

    fetch(serverBase + '/api/watermark', {
      method: 'POST',
      body: formData
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () {
            return null;
          }).then(function (body) {
            var message = (body && body.error && body.error.message) || '';
            if (!message) {
              if (res.status === 413) {
                message = 'Ukuran berkas melebihi batas yang diizinkan.';
              } else if (res.status === 422) {
                message = 'Parameter tanda air tidak valid.';
              } else {
                message = 'Terjadi kendala saat memproses gambar (HTTP ' + res.status + '). Coba lagi sebentar lagi.';
              }
            }
            var err = new Error(message);
            err.pesanLayanan = true;
            throw err;
          });
        }

        var headers = res.headers;
        var outW = headers.get('x-output-width');
        var outH = headers.get('x-output-height');
        var outBytes = headers.get('x-output-bytes');

        var disp = headers.get('content-disposition') || '';
        var match = /filename="?([^";]+)"?/i.exec(disp);
        var filename = match ? match[1] : (formatVal === 'png' ? 'tanda-air.png' : 'tanda-air.jpg');

        return res.blob().then(function (blob) {
          return {
            blob: blob,
            filename: filename,
            width: outW,
            height: outH,
            bytes: outBytes ? parseInt(outBytes, 10) : blob.size,
            format: formatVal.toUpperCase()
          };
        });
      })
      .then(function (resData) {
        state.busy = false;
        updateActionButtons();

        var blobUrl = URL.createObjectURL(resData.blob);
        state.downloadUrl = blobUrl;

        if (el.resultImg) el.resultImg.src = blobUrl;

        if (el.resultStats) {
          el.resultStats.innerHTML = '';
          var items = [
            { label: 'Format', val: resData.format },
            { label: 'Dimensi', val: (resData.width && resData.height) ? (resData.width + ' × ' + resData.height + ' px') : '-' },
            { label: 'Ukuran berkas', val: formatBytes(resData.bytes) }
          ];
          for (var i = 0; i < items.length; i++) {
            var li = document.createElement('li');
            var span = document.createElement('span');
            span.textContent = items[i].label + ': ';
            var strong = document.createElement('strong');
            strong.textContent = items[i].val;
            li.appendChild(span);
            li.appendChild(strong);
            el.resultStats.appendChild(li);
          }
        }

        if (el.result) el.result.hidden = false;

        if (el.download) {
          el.download.href = blobUrl;
          el.download.download = resData.filename;
          el.download.hidden = false;
          try { el.download.focus(); } catch (err) { /* diabaikan */ }
        }

        setStatus('Tanda air berhasil dibuat. Siap diunduh.', 'success');
      })
      .catch(function (err) {
        state.busy = false;
        updateActionButtons();
        var msg = (err && err.pesanLayanan === true && err.message)
          ? err.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
      });
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('button.tool-card__open[data-tool-action="watermark"]');
    triggers.forEach(function (btn) {
      btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
  }

  function open() {
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);
    loadLimits();

    var focusTarget = el.pickBtn || el.close;
    if (focusTarget && typeof focusTarget.focus === 'function') {
      try { focusTarget.focus(); } catch (err) { /* diabaikan */ }
    }
  }

  function close() {
    panel.hidden = true;
    syncTriggers(false);
    var target = state.lastFocus;
    if (!target || target === document.body || (target.tagName && target.tagName.toUpperCase() === 'BODY') || !document.contains(target)) {
      target = document.querySelector('button.tool-card__open[data-tool-action="watermark"]');
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

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.pickBtn && el.input) {
    el.pickBtn.addEventListener('click', function () {
      el.input.click();
    });
  }

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

  if (el.text) {
    el.text.addEventListener('input', function () {
      if (el.charCount) {
        el.charCount.textContent = el.text.value.length + '/60';
      }
      resetResultUi();
    });
    el.text.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        submitWatermark();
      }
    });
  }

  // Segmented mode listener
  var modeRadios = panel.querySelectorAll('input[name="watermark-mode"]');
  for (var i = 0; i < modeRadios.length; i++) {
    modeRadios[i].addEventListener('change', onModeChange);
  }

  // Sliders
  if (el.size) {
    el.size.addEventListener('input', function () {
      if (el.sizeVal) el.sizeVal.textContent = el.size.value + '%';
      resetResultUi();
    });
  }

  if (el.opacity) {
    el.opacity.addEventListener('input', function () {
      if (el.opacityVal) el.opacityVal.textContent = el.opacity.value + '%';
      resetResultUi();
    });
  }

  if (el.angle) {
    el.angle.addEventListener('input', function () {
      state.userChangedAngle = true;
      if (el.angleVal) el.angleVal.textContent = el.angle.value + '°';
      resetResultUi();
    });
  }

  // Radio changes reset result ui
  var otherRadios = panel.querySelectorAll('input[name="watermark-pos"], input[name="watermark-color"], input[name="watermark-format"]');
  for (var j = 0; j < otherRadios.length; j++) {
    otherRadios[j].addEventListener('change', resetResultUi);
  }

  if (el.submit) el.submit.addEventListener('click', submitWatermark);
  if (el.reset) el.reset.addEventListener('click', resetAll);

  window.addEventListener('beforeunload', function () {
    revokeOrigPreview();
    revokeDownload();
  });

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['watermark'] = toggle;

  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      var paramAlat = params.get('alat');
      if (paramAlat !== 'watermark' && paramAlat !== 'tanda-air') return;

      var trigger = document.querySelector('button.tool-card__open[data-tool-action="watermark"]');
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
