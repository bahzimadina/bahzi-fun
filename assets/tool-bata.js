/* =========================================================================
   Panel alat: Hitung kebutuhan bata dinding
   Angka dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu dibuang setelah selesai. Tidak ada angka yang disimpan di disk.

   Skrip terpisah dari app.js supaya daftar alat tetap jalan walau panel ini
   tidak ada di halaman.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('bata-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('bata-close'),
    modeDimensi: document.getElementById('bata-mode-dimensi'),
    modeLuas: document.getElementById('bata-mode-luas'),
    groupDimensi: document.getElementById('bata-group-dimensi'),
    groupLuas: document.getElementById('bata-group-luas'),
    inputPanjang: document.getElementById('bata-input-panjang'),
    inputTinggi: document.getElementById('bata-input-tinggi'),
    inputLuas: document.getElementById('bata-input-luas'),
    inputBukaan: document.getElementById('bata-input-bukaan'),
    jenis: document.getElementById('bata-jenis'),
    groupCampuran: document.getElementById('bata-group-campuran'),
    campuran: document.getElementById('bata-campuran'),
    infoHebel: document.getElementById('bata-info-hebel'),
    cadangan: document.getElementById('bata-cadangan'),
    inputHargaBata: document.getElementById('bata-harga-bata'),
    groupHargaSemen: document.getElementById('bata-group-harga-semen'),
    inputHargaSemen: document.getElementById('bata-harga-semen'),
    groupHargaPasir: document.getElementById('bata-group-harga-pasir'),
    inputHargaPasir: document.getElementById('bata-harga-pasir'),
    groupHargaMortar: document.getElementById('bata-group-harga-mortar'),
    inputHargaMortar: document.getElementById('bata-harga-mortar'),
    status: document.getElementById('bata-status'),
    clear: document.getElementById('bata-clear'),
    submit: document.getElementById('bata-submit'),
    results: document.getElementById('bata-results'),
    resultHint: document.getElementById('bata-result-hint'),
    outputWrap: document.getElementById('bata-output-wrap'),
    heroValue: document.getElementById('bata-hero-value'),
    heroSymbol: document.getElementById('bata-hero-symbol'),
    summaryText: document.getElementById('bata-summary-text'),
    statLuas: document.getElementById('bata-stat-luas'),
    statPasang: document.getElementById('bata-stat-pasang'),
    statCadangan: document.getElementById('bata-stat-cadangan'),
    itemSemen: document.getElementById('bata-item-semen'),
    statSemen: document.getElementById('bata-stat-semen'),
    itemPasir: document.getElementById('bata-item-pasir'),
    statPasir: document.getElementById('bata-stat-pasir'),
    itemMortar: document.getElementById('bata-item-mortar'),
    statMortar: document.getElementById('bata-stat-mortar'),
    itemBiayaTotal: document.getElementById('bata-item-biaya-total'),
    statBiayaTotal: document.getElementById('bata-stat-biaya-total'),
    itemBiayaM2: document.getElementById('bata-item-biaya-m2'),
    statBiayaM2: document.getElementById('bata-stat-biaya-m2'),
    rincianList: document.getElementById('bata-rincian-list'),
    patokanBox: document.getElementById('bata-patokan-box'),
    notesList: document.getElementById('bata-notes-list'),
    copy: document.getElementById('bata-copy'),
    download: document.getElementById('bata-download'),
    linkKeramik: document.getElementById('bata-link-keramik'),
    linkCat: document.getElementById('bata-link-cat')
  };

  var state = {
    limitsLoaded: false,
    limitsData: null,
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

  function getActiveMode() {
    if (el.modeLuas && el.modeLuas.checked) {
      return 'luas';
    }
    return 'dimensi';
  }

  function isHebel() {
    var j = el.jenis ? el.jenis.value : 'bata-merah';
    return j === 'hebel-75' || j === 'hebel-100';
  }

  function formatRibuan(n) {
    if (n === null || n === undefined) return '-';
    var num = Math.round(Number(n));
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function formatDesimal(n) {
    if (n === null || n === undefined) return '-';
    return n.toString().replace('.', ',');
  }

  function updateModeVisibility() {
    var mode = getActiveMode();
    if (mode === 'luas') {
      if (el.groupDimensi) el.groupDimensi.hidden = true;
      if (el.groupLuas) el.groupLuas.hidden = false;
    } else {
      if (el.groupDimensi) el.groupDimensi.hidden = false;
      if (el.groupLuas) el.groupLuas.hidden = true;
    }
    updateControls();
  }

  function updateJenisVisibility() {
    var hebel = isHebel();
    if (hebel) {
      if (el.groupCampuran) el.groupCampuran.hidden = true;
      if (el.campuran) el.campuran.disabled = true;
      if (el.infoHebel) el.infoHebel.hidden = false;
      if (el.groupHargaSemen) el.groupHargaSemen.hidden = true;
      if (el.groupHargaPasir) el.groupHargaPasir.hidden = true;
      if (el.groupHargaMortar) el.groupHargaMortar.hidden = false;
    } else {
      if (el.groupCampuran) el.groupCampuran.hidden = false;
      if (el.campuran) el.campuran.disabled = false;
      if (el.infoHebel) el.infoHebel.hidden = true;
      if (el.groupHargaSemen) el.groupHargaSemen.hidden = false;
      if (el.groupHargaPasir) el.groupHargaPasir.hidden = false;
      if (el.groupHargaMortar) el.groupHargaMortar.hidden = true;
    }
    updatePatokanDisplay();
    updateControls();
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.heroSymbol) el.heroSymbol.textContent = '';
    if (el.summaryText) el.summaryText.textContent = '';
    if (el.rincianList) el.rincianList.innerHTML = '';
    if (el.notesList) el.notesList.innerHTML = '';
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
    var mode = getActiveMode();
    var hasRequired = false;

    if (mode === 'dimensi') {
      var p = el.inputPanjang ? el.inputPanjang.value.trim() : '';
      var t = el.inputTinggi ? el.inputTinggi.value.trim() : '';
      hasRequired = (p.length > 0 && t.length > 0);
    } else {
      var luas = el.inputLuas ? el.inputLuas.value.trim() : '';
      hasRequired = (luas.length > 0);
    }

    var hasAny = false;
    if (el.inputPanjang && el.inputPanjang.value.trim()) hasAny = true;
    if (el.inputTinggi && el.inputTinggi.value.trim()) hasAny = true;
    if (el.inputLuas && el.inputLuas.value.trim()) hasAny = true;
    if (el.inputBukaan && el.inputBukaan.value.trim()) hasAny = true;
    if (el.cadangan && el.cadangan.value.trim() && el.cadangan.value !== '5') hasAny = true;
    if (el.inputHargaBata && el.inputHargaBata.value.trim()) hasAny = true;
    if (el.inputHargaSemen && el.inputHargaSemen.value.trim()) hasAny = true;
    if (el.inputHargaPasir && el.inputHargaPasir.value.trim()) hasAny = true;
    if (el.inputHargaMortar && el.inputHargaMortar.value.trim()) hasAny = true;
    var hasOutput = !!state.lastResult;

    if (el.submit) {
      el.submit.disabled = state.busy || !hasRequired;
      el.submit.textContent = state.busy ? 'Menghitung…' : 'Hitung kebutuhan';
    }
    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAny && !hasOutput);
    }
  }

  function updatePatokanDisplay() {
    if (!el.patokanBox) return;
    var jenisVal = el.jenis ? el.jenis.value : 'bata-merah';
    var campVal = el.campuran ? el.campuran.value : '1:4';

    if (state.limitsData && state.limitsData.tabel_patokan && state.limitsData.tabel_patokan[jenisVal]) {
      var pat = state.limitsData.tabel_patokan[jenisVal];
      var html = '<p><strong>' + pat.label + '</strong> (ukuran ' + pat.ukuran + '): ' +
        formatDesimal(pat.bata_per_m2) + ' buah/m².</p>';

      if (pat.perekat_jenis === 'semen_pasir' && pat.campuran && pat.campuran[campVal]) {
        var c = pat.campuran[campVal];
        html += '<p>Adukan ' + campVal + ': semen ' + formatDesimal(c.semen_kg_per_m2) +
          ' kg/m² (' + formatDesimal(c.semen_sak_per_m2) + ' sak 50 kg), pasir ' +
          formatDesimal(c.pasir_m3_per_m2) + ' m³/m².</p>';
      } else if (pat.perekat_jenis === 'mortar') {
        html += '<p>Perekat mortar instan 40 kg: ' + formatDesimal(pat.mortar_sak_per_m2) + ' sak/m².</p>';
      }

      if (pat.keterangan) {
        html += '<p class="bt__patokan-note">' + pat.keterangan + '</p>';
      }
      el.patokanBox.innerHTML = html;
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/bata/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limitsData = data;
        state.limitsLoaded = true;
        updatePatokanDisplay();
      })
      .catch(function () {
        /* Bila gagal memuat limits, panel tetap fungsional */
      });
  }

  function renderResults(data) {
    state.lastResult = data;
    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    if (el.heroValue) el.heroValue.textContent = formatRibuan(data.bata_dibeli);
    if (el.heroSymbol) el.heroSymbol.textContent = 'Buah (' + data.jenis_label + ')';

    var ringkasan = 'Dinding seluas ' + formatDesimal(data.luas_dinding_m2) + ' m² membutuhkan ' +
      formatRibuan(data.bata_pasang) + ' buah bata terpasang. Dengan cadangan ' + data.cadangan_persen + '%, disarankan membeli ' +
      formatRibuan(data.bata_dibeli) + ' buah.';
    if (el.summaryText) el.summaryText.textContent = ringkasan;

    if (el.statLuas) el.statLuas.textContent = formatDesimal(data.luas_dinding_m2) + ' m²';
    if (el.statPasang) el.statPasang.textContent = formatRibuan(data.bata_pasang) + ' buah';
    if (el.statCadangan) {
      el.statCadangan.textContent = formatRibuan(data.bata_cadangan_pasang) + ' buah (' + data.cadangan_persen + '%)';
    }

    if (data.semen_sak !== null && data.semen_sak !== undefined) {
      if (el.itemSemen) el.itemSemen.hidden = false;
      if (el.statSemen) el.statSemen.textContent = data.semen_sak + ' sak (' + formatDesimal(data.semen_kg) + ' kg)';
      if (el.itemPasir) el.itemPasir.hidden = false;
      if (el.statPasir) el.statPasir.textContent = formatDesimal(data.pasir_m3) + ' m³';
      if (el.itemMortar) el.itemMortar.hidden = true;
    } else {
      if (el.itemSemen) el.itemSemen.hidden = true;
      if (el.itemPasir) el.itemPasir.hidden = true;
      if (el.itemMortar) el.itemMortar.hidden = false;
      if (el.statMortar) el.statMortar.textContent = data.mortar_sak + ' sak (40 kg)';
    }

    if (data.biaya) {
      if (el.itemBiayaTotal) {
        el.itemBiayaTotal.hidden = false;
        var labelTotal = 'Rp' + formatRibuan(data.biaya.total);
        if (!data.biaya.lengkap) {
          labelTotal += ' (sebagian)';
        }
        if (el.statBiayaTotal) el.statBiayaTotal.textContent = labelTotal;
      }
      if (el.itemBiayaM2) {
        el.itemBiayaM2.hidden = false;
        if (el.statBiayaM2) el.statBiayaM2.textContent = 'Rp' + formatRibuan(data.biaya.per_m2) + ' / m²';
      }
    } else {
      if (el.itemBiayaTotal) el.itemBiayaTotal.hidden = true;
      if (el.itemBiayaM2) el.itemBiayaM2.hidden = true;
    }

    if (el.rincianList) {
      el.rincianList.innerHTML = '';
      var itemBata = document.createElement('li');
      var txtBata = data.jenis_label + ': ' + formatRibuan(data.bata_dibeli) + ' buah (' +
        formatRibuan(data.bata_pasang) + ' terpasang + ' + formatRibuan(data.bata_cadangan_pasang) + ' cadangan)';
      if (data.biaya && data.biaya.bata !== null) {
        txtBata += ' - Rp' + formatRibuan(data.biaya.bata);
      }
      itemBata.textContent = txtBata;
      el.rincianList.appendChild(itemBata);

      if (data.semen_sak !== null) {
        var itemSemen = document.createElement('li');
        var txtSemen = 'Semen 50 kg: ' + data.semen_sak + ' sak (' + formatDesimal(data.semen_kg) + ' kg)';
        if (data.biaya && data.biaya.ikat !== null) {
          txtSemen += ' - Rp' + formatRibuan(data.biaya.ikat);
        }
        itemSemen.textContent = txtSemen;
        el.rincianList.appendChild(itemSemen);

        var itemPasir = document.createElement('li');
        var txtPasir = 'Pasir pasang: ' + formatDesimal(data.pasir_m3) + ' m³';
        if (data.biaya && data.biaya.pasir !== null) {
          txtPasir += ' - Rp' + formatRibuan(data.biaya.pasir);
        }
        itemPasir.textContent = txtPasir;
        el.rincianList.appendChild(itemPasir);
      } else if (data.mortar_sak !== null) {
        var itemMortar = document.createElement('li');
        var txtMortar = 'Mortar instan 40 kg: ' + data.mortar_sak + ' sak';
        if (data.biaya && data.biaya.ikat !== null) {
          txtMortar += ' - Rp' + formatRibuan(data.biaya.ikat);
        }
        itemMortar.textContent = txtMortar;
        el.rincianList.appendChild(itemMortar);
      }
    }

    updatePatokanDisplay();

    if (el.notesList) {
      el.notesList.innerHTML = '';
      if (Array.isArray(data.catatan)) {
        for (var i = 0; i < data.catatan.length; i++) {
          var li = document.createElement('li');
          li.textContent = data.catatan[i];
          el.notesList.appendChild(li);
        }
      }
    }
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed) {
          if (parsed.error && parsed.error.message) {
            message = parsed.error.message;
          } else if (parsed.detail && parsed.detail.message) {
            message = parsed.detail.message;
          } else if (typeof parsed.detail === 'string') {
            message = parsed.detail;
          }
        }
      } catch (err) { /* diabaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan hitung kebutuhan bata belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Kebutuhan bata atau ukuran permintaan melebihi batas yang didukung.';
        } else {
          message = 'Terjadi kendala saat memproses perhitungan (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitCalc() {
    if (state.busy) return;

    var mode = getActiveMode();
    var formData = new FormData();
    formData.append('mode', mode);

    if (mode === 'dimensi') {
      var p = el.inputPanjang ? el.inputPanjang.value.trim() : '';
      var t = el.inputTinggi ? el.inputTinggi.value.trim() : '';
      if (!p || !t) {
        setStatus('Masukkan panjang dan tinggi dinding terlebih dahulu.', 'error');
        if (!p && el.inputPanjang) el.inputPanjang.focus();
        else if (!t && el.inputTinggi) el.inputTinggi.focus();
        return;
      }
      formData.append('panjang', p);
      formData.append('tinggi', t);
    } else {
      var luas = el.inputLuas ? el.inputLuas.value.trim() : '';
      if (!luas) {
        setStatus('Masukkan luas dinding terlebih dahulu.', 'error');
        if (el.inputLuas) el.inputLuas.focus();
        return;
      }
      formData.append('luas', luas);
    }

    var bukaan = el.inputBukaan ? el.inputBukaan.value.trim() : '';
    if (bukaan) formData.append('bukaan', bukaan);

    var jenisVal = el.jenis ? el.jenis.value : 'bata-merah';
    formData.append('jenis', jenisVal);

    if (!isHebel() && el.campuran) {
      formData.append('campuran', el.campuran.value);
    }

    var cadanganVal = el.cadangan ? el.cadangan.value.trim() : '';
    if (cadanganVal) formData.append('cadangan', cadanganVal);

    var hb = el.inputHargaBata ? el.inputHargaBata.value.trim() : '';
    if (hb) formData.append('harga_bata', hb);

    if (!isHebel()) {
      var hs = el.inputHargaSemen ? el.inputHargaSemen.value.trim() : '';
      if (hs) formData.append('harga_semen', hs);

      var hp = el.inputHargaPasir ? el.inputHargaPasir.value.trim() : '';
      if (hp) formData.append('harga_pasir', hp);
    } else {
      var hm = el.inputHargaMortar ? el.inputHargaMortar.value.trim() : '';
      if (hm) formData.append('harga_mortar', hm);
    }

    state.busy = true;
    updateControls();
    setStatus('Menghitung…', 'busy');

    fetch(serverBase + '/api/bata', {
      method: 'POST',
      body: formData,
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) {
          return readServerError(response);
        }
        return response.json();
      })
      .then(function (data) {
        state.busy = false;
        renderResults(data);
        setStatus('Perhitungan selesai. Disarankan membeli ' + formatRibuan(data.bata_dibeli) + ' buah bata.', 'success');
        updateControls();
      })
      .catch(function (err) {
        state.busy = false;
        resetResults();
        var msg = (err && err.pesanLayanan)
          ? err.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
        updateControls();
      });
  }

  function buildResultSummaryText(data) {
    if (!data) return '';
    var lines = [];
    lines.push('Hitung Kebutuhan Bata - bahzi.fun');
    lines.push('----------------------------------------');
    lines.push('Jenis bata: ' + data.jenis_label);
    if (data.campuran) {
      lines.push('Campuran adukan semen-pasir: ' + data.campuran);
    }
    lines.push('Luas kotor dinding: ' + formatDesimal(data.luas_kotor_m2) + ' m2');
    if (data.bukaan_m2 > 0) {
      lines.push('Bukaan pintu/jendela: ' + formatDesimal(data.bukaan_m2) + ' m2');
    }
    lines.push('Luas dinding bersih: ' + formatDesimal(data.luas_dinding_m2) + ' m2');
    lines.push('Kebutuhan bata terpasang: ' + formatRibuan(data.bata_pasang) + ' buah');
    lines.push('Cadangan (' + data.cadangan_persen + '%): ' + formatRibuan(data.bata_cadangan_pasang) + ' buah');
    lines.push('Total bata disarankan dibeli: ' + formatRibuan(data.bata_dibeli) + ' buah');

    if (data.semen_sak !== null) {
      lines.push('Semen: ' + data.semen_sak + ' sak 50 kg (' + formatDesimal(data.semen_kg) + ' kg)');
      lines.push('Pasir pasang: ' + formatDesimal(data.pasir_m3) + ' m3');
    } else if (data.mortar_sak !== null) {
      lines.push('Mortar instan: ' + data.mortar_sak + ' sak 40 kg');
    }

    if (data.biaya) {
      lines.push('Perkiraan biaya total: Rp' + formatRibuan(data.biaya.total) + (data.biaya.lengkap ? '' : ' (sebagian)'));
      lines.push('Perkiraan biaya per m2: Rp' + formatRibuan(data.biaya.per_m2) + ' / m2');
    }

    if (Array.isArray(data.catatan) && data.catatan.length > 0) {
      lines.push('Catatan:');
      for (var i = 0; i < data.catatan.length; i++) {
        lines.push('- ' + data.catatan[i]);
      }
    }
    lines.push('----------------------------------------');
    lines.push('Hasil adalah estimasi matematis. Kebutuhan di lapangan dapat berbeda tergantung ukuran nyata bata di toko, ketebalan spesi adukan, dan kebiasaan tukang.');
    return lines.join('\n');
  }

  function copyResult() {
    if (!state.lastResult) return;
    var text = buildResultSummaryText(state.lastResult);
    if (!text) return;

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text).then(function () {
        setStatus('Hasil berhasil disalin ke papan klip.', 'success');
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
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try {
      var ok = document.execCommand('copy');
      if (ok) {
        setStatus('Hasil berhasil disalin ke papan klip.', 'success');
      } else {
        setStatus('Gagal menyalin hasil.', 'error');
      }
    } catch (e) {
      setStatus('Gagal menyalin hasil.', 'error');
    }
    document.body.removeChild(ta);
  }

  function downloadResult() {
    if (!state.lastResult) return;
    revokeDownload();

    var text = buildResultSummaryText(state.lastResult);
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    state.downloadUrl = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = state.downloadUrl;
    a.download = 'hasil-bata.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatus('Berkas ringkasan .txt berhasil diunduh.', 'success');
  }

  function resetAll() {
    if (el.modeDimensi) el.modeDimensi.checked = true;
    if (el.modeLuas) el.modeLuas.checked = false;
    if (el.inputPanjang) el.inputPanjang.value = '';
    if (el.inputTinggi) el.inputTinggi.value = '';
    if (el.inputLuas) el.inputLuas.value = '';
    if (el.inputBukaan) el.inputBukaan.value = '';
    if (el.jenis) el.jenis.value = 'bata-merah';
    if (el.campuran) el.campuran.value = '1:4';
    if (el.cadangan) el.cadangan.value = '5';
    if (el.inputHargaBata) el.inputHargaBata.value = '';
    if (el.inputHargaSemen) el.inputHargaSemen.value = '';
    if (el.inputHargaPasir) el.inputHargaPasir.value = '';
    if (el.inputHargaMortar) el.inputHargaMortar.value = '';

    updateModeVisibility();
    updateJenisVisibility();
    resetResults();
    setStatus('Pilih jenis bata, masukkan ukuran dinding, lalu tekan "Hitung kebutuhan".', '');
    updateControls();
    if (el.inputPanjang) el.inputPanjang.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="bata"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'bata-panel');
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

    if (el.inputPanjang) {
      setTimeout(function () { el.inputPanjang.focus(); }, 100);
    }
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    syncTriggers(false);
    revokeDownload();
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

  function onModeChange() {
    resetResults();
    updateModeVisibility();
  }
  if (el.modeDimensi) el.modeDimensi.addEventListener('change', onModeChange);
  if (el.modeLuas) el.modeLuas.addEventListener('change', onModeChange);

  if (el.jenis) {
    el.jenis.addEventListener('change', function () {
      updateJenisVisibility();
      resetResults();
    });
  }

  if (el.campuran) {
    el.campuran.addEventListener('change', function () {
      updatePatokanDisplay();
      resetResults();
    });
  }

  function onOptionChange() {
    if (state.lastResult) {
      resetResults();
    }
    updateControls();
  }
  if (el.cadangan) el.cadangan.addEventListener('change', onOptionChange);
  if (el.inputHargaBata) el.inputHargaBata.addEventListener('change', onOptionChange);
  if (el.inputHargaSemen) el.inputHargaSemen.addEventListener('change', onOptionChange);
  if (el.inputHargaPasir) el.inputHargaPasir.addEventListener('change', onOptionChange);
  if (el.inputHargaMortar) el.inputHargaMortar.addEventListener('change', onOptionChange);

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      var mode = getActiveMode();
      var valid = false;
      if (mode === 'dimensi') {
        var p = el.inputPanjang ? el.inputPanjang.value.trim() : '';
        var t = el.inputTinggi ? el.inputTinggi.value.trim() : '';
        valid = (p.length > 0 && t.length > 0);
      } else {
        var luas = el.inputLuas ? el.inputLuas.value.trim() : '';
        valid = (luas.length > 0);
      }
      if (valid) {
        submitCalc();
      }
    }
  }

  var inputs = [
    el.inputPanjang,
    el.inputTinggi,
    el.inputLuas,
    el.inputBukaan,
    el.cadangan,
    el.inputHargaBata,
    el.inputHargaSemen,
    el.inputHargaPasir,
    el.inputHargaMortar
  ];

  for (var i = 0; i < inputs.length; i++) {
    if (inputs[i]) {
      inputs[i].addEventListener('input', updateControls);
      inputs[i].addEventListener('keydown', onInputKeydown);
    }
  }

  if (el.submit) el.submit.addEventListener('click', submitCalc);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  if (el.linkKeramik) {
    el.linkKeramik.addEventListener('click', function () {
      close();
      if (window.OmniToolsPanels && typeof window.OmniToolsPanels['keramik'] === 'function') {
        window.OmniToolsPanels['keramik']();
      }
    });
  }

  if (el.linkCat) {
    el.linkCat.addEventListener('click', function () {
      close();
      if (window.OmniToolsPanels && typeof window.OmniToolsPanels['cat'] === 'function') {
        window.OmniToolsPanels['cat']();
      }
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

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel supaya kartu Hitung kebutuhan bata bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['bata'] = toggle;

  // Inisialisasi bawaan
  updateModeVisibility();
  updateJenisVisibility();
  updateControls();
})();
