/* =========================================================================
   Panel alat: Berat volumetrik paket (volumetrik)
   Hitung berat yang dipakai ekspedisi dari dimensi kardus vs timbangan,
   serta perkirakan ongkirnya.
   Semua data diproses di memori server dan tidak disimpan ke disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('volumetrik-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('volumetrik-close'),
    pembagi: document.getElementById('volumetrik-pembagi'),
    pembulatan: document.getElementById('volumetrik-pembulatan'),
    tarif: document.getElementById('volumetrik-tarif'),
    rowsContainer: document.getElementById('volumetrik-rows'),
    addRowBtn: document.getElementById('volumetrik-add-row'),
    status: document.getElementById('volumetrik-status'),
    clear: document.getElementById('volumetrik-clear'),
    submit: document.getElementById('volumetrik-submit'),
    result: document.getElementById('volumetrik-result'),
    totalBerat: document.getElementById('volumetrik-total-berat'),
    totalOngkir: document.getElementById('volumetrik-total-ongkir'),
    totalVolume: document.getElementById('volumetrik-total-volume'),
    totalKoli: document.getElementById('volumetrik-total-koli'),
    tableBody: document.getElementById('volumetrik-table-body'),
    saranContainer: document.getElementById('volumetrik-saran-container'),
    saranList: document.getElementById('volumetrik-saran-list'),
    copy: document.getElementById('volumetrik-copy')
  };

  var FALLBACK_LIMITS = {
    maks_koli: 10,
    dimensi_cm: { min: 1, max: 300 },
    berat_kg: { min: 0.01, max: 1000 },
    pembagi: [6000, 5000, 4000],
    pembulatan: [0.1, 0.5, 1],
    tarif_per_kg: { min: 0, max: 1000000 },
    contoh: {
      pembagi: 6000,
      pembulatan: 0.5,
      tarif_per_kg: 18000,
      koli: [
        {
          nama: 'Kardus 1',
          panjang: 40,
          lebar: 30,
          tinggi: 25,
          berat: 2.4
        }
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

  function formatNumber(num, maxDec) {
    if (num === null || num === undefined || isNaN(num)) return '0';
    var n = Number(num);
    var dec = typeof maxDec === 'number' ? maxDec : 3;
    return new Intl.NumberFormat('id-ID', {
      minimumFractionDigits: 0,
      maximumFractionDigits: dec
    }).format(n);
  }

  function formatRp(num) {
    if (num === null || num === undefined || isNaN(num)) return '—';
    var n = Math.round(Number(num) || 0);
    return 'Rp ' + new Intl.NumberFormat('id-ID').format(n);
  }

  function parseRupiahInput(str) {
    if (!str) return 0;
    var cleaned = String(str).replace(/[^\d]/g, '');
    return cleaned ? Number(cleaned) : 0;
  }

  function parseDecimalInput(str) {
    if (!str) return 0;
    var cleaned = String(str)
      .trim()
      .replace(/\s+/g, '')
      .replace(/,/g, '.')
      .replace(/[^\d.]/g, '');
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
    row.className = 'volumetrik__row';
    row.setAttribute('data-row-id', String(rowId));

    var grid = document.createElement('div');
    grid.className = 'volumetrik__row-grid';

    // 1. Nama
    var colNama = document.createElement('div');
    colNama.className = 'field volumetrik__col-nama';
    var lblNama = document.createElement('label');
    lblNama.setAttribute('for', 'vol-nama-' + rowId);
    lblNama.textContent = 'Nama kardus (opsional)';
    var inpNama = document.createElement('input');
    inpNama.type = 'text';
    inpNama.id = 'vol-nama-' + rowId;
    inpNama.className = 'volumetrik__input volumetrik__input-nama';
    inpNama.maxLength = 40;
    inpNama.placeholder = 'Mis. Kardus ' + rowId;
    inpNama.value = item.nama || '';
    inpNama.autocomplete = 'off';
    colNama.appendChild(lblNama);
    colNama.appendChild(inpNama);

    // 2. Panjang (cm)
    var colP = document.createElement('div');
    colP.className = 'field volumetrik__col-dimensi';
    var lblP = document.createElement('label');
    lblP.setAttribute('for', 'vol-p-' + rowId);
    lblP.textContent = 'Panjang (cm)';
    var inpP = document.createElement('input');
    inpP.type = 'text';
    inpP.id = 'vol-p-' + rowId;
    inpP.className = 'volumetrik__input volumetrik__input-panjang';
    inpP.inputMode = 'decimal';
    inpP.placeholder = 'Mis. 40';
    inpP.value = item.panjang !== undefined && item.panjang !== null ? formatNumber(item.panjang, 2) : '';
    inpP.autocomplete = 'off';
    colP.appendChild(lblP);
    colP.appendChild(inpP);

    // 3. Lebar (cm)
    var colL = document.createElement('div');
    colL.className = 'field volumetrik__col-dimensi';
    var lblL = document.createElement('label');
    lblL.setAttribute('for', 'vol-l-' + rowId);
    lblL.textContent = 'Lebar (cm)';
    var inpL = document.createElement('input');
    inpL.type = 'text';
    inpL.id = 'vol-l-' + rowId;
    inpL.className = 'volumetrik__input volumetrik__input-lebar';
    inpL.inputMode = 'decimal';
    inpL.placeholder = 'Mis. 30';
    inpL.value = item.lebar !== undefined && item.lebar !== null ? formatNumber(item.lebar, 2) : '';
    inpL.autocomplete = 'off';
    colL.appendChild(lblL);
    colL.appendChild(inpL);

    // 4. Tinggi (cm)
    var colT = document.createElement('div');
    colT.className = 'field volumetrik__col-dimensi';
    var lblT = document.createElement('label');
    lblT.setAttribute('for', 'vol-t-' + rowId);
    lblT.textContent = 'Tinggi (cm)';
    var inpT = document.createElement('input');
    inpT.type = 'text';
    inpT.id = 'vol-t-' + rowId;
    inpT.className = 'volumetrik__input volumetrik__input-tinggi';
    inpT.inputMode = 'decimal';
    inpT.placeholder = 'Mis. 25';
    inpT.value = item.tinggi !== undefined && item.tinggi !== null ? formatNumber(item.tinggi, 2) : '';
    inpT.autocomplete = 'off';
    colT.appendChild(lblT);
    colT.appendChild(inpT);

    // 5. Berat timbangan (kg)
    var colB = document.createElement('div');
    colB.className = 'field volumetrik__col-berat';
    var lblB = document.createElement('label');
    lblB.setAttribute('for', 'vol-b-' + rowId);
    lblB.textContent = 'Berat timbangan (kg)';
    var inpB = document.createElement('input');
    inpB.type = 'text';
    inpB.id = 'vol-b-' + rowId;
    inpB.className = 'volumetrik__input volumetrik__input-berat';
    inpB.inputMode = 'decimal';
    inpB.placeholder = 'Mis. 2,4';
    inpB.value = item.berat !== undefined && item.berat !== null ? formatNumber(item.berat, 3) : '';
    inpB.autocomplete = 'off';
    colB.appendChild(lblB);
    colB.appendChild(inpB);

    // 6. Tombol Hapus
    var colAction = document.createElement('div');
    colAction.className = 'volumetrik__col-action';
    var btnHapus = document.createElement('button');
    btnHapus.type = 'button';
    btnHapus.className = 'btn btn--ghost volumetrik__btn-delete';
    btnHapus.setAttribute('aria-label', 'Hapus kardus ini');
    btnHapus.innerHTML = '<span aria-hidden="true">&times;</span> Hapus';
    btnHapus.addEventListener('click', function () {
      var allRows = el.rowsContainer.querySelectorAll('.volumetrik__row');
      if (allRows.length <= 1) {
        setStatus('Minimal harus ada 1 kardus dalam daftar.', 'warn');
        return;
      }
      row.remove();
      updateRowButtons();
    });
    colAction.appendChild(btnHapus);

    grid.appendChild(colNama);
    grid.appendChild(colP);
    grid.appendChild(colL);
    grid.appendChild(colT);
    grid.appendChild(colB);
    grid.appendChild(colAction);
    row.appendChild(grid);

    return row;
  }

  function updateRowButtons() {
    var allRows = el.rowsContainer.querySelectorAll('.volumetrik__row');
    var maxKoli = (state.limits && state.limits.maks_koli) || 10;
    if (el.addRowBtn) {
      el.addRowBtn.disabled = allRows.length >= maxKoli;
    }
  }

  function addRow(data) {
    var allRows = el.rowsContainer.querySelectorAll('.volumetrik__row');
    var maxKoli = (state.limits && state.limits.maks_koli) || 10;
    if (allRows.length >= maxKoli) {
      setStatus('Maksimal ' + maxKoli + ' kardus sekali hitung.', 'warn');
      return;
    }
    var rowEl = createRowElement(data);
    el.rowsContainer.appendChild(rowEl);
    updateRowButtons();
  }

  function populateDefaultRows(contoh) {
    if (!el.rowsContainer) return;
    el.rowsContainer.innerHTML = '';
    var list = (contoh && contoh.koli) || FALLBACK_LIMITS.contoh.koli;
    list.forEach(function (k) {
      addRow(k);
    });
    if (el.pembagi) {
      el.pembagi.value = String((contoh && contoh.pembagi) || FALLBACK_LIMITS.contoh.pembagi);
    }
    if (el.pembulatan) {
      el.pembulatan.value = String((contoh && contoh.pembulatan) || FALLBACK_LIMITS.contoh.pembulatan);
    }
    if (el.tarif) {
      var t = contoh && contoh.tarif_per_kg !== undefined ? contoh.tarif_per_kg : FALLBACK_LIMITS.contoh.tarif_per_kg;
      el.tarif.value = t ? formatNumber(t, 0) : '';
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/volumetrik/limits', {
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
          updateRowButtons();
        }
      })
      .catch(function () {
        // Gunakan batas bawaan jika jaringan belum terhubung
      });
  }

  function getFormData() {
    var pembagiVal = parseInt(el.pembagi ? el.pembagi.value : '6000', 10) || 6000;
    var pembulatanVal = parseFloat(el.pembulatan ? el.pembulatan.value : '0.5') || 0.5;
    var tarifVal = parseRupiahInput(el.tarif ? el.tarif.value : '');
    var rows = el.rowsContainer.querySelectorAll('.volumetrik__row');
    var koliList = [];

    rows.forEach(function (r, idx) {
      var inpNama = r.querySelector('.volumetrik__input-nama');
      var inpP = r.querySelector('.volumetrik__input-panjang');
      var inpL = r.querySelector('.volumetrik__input-lebar');
      var inpT = r.querySelector('.volumetrik__input-tinggi');
      var inpB = r.querySelector('.volumetrik__input-berat');

      var nama = inpNama ? inpNama.value.trim() : '';
      var p = inpP ? parseDecimalInput(inpP.value) : 0;
      var l = inpL ? parseDecimalInput(inpL.value) : 0;
      var t = inpT ? parseDecimalInput(inpT.value) : 0;
      var b = inpB ? parseDecimalInput(inpB.value) : 0;

      koliList.push({
        nama: nama || ('Kardus ' + (idx + 1)),
        panjang: p,
        lebar: l,
        tinggi: t,
        berat: b
      });
    });

    return {
      pembagi: pembagiVal,
      pembulatan: pembulatanVal,
      tarif_per_kg: tarifVal > 0 ? tarifVal : null,
      koli: koliList
    };
  }

  function renderResult(data) {
    if (!el.result || !data) return;
    state.lastResult = data;

    var ringkasan = data.ringkasan || {};
    var koliList = data.koli || [];
    var saranList = data.saran || [];

    // Hero Total Berat
    if (el.totalBerat) {
      el.totalBerat.textContent = formatNumber(data.total_berat, 2) + ' kg';
    }

    // Perkiraan Total Ongkir
    if (el.totalOngkir) {
      if (data.total_ongkir !== null && data.total_ongkir !== undefined) {
        el.totalOngkir.textContent = formatRp(data.total_ongkir);
      } else {
        el.totalOngkir.textContent = '— (Tarif belum diisi)';
      }
    }

    // Total Volume
    if (el.totalVolume) {
      el.totalVolume.textContent = formatNumber(data.total_volume_cm3, 0) + ' cm³';
    }

    // Total Koli
    if (el.totalKoli) {
      el.totalKoli.textContent = String(ringkasan.total_koli || koliList.length) + ' koli';
    }

    // Tabel per koli
    if (el.tableBody) {
      el.tableBody.innerHTML = '';
      koliList.forEach(function (k) {
        var tr = document.createElement('tr');
        var isVol = k.berat_dasar === 'volumetrik';
        if (isVol) {
          tr.className = 'volumetrik__tr--volumetrik';
        }

        // 1. Nama
        var tdNama = document.createElement('td');
        var strongNama = document.createElement('strong');
        strongNama.textContent = k.nama;
        tdNama.appendChild(strongNama);

        // 2. Ukuran (cm)
        var tdUkuran = document.createElement('td');
        tdUkuran.className = 'text-right';
        tdUkuran.textContent = formatNumber(k.panjang, 1) + ' × ' +
          formatNumber(k.lebar, 1) + ' × ' +
          formatNumber(k.tinggi, 1);

        // 3. Volume
        var tdVol = document.createElement('td');
        tdVol.className = 'text-right';
        tdVol.textContent = formatNumber(k.volume_cm3, 0) + ' cm³';

        // 4. Berat aktual
        var tdAktual = document.createElement('td');
        tdAktual.className = 'text-right';
        tdAktual.textContent = formatNumber(k.berat_aktual, 3) + ' kg';

        // 5. Berat volumetrik
        var tdVolumetrik = document.createElement('td');
        tdVolumetrik.className = 'text-right';
        tdVolumetrik.textContent = formatNumber(k.berat_volumetrik, 3) + ' kg';

        // 6. Berat dipakai
        var tdPakai = document.createElement('td');
        tdPakai.className = 'text-right';
        var strongPakai = document.createElement('strong');
        strongPakai.textContent = formatNumber(k.berat_dibulatkan, 2) + ' kg';
        tdPakai.appendChild(strongPakai);

        // 7. Dasar hitungan (penanda teks jelas)
        var tdDasar = document.createElement('td');
        tdDasar.className = 'text-center';
        var badge = document.createElement('span');
        if (isVol) {
          badge.className = 'volumetrik__badge volumetrik__badge--volumetrik';
          badge.textContent = 'Volumetrik (lebih besar)';
        } else {
          badge.className = 'volumetrik__badge volumetrik__badge--aktual';
          badge.textContent = 'Timbangan';
        }
        tdDasar.appendChild(badge);

        tr.appendChild(tdNama);
        tr.appendChild(tdUkuran);
        tr.appendChild(tdVol);
        tr.appendChild(tdAktual);
        tr.appendChild(tdVolumetrik);
        tr.appendChild(tdPakai);
        tr.appendChild(tdDasar);

        el.tableBody.appendChild(tr);
      });
    }

    // Saran & catatan
    if (el.saranContainer && el.saranList) {
      el.saranList.innerHTML = '';
      if (saranList.length > 0) {
        saranList.forEach(function (s) {
          var li = document.createElement('li');
          li.textContent = s;
          el.saranList.appendChild(li);
        });
        el.saranContainer.hidden = false;
      } else {
        el.saranContainer.hidden = true;
      }
    }

    el.result.hidden = false;
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.result.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest' });
  }

  function submitVolumetrik() {
    if (state.busy) return;

    var data = getFormData();

    // Validasi di peramban sebelum mengirim
    if (!data.koli || data.koli.length === 0) {
      setStatus('Daftar kardus tidak boleh kosong.', 'error');
      return;
    }

    for (var i = 0; i < data.koli.length; i++) {
      var item = data.koli[i];
      if (!item.panjang || item.panjang < 1 || item.panjang > 300) {
        setStatus('Dimensi panjang "' + item.nama + '" harus berupa angka antara 1 sampai 300 cm.', 'error');
        return;
      }
      if (!item.lebar || item.lebar < 1 || item.lebar > 300) {
        setStatus('Dimensi lebar "' + item.nama + '" harus berupa angka antara 1 sampai 300 cm.', 'error');
        return;
      }
      if (!item.tinggi || item.tinggi < 1 || item.tinggi > 300) {
        setStatus('Dimensi tinggi "' + item.nama + '" harus berupa angka antara 1 sampai 300 cm.', 'error');
        return;
      }
      if (!item.berat || item.berat < 0.01 || item.berat > 1000) {
        setStatus('Berat timbangan "' + item.nama + '" harus berupa angka antara 0,01 sampai 1.000 kg.', 'error');
        return;
      }
    }

    if (el.result) el.result.hidden = true;
    state.busy = true;
    if (el.submit) el.submit.disabled = true;
    setStatus('Menghitung berat volumetrik...', 'busy');

    if (state.abortController) {
      state.abortController.abort();
    }
    state.abortController = new AbortController();

    fetch(serverBase + '/api/volumetrik', {
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
          setStatus('Perhitungan berat volumetrik berhasil.', 'success');
          renderResult(resp.body.data);
        } else {
          var errObj = resp.body || {};
          var msg = errObj.pesan ||
            (errObj.error && errObj.error.message) ||
            (errObj.detail && errObj.detail.message) ||
            'Gagal menghitung berat volumetrik.';
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
    populateDefaultRows(FALLBACK_LIMITS.contoh);
    setStatus('Formulir telah dikembalikan ke contoh awal. Masukkan ukuran paketmu lalu tekan "Hitung berat".', '');
  }

  function copyResult() {
    if (!state.lastResult) return;
    var res = state.lastResult;
    var ring = res.ringkasan || {};
    var list = res.koli || [];
    var saran = res.saran || [];

    var lines = [
      'Perhitungan Berat Volumetrik Paket — OmniTools (bahzi.fun)',
      '==================================================',
      'Total kardus: ' + (ring.total_koli || list.length) + ' koli',
      'Total berat terpakai: ' + formatNumber(res.total_berat, 2) + ' kg',
      'Total volume: ' + formatNumber(res.total_volume_cm3, 0) + ' cm³',
      'Perkiraan ongkir: ' + (res.total_ongkir ? formatRp(res.total_ongkir) : 'Belum diisi'),
      'Pembagi: ' + formatNumber(res.pembagi, 0) + ' | Pembulatan: ' + formatNumber(res.pembulatan, 1) + ' kg',
      ''
    ];

    if (res.tarif_per_kg) {
      lines.push('Tarif per kg: ' + formatRp(res.tarif_per_kg));
      lines.push('');
    }

    lines.push('Rincian per kardus:');
    list.forEach(function (k, idx) {
      var dasarLabel = k.berat_dasar === 'volumetrik' ? 'Volumetrik' : 'Timbangan';
      lines.push(
        (idx + 1) + '. ' + k.nama + ' — ' +
        formatNumber(k.panjang, 1) + ' × ' + formatNumber(k.lebar, 1) + ' × ' + formatNumber(k.tinggi, 1) + ' cm (' +
        formatNumber(k.volume_cm3, 0) + ' cm³)'
      );
      lines.push('   Berat timbangan: ' + formatNumber(k.berat_aktual, 3) + ' kg | Volumetrik: ' + formatNumber(k.berat_volumetrik, 3) + ' kg');
      lines.push('   Berat dipakai: ' + formatNumber(k.berat_dibulatkan, 2) + ' kg (Dasar: ' + dasarLabel + ')');
      if (k.selisih_kg > 0) {
        lines.push('   Kenaikan dari timbangan: +' + formatNumber(k.selisih_kg, 3) + ' kg (+' + formatNumber(k.selisih_persen, 1) + '%)');
      }
    });

    if (saran.length > 0) {
      lines.push('');
      lines.push('Saran & catatan:');
      saran.forEach(function (s) {
        lines.push('- ' + s);
      });
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
        setStatus('Gagal menyalin ringkasan ke papan klip.', 'error');
      }
      document.body.removeChild(ta);
    }
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="volumetrik"]');
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
      if (el.pembagi) el.pembagi.focus();
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
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      if (panel.contains(document.activeElement)) {
        event.preventDefault();
        submitVolumetrik();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.addRowBtn) {
    el.addRowBtn.addEventListener('click', function () {
      addRow({ nama: '', panjang: '', lebar: '', tinggi: '', berat: '' });
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitVolumetrik);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);

  if (el.tarif) {
    el.tarif.addEventListener('blur', function () {
      var val = parseRupiahInput(this.value);
      if (val > 0) this.value = formatNumber(val, 0);
    });
  }

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels.volumetrik = toggle;

  // Inisialisasi formulir awal
  populateDefaultRows(FALLBACK_LIMITS.contoh);
})();
