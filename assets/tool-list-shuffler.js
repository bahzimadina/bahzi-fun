/* =========================================================================
   Panel alat: Acak urutan daftar (List Shuffler)
   Daftar dikirim ke server lewat multipart/form-data, diacak di memori,
   lalu dibuang setelah selesai. Tidak ada teks yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('list-shuffler-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('list-shuffler-close'),
    limits: document.getElementById('list-shuffler-limits'),
    note: document.getElementById('list-shuffler-note'),
    input: document.getElementById('list-shuffler-input'),
    take: document.getElementById('list-shuffler-take'),
    seed: document.getElementById('list-shuffler-seed'),
    seedHint: document.getElementById('list-shuffler-seed-hint'),
    trim: document.getElementById('list-shuffler-trim'),
    dropEmpty: document.getElementById('list-shuffler-drop-empty'),
    status: document.getElementById('list-shuffler-status'),
    clear: document.getElementById('list-shuffler-clear'),
    submit: document.getElementById('list-shuffler-submit'),
    hint: document.getElementById('list-shuffler-hint'),
    outputWrap: document.getElementById('list-shuffler-output-wrap'),
    output: document.getElementById('list-shuffler-output'),
    linesIn: document.getElementById('list-shuffler-lines-in'),
    linesOut: document.getElementById('list-shuffler-lines-out'),
    seedUsed: document.getElementById('list-shuffler-seed-used'),
    emptyRemoved: document.getElementById('list-shuffler-empty-removed'),
    copy: document.getElementById('list-shuffler-copy'),
    again: document.getElementById('list-shuffler-again'),
    download: document.getElementById('list-shuffler-download')
  };

  if (el.seedHint) {
    el.seedHint.textContent = 'Salin angka dari kartu Kunci acak ke sini untuk mengulang urutan yang sama.';
  }

  var numberFmt = new Intl.NumberFormat('id-ID');

  var FALLBACK_LIMITS = {
    max_chars: 200000,
    max_bytes: 1048576,
    max_mb: 1,
    max_take: 200000,
    min_seed: 0,
    max_seed: 4294967295,
    defaults: {
      take: 0,
      seed: null,
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
    lastFocus: null,
    seedProvidedByUser: false,
    lastRequest: null
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
    if (el.seedUsed) el.seedUsed.textContent = '0';
    if (el.emptyRemoved) el.emptyRemoved.textContent = '0';
  }

  function updateControls() {
    var hasText = !!(el.input && el.input.value.length > 0);
    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Sedang mengacak…' : 'Acak urutan';
    }
    if (el.again) {
      el.again.disabled = state.busy || !state.lastRequest;
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasText && !el.output.value);
    }
  }

  function applyDefaults(defaults) {
    if (!defaults) return;
    if (el.take) {
      el.take.value = defaults.take ? String(defaults.take) : '';
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
    fetch(serverBase + '/api/list-shuffler/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_chars: data.max_chars || FALLBACK_LIMITS.max_chars,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
          max_take: data.max_take || FALLBACK_LIMITS.max_take,
          min_seed: data.min_seed !== undefined ? data.min_seed : FALLBACK_LIMITS.min_seed,
          max_seed: data.max_seed !== undefined ? data.max_seed : FALLBACK_LIMITS.max_seed,
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

  // --- Kirim dan olah daftar ----------------------------------------------
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
          message = 'Layanan acak urutan daftar belum tersambung ke server. Coba lagi nanti.';
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

  function submitShuffle(isRepeat) {
    if (state.busy) return;

    var textVal = '';
    var takeVal = '';
    var seedVal = '';
    var trimVal = true;
    var dropEmptyVal = true;
    var fromUserSeed = false;

    if (isRepeat && state.lastRequest) {
      textVal = state.lastRequest.text;
      takeVal = state.lastRequest.take;
      trimVal = state.lastRequest.trim;
      dropEmptyVal = state.lastRequest.dropEmpty;
      fromUserSeed = !!state.lastRequest.seedProvidedByUser;
      // Kalau kunci acak diisi pengunjung, Acak ulang memakai kunci itu juga;
      // kalau kosong, server membuat kunci baru tiap kali.
      seedVal = fromUserSeed ? state.lastRequest.seed : '';
    } else {
      textVal = el.input ? el.input.value : '';
      takeVal = el.take ? el.take.value.trim() : '';
      fromUserSeed = !!(state.seedProvidedByUser && el.seed && el.seed.value.trim() !== '');
      seedVal = fromUserSeed ? el.seed.value.trim() : '';
      trimVal = el.trim ? el.trim.checked : true;
      dropEmptyVal = el.dropEmpty ? el.dropEmpty.checked : true;
    }

    if (!textVal || !textVal.trim()) {
      setStatus('Masukkan dulu daftar yang ingin diacak.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var maxChars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (textVal.length > maxChars) {
      setStatus('Teks terlalu panjang. Batasnya ' + numberFmt.format(maxChars) + ' karakter.', 'error');
      return;
    }

    resetResults();

    var form = new FormData();
    form.append('text', textVal);
    if (takeVal !== '') {
      form.append('take', takeVal);
    }
    if (fromUserSeed && seedVal !== '') {
      form.append('seed', seedVal);
    }
    form.append('trim', trimVal ? 'true' : 'false');
    form.append('drop_empty', dropEmptyVal ? 'true' : 'false');

    state.busy = true;
    updateControls();
    setStatus('Sedang mengacak urutan…', 'busy');

    fetch(serverBase + '/api/list-shuffler', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        if (el.output) el.output.value = data.text || '';
        if (el.linesIn) el.linesIn.textContent = numberFmt.format(data.lines_in || 0);
        if (el.linesOut) el.linesOut.textContent = numberFmt.format(data.lines_out || 0);
        if (el.seedUsed) el.seedUsed.textContent = String(data.seed !== undefined ? data.seed : 0);
        if (el.emptyRemoved) el.emptyRemoved.textContent = numberFmt.format(data.empty_removed || 0);

        // Catat parameter permintaan yang berhasil untuk tombol "Acak ulang"
        state.lastRequest = {
          text: textVal,
          take: takeVal,
          seed: fromUserSeed ? seedVal : '',
          seedProvidedByUser: fromUserSeed,
          trim: trimVal,
          dropEmpty: dropEmptyVal
        };

        if (el.hint) el.hint.hidden = true;
        if (el.outputWrap) el.outputWrap.hidden = false;
        setStatus('Selesai. ' + numberFmt.format(data.lines_out || 0) + ' baris berhasil diacak.', 'ok');
      })
      .catch(function (error) {
        var isNetwork = error && (error.name === 'TypeError' || /network|fetch|failed to fetch/i.test(error.message));
        var msg = isNetwork ? 'Tidak bisa menghubungi server. Coba lagi sebentar lagi.' : (error && error.message ? error.message : 'Gagal mengacak daftar.');
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
    a.download = 'daftar-acak.txt';
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
    if (el.take) {
      el.take.value = '';
    }
    if (el.seed) {
      el.seed.value = '';
    }
    state.seedProvidedByUser = false;
    state.lastRequest = null;
    applyDefaults(state.limits.defaults || FALLBACK_LIMITS.defaults);
    resetResults();
    updateControls();
    setStatus('Masukkan daftar, atur pilihan, lalu tekan "Acak urutan".', '');
  }

  // --- Buka dan tutup panel -----------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="list-shuffler"]');
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
        setStatus('Masukkan daftar, atur pilihan, lalu tekan "Acak urutan".', '');
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
        submitShuffle(false);
      }
    }
  }

  // --- Pemasangan event ---------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('input', updateControls);
  }

  if (el.seed) {
    state.seedProvidedByUser = el.seed.value.trim() !== '';
    el.seed.addEventListener('input', function () {
      state.seedProvidedByUser = el.seed.value.trim() !== '';
    });
  }

  if (el.submit) el.submit.addEventListener('click', function () { submitShuffle(false); });
  if (el.again) el.again.addEventListener('click', function () { submitShuffle(true); });
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  // Daftarkan panel supaya kartu "List Shuffler" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['list-shuffler'] = toggle;

  updateControls();
})();
