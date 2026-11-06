/* =========================================================================
   Panel alat: Simulasi tabungan
   Menghitung hasil akhir tabungan, perkiraan setoran bulanan untuk sebuah
   target, atau berapa lama sebuah target tabungan tercapai.
   Diproses murni di memori lalu dibuang. Tanpa penyimpanan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('tabungan-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    close: document.getElementById('tabungan-close'),
    // Mode radios
    modeHasil: document.getElementById('tabungan-mode-hasil'),
    modeSetoran: document.getElementById('tabungan-mode-setoran'),
    modeLama: document.getElementById('tabungan-mode-lama'),
    // Rows / field wrappers
    rowTarget: document.getElementById('tabungan-row-target'),
    rowSetoranAwal: document.getElementById('tabungan-row-setoran-awal'),
    rowSetoranBulanan: document.getElementById('tabungan-row-setoran-bulanan'),
    rowBungaTahunan: document.getElementById('tabungan-row-bunga-tahunan'),
    rowLamaTahun: document.getElementById('tabungan-row-lama-tahun'),
    // Inputs
    inputTarget: document.getElementById('tabungan-target'),
    inputSetoranAwal: document.getElementById('tabungan-setoran-awal'),
    inputSetoranBulanan: document.getElementById('tabungan-setoran-bulanan'),
    inputBungaTahunan: document.getElementById('tabungan-bunga-tahunan'),
    inputLamaTahun: document.getElementById('tabungan-lama-tahun'),
    // Buttons & Status
    status: document.getElementById('tabungan-status'),
    clear: document.getElementById('tabungan-clear'),
    submit: document.getElementById('tabungan-submit'),
    // Results
    results: document.getElementById('tabungan-results'),
    resultHint: document.getElementById('tabungan-result-hint'),
    outputWrap: document.getElementById('tabungan-output-wrap'),
    heroLabel: document.getElementById('tabungan-hero-label'),
    heroValue: document.getElementById('tabungan-hero-value'),
    summaryText: document.getElementById('tabungan-summary-text'),
    // Stats
    statSetoran: document.getElementById('tabungan-stat-setoran'),
    statBunga: document.getElementById('tabungan-stat-bunga'),
    statWaktu: document.getElementById('tabungan-stat-waktu'),
    statExtraWrap: document.getElementById('tabungan-stat-extra-wrap'),
    statExtraLabel: document.getElementById('tabungan-stat-extra-label'),
    statExtraValue: document.getElementById('tabungan-stat-extra-value'),
    // Table & Notes
    tabelTbody: document.getElementById('tabungan-tabel-tbody'),
    catatanText: document.getElementById('tabungan-catatan-text'),
    copy: document.getElementById('tabungan-copy')
  };

  var state = {
    mode: 'hasil',
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

  function formatRupiah(n) {
    if (n === null || n === undefined || isNaN(n)) return 'Rp 0';
    return 'Rp ' + formatRibuan(n);
  }

  function formatBulanTahun(totalBulan) {
    var b = Math.max(0, parseInt(totalBulan, 10) || 0);
    var tahun = Math.floor(b / 12);
    var sisaBulan = b % 12;
    if (tahun > 0 && sisaBulan > 0) {
      return tahun + ' tahun ' + sisaBulan + ' bulan';
    } else if (tahun > 0) {
      return tahun + ' tahun';
    }
    return sisaBulan + ' bulan';
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

  function getActiveMode() {
    if (el.modeSetoran && el.modeSetoran.checked) return 'setoran';
    if (el.modeLama && el.modeLama.checked) return 'lama';
    return 'hasil';
  }

  function updateModeVisibility() {
    state.mode = getActiveMode();

    if (el.rowTarget) el.rowTarget.hidden = (state.mode === 'hasil');
    if (el.rowSetoranAwal) el.rowSetoranAwal.hidden = false;
    if (el.rowSetoranBulanan) el.rowSetoranBulanan.hidden = (state.mode === 'setoran');
    if (el.rowBungaTahunan) el.rowBungaTahunan.hidden = false;
    if (el.rowLamaTahun) el.rowLamaTahun.hidden = (state.mode === 'lama');

    if (el.submit) {
      if (state.mode === 'hasil') {
        el.submit.textContent = state.busy ? 'Menghitung…' : 'Hitung tabungan';
      } else if (state.mode === 'setoran') {
        el.submit.textContent = state.busy ? 'Menghitung…' : 'Cari setoran bulanan';
      } else {
        el.submit.textContent = state.busy ? 'Menghitung…' : 'Lihat lama waktunya';
      }
    }

    resetResults();
    setStatus('Pilih mode, isi data tabungan, lalu tekan tombol hitung.', '');
    updateControls();
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.heroValue) el.heroValue.textContent = '';
    if (el.heroLabel) el.heroLabel.textContent = '';
    if (el.summaryText) el.summaryText.textContent = '';
    if (el.statSetoran) el.statSetoran.textContent = '';
    if (el.statBunga) el.statBunga.textContent = '';
    if (el.statWaktu) el.statWaktu.textContent = '';
    if (el.statExtraWrap) el.statExtraWrap.hidden = true;
    if (el.statExtraValue) el.statExtraValue.textContent = '';
    if (el.tabelTbody) el.tabelTbody.innerHTML = '';
    if (el.catatanText) el.catatanText.textContent = '';
    state.lastResult = null;
  }

  function updateControls() {
    var mode = getActiveMode();
    var valTarget = el.inputTarget ? el.inputTarget.value.trim() : '';
    var valAwal = el.inputSetoranAwal ? el.inputSetoranAwal.value.trim() : '';
    var valBulanan = el.inputSetoranBulanan ? el.inputSetoranBulanan.value.trim() : '';
    var valBunga = el.inputBungaTahunan ? el.inputBungaTahunan.value.trim() : '';
    var valLama = el.inputLamaTahun ? el.inputLamaTahun.value.trim() : '';

    var ready = false;
    var hasAny = Boolean(valTarget || valAwal || valBulanan || valBunga || valLama);

    if (mode === 'hasil') {
      ready = Boolean(valAwal && valBulanan && valBunga && valLama);
    } else if (mode === 'setoran') {
      ready = Boolean(valTarget && valAwal && valBunga && valLama);
    } else if (mode === 'lama') {
      ready = Boolean(valTarget && valAwal && valBulanan && valBunga);
    }

    if (el.submit) {
      el.submit.disabled = state.busy || !ready;
      if (state.busy) {
        el.submit.textContent = 'Menghitung…';
      } else {
        if (mode === 'hasil') el.submit.textContent = 'Hitung tabungan';
        else if (mode === 'setoran') el.submit.textContent = 'Cari setoran bulanan';
        else el.submit.textContent = 'Lihat lama waktunya';
      }
    }

    if (el.clear) {
      el.clear.disabled = state.busy || (!hasAny && !state.lastResult);
    }
  }

  function cleanRupiahValue(str) {
    if (!str) return '0';
    return str.replace(/\D/g, '') || '0';
  }

  function formatInputField(input) {
    if (!input) return;
    var rawDigits = input.value.replace(/\D/g, '');
    if (!rawDigits) {
      input.value = '';
    } else {
      input.value = rawDigits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }
    updateControls();
  }

  function renderResult(data) {
    if (!data) return;
    state.lastResult = data;

    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    // Hero
    if (el.heroValue) el.heroValue.textContent = formatRupiah(data.saldo_akhir);
    if (el.heroLabel) {
      if (data.mode === 'setoran') {
        el.heroLabel.textContent = 'Perkiraan saldo akhir (target tercapai)';
      } else if (data.mode === 'lama') {
        el.heroLabel.textContent = 'Perkiraan saldo akhir saat target tercapai';
      } else {
        el.heroLabel.textContent = 'Perkiraan saldo akhir tabungan';
      }
    }

    // Kalimat ringkasan
    if (el.summaryText) {
      if (data.mode === 'setoran') {
        el.summaryText.textContent = 'Sisihkan ' + formatRupiah(data.setoran_bulanan_disarankan) +
          ' per bulan selama ' + data.lama_tahun + ' tahun untuk mencapai target ' + formatRupiah(data.target) + '.';
      } else if (data.mode === 'lama') {
        el.summaryText.textContent = 'Target ' + formatRupiah(data.target) + ' tercapai dalam ' +
          data.bulan_ke_target + ' bulan (sekitar ' + formatBulanTahun(data.bulan_ke_target) + ').';
      } else {
        el.summaryText.textContent = 'Dengan setoran awal ' + formatRupiah(data.setoran_awal) +
          ' dan menabung ' + formatRupiah(data.setoran_bulanan) + '/bulan selama ' + data.lama_tahun +
          ' tahun, terkumpul ' + formatRupiah(data.saldo_akhir) + '.';
      }
    }

    // Grid statistik
    if (el.statSetoran) el.statSetoran.textContent = formatRupiah(data.total_setoran);
    if (el.statBunga) el.statBunga.textContent = formatRupiah(data.total_bunga);
    if (el.statWaktu) {
      if (data.mode === 'lama') {
        el.statWaktu.textContent = data.bulan_ke_target + ' bulan (' + formatBulanTahun(data.bulan_ke_target) + ')';
      } else {
        el.statWaktu.textContent = data.lama_tahun + ' tahun (' + data.lama_bulan + ' bulan)';
      }
    }

    // Kartu info khusus
    if (el.statExtraWrap) {
      if (data.mode === 'setoran') {
        el.statExtraWrap.hidden = false;
        if (el.statExtraLabel) el.statExtraLabel.textContent = 'Setoran bulanan disarankan';
        if (el.statExtraValue) el.statExtraValue.textContent = formatRupiah(data.setoran_bulanan_disarankan);
      } else if (data.mode === 'lama') {
        el.statExtraWrap.hidden = false;
        if (el.statExtraLabel) el.statExtraLabel.textContent = 'Waktu capai target';
        if (el.statExtraValue) el.statExtraValue.textContent = formatBulanTahun(data.bulan_ke_target);
      } else {
        el.statExtraWrap.hidden = true;
      }
    }

    // Tabel tahunan
    if (el.tabelTbody) {
      el.tabelTbody.innerHTML = '';
      if (Array.isArray(data.tabel_tahunan) && data.tabel_tahunan.length > 0) {
        var frag = document.createDocumentFragment();
        for (var i = 0; i < data.tabel_tahunan.length; i++) {
          var row = data.tabel_tahunan[i];
          var tr = document.createElement('tr');

          var tdTahun = document.createElement('td');
          tdTahun.textContent = 'Tahun ke-' + row.tahun;
          tr.appendChild(tdTahun);

          var tdSetoran = document.createElement('td');
          tdSetoran.textContent = formatRupiah(row.setoran_tahun_ini);
          tr.appendChild(tdSetoran);

          var tdBunga = document.createElement('td');
          tdBunga.textContent = formatRupiah(row.bunga_tahun_ini);
          tr.appendChild(tdBunga);

          var tdKumulatif = document.createElement('td');
          tdKumulatif.textContent = formatRupiah(row.bunga_kumulatif);
          tr.appendChild(tdKumulatif);

          var tdSaldo = document.createElement('td');
          tdSaldo.textContent = formatRupiah(row.saldo_akhir);
          tr.appendChild(tdSaldo);

          frag.appendChild(tr);
        }
        el.tabelTbody.appendChild(frag);
      }
    }

    // Catatan
    if (el.catatanText) {
      if (Array.isArray(data.catatan) && data.catatan.length > 0) {
        el.catatanText.textContent = data.catatan.join(' ');
      } else {
        el.catatanText.textContent = 'Pajak bunga dan biaya administrasi bank belum dihitung, jadi hasil nyata bisa sedikit berbeda.';
      }
    }

    setStatus('Simulasi tabungan berhasil dihitung.', 'ok');
  }

  function submitCalc() {
    if (state.busy) return;

    var mode = getActiveMode();
    var fd = new FormData();
    fd.append('mode', mode);

    if (mode === 'hasil') {
      var sAwal = cleanRupiahValue(el.inputSetoranAwal ? el.inputSetoranAwal.value : '');
      var sBulanan = cleanRupiahValue(el.inputSetoranBulanan ? el.inputSetoranBulanan.value : '');
      var bTahunan = el.inputBungaTahunan ? el.inputBungaTahunan.value.trim() : '';
      var lTahun = el.inputLamaTahun ? el.inputLamaTahun.value.trim() : '';

      if (sAwal === '0' && sBulanan === '0') {
        setStatus('Setoran awal dan setoran bulanan tidak boleh keduanya Rp 0.', 'error');
        return;
      }

      fd.append('setoran_awal', sAwal);
      fd.append('setoran_bulanan', sBulanan);
      fd.append('bunga_tahunan', bTahunan);
      fd.append('lama_tahun', lTahun);
    } else if (mode === 'setoran') {
      var tgt = cleanRupiahValue(el.inputTarget ? el.inputTarget.value : '');
      var sAwal = cleanRupiahValue(el.inputSetoranAwal ? el.inputSetoranAwal.value : '');
      var bTahunan = el.inputBungaTahunan ? el.inputBungaTahunan.value.trim() : '';
      var lTahun = el.inputLamaTahun ? el.inputLamaTahun.value.trim() : '';

      fd.append('target', tgt);
      fd.append('setoran_awal', sAwal);
      fd.append('bunga_tahunan', bTahunan);
      fd.append('lama_tahun', lTahun);
    } else { // mode === 'lama'
      var tgt = cleanRupiahValue(el.inputTarget ? el.inputTarget.value : '');
      var sAwal = cleanRupiahValue(el.inputSetoranAwal ? el.inputSetoranAwal.value : '');
      var sBulanan = cleanRupiahValue(el.inputSetoranBulanan ? el.inputSetoranBulanan.value : '');
      var bTahunan = el.inputBungaTahunan ? el.inputBungaTahunan.value.trim() : '';

      fd.append('target', tgt);
      fd.append('setoran_awal', sAwal);
      fd.append('setoran_bulanan', sBulanan);
      fd.append('bunga_tahunan', bTahunan);
    }

    state.busy = true;
    updateControls();
    setStatus('Menghitung simulasi tabungan…', 'busy');

    fetch(serverBase + '/api/tabungan', {
      method: 'POST',
      body: fd
    })
      .then(function (response) {
        return response.json().then(function (json) {
          return { ok: response.ok, status: response.status, data: json };
        }).catch(function () {
          return { ok: response.ok, status: response.status, data: null };
        });
      })
      .then(function (res) {
        state.busy = false;
        updateControls();

        if (!res.ok) {
          var errMsg = 'Terjadi kendala saat menghitung tabungan.';
          if (res.data && res.data.error && res.data.error.message) {
            errMsg = res.data.error.message;
          } else if (res.data && res.data.detail && res.data.detail.message) {
            errMsg = res.data.detail.message;
          }
          setStatus(errMsg, 'error');
          return;
        }

        renderResult(res.data);
      })
      .catch(function () {
        state.busy = false;
        updateControls();
        setStatus('Tidak bisa menghubungi server. Coba lagi sebentar.', 'error');
      });
  }

  function resetAll() {
    if (el.inputTarget) el.inputTarget.value = '';
    if (el.inputSetoranAwal) el.inputSetoranAwal.value = '';
    if (el.inputSetoranBulanan) el.inputSetoranBulanan.value = '';
    if (el.inputBungaTahunan) el.inputBungaTahunan.value = '';
    if (el.inputLamaTahun) el.inputLamaTahun.value = '';

    if (el.modeHasil) el.modeHasil.checked = true;
    updateModeVisibility();

    if (el.inputSetoranAwal) el.inputSetoranAwal.focus();
  }

  function copySummary() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var lines = [];
    lines.push('Simulasi Tabungan — bahzi.fun');
    lines.push('Mode: ' + (d.mode === 'hasil' ? 'Hasil akhir tabungan' : (d.mode === 'setoran' ? 'Cari setoran bulanan' : 'Lama waktu capai target')));
    if (d.target) lines.push('Target tabungan: ' + formatRupiah(d.target));
    lines.push('Setoran awal: ' + formatRupiah(d.setoran_awal));
    if (d.mode === 'setoran') {
      lines.push('Setoran bulanan disarankan: ' + formatRupiah(d.setoran_bulanan_disarankan));
    } else {
      lines.push('Setoran bulanan: ' + formatRupiah(d.setoran_bulanan));
    }
    lines.push('Bunga tahunan: ' + d.bunga_tahunan + '% per tahun');
    if (d.mode === 'lama') {
      lines.push('Lama waktu: ' + d.bulan_ke_target + ' bulan (' + formatBulanTahun(d.bulan_ke_target) + ')');
    } else {
      lines.push('Jangka waktu: ' + d.lama_tahun + ' tahun (' + d.lama_bulan + ' bulan)');
    }
    lines.push('Total setoran: ' + formatRupiah(d.total_setoran));
    lines.push('Total bunga: ' + formatRupiah(d.total_bunga));
    lines.push('Saldo akhir: ' + formatRupiah(d.saldo_akhir));
    if (d.asumsi) lines.push('Asumsi: ' + d.asumsi);

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
    var triggers = document.querySelectorAll('[data-tool-action="tabungan"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'tabungan-panel');
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

    var firstInput = (state.mode === 'hasil' ? el.inputSetoranAwal : el.inputTarget) || el.inputSetoranAwal;
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

  if (el.modeHasil) el.modeHasil.addEventListener('change', updateModeVisibility);
  if (el.modeSetoran) el.modeSetoran.addEventListener('change', updateModeVisibility);
  if (el.modeLama) el.modeLama.addEventListener('change', updateModeVisibility);

  var rupiahInputs = [el.inputTarget, el.inputSetoranAwal, el.inputSetoranBulanan];
  for (var i = 0; i < rupiahInputs.length; i++) {
    if (rupiahInputs[i]) {
      rupiahInputs[i].addEventListener('input', updateControls);
      rupiahInputs[i].addEventListener('blur', function () {
        formatInputField(this);
      });
    }
  }

  var otherInputs = [el.inputBungaTahunan, el.inputLamaTahun];
  for (var j = 0; j < otherInputs.length; j++) {
    if (otherInputs[j]) {
      otherInputs[j].addEventListener('input', function () {
        resetResults();
        updateControls();
      });
    }
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
  window.OmniToolsPanels['tabungan'] = toggle;

  // Inisialisasi awal
  updateModeVisibility();
  updateControls();
})();
