/* =========================================================================
   Panel alat: Kalender Hijriah (konversi tanggal Hijriah <-> Masehi)
   Nilai dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada tanggal yang dicatat ke log.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('hijriah-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('hijriah-close'),
    limits: document.getElementById('hijriah-limits'),
    note: document.getElementById('hijriah-note'),
    modeGroup: document.getElementById('hijriah-mode-group'),
    wrapKeMasehi: document.getElementById('hijriah-wrap-ke-masehi'),
    wrapKeHijriah: document.getElementById('hijriah-wrap-ke-hijriah'),
    hari: document.getElementById('hijriah-hari'),
    bulan: document.getElementById('hijriah-bulan'),
    tahun: document.getElementById('hijriah-tahun'),
    masehi: document.getElementById('hijriah-masehi'),
    submit: document.getElementById('hijriah-ubah'),
    clear: document.getElementById('hijriah-kosongkan'),
    status: document.getElementById('hijriah-status'),
    results: document.getElementById('hijriah-results'),
    resultHint: document.getElementById('hijriah-result-hint'),
    outputWrap: document.getElementById('hijriah-output-wrap'),
    hijriahTeks: document.getElementById('hijriah-hasil-hijriah-teks'),
    hijriahSub: document.getElementById('hijriah-hasil-hijriah-sub'),
    masehiTeks: document.getElementById('hijriah-hasil-masehi-teks'),
    masehiSub: document.getElementById('hijriah-hasil-masehi-sub'),
    pentingSection: document.getElementById('hijriah-penting-section'),
    pentingTitle: document.getElementById('hijriah-penting-title'),
    pentingList: document.getElementById('hijriah-penting-list'),
    copy: document.getElementById('hijriah-copy')
  };

  var DEFAULT_BULAN = [
    { nomor: 1, nama: 'Muharram' },
    { nomor: 2, nama: 'Safar' },
    { nomor: 3, nama: 'Rabiul Awal' },
    { nomor: 4, nama: 'Rabiul Akhir' },
    { nomor: 5, nama: 'Jumadil Awal' },
    { nomor: 6, nama: 'Jumadil Akhir' },
    { nomor: 7, nama: 'Rajab' },
    { nomor: 8, nama: 'Syaban' },
    { nomor: 9, nama: 'Ramadhan' },
    { nomor: 10, nama: 'Syawal' },
    { nomor: 11, nama: 'Dzulkaidah' },
    { nomor: 12, nama: 'Dzulhijjah' }
  ];

  var state = {
    mode: 'ke_masehi',
    busy: false,
    lastFocus: null,
    lastResult: null,
    limitsLoaded: false,
    minTahun: 1300,
    maxTahun: 1600
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
    if (el.hijriahTeks) el.hijriahTeks.textContent = '';
    if (el.hijriahSub) el.hijriahSub.textContent = '';
    if (el.masehiTeks) el.masehiTeks.textContent = '';
    if (el.masehiSub) el.masehiSub.textContent = '';
    if (el.pentingList) el.pentingList.innerHTML = '';
    state.lastResult = null;
  }

  function updateControls() {
    var hasValidInput = false;
    var hasAnyInput = false;

    if (state.mode === 'ke_masehi') {
      var valH = el.hari ? el.hari.value.trim() : '';
      var valB = el.bulan ? el.bulan.value.trim() : '';
      var valT = el.tahun ? el.tahun.value.trim() : '';

      hasValidInput = (valH.length > 0 && valB.length > 0 && valT.length > 0);
      hasAnyInput = (valH.length > 0 || valT.length > 0);
    } else {
      var valM = el.masehi ? el.masehi.value.trim() : '';
      hasValidInput = (valM.length > 0);
      hasAnyInput = (valM.length > 0);
    }

    if (el.submit) {
      el.submit.disabled = state.busy || !hasValidInput;
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAnyInput && !state.lastResult);
    }
  }

  function setMode(newMode) {
    state.mode = (newMode === 'ke_hijriah') ? 'ke_hijriah' : 'ke_masehi';

    if (el.modeGroup) {
      var buttons = el.modeGroup.querySelectorAll('[data-mode]');
      for (var i = 0; i < buttons.length; i++) {
        var btn = buttons[i];
        var isTarget = btn.getAttribute('data-mode') === state.mode;
        if (isTarget) {
          btn.classList.add('chip--active');
          btn.setAttribute('aria-checked', 'true');
        } else {
          btn.classList.remove('chip--active');
          btn.setAttribute('aria-checked', 'false');
        }
      }
    }

    if (state.mode === 'ke_masehi') {
      if (el.wrapKeMasehi) el.wrapKeMasehi.hidden = false;
      if (el.wrapKeHijriah) el.wrapKeHijriah.hidden = true;
    } else {
      if (el.wrapKeMasehi) el.wrapKeMasehi.hidden = true;
      if (el.wrapKeHijriah) el.wrapKeHijriah.hidden = false;
    }

    resetResults();
    setStatus(
      state.mode === 'ke_masehi'
        ? 'Masukkan tanggal Hijriah lalu tekan "Ubah tanggal".'
        : 'Pilih tanggal Masehi lalu tekan "Ubah tanggal".',
      ''
    );
    updateControls();

    // Fokus ke input yang aktif
    if (state.mode === 'ke_masehi' && el.hari) {
      el.hari.focus();
    } else if (state.mode === 'ke_hijriah' && el.masehi) {
      el.masehi.focus();
    }
  }

  function populateBulanSelect(daftarBulan) {
    if (!el.bulan) return;
    var currentVal = el.bulan.value || '1';
    el.bulan.innerHTML = '';
    var list = (daftarBulan && daftarBulan.length) ? daftarBulan : DEFAULT_BULAN;
    for (var i = 0; i < list.length; i++) {
      var opt = document.createElement('option');
      opt.value = String(list[i].nomor);
      opt.textContent = list[i].nomor + ' - ' + list[i].nama;
      if (opt.value === currentVal) opt.selected = true;
      el.bulan.appendChild(opt);
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    populateBulanSelect(DEFAULT_BULAN);

    fetch(serverBase + '/api/hijriah/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data) {
          if (data.ringkasan_batas && el.limits) {
            el.limits.textContent = data.ringkasan_batas;
          }
          if (data.catatan && el.note) {
            el.note.textContent = data.catatan;
          }
          if (data.daftar_bulan && Array.isArray(data.daftar_bulan)) {
            populateBulanSelect(data.daftar_bulan);
          }
          if (data.min_tahun_hijriah) state.minTahun = data.min_tahun_hijriah;
          if (data.max_tahun_hijriah) state.maxTahun = data.max_tahun_hijriah;
        }
        state.limitsLoaded = true;
      })
      .catch(function () {
        // Fallback aman di skrip
        populateBulanSelect(DEFAULT_BULAN);
        state.limitsLoaded = true;
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
      } catch (err) { /* abaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan kalender Hijriah belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Ukuran permintaan melebihi batas yang didukung.';
        } else {
          message = 'Terjadi kendala saat mengubah tanggal (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    // Kartu Hijriah
    if (el.hijriahTeks) {
      el.hijriahTeks.textContent = data.hijriah ? data.hijriah.teks : '';
    }
    if (el.hijriahSub) {
      var hariTeks = (data.masehi && data.masehi.hari) ? data.masehi.hari : '';
      var hariKe = (data.hijriah && data.hijriah.hari_dalam_tahun) ? 'Hari ke-' + data.hijriah.hari_dalam_tahun + ' dalam setahun' : '';
      el.hijriahSub.textContent = (hariTeks && hariKe) ? (hariTeks + ' • ' + hariKe) : (hariTeks || hariKe);
    }

    // Kartu Masehi
    if (el.masehiTeks) {
      el.masehiTeks.textContent = data.masehi ? data.masehi.teks : '';
    }
    if (el.masehiSub) {
      el.masehiSub.textContent = (data.masehi && data.masehi.hari) ? data.masehi.hari : '';
    }

    // Daftar Tanggal Penting
    if (el.pentingTitle && data.hijriah) {
      el.pentingTitle.textContent = 'Tanggal penting tahun ' + data.hijriah.tahun + ' H';
    }

    if (el.pentingList && data.tanggal_penting && Array.isArray(data.tanggal_penting)) {
      el.pentingList.innerHTML = '';
      for (var i = 0; i < data.tanggal_penting.length; i++) {
        var item = data.tanggal_penting[i];
        var li = document.createElement('li');
        li.className = 'hijriah__penting-item';

        var leftDiv = document.createElement('div');
        leftDiv.className = 'hijriah__penting-left';

        var nameSpan = document.createElement('span');
        nameSpan.className = 'hijriah__penting-name';
        nameSpan.textContent = item.nama;

        var hijriahSpan = document.createElement('span');
        hijriahSpan.className = 'hijriah__penting-hijriah';
        hijriahSpan.textContent = item.hijriah;

        leftDiv.appendChild(nameSpan);
        leftDiv.appendChild(hijriahSpan);

        var rightDiv = document.createElement('div');
        rightDiv.className = 'hijriah__penting-right';

        var masehiSpan = document.createElement('span');
        masehiSpan.className = 'hijriah__penting-masehi';
        masehiSpan.textContent = item.masehi;

        var hariSpan = document.createElement('span');
        hariSpan.className = 'hijriah__penting-hari';
        hariSpan.textContent = item.hari;

        rightDiv.appendChild(masehiSpan);
        rightDiv.appendChild(hariSpan);

        li.appendChild(leftDiv);
        li.appendChild(rightDiv);
        el.pentingList.appendChild(li);
      }
    }
  }

  function submitConversion() {
    if (state.busy) return;

    var form = new FormData();
    form.append('mode', state.mode);

    if (state.mode === 'ke_masehi') {
      var valH = el.hari ? el.hari.value.trim() : '';
      var valB = el.bulan ? el.bulan.value.trim() : '';
      var valT = el.tahun ? el.tahun.value.trim() : '';

      if (!valH || !valB || !valT) {
        setStatus('Lengkapi hari, bulan, dan tahun Hijriah.', 'error');
        if (!valH && el.hari) el.hari.focus();
        else if (!valB && el.bulan) el.bulan.focus();
        else if (!valT && el.tahun) el.tahun.focus();
        return;
      }
      form.append('hari', valH);
      form.append('bulan', valB);
      form.append('tahun', valT);
    } else {
      var valM = el.masehi ? el.masehi.value.trim() : '';
      if (!valM) {
        setStatus('Pilih tanggal Masehi yang ingin diubah.', 'error');
        if (el.masehi) el.masehi.focus();
        return;
      }
      form.append('tanggal_masehi', valM);
    }

    state.busy = true;
    updateControls();
    setStatus('Sedang mengubah tanggal...', 'busy');

    fetch(serverBase + '/api/hijriah', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('Tanggal berhasil diubah.', 'ok');
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
    if (!state.lastResult) return;
    var d = state.lastResult;
    var lines = [
      'Konversi Kalender Hijriah',
      'Tanggal Hijriah: ' + d.hijriah.teks + ' (' + d.masehi.hari + ', hari ke-' + d.hijriah.hari_dalam_tahun + ' dalam setahun)',
      'Tanggal Masehi: ' + d.masehi.teks + ' (' + d.masehi.hari + ')',
      '',
      'Tanggal penting tahun ' + d.hijriah.tahun + ' H:'
    ];

    if (d.tanggal_penting && Array.isArray(d.tanggal_penting)) {
      for (var i = 0; i < d.tanggal_penting.length; i++) {
        var it = d.tanggal_penting[i];
        lines.push('• ' + it.nama + ': ' + it.hijriah + ' = ' + it.masehi + ' (' + it.hari + ')');
      }
    }

    lines.push('');
    lines.push('Perhitungan aritmetika (tabular). Bisa berbeda 1 hari dari penetapan resmi pemerintah.');

    var textToCopy = lines.join('\n');

    function notify(ok) {
      if (ok) {
        setStatus('Hasil konversi disalin ke papan klip.', 'ok');
      } else {
        setStatus('Gagal menyalin hasil konversi.', 'error');
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
    if (el.hari) el.hari.value = '';
    if (el.bulan) el.bulan.value = '1';
    if (el.tahun) el.tahun.value = '';
    if (el.masehi) el.masehi.value = '';
    resetResults();
    setStatus(
      state.mode === 'ke_masehi'
        ? 'Masukkan tanggal Hijriah lalu tekan "Ubah tanggal".'
        : 'Pilih tanggal Masehi lalu tekan "Ubah tanggal".',
      ''
    );
    updateControls();
    if (state.mode === 'ke_masehi' && el.hari) {
      el.hari.focus();
    } else if (state.mode === 'ke_hijriah' && el.masehi) {
      el.masehi.focus();
    }
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="hijriah"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
  }

  function open() {
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

    setTimeout(function () {
      if (state.mode === 'ke_masehi' && el.hari) {
        el.hari.focus();
      } else if (state.mode === 'ke_hijriah' && el.masehi) {
        el.masehi.focus();
      }
    }, 100);
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

  if (el.modeGroup) {
    el.modeGroup.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-mode]');
      if (!btn) return;
      var targetMode = btn.getAttribute('data-mode');
      if (targetMode && targetMode !== state.mode) {
        setMode(targetMode);
      }
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var canSubmit = false;
      if (state.mode === 'ke_masehi') {
        var valH = el.hari ? el.hari.value.trim() : '';
        var valB = el.bulan ? el.bulan.value.trim() : '';
        var valT = el.tahun ? el.tahun.value.trim() : '';
        canSubmit = (valH.length > 0 && valB.length > 0 && valT.length > 0);
      } else {
        var valM = el.masehi ? el.masehi.value.trim() : '';
        canSubmit = (valM.length > 0);
      }
      if (canSubmit) {
        submitConversion();
      }
    }
  }

  if (el.hari) {
    el.hari.addEventListener('input', updateControls);
    el.hari.addEventListener('keydown', onInputKeydown);
  }
  if (el.bulan) {
    el.bulan.addEventListener('change', updateControls);
  }
  if (el.tahun) {
    el.tahun.addEventListener('input', updateControls);
    el.tahun.addEventListener('keydown', onInputKeydown);
  }
  if (el.masehi) {
    el.masehi.addEventListener('input', updateControls);
    el.masehi.addEventListener('change', updateControls);
    el.masehi.addEventListener('keydown', onInputKeydown);
  }

  if (el.submit) el.submit.addEventListener('click', submitConversion);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);

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
        submitConversion();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);

  // Daftarkan panel supaya kartu Kalender Hijriah bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['hijriah'] = toggle;

  // Inisialisasi bawaan
  setMode('ke_masehi');
  updateControls();
})();
