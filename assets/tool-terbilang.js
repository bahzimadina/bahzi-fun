/* =========================================================================
   Panel alat: Angka jadi huruf (Terbilang)
   Ubah angka menjadi kata Bahasa Indonesia murni di memori server.
   Tidak ada data atau angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('terbilang-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('terbilang-close'),
    angka: document.getElementById('terbilang-angka'),
    mode: document.getElementById('terbilang-mode'),
    kapital: document.getElementById('terbilang-kapital'),
    submit: document.getElementById('terbilang-submit'),
    clear: document.getElementById('terbilang-clear'),
    status: document.getElementById('terbilang-status'),
    outputWrap: document.getElementById('terbilang-output-wrap'),
    output: document.getElementById('terbilang-output'),
    stats: document.getElementById('terbilang-stats'),
    resultHint: document.getElementById('terbilang-result-hint'),
    copy: document.getElementById('terbilang-copy'),
    download: document.getElementById('terbilang-download')
  };

  var state = {
    busy: false,
    lastFocus: null,
    lastResult: null,
    limits: null,
    limitsLoaded: false
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

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.output) el.output.textContent = '';
    if (el.stats) el.stats.textContent = '';
    state.lastResult = null;
  }

  function updateControls() {
    var val = el.angka ? el.angka.value.trim() : '';
    var hasText = val.length > 0;
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !hasText;
      el.submit.textContent = state.busy ? 'Mengubah...' : 'Ubah ke huruf';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasText && !hasOutput);
    }
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.output) {
      el.output.textContent = data.kata || '';
    }

    if (el.stats) {
      var kataCount = data.jumlah_kata || 0;
      var charCount = data.jumlah_karakter || 0;
      el.stats.textContent = kataCount + ' kata · ' + charCount + ' karakter';
    }
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) {
          message = parsed.error.message;
        }
      } catch (err) { /* bukan json */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan angka jadi huruf belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Nilai masukan atau ukuran permintaan melebihi batas yang didukung.';
        } else {
          message = 'Terjadi kendala saat mengubah angka. Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/terbilang/limits', {
      headers: { 'Accept': 'application/json' }
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limits = data;
        state.limitsLoaded = true;
      })
      .catch(function () {
        // Fallback anggap gagal diam-diam, validasi tetap berjalan di server
      });
  }

  function submitTerbilang() {
    if (state.busy) return;

    var rawAngka = el.angka ? el.angka.value.trim() : '';
    if (!rawAngka) {
      setStatus('Masukkan angka terlebih dahulu.', 'error');
      if (el.angka) el.angka.focus();
      return;
    }

    var modeVal = el.mode ? el.mode.value : 'biasa';
    var kapitalVal = el.kapital ? (el.kapital.checked ? 'true' : 'false') : 'false';

    var form = new FormData();
    form.append('angka', rawAngka);
    form.append('mode', modeVal);
    form.append('kapital', kapitalVal);

    state.busy = true;
    updateControls();
    setStatus('Sedang mengubah angka...', 'busy');

    fetch(serverBase + '/api/terbilang', {
      method: 'POST',
      body: form
    })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('Angka berhasil diubah ke huruf.', 'ok');
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
    if (!state.lastResult || !state.lastResult.kata) return;
    var textToCopy = state.lastResult.kata;

    function notify(ok) {
      if (ok) {
        setStatus('Hasil kata disalin ke papan klip.', 'ok');
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
      var ta = document.createElement('textarea');
      ta.value = textToCopy;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        var ok = document.execCommand('copy');
        notify(ok);
      } catch (err) {
        notify(false);
      }
      document.body.removeChild(ta);
    }
  }

  function downloadResult() {
    if (!state.lastResult || !state.lastResult.kata) return;
    var text = state.lastResult.kata;
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'terbilang.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
    setStatus('Berkas terbilang.txt berhasil diunduh.', 'ok');
  }

  function resetAll() {
    if (el.angka) {
      el.angka.value = '';
      el.angka.focus();
    }
    if (el.mode) el.mode.value = 'biasa';
    if (el.kapital) el.kapital.checked = false;
    resetResults();
    setStatus('Masukkan angka lalu tekan "Ubah ke huruf".', '');
    updateControls();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="terbilang"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'terbilang-panel');
    }
  }

  function open() {
    if (!panel.hidden) return;
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);

    var reduceMotion = false;
    try {
      reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { /* abaikan */ }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    loadLimits();
    updateControls();
    if (el.angka) {
      setTimeout(function () { el.angka.focus(); }, 50);
    }
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
    if (panel.hidden) {
      open();
    } else {
      close();
    }
  }

  // Event Listeners
  if (el.close) el.close.addEventListener('click', close);
  if (el.submit) el.submit.addEventListener('click', submitTerbilang);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  if (el.angka) {
    el.angka.addEventListener('input', updateControls);
    el.angka.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        var val = el.angka.value.trim();
        if (val.length > 0) {
          submitTerbilang();
        }
      }
    });
  }

  if (el.mode) el.mode.addEventListener('change', updateControls);
  if (el.kapital) el.kapital.addEventListener('change', updateControls);

  function onGlobalKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape' && panel.contains(document.activeElement)) {
      event.preventDefault();
      close();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      if (panel.contains(document.activeElement)) {
        event.preventDefault();
        submitTerbilang();
      }
    }
  }
  document.addEventListener('keydown', onGlobalKeydown);

  // Daftarkan panel ke sistem pembuka kartu OmniTools
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['terbilang'] = toggle;

  // Inisialisasi awal
  updateControls();
})();
