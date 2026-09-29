/* =========================================================================
   Panel alat: QR & Barcode Generator
   Data dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu langsung dibuang setelah gambar dihasilkan. Tidak ada yang disimpan.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('qr-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('qr-title'),
    limits: document.getElementById('qr-limits'),
    note: document.getElementById('qr-note'),
    close: document.getElementById('qr-close'),
    mode: document.getElementById('qr-mode'),
    ukuran: document.getElementById('qr-ukuran'),
    fieldKoreksi: document.getElementById('qr-field-koreksi'),
    koreksi: document.getElementById('qr-koreksi'),
    input: document.getElementById('qr-input'),
    charCount: document.getElementById('qr-char-count'),
    btnContohLink: document.getElementById('qr-contoh-link'),
    btnContohBarcode: document.getElementById('qr-contoh-barcode'),
    status: document.getElementById('qr-status'),
    clear: document.getElementById('qr-clear'),
    submit: document.getElementById('qr-submit'),
    results: document.getElementById('qr-results'),
    resultHint: document.getElementById('qr-result-hint'),
    outputWrap: document.getElementById('qr-output-wrap'),
    previewImg: document.getElementById('qr-preview-img'),
    metaFilename: document.getElementById('qr-meta-filename'),
    metaInfo: document.getElementById('qr-meta-info'),
    download: document.getElementById('qr-download')
  };

  var state = {
    mode: 'qr',
    maxCharsQr: 1200,
    maxCharsBarcode: 80,
    limitsLoaded: false,
    limitsLoading: false,
    busy: false,
    lastFocus: null,
    lastBlobUrl: null,
    lastFilename: 'kode-qr.png'
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

  function formatBytes(bytes) {
    if (typeof bytes !== 'number' || isNaN(bytes) || bytes <= 0) return '';
    if (bytes < 1024) return bytes + ' byte';
    var kb = bytes / 1024;
    return kb.toFixed(1).replace('.', ',') + ' KB';
  }

  function updateModeUI() {
    var modeVal = el.mode ? el.mode.value : 'qr';
    if (modeVal !== 'qr' && modeVal !== 'barcode') {
      modeVal = 'qr';
    }
    state.mode = modeVal;

    if (modeVal === 'qr') {
      if (el.fieldKoreksi) el.fieldKoreksi.hidden = false;
      if (el.input) el.input.maxLength = state.maxCharsQr;
    } else {
      if (el.fieldKoreksi) el.fieldKoreksi.hidden = true;
      if (el.input) el.input.maxLength = state.maxCharsBarcode;
    }

    updateControls();
  }

  function updateControls() {
    var val = el.input ? el.input.value : '';
    var len = val.length;
    var max = state.mode === 'barcode' ? state.maxCharsBarcode : state.maxCharsQr;

    if (el.charCount) {
      el.charCount.textContent = len.toLocaleString('id-ID') + ' dari ' + max.toLocaleString('id-ID') + ' karakter';
    }

    var hasText = val.trim().length > 0;
    if (el.submit) el.submit.disabled = state.busy || !hasText;
    if (el.clear) el.clear.disabled = state.busy || len === 0;
  }

  function resetResults() {
    if (state.lastBlobUrl) {
      try {
        URL.revokeObjectURL(state.lastBlobUrl);
      } catch (e) {
        /* abaikan bila gagal revoke */
      }
      state.lastBlobUrl = null;
    }
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.previewImg) el.previewImg.src = '';
    if (el.metaInfo) el.metaInfo.textContent = '';
  }

  function resetAll() {
    if (el.input) {
      el.input.value = '';
      el.input.focus();
    }
    resetResults();
    updateControls();
    setStatus('Pilih mode, masukkan teks, lalu tekan "Buat kode".', '');
  }

  function loadLimits() {
    if (state.limitsLoaded || state.limitsLoading) return;
    state.limitsLoading = true;

    fetch(serverBase + '/api/qr/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsLoading = false;
        if (!data || typeof data !== 'object') return;

        if (typeof data.teks_maks_qr === 'number') state.maxCharsQr = data.teks_maks_qr;
        if (typeof data.teks_maks_barcode === 'number') state.maxCharsBarcode = data.teks_maks_barcode;

        if (el.limits && Array.isArray(data.ukuran) && data.ukuran.length > 0) {
          el.limits.textContent = 'Ukuran ' + data.ukuran[0] + ' sampai ' + data.ukuran[data.ukuran.length - 1] + ' piksel';
        }

        if (el.note && typeof data.catatan === 'string') {
          el.note.textContent = data.catatan;
        }

        // Perbarui opsi ukuran bila opsi belum cocok
        if (el.ukuran && Array.isArray(data.ukuran) && data.ukuran.length > 0) {
          var curSize = el.ukuran.value;
          el.ukuran.innerHTML = '';
          for (var i = 0; i < data.ukuran.length; i++) {
            var sz = data.ukuran[i];
            var optSz = document.createElement('option');
            optSz.value = String(sz);
            optSz.textContent = sz + ' piksel' + (sz === data.ukuran_bawaan ? ' (bawaan)' : '');
            if (String(sz) === String(curSize || data.ukuran_bawaan)) optSz.selected = true;
            el.ukuran.appendChild(optSz);
          }
        }

        // Perbarui opsi koreksi
        if (el.koreksi && Array.isArray(data.koreksi) && data.koreksi.length > 0) {
          var curKor = el.koreksi.value;
          el.koreksi.innerHTML = '';
          for (var j = 0; j < data.koreksi.length; j++) {
            var kor = data.koreksi[j];
            var optKor = document.createElement('option');
            optKor.value = kor.nilai;
            optKor.textContent = kor.label;
            if (kor.nilai === (curKor || 'M')) optKor.selected = true;
            el.koreksi.appendChild(optKor);
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

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) {
          message = parsed.error.message;
        }
      } catch (err) {
        /* diabaikan */
      }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan pembuat kode belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Permintaan terlalu besar (maksimal 16 KB).';
        } else {
          message = 'Terjadi kendala saat memproses kode (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitCode() {
    if (state.busy) return;

    var modeVal = el.mode ? el.mode.value : 'qr';
    var textVal = el.input ? el.input.value.trim() : '';
    var sizeVal = el.ukuran ? el.ukuran.value : '512';
    var ecVal = el.koreksi ? el.koreksi.value : 'M';

    if (!textVal) {
      setStatus('Isi dulu teks yang mau dijadikan kode.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var form = new FormData();
    form.append('mode', modeVal);
    form.append('teks', textVal);
    form.append('ukuran', sizeVal);
    if (modeVal === 'qr') {
      form.append('koreksi', ecVal);
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang membuat kode...', 'busy');

    var headerPixels = '';
    var headerBytes = 0;
    var headerMode = modeVal;

    fetch(serverBase + '/api/qr', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        headerPixels = response.headers.get('X-Qr-Pixels') || '';
        headerMode = response.headers.get('X-Qr-Mode') || modeVal;
        var bytesRaw = response.headers.get('X-Qr-Bytes');
        if (bytesRaw) headerBytes = parseInt(bytesRaw, 10);
        return response.blob();
      })
      .then(function (blob) {
        if (!blob) throw new Error('Data gambar kosong.');
        if (!headerBytes) headerBytes = blob.size;

        if (state.lastBlobUrl) {
          try {
            URL.revokeObjectURL(state.lastBlobUrl);
          } catch (e) {
            /* diabaikan */
          }
        }

        var blobUrl = URL.createObjectURL(blob);
        state.lastBlobUrl = blobUrl;
        state.lastFilename = (headerMode === 'barcode') ? 'barcode.png' : 'kode-qr.png';

        if (el.previewImg) {
          el.previewImg.src = blobUrl;
        }

        if (el.metaFilename) {
          el.metaFilename.textContent = state.lastFilename;
        }

        if (el.metaInfo) {
          var modeLabel = (headerMode === 'barcode') ? 'Barcode Code 128' : 'Kode QR';
          var pxLabel = headerPixels ? (headerPixels.replace('x', ' × ') + ' px') : '';
          var szLabel = formatBytes(headerBytes);
          var parts = [modeLabel];
          if (pxLabel) parts.push(pxLabel);
          if (szLabel) parts.push(szLabel);
          el.metaInfo.textContent = parts.join(' • ');
        }

        if (el.resultHint) el.resultHint.hidden = true;
        if (el.outputWrap) el.outputWrap.hidden = false;

        setStatus('Kode berhasil dibuat.', 'ok');
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

  function downloadPng() {
    if (!state.lastBlobUrl) return;
    var a = document.createElement('a');
    a.href = state.lastBlobUrl;
    a.download = state.lastFilename || 'kode.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatus('Berkas gambar mulai diunduh.', 'ok');
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="qr"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'qr-panel');
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
    } catch (e) {
      /* diabaikan */
    }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    if (el.input) {
      setTimeout(function () { el.input.focus(); }, 100);
    }
  }

  function close() {
    if (panel.hidden) return;
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

  // Pintasan contoh
  if (el.btnContohLink) {
    el.btnContohLink.addEventListener('click', function () {
      if (el.mode) el.mode.value = 'qr';
      updateModeUI();
      if (el.input) {
        el.input.value = 'https://bahzi.fun';
        el.input.focus();
      }
      updateControls();
    });
  }

  if (el.btnContohBarcode) {
    el.btnContohBarcode.addEventListener('click', function () {
      if (el.mode) el.mode.value = 'barcode';
      updateModeUI();
      if (el.input) {
        el.input.value = 'BAHZI-2026';
        el.input.focus();
      }
      updateControls();
    });
  }

  // Event Listeners
  if (el.close) el.close.addEventListener('click', close);

  if (el.mode) {
    el.mode.addEventListener('change', function () {
      updateModeUI();
      resetResults();
      setStatus('Pilih mode, masukkan teks, lalu tekan "Buat kode".', '');
      if (el.input) el.input.focus();
    });
  }

  if (el.input) {
    el.input.addEventListener('input', updateControls);
    el.input.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        submitCode();
      }
    });
  }

  if (el.ukuran) el.ukuran.addEventListener('change', updateControls);
  if (el.koreksi) el.koreksi.addEventListener('change', updateControls);
  if (el.submit) el.submit.addEventListener('click', submitCode);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.download) el.download.addEventListener('click', downloadPng);

  function onKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape' && panel.contains(document.activeElement)) {
      event.preventDefault();
      close();
    }
  }
  document.addEventListener('keydown', onKeydown);

  // Daftarkan panel ke registry global
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['qr'] = toggle;

  // Inisialisasi awal
  loadLimits();
  updateModeUI();
  updateControls();

  // Dukungan buka lewat parameter URL: ?alat=qr
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('alat') !== 'qr') return;

      var trigger = document.querySelector('button.tool-card__open[data-tool-action="qr"]');
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
