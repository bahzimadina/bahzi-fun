/* =========================================================================
   Alat: PDF ke gambar (PDF to PNG / JPG)
   Semua berkas diproses di server lewat memori, lalu langsung dibuang.
   ========================================================================= */
(function () {
  'use strict';

  var app = document.getElementById('pdfimg-app');
  if (!app) return;

  var el = {
    form: document.getElementById('pdfimg-form'),
    dropzone: document.getElementById('pdfimg-dropzone'),
    fileInput: document.getElementById('pdfimg-file-input'),
    browseBtn: document.getElementById('pdfimg-browse-btn'),
    fileBox: document.getElementById('pdfimg-file-box'),
    fileBadge: document.getElementById('pdfimg-file-badge'),
    fileName: document.getElementById('pdfimg-file-name'),
    fileSize: document.getElementById('pdfimg-file-size'),
    removeBtn: document.getElementById('pdfimg-remove-btn'),
    formatPng: document.getElementById('pdfimg-format-png'),
    formatJpg: document.getElementById('pdfimg-format-jpg'),
    fieldQuality: document.getElementById('pdfimg-field-quality'),
    inputDpi: document.getElementById('pdfimg-input-dpi'),
    valDpi: document.getElementById('pdfimg-val-dpi'),
    inputQuality: document.getElementById('pdfimg-input-quality'),
    valQuality: document.getElementById('pdfimg-val-quality'),
    submitBtn: document.getElementById('pdfimg-submit-btn'),
    resetBtn: document.getElementById('pdfimg-reset-btn'),
    status: document.getElementById('pdfimg-status'),
    results: document.getElementById('pdfimg-results'),
    resultsMeta: document.getElementById('pdfimg-results-meta'),
    summaryPages: document.getElementById('pdfimg-summary-pages'),
    summaryFormat: document.getElementById('pdfimg-summary-format'),
    summarySize: document.getElementById('pdfimg-summary-size'),
    infoText: document.getElementById('pdfimg-info-text'),
    previewWrap: document.getElementById('pdfimg-preview-wrap'),
    previewImg: document.getElementById('pdfimg-preview-img'),
    downloadBtn: document.getElementById('pdfimg-download-btn'),
    copyBtn: document.getElementById('pdfimg-copy-btn'),
    limitsDesc: document.getElementById('pdfimg-limits-desc')
  };

  var state = {
    limits: {
      max_file_bytes: 25 * 1024 * 1024,
      max_file_mb: 25,
      max_pages: 50,
      min_dpi: 72,
      max_dpi: 200,
      default_dpi: 150,
      min_quality: 30,
      max_quality: 95,
      default_quality: 85
    },
    selectedFile: null,
    selectedFormat: 'png',
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
    el.status.className = 'status pdfimg__status' + (kind ? ' status--' + kind : '');
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

  function updateFormatFields() {
    if (el.formatJpg && el.formatJpg.checked) {
      state.selectedFormat = 'jpg';
      if (el.fieldQuality) el.fieldQuality.hidden = false;
    } else {
      state.selectedFormat = 'png';
      if (el.fieldQuality) el.fieldQuality.hidden = true;
    }
  }

  function fetchLimits() {
    fetch('/api/pdf/to-image/limits')
      .then(function (resp) {
        if (!resp.ok) throw new Error('Gagal membaca batas layanan.');
        return resp.json();
      })
      .then(function (data) {
        if (data.max_file_bytes) state.limits.max_file_bytes = data.max_file_bytes;
        if (data.max_file_mb) state.limits.max_file_mb = data.max_file_mb;
        if (data.max_pages) state.limits.max_pages = data.max_pages;
        if (data.min_dpi) state.limits.min_dpi = data.min_dpi;
        if (data.max_dpi) state.limits.max_dpi = data.max_dpi;
        if (data.default_dpi) state.limits.default_dpi = data.default_dpi;
        if (data.min_quality) state.limits.min_quality = data.min_quality;
        if (data.max_quality) state.limits.max_quality = data.max_quality;
        if (data.default_quality) state.limits.default_quality = data.default_quality;

        if (el.inputDpi) {
          el.inputDpi.min = String(state.limits.min_dpi);
          el.inputDpi.max = String(state.limits.max_dpi);
          el.inputDpi.value = String(state.limits.default_dpi);
          if (el.valDpi) el.valDpi.textContent = String(state.limits.default_dpi);
        }
        if (el.inputQuality) {
          el.inputQuality.min = String(state.limits.min_quality);
          el.inputQuality.max = String(state.limits.max_quality);
          el.inputQuality.value = String(state.limits.default_quality);
          if (el.valQuality) el.valQuality.textContent = String(state.limits.default_quality);
        }

        updateLimitsDescription();
      })
      .catch(function () {
        updateLimitsDescription();
      });
  }

  function updateControls() {
    var hasFile = !!state.selectedFile;
    if (el.submitBtn) {
      el.submitBtn.disabled = state.busy || !hasFile;
      el.submitBtn.textContent = state.busy ? 'Sedang mengubah…' : 'Ubah jadi gambar';
    }
    if (el.resetBtn) {
      el.resetBtn.disabled = state.busy || (!state.selectedFile && !state.downloadUrl);
    }
    if (el.browseBtn) el.browseBtn.disabled = state.busy;
    if (el.removeBtn) el.removeBtn.disabled = state.busy;
    if (el.fileInput) el.fileInput.disabled = state.busy;
    if (el.formatPng) el.formatPng.disabled = state.busy;
    if (el.formatJpg) el.formatJpg.disabled = state.busy;
    if (el.inputDpi) el.inputDpi.disabled = state.busy;
    if (el.inputQuality) el.inputQuality.disabled = state.busy;
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
    if (el.previewWrap) el.previewWrap.hidden = true;
    if (el.previewImg) el.previewImg.removeAttribute('src');

    if (el.formatPng) el.formatPng.checked = true;
    updateFormatFields();

    if (el.inputDpi) {
      el.inputDpi.value = String(state.limits.default_dpi);
      if (el.valDpi) el.valDpi.textContent = String(state.limits.default_dpi);
    }
    if (el.inputQuality) {
      el.inputQuality.value = String(state.limits.default_quality);
      if (el.valQuality) el.valQuality.textContent = String(state.limits.default_quality);
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
      if (el.previewWrap) el.previewWrap.hidden = true;
      if (el.previewImg) el.previewImg.removeAttribute('src');

      setStatus('Berkas siap diubah. Pilih format dan resolusi lalu klik tombol di bawah.', '');
      updateControls();
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

  function submitToImage(e) {
    if (e) e.preventDefault();
    if (state.busy) return;

    if (!state.selectedFile) {
      setStatus('Pilih berkas PDF terlebih dahulu.', 'error');
      return;
    }

    var fmt = state.selectedFormat;
    var dpiVal = el.inputDpi ? el.inputDpi.value : String(state.limits.default_dpi);

    var formData = new FormData();
    formData.append('file', state.selectedFile);
    formData.append('format', fmt);
    formData.append('dpi', dpiVal);

    if (fmt === 'jpg' && el.inputQuality) {
      formData.append('quality', el.inputQuality.value);
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang merender halaman menjadi gambar…', 'busy');

    fetch('/api/pdf/to-image', {
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
              throw new Error('Tidak bisa menghubungi server. Periksa sambungan lalu coba lagi.');
            }
            var msg = data && data.error && data.error.message
              ? data.error.message
              : 'Gagal memproses berkas PDF.';
            throw new Error(msg);
          });
        }

        var pageCount = parseInt(resp.headers.get('X-Page-Count'), 10) || 1;
        var imageCount = parseInt(resp.headers.get('X-Image-Count'), 10) || pageCount;
        var outputKind = resp.headers.get('X-Output-Kind') || (pageCount > 1 ? 'zip' : 'image');
        var imageFmt = (resp.headers.get('X-Image-Format') || fmt).toUpperCase();
        var dpiUsed = resp.headers.get('X-Dpi') || dpiVal;
        var totalBytes = parseInt(resp.headers.get('X-Total-Bytes'), 10) || 0;
        var procMs = resp.headers.get('X-Processing-Ms');
        var defaultName = outputKind === 'zip' ? 'halaman-pdf.zip' : ('halaman-1.' + fmt.toLowerCase());
        var filename = parseFilenameFromHeader(resp.headers.get('Content-Disposition'), defaultName);

        return resp.blob().then(function (blob) {
          return {
            blob: blob,
            filename: filename,
            pageCount: pageCount,
            imageCount: imageCount,
            outputKind: outputKind,
            imageFmt: imageFmt,
            dpi: dpiUsed,
            sizeBytes: blob.size || totalBytes,
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
          el.downloadBtn.textContent = (res.outputKind === 'zip') ? 'Unduh berkas ZIP' : 'Unduh gambar';
        }

        if (el.summaryPages) el.summaryPages.textContent = res.pageCount + ' halaman';
        if (el.summaryFormat) el.summaryFormat.textContent = res.imageFmt + ' (' + res.dpi + ' DPI)';
        if (el.summarySize) el.summarySize.textContent = formatBytes(res.sizeBytes);

        if (el.resultsMeta) {
          el.resultsMeta.textContent = res.filename + ' (' + formatBytes(res.sizeBytes) + ')';
        }

        if (el.infoText) {
          if (res.outputKind === 'zip') {
            el.infoText.textContent = 'Hasil berupa berkas ZIP berisi ' + res.imageCount + ' gambar (satu berkas per halaman).';
          } else {
            el.infoText.textContent = 'Hasil berupa 1 berkas gambar utuh.';
          }
        }

        // Pratinjau gambar bila 1 halaman
        if (res.outputKind === 'image' && el.previewWrap && el.previewImg) {
          el.previewImg.src = state.downloadUrl;
          el.previewWrap.hidden = false;
        } else if (el.previewWrap) {
          el.previewWrap.hidden = true;
          if (el.previewImg) el.previewImg.removeAttribute('src');
        }

        state.summaryText = 'Hasil konversi PDF ke gambar:\n' +
          '- Nama berkas: ' + res.filename + '\n' +
          '- Halaman: ' + res.pageCount + '\n' +
          '- Format: ' + res.imageFmt + ' (' + res.dpi + ' DPI)\n' +
          '- Ukuran berkas: ' + formatBytes(res.sizeBytes);

        if (el.results) el.results.hidden = false;
        setStatus('Selesai! Gambar siap diunduh.', 'ok');
      })
      .catch(function (err) {
        var rawMsg = (err && err.message) ? String(err.message) : (typeof err === 'string' ? err : '');
        var isNetworkError = (err instanceof TypeError) ||
          (err && err.name === 'TypeError') ||
          /Failed to fetch|NetworkError|Load failed|Network request failed|TypeError/i.test(rawMsg);
        var msg = isNetworkError
          ? 'Tidak bisa menghubungi server. Periksa sambungan lalu coba lagi.'
          : (rawMsg || 'Tidak bisa menghubungi server. Periksa sambungan lalu coba lagi.');
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
      el.dropzone.classList.add('pdfimg__dropzone--active');
    });

    el.dropzone.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('pdfimg__dropzone--active');
    });

    el.dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('pdfimg__dropzone--active');
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

  if (el.formatPng) {
    el.formatPng.addEventListener('change', updateFormatFields);
  }
  if (el.formatJpg) {
    el.formatJpg.addEventListener('change', updateFormatFields);
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
    el.form.addEventListener('submit', submitToImage);
  }

  if (el.copyBtn) {
    el.copyBtn.addEventListener('click', copySummary);
  }

  // Dukungan tombol Esc
  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' || e.key === 'Esc') {
      if (state.selectedFile || state.downloadUrl) {
        clearSelectedFile();
      }
    }
  });

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
  updateFormatFields();
  fetchLimits();
  updateControls();
})();
