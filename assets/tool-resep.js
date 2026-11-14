/* =========================================================================
   Panel alat: Sesuaikan resep masakan (resep)
   Hitung ulang jumlah tiap bahan saat resep dibuat untuk porsi berbeda,
   dibulatkan ke takaran dapur yang wajar.
   Semua data diproses di memori server dan tidak disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('resep-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('resep-close'),
    porsiAsal: document.getElementById('resep-porsi-asal'),
    porsiTarget: document.getElementById('resep-porsi-target'),
    bahan: document.getElementById('resep-bahan'),
    isiContoh: document.getElementById('resep-isi-contoh'),
    bulatkan: document.getElementById('resep-bulatkan'),
    submit: document.getElementById('resep-submit'),
    clear: document.getElementById('resep-clear'),
    status: document.getElementById('resep-status'),
    error: document.getElementById('resep-error'),
    result: document.getElementById('resep-result'),
    statFaktor: document.getElementById('resep-stat-faktor'),
    statDihitung: document.getElementById('resep-stat-dihitung'),
    statTidakDihitung: document.getElementById('resep-stat-tidak-dihitung'),
    listBahan: document.getElementById('resep-list-bahan'),
    tidakDihitungWrap: document.getElementById('resep-tidak-dihitung-wrap'),
    listTidakDihitung: document.getElementById('resep-list-tidak-dihitung'),
    note: document.getElementById('resep-note'),
    copy: document.getElementById('resep-copy'),
    download: document.getElementById('resep-download')
  };

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    limits: null,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    abortController: null
  };

  var CONTOH_BAHAN = [
    '500 gram ayam fillet',
    '3 butir telur',
    '3 siung bawang putih',
    '1/2 sdt merica',
    '2 sdm kecap manis',
    'garam secukupnya'
  ].join('\n');

  function formatAngka(num) {
    if (typeof num !== 'number' || isNaN(num)) return '-';
    if (Math.floor(num) === num) return String(num);
    var s = num.toFixed(2).replace(/\.?0+$/, '');
    return s.replace('.', ',');
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

  function showError(message) {
    if (message && el.result) {
      el.result.hidden = true;
    }
    if (!el.error) return;
    if (!message) {
      el.error.hidden = true;
      el.error.textContent = '';
      return;
    }
    el.error.hidden = false;
    el.error.textContent = message;
  }

  function clearError() {
    showError('');
    var invalidInputs = panel.querySelectorAll('[aria-invalid="true"]');
    for (var i = 0; i < invalidInputs.length; i++) {
      invalidInputs[i].removeAttribute('aria-invalid');
    }
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/resep/limits')
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (data) {
        if (!data) return;
        state.limits = data;
        state.limitsLoaded = true;
        if (data.contoh && data.contoh.bahan) {
          CONTOH_BAHAN = data.contoh.bahan;
        }
      })
      .catch(function () {
        // Biarkan bawaan jika gagal memuat limits
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
        // Abaikan galat parsing JSON
      }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan sesuaikan resep masakan belum tersambung ke server. Coba lagi nanti.';
        } else if (response.status === 413) {
          message = 'Daftar bahan terlalu panjang. Kurangi jumlah baris atau panjang teks.';
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
    lines.push('SESUAIKAN RESEP MASAKAN');
    lines.push('=======================');
    lines.push('Porsi resep asli : ' + data.porsi_asal + ' porsi');
    lines.push('Porsi target     : ' + data.porsi_target + ' porsi');
    lines.push('Faktor pengali   : ' + formatAngka(data.faktor) + '×');
    lines.push('Pembulatan dapur : ' + (data.bulatkan ? 'Aktif (dibulatkan ke takaran wajar)' : 'Tidak (angka persis)'));
    lines.push('');
    lines.push('DAFTAR BAHAN BARU:');

    if (Array.isArray(data.bahan) && data.bahan.length > 0) {
      data.bahan.forEach(function (b, idx) {
        var row = (idx + 1) + '. ' + b.teks_baru + ' (asal: ' + b.teks_asal;
        if (data.bulatkan && b.nilai_persis !== b.jumlah_baru) {
          row += ', nilai persis: ' + formatAngka(b.nilai_persis) + (b.satuan ? ' ' + b.satuan : '');
        }
        if (b.padanan) {
          row += ', ' + b.padanan;
        }
        row += ')';
        lines.push(row);
      });
    } else {
      lines.push('(Tidak ada bahan yang dihitung ulang)');
    }

    if (Array.isArray(data.tidak_dihitung) && data.tidak_dihitung.length > 0) {
      lines.push('');
      lines.push('DIBUAT APA ADANYA (TIDAK DIHITUNG ULANG):');
      data.tidak_dihitung.forEach(function (t) {
        lines.push('- ' + t.teks_asal);
      });
    }

    lines.push('');
    lines.push('Catatan:');
    if (Array.isArray(data.catatan)) {
      data.catatan.forEach(function (c) {
        lines.push('- ' + c);
      });
    } else {
      lines.push('- Hitungan ini hanya menyesuaikan takaran bahan masakan secara matematis.');
    }

    return lines.join('\n');
  }

  function buildSummarySentence(data) {
    var parts = [];
    parts.push('Resep disesuaikan dari ' + data.porsi_asal + ' jadi ' + data.porsi_target + ' porsi (faktor ' + formatAngka(data.faktor) + '×):');
    if (Array.isArray(data.bahan)) {
      var itemSummaries = data.bahan.map(function (b) {
        var str = b.teks_baru;
        if (b.padanan) str += ' (' + b.padanan + ')';
        return str;
      });
      parts.push(itemSummaries.join(', '));
    }
    if (Array.isArray(data.tidak_dihitung) && data.tidak_dihitung.length > 0) {
      var unscaled = data.tidak_dihitung.map(function (t) { return t.teks_asal; }).join(', ');
      parts.push('+ ' + unscaled);
    }
    return parts.join(' ');
  }

  function renderResult(data) {
    state.lastResult = data;
    if (!el.result) return;
    el.result.hidden = false;

    if (el.statFaktor) {
      el.statFaktor.textContent = formatAngka(data.faktor) + '×';
    }
    if (el.statDihitung) {
      el.statDihitung.textContent = data.ringkas.jumlah_bahan + ' bahan';
    }
    if (el.statTidakDihitung) {
      el.statTidakDihitung.textContent = data.ringkas.jumlah_tidak_dihitung + ' baris';
    }

    // Render daftar bahan yang dihitung
    if (el.listBahan) {
      el.listBahan.innerHTML = '';
      if (Array.isArray(data.bahan) && data.bahan.length > 0) {
        data.bahan.forEach(function (b) {
          var row = document.createElement('div');
          row.className = 'resep__row';

          var mainWrap = document.createElement('div');
          mainWrap.className = 'resep__row-main';

          var asalSpan = document.createElement('span');
          asalSpan.className = 'resep__row-origin';
          asalSpan.textContent = b.teks_asal;

          var arrow = document.createElement('span');
          arrow.className = 'resep__row-arrow';
          arrow.setAttribute('aria-hidden', 'true');
          arrow.textContent = '→';

          var baruSpan = document.createElement('span');
          baruSpan.className = 'resep__row-new';
          baruSpan.textContent = b.teks_baru;

          mainWrap.appendChild(asalSpan);
          mainWrap.appendChild(arrow);
          mainWrap.appendChild(baruSpan);
          row.appendChild(mainWrap);

          // Rincian kecil bila dibulatkan atau ada padanan kg/liter
          var details = [];
          if (data.bulatkan && b.nilai_persis !== b.jumlah_baru) {
            details.push('Nilai persis: ' + formatAngka(b.nilai_persis) + (b.satuan ? ' ' + b.satuan : ''));
          }
          if (b.padanan) {
            details.push(b.padanan);
          }

          if (details.length > 0) {
            var detailP = document.createElement('p');
            detailP.className = 'resep__row-detail';
            detailP.textContent = details.join(' • ');
            row.appendChild(detailP);
          }

          el.listBahan.appendChild(row);
        });
      } else {
        var emptyP = document.createElement('p');
        emptyP.className = 'resep__hint';
        emptyP.textContent = 'Tidak ada takaran bahan yang dihitung ulang.';
        el.listBahan.appendChild(emptyP);
      }
    }

    // Render daftar yang tidak dihitung
    if (el.tidakDihitungWrap && el.listTidakDihitung) {
      el.listTidakDihitung.innerHTML = '';
      if (Array.isArray(data.tidak_dihitung) && data.tidak_dihitung.length > 0) {
        el.tidakDihitungWrap.hidden = false;
        data.tidak_dihitung.forEach(function (t) {
          var li = document.createElement('li');
          li.className = 'resep__unscaled-item';
          li.textContent = t.teks_asal;
          el.listTidakDihitung.appendChild(li);
        });
      } else {
        el.tidakDihitungWrap.hidden = true;
      }
    }

    if (el.note && Array.isArray(data.catatan)) {
      el.note.textContent = data.catatan.join(' ');
    }
  }

  function updateControls() {
    var disabled = state.busy;
    if (el.submit) el.submit.disabled = disabled;
    if (el.clear) el.clear.disabled = disabled;
    if (el.isiContoh) el.isiContoh.disabled = disabled;
    if (el.porsiAsal) el.porsiAsal.disabled = disabled;
    if (el.porsiTarget) el.porsiTarget.disabled = disabled;
    if (el.bahan) el.bahan.disabled = disabled;
    if (el.bulatkan) el.bulatkan.disabled = disabled;
  }

  function submitResep() {
    if (state.busy) return;
    clearError();

    var pAsal = el.porsiAsal ? el.porsiAsal.value.trim() : '';
    var pTarget = el.porsiTarget ? el.porsiTarget.value.trim() : '';
    var bahanVal = el.bahan ? el.bahan.value.trim() : '';
    var bulatkanVal = el.bulatkan ? el.bulatkan.checked : true;

    if (!pAsal) {
      showError('Porsi resep asli harus diisi.');
      if (el.porsiAsal) {
        el.porsiAsal.setAttribute('aria-invalid', 'true');
        el.porsiAsal.focus();
      }
      return;
    }

    if (!pTarget) {
      showError('Mau jadi berapa porsi harus diisi.');
      if (el.porsiTarget) {
        el.porsiTarget.setAttribute('aria-invalid', 'true');
        el.porsiTarget.focus();
      }
      return;
    }

    if (!bahanVal) {
      showError('Daftar bahan tidak boleh kosong.');
      if (el.bahan) {
        el.bahan.setAttribute('aria-invalid', 'true');
        el.bahan.focus();
      }
      return;
    }

    if (el.result) {
      el.result.hidden = true;
    }

    var form = new FormData();
    form.append('porsi_asal', pAsal);
    form.append('porsi_target', pTarget);
    form.append('bahan', bahanVal);
    form.append('bulatkan', bulatkanVal ? 'true' : 'false');

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung takaran bahan...', 'busy');

    if (window.AbortController) {
      state.abortController = new AbortController();
    }

    fetch(serverBase + '/api/resep', {
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
        setStatus('Penyesuaian resep selesai.', 'ok');
      })
      .catch(function (error) {
        if (el.result) {
          el.result.hidden = true;
        }
        if (error && error.name === 'AbortError') {
          setStatus('Perhitungan dibatalkan.', '');
          return;
        }
        var msg = (error && error.pesanLayanan === true && error.message)
          ? error.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        showError(msg);
        setStatus('Gagal menghitung bahan. Periksa isian formulir.', 'error');
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
    var text = buildSummarySentence(state.lastResult);

    function onCopied() {
      if (el.copy) {
        var old = el.copy.textContent;
        el.copy.textContent = 'Tersalin';
        setTimeout(function () {
          el.copy.textContent = old;
        }, 2000);
      }
      setStatus('Hasil takaran resep berhasil disalin ke papan klip.', 'ok');
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

  function downloadResult() {
    if (!state.lastResult) return;
    var text = buildPlainText(state.lastResult);
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'hasil-resep.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
    setStatus('Berkas hasil-resep.txt berhasil diunduh.', 'ok');
  }

  function isiContohResep() {
    if (el.porsiAsal) el.porsiAsal.value = '4';
    if (el.porsiTarget) el.porsiTarget.value = '10';
    if (el.bahan) el.bahan.value = CONTOH_BAHAN;
    if (el.bulatkan) el.bulatkan.checked = true;
    clearError();
    setStatus('Contoh resep telah diisi. Tekan "Hitung bahan" untuk melihat hasil.', '');
    if (el.porsiTarget) el.porsiTarget.focus();
  }

  function resetAll() {
    if (el.porsiAsal) el.porsiAsal.value = '';
    if (el.porsiTarget) el.porsiTarget.value = '';
    if (el.bahan) el.bahan.value = '';
    if (el.bulatkan) el.bulatkan.checked = true;
    if (el.result) el.result.hidden = true;
    state.lastResult = null;
    clearError();
    setStatus('Masukkan porsi asli, porsi target, dan daftar bahan, lalu tekan "Hitung bahan".', '');
    updateControls();
    if (el.porsiAsal) el.porsiAsal.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="resep"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
  }

  function open() {
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (panel.hidden) {
      state.lastFocus = document.activeElement;
      panel.hidden = false;
      loadLimits();
      syncTriggers(true);
      panel.focus({ preventScroll: true });
      if (el.porsiAsal) {
        el.porsiAsal.focus();
      }
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
        submitResep();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.isiContoh) el.isiContoh.addEventListener('click', isiContohResep);
  if (el.submit) el.submit.addEventListener('click', submitResep);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['resep'] = toggle;

  updateControls();
})();
