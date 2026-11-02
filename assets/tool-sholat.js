/* =========================================================================
   Panel alat: Jadwal sholat harian untuk kota di Indonesia
   Waktu sholat dihitung secara mandiri di server berdasarkan posisi astronomis
   matahari. Pilihan diproses di memori lalu dibuang, tidak disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('sholat-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('sholat-close'),
    kota: document.getElementById('sholat-kota'),
    manualWrap: document.getElementById('sholat-manual-coords'),
    lintang: document.getElementById('sholat-lintang'),
    bujur: document.getElementById('sholat-bujur'),
    zona: document.getElementById('sholat-zona'),
    tanggal: document.getElementById('sholat-tanggal'),
    metode: document.getElementById('sholat-metode'),
    submit: document.getElementById('sholat-submit'),
    clear: document.getElementById('sholat-clear'),
    status: document.getElementById('sholat-status'),
    results: document.getElementById('sholat-results'),
    resultHint: document.getElementById('sholat-result-hint'),
    outputWrap: document.getElementById('sholat-output'),
    cityName: document.getElementById('sholat-city-name'),
    zoneBadge: document.getElementById('sholat-zone-badge'),
    dateMasehi: document.getElementById('sholat-date-masehi'),
    dateHijriah: document.getElementById('sholat-date-hijriah'),
    methodName: document.getElementById('sholat-method-name'),
    passedWrap: document.getElementById('sholat-passed-wrap'),
    btnBesok: document.getElementById('sholat-btn-besok'),
    timesList: document.getElementById('sholat-times-list'),
    copy: document.getElementById('sholat-copy'),
    download: document.getElementById('sholat-download'),
    noteText: document.getElementById('sholat-note-text')
  };

  var state = {
    limitsLoaded: false,
    limitsData: null,
    busy: false,
    lastFocus: null,
    lastResult: null,
    downloadUrl: null,
    timerInterval: null
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

  function revokeDownload() {
    if (state.downloadUrl) {
      try {
        URL.revokeObjectURL(state.downloadUrl);
      } catch (e) { /* abaikan */ }
      state.downloadUrl = null;
    }
  }

  function stopCountdown() {
    if (state.timerInterval) {
      clearInterval(state.timerInterval);
      state.timerInterval = null;
    }
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="sholat"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'sholat-panel');
    }
  }

  function addOneDay(isoDateStr) {
    var parts = isoDateStr.split('-');
    var y = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10) - 1;
    var d = parseInt(parts[2], 10);
    var dt = new Date(Date.UTC(y, m, d + 1));
    var ny = dt.getUTCFullYear();
    var nm = String(dt.getUTCMonth() + 1).padStart(2, '0');
    var nd = String(dt.getUTCDate()).padStart(2, '0');
    return ny + '-' + nm + '-' + nd;
  }

  function onKotaChange() {
    var isManual = el.kota && el.kota.value === 'custom';
    if (el.manualWrap) {
      el.manualWrap.hidden = !isManual;
    }
    if (isManual && el.lintang) {
      el.lintang.focus();
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/sholat/limits', {
      headers: { 'Accept': 'application/json' },
      cache: 'no-store'
    })
      .then(function (res) {
        if (!res.ok) throw new Error('Gagal mengambil batas alat');
        return res.json();
      })
      .then(function (res) {
        var data = res.data || res;
        state.limitsData = data;
        state.limitsLoaded = true;

        // Isi pilihan kota
        if (el.kota && data.kota && Array.isArray(data.kota)) {
          var currentVal = el.kota.value;
          el.kota.textContent = '';
          for (var i = 0; i < data.kota.length; i++) {
            var k = data.kota[i];
            var opt = document.createElement('option');
            opt.value = k.nama;
            opt.textContent = k.nama;
            el.kota.appendChild(opt);
          }
          var optCustom = document.createElement('option');
          optCustom.value = 'custom';
          optCustom.textContent = 'Lokasi sendiri…';
          el.kota.appendChild(optCustom);

          if (currentVal) {
            el.kota.value = currentVal;
          } else {
            el.kota.value = 'Jakarta';
          }
        }

        // Isi tanggal awal bila kosong
        if (el.tanggal && !el.tanggal.value && data.hari_ini) {
          el.tanggal.value = data.hari_ini;
        }

        // Isi metode bila kosong
        if (el.metode && data.metode && Array.isArray(data.metode)) {
          var curMetode = el.metode.value;
          el.metode.textContent = '';
          for (var m = 0; m < data.metode.length; m++) {
            var item = data.metode[m];
            var mOpt = document.createElement('option');
            mOpt.value = item.id;
            mOpt.textContent = item.nama;
            el.metode.appendChild(mOpt);
          }
          if (curMetode) {
            el.metode.value = curMetode;
          } else {
            el.metode.value = 'kemenag';
          }
        }

        if (el.noteText && data.catatan) {
          el.noteText.textContent = data.catatan;
        }

        onKotaChange();
      })
      .catch(function () {
        // Fallback: batas tetap bisa digunakan dari nilai bawaan HTML
      });
  }

  function updateCountdownTick() {
    if (!state.lastResult || !el.timesList) return;
    var res = state.lastResult;
    var tglParts = res.tanggal.nilai.split('-');
    var year = parseInt(tglParts[0], 10);
    var month = parseInt(tglParts[1], 10);
    var day = parseInt(tglParts[2], 10);
    var zona = Number(res.kota.zona);

    var nowMs = Date.now();
    var nextIndex = -1;
    var diffSec = 0;

    for (var i = 0; i < res.waktu.length; i++) {
      var w = res.waktu[i];
      if (!w.jam) continue;
      var hm = w.jam.split(':');
      var h = parseInt(hm[0], 10);
      var m = parseInt(hm[1], 10);
      var targetUtcMs = Date.UTC(year, month - 1, day, h - zona, m, 0);

      if (targetUtcMs > nowMs) {
        nextIndex = i;
        diffSec = Math.floor((targetUtcMs - nowMs) / 1000);
        break;
      }
    }

    var rows = el.timesList.querySelectorAll('.sh__row');
    for (var r = 0; r < rows.length; r++) {
      var rowEl = rows[r];
      var badgeNext = rowEl.querySelector('.sh__badge-next');
      var countdownEl = rowEl.querySelector('.sh__countdown');

      if (r === nextIndex) {
        rowEl.classList.add('sh__row--next');
        if (badgeNext) badgeNext.hidden = false;
        if (countdownEl) {
          countdownEl.hidden = false;
          if (diffSec < 60) {
            countdownEl.textContent = 'kurang dari 1 menit';
          } else {
            var jamLagi = Math.floor(diffSec / 3600);
            var mntLagi = Math.floor((diffSec % 3600) / 60);
            if (jamLagi > 0) {
              countdownEl.textContent = jamLagi + ' jam ' + mntLagi + ' menit lagi';
            } else {
              countdownEl.textContent = mntLagi + ' menit lagi';
            }
          }
        }
      } else {
        rowEl.classList.remove('sh__row--next');
        if (badgeNext) badgeNext.hidden = true;
        if (countdownEl) {
          countdownEl.hidden = true;
          countdownEl.textContent = '';
        }
      }
    }

    if (el.passedWrap) {
      el.passedWrap.hidden = (nextIndex !== -1);
    }
  }

  function renderResult(data) {
    state.lastResult = data;
    stopCountdown();

    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.cityName) el.cityName.textContent = data.kota.nama;
    if (el.zoneBadge) el.zoneBadge.textContent = data.kota.zona_label;
    if (el.dateMasehi) el.dateMasehi.textContent = data.tanggal.teks;
    if (el.dateHijriah) {
      var hText = (typeof data.tanggal_hijriah === 'object' && data.tanggal_hijriah)
        ? data.tanggal_hijriah.teks
        : data.tanggal_hijriah;
      el.dateHijriah.textContent = hText || '';
    }
    if (el.methodName) {
      var ihtiyatText = data.metode.ihtiyat_menit ? ' (+ihtiyat ' + data.metode.ihtiyat_menit + ' menit)' : '';
      el.methodName.textContent = data.metode.nama + ihtiyatText;
    }
    if (el.noteText && data.catatan) {
      el.noteText.textContent = data.catatan;
    }

    if (el.timesList) {
      el.timesList.textContent = '';
      for (var i = 0; i < data.waktu.length; i++) {
        var w = data.waktu[i];
        var row = document.createElement('div');
        row.className = 'sh__row';
        row.setAttribute('data-kunci', w.kunci);

        var left = document.createElement('div');
        left.className = 'sh__row-left';

        var nameEl = document.createElement('span');
        nameEl.className = 'sh__name';
        nameEl.textContent = w.nama;
        left.appendChild(nameEl);

        var badge = document.createElement('span');
        badge.className = 'sh__badge-next';
        badge.textContent = 'berikutnya';
        badge.hidden = true;
        left.appendChild(badge);

        var right = document.createElement('div');
        right.className = 'sh__row-right';

        var timeEl = document.createElement('span');
        timeEl.className = 'sh__time';
        timeEl.textContent = w.jam ? w.jam : '-';
        right.appendChild(timeEl);

        var countdown = document.createElement('span');
        countdown.className = 'sh__countdown';
        countdown.hidden = true;
        right.appendChild(countdown);

        row.appendChild(left);
        row.appendChild(right);
        el.timesList.appendChild(row);
      }
    }

    updateCountdownTick();
    state.timerInterval = setInterval(updateCountdownTick, 1000);
  }

  function buildScheduleText(data) {
    var lines = [];
    lines.push('Jadwal Sholat - ' + data.kota.nama + ' (' + data.kota.zona_label + ')');
    var hText = (typeof data.tanggal_hijriah === 'object' && data.tanggal_hijriah)
      ? data.tanggal_hijriah.teks
      : data.tanggal_hijriah;
    lines.push(data.tanggal.teks + (hText ? ' / ' + hText : ''));
    lines.push('Metode: ' + data.metode.nama + (data.metode.ihtiyat_menit ? ' (ihtiyat ' + data.metode.ihtiyat_menit + ' menit)' : ''));
    lines.push('');
    for (var i = 0; i < data.waktu.length; i++) {
      var w = data.waktu[i];
      lines.push(w.nama + ': ' + (w.jam ? w.jam : '-'));
    }
    lines.push('');
    lines.push('Catatan:');
    lines.push(data.catatan);
    return lines.join('\n');
  }

  function submitSchedule() {
    if (state.busy) return;

    var payload = {};
    var isManual = el.kota && el.kota.value === 'custom';

    if (isManual) {
      var rawLat = el.lintang ? el.lintang.value.trim() : '';
      var rawLon = el.bujur ? el.bujur.value.trim() : '';
      var rawZona = el.zona ? el.zona.value.trim() : '7';

      if (!rawLat || !rawLon) {
        setStatus('Masukkan angka lintang dan bujur untuk lokasi sendiri.', 'error');
        if (el.lintang && !rawLat) el.lintang.focus();
        else if (el.bujur) el.bujur.focus();
        return;
      }

      var lat = parseFloat(rawLat);
      var lon = parseFloat(rawLon);
      var zona = parseFloat(rawZona);

      if (isNaN(lat) || lat < -90 || lat > 90) {
        setStatus('Lintang harus berupa angka antara -90 sampai 90 derajat.', 'error');
        if (el.lintang) el.lintang.focus();
        return;
      }
      if (isNaN(lon) || lon < -180 || lon > 180) {
        setStatus('Bujur harus berupa angka antara -180 sampai 180 derajat.', 'error');
        if (el.bujur) el.bujur.focus();
        return;
      }

      payload.lintang = lat;
      payload.bujur = lon;
      payload.zona = zona;
      payload.kota = 'custom';
    } else {
      payload.kota = el.kota ? el.kota.value : 'Jakarta';
    }

    if (el.tanggal && el.tanggal.value) {
      payload.tanggal = el.tanggal.value;
    }

    if (el.metode && el.metode.value) {
      payload.metode = el.metode.value;
    }

    state.busy = true;
    if (el.submit) el.submit.disabled = true;
    setStatus('Menghitung…', 'busy');

    fetch(serverBase + '/api/sholat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(payload),
      cache: 'no-store'
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, status: res.status, body: body };
        });
      })
      .then(function (resp) {
        state.busy = false;
        if (el.submit) el.submit.disabled = false;

        if (!resp.ok || !resp.body.ok) {
          var errMsg = 'Terjadi kendala saat menghitung jadwal.';
          if (resp.body && resp.body.error && resp.body.error.message) {
            errMsg = resp.body.error.message;
          }
          setStatus(errMsg, 'error');
          return;
        }

        setStatus('Jadwal sholat berhasil dihitung.', 'success');
        renderResult(resp.body.data);
      })
      .catch(function () {
        state.busy = false;
        if (el.submit) el.submit.disabled = false;
        setStatus('Tidak bisa menghubungi server. Coba lagi.', 'error');
      });
  }

  function resetAll() {
    stopCountdown();
    revokeDownload();
    state.lastResult = null;

    if (el.kota) el.kota.value = 'Jakarta';
    if (el.manualWrap) el.manualWrap.hidden = true;
    if (el.lintang) el.lintang.value = '';
    if (el.bujur) el.bujur.value = '';
    if (el.zona) el.zona.value = '7';

    if (state.limitsData && state.limitsData.hari_ini && el.tanggal) {
      el.tanggal.value = state.limitsData.hari_ini;
    }
    if (el.metode) el.metode.value = 'kemenag';

    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.timesList) el.timesList.textContent = '';
    if (el.passedWrap) el.passedWrap.hidden = true;

    setStatus('Pilih kota dan tanggal, lalu tekan "Lihat jadwal".', '');
    if (el.kota) el.kota.focus();
  }

  function copySchedule() {
    if (!state.lastResult) return;
    var text = buildScheduleText(state.lastResult);

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text).then(function () {
        setStatus('Jadwal berhasil disalin ke papan klip.', 'success');
      }).catch(function () {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'absolute';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setStatus('Jadwal berhasil disalin ke papan klip.', 'success');
    } catch (e) {
      setStatus('Gagal menyalin teks jadwal.', 'error');
    }
  }

  function downloadSchedule() {
    if (!state.lastResult) return;
    revokeDownload();

    var text = buildScheduleText(state.lastResult);
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    state.downloadUrl = URL.createObjectURL(blob);

    var cleanKota = state.lastResult.kota.nama
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
    var fileName = 'jadwal-sholat-' + cleanKota + '-' + state.lastResult.tanggal.nilai + '.txt';

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setStatus('Berkas jadwal sholat berhasil diunduh.', 'success');
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
      if (el.kota) el.kota.focus();
    }, 100);
  }

  function close() {
    if (panel.hidden) return;
    stopCountdown();
    revokeDownload();
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
  if (el.kota) el.kota.addEventListener('change', onKotaChange);
  if (el.submit) el.submit.addEventListener('click', submitSchedule);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copySchedule);
  if (el.download) el.download.addEventListener('click', downloadSchedule);
  if (el.btnBesok) {
    el.btnBesok.addEventListener('click', function () {
      if (!state.lastResult) return;
      var nextDate = addOneDay(state.lastResult.tanggal.nilai);
      if (el.tanggal) el.tanggal.value = nextDate;
      submitSchedule();
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitSchedule();
    }
  }

  if (el.tanggal) el.tanggal.addEventListener('keydown', onInputKeydown);
  if (el.lintang) el.lintang.addEventListener('keydown', onInputKeydown);
  if (el.bujur) el.bujur.addEventListener('keydown', onInputKeydown);

  function onGlobalKeydown(e) {
    if (panel.hidden) return;
    if (e.key === 'Escape' && panel.contains(document.activeElement)) {
      e.preventDefault();
      close();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      if (panel.contains(document.activeElement)) {
        e.preventDefault();
        submitSchedule();
      }
    }
  }
  document.addEventListener('keydown', onGlobalKeydown);
  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel supaya kartu Jadwal Sholat di app.js bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels.sholat = toggle;
})();
