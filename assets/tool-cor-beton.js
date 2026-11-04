/* =========================================================================
   Panel alat: Hitung kebutuhan cor beton
   Data dikirim ke server via multipart/form-data, dihitung murni di memori,
   lalu langsung dibuang. Tanpa penyimpanan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('cor-beton-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('cor-beton-close'),
    // Mode radio
    modePlat: document.getElementById('cor-beton-mode-plat'),
    modeBalok: document.getElementById('cor-beton-mode-balok'),
    modeKolom: document.getElementById('cor-beton-mode-kolom'),
    modeVolume: document.getElementById('cor-beton-mode-volume'),
    // Group fields
    groupPlat: document.getElementById('cor-beton-group-plat'),
    groupBalok: document.getElementById('cor-beton-group-balok'),
    groupKolom: document.getElementById('cor-beton-group-kolom'),
    groupVolume: document.getElementById('cor-beton-group-volume'),
    // Inputs plat
    inputPanjangPlat: document.getElementById('cor-beton-plat-panjang'),
    inputLebarPlat: document.getElementById('cor-beton-plat-lebar'),
    inputTebalPlat: document.getElementById('cor-beton-plat-tebal'),
    // Inputs balok
    inputPanjangBalok: document.getElementById('cor-beton-balok-panjang'),
    inputLebarBalok: document.getElementById('cor-beton-balok-lebar'),
    inputTinggiBalok: document.getElementById('cor-beton-balok-tinggi'),
    // Inputs kolom
    inputJumlahKolom: document.getElementById('cor-beton-kolom-jumlah'),
    inputTinggiKolom: document.getElementById('cor-beton-kolom-tinggi'),
    inputLebarKolom: document.getElementById('cor-beton-kolom-lebar'),
    inputTebalKolom: document.getElementById('cor-beton-kolom-tebal'),
    // Inputs volume
    inputVolume: document.getElementById('cor-beton-vol-volume'),
    // Mutu & Cadangan
    mutu: document.getElementById('cor-beton-mutu'),
    infoMutu: document.getElementById('cor-beton-info-mutu'),
    cadangan: document.getElementById('cor-beton-cadangan'),
    kapasitasTruk: document.getElementById('cor-beton-kapasitas-truk'),
    // Harga (opsional)
    hargaSemen: document.getElementById('cor-beton-harga-semen'),
    hargaPasir: document.getElementById('cor-beton-harga-pasir'),
    hargaKerikil: document.getElementById('cor-beton-harga-kerikil'),
    hargaReadymix: document.getElementById('cor-beton-harga-readymix'),
    // Status & buttons
    status: document.getElementById('cor-beton-status'),
    clear: document.getElementById('cor-beton-clear'),
    submit: document.getElementById('cor-beton-submit'),
    // Output area
    results: document.getElementById('cor-beton-results'),
    resultHint: document.getElementById('cor-beton-result-hint'),
    outputWrap: document.getElementById('cor-beton-output-wrap'),
    heroValue: document.getElementById('cor-beton-hero-value'),
    heroSymbol: document.getElementById('cor-beton-hero-symbol'),
    summaryText: document.getElementById('cor-beton-summary-text'),
    // Stats
    statVolKotor: document.getElementById('cor-beton-stat-vol-kotor'),
    statCadangan: document.getElementById('cor-beton-stat-cadangan'),
    statSemen: document.getElementById('cor-beton-stat-semen'),
    statPasir: document.getElementById('cor-beton-stat-pasir'),
    statKerikil: document.getElementById('cor-beton-stat-kerikil'),
    statAir: document.getElementById('cor-beton-stat-air'),
    statTruk: document.getElementById('cor-beton-stat-truk'),
    statSisaTruk: document.getElementById('cor-beton-stat-sisa-truk'),
    // Biaya
    biayaSection: document.getElementById('cor-beton-biaya-section'),
    statBiayaAdukan: document.getElementById('cor-beton-stat-biaya-adukan'),
    statBiayaAdukanM3: document.getElementById('cor-beton-stat-biaya-adukan-m3'),
    statBiayaReadymix: document.getElementById('cor-beton-stat-biaya-readymix'),
    statBiayaReadymixM3: document.getElementById('cor-beton-stat-biaya-readymix-m3'),
    statBiayaSelisih: document.getElementById('cor-beton-stat-biaya-selisih'),
    statBiayaSelisihKet: document.getElementById('cor-beton-stat-biaya-selisih-ket'),
    // Notes & actions
    notesList: document.getElementById('cor-beton-notes-list'),
    copy: document.getElementById('cor-beton-copy'),
    download: document.getElementById('cor-beton-download'),
    linkBata: document.getElementById('cor-beton-link-bata'),
    linkKeramik: document.getElementById('cor-beton-link-keramik'),
    linkCat: document.getElementById('cor-beton-link-cat')
  };

  var state = {
    limitsLoaded: false,
    limitsData: null,
    busy: false,
    lastFocus: null,
    lastResult: null,
    downloadUrl: null
  };

  var KOMPOSISI_MUTU_DEFAULT = {
    k175: { label: 'K-175', semen: 326, pasir: 760, kerikil: 1029, air: 215 },
    k225: { label: 'K-225', semen: 371, pasir: 698, kerikil: 1047, air: 215 },
    k250: { label: 'K-250', semen: 384, pasir: 692, kerikil: 1039, air: 215 },
    k300: { label: 'K-300', semen: 413, pasir: 681, kerikil: 1027, air: 215 }
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
    if (el.modeBalok && el.modeBalok.checked) return 'balok';
    if (el.modeKolom && el.modeKolom.checked) return 'kolom';
    if (el.modeVolume && el.modeVolume.checked) return 'volume';
    return 'plat';
  }

  function formatRibuan(n) {
    if (n === null || n === undefined) return '-';
    var num = Math.round(Number(n));
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function formatAngkaBerkoma(n) {
    if (n === null || n === undefined || n === '') return '-';
    var s = n.toString().trim();
    if (s === '') return '-';
    var parts = s.replace(',', '.').split('.');
    var bulat = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    if (parts.length > 1 && parts[1].length > 0) {
      return bulat + ',' + parts[1];
    }
    return bulat;
  }

  function formatDesimal(n) {
    if (n === null || n === undefined) return '-';
    return n.toString().replace('.', ',');
  }

  function formatRupiah(n) {
    if (n === null || n === undefined) return '-';
    return 'Rp ' + formatRibuan(n);
  }

  function updateModeVisibility() {
    var mode = getActiveMode();
    if (el.groupPlat) el.groupPlat.hidden = (mode !== 'plat');
    if (el.groupBalok) el.groupBalok.hidden = (mode !== 'balok');
    if (el.groupKolom) el.groupKolom.hidden = (mode !== 'kolom');
    if (el.groupVolume) el.groupVolume.hidden = (mode !== 'volume');
    resetResults();
    updateControls();
  }

  function updateMutuDisplay() {
    if (!el.mutu || !el.infoMutu) return;
    var kode = el.mutu.value || 'k225';
    var item = null;

    if (state.limitsData && state.limitsData.mutu_pilihan) {
      for (var i = 0; i < state.limitsData.mutu_pilihan.length; i++) {
        if (state.limitsData.mutu_pilihan[i].kode === kode) {
          item = state.limitsData.mutu_pilihan[i];
          break;
        }
      }
    }
    if (!item && KOMPOSISI_MUTU_DEFAULT[kode]) {
      var d = KOMPOSISI_MUTU_DEFAULT[kode];
      item = {
        label: d.label,
        semen_kg_per_m3: d.semen,
        pasir_kg_per_m3: d.pasir,
        kerikil_kg_per_m3: d.kerikil,
        air_liter_per_m3: d.air
      };
    }

    if (item) {
      el.infoMutu.textContent = 'Komposisi per 1 m³: Semen ' + formatAngkaBerkoma(item.semen_kg_per_m3) + ' kg | Pasir ' + formatAngkaBerkoma(item.pasir_kg_per_m3) + ' kg | Kerikil ' + formatAngkaBerkoma(item.kerikil_kg_per_m3) + ' kg | Air ' + formatAngkaBerkoma(item.air_liter_per_m3) + ' liter';
    }
  }

  function resetResults() {
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.resultHint) el.resultHint.hidden = false;
    state.lastResult = null;
    revokeDownload();
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      try {
        URL.revokeObjectURL(state.downloadUrl);
      } catch (e) { /* abaikan */ }
      state.downloadUrl = null;
    }
  }

  function hasAnyInput() {
    var mode = getActiveMode();
    if (mode === 'plat') {
      return !!((el.inputPanjangPlat && el.inputPanjangPlat.value.trim()) ||
                (el.inputLebarPlat && el.inputLebarPlat.value.trim()) ||
                (el.inputTebalPlat && el.inputTebalPlat.value.trim()));
    } else if (mode === 'balok') {
      return !!((el.inputPanjangBalok && el.inputPanjangBalok.value.trim()) ||
                (el.inputLebarBalok && el.inputLebarBalok.value.trim()) ||
                (el.inputTinggiBalok && el.inputTinggiBalok.value.trim()));
    } else if (mode === 'kolom') {
      return !!((el.inputJumlahKolom && el.inputJumlahKolom.value.trim()) ||
                (el.inputTinggiKolom && el.inputTinggiKolom.value.trim()) ||
                (el.inputLebarKolom && el.inputLebarKolom.value.trim()) ||
                (el.inputTebalKolom && el.inputTebalKolom.value.trim()));
    } else if (mode === 'volume') {
      return !!(el.inputVolume && el.inputVolume.value.trim());
    }
    return false;
  }

  function isFormComplete() {
    var mode = getActiveMode();
    if (mode === 'plat') {
      return !!(el.inputPanjangPlat && el.inputPanjangPlat.value.trim() &&
                el.inputLebarPlat && el.inputLebarPlat.value.trim() &&
                el.inputTebalPlat && el.inputTebalPlat.value.trim());
    } else if (mode === 'balok') {
      return !!(el.inputPanjangBalok && el.inputPanjangBalok.value.trim() &&
                el.inputLebarBalok && el.inputLebarBalok.value.trim() &&
                el.inputTinggiBalok && el.inputTinggiBalok.value.trim());
    } else if (mode === 'kolom') {
      return !!(el.inputJumlahKolom && el.inputJumlahKolom.value.trim() &&
                el.inputTinggiKolom && el.inputTinggiKolom.value.trim() &&
                el.inputLebarKolom && el.inputLebarKolom.value.trim() &&
                el.inputTebalKolom && el.inputTebalKolom.value.trim());
    } else if (mode === 'volume') {
      return !!(el.inputVolume && el.inputVolume.value.trim());
    }
    return false;
  }

  function updateControls() {
    var anyIn = hasAnyInput();
    var complete = isFormComplete();

    if (el.clear) el.clear.disabled = (!anyIn && !state.lastResult) || state.busy;
    if (el.submit) el.submit.disabled = !complete || state.busy;
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    var url = serverBase + '/api/cor-beton/limits';
    fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('Status ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsData = data;
        state.limitsLoaded = true;
        updateMutuDisplay();
      })
      .catch(function () {
        setStatus('Tidak bisa menghubungi server. Coba lagi sebentar.', 'error');
      });
  }

  function submitCalc() {
    if (state.busy) return;
    if (!isFormComplete()) {
      setStatus('Isi semua ukuran yang diminta untuk mode ini.', 'error');
      return;
    }

    var mode = getActiveMode();
    var fd = new FormData();
    fd.append('mode', mode);

    if (mode === 'plat') {
      fd.append('panjang', el.inputPanjangPlat.value.trim());
      fd.append('lebar', el.inputLebarPlat.value.trim());
      fd.append('tinggi', el.inputTebalPlat.value.trim());
    } else if (mode === 'balok') {
      fd.append('panjang', el.inputPanjangBalok.value.trim());
      fd.append('lebar', el.inputLebarBalok.value.trim());
      fd.append('tinggi', el.inputTinggiBalok.value.trim());
    } else if (mode === 'kolom') {
      fd.append('jumlah', el.inputJumlahKolom.value.trim());
      fd.append('panjang', el.inputTinggiKolom.value.trim());
      fd.append('lebar', el.inputLebarKolom.value.trim());
      fd.append('tinggi', el.inputTebalKolom.value.trim());
    } else if (mode === 'volume') {
      fd.append('volume', el.inputVolume.value.trim());
    }

    if (el.mutu && el.mutu.value) fd.append('mutu', el.mutu.value);
    if (el.cadangan && el.cadangan.value.trim()) fd.append('cadangan', el.cadangan.value.trim());
    if (el.kapasitasTruk && el.kapasitasTruk.value) fd.append('kapasitas_truk', el.kapasitasTruk.value);

    if (el.hargaSemen && el.hargaSemen.value.trim()) fd.append('harga_semen', el.hargaSemen.value.trim());
    if (el.hargaPasir && el.hargaPasir.value.trim()) fd.append('harga_pasir', el.hargaPasir.value.trim());
    if (el.hargaKerikil && el.hargaKerikil.value.trim()) fd.append('harga_kerikil', el.hargaKerikil.value.trim());
    if (el.hargaReadymix && el.hargaReadymix.value.trim()) fd.append('harga_readymix', el.hargaReadymix.value.trim());

    state.busy = true;
    setStatus('Sedang menghitung kebutuhan cor beton...', 'busy');
    updateControls();

    var url = serverBase + '/api/cor-beton';
    fetch(url, {
      method: 'POST',
      body: fd,
      headers: { 'Accept': 'application/json' }
    })
      .then(function (res) {
        return res.json().then(function (json) {
          return { ok: res.ok, status: res.status, data: json };
        }).catch(function () {
          return { ok: res.ok, status: res.status, data: null };
        });
      })
      .then(function (result) {
        state.busy = false;
        updateControls();

        if (!result.ok) {
          var msg = 'Gagal menghitung kebutuhan cor beton.';
          if (result.data) {
            if (result.data.error && result.data.error.message) {
              msg = result.data.error.message;
            } else if (result.data.detail && result.data.detail.message) {
              msg = result.data.detail.message;
            } else if (typeof result.data.detail === 'string') {
              msg = result.data.detail;
            }
          }
          setStatus(msg, 'error');
          resetResults();
          return;
        }

        renderResult(result.data);
        setStatus('Selesai dihitung.', 'success');
      })
      .catch(function () {
        state.busy = false;
        updateControls();
        setStatus('Tidak bisa menghubungi server. Periksa koneksi internetmu.', 'error');
        resetResults();
      });
  }

  function renderResult(data) {
    state.lastResult = data;

    if (el.heroValue) el.heroValue.textContent = formatDesimal(data.volume_m3);
    if (el.heroSymbol) el.heroSymbol.textContent = 'm³ beton';

    if (el.summaryText) {
      var mutuLabel = (data.mutu && data.mutu.label) || 'K-225';
      el.summaryText.textContent = 'Perkiraan total beton jadi mutu ' + mutuLabel + ' (termasuk cadangan ' + data.cadangan_persen + '%).';
    }

    if (el.statVolKotor) el.statVolKotor.textContent = formatDesimal(data.volume_kotor_m3) + ' m³';
    if (el.statCadangan) el.statCadangan.textContent = data.cadangan_persen + '%';

    if (el.statSemen) {
      el.statSemen.textContent = formatRibuan(data.bahan.semen_sak) + ' sak (' + formatAngkaBerkoma(data.bahan.semen_kg) + ' kg)';
    }
    if (el.statPasir) el.statPasir.textContent = formatDesimal(data.bahan.pasir_m3) + ' m³';
    if (el.statKerikil) el.statKerikil.textContent = formatDesimal(data.bahan.kerikil_m3) + ' m³';
    if (el.statAir) el.statAir.textContent = formatAngkaBerkoma(data.bahan.air_liter) + ' liter';

    if (el.statTruk) {
      el.statTruk.textContent = formatRibuan(data.readymix.truk) + ' truk (' + data.readymix.kapasitas_truk_m3 + ' m³/truk)';
    }
    if (el.statSisaTruk) {
      el.statSisaTruk.textContent = formatDesimal(data.readymix.sisa_kapasitas_m3) + ' m³';
    }

    // Biaya
    if (el.biayaSection) {
      var adaBiaya = (data.biaya && (data.biaya.adukan !== null || data.biaya.readymix !== null));
      el.biayaSection.hidden = !adaBiaya;

      if (adaBiaya) {
        if (el.statBiayaAdukan) el.statBiayaAdukan.textContent = formatRupiah(data.biaya.adukan);
        if (el.statBiayaAdukanM3) el.statBiayaAdukanM3.textContent = data.biaya.per_m3_adukan ? (formatRupiah(data.biaya.per_m3_adukan) + ' / m³') : '-';
        if (el.statBiayaReadymix) el.statBiayaReadymix.textContent = formatRupiah(data.biaya.readymix);
        if (el.statBiayaReadymixM3) el.statBiayaReadymixM3.textContent = data.biaya.per_m3_readymix ? (formatRupiah(data.biaya.per_m3_readymix) + ' / m³') : '-';

        if (el.statBiayaSelisih) {
          if (data.biaya.selisih !== null) {
            var diff = data.biaya.selisih;
            el.statBiayaSelisih.textContent = formatRupiah(Math.abs(diff));
            if (el.statBiayaSelisihKet) {
              if (diff > 0) {
                el.statBiayaSelisihKet.textContent = 'Adukan sendiri lebih hemat ' + formatRupiah(diff) + ' dibanding readymix.';
              } else if (diff < 0) {
                el.statBiayaSelisihKet.textContent = 'Readymix lebih hemat ' + formatRupiah(Math.abs(diff)) + ' dibanding adukan sendiri.';
              } else {
                el.statBiayaSelisihKet.textContent = 'Perkiraan total biaya kedua metode sama.';
              }
            }
          } else {
            el.statBiayaSelisih.textContent = '-';
            if (el.statBiayaSelisihKet) el.statBiayaSelisihKet.textContent = 'Isi harga semen, pasir, kerikil, dan readymix untuk membandingkan selisih.';
          }
        }
      }
    }

    // Catatan
    if (el.notesList) {
      el.notesList.innerHTML = '';
      if (data.catatan && data.catatan.length) {
        for (var i = 0; i < data.catatan.length; i++) {
          var li = document.createElement('li');
          li.className = 'cb__notes-item';
          li.textContent = data.catatan[i];
          el.notesList.appendChild(li);
        }
      }
    }

    if (el.outputWrap) el.outputWrap.hidden = false;
    if (el.resultHint) el.resultHint.hidden = true;
    updateControls();
  }

  function buildSummaryText(data) {
    if (!data) return '';
    var lines = [];
    lines.push('HITUNG KEBUTUHAN COR BETON');
    lines.push('===========================');
    lines.push('Mode: ' + data.mode.toUpperCase());
    if (data.mutu) lines.push('Mutu beton: ' + data.mutu.label);
    lines.push('Volume kotor: ' + formatDesimal(data.volume_kotor_m3) + ' m³');
    lines.push('Cadangan: ' + data.cadangan_persen + '%');
    lines.push('Total volume cor: ' + formatDesimal(data.volume_m3) + ' m³');
    lines.push('');
    lines.push('KEBUTUHAN BAHAN (ADUKAN SENDIRI):');
    lines.push('- Semen (sak 50 kg): ' + formatRibuan(data.bahan.semen_sak) + ' sak (' + formatAngkaBerkoma(data.bahan.semen_kg) + ' kg)');
    lines.push('- Pasir pasang: ' + formatDesimal(data.bahan.pasir_m3) + ' m³');
    lines.push('- Kerikil / split: ' + formatDesimal(data.bahan.kerikil_m3) + ' m³');
    lines.push('- Air: ' + formatAngkaBerkoma(data.bahan.air_liter) + ' liter');
    lines.push('');
    lines.push('KEBUTUHAN READYMIX:');
    lines.push('- Jumlah truk mixer: ' + formatRibuan(data.readymix.truk) + ' truk (' + data.readymix.kapasitas_truk_m3 + ' m³/truk)');
    lines.push('- Sisa kapasitas muatan: ' + formatDesimal(data.readymix.sisa_kapasitas_m3) + ' m³');

    if (data.biaya && (data.biaya.adukan !== null || data.biaya.readymix !== null)) {
      lines.push('');
      lines.push('PERKIRAAN BIAYA:');
      if (data.biaya.adukan !== null) {
        lines.push('- Adukan sendiri: ' + formatRupiah(data.biaya.adukan) + ' (' + formatRupiah(data.biaya.per_m3_adukan) + ' / m³)');
      }
      if (data.biaya.readymix !== null) {
        lines.push('- Readymix: ' + formatRupiah(data.biaya.readymix) + ' (' + formatRupiah(data.biaya.per_m3_readymix) + ' / m³)');
      }
      if (data.biaya.selisih !== null) {
        lines.push('- Selisih: ' + formatRupiah(Math.abs(data.biaya.selisih)));
      }
    }

    lines.push('');
    lines.push('CATATAN:');
    if (data.catatan && data.catatan.length) {
      for (var i = 0; i < data.catatan.length; i++) {
        lines.push('- ' + data.catatan[i]);
      }
    }
    lines.push('');
    lines.push('Dihitung di bahzi.fun (OmniTools)');
    return lines.join('\n');
  }

  function copyResult() {
    if (!state.lastResult) return;
    var text = buildSummaryText(state.lastResult);

    function notifySuccess() {
      if (el.copy) {
        var prev = el.copy.textContent;
        el.copy.textContent = 'Tersalin!';
        setTimeout(function () { el.copy.textContent = prev; }, 1800);
      }
      setStatus('Hasil disalin ke papan klip.', 'success');
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(notifySuccess).catch(function () {
        fallbackCopy(text, notifySuccess);
      });
    } else {
      fallbackCopy(text, notifySuccess);
    }
  }

  function fallbackCopy(text, cb) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      if (cb) cb();
    } catch (e) {
      setStatus('Tidak bisa menyalin teks ke papan klip.', 'error');
    }
    document.body.removeChild(ta);
  }

  function downloadResult() {
    if (!state.lastResult) return;
    var text = buildSummaryText(state.lastResult);
    revokeDownload();
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    state.downloadUrl = url;

    var a = document.createElement('a');
    a.href = url;
    a.download = 'hitung-cor-beton-' + Date.now() + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatus('Berkas .txt berhasil diunduh.', 'success');
  }

  function resetAll() {
    if (el.inputPanjangPlat) el.inputPanjangPlat.value = '';
    if (el.inputLebarPlat) el.inputLebarPlat.value = '';
    if (el.inputTebalPlat) el.inputTebalPlat.value = '';

    if (el.inputPanjangBalok) el.inputPanjangBalok.value = '';
    if (el.inputLebarBalok) el.inputLebarBalok.value = '';
    if (el.inputTinggiBalok) el.inputTinggiBalok.value = '';

    if (el.inputJumlahKolom) el.inputJumlahKolom.value = '';
    if (el.inputTinggiKolom) el.inputTinggiKolom.value = '';
    if (el.inputLebarKolom) el.inputLebarKolom.value = '';
    if (el.inputTebalKolom) el.inputTebalKolom.value = '';

    if (el.inputVolume) el.inputVolume.value = '';

    if (el.mutu) el.mutu.value = 'k225';
    if (el.cadangan) el.cadangan.value = '5';
    if (el.kapasitasTruk) el.kapasitasTruk.value = '7';

    if (el.hargaSemen) el.hargaSemen.value = '';
    if (el.hargaPasir) el.hargaPasir.value = '';
    if (el.hargaKerikil) el.hargaKerikil.value = '';
    if (el.hargaReadymix) el.hargaReadymix.value = '';

    updateMutuDisplay();
    resetResults();
    setStatus('Pilih mode, masukkan ukuran, lalu tekan "Hitung kebutuhan".', '');
    updateControls();

    var mode = getActiveMode();
    if (mode === 'plat' && el.inputPanjangPlat) el.inputPanjangPlat.focus();
    else if (mode === 'balok' && el.inputPanjangBalok) el.inputPanjangBalok.focus();
    else if (mode === 'kolom' && el.inputJumlahKolom) el.inputJumlahKolom.focus();
    else if (mode === 'volume' && el.inputVolume) el.inputVolume.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="cor-beton"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'cor-beton-panel');
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

    var mode = getActiveMode();
    var firstInput = el.inputPanjangPlat;
    if (mode === 'balok') firstInput = el.inputPanjangBalok;
    else if (mode === 'kolom') firstInput = el.inputJumlahKolom;
    else if (mode === 'volume') firstInput = el.inputVolume;

    if (firstInput) {
      setTimeout(function () { firstInput.focus(); }, 100);
    }
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    syncTriggers(false);
    revokeDownload();
    if (state.lastFocus && state.lastFocus !== document.body && typeof state.lastFocus.focus === 'function' && document.contains(state.lastFocus)) {
      state.lastFocus.focus();
    } else {
      var trigger = document.querySelector('.tool-card__open[data-tool-action="cor-beton"]');
      if (trigger && typeof trigger.focus === 'function') {
        trigger.focus();
      }
    }
    state.lastFocus = null;
  }

  function toggle() {
    if (panel.hidden) open();
    else close();
  }

  // Event listeners
  if (el.close) el.close.addEventListener('click', close);

  var modeRadios = [el.modePlat, el.modeBalok, el.modeKolom, el.modeVolume];
  for (var m = 0; m < modeRadios.length; m++) {
    if (modeRadios[m]) {
      modeRadios[m].addEventListener('change', updateModeVisibility);
    }
  }

  if (el.mutu) {
    el.mutu.addEventListener('change', function () {
      updateMutuDisplay();
      resetResults();
      updateControls();
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (isFormComplete()) submitCalc();
    }
  }

  var inputs = [
    el.inputPanjangPlat, el.inputLebarPlat, el.inputTebalPlat,
    el.inputPanjangBalok, el.inputLebarBalok, el.inputTinggiBalok,
    el.inputJumlahKolom, el.inputTinggiKolom, el.inputLebarKolom, el.inputTebalKolom,
    el.inputVolume, el.cadangan, el.kapasitasTruk,
    el.hargaSemen, el.hargaPasir, el.hargaKerikil, el.hargaReadymix
  ];

  for (var i = 0; i < inputs.length; i++) {
    if (inputs[i]) {
      inputs[i].addEventListener('input', function () {
        resetResults();
        updateControls();
      });
      inputs[i].addEventListener('keydown', onInputKeydown);
    }
  }

  if (el.submit) el.submit.addEventListener('click', submitCalc);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  if (el.linkBata) {
    el.linkBata.addEventListener('click', function () {
      close();
      if (window.OmniToolsPanels && typeof window.OmniToolsPanels['bata'] === 'function') {
        window.OmniToolsPanels['bata']();
      }
    });
  }

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

  // Daftarkan panel supaya kartu Hitung kebutuhan cor beton bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['cor-beton'] = toggle;

  // Inisialisasi bawaan
  updateModeVisibility();
  updateMutuDisplay();
  updateControls();
})();
