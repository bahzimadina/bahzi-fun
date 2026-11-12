/* =========================================================================
   Panel alat: Hitung tagihan listrik rumah (tagihan-listrik)
   Perkiraan pemakaian kWh dan rupiah tagihan listrik rumah dari daftar peralatan.
   Semua data diproses di memori server dan tidak disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('tagihan-listrik-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('tagihan-listrik-close'),
    note: document.getElementById('tagihan-listrik-note'),
    items: document.getElementById('tagihan-items'),
    addItem: document.getElementById('tagihan-add-item'),
    countBadge: document.getElementById('tagihan-count-badge'),
    golongan: document.getElementById('tagihan-golongan'),
    tarif: document.getElementById('tagihan-tarif'),
    token: document.getElementById('tagihan-token'),
    status: document.getElementById('tagihan-status'),
    clear: document.getElementById('tagihan-clear'),
    submit: document.getElementById('tagihan-submit'),
    result: document.getElementById('tagihan-result'),
    heroTotal: document.getElementById('tagihan-hero-total'),
    statKwhBulan: document.getElementById('tagihan-stat-kwh-bulan'),
    statRpHari: document.getElementById('tagihan-stat-rp-hari'),
    statRpTahun: document.getElementById('tagihan-stat-rp-tahun'),
    terbesar: document.getElementById('tagihan-terbesar'),
    tokenInfo: document.getElementById('tagihan-token-info'),
    tableBody: document.getElementById('tagihan-table-body'),
    catatan: document.getElementById('tagihan-catatan'),
    copy: document.getElementById('tagihan-copy'),
    download: document.getElementById('tagihan-download')
  };

  var FALLBACK_LIMITS = {
    max_alat: 30,
    watt_min: 1,
    watt_max: 100000,
    jam_max: 24,
    jumlah_max: 50,
    tarif_min: 100,
    tarif_max: 5000,
    token_min: 1000,
    token_max: 10000000,
    hari_per_bulan: 30,
    nama_max: 40,
    golongan: [
      { kode: '900-subsidi', label: '900 VA rumah tangga (subsidi)', tarif: 605.0 },
      { kode: '1300', label: '1300 VA rumah tangga', tarif: 1444.7 },
      { kode: '2200', label: '2200 VA rumah tangga', tarif: 1444.7 },
      { kode: '3500', label: '3500–5500 VA rumah tangga', tarif: 1699.53 },
      { kode: 'sendiri', label: 'Isi tarif sendiri', tarif: null }
    ]
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

  function formatRupiah(num) {
    var n = Math.round(Number(num) || 0);
    return 'Rp' + new Intl.NumberFormat('id-ID').format(n);
  }

  function formatKwh(num, decimals) {
    var d = typeof decimals === 'number' ? decimals : 1;
    var n = Number(num) || 0;
    return new Intl.NumberFormat('id-ID', {
      minimumFractionDigits: d,
      maximumFractionDigits: d
    }).format(n) + ' kWh';
  }

  function formatNumber(num, decimals) {
    var d = typeof decimals === 'number' ? decimals : 0;
    var n = Number(num) || 0;
    return new Intl.NumberFormat('id-ID', {
      minimumFractionDigits: d,
      maximumFractionDigits: d
    }).format(n);
  }

  function formatPersen(num) {
    var n = Number(num) || 0;
    return new Intl.NumberFormat('id-ID', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    }).format(n) + '%';
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

  function updateCountBadge() {
    if (!el.items) return;
    var rows = el.items.querySelectorAll('.tagihan__item-row');
    var count = rows.length;
    var max = state.limits.max_alat || 30;
    if (el.countBadge) {
      el.countBadge.textContent = count + ' / ' + max + ' alat';
    }
    if (el.addItem) {
      el.addItem.disabled = (count >= max) || state.busy;
    }
  }

  function createItemRow(namaVal, wattVal, jamVal, jumlahVal) {
    var row = document.createElement('div');
    row.className = 'tagihan__item-row';

    var colNama = document.createElement('div');
    colNama.className = 'tagihan__col tagihan__col--nama';
    var lblNama = document.createElement('label');
    lblNama.className = 'tagihan__label';
    lblNama.textContent = 'Nama alat';
    var inputNama = document.createElement('input');
    inputNama.type = 'text';
    inputNama.className = 'tagihan__input tagihan__input--nama';
    inputNama.placeholder = 'Mis. Kipas angin';
    inputNama.maxLength = state.limits.nama_max || 40;
    inputNama.value = namaVal || '';
    colNama.appendChild(lblNama);
    colNama.appendChild(inputNama);

    var colWatt = document.createElement('div');
    colWatt.className = 'tagihan__col tagihan__col--watt';
    var lblWatt = document.createElement('label');
    lblWatt.className = 'tagihan__label';
    lblWatt.textContent = 'Daya watt';
    var inputWatt = document.createElement('input');
    inputWatt.type = 'number';
    inputWatt.className = 'tagihan__input tagihan__input--watt';
    inputWatt.placeholder = 'Watt';
    inputWatt.min = String(state.limits.watt_min || 1);
    inputWatt.max = String(state.limits.watt_max || 100000);
    inputWatt.step = 'any';
    inputWatt.value = wattVal || '';
    colWatt.appendChild(lblWatt);
    colWatt.appendChild(inputWatt);

    var colJam = document.createElement('div');
    colJam.className = 'tagihan__col tagihan__col--jam';
    var lblJam = document.createElement('label');
    lblJam.className = 'tagihan__label';
    lblJam.textContent = 'Jam pemakaian per hari';
    var inputJam = document.createElement('input');
    inputJam.type = 'number';
    inputJam.className = 'tagihan__input tagihan__input--jam';
    inputJam.placeholder = 'Jam/hari';
    inputJam.min = '0';
    inputJam.max = String(state.limits.jam_max || 24);
    inputJam.step = '0.5';
    inputJam.value = jamVal || '';
    colJam.appendChild(lblJam);
    colJam.appendChild(inputJam);

    var colJumlah = document.createElement('div');
    colJumlah.className = 'tagihan__col tagihan__col--jumlah';
    var lblJumlah = document.createElement('label');
    lblJumlah.className = 'tagihan__label';
    lblJumlah.textContent = 'Jumlah unit';
    var inputJumlah = document.createElement('input');
    inputJumlah.type = 'number';
    inputJumlah.className = 'tagihan__input tagihan__input--jumlah';
    inputJumlah.placeholder = 'Unit';
    inputJumlah.min = '1';
    inputJumlah.max = String(state.limits.jumlah_max || 50);
    inputJumlah.step = '1';
    inputJumlah.value = jumlahVal || '1';
    colJumlah.appendChild(lblJumlah);
    colJumlah.appendChild(inputJumlah);

    var colDel = document.createElement('div');
    colDel.className = 'tagihan__col tagihan__col--del';
    var btnDel = document.createElement('button');
    btnDel.type = 'button';
    btnDel.className = 'tagihan__del-btn';
    var initialLabel = inputNama.value.trim() ? ('Hapus ' + inputNama.value.trim()) : 'Hapus baris alat';
    btnDel.setAttribute('aria-label', initialLabel);
    btnDel.title = 'Hapus alat ini';
    btnDel.innerHTML = '&times;';

    inputNama.addEventListener('input', function () {
      var n = inputNama.value.trim();
      btnDel.setAttribute('aria-label', n ? ('Hapus ' + n) : 'Hapus baris alat');
      updateControls();
    });
    inputWatt.addEventListener('input', updateControls);
    inputJam.addEventListener('input', updateControls);
    inputJumlah.addEventListener('input', updateControls);

    btnDel.addEventListener('click', function () {
      if (el.items && el.items.querySelectorAll('.tagihan__item-row').length > 1) {
        row.remove();
      } else {
        inputNama.value = '';
        inputWatt.value = '';
        inputJam.value = '';
        inputJumlah.value = '1';
        btnDel.setAttribute('aria-label', 'Hapus baris alat');
      }
      updateCountBadge();
      updateControls();
    });

    colDel.appendChild(btnDel);

    row.appendChild(colNama);
    row.appendChild(colWatt);
    row.appendChild(colJam);
    row.appendChild(colJumlah);
    row.appendChild(colDel);

    return row;
  }

  function addItem(nama, watt, jam, jumlah) {
    if (!el.items) return null;
    var rows = el.items.querySelectorAll('.tagihan__item-row');
    var max = state.limits.max_alat || 30;
    if (rows.length >= max) return null;
    var row = createItemRow(nama, watt, jam, jumlah);
    el.items.appendChild(row);
    updateCountBadge();
    updateControls();
    return row;
  }

  function getItemsData() {
    if (!el.items) return [];
    var rows = el.items.querySelectorAll('.tagihan__item-row');
    var data = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var inputNama = r.querySelector('.tagihan__input--nama');
      var inputWatt = r.querySelector('.tagihan__input--watt');
      var inputJam = r.querySelector('.tagihan__input--jam');
      var inputJumlah = r.querySelector('.tagihan__input--jumlah');

      var wattStr = inputWatt ? inputWatt.value.trim() : '';
      var jamStr = inputJam ? inputJam.value.trim() : '';
      var namaStr = inputNama ? inputNama.value.trim() : '';
      var jmlStr = inputJumlah ? inputJumlah.value.trim() : '1';

      // Masukkan item bila ada isian watt atau jam atau nama
      if (wattStr || jamStr || namaStr) {
        data.push({
          nama: namaStr || ('Alat ' + (i + 1)),
          watt: wattStr,
          jam: jamStr,
          jumlah: jmlStr || '1'
        });
      }
    }
    return data;
  }

  function updateControls() {
    var items = getItemsData();
    var hasItem = false;
    for (var i = 0; i < items.length; i++) {
      if (items[i].watt !== '' && items[i].jam !== '') {
        hasItem = true;
        break;
      }
    }

    var tarifVal = el.tarif ? el.tarif.value.trim() : '';
    var golVal = el.golongan ? el.golongan.value : '';
    var tarifOk = Boolean(tarifVal) || (golVal && golVal !== 'sendiri');

    var canSubmit = hasItem && tarifOk && !state.busy;
    if (el.submit) {
      el.submit.disabled = !canSubmit;
    }
    if (el.clear) {
      el.clear.disabled = state.busy && !state.abortController;
    }
  }

  function populateGolonganSelect(golonganList) {
    if (!el.golongan) return;
    var current = el.golongan.value || '1300';
    el.golongan.innerHTML = '';

    golonganList.forEach(function (g) {
      var opt = document.createElement('option');
      opt.value = g.kode;
      var text = g.label;
      if (g.tarif !== null && typeof g.tarif !== 'undefined') {
        text += ' (Rp' + formatNumber(g.tarif, g.tarif % 1 === 0 ? 0 : 1) + '/kWh)';
      }
      opt.textContent = text;
      el.golongan.appendChild(opt);
    });

    el.golongan.value = current || '1300';
    if (!el.golongan.value && el.golongan.options.length > 0) {
      el.golongan.selectedIndex = 0;
    }
  }

  function onGolonganChange() {
    if (!el.golongan) return;
    var selectedKode = el.golongan.value;
    var selectedItem = null;
    for (var i = 0; i < state.limits.golongan.length; i++) {
      if (state.limits.golongan[i].kode === selectedKode) {
        selectedItem = state.limits.golongan[i];
        break;
      }
    }

    if (selectedItem && selectedItem.tarif !== null && typeof selectedItem.tarif !== 'undefined') {
      if (el.tarif) el.tarif.value = String(selectedItem.tarif);
    } else {
      if (el.tarif) {
        el.tarif.value = '';
        el.tarif.focus();
      }
    }
    updateControls();
  }

  function applyLimits(data) {
    state.limits = {
      max_alat: data.max_alat || FALLBACK_LIMITS.max_alat,
      watt_min: data.watt_min || FALLBACK_LIMITS.watt_min,
      watt_max: data.watt_max || FALLBACK_LIMITS.watt_max,
      jam_max: data.jam_max || FALLBACK_LIMITS.jam_max,
      jumlah_max: data.jumlah_max || FALLBACK_LIMITS.jumlah_max,
      tarif_min: data.tarif_min || FALLBACK_LIMITS.tarif_min,
      tarif_max: data.tarif_max || FALLBACK_LIMITS.tarif_max,
      token_min: data.token_min || FALLBACK_LIMITS.token_min,
      token_max: data.token_max || FALLBACK_LIMITS.token_max,
      hari_per_bulan: data.hari_per_bulan || FALLBACK_LIMITS.hari_per_bulan,
      nama_max: data.nama_max || FALLBACK_LIMITS.nama_max,
      golongan: Array.isArray(data.golongan) && data.golongan.length > 0
        ? data.golongan
        : FALLBACK_LIMITS.golongan
    };

    populateGolonganSelect(state.limits.golongan);

    if (el.tarif) {
      el.tarif.min = String(state.limits.tarif_min);
      el.tarif.max = String(state.limits.tarif_max);
    }
    if (el.token) {
      el.token.min = String(state.limits.token_min);
      el.token.max = String(state.limits.token_max);
    }

    // Pasang tarif default jika kolom tarif masih kosong
    if (el.tarif && !el.tarif.value) {
      onGolonganChange();
    }
    updateCountBadge();
    updateControls();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/tagihan-listrik/limits')
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
          message = 'Layanan hitung tagihan listrik belum tersambung ke server. Coba lagi nanti.';
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
    var parts = [];
    parts.push('Perkiraan tagihan listrik: ' + formatRupiah(data.rupiah_bulan) + '/bulan');
    parts.push('Total pemakaian: ' + formatKwh(data.kwh_bulan, 1) + ' (' + formatKwh(data.kwh_hari, 1) + '/hari)');
    if (data.terbesar) {
      parts.push('Alat paling boros: ' + data.terbesar.nama + ' (' + formatRupiah(data.terbesar.rupiah_bulan) + '/bln, ' + formatPersen(data.terbesar.persen) + ')');
    }
    if (data.token) {
      parts.push('Token ' + formatRupiah(data.token.nominal) + ' setara ±' + formatNumber(data.token.kwh, 0) + ' kWh, cukup untuk ±' + formatNumber(data.token.hari, 1) + ' hari.');
    }
    return parts.join(' | ');
  }

  function buildPlainText(data) {
    var lines = [];
    lines.push('HITUNG TAGIHAN LISTRIK RUMAH');
    lines.push('============================');
    lines.push('Total perkiraan tagihan: ' + formatRupiah(data.rupiah_bulan) + ' / bulan');
    lines.push('Perkiraan per hari: ' + formatRupiah(data.rupiah_hari));
    lines.push('Perkiraan setahun: ' + formatRupiah(data.rupiah_tahun));
    lines.push('Total pemakaian listrik: ' + formatKwh(data.kwh_bulan, 2) + ' / bulan (' + formatKwh(data.kwh_hari, 2) + ' / hari)');
    lines.push('Tarif listrik: Rp' + formatNumber(data.tarif, data.tarif % 1 === 0 ? 0 : 2) + ' per kWh (Golongan: ' + data.golongan + ')');
    lines.push('');

    if (data.terbesar) {
      lines.push('Alat paling boros: ' + data.terbesar.nama + ': ' + formatRupiah(data.terbesar.rupiah_bulan) + ' / bulan (' + formatPersen(data.terbesar.persen) + ' dari total)');
      lines.push('');
    }

    if (data.token) {
      lines.push('Simulasi token listrik:');
      lines.push('Token ' + formatRupiah(data.token.nominal) + ' setara ±' + formatNumber(data.token.kwh, 2) + ' kWh, cukup untuk sekitar ' + formatNumber(data.token.hari, 1) + ' hari pemakaian.');
      lines.push('');
    }

    lines.push('Rincian per peralatan:');
    if (Array.isArray(data.rincian)) {
      data.rincian.forEach(function (item, idx) {
        lines.push((idx + 1) + '. ' + item.nama + ': ' + formatNumber(item.watt) + ' W · ' + formatNumber(item.jam, 1) + ' jam/hari · ' + item.jumlah + ' unit');
        lines.push('   -> ' + formatKwh(item.kwh_bulan, 2) + ' / bln · ' + formatRupiah(item.rupiah_bulan) + ' / bln (' + formatPersen(item.persen) + ')');
      });
    }
    lines.push('');
    lines.push('Catatan:');
    lines.push(data.catatan || 'Hitungan memakai 30 hari per bulan dan tarif yang kamu masukkan. Ini perkiraan, bukan tagihan resmi.');
    return lines.join('\n');
  }

  function renderResult(data) {
    state.lastResult = data;

    if (el.heroTotal) {
      el.heroTotal.textContent = formatRupiah(data.rupiah_bulan);
    }
    if (el.statKwhBulan) {
      el.statKwhBulan.textContent = formatKwh(data.kwh_bulan, 1);
    }
    if (el.statRpHari) {
      el.statRpHari.textContent = formatRupiah(data.rupiah_hari);
    }
    if (el.statRpTahun) {
      el.statRpTahun.textContent = formatRupiah(data.rupiah_tahun);
    }

    if (el.terbesar) {
      if (data.terbesar) {
        el.terbesar.hidden = false;
        el.terbesar.innerHTML = 'Pemakaian listrik terbesar adalah <strong>' +
          escapeHtml(data.terbesar.nama) + '</strong> dengan <strong>' +
          formatRupiah(data.terbesar.rupiah_bulan) + '/bulan</strong> (' +
          formatPersen(data.terbesar.persen) + ' dari seluruh tagihan).';
      } else {
        el.terbesar.hidden = true;
      }
    }

    if (el.tokenInfo) {
      if (data.token) {
        el.tokenInfo.hidden = false;
        el.tokenInfo.textContent = 'Token ' + formatRupiah(data.token.nominal) +
          ' setara ±' + formatNumber(data.token.kwh, 0) + ' kWh, cukup untuk sekitar ' +
          formatNumber(data.token.hari, 1) + ' hari.';
      } else {
        el.tokenInfo.hidden = true;
      }
    }

    if (el.tableBody) {
      el.tableBody.innerHTML = '';
      if (Array.isArray(data.rincian)) {
        data.rincian.forEach(function (item) {
          var tr = document.createElement('tr');

          var tdNama = document.createElement('td');
          tdNama.className = 'tagihan__td-nama';
          tdNama.textContent = item.nama;

          var tdDaya = document.createElement('td');
          tdDaya.className = 'text-right tagihan__td-daya';
          var durasiStr = formatNumber(item.jam, item.jam % 1 === 0 ? 0 : 1) + 'j';
          var unitStr = item.jumlah > 1 ? (' × ' + item.jumlah) : '';
          tdDaya.textContent = formatNumber(item.watt) + 'W · ' + durasiStr + unitStr;

          var tdKwh = document.createElement('td');
          tdKwh.className = 'text-right tagihan__td-kwh';
          tdKwh.textContent = formatNumber(item.kwh_bulan, 2);

          var tdRp = document.createElement('td');
          tdRp.className = 'text-right tagihan__td-rp';
          tdRp.textContent = formatRupiah(item.rupiah_bulan);

          var tdPorsi = document.createElement('td');
          tdPorsi.className = 'text-right tagihan__td-porsi';
          var barWrap = document.createElement('div');
          barWrap.className = 'tagihan__porsi-cell';
          var barTrack = document.createElement('div');
          barTrack.className = 'tagihan__bar-track';
          var barFill = document.createElement('div');
          barFill.className = 'tagihan__bar-fill';
          barFill.style.width = Math.min(100, Math.max(0, item.persen)) + '%';
          barTrack.appendChild(barFill);
          var pctText = document.createElement('span');
          pctText.className = 'tagihan__bar-pct';
          pctText.textContent = formatPersen(item.persen);
          barWrap.appendChild(barTrack);
          barWrap.appendChild(pctText);
          tdPorsi.appendChild(barWrap);

          tr.appendChild(tdNama);
          tr.appendChild(tdDaya);
          tr.appendChild(tdKwh);
          tr.appendChild(tdRp);
          tr.appendChild(tdPorsi);

          el.tableBody.appendChild(tr);
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

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function submitTagihan() {
    if (state.busy) return;

    var items = getItemsData();
    if (items.length === 0) {
      setStatus('Isi minimal satu peralatan listrik dulu.', 'error');
      if (el.items) {
        var firstInput = el.items.querySelector('input');
        if (firstInput) firstInput.focus();
      }
      return;
    }

    // Pastikan setiap item yang dikirim punya watt dan jam
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      if (!item.watt) {
        setStatus('Isi daya (watt) untuk "' + item.nama + '".', 'error');
        return;
      }
      if (item.jam === '') {
        setStatus('Isi jam pemakaian per hari untuk "' + item.nama + '".', 'error');
        return;
      }
    }

    var tarifVal = el.tarif ? el.tarif.value.trim() : '';
    var golVal = el.golongan ? el.golongan.value : '1300';
    if (!tarifVal && golVal === 'sendiri') {
      setStatus('Isi tarif per kWh dulu, atau pilih golongan tarif.', 'error');
      if (el.tarif) el.tarif.focus();
      return;
    }

    var tokenVal = el.token ? el.token.value.trim() : '';

    var form = new FormData();
    form.append('alat', JSON.stringify(items));
    form.append('golongan', golVal);
    if (tarifVal) form.append('tarif', tarifVal);
    if (tokenVal) form.append('token', tokenVal);

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung perkiraan tagihan listrik...', 'busy');

    if (window.AbortController) {
      state.abortController = new AbortController();
    }

    fetch(serverBase + '/api/tagihan-listrik', {
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
        setStatus('Tagihan listrik berhasil diperkirakan.', 'ok');
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
      setStatus('Ringkasan tagihan listrik berhasil disalin ke papan klip.', 'ok');
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
    a.download = 'tagihan-listrik.txt';
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
    if (el.items) {
      el.items.innerHTML = '';
      // Mulai dengan 2 baris kosong
      addItem('', '', '', '1');
      addItem('', '', '', '1');
    }
    if (el.golongan) {
      el.golongan.value = '1300';
    }
    onGolonganChange();
    if (el.token) el.token.value = '';
    if (el.result) el.result.hidden = true;
    state.lastResult = null;
    state.busy = false;
    setStatus('Isi daftar peralatan listrik dan tarif, lalu tekan "Hitung tagihan".', '');
    updateCountBadge();
    updateControls();
    if (el.items) {
      var firstInput = el.items.querySelector('input');
      if (firstInput) firstInput.focus();
    }
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="tagihan-listrik"]');
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
      if (el.items) {
        var firstInput = el.items.querySelector('input');
        if (firstInput) firstInput.focus();
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
        submitTagihan();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.addItem) {
    el.addItem.addEventListener('click', function () {
      var row = addItem('', '', '', '1');
      if (row) {
        var inp = row.querySelector('.tagihan__input--nama');
        if (inp) inp.focus();
      }
    });
  }

  if (el.golongan) {
    el.golongan.addEventListener('change', onGolonganChange);
  }
  if (el.tarif) {
    el.tarif.addEventListener('input', updateControls);
    el.tarif.addEventListener('change', updateControls);
  }
  if (el.token) {
    el.token.addEventListener('input', updateControls);
    el.token.addEventListener('change', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitTagihan);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['tagihan-listrik'] = toggle;

  // Inisialisasi awal 2 baris kosong
  if (el.items && el.items.children.length === 0) {
    addItem('', '', '', '1');
    addItem('', '', '', '1');
  }
  applyLimits(FALLBACK_LIMITS);
  updateCountBadge();
  updateControls();
})();
