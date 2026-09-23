/* =========================================================================
   Panel alat: Rapikan teks (Text Formatter)
   Teks dikirim ke server lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada teks yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('text-formatter-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('text-formatter-close'),
    limits: document.getElementById('text-formatter-limits'),
    note: document.getElementById('text-formatter-note'),
    input: document.getElementById('text-formatter-input'),
    collapseSpaces: document.getElementById('text-formatter-collapse-spaces'),
    trimLines: document.getElementById('text-formatter-trim-lines'),
    tabsToSpaces: document.getElementById('text-formatter-tabs-to-spaces'),
    spaceBeforePunctuation: document.getElementById('text-formatter-space-before-punctuation'),
    unifyCharacters: document.getElementById('text-formatter-unify-characters'),
    status: document.getElementById('text-formatter-status'),
    clear: document.getElementById('text-formatter-clear'),
    submit: document.getElementById('text-formatter-submit'),
    hint: document.getElementById('text-formatter-hint'),
    outputWrap: document.getElementById('text-formatter-output-wrap'),
    output: document.getElementById('text-formatter-output'),
    charsIn: document.getElementById('text-formatter-chars-in'),
    charsOut: document.getElementById('text-formatter-chars-out'),
    linesIn: document.getElementById('text-formatter-lines-in'),
    linesOut: document.getElementById('text-formatter-lines-out'),
    blankRemoved: document.getElementById('text-formatter-blank-removed'),
    charsSaved: document.getElementById('text-formatter-chars-saved'),
    copy: document.getElementById('text-formatter-copy'),
    download: document.getElementById('text-formatter-download')
  };

  var numberFmt = new Intl.NumberFormat('id-ID');

  var FALLBACK_LIMITS = {
    max_chars: 200000,
    max_bytes: 1000000,
    max_mb: 1,
    defaults: {
      collapse_spaces: true,
      trim_lines: true,
      tabs_to_spaces: true,
      tab_width: 4,
      space_before_punctuation: true,
      unify_characters: true,
      blank_mode: 'collapse',
      line_mode: 'keep'
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

  function getRadioValue(name, fallback) {
    var checked = panel.querySelector('input[name="' + name + '"]:checked');
    return checked ? checked.value : fallback;
  }

  function setRadioValue(name, value) {
    var target = panel.querySelector('input[name="' + name + '"][value="' + value + '"]');
    if (target) {
      target.checked = true;
    }
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

  function resetResults() {
    if (el.hint) el.hint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.output) el.output.value = '';
    if (el.charsIn) el.charsIn.textContent = '0';
    if (el.charsOut) el.charsOut.textContent = '0';
    if (el.linesIn) el.linesIn.textContent = '0';
    if (el.linesOut) el.linesOut.textContent = '0';
    if (el.blankRemoved) el.blankRemoved.textContent = '0';
    if (el.charsSaved) el.charsSaved.textContent = '0';
  }

  function updateControls() {
    var hasText = !!(el.input && el.input.value.length > 0);
    var hasOutput = !!(el.output && el.output.value.length > 0);
    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Sedang merapikan...' : 'Rapikan teks';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasText && !hasOutput);
    }
  }

  function applyDefaults(defaults) {
    if (!defaults) return;
    if (typeof defaults.collapse_spaces === 'boolean' && el.collapseSpaces) {
      el.collapseSpaces.checked = defaults.collapse_spaces;
    }
    if (typeof defaults.trim_lines === 'boolean' && el.trimLines) {
      el.trimLines.checked = defaults.trim_lines;
    }
    if (typeof defaults.tabs_to_spaces === 'boolean' && el.tabsToSpaces) {
      el.tabsToSpaces.checked = defaults.tabs_to_spaces;
    }
    if (typeof defaults.space_before_punctuation === 'boolean' && el.spaceBeforePunctuation) {
      el.spaceBeforePunctuation.checked = defaults.space_before_punctuation;
    }
    if (typeof defaults.unify_characters === 'boolean' && el.unifyCharacters) {
      el.unifyCharacters.checked = defaults.unify_characters;
    }
    if (defaults.tab_width) {
      setRadioValue('text-formatter-tab-width', String(defaults.tab_width));
    }
    if (defaults.blank_mode) {
      setRadioValue('text-formatter-blank-mode', defaults.blank_mode);
    }
    if (defaults.line_mode) {
      setRadioValue('text-formatter-line-mode', defaults.line_mode);
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
    fetch(serverBase + '/api/text-formatter/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_chars: data.max_chars || FALLBACK_LIMITS.max_chars,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
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
          message = 'Layanan rapikan teks belum tersambung ke server. Coba lagi nanti.';
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

  function submitFormat() {
    if (state.busy) return;

    var textVal = el.input ? el.input.value : '';
    if (!textVal) {
      setStatus('Masukkan teks yang ingin dirapikan.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var maxChars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (textVal.length > maxChars) {
      setStatus('Teks terlalu panjang. Batasnya ' + numberFmt.format(maxChars) + ' karakter.', 'error');
      return;
    }

    resetResults();

    var collapseVal = el.collapseSpaces ? el.collapseSpaces.checked : true;
    var trimVal = el.trimLines ? el.trimLines.checked : true;
    var tabsVal = el.tabsToSpaces ? el.tabsToSpaces.checked : true;
    var punctVal = el.spaceBeforePunctuation ? el.spaceBeforePunctuation.checked : true;
    var unifyVal = el.unifyCharacters ? el.unifyCharacters.checked : true;
    var tabWidthVal = getRadioValue('text-formatter-tab-width', '4');
    var blankModeVal = getRadioValue('text-formatter-blank-mode', 'collapse');
    var lineModeVal = getRadioValue('text-formatter-line-mode', 'keep');

    var form = new FormData();
    form.append('text', textVal);
    form.append('collapse_spaces', collapseVal ? 'true' : 'false');
    form.append('trim_lines', trimVal ? 'true' : 'false');
    form.append('tabs_to_spaces', tabsVal ? 'true' : 'false');
    form.append('space_before_punctuation', punctVal ? 'true' : 'false');
    form.append('unify_characters', unifyVal ? 'true' : 'false');
    form.append('tab_width', tabWidthVal);
    form.append('blank_mode', blankModeVal);
    form.append('line_mode', lineModeVal);

    state.busy = true;
    updateControls();
    setStatus('Sedang merapikan teks...', 'busy');

    fetch(serverBase + '/api/text-formatter', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        if (el.output) el.output.value = data.text || '';

        var mIn = data.masukan || {};
        var kOut = data.keluaran || {};
        var saved = data.dihemat || {};
        var blankDiff = Math.max(0, (mIn.blank_lines || 0) - (kOut.blank_lines || 0));

        if (el.charsIn) el.charsIn.textContent = numberFmt.format(mIn.chars || 0);
        if (el.charsOut) el.charsOut.textContent = numberFmt.format(kOut.chars || 0);
        if (el.linesIn) el.linesIn.textContent = numberFmt.format(mIn.lines || 0);
        if (el.linesOut) el.linesOut.textContent = numberFmt.format(kOut.lines || 0);
        if (el.blankRemoved) el.blankRemoved.textContent = numberFmt.format(blankDiff);
        if (el.charsSaved) el.charsSaved.textContent = numberFmt.format(saved.chars || 0);

        if (el.hint) el.hint.hidden = true;
        if (el.outputWrap) el.outputWrap.hidden = false;
        setStatus('Selesai. Teks berhasil dirapikan.', 'ok');
      })
      .catch(function (error) {
        var isNetwork = error && (error.name === 'TypeError' || /network|fetch|failed to fetch/i.test(error.message));
        var msg = isNetwork ? 'Tidak bisa menghubungi server. Coba lagi sebentar lagi.' : (error && error.message ? error.message : 'Gagal merapikan teks.');
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
    var blob = new Blob([el.output.value], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'hasil-rapikan.txt';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  }

  function resetAll() {
    if (state.busy) return;
    if (el.input) {
      el.input.value = '';
      el.input.focus();
    }
    resetResults();
    setStatus('Masukkan teks, atur pilihan, lalu tekan "Rapikan teks".', '');
    updateControls();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="text-formatter"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
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

    if (typeof panel.focus === 'function') {
      panel.focus({ preventScroll: true });
      if (el.input) {
        el.input.focus();
      }
      if (!el.input || !el.input.value) {
        setStatus('Masukkan teks, atur pilihan, lalu tekan "Rapikan teks".', '');
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
        submitFormat();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('input', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitFormat);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  // Daftarkan panel supaya kartu "Text Formatter" bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['text-formatter'] = toggle;

  updateControls();
})();
