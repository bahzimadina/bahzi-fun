/* =========================================================================
   Alat: Pisah PDF jadi beberapa berkas
   Berkas diproses di server lewat memori, lalu langsung dibuang.
   ========================================================================= */
(function () {
  'use strict';

  var app = document.getElementById('pisah-app');
  if (!app) return;

  var el = {
    form: document.getElementById('pisah-form'),
    dropzone: document.getElementById('pisah-dropzone'),
    fileInput: document.getElementById('pisah-file-input'),
    browseBtn: document.getElementById('pisah-browse-btn'),
    fileBox: document.getElementById('pisah-file-box'),
    fileBadge: document.getElementById('pisah-file-badge'),
    fileName: document.getElementById('pisah-file-name'),
    fileSize: document.getElementById('pisah-file-size'),
    removeBtn: document.getElementById('pisah-remove-btn'),
    pageInfo: document.getElementById('pisah-page-info'),
    pageInfoText: document.getElementById('pisah-page-info-text'),
    modeList: document.getElementById('pisah-mode-list'),
    fieldRange: document.getElementById('pisah-field-range'),
    inputPages: document.getElementById('pisah-input-pages'),
    rangeHint: document.getElementById('pisah-range-hint'),
    fieldChunk: document.getElementById('pisah-field-chunk'),
    inputChunk: document.getElementById('pisah-input-chunk'),
    submitBtn: document.getElementById('pisah-submit-btn'),
    resetBtn: document.getElementById('pisah-reset-btn'),
    status: document.getElementById('pisah-status'),
    results: document.getElementById('pisah-results'),
    resultsMeta: document.getElementById('pisah-results-meta'),
    summaryFiles: document.getElementById('pisah-summary-files'),
    summarySourcePages: document.getElementById('pisah-summary-source-pages'),
    summaryResultPages: document.getElementById('pisah-summary-result-pages'),
    summarySize: document.getElementById('pisah-summary-size'),
    summaryTime: document.getElementById('pisah-summary-time'),
    downloadBtn: document.getElementById('pisah-download-btn'),
    copyBtn: document.getElementById('pisah-copy-btn'),
    limitsDesc: document.getElementById('pisah-limits-desc')
  };

  var DEFAULT_MODES = [
    { id: 'per-halaman', label: 'Pisah setiap halaman' },
    { id: 'rentang', label: 'Ambil rentang halaman' },
    { id: 'setiap-n', label: 'Pisah per beberapa halaman' }
  ];

  var state = {
    limits: {
      max_file_bytes: 25 * 1024 * 1024,
      max_file_mb: 25,
      max_pages: 300,
      modes: DEFAULT_MODES,
      default_chunk: 5,
      min_chunk: 1,
      max_chunk: 100,
      sample_range: '1-3,5'
    },
    selectedFile: null,
    sourcePages: null,
    selectedMode: 'per-halaman',
    downloadUrl: null,
    summaryText: '',
    busy: false
  };

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) {
      return (bytes / 1024).toLocaleString('id-ID', { maximumFractionDigits: 1 }) + ' KB';
    }
    return (bytes / 1048576).toLocaleString('id-ID', { maximumFractionDigits: 1 }) + ' MB';
  }

  function setStatus(message, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status pisah__status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(message));
  }

  function updateLimitsDescription() {
    if (!el.limitsDesc) return;
    el.limitsDesc.textContent = 'Batas berkas: maksimal ' + state.limits.max_file_mb + ' MB dan ' + state.limits.max_pages + ' halaman per dokumen.';
  }

  function renderModeOptions(modes) {
    if (!el.modeList) return;
    el.modeList.textContent = '';

    modes.forEach(function (mode, idx) {
      var label = document.createElement('label');
      label.className = 'pisah__mode-label';

      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'pisah-mode-radio';
      input.value = mode.id;
      input.id = 'pisah-mode-opt-' + idx;
      input.checked = (mode.id === state.selectedMode);

      input.addEventListener('change', function () {
        if (input.checked) {
          state.selectedMode = mode.id;
          updateModeFields();
        }
      });

      var span = document.createElement('span');
      span.className = 'pisah__mode-name';
      span.textContent = mode.label;

      label.appendChild(input);
      label.appendChild(span);
      el.modeList.appendChild(label);
    });
  }

  function updateModeFields() {
    if (el.fieldRange) el.fieldRange.hidden = (state.selectedMode !== 'rentang');
    if (el.fieldChunk) el.fieldChunk.hidden = (state.selectedMode !== 'setiap-n');
  }

  function fetchLimits() {
    fetch('/api/pdf/split/limits')
      .then(function (resp) {
        if (!resp.ok) throw new Error('Gagal membaca batas.');
        return resp.json();
      })
      .then(function (data) {
        if (data.max_file_bytes) state.limits.max_file_bytes = data.max_file_bytes;
        if (data.max_file_mb) state.limits.max_file_mb = data.max_file_mb;
        if (data.max_pages) state.limits.max_pages = data.max_pages;
        if (data.default_chunk) state.limits.default_chunk = data.default_chunk;
        if (data.min_chunk) state.limits.min_chunk = data.min_chunk;
        if (data.max_chunk) state.limits.max_chunk = data.max_chunk;
        if (data.sample_range) state.limits.sample_range = data.sample_range;
        if (Array.isArray(data.modes) && data.modes.length > 0) {
          state.limits.modes = data.modes;
        }
        updateLimitsDescription();
        renderModeOptions(state.limits.modes);
      })
      .catch(function () {
        updateLimitsDescription();
        renderModeOptions(state.limits.modes);
      });
  }

  function updateControls() {
    var hasFile = !!state.selectedFile && (state.sourcePages !== null);
    if (el.submitBtn) {
      el.submitBtn.disabled = state.busy || !hasFile;
      el.submitBtn.textContent = state.busy ? 'Sedang memisah…' : 'Pisah PDF sekarang';
    }
    if (el.resetBtn) {
      el.resetBtn.disabled = state.busy || (!state.selectedFile && !state.downloadUrl);
    }
    if (el.browseBtn) el.browseBtn.disabled = state.busy;
    if (el.removeBtn) el.removeBtn.disabled = state.busy;
    if (el.fileInput) el.fileInput.disabled = state.busy;
    if (el.inputPages) el.inputPages.disabled = state.busy;
    if (el.inputChunk) el.inputChunk.disabled = state.busy;
    if (el.modeList) {
      var inputs = el.modeList.querySelectorAll('input');
      inputs.forEach(function (inp) { inp.disabled = state.busy; });
    }
  }

  function clearSelectedFile() {
    state.selectedFile = null;
    state.sourcePages = null;
    state.summaryText = '';
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }

    if (el.fileInput) el.fileInput.value = '';
    if (el.fileBox) el.fileBox.hidden = true;
    if (el.dropzone) el.dropzone.hidden = false;
    if (el.pageInfo) el.pageInfo.hidden = true;
    if (el.pageInfoText) el.pageInfoText.textContent = '';
    if (el.results) el.results.hidden = true;
    if (el.inputPages) el.inputPages.value = '';
    if (el.inputChunk) el.inputChunk.value = String(state.limits.default_chunk);

    setStatus('Pilih berkas PDF untuk memulai.', '');
    updateControls();
    if (el.browseBtn) {
      el.browseBtn.focus();
    }
  }

  function checkPdfHeader(file, callback) {
    if (!file) return callback(false);
    var isExtPdf = /\.pdf$/i.test(file.name) || file.type === 'application/pdf';
    if (!isExtPdf) return callback(false);

    if (typeof file.slice === 'function') {
      var blobSlice = file.slice(0, 5);
      var reader = new FileReader();
      reader.onload = function () {
        var str = reader.result;
        callback(typeof str === 'string' && str.indexOf('%PDF-') === 0);
      };
      reader.onerror = function () {
        callback(isExtPdf);
      };
      reader.readAsText(blobSlice);
    } else {
      callback(isExtPdf);
    }
  }

  function handleFileSelected(file) {
    if (!file) return;

    if (file.size > state.limits.max_file_bytes) {
      setStatus('Ukuran berkas melebihi batas ' + state.limits.max_file_mb + ' MB.', 'error');
      return;
    }

    checkPdfHeader(file, function (isValidPdf) {
      if (!isValidPdf) {
        setStatus('Berkas bukan PDF yang sah. Pilih berkas dokumen berekstensi .pdf.', 'error');
        return;
      }

      state.selectedFile = file;
      state.sourcePages = null;
      if (el.dropzone) el.dropzone.hidden = true;
      if (el.fileBox) el.fileBox.hidden = false;
      if (el.fileName) el.fileName.textContent = file.name;
      if (el.fileSize) el.fileSize.textContent = formatBytes(file.size);
      if (el.results) el.results.hidden = true;

      setStatus('Sedang membaca berkas…', 'busy');
      updateControls();

      // Minta inspeksi info jumlah halaman ke server
      var formData = new FormData();
      formData.append('file', file);
      formData.append('mode', 'info');

      fetch('/api/pdf/split', {
        method: 'POST',
        body: formData
      })
        .then(function (resp) {
          return resp.text().then(function (text) {
            var data;
            try {
              data = JSON.parse(text);
            } catch (err) {
              throw new Error('Koneksi ke server terputus. Coba lagi sebentar lagi.');
            }
            if (!resp.ok) {
              var msg = data && data.error && data.error.message
                ? data.error.message
                : 'Berkas tidak dapat dibaca oleh server.';
              throw new Error(msg);
            }
            return data;
          });
        })
        .then(function (info) {
          state.sourcePages = info.page_count;
          if (el.pageInfo && el.pageInfoText) {
            el.pageInfoText.textContent = 'Dokumen ini punya ' + info.page_count + ' halaman.';
            el.pageInfo.hidden = false;
          }
          if (el.rangeHint) {
            var sampleEnd = Math.min(3, info.page_count);
            var sampleStr = sampleEnd > 1 ? ('1-' + sampleEnd) : '1';
            if (info.page_count >= 5) sampleStr += ',5';
            el.rangeHint.textContent = 'Tulis nomor atau rentang halaman dipisah koma, misalnya ' + sampleStr + ' (maksimal halaman ' + info.page_count + ').';
          }
          setStatus('Dokumen siap dipisah. Pilih cara memisah lalu tekan tombol untuk memulai.', '');
          updateControls();
        })
        .catch(function (err) {
          state.selectedFile = null;
          state.sourcePages = null;
          if (el.fileBox) el.fileBox.hidden = true;
          if (el.dropzone) el.dropzone.hidden = false;
          setStatus(err.message || 'Koneksi ke server terputus. Coba lagi sebentar lagi.', 'error');
          updateControls();
        });
    });
  }

  function submitSplit(e) {
    if (e) e.preventDefault();
    if (state.busy) return;

    if (!state.selectedFile) {
      setStatus('Pilih berkas PDF terlebih dahulu.', 'error');
      return;
    }

    var mode = state.selectedMode;
    var pagesVal = '';
    var chunkVal = '';

    if (mode === 'rentang') {
      pagesVal = el.inputPages ? el.inputPages.value.trim() : '';
      if (!pagesVal) {
        setStatus('Tulis rentang halaman yang ingin diambil, misalnya 1-3,5.', 'error');
        if (el.inputPages) el.inputPages.focus();
        return;
      }
    } else if (mode === 'setiap-n') {
      chunkVal = el.inputChunk ? el.inputChunk.value.trim() : '';
      var chunkNum = parseInt(chunkVal, 10);
      if (isNaN(chunkNum) || chunkNum < 1 || chunkNum > 100) {
        setStatus('Jumlah halaman per berkas harus berupa angka antara 1 sampai 100.', 'error');
        if (el.inputChunk) el.inputChunk.focus();
        return;
      }
    }

    var formData = new FormData();
    formData.append('file', state.selectedFile);
    formData.append('mode', mode);
    if (mode === 'rentang') {
      formData.append('pages', pagesVal);
    } else if (mode === 'setiap-n') {
      formData.append('chunk', chunkVal);
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang memisah…', 'busy');

    fetch('/api/pdf/split', {
      method: 'POST',
      body: formData
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.text().then(function (text) {
            var data;
            try {
              data = JSON.parse(text);
            } catch (err) {
              throw new Error('Koneksi ke server terputus. Coba lagi sebentar lagi.');
            }
            var msg = data && data.error && data.error.message
              ? data.error.message
              : 'Pemisahan gagal diproses oleh server.';
            throw new Error(msg);
          });
        }

        var kind = resp.headers.get('X-Output-Kind') || 'pdf';
        var fileCount = resp.headers.get('X-Output-Count') || '1';
        var sourcePages = resp.headers.get('X-Source-Pages') || (state.sourcePages ? String(state.sourcePages) : '-');
        var resultPages = resp.headers.get('X-Result-Pages') || '-';
        var procMs = resp.headers.get('X-Processing-Ms');

        var disp = resp.headers.get('Content-Disposition') || '';
        var filenameMatch = disp.match(/filename="?([^";]+)"?/i);
        var filename = filenameMatch ? filenameMatch[1] : (kind === 'zip' ? 'pisah-pdf.zip' : 'pisah-pdf.pdf');

        return resp.blob().then(function (blob) {
          return {
            blob: blob,
            filename: filename,
            kind: kind,
            fileCount: fileCount,
            sourcePages: sourcePages,
            resultPages: resultPages,
            procMs: procMs
          };
        });
      })
      .then(function (res) {
        if (state.downloadUrl) {
          URL.revokeObjectURL(state.downloadUrl);
        }
        state.downloadUrl = URL.createObjectURL(res.blob);

        if (el.downloadBtn) {
          el.downloadBtn.href = state.downloadUrl;
          el.downloadBtn.download = res.filename;
        }

        if (el.summaryFiles) el.summaryFiles.textContent = res.fileCount + ' berkas';
        if (el.summarySourcePages) el.summarySourcePages.textContent = res.sourcePages + ' halaman';
        if (el.summaryResultPages) el.summaryResultPages.textContent = res.resultPages + ' halaman';
        if (el.summarySize) el.summarySize.textContent = formatBytes(res.blob.size);
        if (el.summaryTime) {
          var timeStr = res.procMs ? (parseInt(res.procMs, 10) + ' ms') : '-';
          el.summaryTime.textContent = timeStr;
        }

        if (el.resultsMeta) {
          el.resultsMeta.textContent = res.filename + ' (' + formatBytes(res.blob.size) + ')';
        }

        state.summaryText = 'Hasil pemisahan PDF:\n' +
          '- Nama berkas: ' + res.filename + '\n' +
          '- Jumlah berkas: ' + res.fileCount + '\n' +
          '- Dokumen asal: ' + res.sourcePages + ' halaman\n' +
          '- Dokumen hasil: ' + res.resultPages + ' halaman\n' +
          '- Ukuran hasil: ' + formatBytes(res.blob.size);

        if (el.results) el.results.hidden = false;
        setStatus('Pemisahan selesai. Berkas siap diunduh.', 'ok');
      })
      .catch(function (err) {
        var msg = err.message || 'Koneksi ke server terputus. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
      })
      .finally(function () {
        state.busy = false;
        updateControls();
      });
  }

  function copySummary() {
    if (!state.summaryText) return;

    function fallbackCopy() {
      var ta = document.createElement('textarea');
      ta.value = state.summaryText;
      ta.style.position = 'fixed';
      ta.style.top = '0';
      ta.style.left = '0';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        document.execCommand('copy');
        setStatus('Ringkasan disalin ke papan klip.', 'ok');
      } catch (err) {
        setStatus('Gagal menyalin ringkasan.', 'error');
      }
      document.body.removeChild(ta);
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(state.summaryText)
        .then(function () {
          setStatus('Ringkasan disalin ke papan klip.', 'ok');
        })
        .catch(function () {
          fallbackCopy();
        });
    } else {
      fallbackCopy();
    }
  }

  // --- Penanganan event ----------------------------------------------------
  if (el.browseBtn && el.fileInput) {
    el.browseBtn.addEventListener('click', function () {
      el.fileInput.click();
    });
  }

  if (el.fileInput) {
    el.fileInput.addEventListener('change', function () {
      if (el.fileInput.files && el.fileInput.files.length > 0) {
        handleFileSelected(el.fileInput.files[0]);
      }
    });
  }

  if (el.dropzone) {
    el.dropzone.addEventListener('dragover', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.add('pisah__dropzone--active');
    });

    el.dropzone.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('pisah__dropzone--active');
    });

    el.dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('pisah__dropzone--active');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileSelected(e.dataTransfer.files[0]);
      }
    });

    el.dropzone.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        if (el.fileInput) el.fileInput.click();
      }
    });
  }

  if (el.removeBtn) {
    el.removeBtn.addEventListener('click', clearSelectedFile);
  }

  if (el.resetBtn) {
    el.resetBtn.addEventListener('click', clearSelectedFile);
  }

  if (el.form) {
    el.form.addEventListener('submit', submitSplit);
  }

  if (el.copyBtn) {
    el.copyBtn.addEventListener('click', copySummary);
  }

  // Inisialisasi awal
  renderModeOptions(state.limits.modes);
  updateModeFields();
  fetchLimits();
  updateControls();
})();
