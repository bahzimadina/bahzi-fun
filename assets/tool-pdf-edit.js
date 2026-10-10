/* =========================================================================
   Alat: PDF Editor (Putar, Hapus, Susun Ulang Halaman PDF)
   Semua berkas diproses di layanan lewat memori, lalu langsung dibuang.
   ========================================================================= */
(function () {
  'use strict';

  var app = document.getElementById('pdfedit-app');
  if (!app) return;

  var el = {
    form: document.getElementById('pdfedit-form'),
    dropzone: document.getElementById('pdfedit-dropzone'),
    fileInput: document.getElementById('pdfedit-file-input'),
    browseBtn: document.getElementById('pdfedit-browse-btn'),
    dropHint: document.getElementById('pdfedit-drop-hint'),
    fileBox: document.getElementById('pdfedit-file-box'),
    fileBadge: document.getElementById('pdfedit-file-badge'),
    fileName: document.getElementById('pdfedit-file-name'),
    fileSize: document.getElementById('pdfedit-file-size'),
    filePages: document.getElementById('pdfedit-file-pages'),
    removeBtn: document.getElementById('pdfedit-remove-btn'),
    modeList: document.getElementById('pdfedit-mode-list'),
    panelPutar: document.getElementById('pdfedit-panel-putar'),
    panelHapus: document.getElementById('pdfedit-panel-hapus'),
    panelUrutkan: document.getElementById('pdfedit-panel-urutkan'),
    angleGroup: document.getElementById('pdfedit-angle-group'),
    inputPagesRotate: document.getElementById('pdfedit-input-pages-rotate'),
    inputPagesDelete: document.getElementById('pdfedit-input-pages-delete'),
    inputOrder: document.getElementById('pdfedit-input-order'),
    btnAutoOrder: document.getElementById('pdfedit-btn-auto-order'),
    submitBtn: document.getElementById('pdfedit-submit-btn'),
    resetBtn: document.getElementById('pdfedit-reset-btn'),
    status: document.getElementById('pdfedit-status'),
    results: document.getElementById('pdfedit-results'),
    resultsMeta: document.getElementById('pdfedit-results-meta'),
    summarySource: document.getElementById('pdfedit-summary-source'),
    summaryResult: document.getElementById('pdfedit-summary-result'),
    summaryAffected: document.getElementById('pdfedit-summary-affected'),
    infoText: document.getElementById('pdfedit-info-text'),
    downloadBtn: document.getElementById('pdfedit-download-btn'),
    copyBtn: document.getElementById('pdfedit-copy-btn'),
    noticeList: document.getElementById('pdfedit-notice-list'),
    limitsDesc: document.getElementById('pdfedit-limits-desc')
  };

  var state = {
    limits: {
      max_bytes: 25 * 1024 * 1024,
      max_mb: 25,
      max_pages: 300,
      modes: [
        { id: 'putar', label: 'Putar halaman' },
        { id: 'hapus', label: 'Hapus halaman' },
        { id: 'urutkan', label: 'Susun ulang urutan' }
      ],
      angles: [90, 180, 270],
      notes: []
    },
    selectedFile: null,
    pageCount: 0,
    currentMode: 'putar',
    downloadUrl: null,
    summaryText: '',
    busy: false
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
    el.status.className = 'status pdfedit__status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(message));
  }

  function updateLimitsUi() {
    if (el.limitsDesc) {
      el.limitsDesc.textContent = 'Batas berkas: maksimal ' + state.limits.max_mb + ' MB dan ' + state.limits.max_pages + ' halaman per dokumen.';
    }
    if (el.dropHint) {
      el.dropHint.textContent = 'Format didukung: PDF (maksimal ' + state.limits.max_mb + ' MB & ' + state.limits.max_pages + ' halaman)';
    }
    if (el.noticeList && state.limits.notes && state.limits.notes.length > 0) {
      el.noticeList.innerHTML = '';
      for (var i = 0; i < state.limits.notes.length; i++) {
        var li = document.createElement('li');
        li.textContent = state.limits.notes[i];
        el.noticeList.appendChild(li);
      }
    }
  }

  function renderModeOptions(modes) {
    if (!el.modeList) return;
    el.modeList.innerHTML = '';

    var actionModes = modes.filter(function (m) {
      return m.id !== 'info';
    });

    if (actionModes.length === 0) {
      actionModes = [
        { id: 'putar', label: 'Putar halaman' },
        { id: 'hapus', label: 'Hapus halaman' },
        { id: 'urutkan', label: 'Susun ulang urutan' }
      ];
    }

    actionModes.forEach(function (m, idx) {
      var label = document.createElement('label');
      label.className = 'pdfedit__mode-label';

      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'pdfedit-mode-radio';
      radio.value = m.id;
      if (idx === 0) {
        radio.checked = true;
        state.currentMode = m.id;
      }

      radio.addEventListener('change', function () {
        if (radio.checked) {
          switchMode(m.id);
        }
      });

      var span = document.createElement('span');
      span.className = 'pdfedit__mode-text';
      span.textContent = m.label || m.id;

      label.appendChild(radio);
      label.appendChild(span);
      el.modeList.appendChild(label);
    });

    switchMode(state.currentMode);
  }

  function switchMode(modeId) {
    state.currentMode = modeId;
    if (el.panelPutar) el.panelPutar.hidden = (modeId !== 'putar');
    if (el.panelHapus) el.panelHapus.hidden = (modeId !== 'hapus');
    if (el.panelUrutkan) el.panelUrutkan.hidden = (modeId !== 'urutkan');
  }

  function fetchLimits() {
    fetch('/api/pdf/edit/limits')
      .then(function (resp) {
        if (!resp.ok) throw new Error('Gagal membaca batas layanan.');
        return resp.json();
      })
      .then(function (data) {
        if (data.max_bytes) state.limits.max_bytes = data.max_bytes;
        if (data.max_mb) state.limits.max_mb = data.max_mb;
        if (data.max_pages) state.limits.max_pages = data.max_pages;
        if (data.modes && Array.isArray(data.modes)) state.limits.modes = data.modes;
        if (data.angles && Array.isArray(data.angles)) state.limits.angles = data.angles;
        if (data.notes && Array.isArray(data.notes)) state.limits.notes = data.notes;

        updateLimitsUi();
        renderModeOptions(state.limits.modes);
      })
      .catch(function () {
        updateLimitsUi();
        renderModeOptions(state.limits.modes);
      });
  }

  function updateControls() {
    var hasFile = !!state.selectedFile && state.pageCount > 0;
    if (el.submitBtn) {
      el.submitBtn.disabled = state.busy || !hasFile;
      el.submitBtn.textContent = state.busy ? 'Sedang memproses…' : 'Proses dokumen';
    }
    if (el.resetBtn) {
      el.resetBtn.disabled = state.busy || (!state.selectedFile && !state.downloadUrl);
    }
    if (el.browseBtn) el.browseBtn.disabled = state.busy;
    if (el.removeBtn) el.removeBtn.disabled = state.busy;
    if (el.fileInput) el.fileInput.disabled = state.busy;
    if (el.btnAutoOrder) el.btnAutoOrder.disabled = state.busy;
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

  function inspectFile(file) {
    setStatus('Membaca informasi dokumen…', 'busy');
    state.busy = true;
    updateControls();

    var formData = new FormData();
    formData.append('file', file);
    formData.append('mode', 'info');

    fetch('/api/pdf/edit', {
      method: 'POST',
      body: formData
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().then(function (errBody) {
            var msg = (errBody && errBody.error && errBody.error.message)
              ? errBody.error.message
              : 'Gagal membaca dokumen PDF.';
            throw new Error(msg);
          }).catch(function (parseErr) {
            if (parseErr && parseErr.message) throw parseErr;
            throw new Error('Gagal membaca dokumen PDF (status ' + resp.status + ').');
          });
        }
        return resp.json();
      })
      .then(function (info) {
        state.pageCount = info.page_count || 0;
        if (el.filePages) {
          el.filePages.textContent = 'Dokumen ini punya ' + state.pageCount + ' halaman.';
        }
        setStatus('Dokumen siap disunting. Pilih tindakan lalu klik Proses dokumen.', '');
      })
      .catch(function (err) {
        state.selectedFile = null;
        state.pageCount = 0;
        if (el.dropzone) el.dropzone.hidden = false;
        if (el.fileBox) el.fileBox.hidden = true;
        var rawMsg = (err && err.message) ? String(err.message) : '';
        var isNetworkError = /Failed to fetch|NetworkError|Load failed|TypeError/i.test(rawMsg);
        var msg = isNetworkError
          ? 'Tidak bisa menghubungi layanan. Periksa sambungan lalu coba lagi.'
          : (rawMsg || 'Terjadi kesalahan saat memeriksa dokumen.');
        setStatus(msg, 'error');
      })
      .finally(function () {
        state.busy = false;
        updateControls();
      });
  }

  function handleFileSelected(file) {
    if (!file) return;

    if (file.size > state.limits.max_bytes) {
      setStatus('Ukuran berkas melebihi batas ' + state.limits.max_mb + ' MB.', 'error');
      return;
    }

    checkPdfHeader(file, function (isValidPdf) {
      if (!isValidPdf) {
        setStatus('Berkas bukan dokumen PDF yang sah. Pilih berkas berekstensi .pdf.', 'error');
        return;
      }

      state.selectedFile = file;
      if (el.dropzone) el.dropzone.hidden = true;
      if (el.fileBox) el.fileBox.hidden = false;
      if (el.fileName) el.fileName.textContent = file.name;
      if (el.fileSize) el.fileSize.textContent = formatBytes(file.size);
      if (el.filePages) el.filePages.textContent = 'Menghitung halaman…';
      if (el.results) el.results.hidden = true;

      inspectFile(file);
    });
  }

  function parseFilenameFromHeader(header, fallback) {
    if (!header) return fallback;
    var match = /filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i.exec(header);
    if (match && match[1]) {
      try {
        return decodeURIComponent(match[1].trim());
      } catch (e) {
        return match[1].trim();
      }
    }
    return fallback;
  }

  function handleSubmit(e) {
    if (e) e.preventDefault();
    if (state.busy || !state.selectedFile || state.pageCount <= 0) return;

    var mode = state.currentMode;
    var angleVal = '90';
    var pagesVal = '';
    var orderVal = '';

    if (mode === 'putar') {
      var checkedAngle = document.querySelector('input[name="pdfedit-angle-radio"]:checked');
      if (checkedAngle) angleVal = checkedAngle.value;
      if (el.inputPagesRotate) pagesVal = el.inputPagesRotate.value.trim();
    } else if (mode === 'hapus') {
      if (el.inputPagesDelete) pagesVal = el.inputPagesDelete.value.trim();
      if (!pagesVal) {
        setStatus('Nomor halaman yang akan dihapus wajib diisi.', 'error');
        if (el.inputPagesDelete) el.inputPagesDelete.focus();
        return;
      }
    } else if (mode === 'urutkan') {
      if (el.inputOrder) orderVal = el.inputOrder.value.trim();
      if (!orderVal) {
        setStatus('Urutan nomor halaman wajib diisi.', 'error');
        if (el.inputOrder) el.inputOrder.focus();
        return;
      }
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang memproses dokumen…', 'busy');

    var formData = new FormData();
    formData.append('file', state.selectedFile);
    formData.append('mode', mode);

    if (mode === 'putar') {
      formData.append('angle', angleVal);
      if (pagesVal) formData.append('pages', pagesVal);
    } else if (mode === 'hapus') {
      formData.append('pages', pagesVal);
    } else if (mode === 'urutkan') {
      formData.append('order', orderVal);
    }

    fetch('/api/pdf/edit', {
      method: 'POST',
      body: formData
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().then(function (errBody) {
            var msg = (errBody && errBody.error && errBody.error.message)
              ? errBody.error.message
              : 'Gagal menyunting berkas PDF.';
            throw new Error(msg);
          }).catch(function (parseErr) {
            if (parseErr && parseErr.message) throw parseErr;
            throw new Error('Gagal menyunting berkas PDF (status ' + resp.status + ').');
          });
        }

        var sourcePages = parseInt(resp.headers.get('X-Source-Pages'), 10) || state.pageCount;
        var resultPages = parseInt(resp.headers.get('X-Result-Pages'), 10) || 0;
        var affectedPages = parseInt(resp.headers.get('X-Affected-Pages'), 10) || 0;
        var procMs = resp.headers.get('X-Processing-Ms');
        var filename = parseFilenameFromHeader(resp.headers.get('Content-Disposition'), 'editor-pdf.pdf');

        return resp.blob().then(function (blob) {
          return {
            blob: blob,
            filename: filename,
            sourcePages: sourcePages,
            resultPages: resultPages,
            affectedPages: affectedPages,
            mode: mode,
            angle: angleVal,
            sizeBytes: blob.size,
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
          el.downloadBtn.textContent = 'Unduh PDF';
        }

        if (el.summarySource) el.summarySource.textContent = res.sourcePages + ' halaman';
        if (el.summaryResult) el.summaryResult.textContent = res.resultPages + ' halaman';
        if (el.summaryAffected) el.summaryAffected.textContent = res.affectedPages + ' halaman';

        if (el.resultsMeta) {
          el.resultsMeta.textContent = res.filename + ' (' + formatBytes(res.sizeBytes) + ')';
        }

        var infoDetail = '';
        if (res.mode === 'putar') {
          infoDetail = res.affectedPages + ' halaman diputar ' + res.angle + ' derajat.';
        } else if (res.mode === 'hapus') {
          infoDetail = res.sourcePages + ' halaman jadi ' + res.resultPages + ' halaman (' + res.affectedPages + ' dihapus).';
        } else if (res.mode === 'urutkan') {
          infoDetail = 'Urutan ' + res.resultPages + ' halaman berhasil disusun ulang.';
        }

        if (el.infoText) {
          el.infoText.textContent = infoDetail;
        }

        state.summaryText = 'Hasil PDF Editor:\n' +
          '- Nama berkas: ' + res.filename + '\n' +
          '- Tindakan: ' + infoDetail + '\n' +
          '- Halaman awal: ' + res.sourcePages + '\n' +
          '- Halaman hasil: ' + res.resultPages + '\n' +
          '- Ukuran berkas: ' + formatBytes(res.sizeBytes);

        if (el.results) el.results.hidden = false;
        setStatus('Selesai! Berkas siap diunduh.', 'ok');
      })
      .catch(function (err) {
        var rawMsg = (err && err.message) ? String(err.message) : '';
        var isNetworkError = /Failed to fetch|NetworkError|Load failed|TypeError/i.test(rawMsg);
        var msg = isNetworkError
          ? 'Tidak bisa menghubungi layanan. Periksa sambungan lalu coba lagi.'
          : (rawMsg || 'Terjadi kesalahan saat memproses berkas.');
        setStatus(msg, 'error');
      })
      .finally(function () {
        state.busy = false;
        updateControls();
      });
  }

  function handleReset() {
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }
    state.selectedFile = null;
    state.pageCount = 0;
    state.summaryText = '';

    if (el.fileInput) el.fileInput.value = '';
    if (el.dropzone) el.dropzone.hidden = false;
    if (el.fileBox) el.fileBox.hidden = true;
    if (el.results) el.results.hidden = true;
    if (el.inputPagesRotate) el.inputPagesRotate.value = '';
    if (el.inputPagesDelete) el.inputPagesDelete.value = '';
    if (el.inputOrder) el.inputOrder.value = '';

    setStatus('Pilih berkas PDF untuk memulai.', '');
    updateControls();
    if (el.browseBtn && !el.browseBtn.disabled) el.browseBtn.focus();
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
      el.dropzone.classList.add('pdfedit__dropzone--active');
    });

    el.dropzone.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('pdfedit__dropzone--active');
    });

    el.dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('pdfedit__dropzone--active');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileSelected(e.dataTransfer.files[0]);
      }
    });

    el.dropzone.addEventListener('keydown', function (e) {
      if ((e.key === 'Enter' || e.key === ' ') && el.fileInput) {
        e.preventDefault();
        el.fileInput.click();
      }
    });
  }

  if (el.removeBtn) {
    el.removeBtn.addEventListener('click', handleReset);
  }

  if (el.btnAutoOrder) {
    el.btnAutoOrder.addEventListener('click', function () {
      if (state.pageCount <= 0) {
        setStatus('Pilih berkas PDF terlebih dahulu untuk mengetahui jumlah halaman.', 'error');
        return;
      }
      var arr = [];
      for (var i = 1; i <= state.pageCount; i++) {
        arr.push(i);
      }
      if (el.inputOrder) {
        el.inputOrder.value = arr.join(', ');
        el.inputOrder.focus();
      }
    });
  }

  if (el.form) {
    el.form.addEventListener('submit', handleSubmit);
  }

  if (el.resetBtn) {
    el.resetBtn.addEventListener('click', handleReset);
  }

  if (el.copyBtn) {
    el.copyBtn.addEventListener('click', copySummary);
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (el.results && !el.results.hidden) {
        if (el.submitBtn && !el.submitBtn.disabled) {
          el.submitBtn.focus();
        }
      }
    }
  });

  // Ambil data limits saat awal
  fetchLimits();
  updateControls();
})();
