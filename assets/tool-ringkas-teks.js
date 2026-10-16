/* =========================================================================
   Panel alat: Ringkas teks (Text Summary)
   Ringkas dokumen panjang jadi poin utama secara ekstraktif di memori server.
   Teks diproses di memori lalu dibuang, tidak disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('ringkas-teks-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('ringkas-teks-close'),
    limits: document.getElementById('ringkas-teks-limits'),
    note: document.getElementById('ringkas-teks-note'),
    input: document.getElementById('ringkas-teks-input'),
    inputHint: document.getElementById('ringkas-teks-input-hint'),
    rasio: document.getElementById('ringkas-teks-rasio'),
    format: document.getElementById('ringkas-teks-format'),
    submit: document.getElementById('ringkas-teks-submit'),
    clear: document.getElementById('ringkas-teks-clear'),
    status: document.getElementById('ringkas-teks-status'),
    outputWrap: document.getElementById('ringkas-teks-output-wrap'),
    output: document.getElementById('ringkas-teks-output'),
    copy: document.getElementById('ringkas-teks-copy'),
    download: document.getElementById('ringkas-teks-download'),
    stats: document.getElementById('ringkas-teks-stats'),
    keywords: document.getElementById('ringkas-teks-keywords'),
    keywordsWrap: document.getElementById('ringkas-teks-keywords-wrap'),
    statKalimat: document.getElementById('ringkas-teks-stat-kalimat'),
    statKarakter: document.getElementById('ringkas-teks-stat-karakter'),
    statHemat: document.getElementById('ringkas-teks-stat-hemat'),
    statWaktu: document.getElementById('ringkas-teks-stat-waktu')
  };

  var numberFmt = new Intl.NumberFormat('id-ID');

  var FALLBACK_LIMITS = {
    max_chars: 200000,
    max_bytes: 1000000,
    max_mb: 1,
    min_kalimat: 3,
    rasio_min: 10,
    rasio_max: 80,
    rasio_default: 30,
    format: ['paragraf', 'poin']
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
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.output) el.output.value = '';
    if (el.statKalimat) el.statKalimat.textContent = '0 dari 0';
    if (el.statKarakter) el.statKarakter.textContent = '0 / 0';
    if (el.statHemat) el.statHemat.textContent = '0%';
    if (el.statWaktu) el.statWaktu.textContent = '~0 dtk';
    if (el.keywords) el.keywords.innerHTML = '';
    if (el.keywordsWrap) el.keywordsWrap.hidden = true;
  }

  function updateControls() {
    var hasText = !!(el.input && el.input.value.trim().length > 0);
    var hasOutput = !!(el.output && el.output.value.length > 0);
    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Meringkas...' : 'Ringkas sekarang';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasText && !hasOutput);
    }
  }

  function describeLimits(online) {
    if (!el.limits) return;
    var chars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    var minK = state.limits.min_kalimat || FALLBACK_LIMITS.min_kalimat;
    if (online) {
      el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter, minimal ' + minK + ' kalimat (aturan server)';
    } else {
      el.limits.textContent = 'Maks ' + numberFmt.format(chars) + ' karakter, minimal ' + minK + ' kalimat';
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/text/summary/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_chars: data.max_chars || FALLBACK_LIMITS.max_chars,
          max_bytes: data.max_bytes || FALLBACK_LIMITS.max_bytes,
          max_mb: data.max_mb || FALLBACK_LIMITS.max_mb,
          min_kalimat: data.min_kalimat || FALLBACK_LIMITS.min_kalimat,
          rasio_min: data.rasio_min || FALLBACK_LIMITS.rasio_min,
          rasio_max: data.rasio_max || FALLBACK_LIMITS.rasio_max,
          rasio_default: data.rasio_default || FALLBACK_LIMITS.rasio_default,
          format: data.format || FALLBACK_LIMITS.format
        };
        state.limitsLoaded = true;
        if (data.defaults && data.defaults.rasio) {
          setRadioValue('ringkas-teks-rasio-opt', String(data.defaults.rasio));
        }
        if (data.defaults && data.defaults.format) {
          setRadioValue('ringkas-teks-format-opt', data.defaults.format);
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
      try {
        var data = JSON.parse(text);
        if (data && data.error && data.error.message) {
          message = data.error.message;
        }
      } catch (e) { /* bukan json */ }

      if (!message) {
        if (response.status === 413) {
          message = 'Teks terlalu panjang. Batasnya 200.000 karakter.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }
      throw new Error(message);
    });
  }

  function submitSummary() {
    if (state.busy) return;

    var textVal = el.input ? el.input.value : '';
    if (!textVal || !textVal.trim()) {
      setStatus('Teks masih kosong. Tempel dulu teks yang mau diringkas.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var maxChars = state.limits.max_chars || FALLBACK_LIMITS.max_chars;
    if (textVal.length > maxChars) {
      setStatus('Teks terlalu panjang. Batasnya ' + numberFmt.format(maxChars) + ' karakter.', 'error');
      return;
    }

    resetResults();

    var rasioVal = getRadioValue('ringkas-teks-rasio-opt', '30');
    var formatVal = getRadioValue('ringkas-teks-format-opt', 'paragraf');

    var form = new FormData();
    form.append('text', textVal);
    form.append('rasio', rasioVal);
    form.append('format', formatVal);

    state.busy = true;
    updateControls();
    setStatus('Meringkas...', 'busy');

    fetch(serverBase + '/api/text/summary', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        if (el.output) el.output.value = data.ringkasan || '';

        var kal = data.kalimat || {};
        var kar = data.karakter || {};
        var waktu = data.waktu_baca_detik || 1;

        if (el.statKalimat) {
          el.statKalimat.textContent = (kal.ringkasan || 0) + ' dari ' + (kal.masukan || 0);
        }
        if (el.statKarakter) {
          el.statKarakter.textContent = numberFmt.format(kar.ringkasan || 0) + ' / ' + numberFmt.format(kar.masukan || 0);
        }
        if (el.statHemat) {
          el.statHemat.textContent = (kar.hemat_persen || 0) + '%';
        }
        if (el.statWaktu) {
          el.statWaktu.textContent = '~' + waktu + ' dtk';
        }

        // Tampilkan kata kunci
        if (el.keywords && el.keywordsWrap) {
          el.keywords.innerHTML = '';
          if (Array.isArray(data.kata_kunci) && data.kata_kunci.length > 0) {
            for (var i = 0; i < data.kata_kunci.length; i++) {
              var chip = document.createElement('span');
              chip.className = 'rk__chip';
              chip.textContent = data.kata_kunci[i];
              el.keywords.appendChild(chip);
            }
            el.keywordsWrap.hidden = false;
          } else {
            el.keywordsWrap.hidden = true;
          }
        }

        if (el.outputWrap) el.outputWrap.hidden = false;

        var msgSukses = 'Selesai: ' + (kal.ringkasan || 0) + ' dari ' + (kal.masukan || 0) + ' kalimat dipakai (hemat ' + (kar.hemat_persen || 0) + '%)';
        setStatus(msgSukses, 'ok');
      })
      .catch(function (error) {
        var isNetwork = error && (error.name === 'TypeError' || /network|fetch|failed to fetch/i.test(error.message));
        var msg = isNetwork ? 'Tidak bisa menghubungi server. Coba lagi sebentar lagi.' : (error && error.message ? error.message : 'Gagal meringkas teks.');
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
          setStatus('Hasil ringkasan disalin ke papan klip.', 'ok');
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
          setStatus('Hasil ringkasan disalin ke papan klip.', 'ok');
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
    a.download = 'ringkasan.txt';
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
    setStatus('Masukkan teks minimal 3 kalimat, pilih rasio dan format, lalu tekan "Ringkas sekarang".', '');
    updateControls();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="ringkas-teks"]');
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
        setStatus('Masukkan teks minimal 3 kalimat, pilih rasio dan format, lalu tekan "Ringkas sekarang".', '');
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
        submitSummary();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('input', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitSummary);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  // Daftarkan panel supaya kartu "Ringkas teks" bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['ringkas-teks'] = toggle;

  updateControls();
})();
