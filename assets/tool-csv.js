/* Panel alat: CSV Tools (Alat CSV)
   Data dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu langsung dibuang. Tidak ada data yang disimpan di disk.
*/
(function () {
  'use strict';

  var panel = document.getElementById('csv-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('csv-title'),
    limits: document.getElementById('csv-limits'),
    note: document.getElementById('csv-note'),
    close: document.getElementById('csv-close'),
    mode: document.getElementById('csv-mode'),
    groupPemisah: document.getElementById('csv-group-pemisah'),
    pemisah: document.getElementById('csv-pemisah'),
    groupIndent: document.getElementById('csv-group-indent'),
    indent: document.getElementById('csv-indent'),
    groupHeader: document.getElementById('csv-group-header'),
    header: document.getElementById('csv-header'),
    groupRapikan: document.getElementById('csv-group-rapikan'),
    rapikan: document.getElementById('csv-rapikan'),
    inputLabel: document.getElementById('csv-input-label'),
    btnContoh: document.getElementById('csv-btn-contoh'),
    charCount: document.getElementById('csv-char-count'),
    input: document.getElementById('csv-input'),
    inputHint: document.getElementById('csv-input-hint'),
    status: document.getElementById('csv-status'),
    clear: document.getElementById('csv-clear'),
    submit: document.getElementById('csv-submit'),
    results: document.getElementById('csv-results'),
    resultHint: document.getElementById('csv-result-hint'),
    outputWrap: document.getElementById('csv-output-wrap'),
    stats: document.getElementById('csv-stats'),
    statRows: document.getElementById('csv-stat-rows'),
    statCols: document.getElementById('csv-stat-cols'),
    statDelim: document.getElementById('csv-stat-delim'),
    statEmptyColsWrap: document.getElementById('csv-stat-empty-cols-wrap'),
    statEmptyCols: document.getElementById('csv-stat-empty-cols'),
    outputCodeWrap: document.getElementById('csv-output-code-wrap'),
    outputLabel: document.getElementById('csv-output-label'),
    outputText: document.getElementById('csv-output-text'),
    outputTableWrap: document.getElementById('csv-output-table-wrap'),
    summaryTable: document.getElementById('csv-summary-table'),
    summaryTbody: document.getElementById('csv-summary-tbody'),
    noteResult: document.getElementById('csv-note-result'),
    copy: document.getElementById('csv-copy'),
    download: document.getElementById('csv-download')
  };

  var FALLBACK_CONTOH_CSV = 'nama,kota,pekerjaan,gaji\n' +
    'Budi,"Jakarta, Selatan",Programmer,12000000\n' +
    'Siti,Surabaya,Desainer,9500000\n' +
    'Andi,"Bandung, Barat",Penulis,8000000';

  var FALLBACK_CONTOH_JSON = '[\n' +
    '  {"nama": "Budi", "kota": "Jakarta, Selatan", "pekerjaan": "Programmer", "gaji": 12000000},\n' +
    '  {"nama": "Siti", "kota": "Surabaya", "pekerjaan": "Desainer", "gaji": 9500000},\n' +
    '  {"nama": "Andi", "kota": "Bandung, Barat", "pekerjaan": "Penulis", "gaji": 8000000}\n' +
    ']';

  var state = {
    mode: 'ke_json',
    maxChars: 400000,
    maxBytes: 1048576,
    maxRows: 20000,
    maxCols: 200,
    contohCsv: FALLBACK_CONTOH_CSV,
    contohJson: FALLBACK_CONTOH_JSON,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    lastTextToCopy: '',
    downloadUrl: null,
    downloadFilename: 'hasil.json',
    downloadMime: 'application/json;charset=utf-8'
  };

  function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatAngkaId(val) {
    if (typeof val !== 'number' || isNaN(val)) return String(val || '');
    // Gaya penulisan Indonesia: pemisah ribuan titik, desimal koma
    var parts = String(val).split('.');
    var bulat = parseInt(parts[0], 10);
    var formattedBulat = isNaN(bulat) ? parts[0] : bulat.toLocaleString('id-ID');
    if (parts.length > 1) {
      return formattedBulat + ',' + parts[1];
    }
    return formattedBulat;
  }

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

  function revokeDownload() {
    if (state.downloadUrl) {
      try {
        URL.revokeObjectURL(state.downloadUrl);
      } catch (e) { /* abaikan */ }
      state.downloadUrl = null;
    }
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.outputText) el.outputText.value = '';
    if (el.summaryTbody) el.summaryTbody.innerHTML = '';
    if (el.noteResult) {
      el.noteResult.textContent = '';
      el.noteResult.hidden = true;
    }
    state.lastResult = null;
    state.lastTextToCopy = '';
    revokeDownload();
  }

  function updateCharCount() {
    var text = el.input ? el.input.value : '';
    var len = text.length;
    if (el.charCount) {
      el.charCount.textContent = len.toLocaleString('id-ID') + ' / ' + state.maxChars.toLocaleString('id-ID') + ' karakter';
      if (len > state.maxChars) {
        el.charCount.style.color = 'var(--pink)';
      } else {
        el.charCount.style.color = '';
      }
    }
    var hasText = text.trim().length > 0;
    var hasResult = !!state.lastResult;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Memproses...' : 'Ubah';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasText && !hasResult);
    }
  }

  function updateModeUI() {
    var modeVal = el.mode ? el.mode.value : 'ke_json';
    if (modeVal !== 'ke_json' && modeVal !== 'ke_csv' && modeVal !== 'ringkas') {
      modeVal = 'ke_json';
    }
    state.mode = modeVal;

    if (modeVal === 'ke_json') {
      if (el.inputLabel) el.inputLabel.textContent = 'Teks CSV';
      if (el.input) el.input.placeholder = 'Tempel atau ketik teks CSV di sini...';
      if (el.inputHint) el.inputHint.textContent = 'Ketik atau tempel teks tabel CSV yang ingin diubah ke JSON.';
      if (el.groupPemisah) el.groupPemisah.hidden = false;
      if (el.groupIndent) el.groupIndent.hidden = false;
      if (el.groupHeader) el.groupHeader.hidden = false;
      if (el.groupRapikan) el.groupRapikan.hidden = false;
      state.downloadFilename = 'hasil.json';
      state.downloadMime = 'application/json;charset=utf-8';
    } else if (modeVal === 'ke_csv') {
      if (el.inputLabel) el.inputLabel.textContent = 'Teks JSON';
      if (el.input) el.input.placeholder = 'Tempel atau ketik teks JSON di sini (mis. array objek [{"nama": "Budi"}])...';
      if (el.inputHint) el.inputHint.textContent = 'Ketik atau tempel teks JSON (array objek atau array dari array) yang ingin diubah ke CSV.';
      if (el.groupPemisah) el.groupPemisah.hidden = false;
      if (el.groupIndent) el.groupIndent.hidden = true;
      if (el.groupHeader) el.groupHeader.hidden = true;
      if (el.groupRapikan) el.groupRapikan.hidden = false;
      state.downloadFilename = 'hasil.csv';
      state.downloadMime = 'text/csv;charset=utf-8';
    } else if (modeVal === 'ringkas') {
      if (el.inputLabel) el.inputLabel.textContent = 'Teks CSV';
      if (el.input) el.input.placeholder = 'Tempel atau ketik teks CSV di sini...';
      if (el.inputHint) el.inputHint.textContent = 'Ketik atau tempel teks tabel CSV untuk melihat ringkasan kolomnya.';
      if (el.groupPemisah) el.groupPemisah.hidden = false;
      if (el.groupIndent) el.groupIndent.hidden = true;
      if (el.groupHeader) el.groupHeader.hidden = false;
      if (el.groupRapikan) el.groupRapikan.hidden = false;
      state.downloadFilename = 'ringkasan-csv.txt';
      state.downloadMime = 'text/plain;charset=utf-8';
    }

    resetResults();
    setStatus('Tempel teks di atas, pilih mode yang diinginkan, lalu tekan "Ubah".', '');
    updateCharCount();
  }

  function isiContoh() {
    var modeVal = el.mode ? el.mode.value : 'ke_json';
    if (modeVal === 'ke_csv') {
      if (el.input) el.input.value = state.contohJson;
    } else {
      if (el.input) el.input.value = state.contohCsv;
    }
    resetResults();
    updateCharCount();
    setStatus('Contoh data berhasil diisi.', 'ok');
    if (el.input) el.input.focus();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/csv/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsLoaded = true;
        if (data.max_chars) state.maxChars = data.max_chars;
        if (data.max_bytes) state.maxBytes = data.max_bytes;
        if (data.max_rows) state.maxRows = data.max_rows;
        if (data.max_cols) state.maxCols = data.max_cols;
        if (data.contoh_csv) state.contohCsv = data.contoh_csv;
        if (data.contoh_json) state.contohJson = data.contoh_json;

        if (data.subjudul && el.limits) {
          el.limits.textContent = 'Maks ' + state.maxChars.toLocaleString('id-ID') + ' karakter (1 MB), ' +
            state.maxRows.toLocaleString('id-ID') + ' baris, ' + state.maxCols.toLocaleString('id-ID') + ' kolom';
        }
        if (data.note && el.note) {
          el.note.textContent = data.note;
        }
        updateCharCount();
      })
      .catch(function () {
        /* Tetap pakai nilai bawaan jika permintaan limits gagal */
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
      } catch (err) { /* abaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan CSV Tools belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Ukuran teks melebihi batas 1 MB atau ' + state.maxChars.toLocaleString('id-ID') + ' karakter.';
        } else {
          message = 'Terjadi kendala saat memproses data CSV (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitProcess() {
    if (state.busy) return;

    var text = el.input ? el.input.value : '';
    if (!text.trim()) {
      resetResults();
      setStatus('Tempel atau ketik teks terlebih dahulu.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var modeVal = el.mode ? el.mode.value : 'ke_json';
    var pemisahVal = el.pemisah ? el.pemisah.value : 'otomatis';
    var indentVal = el.indent ? el.indent.value : '2';
    var headerVal = (el.header && el.header.checked) ? 'ya' : 'tidak';
    var rapikanVal = (el.rapikan && el.rapikan.checked) ? 'ya' : 'tidak';

    var form = new FormData();
    form.append('teks', text);
    form.append('mode', modeVal);
    form.append('pemisah', pemisahVal);
    form.append('header', headerVal);
    form.append('rapikan', rapikanVal);
    form.append('indent', indentVal);

    state.busy = true;
    updateCharCount();
    setStatus('Sedang memproses...', 'busy');

    fetch(serverBase + '/api/csv', {
      method: 'POST',
      body: form
    })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('Proses berhasil diselesaikan.', 'ok');
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
        updateCharCount();
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    var mode = data.mode || state.mode;
    state.lastTextToCopy = (data.keluaran && data.keluaran.teks) ? data.keluaran.teks : '';

    // Kartu statistik
    var ringkasan = data.ringkasan || {};
    var totalBaris = (typeof ringkasan.total_baris === 'number') ? ringkasan.total_baris : ringkasan.jumlah_baris || 0;
    var totalKolom = (typeof ringkasan.total_kolom === 'number') ? ringkasan.total_kolom : ringkasan.jumlah_kolom || 0;
    var pemisahStr = ringkasan.pemisah_terpakai || data.pemisah_terpakai || '-';

    if (el.statRows) el.statRows.textContent = formatAngkaId(totalBaris);
    if (el.statCols) el.statCols.textContent = formatAngkaId(totalKolom);
    if (el.statDelim) el.statDelim.textContent = pemisahStr;

    if (mode === 'ringkas') {
      if (el.statEmptyColsWrap) el.statEmptyColsWrap.hidden = false;
      if (el.statEmptyCols) el.statEmptyCols.textContent = formatAngkaId(ringkasan.kolom_kosong || 0);

      // Tampilkan tabel ringkasan
      if (el.outputCodeWrap) el.outputCodeWrap.hidden = true;
      if (el.outputTableWrap) el.outputTableWrap.hidden = false;
      renderTableSummary(data.kolom || []);
      state.downloadFilename = 'ringkasan-csv.txt';
      state.downloadMime = 'text/plain;charset=utf-8';
      if (el.download) el.download.textContent = 'Unduh ringkasan-csv.txt';
    } else {
      if (el.statEmptyColsWrap) el.statEmptyColsWrap.hidden = true;

      // Tampilkan textarea kode hasil
      if (el.outputCodeWrap) el.outputCodeWrap.hidden = false;
      if (el.outputTableWrap) el.outputTableWrap.hidden = true;

      if (el.outputLabel) {
        el.outputLabel.textContent = (mode === 'ke_json') ? 'Hasil Format JSON' : 'Hasil Format CSV';
      }
      if (el.outputText) {
        el.outputText.value = state.lastTextToCopy;
      }

      if (mode === 'ke_json') {
        state.downloadFilename = 'hasil.json';
        state.downloadMime = 'application/json;charset=utf-8';
        if (el.download) el.download.textContent = 'Unduh hasil.json';
      } else {
        state.downloadFilename = 'hasil.csv';
        state.downloadMime = 'text/csv;charset=utf-8';
        if (el.download) el.download.textContent = 'Unduh hasil.csv';
      }
    }

    if (el.noteResult && data.catatan) {
      el.noteResult.textContent = data.catatan;
      el.noteResult.hidden = false;
    } else if (el.noteResult) {
      el.noteResult.hidden = true;
    }
  }

  function renderTableSummary(kolomList) {
    if (!el.summaryTbody) return;
    el.summaryTbody.innerHTML = '';

    if (!Array.isArray(kolomList) || kolomList.length === 0) {
      var trEmpty = document.createElement('tr');
      trEmpty.innerHTML = '<td colspan="6" style="text-align: center; color: var(--text-muted);">Tidak ada kolom yang dianalisis.</td>';
      el.summaryTbody.appendChild(trEmpty);
      return;
    }

    var frag = document.createDocumentFragment();
    kolomList.forEach(function (c) {
      var tr = document.createElement('tr');

      // Tipe badge
      var badgeClass = 'badge--available';
      if (c.tipe === 'kosong') badgeClass = 'badge--soon';
      else if (c.tipe === 'campuran') badgeClass = 'badge--soon';

      // Rincian ekstrem / nilai terbanyak
      var rincianTeks = '-';
      if (c.tipe === 'angka' && typeof c.nilai_terkecil !== 'undefined' && typeof c.nilai_terbesar !== 'undefined') {
        rincianTeks = formatAngkaId(c.nilai_terkecil) + ' s.d. ' + formatAngkaId(c.nilai_terbesar);
      } else if (c.tipe === 'tanggal' && c.nilai_terkecil && c.nilai_terbesar) {
        rincianTeks = escapeHtml(String(c.nilai_terkecil)) + ' s.d. ' + escapeHtml(String(c.nilai_terbesar));
      } else if (Array.isArray(c.nilai_terbanyak) && c.nilai_terbanyak.length > 0) {
        var items = c.nilai_terbanyak.map(function (t) {
          return '"' + escapeHtml(String(t.nilai)) + '" (' + formatAngkaId(t.jumlah) + 'x)';
        });
        rincianTeks = items.join(', ');
      }

      tr.innerHTML = '<td class="mono">' + escapeHtml(String(c.indeks)) + '</td>' +
        '<td><strong>' + escapeHtml(String(c.nama)) + '</strong></td>' +
        '<td><span class="badge ' + badgeClass + '">' + escapeHtml(String(c.tipe)) + '</span></td>' +
        '<td class="mono">' + formatAngkaId(c.sel_kosong) + '</td>' +
        '<td class="mono">' + formatAngkaId(c.nilai_unik) + '</td>' +
        '<td>' + rincianTeks + '</td>';

      frag.appendChild(tr);
    });

    el.summaryTbody.appendChild(frag);
  }

  function copyResult() {
    if (!state.lastTextToCopy) return;

    function notify(ok) {
      if (el.copy) {
        var orig = el.copy.textContent;
        el.copy.textContent = ok ? 'Tersalin!' : 'Gagal salin';
        setTimeout(function () {
          el.copy.textContent = orig;
        }, 1500);
      }
      if (ok) {
        setStatus('Hasil disalin ke papan klip.', 'ok');
      } else {
        setStatus('Gagal menyalin hasil.', 'error');
      }
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(state.lastTextToCopy).then(function () {
        notify(true);
      }).catch(function () {
        fallbackCopy(state.lastTextToCopy, notify);
      });
    } else {
      fallbackCopy(state.lastTextToCopy, notify);
    }
  }

  function fallbackCopy(text, cb) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      cb(ok);
    } catch (e) {
      cb(false);
    }
  }

  function downloadResult() {
    if (!state.lastTextToCopy) return;
    revokeDownload();

    var blob = new Blob([state.lastTextToCopy], { type: state.downloadMime });
    var url = URL.createObjectURL(blob);
    state.downloadUrl = url;

    var a = document.createElement('a');
    a.href = url;
    a.download = state.downloadFilename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function resetAll() {
    if (el.input) el.input.value = '';
    resetResults();
    updateCharCount();
    setStatus('Data dikosongkan. Tempel teks baru lalu tekan "Ubah".', '');
    if (el.input) el.input.focus();
  }

  function syncTriggers(isOpen) {
    var triggers = document.querySelectorAll('[data-tool-action="csv"]');
    for (var i = 0; i < triggers.length; i++) {
      var t = triggers[i];
      if (t.tagName === 'BUTTON' || t.classList.contains('tool-card__open')) {
        t.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      }
      var card = t.closest ? t.closest('.tool-card') : null;
      if (card) {
        card.classList.toggle('tool-card--active', isOpen);
      }
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

    setTimeout(function () {
      if (el.input) el.input.focus();
    }, 100);
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
  if (el.mode) el.mode.addEventListener('change', updateModeUI);
  if (el.btnContoh) el.btnContoh.addEventListener('click', isiContoh);
  if (el.input) el.input.addEventListener('input', updateCharCount);
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

  // Daftarkan panel ke registry global OmniTools
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['csv'] = toggle;

  // Inisialisasi awal
  updateModeUI();

  // Dukungan buka lewat parameter URL: ?alat=csv
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('alat') !== 'csv') return;

      var paramMode = params.get('mode');
      if (paramMode && (paramMode === 'ke_json' || paramMode === 'ke_csv' || paramMode === 'ringkas')) {
        if (el.mode) el.mode.value = paramMode;
      }
      var paramPemisah = params.get('pemisah');
      if (paramPemisah && el.pemisah) {
        el.pemisah.value = paramPemisah;
      }
      updateModeUI();
      open();
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
