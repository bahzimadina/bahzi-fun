/* =========================================================================
   Panel alat: Base64 Encoder/Decoder
   Teks dikirim ke server lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada teks yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('base64-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('base64-close'),
    limits: document.getElementById('base64-limits'),
    note: document.getElementById('base64-note'),
    input: document.getElementById('base64-input'),
    modesContainer: document.getElementById('base64-modes'),
    encodeOptions: document.getElementById('base64-encode-options'),
    variantStandard: document.getElementById('base64-variant-standard'),
    variantUrlsafe: document.getElementById('base64-variant-urlsafe'),
    wrapSelect: document.getElementById('base64-wrap'),
    status: document.getElementById('base64-status'),
    clear: document.getElementById('base64-clear'),
    submit: document.getElementById('base64-submit'),
    hint: document.getElementById('base64-hint'),
    outputWrap: document.getElementById('base64-output-wrap'),
    output: document.getElementById('base64-output'),
    meta: document.getElementById('base64-meta'),
    copy: document.getElementById('base64-copy'),
    download: document.getElementById('base64-download')
  };

  var numberFmt = new Intl.NumberFormat('id-ID');

  var FALLBACK_LIMITS = {
    max_chars: 200000,
    max_bytes: 1048576,
    max_mb: 1
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
    lastMode: 'encode'
  };

  // --- Pembantu status dan hasil ------------------------------------------
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
    var checked = panel.querySelector('input[name="base64-mode"]:checked');
    return checked ? checked.value : 'encode';
  }

  function getSelectedVariant() {
    var checked = panel.querySelector('input[name="base64-variant"]:checked');
    return checked ? checked.value : 'standard';
  }

  function onModeChange() {
    var mode = getSelectedMode();
    state.lastMode = mode;
    if (el.encodeOptions) {
      el.encodeOptions.hidden = (mode === 'decode');
    }
  }

  function describeLimits(online) {
    if (!el.limits) return;
    var chars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (online) {
      el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter, aturan server';
    } else {
      el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter, aturan bawaan';
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/base64/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_chars: data.max_chars || FALLBACK_LIMITS.max_chars,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb
        };
        state.limitsLoaded = true;
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
          message = 'Layanan Base64 belum tersambung ke server. Coba lagi nanti.';
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
    resetResults();

    var form = new FormData();
    form.append('text', textVal);
    form.append('mode', modeVal);

    if (modeVal === 'encode') {
      var variantVal = getSelectedVariant();
      var wrapVal = el.wrapSelect ? el.wrapSelect.value : '0';
      form.append('variant', variantVal);
      form.append('wrap', wrapVal);
    }

    state.busy = true;
    updateControls();
    setStatus('Mengirim teks ke server dan memproses Base64…', 'busy');

    fetch(serverBase + '/api/base64', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        state.lastMode = data.mode || state.lastMode;
        if (el.output) el.output.value = data.text || '';
        if (el.meta) {
          var metaText = '';
          if (data.mode === 'encode') {
            metaText = numberFmt.format(data.chars_in || 0) + ' karakter jadi ' +
                       numberFmt.format(data.chars_out || 0) + ' karakter Base64 (' +
                       numberFmt.format(data.bytes_out || 0) + ' byte)';
          } else {
            metaText = numberFmt.format(data.chars_in || 0) + ' karakter Base64 jadi ' +
                       numberFmt.format(data.chars_out || 0) + ' karakter teks (' +
                       numberFmt.format(data.bytes_out || 0) + ' byte)';
          }
          el.meta.textContent = metaText;
        }
        if (el.hint) el.hint.hidden = true;
        if (el.outputWrap) el.outputWrap.hidden = false;

        var successMsg = (data.mode === 'encode') ? 'Selesai diubah ke Base64.' : 'Selesai didekode ke teks.';
        setStatus(successMsg, 'ok');
      })
      .catch(function (error) {
        var isNetwork = error && (error.name === 'TypeError' || /network|fetch|failed to fetch/i.test(error.message));
        var msg = isNetwork ? 'Tidak bisa menghubungi server. Coba lagi.' : (error && error.message ? error.message : 'Gagal memproses Base64.');
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
    var isEncode = (state.lastMode === 'encode');
    var filename = isEncode ? 'hasil-base64.txt' : 'hasil-teks.txt';
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
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
    setStatus('Tempel teks atau Base64, pilih arah, lalu tekan tombolnya.', '');
  }

  // --- Buka dan tutup panel -----------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="base64"]');
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
        setStatus('Tempel teks atau Base64, pilih arah, lalu tekan tombolnya.', '');
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

  var modeRadios = panel.querySelectorAll('input[name="base64-mode"]');
  modeRadios.forEach(function (radio) {
    radio.addEventListener('change', onModeChange);
  });

  if (el.submit) el.submit.addEventListener('click', submitConvert);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  // Daftarkan panel supaya kartu "Base64 Encoder/Decoder" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['base64'] = toggle;
})();
