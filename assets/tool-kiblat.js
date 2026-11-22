/* =========================================================================
   Panel alat: Arah kiblat dan jarak ke Makkah (kiblat)
   Hitung arah kiblat (sudut dari utara sejati) dan jarak garis lurus ke Ka'bah.
   Pilihan dari kota bawaan atau koordinat sendiri.
   Semua data diproses di memori server dan tidak dicatat ke log.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('kiblat-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('kiblat-close'),
    kota: document.getElementById('kiblat-kota'),
    coordsWrap: document.getElementById('kiblat-coords-wrap'),
    lintang: document.getElementById('kiblat-lintang'),
    bujur: document.getElementById('kiblat-bujur'),
    status: document.getElementById('kiblat-status'),
    clear: document.getElementById('kiblat-clear'),
    submit: document.getElementById('kiblat-submit'),
    result: document.getElementById('kiblat-result'),
    heroDerajat: document.getElementById('kiblat-hero-derajat'),
    heroArah: document.getElementById('kiblat-hero-arah'),
    heroJarak: document.getElementById('kiblat-hero-jarak'),
    statLokasi: document.getElementById('kiblat-stat-lokasi'),
    statKoordinat: document.getElementById('kiblat-stat-koordinat'),
    statDerajat: document.getElementById('kiblat-stat-derajat'),
    statJarak: document.getElementById('kiblat-stat-jarak'),
    pesan: document.getElementById('kiblat-pesan'),
    copy: document.getElementById('kiblat-copy')
  };

  var FALLBACK_KOTA = [
    { nama: 'Ambon', lintang: -3.6958, bujur: 128.1831 },
    { nama: 'Balikpapan', lintang: -1.2654, bujur: 116.8312 },
    { nama: 'Banda Aceh', lintang: 5.5483, bujur: 95.3238 },
    { nama: 'Bandar Lampung', lintang: -5.4292, bujur: 105.2610 },
    { nama: 'Bandung', lintang: -6.9175, bujur: 107.6191 },
    { nama: 'Banjarmasin', lintang: -3.3194, bujur: 114.5908 },
    { nama: 'Batam', lintang: 1.0456, bujur: 104.0305 },
    { nama: 'Bekasi', lintang: -6.2383, bujur: 106.9756 },
    { nama: 'Bengkulu', lintang: -3.8004, bujur: 102.2655 },
    { nama: 'Bogor', lintang: -6.5971, bujur: 106.8060 },
    { nama: 'Cimahi', lintang: -6.8722, bujur: 107.5425 },
    { nama: 'Cirebon', lintang: -6.7320, bujur: 108.5523 },
    { nama: 'Denpasar', lintang: -8.6705, bujur: 115.2126 },
    { nama: 'Depok', lintang: -6.4025, bujur: 106.7942 },
    { nama: 'Gorontalo', lintang: 0.5435, bujur: 123.0568 },
    { nama: 'Jakarta', lintang: -6.2088, bujur: 106.8456 },
    { nama: 'Jambi', lintang: -1.6101, bujur: 103.6131 },
    { nama: 'Jayapura', lintang: -2.5916, bujur: 140.6690 },
    { nama: 'Kediri', lintang: -7.8480, bujur: 112.0178 },
    { nama: 'Kendari', lintang: -3.9985, bujur: 122.5126 },
    { nama: 'Kupang', lintang: -10.1772, bujur: 123.6070 },
    { nama: 'Makassar', lintang: -5.1477, bujur: 119.4327 },
    { nama: 'Malang', lintang: -7.9666, bujur: 112.6326 },
    { nama: 'Manado', lintang: 1.4748, bujur: 124.8421 },
    { nama: 'Manokwari', lintang: -0.8615, bujur: 134.0620 },
    { nama: 'Mataram', lintang: -8.5833, bujur: 116.1167 },
    { nama: 'Medan', lintang: 3.5952, bujur: 98.6722 },
    { nama: 'Padang', lintang: -0.9471, bujur: 100.4172 },
    { nama: 'Palangka Raya', lintang: -2.2161, bujur: 113.9139 },
    { nama: 'Palembang', lintang: -2.9761, bujur: 104.7754 },
    { nama: 'Palu', lintang: -0.9003, bujur: 119.8779 },
    { nama: 'Pangkal Pinang', lintang: -2.1316, bujur: 106.1169 },
    { nama: 'Pekanbaru', lintang: 0.5071, bujur: 101.4478 },
    { nama: 'Pontianak', lintang: -0.0263, bujur: 109.3425 },
    { nama: 'Samarinda', lintang: -0.5016, bujur: 117.1537 },
    { nama: 'Semarang', lintang: -6.9667, bujur: 110.4167 },
    { nama: 'Solo (Surakarta)', lintang: -7.5755, bujur: 110.8243 },
    { nama: 'Sorong', lintang: -0.8762, bujur: 131.2558 },
    { nama: 'Surabaya', lintang: -7.2575, bujur: 112.7521 },
    { nama: 'Tangerang', lintang: -6.1781, bujur: 106.6300 },
    { nama: 'Tanjung Pinang', lintang: 0.9186, bujur: 104.4666 },
    { nama: 'Tasikmalaya', lintang: -7.3274, bujur: 108.2207 },
    { nama: 'Ternate', lintang: 0.7904, bujur: 127.3780 },
    { nama: 'Yogyakarta', lintang: -7.7956, bujur: 110.3695 }
  ];

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    kotaList: FALLBACK_KOTA,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    abortController: null
  };

  function formatNumber(num, decimals) {
    var d = typeof decimals === 'number' ? decimals : 0;
    var n = Number(num) || 0;
    return new Intl.NumberFormat('id-ID', {
      minimumFractionDigits: d,
      maximumFractionDigits: d
    }).format(n);
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

  function cariKotaData(nama) {
    if (!nama) return null;
    var target = String(nama).trim().toLowerCase();
    for (var i = 0; i < state.kotaList.length; i++) {
      if (state.kotaList[i].nama.toLowerCase() === target) {
        return state.kotaList[i];
      }
    }
    return null;
  }

  function updateControls() {
    var isCustom = el.kota && el.kota.value === 'custom';
    if (el.coordsWrap) {
      el.coordsWrap.hidden = !isCustom;
    }

    if (el.lintang) el.lintang.required = isCustom;
    if (el.bujur) el.bujur.required = isCustom;

    var canSubmit = false;
    if (isCustom) {
      var latVal = el.lintang ? el.lintang.value.trim() : '';
      var lonVal = el.bujur ? el.bujur.value.trim() : '';
      canSubmit = Boolean(latVal) && Boolean(lonVal) && !state.busy;
    } else {
      var kotaVal = el.kota ? el.kota.value : '';
      canSubmit = Boolean(kotaVal) && !state.busy;
    }

    if (el.submit) {
      el.submit.disabled = !canSubmit;
    }
    if (el.clear) {
      el.clear.disabled = state.busy && !state.abortController;
    }
  }

  function populateKotaSelect(list) {
    if (!el.kota) return;
    var currentVal = el.kota.value || 'Bandung';
    el.kota.innerHTML = '';

    list.forEach(function (k) {
      var opt = document.createElement('option');
      opt.value = k.nama;
      opt.textContent = k.nama;
      if (k.nama === currentVal) {
        opt.selected = true;
      }
      el.kota.appendChild(opt);
    });

    var optCustom = document.createElement('option');
    optCustom.value = 'custom';
    optCustom.textContent = 'Masukkan koordinat sendiri...';
    if (currentVal === 'custom') {
      optCustom.selected = true;
    }
    el.kota.appendChild(optCustom);

    onKotaPilih();
  }

  function onKotaPilih() {
    if (!el.kota) return;
    var val = el.kota.value;
    if (val === 'custom') {
      if (el.coordsWrap) el.coordsWrap.hidden = false;
      if (el.lintang) el.lintang.required = true;
      if (el.bujur) el.bujur.required = true;
      if (el.lintang) el.lintang.focus();
    } else {
      if (el.coordsWrap) el.coordsWrap.hidden = true;
      if (el.lintang) el.lintang.required = false;
      if (el.bujur) el.bujur.required = false;

      var kData = cariKotaData(val);
      if (kData) {
        if (el.lintang) el.lintang.value = String(kData.lintang);
        if (el.bujur) el.bujur.value = String(kData.bujur);
      }
    }
    updateControls();
  }

  function onManualCoordInput() {
    if (el.kota && el.kota.value !== 'custom') {
      el.kota.value = 'custom';
    }
    updateControls();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/kiblat/limits', {
      headers: { 'Accept': 'application/json' },
      cache: 'no-store'
    })
      .then(function (res) {
        if (!res.ok) throw new Error('Gagal mengambil batas alat');
        return res.json();
      })
      .then(function (body) {
        var data = (body && body.data) || body;
        if (data && Array.isArray(data.kota) && data.kota.length > 0) {
          state.kotaList = data.kota;
          state.limitsLoaded = true;
          populateKotaSelect(state.kotaList);
        }
      })
      .catch(function () {
        // Gunakan fallback kota yang sudah ada
      });
  }

  function renderResult(data) {
    state.lastResult = data;
    if (!el.result) return;

    var arahNum = Number(data.arah_derajat) || 0;
    var jarakNum = Number(data.jarak_km) || 0;

    if (el.heroDerajat) {
      el.heroDerajat.textContent = formatNumber(arahNum, 1) + '°';
    }
    if (el.heroArah) {
      el.heroArah.textContent = data.arah_mata_angin ? data.arah_mata_angin.toUpperCase() : '-';
    }
    if (el.heroJarak) {
      el.heroJarak.textContent = formatNumber(jarakNum, 0) + ' km';
    }

    if (el.statLokasi) {
      el.statLokasi.textContent = data.lokasi || '-';
    }
    if (el.statKoordinat) {
      var latStr = (data.lintang >= 0 ? '+' : '') + formatNumber(data.lintang, 4) + '°';
      var lonStr = (data.bujur >= 0 ? '+' : '') + formatNumber(data.bujur, 4) + '°';
      el.statKoordinat.textContent = latStr + ', ' + lonStr;
    }
    if (el.statDerajat) {
      el.statDerajat.textContent = formatNumber(arahNum, 1) + '° dari utara sejati';
    }
    if (el.statJarak) {
      el.statJarak.textContent = formatNumber(jarakNum, 0) + ' km ke Ka\'bah';
    }
    if (el.pesan) {
      el.pesan.textContent = data.catatan_utara || '';
    }

    el.result.hidden = false;
    el.result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function submitKiblat() {
    if (state.busy) return;

    var isCustom = el.kota && el.kota.value === 'custom';
    var payload = {};

    if (isCustom) {
      var lat = el.lintang ? el.lintang.value.trim() : '';
      var lon = el.bujur ? el.bujur.value.trim() : '';
      if (!lat || !lon) {
        setStatus('Harap isi koordinat lintang dan bujur.', 'warn');
        if (!lat && el.lintang) el.lintang.focus();
        else if (!lon && el.bujur) el.bujur.focus();
        return;
      }
      payload.lintang = lat;
      payload.bujur = lon;
    } else {
      var kota = el.kota ? el.kota.value : '';
      if (!kota) {
        setStatus('Pilih kota terlebih dahulu.', 'warn');
        return;
      }
      payload.kota = kota;
    }

    state.busy = true;
    updateControls();
    setStatus('Menghitung arah kiblat...', 'busy');

    if (state.abortController) {
      state.abortController.abort();
    }
    state.abortController = new AbortController();

    fetch(serverBase + '/api/kiblat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      cache: 'no-store',
      body: JSON.stringify(payload),
      signal: state.abortController.signal
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, status: res.status, body: body };
        });
      })
      .then(function (resp) {
        state.busy = false;
        state.abortController = null;
        updateControls();

        if (!resp.ok || !resp.body || resp.body.ok === false) {
          var msg = (resp.body && (resp.body.pesan || (resp.body.error && resp.body.error.message))) ||
            'Terjadi kesalahan saat menghitung arah kiblat.';
          setStatus(msg, 'error');
          return;
        }

        var data = resp.body.data || resp.body;
        setStatus('Perhitungan arah kiblat selesai.', 'success');
        renderResult(data);
      })
      .catch(function (err) {
        if (err.name === 'AbortError') return;
        state.busy = false;
        state.abortController = null;
        updateControls();
        setStatus('Tidak bisa terhubung ke server. Periksa koneksi internetmu.', 'error');
      });
  }

  function resetAll() {
    if (state.abortController) {
      state.abortController.abort();
      state.abortController = null;
    }
    state.busy = false;
    state.lastResult = null;

    if (el.kota) el.kota.value = 'Bandung';
    if (el.coordsWrap) el.coordsWrap.hidden = true;
    var kData = cariKotaData('Bandung');
    if (kData) {
      if (el.lintang) el.lintang.value = String(kData.lintang);
      if (el.bujur) el.bujur.value = String(kData.bujur);
    } else {
      if (el.lintang) el.lintang.value = '-6.9175';
      if (el.bujur) el.bujur.value = '107.6191';
    }
    if (el.lintang) el.lintang.required = false;
    if (el.bujur) el.bujur.required = false;

    if (el.result) el.result.hidden = true;
    setStatus('Pilih kota atau masukkan koordinat, lalu tekan "Hitung arah kiblat".', '');
    updateControls();
    if (el.kota) el.kota.focus();
  }

  function copyResult() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var arahStr = formatNumber(d.arah_derajat, 1) + '°';
    var mataAnginStr = d.arah_mata_angin ? d.arah_mata_angin : '';
    var jarakStr = formatNumber(d.jarak_km, 0) + ' km';
    var latStr = (d.lintang >= 0 ? '+' : '') + formatNumber(d.lintang, 4) + '°';
    var lonStr = (d.bujur >= 0 ? '+' : '') + formatNumber(d.bujur, 4) + '°';

    var lines = [
      'Arah Kiblat & Jarak ke Makkah',
      'Lokasi: ' + d.lokasi + ' (' + latStr + ', ' + lonStr + ')',
      'Arah kiblat: ' + arahStr + ' (' + mataAnginStr + ' dari utara sejati)',
      'Jarak ke Ka\'bah: ' + jarakStr,
      'Catatan: ' + (d.catatan_utara || '')
    ];
    var text = lines.join('\n');

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        setStatus('Ringkasan disalin ke papan klip.', 'success');
      }).catch(function () {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      setStatus('Ringkasan disalin ke papan klip.', 'success');
    } catch (e) {
      setStatus('Gagal menyalin. Silakan salin hasil secara manual.', 'warn');
    }
    document.body.removeChild(ta);
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="kiblat"]');
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
      if (el.kota) el.kota.focus();
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
        submitKiblat();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.kota) el.kota.addEventListener('change', onKotaPilih);
  if (el.lintang) {
    el.lintang.addEventListener('input', onManualCoordInput);
    el.lintang.addEventListener('change', onManualCoordInput);
  }
  if (el.bujur) {
    el.bujur.addEventListener('input', onManualCoordInput);
    el.bujur.addEventListener('change', onManualCoordInput);
  }

  if (el.submit) el.submit.addEventListener('click', submitKiblat);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels.kiblat = toggle;

  populateKotaSelect(state.kotaList);
  updateControls();
})();
