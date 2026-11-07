/* =========================================================================
   Panel alat: Hitung kalori & berat badan ideal
   Menghitung kebutuhan kalori harian (BMR Mifflin-St Jeor & TDEE),
   Indeks Massa Tubuh (IMT) batas Asia-Pasifik, rentang berat ideal,
   dan perkiraan waktu pencapaian target.
   Diproses murni di memori. Tanpa penyimpanan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('kalori-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('kalori-close'),
    // Jenis kelamin radios
    jkPria: document.getElementById('kalori-jk-pria'),
    jkWanita: document.getElementById('kalori-jk-wanita'),
    // Inputs
    inputUmur: document.getElementById('kalori-umur'),
    inputTinggi: document.getElementById('kalori-tinggi'),
    inputBerat: document.getElementById('kalori-berat'),
    selectAktivitas: document.getElementById('kalori-aktivitas'),
    // Target radios
    targetTurun: document.getElementById('kalori-target-turun'),
    targetTetap: document.getElementById('kalori-target-tetap'),
    targetNaik: document.getElementById('kalori-target-naik'),
    // Laju row & select
    rowLaju: document.getElementById('kalori-row-laju'),
    selectLaju: document.getElementById('kalori-laju'),
    // Buttons & Status
    status: document.getElementById('kalori-status'),
    clear: document.getElementById('kalori-clear'),
    submit: document.getElementById('kalori-submit'),
    // Results
    results: document.getElementById('kalori-results'),
    resultHint: document.getElementById('kalori-result-hint'),
    outputWrap: document.getElementById('kalori-output-wrap'),
    heroLabel: document.getElementById('kalori-hero-label'),
    heroValue: document.getElementById('kalori-hero-value'),
    summaryText: document.getElementById('kalori-summary-text'),
    // Stats
    statBmr: document.getElementById('kalori-stat-bmr'),
    statTdee: document.getElementById('kalori-stat-tdee'),
    statImt: document.getElementById('kalori-stat-imt'),
    statIdeal: document.getElementById('kalori-stat-ideal'),
    statSelisihWrap: document.getElementById('kalori-stat-selisih-wrap'),
    statSelisihLabel: document.getElementById('kalori-stat-selisih-label'),
    statSelisihValue: document.getElementById('kalori-stat-selisih-value'),
    statWaktuWrap: document.getElementById('kalori-stat-waktu-wrap'),
    statWaktuValue: document.getElementById('kalori-stat-waktu-value'),
    // Notes & Copy
    catatanList: document.getElementById('kalori-catatan-list'),
    copy: document.getElementById('kalori-copy')
  };

  var state = {
    busy: false,
    lastFocus: null,
    lastResult: null
  };

  function formatRibuan(n) {
    if (n === null || n === undefined || isNaN(n)) return '0';
    var num = Math.round(Number(n));
    var sign = num < 0 ? '-' : '';
    var absStr = Math.abs(num).toString();
    return sign + absStr.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function formatAngka(val, maxDesimal) {
    if (val === null || val === undefined || isNaN(val)) return '0';
    var d = typeof maxDesimal === 'number' ? maxDesimal : 1;
    var num = Number(val);
    var isNeg = num < 0;
    var formatted = Math.abs(num).toFixed(d);
    var parts = formatted.split('.');
    var bulat = parseInt(parts[0], 10);
    var bulatStr = bulat.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    if (parts.length > 1) {
      var des = parts[1].replace(/0+$/, '');
      return (isNeg ? '-' : '') + (des ? bulatStr + ',' + des : bulatStr);
    }
    return (isNeg ? '-' : '') + bulatStr;
  }

  function kapitalHuruf(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  function setStatus(message, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status' + (kind ? ' status--' + kind : '');
    if (kind === 'error') {
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

  function getJenisKelamin() {
    if (el.jkWanita && el.jkWanita.checked) return 'wanita';
    return 'pria';
  }

  function getTarget() {
    if (el.targetTurun && el.targetTurun.checked) return 'turun';
    if (el.targetNaik && el.targetNaik.checked) return 'naik';
    return 'tetap';
  }

  function updateTargetVisibility() {
    var target = getTarget();
    if (el.rowLaju) {
      el.rowLaju.hidden = (target === 'tetap');
    }
    resetResults();
    updateControls();
  }

  function resetResults() {
    state.lastResult = null;
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.heroLabel) el.heroLabel.textContent = '';
    if (el.summaryText) el.summaryText.textContent = '';
    if (el.statBmr) el.statBmr.textContent = '';
    if (el.statTdee) el.statTdee.textContent = '';
    if (el.statImt) el.statImt.textContent = '';
    if (el.statIdeal) el.statIdeal.textContent = '';
    if (el.statSelisihWrap) el.statSelisihWrap.hidden = true;
    if (el.statSelisihValue) el.statSelisihValue.textContent = '';
    if (el.statWaktuWrap) el.statWaktuWrap.hidden = true;
    if (el.statWaktuValue) el.statWaktuValue.textContent = '';
    if (el.catatanList) el.catatanList.innerHTML = '';
  }

  function updateControls() {
    if (state.busy) {
      if (el.submit) {
        el.submit.disabled = true;
        el.submit.textContent = 'Menghitung…';
      }
      if (el.clear) el.clear.disabled = true;
      return;
    }

    if (el.submit) el.submit.textContent = 'Hitung kalori';

    var umur = el.inputUmur ? el.inputUmur.value.trim() : '';
    var tinggi = el.inputTinggi ? el.inputTinggi.value.trim() : '';
    var berat = el.inputBerat ? el.inputBerat.value.trim() : '';
    var aktivitas = el.selectAktivitas ? el.selectAktivitas.value : '';

    var isValid = (umur !== '' && tinggi !== '' && berat !== '' && aktivitas !== '');
    if (el.submit) el.submit.disabled = !isValid;

    var hasValue = (umur !== '' || tinggi !== '' || berat !== '' || aktivitas !== 'sedang' || getTarget() !== 'tetap');
    if (el.clear) el.clear.disabled = !hasValue;
  }

  function renderResult(data) {
    state.lastResult = data;

    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    // Angka besar target kalori
    if (el.heroLabel) el.heroLabel.textContent = 'Target kalori harian';
    if (el.heroValue) el.heroValue.textContent = formatRibuan(data.kalori_target) + ' kkal per hari';

    // Kalimat ringkasan
    if (el.summaryText) {
      var s = '';
      if (data.dibatasi) {
        if (data.target !== 'tetap') {
          var selisihSebenarnya = Math.round(Math.abs(Number(data.tdee) - Number(data.kalori_target)));
          s = 'Selisih hanya sekitar ' + formatRibuan(selisihSebenarnya) + ' kkal per hari, bukan ' + formatRibuan(data.selisih_harian) + ' kkal seperti yang diminta, karena angka target dinaikkan ke batas aman 1.200 kkal per hari.';
        } else {
          s = 'Kebutuhan kalori harian untuk menjaga berat badanmu di sekitar ' + formatAngka(data.berat_sekarang, 1) + ' kg. Angka target dinaikkan ke batas aman 1.200 kkal per hari.';
        }
      } else if (data.target === 'tetap') {
        s = 'Kebutuhan kalori harian untuk menjaga berat badanmu di sekitar ' + formatAngka(data.berat_sekarang, 1) + ' kg.';
      } else if (data.target === 'turun') {
        s = 'Defisit sekitar ' + formatRibuan(data.selisih_harian) + ' kkal per hari untuk menurunkan berat badan ~' + formatAngka(data.kg_per_minggu, 2) + ' kg per minggu.';
      } else {
        s = 'Surplus sekitar ' + formatRibuan(data.selisih_harian) + ' kkal per hari untuk menaikkan berat badan ~' + formatAngka(data.kg_per_minggu, 2) + ' kg per minggu.';
      }
      el.summaryText.textContent = s;
    }

    // Kartu statistik
    if (el.statBmr) el.statBmr.textContent = formatRibuan(data.bmr) + ' kkal';
    if (el.statTdee) el.statTdee.textContent = formatRibuan(data.tdee) + ' kkal';
    if (el.statImt) {
      el.statImt.textContent = formatAngka(data.imt, 2) + ' (' + kapitalHuruf(data.imt_kategori) + ')';
    }
    if (el.statIdeal) {
      el.statIdeal.textContent = formatAngka(data.berat_ideal_min, 1) + ' – ' + formatAngka(data.berat_ideal_maks, 1) + ' kg';
    }

    // Selisih ke berat ideal
    if (el.statSelisihWrap) {
      if (data.selisih_berat_ke_ideal !== null && data.selisih_berat_ke_ideal !== undefined) {
        el.statSelisihWrap.hidden = false;
        if (el.statSelisihLabel) {
          el.statSelisihLabel.textContent = (data.berat_sekarang > data.berat_ideal_maks)
            ? 'Kelebihan dari batas ideal'
            : 'Kekurangan dari batas ideal';
        }
        if (el.statSelisihValue) {
          el.statSelisihValue.textContent = formatAngka(data.selisih_berat_ke_ideal, 1) + ' kg';
        }
      } else {
        el.statSelisihWrap.hidden = false;
        if (el.statSelisihLabel) el.statSelisihLabel.textContent = 'Posisi berat badan';
        if (el.statSelisihValue) el.statSelisihValue.textContent = 'Sudah di rentang ideal';
      }
    }

    // Perkiraan waktu
    if (el.statWaktuWrap) {
      if (data.perkiraan_minggu !== null && data.perkiraan_minggu !== undefined) {
        el.statWaktuWrap.hidden = false;
        var waktuText = data.perkiraan_minggu + ' minggu';
        if (data.perkiraan_bulan_teks) {
          waktuText += ' (' + data.perkiraan_bulan_teks + ')';
        }
        if (el.statWaktuValue) el.statWaktuValue.textContent = waktuText;
      } else {
        el.statWaktuWrap.hidden = true;
      }
    }

    // Catatan jujur
    if (el.catatanList) {
      el.catatanList.innerHTML = '';
      if (Array.isArray(data.catatan)) {
        for (var i = 0; i < data.catatan.length; i++) {
          var li = document.createElement('li');
          li.className = 'kk__notes-item';
          li.textContent = data.catatan[i];
          el.catatanList.appendChild(li);
        }
      }
    }

    setStatus('Kebutuhan kalori dan berat ideal berhasil dihitung.', 'ok');
  }

  function submitCalc() {
    if (state.busy) return;

    var jk = getJenisKelamin();
    var umur = el.inputUmur ? el.inputUmur.value.trim() : '';
    var tinggi = el.inputTinggi ? el.inputTinggi.value.trim() : '';
    var berat = el.inputBerat ? el.inputBerat.value.trim() : '';
    var aktivitas = el.selectAktivitas ? el.selectAktivitas.value : '';
    var target = getTarget();
    var laju = el.selectLaju ? el.selectLaju.value : 'sedang';

    if (!umur) {
      setStatus('Isi umur terlebih dahulu.', 'error');
      if (el.inputUmur) el.inputUmur.focus();
      return;
    }
    if (!tinggi) {
      setStatus('Isi tinggi badan terlebih dahulu.', 'error');
      if (el.inputTinggi) el.inputTinggi.focus();
      return;
    }
    if (!berat) {
      setStatus('Isi berat badan terlebih dahulu.', 'error');
      if (el.inputBerat) el.inputBerat.focus();
      return;
    }

    var fd = new FormData();
    fd.append('jenis_kelamin', jk);
    fd.append('umur', umur);
    fd.append('tinggi', tinggi);
    fd.append('berat', berat);
    fd.append('aktivitas', aktivitas);
    fd.append('target', target);
    if (target !== 'tetap') {
      fd.append('laju', laju);
    }

    state.busy = true;
    updateControls();
    setStatus('Menghitung perkiraan kalori…', 'busy');

    fetch(serverBase + '/api/kalori', {
      method: 'POST',
      body: fd
    })
      .then(function (response) {
        return response.json().then(function (json) {
          if (!response.ok) {
            var msg = 'Terjadi kendala saat menghitung kalori.';
            if (json && json.error && json.error.message) {
              msg = json.error.message;
            } else if (json && json.detail && json.detail.message) {
              msg = json.detail.message;
            } else if (json && typeof json.detail === 'string') {
              msg = json.detail;
            }
            var err = new Error(msg);
            err.pesanLayanan = true;
            throw err;
          }
          return json;
        }).catch(function (err) {
          if (err && err.pesanLayanan) throw err;
          var e = new Error(
            response.status === 413
              ? 'Ukuran permintaan melebihi batas 64 KB.'
              : 'Terjadi kendala saat menghubungi server (HTTP ' + response.status + '). Coba lagi sebentar.'
          );
          e.pesanLayanan = true;
          throw e;
        });
      })
      .then(function (data) {
        state.busy = false;
        renderResult(data);
        updateControls();
      })
      .catch(function (err) {
        state.busy = false;
        resetResults();
        var msg = (err && err.pesanLayanan === true && err.message)
          ? err.message
          : 'Tidak bisa menghubungi server. Coba lagi sebentar.';
        setStatus(msg, 'error');
        updateControls();
      });
  }

  function resetAll() {
    if (el.jkPria) el.jkPria.checked = true;
    if (el.inputUmur) el.inputUmur.value = '';
    if (el.inputTinggi) el.inputTinggi.value = '';
    if (el.inputBerat) el.inputBerat.value = '';
    if (el.selectAktivitas) el.selectAktivitas.value = 'sedang';
    if (el.targetTetap) el.targetTetap.checked = true;
    if (el.selectLaju) el.selectLaju.value = 'sedang';

    updateTargetVisibility();
    resetResults();
    setStatus('Isi data fisik dan aktivitasmu, lalu tekan tombol hitung.', '');
    updateControls();

    if (el.inputUmur) el.inputUmur.focus();
  }

  function copySummary() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var lines = [];
    lines.push('Hitung Kalori & Berat Badan Ideal - bahzi.fun');
    lines.push('----------------------------------------');
    lines.push('Jenis kelamin: ' + (d.jenis_kelamin === 'wanita' ? 'Wanita' : 'Pria'));
    lines.push('Berat sekarang: ' + formatAngka(d.berat_sekarang, 1) + ' kg');
    lines.push('Aktivitas: ' + kapitalHuruf(d.aktivitas) + ' (faktor ' + formatAngka(d.aktivitas_faktor, 3) + ')');
    var targetLabel = 'Jaga berat badan';
    if (d.target === 'turun') targetLabel = 'Turunkan berat badan';
    if (d.target === 'naik') targetLabel = 'Naikkan berat badan';
    lines.push('Target: ' + targetLabel + (d.laju && d.target !== 'tetap' ? ' (Laju: ' + d.laju + ')' : ''));
    lines.push('');
    lines.push('Target kalori harian: ' + formatRibuan(d.kalori_target) + ' kkal per hari' + (d.dibatasi ? ' (batas aman)' : ''));
    lines.push('BMR (Basal Metabolic Rate): ' + formatRibuan(d.bmr) + ' kkal');
    lines.push('TDEE (Kebutuhan harian): ' + formatRibuan(d.tdee) + ' kkal');
    lines.push('IMT: ' + formatAngka(d.imt, 2) + ' (' + kapitalHuruf(d.imt_kategori) + ')');
    lines.push('Rentang berat ideal: ' + formatAngka(d.berat_ideal_min, 1) + ' – ' + formatAngka(d.berat_ideal_maks, 1) + ' kg');
    if (d.selisih_berat_ke_ideal !== null && d.selisih_berat_ke_ideal !== undefined) {
      lines.push('Selisih ke berat ideal: ' + formatAngka(d.selisih_berat_ke_ideal, 1) + ' kg');
    }
    if (d.perkiraan_minggu !== null && d.perkiraan_minggu !== undefined) {
      lines.push('Perkiraan waktu: ' + d.perkiraan_minggu + ' minggu' + (d.perkiraan_bulan_teks ? ' (' + d.perkiraan_bulan_teks + ')' : ''));
    }
    lines.push('----------------------------------------');
    lines.push('* Rumus Mifflin-St Jeor & batas IMT Asia-Pasifik. Bukan nasihat medis.');

    var text = lines.join('\n');

    function notify(ok) {
      if (ok) {
        setStatus('Ringkasan berhasil disalin ke papan klip.', 'ok');
      } else {
        setStatus('Gagal menyalin ringkasan.', 'error');
      }
      if (el.copy) {
        var orig = el.copy.textContent;
        el.copy.textContent = ok ? 'Tersalin!' : 'Gagal';
        setTimeout(function () { el.copy.textContent = orig; }, 1500);
      }
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text).then(function () {
        notify(true);
      }).catch(function () {
        notify(false);
      });
    } else {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
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

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="kalori"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'kalori-panel');
    }
  }

  function open() {
    if (!panel.hidden) return;
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);

    var reduceMotion = false;
    try {
      reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { /* abaikan */ }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    var firstInput = el.inputUmur;
    if (firstInput) {
      setTimeout(function () { firstInput.focus(); }, 100);
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

  if (el.jkPria) el.jkPria.addEventListener('change', function () { resetResults(); updateControls(); });
  if (el.jkWanita) el.jkWanita.addEventListener('change', function () { resetResults(); updateControls(); });

  var textInputs = [el.inputUmur, el.inputTinggi, el.inputBerat];
  for (var i = 0; i < textInputs.length; i++) {
    if (textInputs[i]) {
      textInputs[i].addEventListener('input', function () {
        resetResults();
        updateControls();
      });
    }
  }

  if (el.selectAktivitas) {
    el.selectAktivitas.addEventListener('change', function () {
      resetResults();
      updateControls();
    });
  }

  if (el.targetTurun) el.targetTurun.addEventListener('change', updateTargetVisibility);
  if (el.targetTetap) el.targetTetap.addEventListener('change', updateTargetVisibility);
  if (el.targetNaik) el.targetNaik.addEventListener('change', updateTargetVisibility);

  if (el.selectLaju) {
    el.selectLaju.addEventListener('change', function () {
      resetResults();
      updateControls();
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitCalc);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copySummary);

  function onKeydown(e) {
    if (panel.hidden) return;
    if (e.key === 'Escape' && panel.contains(document.activeElement)) {
      e.preventDefault();
      close();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      if (panel.contains(document.activeElement) && el.submit && !el.submit.disabled) {
        e.preventDefault();
        submitCalc();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);

  // Daftarkan panel ke daftar panel OmniTools
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['kalori'] = toggle;

  // Inisialisasi awal
  updateTargetVisibility();
  updateControls();
})();
