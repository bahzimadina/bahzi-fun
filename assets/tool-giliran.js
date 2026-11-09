/* =========================================================================
   Panel alat: Bagi giliran tugas (giliran)
   Menyusun jadwal giliran/piket harian atau mingguan dari daftar nama.
   Semua data diproses di memori server dan tidak disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('giliran-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('giliran-close'),
    note: document.getElementById('giliran-note'),
    names: document.getElementById('giliran-names'),
    namesHint: document.getElementById('giliran-names-hint'),
    mode: document.getElementById('giliran-mode'),
    perSlot: document.getElementById('giliran-per-slot'),
    slots: document.getElementById('giliran-slots'),
    mulai: document.getElementById('giliran-mulai'),
    urutan: document.getElementById('giliran-urutan'),
    seedWrap: document.getElementById('giliran-seed-wrap'),
    seed: document.getElementById('giliran-seed'),
    seedClear: document.getElementById('giliran-seed-clear'),
    seedHint: document.getElementById('giliran-seed-hint'),
    lewati: document.getElementById('giliran-lewati'),
    lewatiHint: document.getElementById('giliran-lewati-hint'),
    status: document.getElementById('giliran-status'),
    clear: document.getElementById('giliran-clear'),
    submit: document.getElementById('giliran-submit'),
    result: document.getElementById('giliran-result'),
    statNama: document.getElementById('giliran-stat-nama'),
    statGiliran: document.getElementById('giliran-stat-giliran'),
    statRata: document.getElementById('giliran-stat-rata'),
    list: document.getElementById('giliran-list'),
    counts: document.getElementById('giliran-counts'),
    copy: document.getElementById('giliran-copy'),
    download: document.getElementById('giliran-download')
  };

  var FALLBACK_LIMITS = {
    max_names: 100,
    min_names: 1,
    max_name_chars: 40,
    max_slots: 200,
    min_slots: 1,
    max_per_slot: 20,
    min_per_slot: 1,
    max_text_chars: 20000,
    default_mode: 'harian',
    default_order: 'maju',
    default_per_slot: 2,
    default_slots: 8,
    default_tanggal_mulai: ''
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

  function updateControls() {
    var hasNames = el.names && el.names.value.trim().length > 0;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasNames;
    }
    if (el.clear) {
      el.clear.disabled = state.busy && !state.abortController;
    }
  }

  function applyLimits(data) {
    state.limits = {
      max_names: data.max_names || FALLBACK_LIMITS.max_names,
      min_names: data.min_names || FALLBACK_LIMITS.min_names,
      max_name_chars: data.max_name_chars || FALLBACK_LIMITS.max_name_chars,
      max_slots: data.max_slots || FALLBACK_LIMITS.max_slots,
      min_slots: data.min_slots || FALLBACK_LIMITS.min_slots,
      max_per_slot: data.max_per_slot || FALLBACK_LIMITS.max_per_slot,
      min_per_slot: data.min_per_slot || FALLBACK_LIMITS.min_per_slot,
      max_text_chars: data.max_text_chars || FALLBACK_LIMITS.max_text_chars,
      default_mode: data.default_mode || FALLBACK_LIMITS.default_mode,
      default_order: data.default_order || FALLBACK_LIMITS.default_order,
      default_per_slot: data.default_per_slot || FALLBACK_LIMITS.default_per_slot,
      default_slots: data.default_slots || FALLBACK_LIMITS.default_slots,
      default_tanggal_mulai: data.default_tanggal_mulai || FALLBACK_LIMITS.default_tanggal_mulai
    };

    if (el.perSlot) {
      el.perSlot.min = String(state.limits.min_per_slot);
      el.perSlot.max = String(state.limits.max_per_slot);
    }
    if (el.slots) {
      el.slots.min = String(state.limits.min_slots);
      el.slots.max = String(state.limits.max_slots);
    }
    if (el.mulai && !el.mulai.value && state.limits.default_tanggal_mulai) {
      el.mulai.value = state.limits.default_tanggal_mulai;
    }
    if (el.note && data.notes) {
      el.note.textContent = data.notes;
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/giliran/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsLoaded = true;
        applyLimits(data);
      })
      .catch(function () {
        // Jika gagal, pakai batas cadangan
        applyLimits(FALLBACK_LIMITS);
      });
  }

  function initDefaultDate() {
    if (el.mulai && !el.mulai.value) {
      var now = new Date();
      var year = now.getFullYear();
      var month = String(now.getMonth() + 1).padStart(2, '0');
      var day = String(now.getDate()).padStart(2, '0');
      el.mulai.value = year + '-' + month + '-' + day;
    }
  }

  function onModeChange() {
    var isMingguan = el.mode && el.mode.value === 'mingguan';
    if (el.lewati) {
      el.lewati.disabled = isMingguan;
    }
    if (el.lewatiHint) {
      el.lewatiHint.textContent = isMingguan
        ? 'Mode mingguan dihitung per 7 hari tanpa melewati akhir pekan.'
        : 'Sabtu dan Minggu dilewati agar giliran jatuh di hari kerja.';
    }
  }

  function onUrutanChange() {
    var isAcak = el.urutan && el.urutan.value === 'acak';
    if (el.seedWrap) {
      el.seedWrap.hidden = !isAcak;
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
      } catch (err) {
        // Abaikan galat parse JSON
      }

      if (!message) {
        if (response.status === 413) {
          message = 'Teks daftar nama terlalu besar. Batasnya 64 KB.';
        } else if (response.status === 404) {
          message = 'Layanan bagi giliran belum tersambung ke server. Coba lagi nanti.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }

      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function buildPlainText(data) {
    var lines = [];
    lines.push('JADWAL GILIRAN TUGAS');
    var modeLabel = data.mode === 'mingguan' ? 'Mingguan' : 'Harian';
    lines.push('Mode: ' + modeLabel + ' | Tanggal mulai: ' + data.tanggal_mulai + ' | Orang per giliran: ' + data.per_slot);
    lines.push('');
    (data.giliran || []).forEach(function (slot) {
      lines.push(slot.label + ': ' + (slot.orang || []).join(', '));
    });
    lines.push('');
    lines.push('Hitungan:');
    (data.hitungan || []).forEach(function (item) {
      var slotStr = (item.giliran || []).join(', ');
      lines.push('- ' + item.nama + ': ' + item.kali + ' kali (giliran ' + slotStr + ')');
    });
    return lines.join('\n');
  }

  function renderResult(data) {
    state.lastResult = data;

    if (el.statNama) {
      el.statNama.textContent = String(data.jumlah_nama || 0);
    }
    if (el.statGiliran) {
      el.statGiliran.textContent = String(data.jumlah_giliran || 0);
    }
    if (el.statRata) {
      if (data.jumlah_nama > 0) {
        var avg = (data.jumlah_giliran * data.per_slot) / data.jumlah_nama;
        el.statRata.textContent = avg.toFixed(1).replace('.', ',') + 'x';
      } else {
        el.statRata.textContent = '0x';
      }
    }

    if (el.list) {
      el.list.textContent = '';
      (data.giliran || []).forEach(function (slot) {
        var card = document.createElement('div');
        card.className = 'giliran__slot-card';

        var head = document.createElement('div');
        head.className = 'giliran__slot-head';

        var no = document.createElement('span');
        no.className = 'giliran__slot-badge';
        no.textContent = data.mode === 'mingguan' ? 'Minggu ' + slot.nomor : '#' + slot.nomor;

        var label = document.createElement('span');
        label.className = 'giliran__slot-date';
        label.textContent = slot.label;

        head.appendChild(no);
        head.appendChild(label);

        var body = document.createElement('div');
        body.className = 'giliran__slot-body';

        (slot.orang || []).forEach(function (orang) {
          var tag = document.createElement('span');
          tag.className = 'giliran__person-tag';
          tag.textContent = orang;
          body.appendChild(tag);
        });

        card.appendChild(head);
        card.appendChild(body);
        el.list.appendChild(card);
      });
    }

    if (el.counts) {
      el.counts.textContent = '';
      (data.hitungan || []).forEach(function (item) {
        var row = document.createElement('div');
        row.className = 'giliran__count-item';

        var nameSpan = document.createElement('span');
        nameSpan.className = 'giliran__count-name';
        nameSpan.textContent = item.nama;

        var timesSpan = document.createElement('span');
        timesSpan.className = 'giliran__count-times';
        timesSpan.textContent = item.kali + ' kali';

        var detailSpan = document.createElement('span');
        detailSpan.className = 'giliran__count-detail';
        detailSpan.textContent = 'Giliran: ' + (item.giliran || []).join(', ');

        row.appendChild(nameSpan);
        row.appendChild(timesSpan);
        row.appendChild(detailSpan);
        el.counts.appendChild(row);
      });
    }

    if (el.result) {
      el.result.hidden = false;
    }
  }

  function submitGiliran() {
    if (state.busy) return;

    var namesVal = el.names ? el.names.value.trim() : '';
    if (!namesVal) {
      setStatus('Masukkan dulu daftar nama, satu nama per baris.', 'error');
      if (el.names) el.names.focus();
      return;
    }

    var form = new FormData();
    form.append('names', el.names.value);
    form.append('mode', el.mode ? el.mode.value : 'harian');
    form.append('per_slot', el.perSlot ? el.perSlot.value : '2');
    form.append('slots', el.slots ? el.slots.value : '8');
    if (el.mulai && el.mulai.value) {
      form.append('tanggal_mulai', el.mulai.value);
    }
    var urutanVal = el.urutan ? el.urutan.value : 'maju';
    form.append('urutan', urutanVal);
    if (urutanVal === 'acak' && el.seed && el.seed.value.trim() !== '') {
      form.append('seed', el.seed.value.trim());
    }
    var lewatiVal = el.lewati && !el.lewati.disabled ? el.lewati.checked : false;
    form.append('lewati_akhir_pekan', lewatiVal ? 'true' : 'false');

    state.busy = true;
    updateControls();
    setStatus('Sedang menyusun jadwal giliran...', 'busy');

    if (window.AbortController) {
      state.abortController = new AbortController();
    }

    fetch(serverBase + '/api/giliran', {
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
        setStatus('Jadwal giliran berhasil disusun.', 'ok');
      })
      .catch(function (error) {
        if (error && error.name === 'AbortError') {
          setStatus('Penyusunan jadwal dibatalkan.', '');
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

  function copySchedule() {
    if (!state.lastResult) return;
    var text = buildPlainText(state.lastResult);

    function onCopied() {
      if (el.copy) {
        var old = el.copy.textContent;
        el.copy.textContent = 'Tersalin';
        setTimeout(function () {
          el.copy.textContent = old;
        }, 2000);
      }
      setStatus('Jadwal berhasil disalin ke papan klip.', 'ok');
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

  function downloadSchedule() {
    if (!state.lastResult) return;
    var text = buildPlainText(state.lastResult);
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'jadwal-giliran.txt';
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
    if (el.names) el.names.value = '';
    if (el.seed) el.seed.value = '';
    if (el.result) el.result.hidden = true;
    if (el.list) el.list.textContent = '';
    if (el.counts) el.counts.textContent = '';
    state.lastResult = null;
    state.busy = false;
    setStatus('Masukkan daftar nama, lalu tekan "Susun jadwal".', '');
    updateControls();
    if (el.names) el.names.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="giliran"]');
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
      initDefaultDate();
      syncTriggers(true);
      panel.focus({ preventScroll: true });
      if (el.names) el.names.focus();
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
        submitGiliran();
      }
    }
  }

  // Pemasangan pendengar acara (event listener)
  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.names) {
    el.names.addEventListener('input', updateControls);
  }
  if (el.mode) {
    el.mode.addEventListener('change', onModeChange);
  }
  if (el.urutan) {
    el.urutan.addEventListener('change', onUrutanChange);
  }
  if (el.seedClear) {
    el.seedClear.addEventListener('click', function () {
      if (el.seed) {
        el.seed.value = '';
        el.seed.focus();
      }
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitGiliran);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copySchedule);
  if (el.download) el.download.addEventListener('click', downloadSchedule);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['giliran'] = toggle;

  initDefaultDate();
  onModeChange();
  onUrutanChange();
  updateControls();
})();
