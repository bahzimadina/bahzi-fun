/* =========================================================================
   Panel alat: Konverter satuan (Unit Converter)
   Nilai dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada nilai yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('unit-convert-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('unit-convert-close'),
    limits: document.getElementById('unit-convert-limits'),
    note: document.getElementById('unit-convert-note'),
    category: document.getElementById('unit-convert-category'),
    input: document.getElementById('unit-convert-input'),
    from: document.getElementById('unit-convert-from'),
    to: document.getElementById('unit-convert-to'),
    swap: document.getElementById('unit-convert-swap'),
    status: document.getElementById('unit-convert-status'),
    clear: document.getElementById('unit-convert-clear'),
    submit: document.getElementById('unit-convert-submit'),
    results: document.getElementById('unit-convert-results'),
    hint: document.getElementById('unit-convert-hint'),
    outputWrap: document.getElementById('unit-convert-output-wrap'),
    resultValue: document.getElementById('unit-convert-result-value'),
    resultSymbol: document.getElementById('unit-convert-result-symbol'),
    rate: document.getElementById('unit-convert-rate'),
    noteExtra: document.getElementById('unit-convert-note-extra'),
    table: document.getElementById('unit-convert-table'),
    copy: document.getElementById('unit-convert-copy'),
    download: document.getElementById('unit-convert-download')
  };

  var FALLBACK_CATEGORIES = [
    {
      id: 'panjang',
      nama: 'Panjang',
      units: [
        { value: 'mm', kode: 'mm', label: 'Milimeter', simbol: 'mm' },
        { value: 'cm', kode: 'cm', label: 'Sentimeter', simbol: 'cm' },
        { value: 'm', kode: 'm', label: 'Meter', simbol: 'm' },
        { value: 'km', kode: 'km', label: 'Kilometer', simbol: 'km' },
        { value: 'inci', kode: 'inci', label: 'Inci', simbol: 'in' },
        { value: 'kaki', kode: 'kaki', label: 'Kaki', simbol: 'ft' },
        { value: 'yard', kode: 'yard', label: 'Yard', simbol: 'yd' },
        { value: 'mil', kode: 'mil', label: 'Mil', simbol: 'mil' }
      ]
    },
    {
      id: 'massa',
      nama: 'Berat',
      units: [
        { value: 'mg', kode: 'mg', label: 'Miligram', simbol: 'mg' },
        { value: 'g', kode: 'g', label: 'Gram', simbol: 'g' },
        { value: 'kg', kode: 'kg', label: 'Kilogram', simbol: 'kg' },
        { value: 'ton', kode: 'ton', label: 'Ton', simbol: 'ton' },
        { value: 'pon', kode: 'pon', label: 'Pon', simbol: 'pon' },
        { value: 'ons', kode: 'ons', label: 'Ons', simbol: 'ons' }
      ]
    },
    {
      id: 'suhu',
      nama: 'Suhu',
      units: [
        { value: 'celsius', kode: 'celsius', label: 'Celsius', simbol: '°C' },
        { value: 'fahrenheit', kode: 'fahrenheit', label: 'Fahrenheit', simbol: '°F' },
        { value: 'kelvin', kode: 'kelvin', label: 'Kelvin', simbol: 'K' },
        { value: 'reamur', kode: 'reamur', label: 'Reamur', simbol: '°R' }
      ]
    },
    {
      id: 'luas',
      nama: 'Luas',
      units: [
        { value: 'cm2', kode: 'cm2', label: 'Sentimeter persegi', simbol: 'cm²' },
        { value: 'm2', kode: 'm2', label: 'Meter persegi', simbol: 'm²' },
        { value: 'are', kode: 'are', label: 'Are', simbol: 'are' },
        { value: 'hektar', kode: 'hektar', label: 'Hektar', simbol: 'ha' },
        { value: 'km2', kode: 'km2', label: 'Kilometer persegi', simbol: 'km²' },
        { value: 'kaki2', kode: 'kaki2', label: 'Kaki persegi', simbol: 'ft²' },
        { value: 'acre', kode: 'acre', label: 'Acre', simbol: 'acre' }
      ]
    },
    {
      id: 'volume',
      nama: 'Volume',
      units: [
        { value: 'ml', kode: 'ml', label: 'Mililiter', simbol: 'ml' },
        { value: 'l', kode: 'l', label: 'Liter', simbol: 'l' },
        { value: 'm3', kode: 'm3', label: 'Meter kubik', simbol: 'm³' },
        { value: 'cm3', kode: 'cm3', label: 'Sentimeter kubik', simbol: 'cm³' },
        { value: 'galon', kode: 'galon', label: 'Galon (AS)', simbol: 'gal' },
        { value: 'cup', kode: 'cup', label: 'Cangkir (AS)', simbol: 'cup' }
      ]
    },
    {
      id: 'kecepatan',
      nama: 'Kecepatan',
      units: [
        { value: 'ms', kode: 'ms', label: 'Meter per detik', simbol: 'm/s' },
        { value: 'kmjam', kode: 'kmjam', label: 'Kilometer per jam', simbol: 'km/jam' },
        { value: 'mph', kode: 'mph', label: 'Mil per jam', simbol: 'mph' },
        { value: 'knot', kode: 'knot', label: 'Knot', simbol: 'knot' }
      ]
    },
    {
      id: 'waktu',
      nama: 'Waktu',
      units: [
        { value: 'detik', kode: 'detik', label: 'Detik', simbol: 'detik' },
        { value: 'menit', kode: 'menit', label: 'Menit', simbol: 'menit' },
        { value: 'jam', kode: 'jam', label: 'Jam', simbol: 'jam' },
        { value: 'hari', kode: 'hari', label: 'Hari', simbol: 'hari' },
        { value: 'minggu', kode: 'minggu', label: 'Minggu', simbol: 'minggu' },
        { value: 'bulan', kode: 'bulan', label: 'Bulan (30 hari)', simbol: 'bulan' },
        { value: 'tahun', kode: 'tahun', label: 'Tahun (365 hari)', simbol: 'tahun' }
      ]
    },
    {
      id: 'data',
      nama: 'Data',
      units: [
        { value: 'byte', kode: 'byte', label: 'Byte', simbol: 'B' },
        { value: 'kb', kode: 'kb', label: 'Kilobyte', simbol: 'KB' },
        { value: 'mb', kode: 'mb', label: 'Megabyte', simbol: 'MB' },
        { value: 'gb', kode: 'gb', label: 'Gigabyte', simbol: 'GB' },
        { value: 'tb', kode: 'tb', label: 'Terabyte', simbol: 'TB' },
        { value: 'kib', kode: 'kib', label: 'Kibibyte', simbol: 'KiB' },
        { value: 'mib', kode: 'mib', label: 'Mebibyte', simbol: 'MiB' },
        { value: 'gib', kode: 'gib', label: 'Gibibyte', simbol: 'GiB' },
        { value: 'tib', kode: 'tib', label: 'Tebibyte', simbol: 'TiB' }
      ]
    }
  ];

  var state = {
    categories: FALLBACK_CATEGORIES,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    downloadUrl: null
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

  function getCategoryData(catId) {
    for (var i = 0; i < state.categories.length; i++) {
      if (state.categories[i].id === catId) {
        return state.categories[i];
      }
    }
    return state.categories[0] || null;
  }

  function populateUnitDropdowns(defaultFrom, defaultTo) {
    if (!el.category || !el.from || !el.to) return;
    var catId = el.category.value;
    var catData = getCategoryData(catId);
    if (!catData || !catData.units) return;

    var prevFrom = defaultFrom || el.from.value;
    var prevTo = defaultTo || el.to.value;

    el.from.innerHTML = '';
    el.to.innerHTML = '';

    for (var i = 0; i < catData.units.length; i++) {
      var u = catData.units[i];
      var code = u.kode || u.value;
      var text = u.label + (u.simbol ? ' (' + u.simbol + ')' : '');

      var optFrom = document.createElement('option');
      optFrom.value = code;
      optFrom.textContent = text;
      el.from.appendChild(optFrom);

      var optTo = document.createElement('option');
      optTo.value = code;
      optTo.textContent = text;
      el.to.appendChild(optTo);
    }

    // Tentukan pilihan default
    var hasPrevFrom = false;
    var hasPrevTo = false;
    for (var j = 0; j < catData.units.length; j++) {
      var c = catData.units[j].kode || catData.units[j].value;
      if (c === prevFrom) hasPrevFrom = true;
      if (c === prevTo) hasPrevTo = true;
    }

    if (hasPrevFrom) {
      el.from.value = prevFrom;
    } else if (catData.units.length > 0) {
      el.from.value = catData.units[0].kode || catData.units[0].value;
    }

    if (hasPrevTo && prevTo !== el.from.value) {
      el.to.value = prevTo;
    } else if (catData.units.length > 1) {
      el.to.value = catData.units[1].kode || catData.units[1].value;
    } else if (catData.units.length > 0) {
      el.to.value = catData.units[0].kode || catData.units[0].value;
    }
  }

  function swapUnits() {
    if (!el.from || !el.to) return;
    var temp = el.from.value;
    el.from.value = el.to.value;
    el.to.value = temp;
    if (state.lastResult && el.input && el.input.value.trim().length > 0) {
      submitConvert();
    }
  }

  function resetResults() {
    if (el.hint) el.hint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.resultValue) el.resultValue.textContent = '';
    if (el.resultSymbol) el.resultSymbol.textContent = '';
    if (el.rate) el.rate.textContent = '';
    if (el.noteExtra) {
      el.noteExtra.hidden = true;
      el.noteExtra.textContent = '';
    }
    if (el.table) el.table.innerHTML = '';
    state.lastResult = null;
    revokeDownload();
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }
  }

  function updateControls() {
    var hasVal = !!(el.input && el.input.value.trim().length > 0);
    var hasOutput = !!(state.lastResult);
    if (el.submit) {
      el.submit.disabled = state.busy || !hasVal;
      el.submit.textContent = state.busy ? 'Mengonversi...' : 'Konversi';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasVal && !hasOutput);
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch('/api/unit-convert/limits', { headers: { credentials: 'same-origin', Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data && Array.isArray(data.categories) && data.categories.length > 0) {
          state.categories = data.categories;

          // Perbarui dropdown kategori bila perlu
          if (el.category) {
            var currentCat = el.category.value;
            el.category.innerHTML = '';
            for (var i = 0; i < data.categories.length; i++) {
              var c = data.categories[i];
              var opt = document.createElement('option');
              opt.value = c.id;
              opt.textContent = c.nama;
              if (c.id === currentCat) opt.selected = true;
              el.category.appendChild(opt);
            }
          }
        }
        state.limitsLoaded = true;

        if (data && data.defaults) {
          if (el.category && data.defaults.category) {
            el.category.value = data.defaults.category;
          }
          populateUnitDropdowns(data.defaults.from, data.defaults.to);
        } else {
          populateUnitDropdowns();
        }
      })
      .catch(function () {
        // Gunakan batas bawaan
        populateUnitDropdowns();
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.hint) el.hint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.resultValue) el.resultValue.textContent = data.hasil_teks;
    if (el.resultSymbol) el.resultSymbol.textContent = data.ke.simbol || data.ke.kode;

    if (el.rate) {
      var dariSimbol = (data.dari && (data.dari.simbol || data.dari.label)) || '';
      var keSimbol = (data.ke && (data.ke.simbol || data.ke.label)) || '';
      el.rate.textContent = '1 ' + dariSimbol + ' = ' + data.laju_teks + ' ' + keSimbol;
    }

    if (el.noteExtra) {
      if (data.catatan) {
        el.noteExtra.hidden = false;
        el.noteExtra.textContent = data.catatan;
      } else {
        el.noteExtra.hidden = true;
        el.noteExtra.textContent = '';
      }
    }

    // Render tabel semua satuan
    if (el.table && Array.isArray(data.semua)) {
      el.table.innerHTML = '';
      for (var i = 0; i < data.semua.length; i++) {
        var u = data.semua[i];
        var row = document.createElement('div');
        row.className = 'unit__table-row';
        if (u.kode === data.ke.kode) {
          row.classList.add('unit__table-row--highlight');
        }

        var labelCol = document.createElement('span');
        labelCol.className = 'unit__table-label';
        labelCol.textContent = u.label;

        var valCol = document.createElement('span');
        valCol.className = 'unit__table-value';
        valCol.textContent = u.teks + ' ' + (u.simbol || u.kode);

        row.appendChild(labelCol);
        row.appendChild(valCol);
        el.table.appendChild(row);
      }
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
      } catch (err) { /* diabaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan konverter satuan belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Nilai di luar jangkauan yang didukung (maksimum 10¹⁵).';
        } else {
          message = 'Terjadi kendala saat memproses konversi (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitConvert() {
    if (state.busy) return;

    var val = el.input ? el.input.value.trim() : '';
    if (!val) {
      setStatus('Masukkan angka yang ingin dikonversi.', 'error');
      if (el.input) el.input.focus();
      return;
    }

    var cat = el.category ? el.category.value : 'panjang';
    var fromU = el.from ? el.from.value : '';
    var toU = el.to ? el.to.value : '';

    if (!fromU || !toU) {
      setStatus('Pilih satuan asal dan satuan tujuan.', 'error');
      return;
    }

    var form = new FormData();
    form.append('value', val);
    form.append('category', cat);
    form.append('from', fromU);
    form.append('to', toU);

    state.busy = true;
    updateControls();
    setStatus('Sedang mengonversi...', 'busy');

    fetch('/api/unit-convert', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus('Konversi berhasil.', 'ok');
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
    var textToCopy = state.lastResult.hasil_teks + ' ' + (state.lastResult.ke.simbol || state.lastResult.ke.kode);

    function notify(ok) {
      if (!el.copy) return;
      var orig = el.copy.textContent;
      el.copy.textContent = ok ? 'Tersalin!' : 'Gagal salin';
      setTimeout(function () {
        el.copy.textContent = orig;
      }, 1500);
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
    if (!state.lastResult) return;
    var d = state.lastResult;
    var lines = [];
    lines.push('Konversi Satuan: ' + d.kategori.nama);
    lines.push('----------------------------------------');
    lines.push('Nilai asal  : ' + (el.input ? el.input.value.trim() : '') + ' ' + d.dari.label + ' (' + (d.dari.simbol || d.dari.kode) + ')');
    lines.push('Hasil       : ' + d.hasil_teks + ' ' + d.ke.label + ' (' + (d.ke.simbol || d.ke.kode) + ')');
    var dariSimbol = (d.dari && (d.dari.simbol || d.dari.label)) || '';
    var keSimbol = (d.ke && (d.ke.simbol || d.ke.label)) || '';
    lines.push('Perbandingan: 1 ' + dariSimbol + ' = ' + d.laju_teks + ' ' + keSimbol);
    if (d.catatan) {
      lines.push('Catatan     : ' + d.catatan);
    }
    lines.push('');
    lines.push('Semua Satuan (' + d.kategori.nama + '):');
    if (Array.isArray(d.semua)) {
      for (var i = 0; i < d.semua.length; i++) {
        var u = d.semua[i];
        lines.push('- ' + u.label + ': ' + u.teks + ' ' + (u.simbol || u.kode));
      }
    }
    lines.push('');
    lines.push('Nilai diproses di memori lalu dibuang, tidak disimpan.');

    var content = lines.join('\n');
    revokeDownload();
    var blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    state.downloadUrl = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = 'konversi-satuan-' + d.kategori.id + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function resetAll() {
    if (el.input) {
      el.input.value = '';
      el.input.focus();
    }
    resetResults();
    setStatus('Masukkan angka, pilih satuan asal dan tujuan, lalu tekan "Konversi".', '');
    updateControls();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="unit-converter"], [data-tool-action="unit-convert"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'unit-convert-panel');
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

    if (el.input) {
      setTimeout(function () { el.input.focus(); }, 100);
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

  if (el.category) {
    el.category.addEventListener('change', function () {
      populateUnitDropdowns();
      if (state.lastResult && el.input && el.input.value.trim().length > 0) {
        submitConvert();
      } else {
        resetResults();
      }
    });
  }

  if (el.swap) el.swap.addEventListener('click', swapUnits);
  if (el.from) el.from.addEventListener('change', function () {
    if (state.lastResult && el.input && el.input.value.trim().length > 0) submitConvert();
  });
  if (el.to) el.to.addEventListener('change', function () {
    if (state.lastResult && el.input && el.input.value.trim().length > 0) submitConvert();
  });

  if (el.input) {
    el.input.addEventListener('input', updateControls);
    el.input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (el.input.value.trim().length > 0) {
          submitConvert();
        }
      }
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitConvert);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  function onKeydown(event) {
    if (panel.hidden) return;
    if (event.key === 'Escape' && panel.contains(document.activeElement)) {
      event.preventDefault();
      close();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      if (panel.contains(document.activeElement)) { event.preventDefault(); submitConvert(); }
    }
  }
  document.addEventListener('keydown', onKeydown);

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel supaya kartu Unit Converter bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['unit-converter'] = toggle;
  window.OmniToolsPanels['unit-convert'] = toggle;

  // Inisialisasi bawaan
  populateUnitDropdowns();
  updateControls();
})();
