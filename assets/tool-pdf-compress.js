/* =========================================================================
   Alat: Perkecil PDF (Compress PDF)
   Berkas diproses di server lewat memori, lalu langsung dibuang.
   ========================================================================= */
(function () {
  'use strict';

  var app = document.getElementById('kompres-app');
  if (!app) return;

  var el = {
    form: document.getElementById('kompres-form'),
    dropzone: document.getElementById('kompres-dropzone'),
    fileInput: document.getElementById('kompres-file-input'),
    browseBtn: document.getElementById('kompres-browse-btn'),
    fileBox: document.getElementById('kompres-file-box'),
    fileBadge: document.getElementById('kompres-file-badge'),
    fileName: document.getElementById('kompres-file-name'),
    fileSize: document.getElementById('kompres-file-size'),
    removeBtn: document.getElementById('kompres-remove-btn'),
    modeList: document.getElementById('kompres-mode-list'),
    fieldCustom: document.getElementById('kompres-field-custom'),
    inputDpi: document.getElementById('kompres-input-dpi'),
    valDpi: document.getElementById('kompres-val-dpi'),
    inputQuality: document.getElementById('kompres-input-quality'),
    valQuality: document.getElementById('kompres-val-quality'),
    submitBtn: document.getElementById('kompres-submit-btn'),
    resetBtn: document.getElementById('kompres-reset-btn'),
    status: document.getElementById('kompres-status'),
    results: document.getElementById('kompres-results'),
    resultsMeta: document.getElementById('kompres-results-meta'),
    summaryBefore: document.getElementById('kompres-summary-before'),
    summaryAfter: document.getElementById('kompres-summary-after'),
    summarySaved: document.getElementById('kompres-summary-saved'),
    notesBox: document.getElementById('kompres-notes'),
    notesText: document.getElementById('kompres-notes-text'),
    downloadBtn: document.getElementById('kompres-download-btn'),
    copyBtn: document.getElementById('kompres-copy-btn'),
    limitsDesc: document.getElementById('kompres-limits-desc')
  };

  var DEFAULT_MODES = [
    {
      id: 'ringan',
      label: 'Ringan',
      desc: 'Bersihkan struktur berkas tanpa mengubah tampilan. Teks tetap utuh dan bisa dipilih.',
      keep_text: true
    },
    {
      id: 'sedang',
      label: 'Sedang',
      desc: 'Turunkan resolusi gambar berlebih secara seimbang. Teks tetap utuh dan bisa dipilih.',
      keep_text: true
    },
    {
      id: 'kuat',
      label: 'Kuat',
      desc: 'Ubah seluruh halaman menjadi gambar JPEG beresolusi hemat. Teks tidak bisa dipilih lagi. Cocok untuk dokumen hasil pindai atau foto.',
      keep_text: false
    }
  ];

  var state = {
    limits: {
      max_file_bytes: 25 * 1024 * 1024,
      max_file_mb: 25,
      max_pages: 300,
      modes: DEFAULT_MODES,
      dpi_min: 72,
      dpi_max: 200,
      dpi_default: 110,
      quality_min: 30,
      quality_max: 95,
      quality_default: 60
    },
    selectedFile: null,
    selectedMode: 'sedang',
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
    el.status.className = 'status kompres__status' + (kind ? ' status--' + kind : '');
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
      label.className = 'kompres__mode-label';

      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'kompres-mode-radio';
      input.value = mode.id;
      input.id = 'kompres-mode-opt-' + idx;
      input.checked = (mode.id === state.selectedMode);

      input.addEventListener('change', function () {
        if (input.checked) {
          state.selectedMode = mode.id;
          updateModeFields();
        }
      });

      var textWrap = document.createElement('div');
      textWrap.className = 'kompres__mode-text';

      var spanTitle = document.createElement('span');
      spanTitle.className = 'kompres__mode-name';
      spanTitle.textContent = mode.label;

      var spanDesc = document.createElement('span');
      spanDesc.className = 'kompres__mode-desc';
      spanDesc.textContent = mode.desc;

      textWrap.appendChild(spanTitle);
      textWrap.appendChild(spanDesc);

      label.appendChild(input);
      label.appendChild(textWrap);
      el.modeList.appendChild(label);
    });
  }

  function updateModeFields() {
    if (el.fieldCustom) {
      el.fieldCustom.hidden = (state.selectedMode !== 'kuat');
    }
  }

  function fetchLimits() {
    fetch('/api/pdf/compress/limits')
      .then(function (resp) {
        if (!resp.ok) throw new Error('Gagal membaca batas.');
        return resp.json();
      })
      .then(function (data) {
        if (data.max_file_bytes) state.limits.max_file_bytes = data.max_file_bytes;
        if (data.max_file_mb) state.limits.max_file_mb = data.max_file_mb;
        if (data.max_pages) state.limits.max_pages = data.max_pages;
        if (data.dpi_min) state.limits.dpi_min = data.dpi_min;
        if (data.dpi_max) state.limits.dpi_max = data.dpi_max;
        if (data.dpi_default) state.limits.dpi_default = data.dpi_default;
        if (data.quality_min) state.limits.quality_min = data.quality_min;
        if (data.quality_max) state.limits.quality_max = data.quality_max;
        if (data.quality_default) state.limits.quality_default = data.quality_default;
        if (Array.isArray(data.modes) && data.modes.length > 0) {
          state.limits.modes = data.modes;
        }

        if (el.inputDpi) {
          el.inputDpi.min = String(state.limits.dpi_min);
          el.inputDpi.max = String(state.limits.dpi_max);
          el.inputDpi.value = String(state.limits.dpi_default);
          if (el.valDpi) el.valDpi.textContent = String(state.limits.dpi_default);
        }
        if (el.inputQuality) {
          el.inputQuality.min = String(state.limits.quality_min);
          el.inputQuality.max = String(state.limits.quality_max);
          el.inputQuality.value = String(state.limits.quality_default);
          if (el.valQuality) el.valQuality.textContent = String(state.limits.quality_default);
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
    var hasFile = !!state.selectedFile;
    if (el.submitBtn) {
      el.submitBtn.disabled = state.busy || !hasFile;
      el.submitBtn.textContent = state.busy ? 'Sedang memperkecil…' : 'Perkecil PDF sekarang';
    }
    if (el.resetBtn) {
      el.resetBtn.disabled = state.busy || (!state.selectedFile && !state.downloadUrl);
    }
    if (el.browseBtn) el.browseBtn.disabled = state.busy;
    if (el.removeBtn) el.removeBtn.disabled = state.busy;
    if (el.fileInput) el.fileInput.disabled = state.busy;
    if (el.inputDpi) el.inputDpi.disabled = state.busy;
    if (el.inputQuality) el.inputQuality.disabled = state.busy;
    if (el.modeList) {
      var inputs = el.modeList.querySelectorAll('input');
      inputs.forEach(function (inp) { inp.disabled = state.busy; });
    }
  }

  function clearSelectedFile() {
    state.selectedFile = null;
    state.summaryText = '';
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }

    if (el.fileInput) el.fileInput.value = '';
    if (el.fileBox) el.fileBox.hidden = true;
    if (el.dropzone) el.dropzone.hidden = false;
    if (el.results) el.results.hidden = true;

    if (el.inputDpi) {
      el.inputDpi.value = String(state.limits.dpi_default);
      if (el.valDpi) el.valDpi.textContent = String(state.limits.dpi_default);
    }
    if (el.inputQuality) {
      el.inputQuality.value = String(state.limits.quality_default);
      if (el.valQuality) el.valQuality.textContent = String(state.limits.quality_default);
    }

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
      if (el.dropzone) el.dropzone.hidden = true;
      if (el.fileBox) el.fileBox.hidden = false;
      if (el.fileName) el.fileName.textContent = file.name;
      if (el.fileSize) el.fileSize.textContent = formatBytes(file.size);
      if (el.results) el.results.hidden = true;

      setStatus('Berkas siap diperkecil. Pilih tingkat kompresi lalu klik tombol di bawah.', '');
      updateControls();
    });
  }

  function submitCompress(e) {
    if (e) e.preventDefault();
    if (state.busy) return;

    if (!state.selectedFile) {
      setStatus('Pilih berkas PDF terlebih dahulu.', 'error');
      return;
    }

    var mode = state.selectedMode;
    var formData = new FormData();
    formData.append('file', state.selectedFile);
    formData.append('mode', mode);

    if (mode === 'kuat') {
      if (el.inputDpi) formData.append('dpi', el.inputDpi.value);
      if (el.inputQuality) formData.append('quality', el.inputQuality.value);
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang memperkecil…', 'busy');

    fetch('/api/pdf/compress', {
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
              : 'Kompresi gagal diproses oleh server.';
            throw new Error(msg);
          });
        }

        var sizeBefore = parseInt(resp.headers.get('X-Size-Before'), 10) || state.selectedFile.size;
        var sizeAfter = parseInt(resp.headers.get('X-Size-After'), 10) || 0;
        var savedPercent = resp.headers.get('X-Saved-Percent') || '0';
        var pageCount = resp.headers.get('X-Page-Count') || '-';
        var modeUsed = resp.headers.get('X-Mode') || mode;
        var usedOriginal = resp.headers.get('X-Used-Original') === 'true';
        var notes = resp.headers.get('X-Notes') || '';
        var procMs = resp.headers.get('X-Processing-Ms');

        return resp.blob().then(function (blob) {
          return {
            blob: blob,
            filename: 'kompres-pdf.pdf',
            sizeBefore: sizeBefore,
            sizeAfter: blob.size || sizeAfter,
            savedPercent: savedPercent,
            pageCount: pageCount,
            modeUsed: modeUsed,
            usedOriginal: usedOriginal,
            notes: notes,
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

        var savedDisplay = (res.savedPercent !== null && res.savedPercent !== undefined && res.savedPercent !== '')
          ? String(res.savedPercent)
          : '0';

        if (el.summaryBefore) el.summaryBefore.textContent = formatBytes(res.sizeBefore);
        if (el.summaryAfter) el.summaryAfter.textContent = formatBytes(res.sizeAfter);
        if (el.summarySaved) el.summarySaved.textContent = savedDisplay + '%';

        if (el.resultsMeta) {
          el.resultsMeta.textContent = res.filename + ' (' + formatBytes(res.blob.size) + ')';
        }

        if (el.notesBox && el.notesText) {
          if (res.notes) {
            el.notesText.textContent = res.notes;
            el.notesBox.hidden = false;
          } else {
            el.notesBox.hidden = true;
          }
        }

        state.summaryText = 'Hasil kompresi PDF:\n' +
          '- Nama berkas: ' + res.filename + '\n' +
          '- Ukuran awal: ' + formatBytes(res.sizeBefore) + '\n' +
          '- Ukuran akhir: ' + formatBytes(res.sizeAfter) + '\n' +
          '- Penghematan: ' + savedDisplay + '%\n' +
          (res.notes ? ('- Catatan: ' + res.notes + '\n') : '');

        var savedNum = parseFloat(savedDisplay);
        if (isNaN(savedNum)) {
          savedNum = 0;
        }

        var statusMsg;
        if (res.usedOriginal) {
          statusMsg = 'Berkas Anda sudah efisien, jadi ukurannya tidak bisa diperkecil lagi. Berkas asli tetap siap diunduh.';
        } else if (savedNum <= 0 || savedNum < 1) {
          statusMsg = 'Selesai, tetapi penghematannya sangat kecil karena berkas sudah efisien. Coba tingkat lain bila ingin lebih ringan.';
        } else {
          statusMsg = 'PDF berhasil diperkecil. Berkas siap diunduh.';
        }

        if (el.results) el.results.hidden = false;
        setStatus(statusMsg, 'ok');
      })
      .catch(function (err) {
        var rawMsg = (err && err.message) ? String(err.message) : (typeof err === 'string' ? err : '');
        var isNetworkError = (err instanceof TypeError) ||
          (err && err.name === 'TypeError') ||
          /Failed to fetch|NetworkError|Load failed|Network request failed|TypeError/i.test(rawMsg);
        var msg = isNetworkError
          ? 'Tidak bisa menghubungi server. Periksa sambungan internet Anda lalu coba lagi.'
          : (rawMsg || 'Koneksi ke server terputus. Coba lagi sebentar lagi.');
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
      el.dropzone.classList.add('kompres__dropzone--active');
    });

    el.dropzone.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('kompres__dropzone--active');
    });

    el.dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('kompres__dropzone--active');
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

  if (el.inputDpi && el.valDpi) {
    el.inputDpi.addEventListener('input', function () {
      el.valDpi.textContent = el.inputDpi.value;
    });
  }

  if (el.inputQuality && el.valQuality) {
    el.inputQuality.addEventListener('input', function () {
      el.valQuality.textContent = el.inputQuality.value;
    });
  }

  if (el.removeBtn) {
    el.removeBtn.addEventListener('click', clearSelectedFile);
  }

  if (el.resetBtn) {
    el.resetBtn.addEventListener('click', clearSelectedFile);
  }

  if (el.form) {
    el.form.addEventListener('submit', submitCompress);
  }

  if (el.copyBtn) {
    el.copyBtn.addEventListener('click', copySummary);
  }

  // Bilah persetujuan cookie (Consent Mode v2)
  var cookieBar = document.getElementById('cookiebar');
  if (cookieBar) {
    var okBtn = document.getElementById('cookiebar-ok');
    var tolakBtn = document.getElementById('cookiebar-tolak');
    var COOKIE_STORAGE_KEY = 'bahzi-cookie-consent';

    var savedConsent = null;
    try {
      savedConsent = localStorage.getItem(COOKIE_STORAGE_KEY);
      if (savedConsent !== 'granted' && savedConsent !== 'denied') {
        if (localStorage.getItem('bahzi-cookie-ok') === '1') savedConsent = 'granted';
        else savedConsent = null;
      }
    } catch (e) {}

    function updateConsent(val) {
      if (typeof window.gtag === 'function') {
        window.gtag('consent', 'update', {
          ad_storage: val,
          ad_user_data: val,
          ad_personalization: val,
          analytics_storage: val
        });
      }
    }

    if (savedConsent) {
      updateConsent(savedConsent);
    } else {
      cookieBar.hidden = false;
      document.body.classList.add('has-cookiebar');
    }

    function closeCookiebar(val) {
      try { localStorage.setItem(COOKIE_STORAGE_KEY, val); } catch (e) {}
      updateConsent(val);
      cookieBar.hidden = true;
      document.body.classList.remove('has-cookiebar');
    }

    if (okBtn) okBtn.addEventListener('click', function () { closeCookiebar('granted'); });
    if (tolakBtn) tolakBtn.addEventListener('click', function () { closeCookiebar('denied'); });
  }

  // Inisialisasi awal
  renderModeOptions(state.limits.modes);
  updateModeFields();
  fetchLimits();
  updateControls();
})();
