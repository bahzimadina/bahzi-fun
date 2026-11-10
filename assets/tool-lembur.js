/* =========================================================================
   Panel alat: Hitung upah lembur (lembur)
   Perkiraan upah lembur dari gaji sebulan berdasarkan PP 35/2021.
   Semua data diproses di memori server dan tidak disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('lembur-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('lembur-close'),
    note: document.getElementById('lembur-note'),
    upah: document.getElementById('lembur-upah'),
    jenis: document.getElementById('lembur-jenis'),
    mingguWrap: document.getElementById('lembur-minggu-wrapper'),
    minggu: document.getElementById('lembur-minggu'),
    jam: document.getElementById('lembur-jam'),
    jamHint: document.getElementById('lembur-jam-hint'),
    status: document.getElementById('lembur-status'),
    clear: document.getElementById('lembur-clear'),
    submit: document.getElementById('lembur-submit'),
    result: document.getElementById('lembur-result'),
    statTotal: document.getElementById('lembur-stat-total'),
    statSejam: document.getElementById('lembur-stat-sejam'),
    statDiterima: document.getElementById('lembur-stat-diterima'),
    statPersen: document.getElementById('lembur-stat-persen'),
    ringkasan: document.getElementById('lembur-ringkasan'),
    rincian: document.getElementById('lembur-rincian'),
    catatan: document.getElementById('lembur-catatan'),
    copy: document.getElementById('lembur-copy'),
    download: document.getElementById('lembur-download')
  };

  var FALLBACK_LIMITS = {
    upah_min: 100000,
    upah_max: 1000000000,
    jam_kerja_max: 4,
    jam_libur_max: 12,
    langkah_jam: 0.5,
    hari_kerja_mingguan: [5, 6],
    jenis_hari: ['kerja', 'libur'],
    pembagi_upah_sejam: 173
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

  function formatRupiah(num, decimals) {
    var n = Number(num) || 0;
    if (decimals) {
      var parts = n.toFixed(decimals).split('.');
      var ribuan = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
      return 'Rp' + ribuan + ',' + parts[1];
    }
    var val = Math.round(n);
    return 'Rp' + val.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function formatPersen(num) {
    var n = Number(num) || 0;
    return n.toFixed(2).replace('.', ',') + '%';
  }

  function formatJam(num) {
    var n = Number(num) || 0;
    return String(n).replace('.', ',');
  }

  function formatPengali(p) {
    var n = Number(p) || 0;
    return (n % 1 === 0 ? String(n) : n.toFixed(1)).replace('.', ',') + 'x';
  }

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

  function updateDayView() {
    var isLibur = el.jenis && el.jenis.value === 'libur';
    if (el.mingguWrap) {
      el.mingguWrap.hidden = !isLibur;
    }
    var maxJam = isLibur ? (state.limits.jam_libur_max || 12) : (state.limits.jam_kerja_max || 4);
    if (el.jam) {
      el.jam.max = String(maxJam);
    }
    if (el.jamHint) {
      el.jamHint.textContent = isLibur
        ? 'Maksimal ' + maxJam + ' jam untuk hari istirahat/libur resmi (kelipatan 0,5).'
        : 'Maksimal ' + maxJam + ' jam untuk hari kerja (kelipatan 0,5).';
    }
  }

  function updateControls() {
    var upahVal = el.upah ? el.upah.value.trim() : '';
    var jamVal = el.jam ? el.jam.value.trim() : '';
    var canSubmit = upahVal.length > 0 && jamVal.length > 0 && !state.busy;
    if (el.submit) {
      el.submit.disabled = !canSubmit;
    }
    if (el.clear) {
      el.clear.disabled = state.busy && !state.abortController;
    }
  }

  function applyLimits(data) {
    state.limits = {
      upah_min: data.upah_min || FALLBACK_LIMITS.upah_min,
      upah_max: data.upah_max || FALLBACK_LIMITS.upah_max,
      jam_kerja_max: data.jam_kerja_max || FALLBACK_LIMITS.jam_kerja_max,
      jam_libur_max: data.jam_libur_max || FALLBACK_LIMITS.jam_libur_max,
      langkah_jam: data.langkah_jam || FALLBACK_LIMITS.langkah_jam,
      hari_kerja_mingguan: data.hari_kerja_mingguan || FALLBACK_LIMITS.hari_kerja_mingguan,
      jenis_hari: data.jenis_hari || FALLBACK_LIMITS.jenis_hari,
      pembagi_upah_sejam: data.pembagi_upah_sejam || FALLBACK_LIMITS.pembagi_upah_sejam
    };

    if (el.upah) {
      el.upah.min = String(state.limits.upah_min);
      el.upah.max = String(state.limits.upah_max);
    }
    if (el.jam) {
      el.jam.step = String(state.limits.langkah_jam);
      el.jam.min = String(state.limits.langkah_jam);
    }
    updateDayView();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/lembur/limits')
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
        if (parsed) {
          if (parsed.pesan) {
            message = parsed.pesan;
          } else if (parsed.error && parsed.error.message) {
            message = parsed.error.message;
          } else if (parsed.detail && parsed.detail.message) {
            message = parsed.detail.message;
          }
        }
      } catch (err) {
        // Abaikan galat parse JSON
      }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan hitung upah lembur belum tersambung ke server. Coba lagi nanti.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }

      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function buildSummarySentence(data) {
    var hariLabel = data.jenis_hari === 'kerja' ? 'hari kerja' : 'hari libur';
    return 'Lembur ' + formatJam(data.jam_lembur) + ' jam di ' + hariLabel +
      ', upah ' + formatRupiah(data.upah_bulanan) + '/bulan: upah lembur ' +
      formatRupiah(data.total_upah_lembur) + ', total diterima ' +
      formatRupiah(data.total_diterima) + '.';
  }

  function buildPlainText(data) {
    var lines = [];
    lines.push('HITUNG UPAH LEMBUR');
    lines.push('Upah bulanan: ' + formatRupiah(data.upah_bulanan));
    lines.push('Upah sejam: ' + formatRupiah(data.upah_sejam, 2) + ' (dasar upah sebulan / 173)');
    var jenisLabel = data.jenis_hari === 'kerja'
      ? 'Hari kerja (Senin-Jumat/Sabtu)'
      : 'Hari istirahat atau libur resmi (' + data.hari_kerja_mingguan + ' hari kerja seminggu)';
    lines.push('Jenis hari: ' + jenisLabel);
    lines.push('Jam lembur: ' + formatJam(data.jam_lembur) + ' jam');
    lines.push('');
    lines.push('Rincian per jam:');
    if (Array.isArray(data.rincian)) {
      data.rincian.forEach(function (item) {
        lines.push('- Jam ke-' + item.jam_ke + ' · ' + formatPengali(item.pengali) + ' · ' + formatRupiah(item.upah));
      });
    }
    lines.push('');
    lines.push('Total upah lembur: ' + formatRupiah(data.total_upah_lembur));
    lines.push('Total diterima bulan ini: ' + formatRupiah(data.total_diterima));
    lines.push('Tambahan: ' + formatPersen(data.persen_tambahan));
    lines.push('');
    lines.push('Ringkasan:');
    lines.push(buildSummarySentence(data));
    lines.push('');
    lines.push('Catatan:');
    lines.push(data.catatan || 'Hitungan memakai upah sejam = upah sebulan / 173. Uang makan lembur, potongan, dan pajak tidak dihitung di sini.');
    return lines.join('\n');
  }

  function renderResult(data) {
    state.lastResult = data;

    if (el.statTotal) {
      el.statTotal.textContent = formatRupiah(data.total_upah_lembur);
    }
    if (el.statSejam) {
      el.statSejam.textContent = formatRupiah(data.upah_sejam, 2);
    }
    if (el.statDiterima) {
      el.statDiterima.textContent = formatRupiah(data.total_diterima);
    }
    if (el.statPersen) {
      el.statPersen.textContent = formatPersen(data.persen_tambahan);
    }

    if (el.ringkasan) {
      el.ringkasan.textContent = buildSummarySentence(data);
    }

    if (el.rincian) {
      el.rincian.innerHTML = '';
      if (Array.isArray(data.rincian)) {
        data.rincian.forEach(function (item) {
          var li = document.createElement('li');
          li.className = 'lembur__rincian-item';

          var left = document.createElement('span');
          left.className = 'lembur__rincian-item-left';

          var label = document.createElement('span');
          label.textContent = 'Jam ke-' + item.jam_ke;

          var tag = document.createElement('span');
          tag.className = 'lembur__rincian-item-tag';
          tag.textContent = formatPengali(item.pengali);

          left.appendChild(label);
          left.appendChild(tag);

          var right = document.createElement('strong');
          right.textContent = formatRupiah(item.upah);

          li.appendChild(left);
          li.appendChild(right);
          el.rincian.appendChild(li);
        });
      }
    }

    if (el.catatan && data.catatan) {
      el.catatan.textContent = data.catatan;
    }

    if (el.result) {
      el.result.hidden = false;
    }
  }

  function submitLembur() {
    if (state.busy) return;

    var upahVal = el.upah ? el.upah.value.trim() : '';
    if (!upahVal) {
      setStatus('Isi upah bulanan terlebih dahulu.', 'error');
      if (el.upah) el.upah.focus();
      return;
    }

    var jamVal = el.jam ? el.jam.value.trim() : '';
    if (!jamVal) {
      setStatus('Isi jumlah jam lembur terlebih dahulu.', 'error');
      if (el.jam) el.jam.focus();
      return;
    }

    var form = new FormData();
    form.append('upah_bulanan', upahVal);
    form.append('jenis_hari', el.jenis ? el.jenis.value : 'kerja');
    form.append('jam_lembur', jamVal);
    if (el.jenis && el.jenis.value === 'libur' && el.minggu) {
      form.append('hari_kerja_mingguan', el.minggu.value);
    } else {
      form.append('hari_kerja_mingguan', '5');
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung upah lembur...', 'busy');

    if (window.AbortController) {
      state.abortController = new AbortController();
    }

    fetch(serverBase + '/api/lembur', {
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
        setStatus('Upah lembur berhasil dihitung.', 'ok');
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
    var text = buildSummarySentence(state.lastResult);

    function onCopied() {
      if (el.copy) {
        var old = el.copy.textContent;
        el.copy.textContent = 'Tersalin';
        setTimeout(function () {
          el.copy.textContent = old;
        }, 2000);
      }
      setStatus('Ringkasan upah lembur berhasil disalin ke papan klip.', 'ok');
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
    a.download = 'upah-lembur.txt';
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
    if (el.upah) el.upah.value = '';
    if (el.jenis) el.jenis.value = 'kerja';
    if (el.minggu) el.minggu.value = '5';
    if (el.jam) el.jam.value = '';
    if (el.result) el.result.hidden = true;
    state.lastResult = null;
    state.busy = false;
    updateDayView();
    setStatus('Masukkan upah bulanan dan jam lembur, lalu tekan "Hitung upah lembur".', '');
    updateControls();
    if (el.upah) el.upah.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="lembur"]');
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
      if (el.upah) el.upah.focus();
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
        submitLembur();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.upah) {
    el.upah.addEventListener('input', updateControls);
    el.upah.addEventListener('change', updateControls);
  }
  if (el.jenis) {
    el.jenis.addEventListener('change', function () {
      updateDayView();
      updateControls();
    });
  }
  if (el.jam) {
    el.jam.addEventListener('input', updateControls);
    el.jam.addEventListener('change', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitLembur);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['lembur'] = toggle;

  updateDayView();
  updateControls();
})();
