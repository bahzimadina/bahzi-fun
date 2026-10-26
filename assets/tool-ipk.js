/* =========================================================================
   Panel alat: Hitung IPK (Kalkulator IPK Kuliah)
   Daftar mata kuliah dan nilai diproses di memori server lalu dibuang.
   Tidak ada data yang disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('ipk-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('ipk-title'),
    limits: document.getElementById('ipk-limits'),
    note: document.getElementById('ipk-note'),
    close: document.getElementById('ipk-close'),
    rows: document.getElementById('ipk-rows'),
    add: document.getElementById('ipk-add'),
    target: document.getElementById('ipk-target'),
    cekTarget: document.getElementById('ipk-cek-target'),
    status: document.getElementById('ipk-status'),
    reset: document.getElementById('ipk-reset'),
    submit: document.getElementById('ipk-submit'),
    result: document.getElementById('ipk-result'),
    angka: document.getElementById('ipk-angka'),
    predikat: document.getElementById('ipk-predikat'),
    totalSks: document.getElementById('ipk-total-sks'),
    jumlahMk: document.getElementById('ipk-jumlah-mk'),
    totalMutu: document.getElementById('ipk-total-mutu'),
    targetHasil: document.getElementById('ipk-target-hasil'),
    rincian: document.getElementById('ipk-rincian'),
    copy: document.getElementById('ipk-copy')
  };

  var numberFmt = new Intl.NumberFormat('id-ID');
  var mutuFmt = new Intl.NumberFormat('id-ID', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 2
  });

  var FALLBACK_LIMITS = {
    max_courses: 60,
    sks_per_course: { min: 1, max: 30 },
    max_total_sks: 400,
    grades: [
      { value: 'A', weight: 4.0 },
      { value: 'AB', weight: 3.5 },
      { value: 'B', weight: 3.0 },
      { value: 'BC', weight: 2.5 },
      { value: 'C', weight: 2.0 },
      { value: 'CD', weight: 1.5 },
      { value: 'D', weight: 1.0 },
      { value: 'E', weight: 0.0 }
    ],
    target: { min: 0.0, max: 4.0 }
  };

  var state = {
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    copyTimer: null
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

  function describeLimits(limits) {
    if (!el.limits) return;
    var maxMk = limits.max_courses || FALLBACK_LIMITS.max_courses;
    var minSks = (limits.sks_per_course && limits.sks_per_course.min) || 1;
    var maxSks = (limits.sks_per_course && limits.sks_per_course.max) || 30;
    el.limits.textContent = 'Batas bawaan: maks ' + maxMk + ' mata kuliah, SKS ' + minSks + ' sampai ' + maxSks + ' per mata kuliah';
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/ipk/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = data;
        state.limitsLoaded = true;
        describeLimits(data);
      })
      .catch(function () {
        describeLimits(FALLBACK_LIMITS);
      });
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
          message = 'Layanan hitung IPK belum tersambung ke server. Coba lagi nanti.';
        } else if (response.status === 413) {
          message = 'Permintaan terlalu besar. Silakan kurangi jumlah baris.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function getRows() {
    if (!el.rows) return [];
    return Array.prototype.slice.call(el.rows.querySelectorAll('.ipk__row'));
  }

  function classifyRows() {
    var rows = getRows();
    var valid = [];
    var incomplete = [];
    var invalid = [];
    var empty = [];
    var problems = [];

    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var rowNum = i + 1;
      var inputNama = r.querySelector('.ipk__col-nama input');
      var inputSks = r.querySelector('.ipk__col-sks input');
      var selectNilai = r.querySelector('.ipk__col-nilai select');

      var nama = inputNama ? inputNama.value.trim() : '';
      var sksRaw = inputSks ? inputSks.value.trim() : '';
      var nilai = selectNilai ? selectNilai.value.trim() : '';

      var hasBadInput = Boolean(inputSks && inputSks.validity && inputSks.validity.badInput);
      var hasSks = sksRaw !== '' || hasBadInput;
      var hasNilai = nilai !== '';
      var hasNama = nama !== '';

      // Baris benar-benar kosong (nama, SKS, nilai semuanya kosong) diabaikan
      if (!hasNama && !hasSks && !hasNilai) {
        empty.push({ row: r, rowNum: rowNum });
        continue;
      }

      // Validasi SKS: harus bilangan bulat 1 sampai 30
      var isSksValid = false;
      var sksNum = null;
      if (!hasBadInput && /^\d+$/.test(sksRaw)) {
        var parsed = parseInt(sksRaw, 10);
        if (parsed >= 1 && parsed <= 30) {
          isSksValid = true;
          sksNum = parsed;
        }
      }

      // 1. Tidak sah: SKS terisi tapi bukan bilangan bulat 1 sampai 30
      if (hasSks && !isSksValid) {
        var probInvalid = {
          row: r,
          rowNum: rowNum,
          type: 'invalid',
          fields: inputSks ? [inputSks] : [],
          message: 'Baris ' + rowNum + ': SKS harus bilangan bulat 1 sampai 30.'
        };
        invalid.push(probInvalid);
        problems.push(probInvalid);
        continue;
      }

      // 2. Tidak lengkap: SKS ada tapi nilai kosong, nilai ada tapi SKS kosong, atau nama terisi tapi SKS/nilai belum lengkap
      if (!hasSks || !hasNilai) {
        var missingFields = [];
        if (!hasSks && inputSks) missingFields.push(inputSks);
        if (!hasNilai && selectNilai) missingFields.push(selectNilai);

        var probIncomplete = {
          row: r,
          rowNum: rowNum,
          type: 'incomplete',
          fields: missingFields,
          message: 'Baris ' + rowNum + ' belum lengkap. Isi SKS dan nilainya, atau kosongkan baris itu.'
        };
        incomplete.push(probIncomplete);
        problems.push(probIncomplete);
        continue;
      }

      // 3. Lengkap-sah
      valid.push({
        row: r,
        rowNum: rowNum,
        nama: nama,
        sks: sksNum,
        nilai: nilai
      });
    }

    return {
      valid: valid,
      incomplete: incomplete,
      invalid: invalid,
      empty: empty,
      problems: problems
    };
  }

  function getValidCourses() {
    var c = classifyRows();
    var list = [];
    for (var i = 0; i < c.valid.length; i++) {
      list.push({
        nama: c.valid[i].nama,
        sks: c.valid[i].sks,
        nilai: c.valid[i].nilai
      });
    }
    return list;
  }

  function clearInvalidField(field) {
    if (!field) return;
    field.removeAttribute('aria-invalid');
    field.classList.remove('ipk__field--invalid');
  }

  function clearAllInvalid() {
    var fields = document.querySelectorAll('#ipk-panel .ipk__field--invalid, #ipk-panel [aria-invalid]');
    for (var i = 0; i < fields.length; i++) {
      clearInvalidField(fields[i]);
    }
  }

  function handleRowProblems(analysis) {
    clearAllInvalid();
    if (!analysis || !analysis.problems || analysis.problems.length === 0) return;

    for (var p = 0; p < analysis.problems.length; p++) {
      var prob = analysis.problems[p];
      for (var f = 0; f < prob.fields.length; f++) {
        var field = prob.fields[f];
        field.setAttribute('aria-invalid', 'true');
        field.classList.add('ipk__field--invalid');
      }
    }

    var first = analysis.problems[0];
    setStatus(first.message, 'error');

    if (first.fields && first.fields.length > 0 && typeof first.fields[0].focus === 'function') {
      try {
        first.fields[0].focus();
      } catch (err) { /* diabaikan */ }
    }
  }

  function hasAnyInput() {
    var rows = getRows();
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var inputNama = r.querySelector('.ipk__col-nama input');
      var inputSks = r.querySelector('.ipk__col-sks input');
      var selectNilai = r.querySelector('.ipk__col-nilai select');
      var sksBad = Boolean(inputSks && inputSks.validity && inputSks.validity.badInput);
      if ((inputNama && inputNama.value.trim() !== '') ||
          (inputSks && (inputSks.value.trim() !== '' || sksBad)) ||
          (selectNilai && selectNilai.value !== '')) {
        return true;
      }
    }
    if (el.target && el.target.value.trim() !== '') return true;
    return false;
  }

  function updateControls() {
    var rows = getRows();
    var validCourses = getValidCourses();
    var hasValid = validCourses.length > 0;
    var hasInput = hasAnyInput();
    var hasResult = !!(el.result && !el.result.hidden);
    var maxRows = (state.limits && state.limits.max_courses) || 60;

    if (el.submit) {
      el.submit.disabled = state.busy || !hasValid;
      el.submit.textContent = state.busy ? 'Sedang menghitung...' : 'Hitung IPK';
    }
    if (el.cekTarget) {
      el.cekTarget.disabled = state.busy || !hasValid;
    }
    if (el.reset) {
      el.reset.disabled = state.busy || (!hasInput && !hasResult);
    }
    if (el.add) {
      el.add.disabled = state.busy || (rows.length >= maxMk());
    }

    // Perbarui nomor dan aria-label pada tiap baris
    for (var i = 0; i < rows.length; i++) {
      var rowNum = i + 1;
      var inNama = rows[i].querySelector('.ipk__col-nama input');
      var inSks = rows[i].querySelector('.ipk__col-sks input');
      var inNilai = rows[i].querySelector('.ipk__col-nilai select');
      var btnHapus = rows[i].querySelector('.ipk__col-aksi button');

      if (inNama) inNama.setAttribute('aria-label', 'Nama mata kuliah baris ' + rowNum);
      if (inSks) inSks.setAttribute('aria-label', 'SKS baris ' + rowNum);
      if (inNilai) inNilai.setAttribute('aria-label', 'Nilai baris ' + rowNum);
      if (btnHapus) btnHapus.setAttribute('aria-label', 'Hapus baris ' + rowNum);
    }
  }

  function maxMk() {
    return (state.limits && state.limits.max_courses) || 60;
  }

  function createRowElement(rowNum) {
    var row = document.createElement('div');
    row.className = 'ipk__row';

    // Kolom nama mata kuliah
    var colNama = document.createElement('div');
    colNama.className = 'ipk__col ipk__col-nama';
    var inNama = document.createElement('input');
    inNama.type = 'text';
    inNama.className = 'ipk__input ipk__input-nama';
    inNama.maxLength = 80;
    inNama.placeholder = 'Mata kuliah (opsional)';
    inNama.setAttribute('aria-label', 'Nama mata kuliah baris ' + rowNum);
    inNama.setAttribute('autocomplete', 'off');
    inNama.setAttribute('spellcheck', 'false');
    colNama.appendChild(inNama);

    // Kolom SKS
    var colSks = document.createElement('div');
    colSks.className = 'ipk__col ipk__col-sks';
    var inSks = document.createElement('input');
    inSks.type = 'number';
    inSks.className = 'ipk__input ipk__input-sks';
    inSks.min = '1';
    inSks.max = '30';
    inSks.inputMode = 'numeric';
    inSks.placeholder = 'SKS';
    inSks.setAttribute('aria-label', 'SKS baris ' + rowNum);
    colSks.appendChild(inSks);

    // Kolom Nilai
    var colNilai = document.createElement('div');
    colNilai.className = 'ipk__col ipk__col-nilai';
    var selNilai = document.createElement('select');
    selNilai.className = 'ipk__select ipk__select-nilai';
    selNilai.setAttribute('aria-label', 'Nilai baris ' + rowNum);

    var optPlaceholder = document.createElement('option');
    optPlaceholder.value = '';
    optPlaceholder.textContent = 'Nilai';
    optPlaceholder.disabled = true;
    optPlaceholder.selected = true;
    selNilai.appendChild(optPlaceholder);

    var grades = [
      { val: 'A', label: 'A (4,0)' },
      { val: 'AB', label: 'AB (3,5)' },
      { val: 'B', label: 'B (3,0)' },
      { val: 'BC', label: 'BC (2,5)' },
      { val: 'C', label: 'C (2,0)' },
      { val: 'CD', label: 'CD (1,5)' },
      { val: 'D', label: 'D (1,0)' },
      { val: 'E', label: 'E (0,0)' }
    ];
    for (var g = 0; g < grades.length; g++) {
      var opt = document.createElement('option');
      opt.value = grades[g].val;
      opt.textContent = grades[g].label;
      selNilai.appendChild(opt);
    }
    colNilai.appendChild(selNilai);

    // Kolom aksi hapus
    var colAksi = document.createElement('div');
    colAksi.className = 'ipk__col ipk__col-aksi';
    var btnHapus = document.createElement('button');
    btnHapus.type = 'button';
    btnHapus.className = 'ipk__row-del';
    btnHapus.setAttribute('aria-label', 'Hapus baris ' + rowNum);
    btnHapus.innerHTML = '<span aria-hidden="true">&times;</span>';
    colAksi.appendChild(btnHapus);

    row.appendChild(colNama);
    row.appendChild(colSks);
    row.appendChild(colNilai);
    row.appendChild(colAksi);

    attachRowEvents(row);
    return row;
  }

  function attachRowEvents(row) {
    var inNama = row.querySelector('.ipk__col-nama input');
    var inSks = row.querySelector('.ipk__col-sks input');
    var selNilai = row.querySelector('.ipk__col-nilai select');
    var btnHapus = row.querySelector('.ipk__col-aksi button');

    function onFieldChange() {
      clearInvalidField(this);
      var rNama = inNama ? inNama.value.trim() : '';
      var rSks = inSks ? inSks.value.trim() : '';
      var rNilai = selNilai ? selNilai.value.trim() : '';
      if (rNama === '' && rSks === '' && rNilai === '') {
        clearInvalidField(inNama);
        clearInvalidField(inSks);
        clearInvalidField(selNilai);
      }
      updateControls();
    }

    if (inNama) {
      inNama.addEventListener('input', onFieldChange);
      inNama.addEventListener('change', onFieldChange);
    }
    if (inSks) {
      inSks.addEventListener('input', onFieldChange);
      inSks.addEventListener('change', onFieldChange);
    }
    if (selNilai) {
      selNilai.addEventListener('change', onFieldChange);
      selNilai.addEventListener('input', onFieldChange);
    }
    if (btnHapus) {
      btnHapus.addEventListener('click', function () {
        var rows = getRows();
        if (rows.length > 1) {
          row.parentNode.removeChild(row);
        } else {
          if (inNama) inNama.value = '';
          if (inSks) inSks.value = '';
          if (selNilai) selNilai.value = '';
          clearInvalidField(inNama);
          clearInvalidField(inSks);
          clearInvalidField(selNilai);
        }
        updateControls();
      });
    }
  }

  function addRow(focusInput) {
    if (!el.rows) return;
    var rows = getRows();
    if (rows.length >= maxMk()) return;
    var newRow = createRowElement(rows.length + 1);
    el.rows.appendChild(newRow);
    updateControls();
    if (focusInput) {
      var inNama = newRow.querySelector('.ipk__col-nama input');
      if (inNama) inNama.focus();
    }
  }

  function initRows() {
    if (!el.rows) return;
    var existingRows = getRows();
    if (existingRows.length > 0) {
      for (var i = 0; i < existingRows.length; i++) {
        attachRowEvents(existingRows[i]);
      }
    } else {
      el.rows.innerHTML = '';
      for (var j = 0; j < 3; j++) {
        el.rows.appendChild(createRowElement(j + 1));
      }
    }
    updateControls();
  }

  function resetResults() {
    if (el.result) el.result.hidden = true;
    if (el.angka) el.angka.textContent = '0,00';
    if (el.predikat) el.predikat.textContent = 'Predikat: -';
    if (el.totalSks) el.totalSks.textContent = '0';
    if (el.jumlahMk) el.jumlahMk.textContent = '0';
    if (el.totalMutu) el.totalMutu.textContent = '0,0';
    if (el.targetHasil) el.targetHasil.innerHTML = '';
    if (el.rincian) el.rincian.innerHTML = '';
    state.lastResult = null;
  }

  function resetAll() {
    if (state.busy) return;
    clearAllInvalid();
    if (el.rows) {
      el.rows.innerHTML = '';
      for (var j = 0; j < 3; j++) {
        el.rows.appendChild(createRowElement(j + 1));
      }
    }
    if (el.target) el.target.value = '';
    resetResults();
    setStatus('Isi SKS dan nilai tiap mata kuliah, lalu tekan Hitung IPK.', '');
    var firstInput = el.rows ? el.rows.querySelector('input') : null;
    if (firstInput) firstInput.focus();
    updateControls();
  }

  function renderResult(data) {
    state.lastResult = data;
    if (!el.result) return;

    if (el.angka) el.angka.textContent = data.ipk_teks || '0,00';
    if (el.predikat) el.predikat.textContent = 'Predikat: ' + (data.predikat || '-');
    if (el.totalSks) el.totalSks.textContent = numberFmt.format(data.total_sks || 0);
    if (el.jumlahMk) el.jumlahMk.textContent = numberFmt.format(data.jumlah_mk || 0);
    if (el.totalMutu) el.totalMutu.textContent = mutuFmt.format(data.total_mutu || 0);

    // Bagian target
    if (el.targetHasil) {
      el.targetHasil.innerHTML = '';
      if (data.target) {
        var t = data.target;
        var box = document.createElement('div');
        box.className = 'ipk__target-box' +
          (t.sudah_tercapai ? ' ipk__target-box--sukses' :
           (t.tidak_mungkin ? ' ipk__target-box--perhatian' : ' ipk__target-box--info'));

        var title = document.createElement('strong');
        title.className = 'ipk__target-box-title';
        var tDiminta = (new Intl.NumberFormat('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 })).format(t.diminta);
        title.textContent = 'Target IPK: ' + tDiminta;

        var pesan = document.createElement('p');
        pesan.className = 'ipk__target-box-pesan';
        pesan.textContent = t.pesan;

        box.appendChild(title);
        box.appendChild(pesan);
        el.targetHasil.appendChild(box);
      }
    }

    // Tabel rincian
    if (el.rincian) {
      el.rincian.innerHTML = '';
      if (data.rincian && data.rincian.length > 0) {
        var thead = document.createElement('thead');
        var trHead = document.createElement('tr');
        var headers = ['No', 'Mata kuliah', 'SKS', 'Nilai', 'Bobot', 'Mutu'];
        for (var h = 0; h < headers.length; h++) {
          var th = document.createElement('th');
          th.textContent = headers[h];
          trHead.appendChild(th);
        }
        thead.appendChild(trHead);
        el.rincian.appendChild(thead);

        var tbody = document.createElement('tbody');
        for (var r = 0; r < data.rincian.length; r++) {
          var item = data.rincian[r];
          var tr = document.createElement('tr');

          var tdNo = document.createElement('td');
          tdNo.className = 'ipk__cell-num';
          tdNo.textContent = String(r + 1);

          var tdNama = document.createElement('td');
          tdNama.textContent = item.nama || '(Tanpa nama)';

          var tdSks = document.createElement('td');
          tdSks.className = 'ipk__cell-num';
          tdSks.textContent = String(item.sks);

          var tdNilai = document.createElement('td');
          tdNilai.className = 'ipk__cell-center';
          tdNilai.textContent = item.nilai;

          var tdBobot = document.createElement('td');
          tdBobot.className = 'ipk__cell-num';
          tdBobot.textContent = mutuFmt.format(item.bobot);

          var tdMutu = document.createElement('td');
          tdMutu.className = 'ipk__cell-num';
          tdMutu.textContent = mutuFmt.format(item.mutu);

          tr.appendChild(tdNo);
          tr.appendChild(tdNama);
          tr.appendChild(tdSks);
          tr.appendChild(tdNilai);
          tr.appendChild(tdBobot);
          tr.appendChild(tdMutu);
          tbody.appendChild(tr);
        }
        el.rincian.appendChild(tbody);
      }
    }

    el.result.hidden = false;
  }

  function submitIpk() {
    if (state.busy) return;
    var analysis = classifyRows();
    if (analysis.valid.length === 0) {
      setStatus('Tambahkan minimal satu mata kuliah dengan SKS dan nilai.', 'error');
      return;
    }
    if (analysis.problems.length > 0) {
      handleRowProblems(analysis);
      return;
    }

    clearAllInvalid();

    var validCourses = [];
    for (var i = 0; i < analysis.valid.length; i++) {
      validCourses.push({
        nama: analysis.valid[i].nama,
        sks: analysis.valid[i].sks,
        nilai: analysis.valid[i].nilai
      });
    }

    var formData = new FormData();
    formData.append('courses', JSON.stringify(validCourses));
    var targetVal = el.target ? el.target.value.trim() : '';
    if (targetVal) {
      formData.append('target', targetVal);
    }

    state.busy = true;
    setStatus('Sedang menghitung IPK...', 'busy');
    updateControls();

    fetch(serverBase + '/api/ipk', {
      method: 'POST',
      body: formData,
      headers: { Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResult(data);
        setStatus('Perhitungan selesai.', 'success');
      })
      .catch(function (err) {
        var pesan = err.pesanLayanan
          ? err.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        setStatus(pesan, 'error');
      })
      .finally(function () {
        state.busy = false;
        updateControls();
      });
  }

  function cekTargetHandler() {
    if (state.busy) return;
    var analysis = classifyRows();
    if (analysis.valid.length === 0) {
      setStatus('Tambahkan minimal satu mata kuliah dengan SKS dan nilai.', 'error');
      return;
    }
    if (analysis.problems.length > 0) {
      handleRowProblems(analysis);
      return;
    }
    var targetVal = el.target ? el.target.value.trim() : '';
    if (!targetVal) {
      if (el.target) el.target.focus();
      setStatus('Ketik angka target IPK (mis. 3,60) yang ingin diperiksa.', '');
      return;
    }
    submitIpk();
  }

  function copySummary() {
    if (!state.lastResult) return;
    var res = state.lastResult;
    var lines = [
      'Hasil Hitung IPK - bahzi.fun',
      'IPK: ' + res.ipk_teks + ' (' + res.predikat + ')',
      'Total SKS: ' + res.total_sks + ' | Jumlah mata kuliah: ' + res.jumlah_mk + ' | Total mutu: ' + mutuFmt.format(res.total_mutu)
    ];

    if (res.target) {
      lines.push('');
      lines.push('Target IPK: ' + mutuFmt.format(res.target.diminta));
      lines.push('Keterangan target: ' + res.target.pesan);
    }

    if (res.rincian && res.rincian.length > 0) {
      lines.push('');
      lines.push('Rincian mata kuliah:');
      for (var i = 0; i < res.rincian.length; i++) {
        var m = res.rincian[i];
        var namaMk = m.nama ? m.nama : 'Mata kuliah ' + (i + 1);
        lines.push((i + 1) + '. ' + namaMk + ' (' + m.sks + ' SKS, nilai ' + m.nilai + ', mutu ' + mutuFmt.format(m.mutu) + ')');
      }
    }

    var text = lines.join('\n');
    var done = function () {
      if (!el.copy) return;
      var original = el.copy.textContent;
      el.copy.textContent = 'Tersalin!';
      clearTimeout(state.copyTimer);
      state.copyTimer = setTimeout(function () {
        if (el.copy) el.copy.textContent = original;
      }, 2000);
    };

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text).then(done).catch(function () {
        fallbackCopy(text, done);
      });
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, cb) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
      if (typeof cb === 'function') cb();
    } catch (err) { /* abaikan */ }
    document.body.removeChild(ta);
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="ipk"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
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
    } catch (e) { /* diabaikan */ }

    if (typeof panel.focus === 'function') {
      panel.focus({ preventScroll: true });
      var firstInput = el.rows ? el.rows.querySelector('input') : null;
      if (firstInput) firstInput.focus();
    }
    panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    syncTriggers(false);
    if (state.lastFocus && typeof state.lastFocus.focus === 'function' && document.contains(state.lastFocus)) {
      state.lastFocus.focus();
    } else {
      var trigger = document.querySelector('.tool-card__open[data-tool-action="ipk"]');
      if (trigger && typeof trigger.focus === 'function') {
        trigger.focus();
      }
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
        submitIpk();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.add) el.add.addEventListener('click', function () { addRow(true); });
  if (el.cekTarget) el.cekTarget.addEventListener('click', cekTargetHandler);
  if (el.target) {
    el.target.addEventListener('input', updateControls);
    el.target.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        submitIpk();
      }
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitIpk);
  if (el.reset) el.reset.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copySummary);

  // Daftarkan panel supaya kartu "Hitung IPK" bisa membuka dan menutupnya
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['ipk'] = toggle;

  // Inisialisasi awal baris
  initRows();
})();
