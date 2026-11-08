/* =========================================================================
   Panel alat: Beri nomor halaman PDF
   Menambahkan nomor halaman ke dokumen PDF (ditempel di atas halaman),
   dengan pilihan posisi, format tampilan, nomor awal, ukuran huruf,
   dan rentang halaman tertentu.
   Semua berkas diproses murni di memori lalu langsung dibuang.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('nomor-halaman-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('nomor-halaman-close'),
    drop: document.getElementById('nomor-halaman-drop'),
    fileInput: document.getElementById('nomor-halaman-file'),
    fileBox: document.getElementById('nomor-halaman-file-box'),
    fileName: document.getElementById('nomor-halaman-filename'),
    fileSize: document.getElementById('nomor-halaman-filesize'),
    removeFile: document.getElementById('nomor-halaman-remove-file'),
    empty: document.getElementById('nomor-halaman-empty'),
    position: document.getElementById('nomor-halaman-position'),
    format: document.getElementById('nomor-halaman-format'),
    start: document.getElementById('nomor-halaman-start'),
    size: document.getElementById('nomor-halaman-size'),
    pages: document.getElementById('nomor-halaman-pages'),
    result: document.getElementById('nomor-halaman-result'),
    summary: document.getElementById('nomor-halaman-summary'),
    download: document.getElementById('nomor-halaman-download'),
    copy: document.getElementById('nomor-halaman-copy'),
    status: document.getElementById('nomor-halaman-status'),
    clear: document.getElementById('nomor-halaman-clear'),
    submit: document.getElementById('nomor-halaman-submit')
  };

  var state = {
    file: null,
    busy: false,
    downloadUrl: null,
    lastSummary: '',
    lastFocus: null
  };

  function formatBytes(bytes) {
    if (typeof bytes !== 'number' || isNaN(bytes)) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) {
      return (bytes / 1024).toLocaleString('id-ID', { maximumFractionDigits: 1 }) + ' KB';
    }
    return (bytes / 1048576).toLocaleString('id-ID', { maximumFractionDigits: 1 }) + ' MB';
  }

  function setStatus(message, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status' + (kind ? ' status--' + kind : '');
    if (kind === 'error') {
      el.status.setAttribute('role', 'alert');
    } else {
      el.status.setAttribute('role', 'status');
    }
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
      try {
        URL.revokeObjectURL(state.downloadUrl);
      } catch (err) { /* diabaikan */ }
      state.downloadUrl = null;
    }
  }

  function resetResultUi() {
    revokeDownload();
    state.lastSummary = '';
    if (el.result) el.result.hidden = true;
    if (el.summary) el.summary.textContent = '';
    if (el.download) {
      el.download.hidden = true;
      el.download.href = '#';
    }
    if (el.copy) el.copy.hidden = true;
  }

  function updateControls() {
    var hasFile = !!state.file;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasFile;
      el.submit.textContent = state.busy ? 'Menempel nomor…' : 'Beri nomor';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasFile && !state.lastSummary);
    }
    if (el.removeFile) {
      el.removeFile.disabled = state.busy;
    }
  }

  function setFile(file) {
    if (!file) {
      state.file = null;
      if (el.fileInput) el.fileInput.value = '';
      if (el.fileBox) el.fileBox.hidden = true;
      if (el.empty) el.empty.hidden = false;
      if (el.drop) el.drop.hidden = false;
      resetResultUi();
      setStatus('Pilih berkas PDF untuk mulai memberi nomor halaman.');
      updateControls();
      return;
    }

    var isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
    if (!isPdf) {
      setStatus('Berkas bukan dokumen PDF yang sah. Pilih berkas berakhiran .pdf.', 'error');
      return;
    }

    var maxBytes = 25 * 1024 * 1024;
    if (file.size > maxBytes) {
      setStatus('Ukuran berkas melebihi batas 25 MB.', 'error');
      return;
    }

    state.file = file;
    if (el.fileName) el.fileName.textContent = file.name;
    if (el.fileSize) el.fileSize.textContent = formatBytes(file.size);
    if (el.fileBox) el.fileBox.hidden = false;
    if (el.empty) el.empty.hidden = true;
    if (el.drop) el.drop.hidden = true;

    resetResultUi();
    setStatus('Berkas "' + file.name + '" siap diberi nomor. Atur pilihan lalu tekan "Beri nomor".', 'ok');
    updateControls();
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) {
          message = parsed.error.message;
        }
      } catch (err) { /* balasan bukan format JSON */ }

      if (!message) {
        if (response.status === 413) {
          message = 'Ukuran berkas melebihi batas 25 MB.';
        } else if (response.status === 404) {
          message = 'Layanan belum tersambung ke server. Coba lagi nanti.';
        } else {
          message = 'Layanan membalas dengan status ' + response.status + '. Silakan coba lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    ta.style.top = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
      setStatus('Ringkasan berhasil disalin ke papan klip.', 'ok');
    } catch (e) {
      setStatus('Gagal menyalin ringkasan ke papan klip.', 'error');
    }
    document.body.removeChild(ta);
  }

  function copySummary() {
    if (!state.lastSummary) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(state.lastSummary).then(function () {
        setStatus('Ringkasan berhasil disalin ke papan klip.', 'ok');
      }).catch(function () {
        fallbackCopy(state.lastSummary);
      });
    } else {
      fallbackCopy(state.lastSummary);
    }
  }

  function submitJob() {
    if (state.busy || !state.file) return;

    var startVal = (el.start && el.start.value) ? el.start.value.trim() : '1';
    var sizeVal = (el.size && el.size.value) ? el.size.value.trim() : '11';
    var pagesVal = (el.pages && el.pages.value) ? el.pages.value.trim() : '';
    var posVal = (el.position && el.position.value) ? el.position.value : 'bawah-tengah';
    var fmtVal = (el.format && el.format.value) ? el.format.value : 'angka';

    var startNum = parseInt(startVal, 10);
    if (!/^\d+$/.test(startVal) || isNaN(startNum) || startNum < 1 || startNum > 99999) {
      setStatus('Nomor awal halaman harus berupa bilangan bulat antara 1 sampai 99999.', 'error');
      if (el.start) el.start.focus();
      return;
    }

    var sizeNum = parseFloat(sizeVal);
    if (isNaN(sizeNum) || sizeNum < 8 || sizeNum > 24) {
      setStatus('Ukuran huruf harus berupa angka antara 8 sampai 24 pt.', 'error');
      if (el.size) el.size.focus();
      return;
    }

    var form = new FormData();
    form.append('file', state.file, state.file.name);
    form.append('position', posVal);
    form.append('format', fmtVal);
    form.append('start', startVal);
    form.append('size', sizeVal);
    if (pagesVal) {
      form.append('pages', pagesVal);
    }

    state.busy = true;
    updateControls();
    resetResultUi();
    setStatus('Mengirim dokumen dan menempel nomor halaman di layanan…', 'busy');

    fetch(serverBase + '/api/pdf/page-numbers', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.blob().then(function (blob) {
          var numbered = response.headers.get('X-Pages-Numbered');
          return {
            blob: blob,
            numberedCount: numbered ? parseInt(numbered, 10) : null
          };
        });
      })
      .then(function (result) {
        revokeDownload();
        state.downloadUrl = URL.createObjectURL(result.blob);

        var countText = (result.numberedCount !== null && !isNaN(result.numberedCount))
          ? result.numberedCount + ' halaman'
          : 'Dokumen';
        var summaryText = countText + ' diberi nomor, mulai dari ' + startNum;
        state.lastSummary = summaryText;

        if (el.summary) {
          el.summary.textContent = summaryText;
        }

        if (el.download) {
          el.download.href = state.downloadUrl;
          el.download.download = 'pdf-bernomor.pdf';
          el.download.hidden = false;
        }

        if (el.copy) {
          el.copy.hidden = false;
        }

        if (el.result) {
          el.result.hidden = false;
        }

        setStatus('Selesai: ' + summaryText + '. Tekan "Unduh PDF" untuk menyimpan.', 'ok');
        if (el.download) el.download.focus();
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

  function resetAll() {
    setFile(null);
    if (el.position) el.position.value = 'bawah-tengah';
    if (el.format) el.format.value = 'angka';
    if (el.start) el.start.value = '1';
    if (el.size) el.size.value = '11';
    if (el.pages) el.pages.value = '';
  }

  // --- Buka / tutup panel ---------------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="nomor-halaman"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'nomor-halaman-panel');
    }
  }

  function open() {
    if (!panel.hidden) return;
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);

    var reduceMotion = false;
    try {
      reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { /* diabaikan */ }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    if (el.fileInput) {
      setTimeout(function () {
        if (el.drop && !el.drop.hidden) {
          el.drop.focus();
        } else if (el.submit && !el.submit.disabled) {
          el.submit.focus();
        }
      }, 100);
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

  // --- Event Listeners ------------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  if (el.removeFile) el.removeFile.addEventListener('click', function () { setFile(null); });
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.submit) el.submit.addEventListener('click', submitJob);
  if (el.copy) el.copy.addEventListener('click', copySummary);

  if (el.fileInput) {
    el.fileInput.addEventListener('change', function (e) {
      var files = e.target.files;
      if (files && files.length > 0) {
        setFile(files[0]);
      }
    });
  }

  if (el.drop) {
    ['dragenter', 'dragover'].forEach(function (type) {
      el.drop.addEventListener(type, function (e) {
        e.preventDefault();
        e.stopPropagation();
        el.drop.classList.add('is-dragover');
      });
    });
    ['dragleave', 'dragend'].forEach(function (type) {
      el.drop.addEventListener(type, function (e) {
        e.preventDefault();
        e.stopPropagation();
        el.drop.classList.remove('is-dragover');
      });
    });
    el.drop.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('is-dragover');
      var files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length > 0) {
        setFile(files[0]);
      }
    });
  }

  function onKeydown(e) {
    if (panel.hidden) return;
    if (e.key === 'Escape' && panel.contains(document.activeElement)) {
      e.preventDefault();
      close();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      if (panel.contains(document.activeElement) && el.submit && !el.submit.disabled) {
        e.preventDefault();
        submitJob();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel ke daftar panel OmniTools
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['nomor-halaman'] = toggle;

  // Inisialisasi awal
  updateControls();
})();
