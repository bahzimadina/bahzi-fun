/* Panel alat: Pas foto
   Pengunjung mengunggah satu foto, lalu mendapatkan pas foto siap cetak
   ukuran 2x3, 3x4, atau 4x6 cm dengan pilihan 300 atau 600 DPI, fokus potongan,
   dan batas ukuran berkas opsional.
   Diproses di memori server dan hasilnya diunduh langsung tanpa tulis ke disk.
*/
(function () {
  'use strict';

  var panel = document.getElementById('pas-foto-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('pas-foto-close'),
    limits: document.getElementById('pas-foto-limits'),
    drop: document.getElementById('pas-foto-drop'),
    input: document.getElementById('pas-foto-input'),
    pickBtn: document.getElementById('pas-foto-pick-btn'),
    empty: document.getElementById('pas-foto-empty'),
    origWrap: document.getElementById('pas-foto-orig-wrap'),
    origImg: document.getElementById('pas-foto-orig-img'),
    filename: document.getElementById('pas-foto-filename'),
    origMeta: document.getElementById('pas-foto-orig-meta'),
    controls: document.getElementById('pas-foto-controls'),
    maxKb: document.getElementById('pas-foto-max-kb'),
    result: document.getElementById('pas-foto-result'),
    resultImg: document.getElementById('pas-foto-result-img'),
    resultStats: document.getElementById('pas-foto-result-stats'),
    upscaledNote: document.getElementById('pas-foto-upscaled-note'),
    targetNote: document.getElementById('pas-foto-target-note'),
    status: document.getElementById('pas-foto-status'),
    reset: document.getElementById('pas-foto-reset'),
    submit: document.getElementById('pas-foto-submit'),
    download: document.getElementById('pas-foto-download')
  };

  var FALLBACK_LIMITS = {
    max_mb: 20,
    max_bytes: 20 * 1024 * 1024,
    max_pixels: 40000000,
    max_side: 12000
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
    appliedOptions: null
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
    state.appliedOptions = null;
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
    if (el.upscaledNote) {
      el.upscaledNote.hidden = true;
    }
    if (el.targetNote) {
      el.targetNote.hidden = true;
    }
  }

  function getCurrentOptions() {
    return {
      size: getRadioValue('pas-foto-size') || '3x4',
      dpi: getRadioValue('pas-foto-dpi') || '300',
      fokus: getRadioValue('pas-foto-fokus') || 'atas',
      maxKb: el.maxKb ? el.maxKb.value.trim() : ''
    };
  }

  function haveOptionsChanged() {
    if (!state.appliedOptions) return false;
    var cur = getCurrentOptions();
    return (
      cur.size !== state.appliedOptions.size ||
      cur.dpi !== state.appliedOptions.dpi ||
      cur.fokus !== state.appliedOptions.fokus ||
      cur.maxKb !== state.appliedOptions.maxKb
    );
  }

  function onOptionChange() {
    if (!state.downloadUrl && (!el.result || el.result.hidden)) return;
    if (!haveOptionsChanged()) return;

    resetResultUi();
    setStatus('Tekan Buat pas foto untuk memakai pilihan baru.');
    updateActionButtons();
  }

  function updateActionButtons() {
    var hasFile = !!state.file;
    if (el.submit) el.submit.disabled = !hasFile || state.busy;
    if (el.reset) el.reset.disabled = !hasFile && !state.origUrl && !state.downloadUrl;
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/pas-foto/limits')
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
          max_side: data.max_side || FALLBACK_LIMITS.max_side
        };
        state.limitsLoaded = true;
        if (el.limits) {
          el.limits.textContent = 'Maks ' + state.limits.max_mb + ' MB, JPG/PNG/WebP. Ukuran 2x3, 3x4, atau 4x6 cm.';
        }
      })
      .catch(function () {
        /* Tetap pakai fallback bawaan bila gagal */
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

    setStatus('Foto siap diproses. Pilih ukuran cetak lalu tekan "Buat pas foto".');
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
    if (el.maxKb) el.maxKb.value = '';

    setRadioValue('pas-foto-size', '3x4');
    setRadioValue('pas-foto-dpi', '300');
    setRadioValue('pas-foto-fokus', 'atas');

    resetResultUi();
    setStatus('Pilih foto untuk mulai membuat pas foto.');
    updateActionButtons();
    if (el.pickBtn && typeof el.pickBtn.focus === 'function') {
      try { el.pickBtn.focus(); } catch (err) { /* diabaikan */ }
    }
  }

  function submitPasFoto() {
    if (!state.file || state.busy) return;

    var sizeVal = getRadioValue('pas-foto-size') || '3x4';
    var dpiVal = getRadioValue('pas-foto-dpi') || '300';
    var fokusVal = getRadioValue('pas-foto-fokus') || 'atas';
    var maxKbRaw = el.maxKb ? el.maxKb.value.trim() : '';
    var maxKbVal = null;

    if (maxKbRaw) {
      maxKbVal = parseInt(maxKbRaw, 10);
      if (isNaN(maxKbVal) || maxKbVal < 10 || maxKbVal > 5000) {
        setStatus('Batas ukuran berkas harus berupa angka antara 10 sampai 5000 KB.', 'error');
        if (el.maxKb) el.maxKb.focus();
        return;
      }
    }

    state.busy = true;
    updateActionButtons();
    setStatus('Sedang memproses pas foto...', 'busy');
    resetResultUi();

    var formData = new FormData();
    formData.append('file', state.file);
    formData.append('size', sizeVal);
    formData.append('dpi', dpiVal);
    formData.append('fokus', fokusVal);
    if (maxKbVal !== null) {
      formData.append('max_kb', String(maxKbVal));
    }

    fetch(serverBase + '/api/pas-foto', {
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
                message = 'Ukuran berkas melebihi batas 20 MB.';
              } else {
                message = 'Terjadi kendala saat memproses pas foto (HTTP ' + res.status + '). Coba lagi sebentar lagi.';
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
        var outDpi = headers.get('x-output-dpi') || dpiVal;
        var outKb = headers.get('x-output-kb');
        var outBytes = headers.get('x-output-bytes');
        var outQuality = headers.get('x-output-quality') || '95';
        var outCm = sizeVal + ' cm';
        var isUpscaled = headers.get('x-upscaled') === 'true';
        var isTargetMet = headers.get('x-target-met') !== 'false';

        var disp = headers.get('content-disposition') || '';
        var match = /filename="?([^";]+)"?/i.exec(disp);
        var filename = match ? match[1] : ('pas-foto-' + sizeVal + '.jpg');

        return res.blob().then(function (blob) {
          return {
            blob: blob,
            filename: filename,
            width: outW,
            height: outH,
            dpi: outDpi,
            kb: outKb ? parseInt(outKb, 10) : Math.ceil(blob.size / 1024),
            bytes: outBytes ? parseInt(outBytes, 10) : blob.size,
            quality: outQuality,
            cm: outCm,
            upscaled: isUpscaled,
            targetMet: isTargetMet
          };
        });
      })
      .then(function (resData) {
        state.busy = false;
        state.appliedOptions = {
          size: sizeVal,
          dpi: dpiVal,
          fokus: fokusVal,
          maxKb: maxKbRaw
        };
        updateActionButtons();

        var blobUrl = URL.createObjectURL(resData.blob);
        state.downloadUrl = blobUrl;

        if (el.resultImg) el.resultImg.src = blobUrl;

        if (el.resultStats) {
          el.resultStats.innerHTML = '';
          var items = [
            { label: 'Ukuran', val: resData.cm },
            { label: 'Piksel', val: (resData.width && resData.height) ? (resData.width + ' × ' + resData.height + ' px') : '-' },
            { label: 'Ketajaman', val: resData.dpi + ' dpi' },
            { label: 'Ukuran berkas', val: formatBytes(resData.bytes) },
            { label: 'Kualitas', val: resData.quality }
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

        if (el.upscaledNote) {
          el.upscaledNote.hidden = !resData.upscaled;
        }
        if (el.targetNote) {
          el.targetNote.hidden = resData.targetMet;
        }

        if (el.result) el.result.hidden = false;

        if (el.download) {
          el.download.href = blobUrl;
          el.download.download = resData.filename;
          el.download.hidden = false;
          el.download.focus();
        }

        setStatus('Pas foto siap diunduh.', 'success');
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
    var triggers = document.querySelectorAll('button.tool-card__open[data-tool-action="pas-foto"]');
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
      target = document.querySelector('button.tool-card__open[data-tool-action="pas-foto"]');
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

  if (el.maxKb) {
    el.maxKb.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        submitPasFoto();
      }
    });
  }

  if (el.controls) {
    el.controls.addEventListener('change', onOptionChange);
    el.controls.addEventListener('input', onOptionChange);
  }

  if (el.submit) el.submit.addEventListener('click', submitPasFoto);
  if (el.reset) el.reset.addEventListener('click', resetAll);

  window.addEventListener('beforeunload', function () {
    revokeOrigPreview();
    revokeDownload();
  });

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['pas-foto'] = toggle;

  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      var paramAlat = params.get('alat');
      if (paramAlat !== 'pas-foto') return;

      var trigger = document.querySelector('button.tool-card__open[data-tool-action="pas-foto"]');
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
