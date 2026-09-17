/* =========================================================================
   Panel alat: Hitung kata (Word Counter)
   Teks dikirim ke server lewat multipart/form-data, dihitung di memori,
   lalu dibuang setelah selesai. Tidak ada teks yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('word-count-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('word-count-close'),
    limits: document.getElementById('word-count-limits'),
    note: document.getElementById('word-count-note'),
    input: document.getElementById('word-count-input'),
    submit: document.getElementById('word-count-submit'),
    clear: document.getElementById('word-count-clear'),
    status: document.getElementById('word-count-status'),
    hint: document.getElementById('word-count-hint'),
    grid: document.getElementById('word-count-grid'),
    details: document.getElementById('word-count-details'),
    valWords: document.getElementById('word-count-val-words'),
    valChars: document.getElementById('word-count-val-chars'),
    valCharsNoSpaces: document.getElementById('word-count-val-chars-no-spaces'),
    valSentences: document.getElementById('word-count-val-sentences'),
    valParagraphs: document.getElementById('word-count-val-paragraphs'),
    valLines: document.getElementById('word-count-val-lines'),
    valUniqueWords: document.getElementById('word-count-val-unique-words'),
    valReadingTime: document.getElementById('word-count-val-reading-time'),
    valSpeakingTime: document.getElementById('word-count-val-speaking-time'),
    longest: document.getElementById('word-count-longest'),
    topList: document.getElementById('word-count-top-list'),
    topEmpty: document.getElementById('word-count-top-empty')
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
    lastFocus: null
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
    if (el.grid) el.grid.hidden = true;
    if (el.details) el.details.hidden = true;
    if (el.topList) el.topList.textContent = '';
    if (el.topEmpty) el.topEmpty.hidden = true;
  }

  function updateControls() {
    var hasText = !!(el.input && el.input.value.length > 0);
    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Menghitung…' : 'Hitung';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || !hasText;
    }
  }

  // --- Aturan dari server -------------------------------------------------
  function describeLimits(online) {
    if (!el.limits) return;
    var chars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    var text = 'Maks ' + numberFmt.format(chars) + ' karakter';
    el.limits.textContent = text + (online ? ', aturan dari server' : ', aturan bawaan');
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/word-count/limits', { headers: { Accept: 'application/json' } })
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

  // --- Kirim dan hitung kata ----------------------------------------------
  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) {
          message = parsed.error.message;
        }
      } catch (err) { /* diabaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan hitung kata belum tersambung ke server. Coba lagi nanti.';
        } else if (response.status === 413) {
          message = 'Teks melebihi batas karakter yang diizinkan.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }
      throw new Error(message);
    });
  }

  function renderResult(data) {
    if (el.valWords) el.valWords.textContent = numberFmt.format(data.words || 0);
    if (el.valChars) el.valChars.textContent = numberFmt.format(data.chars || 0);
    if (el.valCharsNoSpaces) el.valCharsNoSpaces.textContent = numberFmt.format(data.chars_no_spaces || 0);
    if (el.valSentences) el.valSentences.textContent = numberFmt.format(data.sentences || 0);
    if (el.valParagraphs) el.valParagraphs.textContent = numberFmt.format(data.paragraphs || 0);
    if (el.valLines) el.valLines.textContent = numberFmt.format(data.lines || 0);
    if (el.valUniqueWords) el.valUniqueWords.textContent = numberFmt.format(data.unique_words || 0);
    if (el.valReadingTime) el.valReadingTime.textContent = numberFmt.format(data.reading_minutes || 0) + ' mnt';
    if (el.valSpeakingTime) el.valSpeakingTime.textContent = numberFmt.format(data.speaking_minutes || 0) + ' mnt';

    if (el.longest) {
      if (data.longest_word) {
        el.longest.textContent = data.longest_word + ' (' + numberFmt.format(data.longest_word.length) + ' karakter)';
      } else {
        el.longest.textContent = '-';
      }
    }

    if (el.topList) {
      el.topList.textContent = '';
      var topWords = data.top_words || [];
      if (topWords.length > 0) {
        topWords.forEach(function (item) {
          var word = item.word !== undefined ? item.word : item[0];
          var count = item.count !== undefined ? item.count : item[1];
          var li = document.createElement('li');
          li.className = 'wordcount__top-item';

          var wordSpan = document.createElement('span');
          wordSpan.className = 'wordcount__top-word';
          wordSpan.textContent = word;

          var countSpan = document.createElement('span');
          countSpan.className = 'wordcount__top-count';
          countSpan.textContent = numberFmt.format(count) + '×';

          li.appendChild(wordSpan);
          li.appendChild(document.createTextNode(' '));
          li.appendChild(countSpan);
          el.topList.appendChild(li);
        });
        if (el.topEmpty) el.topEmpty.hidden = true;
      } else {
        if (el.topEmpty) el.topEmpty.hidden = false;
      }
    }

    if (el.hint) el.hint.hidden = true;
    if (el.grid) el.grid.hidden = false;
    if (el.details) el.details.hidden = false;
  }

  function submitCount() {
    if (state.busy) return;

    var textVal = el.input ? el.input.value : '';
    if (!textVal || !textVal.trim()) {
      setStatus('Teks masih kosong. Masukkan teks untuk dihitung.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var maxChars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (textVal.length > maxChars) {
      setStatus('Panjang teks melebihi batas ' + numberFmt.format(maxChars) + ' karakter.', 'error');
      return;
    }

    var form = new FormData();
    form.append('text', textVal);

    state.busy = true;
    updateControls();
    setStatus('Mengirim teks ke server dan menghitung…', 'busy');

    fetch(serverBase + '/api/word-count', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResult(data);
        var msg = 'Selesai dihitung: ' + numberFmt.format(data.words) + ' kata, ' +
                  numberFmt.format(data.chars) + ' karakter.';
        setStatus(msg, 'ok');
      })
      .catch(function (error) {
        var errText = error && error.message ? error.message : 'Gagal menghitung kata.';
        setStatus(errText, 'error');
      })
      .then(function () {
        state.busy = false;
        updateControls();
      });
  }

  function resetAll() {
    if (el.input) {
      el.input.value = '';
      el.input.focus();
    }
    resetResults();
    updateControls();
    setStatus('Panel dibersihkan. Masukkan teks untuk mulai menghitung.', '');
  }

  // --- Buka dan tutup panel -----------------------------------------------
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="word-count"]');
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
        setStatus('Ketik atau tempel teks di atas, lalu tekan "Hitung".', '');
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
    }
  }

  // --- Pemasangan event ---------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('input', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitCount);
  if (el.clear) el.clear.addEventListener('click', resetAll);

  // Daftarkan panel supaya kartu "Word Counter" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['word-count'] = toggle;
})();
