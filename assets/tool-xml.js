/* =========================================================================
   Panel alat: Rapikan & periksa XML (XML Formatter & Validator)
   Teks XML dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada teks yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('xml-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('xml-title'),
    limits: document.getElementById('xml-limits'),
    note: document.getElementById('xml-note'),
    close: document.getElementById('xml-close'),
    btnContoh: document.getElementById('xml-btn-contoh'),
    input: document.getElementById('xml-input'),
    mode: document.getElementById('xml-mode'),
    indent: document.getElementById('xml-indent'),
    indentGroup: document.getElementById('xml-indent-group'),
    sortKeys: document.getElementById('xml-sort-keys'),
    sortKeysGroup: document.getElementById('xml-sort-keys-group'),
    status: document.getElementById('xml-status'),
    clear: document.getElementById('xml-clear'),
    submit: document.getElementById('xml-submit'),
    hint: document.getElementById('xml-hint'),
    outputWrap: document.getElementById('xml-output-wrap'),
    output: document.getElementById('xml-output'),
    stats: document.getElementById('xml-stats'),
    statLines: document.getElementById('xml-stat-lines'),
    statChars: document.getElementById('xml-stat-chars'),
    statBytes: document.getElementById('xml-stat-bytes'),
    statDepth: document.getElementById('xml-stat-depth'),
    statElements: document.getElementById('xml-stat-elements'),
    statAttrs: document.getElementById('xml-stat-attrs'),
    statRoot: document.getElementById('xml-stat-root'),
    noteResult: document.getElementById('xml-note-result'),
    copy: document.getElementById('xml-copy'),
    download: document.getElementById('xml-download')
  };

  var FALLBACK_MODES = [
    { value: 'rapikan', label: 'Rapikan (beri jarak & baris baru)' },
    { value: 'padatkan', label: 'Padatkan jadi satu baris' },
    { value: 'periksa', label: 'Periksa saja (tidak diubah)' },
    { value: 'ke_json', label: 'Ubah jadi JSON' }
  ];

  var CONTOH_XML =
    '<toko nama="Buku Cemerlang">\n' +
    '  <buku id="1" kategori="fiksi">\n' +
    '    <judul>Laskar Pelangi</judul>\n' +
    '    <penulis>Andrea Hirata</penulis>\n' +
    '  </buku>\n' +
    '  <buku id="2" kategori="nonfiksi">\n' +
    '    <judul>Filosofi Teras</judul>\n' +
    '    <penulis>Henry Manampiring</penulis>\n' +
    '  </buku>\n' +
    '</toko>';

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
    var mode = el.mode ? el.mode.value : 'rapikan';
    var showIndent = (mode === 'rapikan' || mode === 'ke_json');
    var showSortKeys = (mode === 'ke_json');

    if (el.indentGroup) {
      el.indentGroup.hidden = !showIndent;
      if (!showIndent) {
        el.indentGroup.classList.add('js__field--disabled');
      } else {
        el.indentGroup.classList.remove('js__field--disabled');
      }
    }
    if (el.indent) {
      el.indent.disabled = state.busy || !showIndent;
    }

    if (el.sortKeysGroup) {
      el.sortKeysGroup.hidden = !showSortKeys;
    }
    if (el.sortKeys) {
      el.sortKeys.disabled = state.busy || !showSortKeys;
    }

    if (el.download) {
      if (mode === 'ke_json') {
        el.download.textContent = 'Unduh .json';
      } else {
        el.download.textContent = 'Unduh .xml';
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
    fetch(serverBase + '/api/xml/limits', { headers: { credentials: 'same-origin', Accept: 'application/json' } })
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
          var charText = data.max_chars ? data.max_chars.toLocaleString('id-ID') : '400.000';
          var depthVal = data.max_depth || 120;
          el.limits.textContent = 'Maks ' + charText + ' karakter (1 MB), kedalaman ' + depthVal;
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

    if (el.output) {
      el.output.value = (data.keluaran && data.keluaran.teks) || data.teks || '';
    }

    if (el.stats && data.statistik) {
      el.stats.hidden = false;
      var s = data.statistik;
      if (el.statLines) {
        el.statLines.textContent = s.baris_sebelum + ' \u2192 ' + s.baris_sesudah;
      }
      if (el.statChars) {
        el.statChars.textContent = s.karakter_sebelum.toLocaleString('id-ID') + ' \u2192 ' + s.karakter_sesudah.toLocaleString('id-ID');
      }
      if (el.statBytes) {
        el.statBytes.textContent = formatBytes(s.ukuran_sebelum);
      }
      if (el.statDepth) {
        el.statDepth.textContent = String(s.kedalaman);
      }
      if (el.statElements) {
        el.statElements.textContent = s.elemen.toLocaleString('id-ID');
      }
      if (el.statAttrs) {
        el.statAttrs.textContent = s.atribut.toLocaleString('id-ID');
      }
      if (el.statRoot) {
        el.statRoot.textContent = s.akar || '-';
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
          message = 'Layanan alat XML belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Ukuran XML melebihi batas maksimum 1 MB atau 400.000 karakter.';
        } else {
          message = 'Terjadi kendala saat memproses XML (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
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
      setStatus('Tempel atau ketik teks XML terlebih dahulu.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var modeVal = el.mode ? el.mode.value : 'rapikan';
    var indentVal = el.indent ? el.indent.value : '2';
    var sortKeysVal = el.sortKeys ? el.sortKeys.checked : false;

    var form = new FormData();
    form.append('teks', el.input ? el.input.value : '');
    form.append('mode', modeVal);
    form.append('indent', indentVal);
    form.append('urutkan_kunci', sortKeysVal ? 'ya' : 'tidak');

    state.busy = true;
    updateControls();
    setStatus('Sedang memproses XML...', 'busy');

    fetch(serverBase + '/api/xml', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('XML sah dan selesai diproses.', 'ok');
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
    var filename = 'hasil-rapi.xml';
    var mimeType = 'application/xml;charset=utf-8';

    if (mode === 'padatkan') {
      filename = 'hasil-padat.xml';
    } else if (mode === 'ke_json') {
      filename = 'hasil.json';
      mimeType = 'application/json;charset=utf-8';
    } else if (mode === 'periksa') {
      filename = 'hasil.xml';
      mimeType = 'application/xml;charset=utf-8';
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

  function isiContoh() {
    if (el.input) {
      el.input.value = CONTOH_XML;
    }
    resetResults();
    setStatus('Contoh XML berhasil diisi.', 'ok');
    updateControls();
    if (el.input) {
      el.input.focus();
    }
  }

  function resetAll() {
    if (el.input) el.input.value = '';
    resetResults();
    setStatus('Tempel teks XML di atas, pilih mode yang diinginkan, lalu tekan "Proses".', '');
    updateControls();
    if (el.input) el.input.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="xml"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'xml-panel');
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
    } catch (e) { /* diabaikan */ }

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

  if (el.btnContoh) el.btnContoh.addEventListener('click', isiContoh);

  if (el.mode) {
    el.mode.addEventListener('change', function () {
      updateIndentState();
      resetResults();
      setStatus('Tempel teks XML di atas, pilih mode yang diinginkan, lalu tekan "Proses".', '');
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

  // Daftarkan panel supaya kartu Rapikan & periksa XML bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['xml'] = toggle;

  // Inisialisasi bawaan
  updateIndentState();
  updateControls();
})();
