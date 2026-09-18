/* =========================================================================
   Panel alat: Pengubah huruf (Case Converter)
   Teks dikirim ke server lewat multipart/form-data, diubah di memori,
   lalu dibuang setelah selesai. Tidak ada teks yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('case-convert-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('case-convert-close'),
    limits: document.getElementById('case-convert-limits'),
    note: document.getElementById('case-convert-note'),
    input: document.getElementById('case-convert-input'),
    modesContainer: document.getElementById('case-convert-modes'),
    status: document.getElementById('case-convert-status'),
    clear: document.getElementById('case-convert-clear'),
    submit: document.getElementById('case-convert-submit'),
    hint: document.getElementById('case-convert-hint'),
    outputWrap: document.getElementById('case-convert-output-wrap'),
    output: document.getElementById('case-convert-output'),
    meta: document.getElementById('case-convert-meta'),
    copy: document.getElementById('case-convert-copy'),
    download: document.getElementById('case-convert-download')
  };

  var numberFmt = new Intl.NumberFormat('id-ID');

  var FALLBACK_LIMITS = {
    max_chars: 200000,
    max_bytes: 1048576,
    max_mb: 1,
    modes: ['upper', 'lower', 'title', 'sentence', 'inverse', 'alternating', 'camel', 'snake', 'kebab', 'slug'],
    mode_labels: {
      upper: 'HURUF BESAR',
      lower: 'huruf kecil',
      title: 'Kapital Tiap Kata',
      sentence: 'Kapital Awal Kalimat',
      inverse: 'Balik Besar-Kecil',
      alternating: 'Selang-seling',
      camel: 'camelCase',
      snake: 'snake_case',
      kebab: 'kebab-case',
      slug: 'slug-url'
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
    downloadUrl: null
  };

  // --- Pembantu -----------------------------------------------------------
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
    if (el.meta) el.meta.textContent = '';
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }
  }

  function updateControls() {
    var hasText = !!(el.input && el.input.value.length > 0);
    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Mengubah…' : 'Ubah';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || !hasText;
    }
  }

  function getSelectedMode() {
    var checked = panel.querySelector('input[name="case-convert-mode"]:checked');
    return checked ? checked.value : 'upper';
  }

  // --- Aturan dan pilihan mode dari server --------------------------------
  function buildModes(modes, labels) {
    if (!el.modesContainer || !Array.isArray(modes) || !modes.length) return;
    var current = getSelectedMode();
    el.modesContainer.textContent = '';
    modes.forEach(function (modeKey, idx) {
      var labelText = (labels && labels[modeKey]) ? labels[modeKey] : modeKey;
      var lbl = document.createElement('label');
      lbl.className = 'caseconvert__mode-label';

      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'case-convert-mode';
      radio.value = modeKey;
      if (current ? modeKey === current : idx === 0) {
        radio.checked = true;
      }

      var span = document.createElement('span');
      span.textContent = labelText;

      lbl.appendChild(radio);
      lbl.appendChild(document.createTextNode(' '));
      lbl.appendChild(span);
      el.modesContainer.appendChild(lbl);
    });
  }

  function describeLimits(online) {
    if (!el.limits) return;
    var chars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    var modeCount = (state.limits.modes && state.limits.modes.length) || 10;
    if (online) {
      el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter, ' + numberFmt.format(modeCount) + ' mode pengubahan';
    } else {
      el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter, aturan bawaan';
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/case/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_chars: data.max_chars || FALLBACK_LIMITS.max_chars,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
          modes: data.modes || FALLBACK_LIMITS.modes,
          mode_labels: data.mode_labels || FALLBACK_LIMITS.mode_labels
        };
        state.limitsLoaded = true;
        buildModes(data.modes, data.mode_labels);
        describeLimits(true);
      })
      .catch(function () {
        describeLimits(false);
      });
  }

  // --- Kirim dan ubah teks ------------------------------------------------
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
          message = 'Layanan pengubah huruf belum tersambung ke server. Coba lagi nanti.';
        } else if (response.status === 413) {
          message = 'Teks melebihi batas yang diizinkan. Silakan perpendek teks.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      } else if (code === 'TOO_LONG') {
        message += ' Silakan perpendek teks.';
      }
      throw new Error(message);
    });
  }

  function submitConvert() {
    if (state.busy) return;

    var textVal = el.input ? el.input.value : '';
    if (!textVal || !textVal.trim()) {
      setStatus('Teks kosong atau hanya berisi spasi. Masukkan teks untuk diubah.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var maxChars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (textVal.length > maxChars) {
      setStatus('Panjang teks ' + numberFmt.format(textVal.length) + ' karakter melebihi batas ' + numberFmt.format(maxChars) + ' karakter. Silakan perpendek teks.', 'error');
      return;
    }

    var modeVal = getSelectedMode();
    if (!modeVal) {
      setStatus('Mode pengubahan wajib dipilih.', 'error');
      return;
    }

    // Kosongkan hasil sebelum mulai mengirim
    resetResults();

    var form = new FormData();
    form.append('text', textVal);
    form.append('mode', modeVal);

    state.busy = true;
    updateControls();
    setStatus('Mengirim teks ke server dan mengubah format…', 'busy');

    fetch(serverBase + '/api/case', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        if (el.output) el.output.value = data.text || '';
        if (el.meta) {
          var modeLabel = (state.limits.mode_labels && state.limits.mode_labels[data.mode]) || data.mode;
          var metaText = numberFmt.format(data.chars_out || 0) + ' karakter, ' +
                         numberFmt.format(data.words || 0) + ' kata, mode ' + modeLabel;
          el.meta.textContent = metaText;
        }
        if (el.hint) el.hint.hidden = true;
        if (el.outputWrap) el.outputWrap.hidden = false;
        setStatus('Selesai diubah ke ' + ((state.limits.mode_labels && state.limits.mode_labels[data.mode]) || data.mode) + '.', 'ok');
      })
      .catch(function (error) {
        var isNetwork = error && (error.name === 'TypeError' || /network|fetch|failed to fetch/i.test(error.message));
        var msg = isNetwork ? 'Tidak bisa menghubungi server. Coba lagi.' : (error && error.message ? error.message : 'Gagal mengubah teks.');
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
    a.download = 'hasil-ubah-huruf.txt';
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
    resetResults();
    updateControls();
    setStatus('Ketik atau tempel teks, pilih mode, lalu tekan "Ubah".', '');
  }

  // --- Buka dan tutup panel -----------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="case-convert"]');
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
        setStatus('Ketik atau tempel teks, pilih mode, lalu tekan "Ubah".', '');
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
        submitConvert();
      }
    }
  }

  // --- Pemasangan event ---------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('input', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitConvert);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  // Daftarkan panel supaya kartu "Case Converter" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['case-convert'] = toggle;
})();
