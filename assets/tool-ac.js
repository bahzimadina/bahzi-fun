/* =========================================================================
   Panel alat: Hitung kapasitas AC ruangan (ac)
   Perkirakan kebutuhan BTU dan ukuran PK AC dari ukuran ruangan,
   jumlah orang, perangkat penghasil panas, dan paparan sinar matahari.
   Semua data diproses di memori server dan tidak disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('ac-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('ac-close'),
    note: document.getElementById('ac-note'),
    panjang: document.getElementById('ac-panjang'),
    lebar: document.getElementById('ac-lebar'),
    tinggi: document.getElementById('ac-tinggi'),
    orang: document.getElementById('ac-orang'),
    perangkat: document.getElementById('ac-perangkat'),
    matahari: document.getElementById('ac-matahari'),
    status: document.getElementById('ac-status'),
    clear: document.getElementById('ac-clear'),
    submit: document.getElementById('ac-submit'),
    result: document.getElementById('ac-result'),
    heroBtu: document.getElementById('ac-hero-btu'),
    heroPk: document.getElementById('ac-hero-pk'),
    statLuas: document.getElementById('ac-stat-luas'),
    statVolume: document.getElementById('ac-stat-volume'),
    statBtuDasar: document.getElementById('ac-stat-btu-dasar'),
    statTambahan: document.getElementById('ac-stat-tambahan'),
    catatanPk: document.getElementById('ac-catatan-pk'),
    tableBody: document.getElementById('ac-table-body'),
    pesan: document.getElementById('ac-pesan'),
    copy: document.getElementById('ac-copy')
  };

  var FALLBACK_LIMITS = {
    panjang: { min: 1, max: 30 },
    lebar: { min: 1, max: 30 },
    tinggi: { min: 2, max: 5, default: 2.8 },
    orang: { min: 1, max: 50, default: 2 },
    perangkat: { min: 0, max: 20, default: 0 },
    matahari: ['teduh', 'sedang', 'terkena matahari langsung'],
    patokan_btu_per_m2: 500,
    pilihan_pk: [
      { pk: '1/2 PK', kapasitas_btu: 5000 },
      { pk: '3/4 PK', kapasitas_btu: 7000 },
      { pk: '1 PK', kapasitas_btu: 9000 },
      { pk: '1 1/4 PK', kapasitas_btu: 11000 },
      { pk: '1 1/2 PK', kapasitas_btu: 12000 },
      { pk: '2 PK', kapasitas_btu: 18000 },
      { pk: '2 1/2 PK', kapasitas_btu: 24000 }
    ]
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

  function formatNumber(num, decimals) {
    var d = typeof decimals === 'number' ? decimals : 0;
    var n = Number(num) || 0;
    return new Intl.NumberFormat('id-ID', {
      minimumFractionDigits: d,
      maximumFractionDigits: d
    }).format(n);
  }

  function formatBtu(num) {
    var n = Math.round(Number(num) || 0);
    return formatNumber(n, 0) + ' BTU/jam';
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
    el.status.appendChild(document.createTextNode(message));
  }

  function updateControls() {
    var pVal = el.panjang ? el.panjang.value.trim() : '';
    var lVal = el.lebar ? el.lebar.value.trim() : '';
    var canSubmit = Boolean(pVal) && Boolean(lVal) && !state.busy;

    if (el.submit) {
      el.submit.disabled = !canSubmit;
    }
    if (el.clear) {
      el.clear.disabled = state.busy && !state.abortController;
    }
  }

  function applyLimits(data) {
    state.limits = {
      panjang: data.panjang || FALLBACK_LIMITS.panjang,
      lebar: data.lebar || FALLBACK_LIMITS.lebar,
      tinggi: data.tinggi || FALLBACK_LIMITS.tinggi,
      orang: data.orang || FALLBACK_LIMITS.orang,
      perangkat: data.perangkat || FALLBACK_LIMITS.perangkat,
      matahari: Array.isArray(data.matahari) ? data.matahari : FALLBACK_LIMITS.matahari,
      patokan_btu_per_m2: data.patokan_btu_per_m2 || FALLBACK_LIMITS.patokan_btu_per_m2,
      pilihan_pk: Array.isArray(data.pilihan_pk) ? data.pilihan_pk : FALLBACK_LIMITS.pilihan_pk
    };

    if (el.panjang) {
      el.panjang.min = String(state.limits.panjang.min || 1);
      el.panjang.max = String(state.limits.panjang.max || 30);
    }
    if (el.lebar) {
      el.lebar.min = String(state.limits.lebar.min || 1);
      el.lebar.max = String(state.limits.lebar.max || 30);
    }
    if (el.tinggi) {
      el.tinggi.min = String(state.limits.tinggi.min || 2);
      el.tinggi.max = String(state.limits.tinggi.max || 5);
      if (!el.tinggi.value && state.limits.tinggi.default) {
        el.tinggi.value = String(state.limits.tinggi.default);
      }
    }
    if (el.orang) {
      el.orang.min = String(state.limits.orang.min || 1);
      el.orang.max = String(state.limits.orang.max || 50);
      if (!el.orang.value && typeof state.limits.orang.default !== 'undefined') {
        el.orang.value = String(state.limits.orang.default);
      }
    }
    if (el.perangkat) {
      el.perangkat.min = String(state.limits.perangkat.min || 0);
      el.perangkat.max = String(state.limits.perangkat.max || 20);
      if (!el.perangkat.value && typeof state.limits.perangkat.default !== 'undefined') {
        el.perangkat.value = String(state.limits.perangkat.default);
      }
    }

    updateControls();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/ac/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        state.limitsLoaded = true;
        applyLimits(data);
      })
      .catch(function () {
        applyLimits(FALLBACK_LIMITS);
      });
  }

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed) {
          if (parsed.pesan) {
            message = parsed.pesan;
          } else if (parsed.error && parsed.error.message) {
            message = parsed.error.message;
          } else if (parsed.detail && parsed.detail.message) {
            message = parsed.detail.message;
          }
        }
      } catch (err) {
        // Abaikan galat parse
      }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan hitung kapasitas AC belum tersambung ke server. Coba lagi nanti.';
        } else {
          message = 'Server membalas HTTP ' + response.status + '. Silakan coba lagi.';
        }
      }

      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function renderResult(data) {
    state.lastResult = data;

    if (el.heroBtu) {
      el.heroBtu.textContent = formatBtu(data.btu);
    }
    if (el.heroPk) {
      if (data.pk) {
        el.heroPk.textContent = 'Rekomendasi: ' + data.pk_label;
      } else {
        el.heroPk.textContent = data.pk_label;
      }
    }

    if (el.statLuas) {
      el.statLuas.textContent = formatNumber(data.luas_m2, 1) + ' m²';
    }
    if (el.statVolume) {
      el.statVolume.textContent = formatNumber(data.volume_m3, 1) + ' m³';
    }
    if (el.statBtuDasar && data.rincian) {
      el.statBtuDasar.textContent = formatNumber(data.rincian.btu_dasar, 0) + ' BTU';
    }
    if (el.statTambahan && data.rincian) {
      var totalTambahan = (data.rincian.tambahan_orang || 0) + (data.rincian.tambahan_perangkat || 0);
      var faktorPct = Math.round(((data.rincian.faktor_matahari || 1) - 1) * 100);
      var tambahanText = '+' + formatNumber(totalTambahan, 0) + ' BTU';
      if (faktorPct > 0) {
        tambahanText += ' (panas +' + faktorPct + '%)';
      }
      el.statTambahan.textContent = tambahanText;
    }

    if (el.catatanPk) {
      if (data.catatan_pk) {
        el.catatanPk.hidden = false;
        el.catatanPk.textContent = data.catatan_pk;
      } else {
        el.catatanPk.hidden = true;
        el.catatanPk.textContent = '';
      }
    }

    if (el.tableBody) {
      el.tableBody.innerHTML = '';
      if (Array.isArray(data.pilihan)) {
        data.pilihan.forEach(function (item) {
          var tr = document.createElement('tr');
          if (data.pk && item.pk === data.pk) {
            tr.className = 'ac__tr--recommended';
          }

          var tdPk = document.createElement('td');
          tdPk.className = 'ac__td-pk';
          tdPk.textContent = item.pk;
          if (data.pk && item.pk === data.pk) {
            var recBadge = document.createElement('span');
            recBadge.className = 'ac__badge-rec';
            recBadge.textContent = ' (Rekomendasi)';
            tdPk.appendChild(recBadge);
          }

          var tdBtu = document.createElement('td');
          tdBtu.className = 'text-right ac__td-btu';
          tdBtu.textContent = formatNumber(item.kapasitas_btu, 0) + ' BTU/jam';

          var tdStatus = document.createElement('td');
          tdStatus.className = 'text-right ac__td-status';
          var badge = document.createElement('span');
          if (item.cukup) {
            badge.className = 'ac__badge ac__badge--cukup';
            badge.textContent = 'Cukup';
          } else {
            badge.className = 'ac__badge ac__badge--kurang';
            badge.textContent = 'Kurang';
          }
          tdStatus.appendChild(badge);

          tr.appendChild(tdPk);
          tr.appendChild(tdBtu);
          tr.appendChild(tdStatus);

          el.tableBody.appendChild(tr);
        });
      }
    }

    if (el.pesan && data.pesan) {
      el.pesan.textContent = data.pesan;
    }

    if (el.result) {
      el.result.hidden = false;
    }
  }

  function submitAc() {
    if (state.busy) return;

    var pStr = el.panjang ? el.panjang.value.trim() : '';
    var lStr = el.lebar ? el.lebar.value.trim() : '';

    if (!pStr) {
      setStatus('Isi panjang ruangan dulu.', 'error');
      if (el.panjang) el.panjang.focus();
      return;
    }
    if (!lStr) {
      setStatus('Isi lebar ruangan dulu.', 'error');
      if (el.lebar) el.lebar.focus();
      return;
    }

    var tStr = el.tinggi ? el.tinggi.value.trim() : '2.8';
    var oStr = el.orang ? el.orang.value.trim() : '2';
    var prStr = el.perangkat ? el.perangkat.value.trim() : '0';
    var mStr = el.matahari ? el.matahari.value : 'teduh';

    var payload = {
      panjang: pStr,
      lebar: lStr,
      tinggi: tStr || '2.8',
      orang: oStr || '2',
      perangkat: prStr || '0',
      matahari: mStr || 'teduh'
    };

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung kapasitas AC ruangan...', 'busy');

    if (window.AbortController) {
      state.abortController = new AbortController();
    }

    fetch(serverBase + '/api/ac', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload),
      signal: state.abortController ? state.abortController.signal : undefined
    })
      .then(function (res) {
        if (!res.ok) return readServerError(res);
        return res.json();
      })
      .then(function (data) {
        renderResult(data);
        setStatus('Kebutuhan AC berhasil dihitung.', 'ok');
      })
      .catch(function (error) {
        if (error && error.name === 'AbortError') {
          setStatus('Perhitungan dibatalkan.', '');
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

  function copyResult() {
    if (!state.lastResult) return;
    var d = state.lastResult;
    var text = 'Kebutuhan pendinginan ruangan: ' + formatBtu(d.btu) +
      ' | Rekomendasi: ' + (d.pk || d.pk_label) +
      ' | Luas: ' + formatNumber(d.luas_m2, 1) + ' m²' +
      ' | Volume: ' + formatNumber(d.volume_m3, 1) + ' m³';

    function onCopied() {
      if (el.copy) {
        var old = el.copy.textContent;
        el.copy.textContent = 'Tersalin';
        setTimeout(function () {
          el.copy.textContent = old;
        }, 2000);
      }
      setStatus('Ringkasan kapasitas AC berhasil disalin ke papan klip.', 'ok');
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

  function resetAll() {
    if (state.abortController) {
      state.abortController.abort();
      state.abortController = null;
    }
    if (el.panjang) el.panjang.value = '4';
    if (el.lebar) el.lebar.value = '5';
    if (el.tinggi) el.tinggi.value = '2.8';
    if (el.orang) el.orang.value = '2';
    if (el.perangkat) el.perangkat.value = '0';
    if (el.matahari) el.matahari.value = 'teduh';
    if (el.result) el.result.hidden = true;
    state.lastResult = null;
    state.busy = false;
    setStatus('Isi ukuran ruangan dan kondisi ruangan, lalu tekan "Hitung kapasitas AC".', '');
    updateControls();
    if (el.panjang) el.panjang.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="ac"]');
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
      if (el.panjang) el.panjang.focus();
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
        submitAc();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.panjang) {
    el.panjang.addEventListener('input', updateControls);
    el.panjang.addEventListener('change', updateControls);
  }
  if (el.lebar) {
    el.lebar.addEventListener('input', updateControls);
    el.lebar.addEventListener('change', updateControls);
  }
  if (el.tinggi) {
    el.tinggi.addEventListener('input', updateControls);
    el.tinggi.addEventListener('change', updateControls);
  }
  if (el.orang) {
    el.orang.addEventListener('input', updateControls);
    el.orang.addEventListener('change', updateControls);
  }
  if (el.perangkat) {
    el.perangkat.addEventListener('input', updateControls);
    el.perangkat.addEventListener('change', updateControls);
  }
  if (el.matahari) {
    el.matahari.addEventListener('change', updateControls);
  }

  if (el.submit) el.submit.addEventListener('click', submitAc);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels.ac = toggle;

  applyLimits(FALLBACK_LIMITS);
  updateControls();
})();
