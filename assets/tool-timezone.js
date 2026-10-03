/* Panel alat: Konverter zona waktu (Time Zone Converter)
   Data dikirim ke layanan lewat multipart/form-data, diproses di memori,
   lalu langsung dibuang. Tidak ada data yang disimpan di disk.
*/
(function () {
  'use strict';

  var panel = document.getElementById('timezone-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('timezone-title'),
    limits: document.getElementById('timezone-limits'),
    note: document.getElementById('timezone-note'),
    close: document.getElementById('timezone-close'),
    mode: document.getElementById('tz-mode'),
    date: document.getElementById('tz-date'),
    groupJam: document.getElementById('tz-group-jam'),
    time: document.getElementById('tz-time'),
    btnNow: document.getElementById('tz-now'),
    from: document.getElementById('tz-from'),
    groupKe: document.getElementById('tz-group-ke'),
    to: document.getElementById('tz-to'),
    groupMulti: document.getElementById('tz-group-multi'),
    multiCount: document.getElementById('tz-multi-count'),
    gridCities: document.getElementById('tz-grid-cities'),
    groupRentang: document.getElementById('tz-group-rentang'),
    startHour: document.getElementById('tz-start-hour'),
    endHour: document.getElementById('tz-end-hour'),
    status: document.getElementById('tz-status'),
    clear: document.getElementById('tz-clear'),
    submit: document.getElementById('tz-submit'),
    results: document.getElementById('tz-results'),
    resultHint: document.getElementById('tz-result-hint'),
    outputWrap: document.getElementById('tz-output-wrap'),
    outputContent: document.getElementById('tz-output-content'),
    copy: document.getElementById('tz-copy'),
    download: document.getElementById('tz-download')
  };

  var FALLBACK_ZONES = [
    { id: 'wib', iana: 'Asia/Jakarta', label: 'WIB (Jakarta)' },
    { id: 'wita', iana: 'Asia/Makassar', label: 'WITA (Makassar, Bali)' },
    { id: 'wit', iana: 'Asia/Jayapura', label: 'WIT (Jayapura)' },
    { id: 'singapura', iana: 'Asia/Singapore', label: 'Singapura' },
    { id: 'bangkok', iana: 'Asia/Bangkok', label: 'Bangkok' },
    { id: 'tokyo', iana: 'Asia/Tokyo', label: 'Tokyo' },
    { id: 'seoul', iana: 'Asia/Seoul', label: 'Seoul' },
    { id: 'shanghai', iana: 'Asia/Shanghai', label: 'Shanghai' },
    { id: 'hongkong', iana: 'Asia/Hong_Kong', label: 'Hong Kong' },
    { id: 'delhi', iana: 'Asia/Kolkata', label: 'New Delhi' },
    { id: 'dubai', iana: 'Asia/Dubai', label: 'Dubai' },
    { id: 'mekkah', iana: 'Asia/Riyadh', label: 'Mekkah / Arab Saudi' },
    { id: 'kairo', iana: 'Africa/Cairo', label: 'Kairo' },
    { id: 'istanbul', iana: 'Europe/Istanbul', label: 'Istanbul' },
    { id: 'london', iana: 'Europe/London', label: 'London' },
    { id: 'paris', iana: 'Europe/Paris', label: 'Paris' },
    { id: 'berlin', iana: 'Europe/Berlin', label: 'Berlin' },
    { id: 'newyork', iana: 'America/New_York', label: 'New York' },
    { id: 'losangeles', iana: 'America/Los_Angeles', label: 'Los Angeles' },
    { id: 'saopaulo', iana: 'America/Sao_Paulo', label: 'Sao Paulo' },
    { id: 'sydney', iana: 'Australia/Sydney', label: 'Sydney' },
    { id: 'auckland', iana: 'Pacific/Auckland', label: 'Auckland' }
  ];

  var state = {
    mode: 'titik',
    zones: FALLBACK_ZONES,
    maxZones: 8,
    defaultStartHour: 6,
    defaultEndHour: 22,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResultText: '',
    downloadUrl: null
  };

  function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

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

  function initHourDropdowns() {
    if (!el.startHour || !el.endHour) return;

    var startDef = typeof state.defaultStartHour === 'number' ? state.defaultStartHour : 6;
    var endDef = typeof state.defaultEndHour === 'number' ? state.defaultEndHour : 22;

    var curStart = el.startHour.value ? parseInt(el.startHour.value, 10) : startDef;
    var curEnd = el.endHour.value ? parseInt(el.endHour.value, 10) : endDef;
    if (isNaN(curStart)) curStart = startDef;
    if (isNaN(curEnd)) curEnd = endDef;

    el.startHour.innerHTML = '';
    el.endHour.innerHTML = '';

    for (var h = 0; h < 24; h++) {
      var val = (h < 10 ? '0' : '') + h + ':00';
      var optStart = document.createElement('option');
      optStart.value = String(h);
      optStart.textContent = val;
      if (h === curStart) optStart.selected = true;
      el.startHour.appendChild(optStart);

      var optEnd = document.createElement('option');
      optEnd.value = String(h);
      optEnd.textContent = val;
      if (h === curEnd) optEnd.selected = true;
      el.endHour.appendChild(optEnd);
    }

    el.startHour.value = String(curStart);
    el.endHour.value = String(curEnd);
  }

  function getDefaultCheckedZones(refId) {
    var baseDefaults = ['london', 'tokyo', 'newyork'];
    var zoneIds = state.zones.map(function (z) { return z.id; });
    var result = [];

    baseDefaults.forEach(function (defId) {
      if (defId !== refId && zoneIds.indexOf(defId) !== -1) {
        result.push(defId);
      } else {
        // cari kota terdekat dari daftar yang belum dipilih dan bukan acuan
        var targetIdx = zoneIds.indexOf(defId);
        if (targetIdx === -1) targetIdx = 0;
        var found = null;
        for (var step = 1; step < zoneIds.length; step++) {
          var nextIdx = targetIdx + step;
          if (nextIdx < zoneIds.length) {
            var candNext = zoneIds[nextIdx];
            if (candNext !== refId && result.indexOf(candNext) === -1 && baseDefaults.indexOf(candNext) === -1) {
              found = candNext;
              break;
            }
          }
          var prevIdx = targetIdx - step;
          if (prevIdx >= 0) {
            var candPrev = zoneIds[prevIdx];
            if (candPrev !== refId && result.indexOf(candPrev) === -1 && baseDefaults.indexOf(candPrev) === -1) {
              found = candPrev;
              break;
            }
          }
        }
        if (!found) {
          for (var i = 0; i < zoneIds.length; i++) {
            var cand = zoneIds[i];
            if (cand !== refId && result.indexOf(cand) === -1) {
              found = cand;
              break;
            }
          }
        }
        if (found) {
          result.push(found);
        }
      }
    });

    return result;
  }

  function renderCityCheckboxes(checkedIds) {
    if (!el.gridCities) return;
    el.gridCities.innerHTML = '';

    var refId = el.from ? el.from.value : 'wib';
    var defaultList = Array.isArray(checkedIds) ? checkedIds : getDefaultCheckedZones(refId);
    var checkedMap = {};
    defaultList.forEach(function (id) {
      if (id !== refId) {
        checkedMap[id] = true;
      }
    });

    state.zones.forEach(function (z) {
      var isRef = (z.id === refId);
      var labelNode = document.createElement('label');
      labelNode.className = 'tz__city-item' + (isRef ? ' tz__city-item--disabled' : '');
      if (isRef) {
        labelNode.style.opacity = '0.6';
        labelNode.style.cursor = 'not-allowed';
      }

      var chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.className = 'tz__checkbox';
      chk.value = z.id;
      chk.checked = !isRef && !!checkedMap[z.id];
      chk.disabled = isRef;
      chk.addEventListener('change', onCheckboxChange);

      var span = document.createElement('span');
      span.textContent = z.label;

      var note = document.createElement('small');
      note.className = 'tz__city-ref';
      note.style.fontSize = '0.8em';
      note.style.color = 'var(--text-muted)';
      note.style.marginLeft = '0.25rem';
      note.textContent = '(zona acuan)';
      note.hidden = !isRef;

      labelNode.appendChild(chk);
      labelNode.appendChild(span);
      labelNode.appendChild(note);
      el.gridCities.appendChild(labelNode);
    });

    updateCheckboxCounter();
  }

  function syncReferenceZone() {
    if (!el.gridCities) return;
    var refId = el.from ? el.from.value : '';

    var items = el.gridCities.querySelectorAll('.tz__city-item');
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var chk = item.querySelector('.tz__checkbox');
      var note = item.querySelector('.tz__city-ref');
      if (!chk) continue;

      var isRef = (chk.value === refId);
      if (isRef) {
        chk.checked = false;
        chk.disabled = true;
        item.classList.add('tz__city-item--disabled');
        item.style.opacity = '0.6';
        item.style.cursor = 'not-allowed';
        if (note) note.hidden = false;
      } else {
        chk.disabled = false;
        item.classList.remove('tz__city-item--disabled');
        item.style.opacity = '';
        item.style.cursor = '';
        if (note) note.hidden = true;
      }
    }

    updateCheckboxCounter();
  }

  function onFromChange() {
    syncReferenceZone();
  }

  function getCheckedZones() {
    if (!el.gridCities) return [];
    var refId = el.from ? el.from.value : '';
    var checked = [];
    var chks = el.gridCities.querySelectorAll('.tz__checkbox:checked');
    for (var i = 0; i < chks.length; i++) {
      var val = chks[i].value;
      if (!chks[i].disabled && val !== refId) {
        checked.push(val);
      }
    }
    return checked;
  }

  function updateCheckboxCounter() {
    var checked = getCheckedZones();
    var count = checked.length;
    if (el.multiCount) {
      if (count >= state.maxZones) {
        el.multiCount.textContent = count + ' dari ' + state.maxZones + ' dipilih (maksimal)';
      } else {
        el.multiCount.textContent = count + ' dari ' + state.maxZones + ' dipilih';
      }
    }
    return count;
  }

  function onCheckboxChange(e) {
    var count = updateCheckboxCounter();
    if (count > state.maxZones) {
      e.target.checked = false;
      updateCheckboxCounter();
      setStatus('Maksimal ' + state.maxZones + ' kota yang dapat dipilih.', 'error');
    }
  }

  function updateModeUI() {
    var modeVal = el.mode ? el.mode.value : 'titik';
    if (modeVal !== 'titik' && modeVal !== 'banding' && modeVal !== 'cocok') {
      modeVal = 'titik';
    }
    state.mode = modeVal;

    if (el.groupJam) el.groupJam.hidden = (modeVal === 'cocok');
    if (el.groupKe) el.groupKe.hidden = (modeVal !== 'titik');
    if (el.groupMulti) el.groupMulti.hidden = (modeVal === 'titik');
    if (el.groupRentang) el.groupRentang.hidden = (modeVal !== 'cocok');

    resetResults();
    setStatus('Pilih zona dan waktu, lalu tekan "Hitung".', '');
  }

  function setTimeToNowWib() {
    try {
      var now = new Date();
      var dtfDate = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Jakarta',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      });
      var dtfTime = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Jakarta',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23'
      });
      if (el.date) el.date.value = dtfDate.format(now);
      if (el.time) el.time.value = dtfTime.format(now);
      setStatus('Waktu disetel ke WIB saat ini.', 'ok');
    } catch (e) {
      var d = new Date();
      var y = d.getFullYear();
      var m = String(d.getMonth() + 1).padStart(2, '0');
      var day = String(d.getDate()).padStart(2, '0');
      var hr = String(d.getHours()).padStart(2, '0');
      var min = String(d.getMinutes()).padStart(2, '0');
      if (el.date) el.date.value = y + '-' + m + '-' + day;
      if (el.time) el.time.value = hr + ':' + min;
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/timezone/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsLoaded = true;
        if (data.zones && Array.isArray(data.zones)) {
          var curChecked = getCheckedZones();
          state.zones = data.zones;
          renderCityCheckboxes(curChecked.length ? curChecked : null);
        }
        if (data.max_zones) {
          state.maxZones = data.max_zones;
          updateCheckboxCounter();
        }
        if (data.subjudul && el.limits) {
          el.limits.textContent = data.subjudul;
        }
        if (data.note && el.note) {
          el.note.textContent = data.note;
        }
        if (typeof data.default_start_hour === 'number') {
          state.defaultStartHour = data.default_start_hour;
        }
        if (typeof data.default_end_hour === 'number') {
          state.defaultEndHour = data.default_end_hour;
        }
      })
      .catch(function () {
        /* Tetap pakai nilai bawaan jika permintaan limits gagal */
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
      } catch (err) { /* abaikan */ }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan konverter zona waktu belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Ukuran data permintaan melebihi batas 64 KB.';
        } else {
          message = 'Terjadi kendala saat memproses konversi (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }
      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitCalc() {
    if (state.busy) return;

    var modeVal = el.mode ? el.mode.value : 'titik';
    var dateVal = el.date ? el.date.value.trim() : '';
    var fromVal = el.from ? el.from.value : '';

    if (!dateVal) {
      resetResults();
      setStatus('Masukkan tanggal acuan.', 'error');
      if (el.date) el.date.focus();
      return;
    }
    if (!fromVal) {
      resetResults();
      setStatus('Pilih zona acuan.', 'error');
      if (el.from) el.from.focus();
      return;
    }

    var form = new FormData();
    form.append('mode', modeVal);
    form.append('tanggal', dateVal);
    form.append('dari', fromVal);

    if (modeVal === 'titik') {
      var timeVal = el.time ? el.time.value.trim() : '';
      var toVal = el.to ? el.to.value : '';
      if (!timeVal) {
        resetResults();
        setStatus('Masukkan jam acuan.', 'error');
        if (el.time) el.time.focus();
        return;
      }
      if (!toVal) {
        resetResults();
        setStatus('Pilih zona tujuan.', 'error');
        if (el.to) el.to.focus();
        return;
      }
      form.append('jam', timeVal);
      form.append('ke', toVal);
    } else if (modeVal === 'banding') {
      var checkedZones = getCheckedZones();
      if (checkedZones.length === 0) {
        resetResults();
        setStatus('Pilih minimal satu kota tujuan untuk perbandingan.', 'error');
        return;
      }
      var timeValBanding = el.time ? el.time.value.trim() : '';
      if (!timeValBanding) {
        resetResults();
        setStatus('Masukkan jam acuan.', 'error');
        if (el.time) el.time.focus();
        return;
      }
      form.append('jam', timeValBanding);
      form.append('zona', checkedZones.join(','));
    } else if (modeVal === 'cocok') {
      var checkedZonesCocok = getCheckedZones();
      if (checkedZonesCocok.length === 0) {
        resetResults();
        setStatus('Pilih minimal satu kota tujuan peserta rapat.', 'error');
        return;
      }
      var startVal = el.startHour ? el.startHour.value : String(state.defaultStartHour);
      var endVal = el.endHour ? el.endHour.value : String(state.defaultEndHour);
      var startNum = parseInt(startVal, 10);
      var endNum = parseInt(endVal, 10);
      if (isNaN(startNum)) startNum = state.defaultStartHour;
      if (isNaN(endNum)) endNum = state.defaultEndHour;

      var adjustedNotice = '';
      if (startNum >= endNum) {
        if (startNum >= 23) {
          resetResults();
          setStatus('Jam mulai sudah 23:00, tidak ada rentang yang bisa dihitung.', 'error');
          if (el.startHour) el.startHour.focus();
          return;
        }
        var newEnd = Math.min(23, startNum + 1);
        endVal = String(newEnd);
        if (el.endHour) el.endHour.value = endVal;
        var endText = (newEnd < 10 ? '0' : '') + newEnd + ':00';
        adjustedNotice = 'Jam selesai disesuaikan otomatis menjadi ' + endText + ' karena harus lebih akhir dari jam mulai.';
      }

      form.append('zona', checkedZonesCocok.join(','));
      form.append('jam_mulai', String(startNum));
      form.append('jam_selesai', endVal);
    }

    state.busy = true;
    if (el.submit) el.submit.disabled = true;
    setStatus('Menghitung...', 'busy');

    fetch(serverBase + '/api/timezone', {
      method: 'POST',
      body: form
    })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderResults(data);
        setStatus(adjustedNotice || 'Perhitungan berhasil.', adjustedNotice ? 'warn' : 'ok');
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
        if (el.submit) el.submit.disabled = false;
      });
  }

  function renderResults(data) {
    if (!el.outputContent || !el.outputWrap || !el.resultHint) return;

    el.resultHint.hidden = true;
    el.outputWrap.hidden = false;
    el.outputContent.innerHTML = '';

    if (data.mode === 'titik') {
      renderTitik(data);
    } else if (data.mode === 'banding') {
      renderBanding(data);
    } else if (data.mode === 'cocok') {
      renderCocok(data);
    }
  }

  function renderTitik(data) {
    var acuan = data.acuan;
    var tujuan = data.tujuan;

    var html = '';
    html += '<div class="tz__cards-grid">';

    // Kartu acuan
    html += '<div class="tz__card">';
    html += '  <div class="tz__card-header">';
    html += '    <span class="tz__card-tag">Zona acuan</span>';
    html += '    <span class="tz__badge tz__badge--neutral">' + escapeHtml(acuan.singkatan) + '</span>';
    html += '  </div>';
    html += '  <div class="tz__card-city">' + escapeHtml(acuan.label) + '</div>';
    html += '  <div class="tz__clock">' + escapeHtml(acuan.jam) + '</div>';
    html += '  <div class="tz__card-date">' + escapeHtml(acuan.waktu.split(',')[0]) + '</div>';
    html += '  <div class="tz__card-offset">' + escapeHtml(acuan.offset_teks) + '</div>';
    html += '</div>';

    // Kartu tujuan
    html += '<div class="tz__card tz__card--target">';
    html += '  <div class="tz__card-header">';
    html += '    <span class="tz__card-tag">Zona tujuan</span>';
    html += '    <span class="tz__badge tz__badge--brand">' + escapeHtml(tujuan.singkatan) + '</span>';
    html += '  </div>';
    html += '  <div class="tz__card-city">' + escapeHtml(tujuan.label) + '</div>';
    html += '  <div class="tz__clock">' + escapeHtml(tujuan.jam) + '</div>';
    html += '  <div class="tz__card-date">' + escapeHtml(tujuan.waktu.split(',')[0]) + ' &bull; <span class="tz__badge-pill">' + escapeHtml(data.geser_teks) + '</span></div>';
    html += '  <div class="tz__card-offset">' + escapeHtml(tujuan.offset_teks) + '</div>';
    html += '</div>';

    html += '</div>';

    // Kalimat selisih
    html += '<div class="tz__summary">';
    html += '  <p class="tz__summary-text">' + escapeHtml(data.selisih_teks) + ' (' + escapeHtml(data.geser_teks) + ').</p>';
    html += '</div>';

    el.outputContent.innerHTML = html;

    // Siapkan teks untuk papan klip dan berkas unduhan
    var lines = [
      'Konverter Zona Waktu (bahzi.fun)',
      'Mode: Konversi Titik Waktu',
      '',
      'Zona Acuan : ' + acuan.label + ' (' + acuan.offset_teks + ', ' + acuan.singkatan + ')',
      'Waktu      : ' + acuan.waktu,
      '',
      'Zona Tujuan: ' + tujuan.label + ' (' + tujuan.offset_teks + ', ' + tujuan.singkatan + ')',
      'Waktu      : ' + tujuan.waktu,
      '',
      'Keterangan : ' + data.selisih_teks + ' (' + data.geser_teks + ')'
    ];
    state.lastResultText = lines.join('\n');
  }

  function renderBanding(data) {
    var acuan = data.acuan;
    var daftar = data.daftar || [];

    var html = '';
    html += '<div class="tz__banding-list">';

    // Baris acuan
    html += '<div class="tz__row tz__row--acuan">';
    html += '  <div class="tz__row-main">';
    html += '    <div class="tz__row-city">' + escapeHtml(acuan.label) + ' <span class="tz__badge tz__badge--neutral">Acuan</span></div>';
    html += '    <div class="tz__row-sub">' + escapeHtml(acuan.waktu.split(',')[0]) + ' &bull; ' + escapeHtml(acuan.offset_teks) + ' (' + escapeHtml(acuan.singkatan) + ')</div>';
    html += '  </div>';
    html += '  <div class="tz__row-time">';
    html += '    <div class="tz__clock tz__clock--sm">' + escapeHtml(acuan.jam) + '</div>';
    html += '  </div>';
    html += '</div>';

    // Baris kota-kota pembanding
    daftar.forEach(function (item) {
      var rowClass = 'tz__row' + (item.jam_kerja ? ' tz__row--work' : ' tz__row--outside');
      var badgeClass = item.jam_kerja ? 'tz__badge tz__badge--work' : 'tz__badge tz__badge--outside';

      html += '<div class="' + rowClass + '">';
      html += '  <div class="tz__row-main">';
      html += '    <div class="tz__row-city">' + escapeHtml(item.label) + '</div>';
      html += '    <div class="tz__row-sub">' + escapeHtml(item.waktu.split(',')[0]) + ' &bull; ' + escapeHtml(item.offset_teks) + ' (' + escapeHtml(item.singkatan) + ') &bull; ' + escapeHtml(item.geser_teks) + '</div>';
      html += '  </div>';
      html += '  <div class="tz__row-time">';
      html += '    <div class="tz__clock tz__clock--sm">' + escapeHtml(item.jam) + '</div>';
      html += '    <span class="' + badgeClass + '">' + escapeHtml(item.keterangan) + '</span>';
      html += '  </div>';
      html += '</div>';
    });

    html += '</div>';
    el.outputContent.innerHTML = html;

    var textLines = [
      'Konverter Zona Waktu (bahzi.fun)',
      'Mode: Bandingkan Beberapa Kota',
      '',
      'Acuan: ' + acuan.label + ' - ' + acuan.waktu + ' (' + acuan.offset_teks + ')',
      '',
      'Perbandingan:'
    ];
    daftar.forEach(function (item, idx) {
      textLines.push((idx + 1) + '. ' + item.label + ': ' + item.jam + ' ' + item.singkatan + ' (' + item.waktu.split(',')[0] + ', ' + item.geser_teks + ') - ' + item.keterangan);
    });
    state.lastResultText = textLines.join('\n');
  }

  function renderCocok(data) {
    var rekomendasi = data.rekomendasi || [];
    var acuan = data.acuan || {};

    var html = '';
    html += '<div class="tz__cocok-summary">';
    html += '  <p class="tz__summary-text">Peringkat jam rapat terbaik diurutkan dari kesesuaian jam kerja (08:00 sampai 17:59 waktu setempat).</p>';
    html += '</div>';

    html += '<div class="tz__cocok-list">';
    rekomendasi.forEach(function (r, index) {
      var badgeClass = r.semua_jam_kerja ? 'tz__badge tz__badge--work' : (r.cocok > 0 ? 'tz__badge tz__badge--partial' : 'tz__badge tz__badge--outside');
      var itemClass = 'tz__cocok-item' + (r.semua_jam_kerja ? ' tz__cocok-item--perfect' : '');

      html += '<div class="' + itemClass + '">';
      html += '  <div class="tz__cocok-head">';
      html += '    <div class="tz__cocok-time-wrap">';
      html += '      <span class="tz__cocok-rank">#' + (index + 1) + '</span>';
      html += '      <span class="tz__clock tz__clock--sm">' + escapeHtml(r.jam_acuan) + '</span>';
      html += '      <span class="tz__cocok-tz">' + escapeHtml(acuan.singkatan || '') + '</span>';
      html += '    </div>';
      html += '    <span class="' + badgeClass + '">' + escapeHtml(r.cocok + ' dari ' + r.total + ' kota masuk jam kerja') + '</span>';
      html += '  </div>';

      html += '  <div class="tz__cocok-details">';
      (r.detail || []).forEach(function (d) {
        var pillClass = 'tz__detail-pill' + (d.jam_kerja ? ' tz__detail-pill--work' : ' tz__detail-pill--outside');
        html += '<div class="' + pillClass + '" title="' + escapeHtml(d.keterangan) + '">';
        html += '  <span class="tz__pill-city">' + escapeHtml(d.label) + '</span>';
        html += '  <span class="tz__pill-time">' + escapeHtml(d.jam) + '</span>';
        html += '</div>';
      });
      html += '  </div>';
      html += '</div>';
    });
    html += '</div>';

    el.outputContent.innerHTML = html;

    var textLines = [
      'Konverter Zona Waktu (bahzi.fun)',
      'Mode: Cari Jam Rapat yang Cocok',
      '',
      'Acuan  : ' + (acuan.label || '') + ' (' + (acuan.offset_teks || '') + ')',
      'Tanggal: ' + (acuan.tanggal || ''),
      'Rentang: ' + (data.rentang ? data.rentang.jam_mulai + ' - ' + data.rentang.jam_selesai : ''),
      '',
      'Peringkat Jam Rapat:'
    ];

    rekomendasi.forEach(function (r, idx) {
      textLines.push((idx + 1) + '. ' + r.jam_acuan_teks + ' (' + r.cocok + ' dari ' + r.total + ' kota masuk jam kerja)');
      (r.detail || []).forEach(function (d) {
        textLines.push('   - ' + d.label + ': ' + d.jam + ' (' + d.keterangan + ')');
      });
    });

    state.lastResultText = textLines.join('\n');
  }

  function resetResults() {
    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.outputContent) el.outputContent.innerHTML = '';
    state.lastResultText = '';
    revokeDownload();
  }

  function resetAll() {
    if (el.mode) el.mode.value = 'titik';
    setTimeToNowWib();
    if (el.from) el.from.value = 'wib';
    if (el.to) el.to.value = 'london';
    if (el.startHour) el.startHour.value = String(state.defaultStartHour);
    if (el.endHour) el.endHour.value = String(state.defaultEndHour);

    renderCityCheckboxes();
    updateModeUI();
    resetResults();
    setStatus('Pilihan dikosongkan ke pengaturan awal.', '');
  }

  function copyResult() {
    if (!state.lastResultText) return;

    function notify(ok) {
      if (!el.copy) return;
      var orig = el.copy.textContent;
      el.copy.textContent = ok ? 'Tersalin!' : 'Gagal salin';
      setTimeout(function () {
        el.copy.textContent = orig;
      }, 1500);
    }

    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(state.lastResultText).then(function () {
        notify(true);
      }).catch(function () {
        fallbackCopy(state.lastResultText, notify);
      });
    } else {
      fallbackCopy(state.lastResultText, notify);
    }
  }

  function fallbackCopy(text, cb) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      cb(ok);
    } catch (e) {
      cb(false);
    }
  }

  function revokeDownload() {
    if (state.downloadUrl) {
      try {
        URL.revokeObjectURL(state.downloadUrl);
      } catch (e) { /* abaikan */ }
      state.downloadUrl = null;
    }
  }

  function downloadResult() {
    if (!state.lastResultText) return;
    revokeDownload();

    var blob = new Blob([state.lastResultText], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    state.downloadUrl = url;

    var a = document.createElement('a');
    a.href = url;
    a.download = 'hasil-zona-waktu.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function syncTriggers(isOpen) {
    var triggers = document.querySelectorAll('[data-tool-action="timezone"]');
    for (var i = 0; i < triggers.length; i++) {
      var t = triggers[i];
      if (t.tagName === 'BUTTON' || t.classList.contains('tool-card__open')) {
        t.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      }
      var card = t.closest ? t.closest('.tool-card') : null;
      if (card) {
        card.classList.toggle('tool-card--active', isOpen);
      }
    }
  }

  function open() {
    if (!panel.hidden) return;
    state.lastFocus = document.activeElement;
    panel.hidden = false;
    syncTriggers(true);
    loadLimits();

    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    setTimeout(function () {
      if (el.mode) el.mode.focus();
    }, 100);
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
  if (el.mode) el.mode.addEventListener('change', updateModeUI);
  if (el.from) el.from.addEventListener('change', onFromChange);
  if (el.btnNow) el.btnNow.addEventListener('click', setTimeToNowWib);
  if (el.submit) el.submit.addEventListener('click', submitCalc);
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
      if (panel.contains(document.activeElement)) {
        event.preventDefault();
        submitCalc();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);
  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel ke registry global OmniTools
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['timezone'] = toggle;

  // Inisialisasi awal
  initHourDropdowns();
  renderCityCheckboxes();
  setTimeToNowWib();
  updateModeUI();

  // Dukungan buka lewat parameter URL: ?alat=timezone
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('alat') !== 'timezone') return;

      var paramMode = params.get('mode');
      if (paramMode && (paramMode === 'titik' || paramMode === 'banding' || paramMode === 'cocok')) {
        if (el.mode) el.mode.value = paramMode;
      }
      if (params.get('dari') && el.from) {
        el.from.value = params.get('dari');
        syncReferenceZone();
      }
      if (params.get('ke') && el.to) el.to.value = params.get('ke');
      if (params.get('tanggal') && el.date) el.date.value = params.get('tanggal');
      if (params.get('jam') && el.time) el.time.value = params.get('jam');

      updateModeUI();
      open();
      submitCalc();
    } catch (e) {
      /* abaikan */
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', handleUrlParam);
  } else {
    handleUrlParam();
  }
})();
