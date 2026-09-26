/* =========================================================================
   Panel alat: Rapikan & periksa JSON (JSON Formatter & Validator)
   Teks JSON dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada teks yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('json-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('json-title'),
    limits: document.getElementById('json-limits'),
    note: document.getElementById('json-note'),
    close: document.getElementById('json-close'),
    input: document.getElementById('json-input'),
    mode: document.getElementById('json-mode'),
    indent: document.getElementById('json-indent'),
    indentGroup: document.getElementById('json-indent-group'),
    sortKeys: document.getElementById('json-sort-keys'),
    status: document.getElementById('json-status'),
    clear: document.getElementById('json-clear'),
    submit: document.getElementById('json-submit'),
    hint: document.getElementById('json-hint'),
    outputWrap: document.getElementById('json-output-wrap'),
    output: document.getElementById('json-output'),
    stats: document.getElementById('json-stats'),
    statLines: document.getElementById('json-stat-lines'),
    statChars: document.getElementById('json-stat-chars'),
    statBytes: document.getElementById('json-stat-bytes'),
    statDepth: document.getElementById('json-stat-depth'),
    statKeys: document.getElementById('json-stat-keys'),
    statItems: document.getElementById('json-stat-items'),
    statLeaves: document.getElementById('json-stat-leaves'),
    statRoot: document.getElementById('json-stat-root'),
    noteResult: document.getElementById('json-note-result'),
    copy: document.getElementById('json-copy'),
    download: document.getElementById('json-download')
  };

  var FALLBACK_MODES = [
    { value: 'rapikan', label: 'Rapikan (beri jarak & baris baru)' },
    { value: 'padatkan', label: 'Padatkan jadi satu baris' },
    { value: 'periksa', label: 'Periksa saja (tidak diubah)' }
  ];

  var state = {
    modes: FALLBACK_MODES,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    downloadUrl: null
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
    if (typeof bytes !== 'number' || isNaN(bytes)) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  }

  function updateIndentState() {
    if (!el.indent) return;
    var mode = el.mode ? el.mode.value : 'rapikan';
    var disableIndent = (mode === 'padatkan' || mode === 'periksa');
    el.indent.disabled = state.busy || disableIndent;
    if (el.indentGroup) {
      if (disableIndent) {
        el.indentGroup.classList.add('js__field--disabled');
      } else {
        el.indentGroup.classList.remove('js__field--disabled');
      }
    }
  }

  function resetResults() {
    if (el.hint) el.hint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.output) el.output.value = '';
    if (el.stats) el.stats.hidden = true;
    if (el.noteResult) {
      el.noteResult.textContent = '';
      el.noteResult.hidden = true;
    }
    state.lastResult = null;
    revokeDownload();
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }
  }

  function updateControls() {
    var text = el.input ? el.input.value.trim() : '';
    var hasText = text.length > 0;
    var hasOutput = !!(state.lastResult);

    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Memproses...' : 'Proses';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasText && !hasOutput);
    }
    updateIndentState();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/json/limits', { headers: { credentials: 'same-origin', Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data && Array.isArray(data.modes) && data.modes.length > 0) {
          state.modes = data.modes;
          if (el.mode) {
            var currentVal = el.mode.value;
            el.mode.innerHTML = '';
            for (var i = 0; i < data.modes.length; i++) {
              var m = data.modes[i];
              var opt = document.createElement('option');
              opt.value = m.value;
              opt.textContent = m.label;
              if (m.value === currentVal) opt.selected = true;
              el.mode.appendChild(opt);
            }
          }
        }
        if (data && el.limits) {
          el.limits.textContent = 'Maks ' + (data.max_chars ? data.max_chars.toLocaleString('id-ID') : '400.000') + ' karakter (1 MB), kedalaman ' + (data.max_depth || 120);
        }
        state.limitsLoaded = true;
        updateIndentState();
      })
      .catch(function () {
        updateIndentState();
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.hint) el.hint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.output && data.keluaran) {
      el.output.value = data.keluaran.teks || '';
    }

    if (el.stats && data.masukan && data.keluaran && data.statistik) {
      el.stats.hidden = false;
      if (el.statLines) {
        el.statLines.textContent = data.masukan.lines + ' \u2192 ' + data.keluaran.lines;
      }
      if (el.statChars) {
        el.statChars.textContent = data.masukan.chars.toLocaleString('id-ID') + ' \u2192 ' + data.keluaran.chars.toLocaleString('id-ID');
      }
      if (el.statBytes) {
        el.statBytes.textContent = formatBytes(data.masukan.bytes);
      }
      if (el.statDepth) {
        el.statDepth.textContent = String(data.statistik.kedalaman);
      }
      if (el.statKeys) {
        el.statKeys.textContent = data.statistik.jumlah_kunci.toLocaleString('id-ID');
      }
      if (el.statItems) {
        el.statItems.textContent = data.statistik.jumlah_item.toLocaleString('id-ID');
      }
      if (el.statLeaves) {
        el.statLeaves.textContent = data.statistik.jumlah_daun.toLocaleString('id-ID');
      }
      if (el.statRoot) {
        el.statRoot.textContent = data.statistik.akar || '-';
      }
    }

    if (el.noteResult && data.catatan) {
      el.noteResult.textContent = data.catatan;
      el.noteResult.hidden = false;
    }
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      var posisi = null;
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error) {
          if (parsed.error.message) message = parsed.error.message;
          if (parsed.error.posisi) posisi = parsed.error.posisi;
        }
      } catch (err) { /* diabaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan alat JSON belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Ukuran JSON melebihi batas maksimum 1 MB atau 400.000 karakter.';
        } else {
          message = 'Terjadi kendala saat memproses JSON (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      e.posisi = posisi;
      throw e;
    });
  }

  function submitProcess() {
    if (state.busy) return;

    var text = el.input ? el.input.value.trim() : '';
    if (!text) {
      setStatus('Tempel atau ketik teks JSON terlebih dahulu.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var modeVal = el.mode ? el.mode.value : 'rapikan';
    var indentVal = el.indent ? el.indent.value : '2';
    var sortKeysVal = el.sortKeys ? el.sortKeys.checked : false;

    var form = new FormData();
    form.append('text', el.input ? el.input.value : '');
    form.append('mode', modeVal);
    form.append('indent', indentVal);
    form.append('urutkan_kunci', sortKeysVal ? 'true' : 'false');

    state.busy = true;
    updateControls();
    setStatus('Sedang memproses JSON...', 'busy');

    fetch(serverBase + '/api/json', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('JSON sah dan selesai diproses.', 'ok');
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

  function copyResult() {
    if (!state.lastResult || !el.output) return;
    var textToCopy = el.output.value;

    function notify(ok) {
      if (ok) {
        setStatus('Hasil disalin ke papan klip.', 'ok');
      } else {
        setStatus('Gagal menyalin hasil.', 'error');
      }
      if (el.copy) {
        var orig = el.copy.textContent;
        el.copy.textContent = ok ? 'Tersalin!' : 'Gagal salin';
        setTimeout(function () {
          el.copy.textContent = orig;
        }, 1500);
      }
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(textToCopy).then(function () {
        notify(true);
      }).catch(function () {
        notify(false);
      });
    } else {
      el.output.select();
      try {
        var ok = document.execCommand('copy');
        notify(ok);
      } catch (err) {
        notify(false);
      }
    }
  }

  function downloadResult() {
    if (!state.lastResult || !el.output) return;
    var d = state.lastResult;
    var content = el.output.value;
    var mode = d.mode || 'rapikan';
    var filename = 'rapi.json';
    var mimeType = 'application/json;charset=utf-8';

    if (mode === 'padatkan') {
      filename = 'padat.json';
    } else if (mode === 'periksa') {
      filename = 'diperiksa.txt';
      mimeType = 'text/plain;charset=utf-8';
    }

    revokeDownload();
    var blob = new Blob([content], { type: mimeType });
    state.downloadUrl = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function resetAll() {
    if (el.input) el.input.value = '';
    resetResults();
    setStatus('Tempel teks JSON di atas, pilih mode yang diinginkan, lalu tekan "Proses".', '');
    updateControls();
    if (el.input) el.input.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="json"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'json-panel');
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
    } catch (e) { /* abaikan */ }

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
    revokeDownload();
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

  // Event Listeners
  if (el.close) el.close.addEventListener('click', close);

  if (el.mode) {
    el.mode.addEventListener('change', function () {
      updateIndentState();
      resetResults();
      setStatus('Tempel teks JSON di atas, pilih mode yang diinginkan, lalu tekan "Proses".', '');
      updateControls();
    });
  }

  if (el.input) {
    el.input.addEventListener('input', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitProcess);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  function onKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape' && panel.contains(document.activeElement)) {
      event.preventDefault();
      close();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      if (panel.contains(document.activeElement)) {
        event.preventDefault();
        submitProcess();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel supaya kartu Rapikan & periksa JSON bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['json'] = toggle;

  // Inisialisasi bawaan
  updateIndentState();
  updateControls();
})();
