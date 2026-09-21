/* =========================================================================
   Panel alat: Hapus baris duplikat (Remove Duplicates)
   Teks dikirim ke server lewat multipart/form-data, dibersihkan di memori,
   lalu dibuang setelah selesai. Tidak ada teks yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('remove-duplicates-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('remove-duplicates-close'),
    limits: document.getElementById('remove-duplicates-limits'),
    note: document.getElementById('remove-duplicates-note'),
    input: document.getElementById('remove-duplicates-input'),
    trim: document.getElementById('remove-duplicates-trim'),
    dropEmpty: document.getElementById('remove-duplicates-drop-empty'),
    status: document.getElementById('remove-duplicates-status'),
    clear: document.getElementById('remove-duplicates-clear'),
    submit: document.getElementById('remove-duplicates-submit'),
    hint: document.getElementById('remove-duplicates-hint'),
    outputWrap: document.getElementById('remove-duplicates-output-wrap'),
    output: document.getElementById('remove-duplicates-output'),
    linesIn: document.getElementById('remove-duplicates-lines-in'),
    linesOut: document.getElementById('remove-duplicates-lines-out'),
    dupesRemoved: document.getElementById('remove-duplicates-dupes-removed'),
    emptyRemoved: document.getElementById('remove-duplicates-empty-removed'),
    copy: document.getElementById('remove-duplicates-copy'),
    download: document.getElementById('remove-duplicates-download')
  };

  var numberFmt = new Intl.NumberFormat('id-ID');

  var FALLBACK_LIMITS = {
    max_chars: 200000,
    max_bytes: 1048576,
    max_mb: 1,
    keep_options: [
      { value: 'first', label: 'Simpan kemunculan pertama' },
      { value: 'last', label: 'Simpan kemunculan terakhir' }
    ],
    defaults: {
      keep: 'first',
      case_sensitive: false,
      trim: true,
      drop_empty: true
    }
  };

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    busy: false,
    lastFocus: null
  };

  // --- Pembantu status dan kontrol ----------------------------------------
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

  function resetResults() {
    if (el.hint) el.hint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.output) el.output.value = '';
    if (el.linesIn) el.linesIn.textContent = '0';
    if (el.linesOut) el.linesOut.textContent = '0';
    if (el.dupesRemoved) el.dupesRemoved.textContent = '0';
    if (el.emptyRemoved) el.emptyRemoved.textContent = '0';
  }

  function updateControls() {
    var hasText = !!(el.input && el.input.value.length > 0);
    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Sedang memproses…' : 'Hapus duplikat';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || !hasText;
    }
  }

  function applyDefaults(defaults) {
    if (!defaults) return;
    if (defaults.keep) {
      var keepRadio = panel.querySelector('input[name="remove-duplicates-keep"][value="' + defaults.keep + '"]');
      if (keepRadio) keepRadio.checked = true;
    }
    if (typeof defaults.case_sensitive === 'boolean') {
      var caseRadio = panel.querySelector('input[name="remove-duplicates-case"][value="' + (defaults.case_sensitive ? 'true' : 'false') + '"]');
      if (caseRadio) caseRadio.checked = true;
    }
    if (typeof defaults.trim === 'boolean' && el.trim) {
      el.trim.checked = defaults.trim;
    }
    if (typeof defaults.drop_empty === 'boolean' && el.dropEmpty) {
      el.dropEmpty.checked = defaults.drop_empty;
    }
  }

  function describeLimits(online) {
    if (!el.limits) return;
    var chars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (online) {
      el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter, aturan dari server';
    } else {
      el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter, aturan bawaan';
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/remove-duplicates/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_chars: data.max_chars || FALLBACK_LIMITS.max_chars,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
          keep_options: data.keep_options || FALLBACK_LIMITS.keep_options,
          defaults: data.defaults || FALLBACK_LIMITS.defaults
        };
        state.limitsLoaded = true;
        if (data.defaults) {
          applyDefaults(data.defaults);
        }
        describeLimits(true);
      })
      .catch(function () {
        describeLimits(false);
      });
  }

  // --- Kirim dan olah teks ------------------------------------------------
  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      var code = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error) {
          message = parsed.error.message || '';
          code = parsed.error.code || '';
        }
      } catch (err) { /* diabaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan hapus duplikat belum tersambung ke server. Coba lagi nanti.';
        } else if (response.status === 413) {
          message = 'Teks terlalu panjang. Batasnya 200.000 karakter.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      } else if (code === 'TOO_LONG') {
        message += ' Silakan perpendek teks.';
      }
      throw new Error(message);
    });
  }

  function submitDedupe() {
    if (state.busy) return;

    var textVal = el.input ? el.input.value : '';
    if (!textVal || !textVal.trim()) {
      setStatus('Masukkan dulu daftar baris yang ingin dirapikan.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var maxChars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (textVal.length > maxChars) {
      setStatus('Teks terlalu panjang. Batasnya ' + numberFmt.format(maxChars) + ' karakter.', 'error');
      return;
    }

    resetResults();

    var keepChecked = panel.querySelector('input[name="remove-duplicates-keep"]:checked');
    var keepVal = keepChecked ? keepChecked.value : 'first';

    var caseChecked = panel.querySelector('input[name="remove-duplicates-case"]:checked');
    var caseVal = caseChecked ? caseChecked.value : 'false';

    var trimVal = el.trim ? el.trim.checked : true;
    var dropEmptyVal = el.dropEmpty ? el.dropEmpty.checked : true;

    var form = new FormData();
    form.append('text', textVal);
    form.append('keep', keepVal);
    form.append('case_sensitive', caseVal === 'true' ? 'true' : 'false');
    form.append('trim', trimVal ? 'true' : 'false');
    form.append('drop_empty', dropEmptyVal ? 'true' : 'false');

    state.busy = true;
    updateControls();
    setStatus('Sedang memproses…', 'busy');

    fetch(serverBase + '/api/remove-duplicates', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        if (el.output) el.output.value = data.text || '';
        if (el.linesIn) el.linesIn.textContent = numberFmt.format(data.lines_in || 0);
        if (el.linesOut) el.linesOut.textContent = numberFmt.format(data.lines_out || 0);
        if (el.dupesRemoved) el.dupesRemoved.textContent = numberFmt.format(data.duplicates_removed || 0);
        if (el.emptyRemoved) el.emptyRemoved.textContent = numberFmt.format(data.empty_removed || 0);

        if (el.hint) el.hint.hidden = true;
        if (el.outputWrap) el.outputWrap.hidden = false;
        setStatus('Selesai. ' + numberFmt.format(data.duplicates_removed || 0) + ' baris duplikat dibuang.', 'ok');
      })
      .catch(function (error) {
        var isNetwork = error && (error.name === 'TypeError' || /network|fetch|failed to fetch/i.test(error.message));
        var msg = isNetwork ? 'Tidak bisa menghubungi server. Coba lagi sebentar lagi.' : (error && error.message ? error.message : 'Gagal memproses daftar baris.');
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
      } catch (e) {
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
    a.download = 'daftar-tanpa-duplikat.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 100);
  }

  function resetAll() {
    if (el.input) {
      el.input.value = '';
      el.input.focus();
    }
    applyDefaults(state.limits.defaults || FALLBACK_LIMITS.defaults);
    resetResults();
    updateControls();
    setStatus('Masukkan daftar baris, atur pilihan, lalu tekan "Hapus duplikat".', '');
  }

  // --- Buka dan tutup panel -----------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="remove-duplicates"]');
    triggers.forEach(function (trigger) {
      trigger.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
  }

  function open() {
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (panel.hidden) {
      state.lastFocus = document.activeElement;
      panel.hidden = false;
      loadLimits();
      describeLimits(state.limitsLoaded);
      syncTriggers(true);
      panel.focus({ preventScroll: true });
      if (el.input) {
        el.input.focus();
      }
      if (!el.input || !el.input.value) {
        setStatus('Masukkan daftar baris, atur pilihan, lalu tekan "Hapus duplikat".', '');
      }
    }
    panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
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
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      if (panel.contains(document.activeElement)) {
        event.preventDefault();
        submitDedupe();
      }
    }
  }

  // --- Pemasangan event ---------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('input', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitDedupe);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  // Daftarkan panel supaya kartu "Remove Duplicates" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['remove-duplicates'] = toggle;
})();
