/* =========================================================================
   Panel alat: Rencana bebas utang (utang)
   Simulasi pelunasan utang sekaligus dengan strategi bunga tertinggi (avalanche)
   atau saldo terkecil (snowball), termasuk efek pengalihan cicilan lunas.
   Semua data diproses di memori server dan tidak disimpan ke disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('utang-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('utang-close'),
    dana: document.getElementById('utang-dana'),
    rowsContainer: document.getElementById('utang-rows'),
    addRowBtn: document.getElementById('utang-add-row'),
    status: document.getElementById('utang-status'),
    clear: document.getElementById('utang-clear'),
    submit: document.getElementById('utang-submit'),
    result: document.getElementById('utang-result'),
    heroBulan: document.getElementById('utang-hero-bulan'),
    heroDurasi: document.getElementById('utang-hero-durasi'),
    statBunga: document.getElementById('utang-stat-bunga'),
    statTotal: document.getElementById('utang-stat-total'),
    statDana: document.getElementById('utang-stat-dana'),
    tableBody: document.getElementById('utang-table-body'),
    comparison: document.getElementById('utang-comparison'),
    comparisonText: document.getElementById('utang-comparison-text'),
    warnings: document.getElementById('utang-warnings'),
    warningsList: document.getElementById('utang-warnings-list'),
    copy: document.getElementById('utang-copy')
  };

  var FALLBACK_LIMITS = {
    maks_utang: 8,
    batas: {
      sisa: { min: 1000, max: 1000000000000 },
      bunga: { min: 0, max: 100 },
      minimum: { min: 1000 },
      dana_bulanan: { min: 1000 },
      maks_bulan: 600,
      nama_max_length: 40
    },
    strategi: [
      { nilai: 'bunga', label: 'Bunga tertinggi dulu' },
      { nilai: 'saldo', label: 'Saldo terkecil dulu' }
    ],
    contoh: {
      dana_bulanan: 2500000,
      strategi: 'bunga',
      utang: [
        { nama: 'Kartu kredit', sisa: 12000000, bunga: 24, minimum: 600000 },
        { nama: 'Paylater', sisa: 3500000, bunga: 36, minimum: 350000 },
        { nama: 'Pinjaman bank', sisa: 25000000, bunga: 14, minimum: 900000 }
      ]
    }
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
    abortController: null,
    rowCounter: 0
  };

  function formatNumber(num) {
    var n = Math.round(Number(num) || 0);
    return new Intl.NumberFormat('id-ID').format(n);
  }

  function formatRp(num) {
    return 'Rp ' + formatNumber(num);
  }

  function parseRupiahInput(str) {
    if (!str) return 0;
    var cleaned = String(str).replace(/[^\d]/g, '');
    return cleaned ? Number(cleaned) : 0;
  }

  function parseBungaInput(str) {
    if (!str) return 0;
    var cleaned = String(str).replace('%', '').trim().replace(',', '.').replace(/[^\d.]/g, '');
    return cleaned ? parseFloat(cleaned) || 0 : 0;
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
    var span = document.createElement('span');
    span.textContent = message || '';
    el.status.appendChild(span);
  }

  function createRowElement(data) {
    state.rowCounter += 1;
    var rowId = state.rowCounter;
    var item = data || {};

    var row = document.createElement('div');
    row.className = 'utang__row';
    row.setAttribute('data-row-id', String(rowId));

    var grid = document.createElement('div');
    grid.className = 'utang__row-grid';

    // 1. Nama
    var colNama = document.createElement('div');
    colNama.className = 'field utang__col-nama';
    var lblNama = document.createElement('label');
    lblNama.setAttribute('for', 'utang-nama-' + rowId);
    lblNama.textContent = 'Nama utang / pinjaman';
    var inpNama = document.createElement('input');
    inpNama.type = 'text';
    inpNama.id = 'utang-nama-' + rowId;
    inpNama.className = 'utang__input utang__input-nama';
    inpNama.maxLength = 40;
    inpNama.placeholder = 'Mis. Kartu kredit ' + rowId;
    inpNama.value = item.nama || '';
    inpNama.autocomplete = 'off';
    colNama.appendChild(lblNama);
    colNama.appendChild(inpNama);

    // 2. Sisa Utang
    var colSisa = document.createElement('div');
    colSisa.className = 'field utang__col-sisa';
    var lblSisa = document.createElement('label');
    lblSisa.setAttribute('for', 'utang-sisa-' + rowId);
    lblSisa.textContent = 'Sisa utang (Rp)';
    var inpSisa = document.createElement('input');
    inpSisa.type = 'text';
    inpSisa.id = 'utang-sisa-' + rowId;
    inpSisa.className = 'utang__input utang__input-sisa';
    inpSisa.inputMode = 'numeric';
    inpSisa.placeholder = 'Mis. 10.000.000';
    inpSisa.value = item.sisa ? formatNumber(item.sisa) : '';
    inpSisa.autocomplete = 'off';
    inpSisa.addEventListener('blur', function () {
      var val = parseRupiahInput(this.value);
      if (val > 0) this.value = formatNumber(val);
    });
    colSisa.appendChild(lblSisa);
    colSisa.appendChild(inpSisa);

    // 3. Bunga per tahun
    var colBunga = document.createElement('div');
    colBunga.className = 'field utang__col-bunga';
    var lblBunga = document.createElement('label');
    lblBunga.setAttribute('for', 'utang-bunga-' + rowId);
    lblBunga.textContent = 'Bunga per tahun (%)';
    var inpBunga = document.createElement('input');
    inpBunga.type = 'text';
    inpBunga.id = 'utang-bunga-' + rowId;
    inpBunga.className = 'utang__input utang__input-bunga';
    inpBunga.inputMode = 'decimal';
    inpBunga.placeholder = 'Mis. 24';
    inpBunga.value = typeof item.bunga === 'number' ? String(item.bunga) : (item.bunga || '');
    inpBunga.autocomplete = 'off';
    colBunga.appendChild(lblBunga);
    colBunga.appendChild(inpBunga);

    // 4. Cicilan minimum
    var colMin = document.createElement('div');
    colMin.className = 'field utang__col-min';
    var lblMin = document.createElement('label');
    lblMin.setAttribute('for', 'utang-min-' + rowId);
    lblMin.textContent = 'Cicilan minimum (Rp)';
    var inpMin = document.createElement('input');
    inpMin.type = 'text';
    inpMin.id = 'utang-min-' + rowId;
    inpMin.className = 'utang__input utang__input-min';
    inpMin.inputMode = 'numeric';
    inpMin.placeholder = 'Mis. 500.000';
    inpMin.value = item.minimum ? formatNumber(item.minimum) : '';
    inpMin.autocomplete = 'off';
    inpMin.addEventListener('blur', function () {
      var val = parseRupiahInput(this.value);
      if (val > 0) this.value = formatNumber(val);
    });
    colMin.appendChild(lblMin);
    colMin.appendChild(inpMin);

    // 5. Tombol Hapus
    var colAction = document.createElement('div');
    colAction.className = 'utang__col-action';
    var btnHapus = document.createElement('button');
    btnHapus.type = 'button';
    btnHapus.className = 'btn btn--ghost utang__btn-delete';
    btnHapus.setAttribute('aria-label', 'Hapus utang ini');
    btnHapus.innerHTML = '<span aria-hidden="true">&times;</span> Hapus';
    btnHapus.addEventListener('click', function () {
      var allRows = el.rowsContainer.querySelectorAll('.utang__row');
      if (allRows.length <= 1) {
        setStatus('Minimal harus ada 1 utang dalam daftar.', 'warn');
        return;
      }
      row.remove();
      updateRowButtons();
    });
    colAction.appendChild(btnHapus);

    grid.appendChild(colNama);
    grid.appendChild(colSisa);
    grid.appendChild(colBunga);
    grid.appendChild(colMin);
    grid.appendChild(colAction);
    row.appendChild(grid);

    return row;
  }

  function updateRowButtons() {
    var allRows = el.rowsContainer.querySelectorAll('.utang__row');
    var maxUtang = (state.limits && state.limits.maks_utang) || 8;
    if (el.addRowBtn) {
      el.addRowBtn.disabled = allRows.length >= maxUtang;
    }
  }

  function addRow(data) {
    var allRows = el.rowsContainer.querySelectorAll('.utang__row');
    var maxUtang = (state.limits && state.limits.maks_utang) || 8;
    if (allRows.length >= maxUtang) {
      setStatus('Maksimal ' + maxUtang + ' utang sekali hitung.', 'warn');
      return;
    }
    var rowEl = createRowElement(data);
    el.rowsContainer.appendChild(rowEl);
    updateRowButtons();
  }

  function populateDefaultRows(contoh) {
    if (!el.rowsContainer) return;
    el.rowsContainer.innerHTML = '';
    var list = (contoh && contoh.utang) || FALLBACK_LIMITS.contoh.utang;
    list.forEach(function (u) {
      addRow(u);
    });
    if (el.dana) {
      var d = (contoh && contoh.dana_bulanan) || FALLBACK_LIMITS.contoh.dana_bulanan;
      el.dana.value = formatNumber(d);
    }
    var strat = (contoh && contoh.strategi) || 'bunga';
    var radio = panel.querySelector('input[name="utang-strategi"][value="' + strat + '"]');
    if (radio) radio.checked = true;
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/utang/limits', {
      headers: { Accept: 'application/json' }
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (data && data.ok && data.data) {
          state.limits = data.data;
          state.limitsLoaded = true;
        }
      })
      .catch(function () {
        // Abaikan galat jaringan, gunakan batas bawaan
      });
  }

  function getSelectedStrategi() {
    var checked = panel.querySelector('input[name="utang-strategi"]:checked');
    return checked ? checked.value : 'bunga';
  }

  function getFormData() {
    var danaVal = parseRupiahInput(el.dana ? el.dana.value : '');
    var strat = getSelectedStrategi();
    var rows = el.rowsContainer.querySelectorAll('.utang__row');
    var utangList = [];

    rows.forEach(function (r, idx) {
      var inpNama = r.querySelector('.utang__input-nama');
      var inpSisa = r.querySelector('.utang__input-sisa');
      var inpBunga = r.querySelector('.utang__input-bunga');
      var inpMin = r.querySelector('.utang__input-min');

      var nama = inpNama ? inpNama.value.trim() : '';
      var sisa = inpSisa ? parseRupiahInput(inpSisa.value) : 0;
      var bunga = inpBunga ? parseBungaInput(inpBunga.value) : 0;
      var minimum = inpMin ? parseRupiahInput(inpMin.value) : 0;

      utangList.push({
        nama: nama || ('Utang ' + (idx + 1)),
        sisa: sisa,
        bunga: bunga,
        minimum: minimum
      });
    });

    return {
      dana_bulanan: danaVal,
      strategi: strat,
      utang: utangList
    };
  }

  function renderResult(data) {
    if (!el.result || !data) return;
    state.lastResult = data;

    var ringkasan = data.ringkasan || {};
    var perUtang = data.per_utang || [];
    var perbandingan = data.perbandingan;
    var peringatan = data.peringatan || [];

    // Hero
    if (el.heroBulan) {
      el.heroBulan.textContent = 'Bebas utang dalam ' + ringkasan.bulan + ' bulan';
    }
    if (el.heroDurasi) {
      var thn = ringkasan.tahun || 0;
      var bln = ringkasan.sisa_bulan || 0;
      var durasiStr = '';
      if (thn > 0 && bln > 0) {
        durasiStr = 'sekitar ' + thn + ' tahun ' + bln + ' bulan';
      } else if (thn > 0) {
        durasiStr = 'sekitar ' + thn + ' tahun';
      } else {
        durasiStr = 'sekitar ' + bln + ' bulan';
      }
      el.heroDurasi.textContent = durasiStr;
    }

    // Stats
    if (el.statBunga) el.statBunga.textContent = formatRp(ringkasan.total_bunga);
    if (el.statTotal) el.statTotal.textContent = formatRp(ringkasan.total_dibayar);
    if (el.statDana) el.statDana.textContent = formatRp(ringkasan.dana_bulanan) + ' / bulan';

    // Table
    if (el.tableBody) {
      el.tableBody.innerHTML = '';
      perUtang.forEach(function (u) {
        var tr = document.createElement('tr');

        var tdNama = document.createElement('td');
        tdNama.textContent = u.nama;

        var tdSisa = document.createElement('td');
        tdSisa.className = 'text-right';
        tdSisa.textContent = formatRp(u.sisa_awal);

        var tdBunga = document.createElement('td');
        tdBunga.className = 'text-right';
        tdBunga.textContent = formatRp(u.bunga_total);

        var tdTotal = document.createElement('td');
        tdTotal.className = 'text-right';
        tdTotal.textContent = formatRp(u.total_dibayar);

        var tdLunas = document.createElement('td');
        tdLunas.className = 'text-center';
        var badge = document.createElement('span');
        badge.className = 'utang__badge-lunas';
        badge.textContent = 'Bulan ke-' + u.lunas_bulan;
        tdLunas.appendChild(badge);

        tr.appendChild(tdNama);
        tr.appendChild(tdSisa);
        tr.appendChild(tdBunga);
        tr.appendChild(tdTotal);
        tr.appendChild(tdLunas);
        el.tableBody.appendChild(tr);
      });
    }

    // Perbandingan strategi
    if (el.comparison && el.comparisonText) {
      if (perbandingan) {
        var compLabel = perbandingan.strategi_label || (perbandingan.strategi === 'saldo' ? 'Saldo terkecil dulu' : 'Bunga tertinggi dulu');
        var myLabel = ringkasan.strategi_label || (ringkasan.strategi === 'saldo' ? 'Saldo terkecil dulu' : 'Bunga tertinggi dulu');
        var text = 'Dengan strategi ' + compLabel.toLowerCase() + ', utang lunas dalam ' +
          perbandingan.bulan + ' bulan dengan total bunga ' + formatRp(perbandingan.total_bunga) + '. ';

        if (perbandingan.lebih_hemat === ringkasan.strategi) {
          text += 'Strategi yang kamu pilih (' + myLabel + ') menghemat bunga sebesar ' + formatRp(perbandingan.selisih_bunga) + '!';
        } else if (perbandingan.lebih_hemat === perbandingan.strategi) {
          text += 'Strategi ' + compLabel.toLowerCase() + ' lebih hemat bunga sebesar ' + formatRp(perbandingan.selisih_bunga) + '.';
        } else {
          text += 'Kedua strategi menghasilkan total beban bunga yang sama.';
        }
        el.comparisonText.textContent = text;
        el.comparison.hidden = false;
      } else {
        var otherStratName = ringkasan.strategi === 'bunga' ? 'saldo terkecil dulu' : 'bunga tertinggi dulu';
        el.comparisonText.textContent = 'Dengan strategi ' + otherStratName + ', utang belum lunas dalam 50 tahun (600 bulan).';
        el.comparison.hidden = false;
      }
    }

    // Peringatan
    if (el.warnings && el.warningsList) {
      el.warningsList.innerHTML = '';
      if (peringatan && peringatan.length > 0) {
        peringatan.forEach(function (p) {
          var li = document.createElement('li');
          li.textContent = p;
          el.warningsList.appendChild(li);
        });
        el.warnings.hidden = false;
      } else {
        el.warnings.hidden = true;
      }
    }

    el.result.hidden = false;
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.result.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest' });
  }

  function submitUtang() {
    if (state.busy) return;

    var data = getFormData();

    // Validasi awal di peramban
    if (!data.utang || data.utang.length === 0) {
      setStatus('Daftar utang belum diisi.', 'error');
      return;
    }
    for (var i = 0; i < data.utang.length; i++) {
      var item = data.utang[i];
      if (!item.sisa || item.sisa < 1000) {
        setStatus('Sisa utang "' + item.nama + '" harus berupa angka minimal Rp 1.000.', 'error');
        return;
      }
      if (item.bunga < 0 || item.bunga > 100) {
        setStatus('Suku bunga "' + item.nama + '" harus antara 0% sampai 100%.', 'error');
        return;
      }
      if (!item.minimum || item.minimum < 1000) {
        setStatus('Cicilan minimum "' + item.nama + '" harus berupa angka minimal Rp 1.000.', 'error');
        return;
      }
    }

    if (!data.dana_bulanan || data.dana_bulanan < 1000) {
      setStatus('Dana bulanan harus diisi minimal Rp 1.000.', 'error');
      return;
    }

    var totalMin = data.utang.reduce(function (acc, u) { return acc + (u.minimum || 0); }, 0);
    if (data.dana_bulanan < totalMin) {
      setStatus('Dana bulanan (' + formatRp(data.dana_bulanan) + ') kurang dari total cicilan minimum (' + formatRp(totalMin) + ').', 'error');
      return;
    }

    state.busy = true;
    if (el.submit) el.submit.disabled = true;
    setStatus('Menghitung rencana pelunasan...', 'busy');

    if (state.abortController) {
      state.abortController.abort();
    }
    state.abortController = new AbortController();

    fetch(serverBase + '/api/utang', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify(data),
      signal: state.abortController.signal
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { status: res.status, ok: res.ok, body: body };
        });
      })
      .then(function (resp) {
        state.busy = false;
        if (el.submit) el.submit.disabled = false;

        if (resp.ok && resp.body && resp.body.ok && resp.body.data) {
          setStatus('Rencana pelunasan berhasil dihitung.', 'success');
          renderResult(resp.body.data);
        } else {
          var errObj = resp.body || {};
          var msg = errObj.pesan ||
            (errObj.error && errObj.error.message) ||
            (errObj.detail && errObj.detail.message) ||
            'Gagal menghitung rencana pelunasan.';
          setStatus(msg, 'error');
        }
      })
      .catch(function (err) {
        state.busy = false;
        if (el.submit) el.submit.disabled = false;
        if (err && err.name === 'AbortError') return;
        setStatus('Terjadi kendala jaringan saat menghubungi server. Silakan coba lagi.', 'error');
      });
  }

  function resetAll() {
    if (el.result) el.result.hidden = true;
    state.lastResult = null;
    if (el.dana) el.dana.value = '';
    populateDefaultRows(FALLBACK_LIMITS.contoh);
    setStatus('Formulir telah dikosongkan ke contoh awal. Masukkan utangmu lalu tekan "Hitung rencana".', '');
  }

  function copyResult() {
    if (!state.lastResult) return;
    var res = state.lastResult;
    var r = res.ringkasan || {};
    var per = res.per_utang || [];
    var comp = res.perbandingan;

    var lines = [
      'Rencana Bebas Utang — OmniTools (bahzi.fun)',
      '----------------------------------------',
      'Target: Bebas utang dalam ' + r.bulan + ' bulan (' + (r.tahun > 0 ? r.tahun + ' tahun ' : '') + r.sisa_bulan + ' bulan)',
      'Strategi: ' + r.strategi_label,
      'Dana per bulan: ' + formatRp(r.dana_bulanan),
      'Total utang pokok: ' + formatRp(r.total_utang),
      'Total bunga terbayar: ' + formatRp(r.total_bunga),
      'Total yang dibayarkan: ' + formatRp(r.total_dibayar),
      '',
      'Urutan pelunasan:'
    ];

    per.forEach(function (u, i) {
      lines.push((i + 1) + '. ' + u.nama + ' — Lunas bulan ke-' + u.lunas_bulan +
        ' (Pokok: ' + formatRp(u.sisa_awal) + ', Bunga: ' + formatRp(u.bunga_total) + ', Total: ' + formatRp(u.total_dibayar) + ')');
    });

    if (comp) {
      lines.push('');
      lines.push('Perbandingan:');
      lines.push('- Strategi ' + comp.strategi_label.toLowerCase() + ': lunas ' + comp.bulan + ' bulan, bunga ' + formatRp(comp.total_bunga));
    }

    var text = lines.join('\n');

    function notifyCopied() {
      if (!el.copy) return;
      var originalText = el.copy.textContent;
      el.copy.textContent = 'Tersalin!';
      el.copy.disabled = true;
      setTimeout(function () {
        if (el.copy) {
          el.copy.textContent = originalText;
          el.copy.disabled = false;
        }
      }, 2500);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(notifyCopied).catch(function () {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }

    function fallbackCopy(str) {
      var ta = document.createElement('textarea');
      ta.value = str;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.top = '-9999px';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        document.execCommand('copy');
        notifyCopied();
      } catch (e) {
        setStatus('Gagal menyalin teks ke papan klip.', 'error');
      }
      document.body.removeChild(ta);
    }
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="utang"]');
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
      if (el.dana) el.dana.focus();
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
        submitUtang();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.addRowBtn) {
    el.addRowBtn.addEventListener('click', function () {
      addRow({ nama: '', sisa: 0, bunga: 0, minimum: 0 });
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitUtang);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);

  if (el.dana) {
    el.dana.addEventListener('blur', function () {
      var val = parseRupiahInput(this.value);
      if (val > 0) this.value = formatNumber(val);
    });
  }

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels.utang = toggle;

  // Inisialisasi formulir awal
  populateDefaultRows(FALLBACK_LIMITS.contoh);
})();
