/* =========================================================================
   Panel alat: Simulasi cicilan (hitung perkiraan angsuran pinjaman)
   Nilai dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('cicilan-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('cicilan-close'),
    limits: document.getElementById('cicilan-limits'),
    pokok: document.getElementById('cicilan-pokok'),
    bunga: document.getElementById('cicilan-bunga'),
    tenor: document.getElementById('cicilan-tenor'),
    metodeGroup: document.getElementById('cicilan-metode-group'),
    submit: document.getElementById('cicilan-hitung'),
    clear: document.getElementById('cicilan-kosongkan'),
    status: document.getElementById('cicilan-status'),
    results: document.getElementById('cicilan-results'),
    resultHint: document.getElementById('cicilan-result-hint'),
    outputWrap: document.getElementById('cicilan-output-wrap'),
    heroValue: document.getElementById('cicilan-hero-value'),
    totalBunga: document.getElementById('cicilan-total-bunga'),
    totalBayar: document.getElementById('cicilan-total-bayar'),
    jadwalTbody: document.getElementById('cicilan-jadwal-tbody'),
    toggleJadwal: document.getElementById('cicilan-toggle-jadwal'),
    copy: document.getElementById('cicilan-copy')
  };

  var state = {
    metode: 'anuitas',
    busy: false,
    lastFocus: null,
    lastResult: null,
    expandedJadwal: false,
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

  function formatRupiah(str) {
    if (!str && str !== 0) return 'Rp 0,00';
    var parts = String(str).split('.');
    var intPart = parts[0];
    var decPart = parts.length > 1 ? parts[1] : '00';
    if (decPart.length === 1) decPart += '0';
    if (decPart.length > 2) decPart = decPart.slice(0, 2);

    var sign = '';
    if (intPart.charAt(0) === '-') {
      sign = '-';
      intPart = intPart.slice(1);
    }
    var formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return 'Rp ' + sign + formattedInt + ',' + decPart;
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.totalBunga) el.totalBunga.textContent = '';
    if (el.totalBayar) el.totalBayar.textContent = '';
    if (el.jadwalTbody) el.jadwalTbody.innerHTML = '';
    if (el.toggleJadwal) el.toggleJadwal.hidden = true;
    state.lastResult = null;
    state.expandedJadwal = false;
  }

  function updateControls() {
    var valPokok = el.pokok ? el.pokok.value.trim() : '';
    var valBunga = el.bunga ? el.bunga.value.trim() : '';
    var valTenor = el.tenor ? el.tenor.value.trim() : '';

    var hasAll = valPokok.length > 0 && valBunga.length > 0 && valTenor.length > 0;
    var hasAny = valPokok.length > 0 || valBunga.length > 0 || valTenor.length > 0;
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !hasAll;
      el.submit.textContent = state.busy ? 'Menghitung...' : 'Hitung';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAny && !hasOutput);
    }
  }

  function renderJadwalRows() {
    if (!el.jadwalTbody || !state.lastResult || !Array.isArray(state.lastResult.jadwal)) return;
    var jadwal = state.lastResult.jadwal;
    var limit = state.expandedJadwal ? jadwal.length : Math.min(12, jadwal.length);

    el.jadwalTbody.innerHTML = '';
    var fragment = document.createDocumentFragment();

    for (var i = 0; i < limit; i++) {
      var item = jadwal[i];
      var tr = document.createElement('tr');

      var tdMonth = document.createElement('td');
      tdMonth.textContent = 'Bulan ' + item.bulan;
      tr.appendChild(tdMonth);

      var tdAngsuran = document.createElement('td');
      tdAngsuran.textContent = formatRupiah(item.angsuran);
      tr.appendChild(tdAngsuran);

      var tdBunga = document.createElement('td');
      tdBunga.textContent = formatRupiah(item.bunga);
      tr.appendChild(tdBunga);

      var tdPokok = document.createElement('td');
      tdPokok.textContent = formatRupiah(item.pokok);
      tr.appendChild(tdPokok);

      var tdSisa = document.createElement('td');
      tdSisa.textContent = formatRupiah(item.sisa);
      tr.appendChild(tdSisa);

      fragment.appendChild(tr);
    }
    el.jadwalTbody.appendChild(fragment);

    if (el.toggleJadwal) {
      if (jadwal.length > 12) {
        el.toggleJadwal.hidden = false;
        el.toggleJadwal.textContent = state.expandedJadwal
          ? 'Ringkas lagi'
          : 'Tampilkan semua ' + jadwal.length + ' bulan';
      } else {
        el.toggleJadwal.hidden = true;
      }
    }
  }

  function renderResults(data) {
    state.lastResult = data;
    state.expandedJadwal = false;

    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.heroValue) {
      el.heroValue.textContent = formatRupiah(data.angsuran_per_bulan);
    }
    if (el.totalBunga) {
      el.totalBunga.textContent = formatRupiah(data.total_bunga);
    }
    if (el.totalBayar) {
      el.totalBayar.textContent = formatRupiah(data.total_bayar);
    }

    renderJadwalRows();
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) {
          message = parsed.error.message;
        }
      } catch (err) { /* abaikan parsing */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan simulasi cicilan belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Ukuran permintaan melebihi batas yang didukung.';
        } else {
          message = 'Terjadi kendala saat memproses simulasi cicilan (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitCalc() {
    if (state.busy) return;

    var valPokok = el.pokok ? el.pokok.value.replace(/\D/g, '') : '';
    var valBunga = el.bunga ? el.bunga.value.trim() : '';
    var valTenor = el.tenor ? el.tenor.value.trim() : '';

    if (!valPokok || !valBunga || !valTenor) {
      setStatus('Lengkapi pokok pinjaman, bunga, dan tenor.', 'error');
      if (!valPokok && el.pokok) {
        el.pokok.focus();
      } else if (!valBunga && el.bunga) {
        el.bunga.focus();
      } else if (!valTenor && el.tenor) {
        el.tenor.focus();
      }
      return;
    }

    var form = new FormData();
    form.append('pokok', valPokok);
    form.append('bunga', valBunga);
    form.append('tenor', valTenor);
    form.append('metode', state.metode);

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung simulasi...', 'busy');

    fetch(serverBase + '/api/cicilan', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('Simulasi cicilan selesai dihitung.', 'ok');
      })
      .catch(function (err) {
        resetResults();
        var msg = (err && err.pesanLayanan === true && err.message)
          ? err.message
          : 'Koneksi ke layanan gagal. Periksa sambungan internetmu dan coba lagi.';
        setStatus(msg, 'error');
      })
      .finally(function () {
        state.busy = false;
        updateControls();
      });
  }

  function copyResult() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var metodeLabel = d.metode === 'anuitas' ? 'Anuitas' : 'Bunga tetap';
    var textToCopy = [
      'Simulasi Cicilan Pinjaman (' + metodeLabel + ')',
      'Pokok pinjaman: ' + formatRupiah(d.pokok),
      'Bunga tahunan: ' + d.bunga_tahunan + '% per tahun',
      'Tenor: ' + d.tenor_bulan + ' bulan',
      'Perkiraan angsuran: ' + formatRupiah(d.angsuran_per_bulan) + ' / bulan',
      'Total bunga: ' + formatRupiah(d.total_bunga),
      'Total bayar: ' + formatRupiah(d.total_bayar),
      '',
      'Perkiraan saja. Belum termasuk biaya admin, provisi, asuransi, dan denda.'
    ].join('\n');

    function notify(ok) {
      if (ok) {
        setStatus('Ringkasan disalin ke papan klip.', 'ok');
      } else {
        setStatus('Gagal menyalin ringkasan.', 'error');
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

  function resetAll() {
    if (el.pokok) el.pokok.value = '';
    if (el.bunga) el.bunga.value = '';
    if (el.tenor) el.tenor.value = '';
    setMetode('anuitas');
    resetResults();
    setStatus('Masukkan pokok pinjaman, bunga, dan tenor, lalu tekan "Hitung".', '');
    updateControls();
    if (el.pokok) el.pokok.focus();
  }

  function setMetode(metodeVal) {
    state.metode = metodeVal === 'flat' ? 'flat' : 'anuitas';
    if (el.metodeGroup) {
      var buttons = el.metodeGroup.querySelectorAll('[data-metode]');
      for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        var isTarget = btn.getAttribute('data-metode') === state.metode;
        if (isTarget) {
          btn.classList.add('chip--active');
          btn.setAttribute('aria-checked', 'true');
        } else {
          btn.classList.remove('chip--active');
          btn.setAttribute('aria-checked', 'false');
        }
      }
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/cicilan/limits', { headers: { credentials: 'same-origin', Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data && el.limits) {
          el.limits.textContent = 'Pokok Rp 100 rb sampai Rp 100 miliar, tenor 1 sampai 360 bulan';
        }
        state.limitsLoaded = true;
      })
      .catch(function () {
        /* Tetap pakai teks bawaan bila gagal memuat info limits */
      });
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="cicilan"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'cicilan-panel');
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
    } catch (e) { /* abaikan */ }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    if (el.pokok) {
      setTimeout(function () { el.pokok.focus(); }, 100);
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

  if (el.metodeGroup) {
    el.metodeGroup.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-metode]');
      if (!btn) return;
      var targetMetode = btn.getAttribute('data-metode');
      if (targetMetode && targetMetode !== state.metode) {
        setMetode(targetMetode);
        if (state.lastResult) {
          submitCalc();
        }
      }
    });
  }

  function formatPokokInput() {
    if (!el.pokok) return;
    var rawDigits = el.pokok.value.replace(/\D/g, '');
    if (!rawDigits) {
      el.pokok.value = '';
    } else {
      el.pokok.value = rawDigits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }
    updateControls();
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var valP = el.pokok ? el.pokok.value.trim() : '';
      var valB = el.bunga ? el.bunga.value.trim() : '';
      var valT = el.tenor ? el.tenor.value.trim() : '';
      if (valP && valB && valT) {
        submitCalc();
      } else if (!valP && el.pokok) {
        el.pokok.focus();
      } else if (!valB && el.bunga) {
        el.bunga.focus();
      } else if (!valT && el.tenor) {
        el.tenor.focus();
      }
    }
  }

  if (el.pokok) {
    el.pokok.addEventListener('input', formatPokokInput);
    el.pokok.addEventListener('keydown', onInputKeydown);
  }

  if (el.bunga) {
    el.bunga.addEventListener('input', updateControls);
    el.bunga.addEventListener('keydown', onInputKeydown);
  }

  if (el.tenor) {
    el.tenor.addEventListener('input', updateControls);
    el.tenor.addEventListener('keydown', onInputKeydown);
  }

  if (el.submit) el.submit.addEventListener('click', submitCalc);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);

  if (el.toggleJadwal) {
    el.toggleJadwal.addEventListener('click', function () {
      state.expandedJadwal = !state.expandedJadwal;
      renderJadwalRows();
    });
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
        submitCalc();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);

  // Daftarkan panel supaya kartu Simulasi cicilan bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['cicilan'] = toggle;

  // Inisialisasi bawaan
  setMetode('anuitas');
  updateControls();
})();
