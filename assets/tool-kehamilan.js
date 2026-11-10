/* =========================================================================
   Panel alat: Kalkulator kehamilan (kehamilan)
   Perkiraan hari lahir (HPL) dan usia kehamilan dari HPHT.
   Semua data diproses di memori server dan tidak disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('kehamilan-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('kehamilan-close'),
    note: document.getElementById('kehamilan-note'),
    hpht: document.getElementById('kehamilan-hpht'),
    siklus: document.getElementById('kehamilan-siklus'),
    tanggal: document.getElementById('kehamilan-tanggal'),
    status: document.getElementById('kehamilan-status'),
    clear: document.getElementById('kehamilan-clear'),
    submit: document.getElementById('kehamilan-submit'),
    result: document.getElementById('kehamilan-result'),
    statUsia: document.getElementById('kehamilan-stat-usia'),
    statHpl: document.getElementById('kehamilan-stat-hpl'),
    statTrimester: document.getElementById('kehamilan-stat-trimester'),
    bar: document.getElementById('kehamilan-bar'),
    barFill: null,
    barPersen: document.getElementById('kehamilan-bar-persen'),
    rentang: document.getElementById('kehamilan-rentang'),
    sisa: document.getElementById('kehamilan-sisa'),
    catatan: document.getElementById('kehamilan-catatan'),
    copy: document.getElementById('kehamilan-copy'),
    download: document.getElementById('kehamilan-download')
  };

  if (el.bar) {
    el.barFill = el.bar.querySelector('.kehamilan__bar-fill');
  }

  var FALLBACK_LIMITS = {
    min_siklus: 21,
    max_siklus: 40,
    default_siklus: 28,
    max_usia_minggu: 45,
    zona_waktu: 'Asia/Jakarta'
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
    lastResult: null,
    abortController: null
  };

  function setStatus(message, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status' + (kind ? ' status--' + kind : '');
    if (kind === 'error' || kind === 'warn' || kind === 'warning') {
      el.status.setAttribute('role', 'alert');
    } else {
      el.status.setAttribute('role', 'status');
    }
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(message));
  }

  function updateControls() {
    var hasHpht = el.hpht && el.hpht.value.trim().length > 0;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasHpht;
    }
    if (el.clear) {
      el.clear.disabled = state.busy && !state.abortController;
    }
  }

  function applyLimits(data) {
    state.limits = {
      min_siklus: data.min_siklus || FALLBACK_LIMITS.min_siklus,
      max_siklus: data.max_siklus || FALLBACK_LIMITS.max_siklus,
      default_siklus: data.default_siklus || FALLBACK_LIMITS.default_siklus,
      max_usia_minggu: data.max_usia_minggu || FALLBACK_LIMITS.max_usia_minggu,
      zona_waktu: data.zona_waktu || FALLBACK_LIMITS.zona_waktu
    };

    if (el.siklus && !el.siklus.value) {
      el.siklus.value = String(state.limits.default_siklus);
    }
    if (el.note && data.catatan) {
      el.note.textContent = data.catatan;
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/kehamilan/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsLoaded = true;
        applyLimits(data);
      })
      .catch(function () {
        applyLimits(FALLBACK_LIMITS);
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
      } catch (err) {
        // Abaikan galat parse JSON
      }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan kalkulator kehamilan belum tersambung ke server. Coba lagi nanti.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }

      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function buildPlainText(data) {
    var lines = [];
    lines.push('PERKIRAAN KEHAMILAN & HARI LAHIR (HPL)');
    lines.push('HPHT: ' + data.hpht + ' | Siklus: ' + data.siklus + ' hari | Dihitung per: ' + data.tanggal_acuan);
    lines.push('');
    lines.push('Usia kehamilan: ' + data.usia_teks + ' (' + data.trimester_label + ')');
    lines.push('Perkiraan lahir (HPL): ' + data.hpl_teks);
    lines.push('Sisa waktu: ' + data.sisa_teks);
    lines.push('Rentang persalinan cukup bulan: ' + data.cukup_bulan_mulai + ' sampai ' + data.cukup_bulan_selesai);
    lines.push('Perjalanan kehamilan: ' + data.persen + '%');
    lines.push('');
    lines.push('Catatan: ' + data.catatan);
    return lines.join('\n');
  }

  function renderResult(data) {
    state.lastResult = data;

    if (el.statUsia) {
      el.statUsia.textContent = data.usia_teks;
    }
    if (el.statHpl) {
      el.statHpl.textContent = data.hpl_teks;
    }
    if (el.statTrimester) {
      el.statTrimester.textContent = data.trimester_label;
    }

    if (el.bar) {
      el.bar.setAttribute('aria-valuenow', String(data.persen));
    }
    var fill = el.barFill || (el.bar ? el.bar.querySelector('.kehamilan__bar-fill') : null);
    if (fill) {
      fill.style.width = Math.min(100, Math.max(0, data.persen)) + '%';
    }
    if (el.barPersen) {
      el.barPersen.textContent = data.persen + '%';
    }

    if (el.sisa) {
      el.sisa.textContent = data.sisa_teks;
    }

    if (el.rentang) {
      el.rentang.textContent = 'Rentang persalinan cukup bulan (37–42 minggu): ' + data.cukup_bulan_mulai + ' sampai ' + data.cukup_bulan_selesai;
    }

    if (el.catatan) {
      el.catatan.textContent = data.catatan;
    }

    if (el.result) {
      el.result.hidden = false;
    }
  }

  function submitKehamilan() {
    if (state.busy) return;

    var hphtVal = el.hpht ? el.hpht.value.trim() : '';
    if (!hphtVal) {
      setStatus('Pilih tanggal hari pertama haid terakhir (HPHT) terlebih dahulu.', 'error');
      if (el.hpht) el.hpht.focus();
      return;
    }

    var form = new FormData();
    form.append('hpht', hphtVal);
    form.append('siklus', el.siklus ? el.siklus.value : '28');
    if (el.tanggal && el.tanggal.value.trim() !== '') {
      form.append('tanggal', el.tanggal.value.trim());
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung perkiraan...', 'busy');

    if (window.AbortController) {
      state.abortController = new AbortController();
    }

    fetch(serverBase + '/api/kehamilan', {
      method: 'POST',
      body: form,
      signal: state.abortController ? state.abortController.signal : undefined
    })
      .then(function (res) {
        if (!res.ok) return readServerError(res);
        return res.json();
      })
      .then(function (data) {
        renderResult(data);
        setStatus('Perkiraan kehamilan berhasil dihitung.', 'ok');
      })
      .catch(function (error) {
        if (error && error.name === 'AbortError') {
          setStatus('Perhitungan dibatalkan.', '');
          return;
        }
        var msg = (error && error.pesanLayanan === true && error.message)
          ? error.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
      })
      .then(function () {
        state.busy = false;
        state.abortController = null;
        updateControls();
      });
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    ta.style.top = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    var ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (err) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  function copyResult() {
    if (!state.lastResult) return;
    var text = buildPlainText(state.lastResult);

    function onCopied() {
      if (el.copy) {
        var old = el.copy.textContent;
        el.copy.textContent = 'Tersalin';
        setTimeout(function () {
          el.copy.textContent = old;
        }, 2000);
      }
      setStatus('Hasil perkiraan berhasil disalin ke papan klip.', 'ok');
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text)
        .then(onCopied)
        .catch(function () {
          if (fallbackCopy(text)) {
            onCopied();
          } else {
            setStatus('Tidak bisa menyalin secara otomatis. Silakan salin manual.', 'error');
          }
        });
    } else if (fallbackCopy(text)) {
      onCopied();
    } else {
      setStatus('Tidak bisa menyalin secara otomatis. Silakan salin manual.', 'error');
    }
  }

  function downloadResult() {
    if (!state.lastResult) return;
    var text = buildPlainText(state.lastResult);
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'perkiraan-kehamilan.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  function resetAll() {
    if (state.abortController) {
      state.abortController.abort();
      state.abortController = null;
    }
    if (el.hpht) el.hpht.value = '';
    if (el.siklus) el.siklus.value = String(state.limits.default_siklus || 28);
    if (el.tanggal) el.tanggal.value = '';
    if (el.result) el.result.hidden = true;
    state.lastResult = null;
    state.busy = false;
    setStatus('Pilih tanggal HPHT, lalu tekan "Hitung perkiraan".', '');
    updateControls();
    if (el.hpht) el.hpht.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="kehamilan"]');
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
      syncTriggers(true);
      panel.focus({ preventScroll: true });
      if (el.hpht) el.hpht.focus();
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
        submitKehamilan();
      }
    }
  }

  // Pemasangan pendengar acara
  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.hpht) {
    el.hpht.addEventListener('input', updateControls);
    el.hpht.addEventListener('change', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitKehamilan);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['kehamilan'] = toggle;

  updateControls();
})();
