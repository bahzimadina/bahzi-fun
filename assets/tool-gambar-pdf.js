/* =========================================================================
   Panel alat: Gambar jadi PDF
   Menyusun beberapa berkas gambar (JPG, PNG, WebP) menjadi satu berkas PDF.
   Tiap gambar diletakkan pada satu halaman di memori, lalu diunduh langsung.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('gambar-pdf-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('gambar-pdf-close'),
    limits: document.getElementById('gambar-pdf-limits'),
    drop: document.getElementById('gambar-pdf-drop'),
    input: document.getElementById('gambar-pdf-input'),
    list: document.getElementById('gambar-pdf-list'),
    empty: document.getElementById('gambar-pdf-empty'),
    selectUkuran: document.getElementById('gambar-pdf-ukuran'),
    selectOrientasi: document.getElementById('gambar-pdf-orientasi'),
    selectMargin: document.getElementById('gambar-pdf-margin'),
    status: document.getElementById('gambar-pdf-status'),
    clear: document.getElementById('gambar-pdf-clear'),
    submit: document.getElementById('gambar-pdf-submit'),
    result: document.getElementById('gambar-pdf-result'),
    resultMeta: document.getElementById('gambar-pdf-result-meta'),
    download: document.getElementById('gambar-pdf-download'),
    reset: document.getElementById('gambar-pdf-reset')
  };

  var FALLBACK_LIMITS = {
    max_files: 20,
    max_file_mb: 15,
    max_total_mb: 40,
    max_pixels: 40000000,
    max_side: 3500,
    page_sizes: [
      { id: 'a4', label: 'A4 (210 x 297 mm)' },
      { id: 'f4', label: 'F4 (215 x 330 mm)' },
      { id: 'letter', label: 'Letter (216 x 279 mm)' },
      { id: 'auto', label: 'Otomatis (ikut ukuran gambar)' }
    ],
    orientations: [
      { id: 'auto', label: 'Otomatis' },
      { id: 'tegak', label: 'Tegak' },
      { id: 'mendatar', label: 'Mendatar' }
    ],
    margins: [0, 5, 10, 15, 20],
    default: {
      ukuran: 'a4',
      orientasi: 'auto',
      margin: 10
    }
  };

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    files: [],
    busy: false,
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    downloadUrl: null,
    lastFocus: null
  };

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1).replace('.', ',') + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2).replace('.', ',') + ' MB';
  }

  function setStatus(message, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status gdp__status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(message));
  }

  function isSupportedExtension(name) {
    var lower = (name || '').toLowerCase();
    return lower.endsWith('.jpg') || lower.endsWith('.jpeg') || lower.endsWith('.png') || lower.endsWith('.webp');
  }

  function isSupportedMime(type) {
    var t = (type || '').toLowerCase();
    return t === 'image/jpeg' || t === 'image/jpg' || t === 'image/png' || t === 'image/webp';
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      try {
        URL.revokeObjectURL(state.downloadUrl);
      } catch (e) {}
      state.downloadUrl = null;
    }
  }

  function updateControls() {
    var hasFiles = state.files.length > 0;
    if (el.clear) el.clear.disabled = state.busy || !hasFiles;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasFiles;
      el.submit.textContent = state.busy ? 'Sedang menyusun PDF...' : 'Buat PDF';
    }
  }

  function renderList() {
    if (!el.list || !el.empty) return;
    el.list.textContent = '';

    if (state.files.length === 0) {
      el.list.hidden = true;
      el.empty.hidden = false;
      updateControls();
      return;
    }

    el.list.hidden = false;
    el.empty.hidden = true;

    state.files.forEach(function (item, index) {
      var li = document.createElement('li');
      li.className = 'filelist__item gdp__item';

      var pos = document.createElement('span');
      pos.className = 'filelist__pos gdp__pos';
      pos.textContent = String(index + 1);
      li.appendChild(pos);

      var meta = document.createElement('div');
      meta.className = 'filelist__meta gdp__meta';

      var name = document.createElement('p');
      name.className = 'filelist__name gdp__name';
      name.textContent = item.file.name;
      meta.appendChild(name);

      var size = document.createElement('p');
      size.className = 'filelist__size gdp__size';
      size.textContent = formatBytes(item.file.size);
      meta.appendChild(size);

      li.appendChild(meta);

      var actions = document.createElement('div');
      actions.className = 'filelist__actions gdp__actions';

      var upBtn = document.createElement('button');
      upBtn.type = 'button';
      upBtn.className = 'iconbtn gdp__btn-action';
      upBtn.setAttribute('aria-label', 'Pindahkan ' + item.file.name + ' ke atas');
      upBtn.textContent = '▲';
      upBtn.disabled = state.busy || index === 0;
      upBtn.addEventListener('click', function () {
        moveFile(index, index - 1);
      });
      actions.appendChild(upBtn);

      var downBtn = document.createElement('button');
      downBtn.type = 'button';
      downBtn.className = 'iconbtn gdp__btn-action';
      downBtn.setAttribute('aria-label', 'Pindahkan ' + item.file.name + ' ke bawah');
      downBtn.textContent = '▼';
      downBtn.disabled = state.busy || index === state.files.length - 1;
      downBtn.addEventListener('click', function () {
        moveFile(index, index + 1);
      });
      actions.appendChild(downBtn);

      var delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'iconbtn iconbtn--danger gdp__btn-action';
      delBtn.setAttribute('aria-label', 'Hapus ' + item.file.name);
      delBtn.textContent = '✕';
      delBtn.disabled = state.busy;
      delBtn.addEventListener('click', function () {
        removeFile(index);
      });
      actions.appendChild(delBtn);

      li.appendChild(actions);
      el.list.appendChild(li);
    });

    updateControls();
  }

  function moveFile(fromIndex, toIndex) {
    if (state.busy) return;
    if (toIndex < 0 || toIndex >= state.files.length) return;
    var target = state.files.splice(fromIndex, 1)[0];
    state.files.splice(toIndex, 0, target);
    renderList();
  }

  function removeFile(index) {
    if (state.busy) return;
    state.files.splice(index, 1);
    renderList();
    if (state.files.length === 0) {
      setStatus('Daftar gambar dikosongkan.');
    } else {
      setStatus('Satu gambar dihapus dari daftar.');
    }
  }

  function handleFiles(incoming) {
    if (!incoming || !incoming.length) return;
    var maxFiles = state.limits.max_files || 20;
    var maxFileBytes = (state.limits.max_file_mb || 15) * 1024 * 1024;
    var maxTotalBytes = (state.limits.max_total_mb || 40) * 1024 * 1024;

    var currentTotal = 0;
    state.files.forEach(function (f) {
      currentTotal += f.file.size;
    });

    var added = 0;
    var warningMessage = null;

    for (var i = 0; i < incoming.length; i++) {
      var file = incoming[i];
      if (!isSupportedExtension(file.name) && !isSupportedMime(file.type)) {
        warningMessage = 'Hanya gambar JPG, PNG, atau WebP yang bisa dipakai.';
        continue;
      }
      if (file.size === 0) {
        warningMessage = 'Ada berkas yang kosong. Pilih gambar lain.';
        continue;
      }
      if (file.size > maxFileBytes) {
        warningMessage = 'Satu gambar paling besar 15 MB.';
        continue;
      }
      if (state.files.length >= maxFiles) {
        warningMessage = 'Paling banyak 20 gambar sekali jalan.';
        break;
      }
      if (currentTotal + file.size > maxTotalBytes) {
        warningMessage = 'Total semua gambar paling besar 40 MB. Kurangi dulu jumlahnya.';
        break;
      }

      state.files.push({
        file: file,
        id: 'img-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7)
      });
      currentTotal += file.size;
      added++;
    }

    renderList();

    if (warningMessage) {
      setStatus(warningMessage, 'error');
    } else if (added > 0) {
      setStatus(added + ' gambar ditambahkan. Total ' + state.files.length + ' gambar terpilih.');
    }
  }

  function resetAll() {
    if (state.busy) return;
    state.files = [];
    if (el.input) el.input.value = '';
    renderList();
    revokeDownload();
    if (el.result) el.result.hidden = true;
    if (el.download) el.download.hidden = true;
    setStatus('Pilih beberapa gambar JPG, PNG, atau WebP untuk disusun jadi PDF.');
  }

  function submitPdf() {
    if (state.busy || state.files.length === 0) return;

    var totalBytes = 0;
    state.files.forEach(function (f) {
      totalBytes += f.file.size;
    });
    var maxTotalBytes = (state.limits.max_total_mb || 40) * 1024 * 1024;
    if (totalBytes > maxTotalBytes) {
      setStatus('Total semua gambar paling besar 40 MB. Kurangi dulu jumlahnya.', 'error');
      return;
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang menyusun PDF...', 'busy');
    if (el.result) el.result.hidden = true;
    if (el.download) el.download.hidden = true;
    revokeDownload();

    var formData = new FormData();
    state.files.forEach(function (item) {
      formData.append('files', item.file, item.file.name);
    });

    var ukuran = el.selectUkuran ? el.selectUkuran.value : 'a4';
    var orientasi = el.selectOrientasi ? el.selectOrientasi.value : 'auto';
    var margin = el.selectMargin ? el.selectMargin.value : '10';

    formData.append('ukuran', ukuran);
    formData.append('orientasi', orientasi);
    formData.append('margin', margin);

    fetch(serverBase + '/api/gambar-pdf', {
      method: 'POST',
      body: formData
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().catch(function () {
            return { error: { message: 'Gagal menyusun PDF. Coba periksa berkas gambar Anda.' } };
          }).then(function (body) {
            var msg = (body.error && body.error.message) ||
                      (body.detail && body.detail.message) ||
                      (body.detail && typeof body.detail === 'string' ? body.detail : null) ||
                      'Gagal menyusun PDF.';
            throw new Error(msg);
          });
        }

        var pageCount = response.headers.get('X-Page-Count') || String(state.files.length);
        return response.blob().then(function (blob) {
          return {
            blob: blob,
            pageCount: pageCount
          };
        });
      })
      .then(function (result) {
        state.downloadUrl = URL.createObjectURL(result.blob);
        if (el.download) {
          el.download.href = state.downloadUrl;
          el.download.download = 'gambar-jadi-pdf.pdf';
          el.download.hidden = false;
        }

        if (el.resultMeta) {
          el.resultMeta.textContent = 'PDF berhasil dibuat: ' + result.pageCount + ' halaman, ukuran ' + formatBytes(result.blob.size) + '.';
        }
        if (el.result) {
          el.result.hidden = false;
        }

        setStatus('PDF berhasil disusun dan siap diunduh.', 'ok');
      })
      .catch(function (error) {
        var msg = error && error.message;
        if (!msg || msg === 'Failed to fetch' || msg.indexOf('NetworkError') !== -1) {
          msg = 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        }
        setStatus(msg, 'error');
      })
      .then(function () {
        state.busy = false;
        updateControls();
      });
  }

  function populateOptions(limitsData) {
    if (limitsData.page_sizes && el.selectUkuran) {
      var currentSize = el.selectUkuran.value || 'a4';
      el.selectUkuran.textContent = '';
      limitsData.page_sizes.forEach(function (opt) {
        var option = document.createElement('option');
        option.value = opt.id;
        option.textContent = opt.label;
        if (opt.id === currentSize) option.selected = true;
        el.selectUkuran.appendChild(option);
      });
    }

    if (limitsData.orientations && el.selectOrientasi) {
      var currentOri = el.selectOrientasi.value || 'auto';
      el.selectOrientasi.textContent = '';
      limitsData.orientations.forEach(function (opt) {
        var option = document.createElement('option');
        option.value = opt.id;
        option.textContent = opt.label;
        if (opt.id === currentOri) option.selected = true;
        el.selectOrientasi.appendChild(option);
      });
    }

    if (limitsData.margins && el.selectMargin) {
      var currentMargin = el.selectMargin.value || '10';
      el.selectMargin.textContent = '';
      limitsData.margins.forEach(function (m) {
        var option = document.createElement('option');
        option.value = String(m);
        option.textContent = m === 0 ? 'Tanpa margin (0 mm)' : m + ' mm';
        if (String(m) === String(currentMargin)) option.selected = true;
        el.selectMargin.appendChild(option);
      });
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/gambar-pdf/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('status ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limits = data;
        state.limitsLoaded = true;
        populateOptions(data);
        if (el.limits) {
          el.limits.textContent = 'Maks ' + data.max_files + ' berkas, total ' + data.max_total_mb + ' MB (JPG, PNG, atau WebP)';
        }
      })
      .catch(function () {
        populateOptions(FALLBACK_LIMITS);
      });
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="gambar-pdf"]');
    triggers.forEach(function (trigger) {
      trigger.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
  }

  function open() {
    if (panel.hidden) {
      state.lastFocus = document.activeElement;
      panel.hidden = false;
      loadLimits();
      syncTriggers(true);
      panel.focus({ preventScroll: true });
      if (state.files.length === 0) {
        setStatus('Pilih beberapa gambar JPG, PNG, atau WebP untuk disusun jadi PDF.');
      }
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
    if (panel.hidden) open(); else close();
  }

  function onKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape' && panel.contains(document.activeElement)) {
      event.preventDefault();
      close();
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('change', function () {
      if (el.input.files && el.input.files.length) {
        handleFiles(el.input.files);
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
        handleFiles(event.dataTransfer.files);
      }
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitPdf);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.reset) el.reset.addEventListener('click', resetAll);

  window.addEventListener('beforeunload', function () {
    revokeDownload();
  });

  populateOptions(FALLBACK_LIMITS);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['gambar-pdf'] = toggle;

  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      var paramAlat = params.get('alat');
      if (paramAlat !== 'gambar-jadi-pdf' && paramAlat !== 'gambar-pdf') return;

      var trigger = document.querySelector('button.tool-card__open[data-tool-action="gambar-pdf"]');
      if (trigger) {
        trigger.click();
      } else {
        open();
      }
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', handleUrlParam);
  } else {
    handleUrlParam();
  }
})();
