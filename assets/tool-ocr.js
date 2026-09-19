/* =========================================================================
   Alat: Ambil teks dari gambar & PDF (OCR)
   Berkas dikirim ke server lewat multipart/form-data, dibaca di memori,
   lalu langsung dibuang. Tidak ada berkas yang disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var app = document.getElementById('ocr-app');
  if (!app) return;

  var el = {
    form: document.getElementById('ocr-form'),
    dropzone: document.getElementById('ocr-dropzone'),
    fileInput: document.getElementById('ocr-file-input'),
    browseBtn: document.getElementById('ocr-browse-btn'),
    fileBox: document.getElementById('ocr-file-box'),
    fileType: document.getElementById('ocr-file-type'),
    fileName: document.getElementById('ocr-file-name'),
    fileSize: document.getElementById('ocr-file-size'),
    removeBtn: document.getElementById('ocr-remove-btn'),
    langList: document.getElementById('ocr-lang-list'),
    submitBtn: document.getElementById('ocr-submit-btn'),
    resetBtn: document.getElementById('ocr-reset-btn'),
    status: document.getElementById('ocr-status'),
    results: document.getElementById('ocr-results'),
    resultsMeta: document.getElementById('ocr-results-meta'),
    output: document.getElementById('ocr-output'),
    copyBtn: document.getElementById('ocr-copy-btn'),
    downloadBtn: document.getElementById('ocr-download-btn'),
    limitsDesc: document.getElementById('ocr-limits-desc')
  };

  var numberFmt = new Intl.NumberFormat('id-ID');

  var DEFAULT_LANGUAGES = [
    { value: 'ind+eng', label: 'Campuran (Indonesia + Inggris)' },
    { value: 'ind', label: 'Indonesia' },
    { value: 'eng', label: 'Inggris' }
  ];

  var state = {
    limits: {
      max_bytes: 20 * 1024 * 1024,
      max_pages: 15,
      time_limit_seconds: 120,
      languages: DEFAULT_LANGUAGES
    },
    limitsLoaded: false,
    selectedFile: null,
    busy: false
  };

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toLocaleString('id-ID', { maximumFractionDigits: 1 }) + ' KB';
    return (bytes / (1024 * 1024)).toLocaleString('id-ID', { maximumFractionDigits: 1 }) + ' MB';
  }

  function setStatus(message, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status ocr__status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(message));
  }

  function renderLanguageOptions(languages) {
    if (!el.langList) return;
    el.langList.textContent = '';

    var currentSelection = 'ind+eng';
    var hasDefault = languages.some(function (item) { return item.value === currentSelection; });
    if (!hasDefault && languages.length > 0) {
      currentSelection = languages[0].value;
    }

    languages.forEach(function (lang, idx) {
      var label = document.createElement('label');
      label.className = 'ocr__lang-label';

      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'ocr-lang';
      input.value = lang.value;
      input.checked = (lang.value === currentSelection);
      input.id = 'ocr-lang-' + idx;

      var text = document.createElement('span');
      text.className = 'ocr__lang-name';
      text.textContent = lang.label;

      label.appendChild(input);
      label.appendChild(text);
      el.langList.appendChild(label);
    });
  }

  function updateLimitsDescription() {
    if (!el.limitsDesc) return;
    var mb = Math.round(state.limits.max_bytes / (1024 * 1024));
    el.limitsDesc.textContent = 'Batas berkas: maksimal ' + mb + ' MB per berkas dan PDF maksimal ' + state.limits.max_pages + ' halaman.';
  }

  function fetchLimits() {
    fetch('/api/ocr/limits')
      .then(function (resp) {
        if (!resp.ok) throw new Error('Gagal memuat batas.');
        return resp.json();
      })
      .then(function (data) {
        if (data.max_bytes) state.limits.max_bytes = data.max_bytes;
        if (data.max_pages) state.limits.max_pages = data.max_pages;
        if (data.time_limit_seconds) state.limits.time_limit_seconds = data.time_limit_seconds;
        if (Array.isArray(data.languages) && data.languages.length > 0) {
          state.limits.languages = data.languages;
        }
        state.limitsLoaded = true;
        updateLimitsDescription();
        renderLanguageOptions(state.limits.languages);
      })
      .catch(function () {
        // Gunakan nilai bawaan bila permintaan batas belum berhasil
        updateLimitsDescription();
        renderLanguageOptions(state.limits.languages);
      });
  }

  function getSelectedLanguage() {
    var checked = el.langList ? el.langList.querySelector('input[name="ocr-lang"]:checked') : null;
    return checked ? checked.value : 'ind+eng';
  }

  function updateControls() {
    var hasFile = !!state.selectedFile;
    if (el.submitBtn) {
      el.submitBtn.disabled = state.busy || !hasFile;
      el.submitBtn.textContent = state.busy ? 'Membaca…' : 'Ambil teks';
    }
    if (el.resetBtn) {
      el.resetBtn.disabled = state.busy || !hasFile;
    }
    if (el.browseBtn) {
      el.browseBtn.disabled = state.busy;
    }
    if (el.removeBtn) {
      el.removeBtn.disabled = state.busy;
    }
    if (el.fileInput) {
      el.fileInput.disabled = state.busy;
    }
    if (el.langList) {
      var inputs = el.langList.querySelectorAll('input');
      inputs.forEach(function (inp) { inp.disabled = state.busy; });
    }
  }

  function handleFileSelected(file) {
    if (!file) return;

    var maxBytes = state.limits.max_bytes;
    if (file.size > maxBytes) {
      var mb = Math.round(maxBytes / (1024 * 1024));
      setStatus('Ukuran berkas melebihi batas ' + mb + ' MB.', 'error');
      return;
    }

    state.selectedFile = file;
    if (el.dropzone) el.dropzone.hidden = true;
    if (el.fileBox) el.fileBox.hidden = false;

    var isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
    if (el.fileType) {
      el.fileType.textContent = isPdf ? 'PDF' : 'GAMBAR';
      el.fileType.className = 'ocr__file-badge ' + (isPdf ? 'ocr__file-badge--pdf' : 'ocr__file-badge--img');
    }
    if (el.fileName) el.fileName.textContent = file.name;
    if (el.fileSize) el.fileSize.textContent = formatBytes(file.size);

    if (el.results) el.results.hidden = true;
    if (el.output) el.output.value = '';
    if (el.resultsMeta) el.resultsMeta.textContent = '';

    setStatus('Berkas siap. Tekan "Ambil teks" untuk memulai pembacaan.', '');
    updateControls();
  }

  function clearSelectedFile() {
    state.selectedFile = null;
    if (el.fileInput) el.fileInput.value = '';
    if (el.fileBox) el.fileBox.hidden = true;
    if (el.dropzone) el.dropzone.hidden = false;
    if (el.results) el.results.hidden = true;
    if (el.output) el.output.value = '';
    if (el.resultsMeta) el.resultsMeta.textContent = '';
    setStatus('Pilih berkas gambar atau PDF untuk memulai.', '');
    updateControls();
  }

  function submitOcr(e) {
    if (e) e.preventDefault();
    if (state.busy) return;

    if (!state.selectedFile) {
      setStatus('Berkas wajib dipilih.', 'error');
      return;
    }

    if (state.selectedFile.size > state.limits.max_bytes) {
      var mb = Math.round(state.limits.max_bytes / (1024 * 1024));
      setStatus('Ukuran berkas lebih dari ' + mb + ' MB.', 'error');
      return;
    }

    var selectedLang = getSelectedLanguage();
    var formData = new FormData();
    formData.append('file', state.selectedFile);
    formData.append('lang', selectedLang);

    state.busy = true;
    updateControls();
    setStatus('Sedang membaca teks dari berkas, tunggu sebentar...', 'busy');

    fetch('/api/ocr', {
      method: 'POST',
      body: formData
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          if (!resp.ok) {
            var msg = data && data.error && data.error.message
              ? data.error.message
              : 'Teksnya gagal diambil. Coba berkas lain atau pilihan bahasa lain.';
            throw new Error(msg);
          }
          return data;
        });
      })
      .then(function (res) {
        if (!el.results || !el.output) return;

        el.results.hidden = false;
        el.output.value = res.text || '';

        var durationSec = (res.duration_ms / 1000).toLocaleString('id-ID', {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1
        });
        var pageStr = res.pages > 1 ? (numberFmt.format(res.pages) + ' halaman') : '1 halaman';
        var charStr = numberFmt.format(res.chars) + ' karakter';

        if (el.resultsMeta) {
          el.resultsMeta.textContent = 'Selesai: ' + pageStr + ', ' + charStr + ', ' + durationSec + ' detik';
        }

        if (res.empty) {
          el.output.placeholder = '(Tidak ada teks yang terbaca dari berkas ini)';
          setStatus('Selesai dibaca, tetapi tidak ada teks yang terbaca. Pastikan dokumen jelas dan tegak.', '');
        } else {
          setStatus('Teks berhasil diambil.', 'ok');
        }

        el.results.focus({ preventScroll: true });
        el.output.focus({ preventScroll: false });
      })
      .catch(function (err) {
        var isNetwork = err && (err.name === 'TypeError' || /network|fetch|failed to fetch/i.test(err.message));
        var msg = isNetwork
          ? 'Tidak dapat menghubungi server. Periksa koneksi internet lalu coba lagi.'
          : (err && err.message ? err.message : 'Teksnya gagal diambil. Coba berkas lain.');
        setStatus(msg, 'error');
      })
      .then(function () {
        state.busy = false;
        updateControls();
      });
  }

  function copyResult() {
    if (!el.output || !el.output.value) return;
    var text = el.output.value;

    function fallbackCopy() {
      try {
        el.output.focus();
        el.output.select();
        var ok = document.execCommand('copy');
        if (ok) {
          setStatus('Hasil disalin.', 'ok');
        } else {
          setStatus('Tidak dapat menyalin hasil secara otomatis. Silakan salin manual.', 'error');
        }
      } catch (err) {
        setStatus('Tidak dapat menyalin hasil secara otomatis. Silakan salin manual.', 'error');
      }
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text)
        .then(function () {
          setStatus('Hasil disalin.', 'ok');
        })
        .catch(function () {
          fallbackCopy();
        });
    } else {
      fallbackCopy();
    }
  }

  function downloadResult() {
    if (!el.output || !el.output.value) return;
    var text = el.output.value;
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'hasil-teks.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 100);
  }

  // --- Penanganan Event ----------------------------------------------------
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
      el.dropzone.classList.add('ocr__dropzone--active');
    });

    el.dropzone.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('ocr__dropzone--active');
    });

    el.dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.dropzone.classList.remove('ocr__dropzone--active');
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
    el.form.addEventListener('submit', submitOcr);
  }

  if (el.copyBtn) {
    el.copyBtn.addEventListener('click', copyResult);
  }

  if (el.downloadBtn) {
    el.downloadBtn.addEventListener('click', downloadResult);
  }

  // Inisialisasi awal
  renderLanguageOptions(state.limits.languages);
  fetchLimits();
  updateControls();
})();
