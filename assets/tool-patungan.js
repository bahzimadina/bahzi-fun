/* =========================================================================
   Panel alat: Bagi tagihan patungan (patungan)
   Bagi tagihan makan bareng, arisan, atau patungan kado: rata atau sesuai pesanan.
   Semua data diproses di memori server dan tidak disimpan di disk.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('patungan-panel');
  if (!panel) return;

  var el = {
    close: document.getElementById('patungan-close'),
    modeRataBtn: document.getElementById('patungan-mode-rata'),
    modePesananBtn: document.getElementById('patungan-mode-pesanan'),
    rataGroup: document.getElementById('patungan-rata-group'),
    pesananGroup: document.getElementById('patungan-pesanan-group'),
    total: document.getElementById('patungan-total'),
    orang: document.getElementById('patungan-orang'),
    pesanan: document.getElementById('patungan-pesanan'),
    hitungOrang: document.getElementById('patungan-hitung-orang'),
    pajak: document.getElementById('patungan-pajak'),
    layanan: document.getElementById('patungan-layanan'),
    tambahan: document.getElementById('patungan-tambahan'),
    pembulatan: document.getElementById('patungan-pembulatan'),
    submit: document.getElementById('patungan-submit'),
    clear: document.getElementById('patungan-clear'),
    status: document.getElementById('patungan-status'),
    error: document.getElementById('patungan-error'),
    result: document.getElementById('patungan-result'),
    heroPerOrangWrap: document.getElementById('patungan-hero-per-orang-wrap'),
    perOrang: document.getElementById('patungan-per-orang'),
    totalAkhir: document.getElementById('patungan-total-akhir'),
    ditagih: document.getElementById('patungan-ditagih'),
    kelebihan: document.getElementById('patungan-kelebihan'),
    tableWrap: document.getElementById('patungan-table-wrap'),
    tableBody: document.getElementById('patungan-table-body'),
    note: document.getElementById('patungan-note'),
    copy: document.getElementById('patungan-copy'),
    download: document.getElementById('patungan-download')
  };

  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) {
    serverBase = metaBase.content.trim().replace(/\/+$/, '');
  }

  var state = {
    mode: 'rata',
    limits: null,
    limitsLoaded: false,
    busy: false,
    lastFocus: null,
    lastResult: null,
    abortController: null
  };

  function formatRupiah(num) {
    var n = Math.round(Number(num) || 0);
    return 'Rp' + new Intl.NumberFormat('id-ID').format(n);
  }

  function formatNumber(num, decimals) {
    var d = typeof decimals === 'number' ? decimals : 0;
    var n = Number(num) || 0;
    return new Intl.NumberFormat('id-ID', {
      minimumFractionDigits: d,
      maximumFractionDigits: d
    }).format(n);
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

  function updateHitungOrang() {
    if (!el.hitungOrang || !el.pesanan) return;
    var val = el.pesanan.value || '';
    var lines = val.split('\n').filter(function (l) {
      return l.trim().length > 0;
    });
    el.hitungOrang.textContent = lines.length + ' orang';
  }

  function setMode(newMode) {
    state.mode = newMode;
    if (newMode === 'rata') {
      if (el.modeRataBtn) {
        el.modeRataBtn.classList.add('patungan__seg-btn--active');
        el.modeRataBtn.setAttribute('aria-pressed', 'true');
      }
      if (el.modePesananBtn) {
        el.modePesananBtn.classList.remove('patungan__seg-btn--active');
        el.modePesananBtn.setAttribute('aria-pressed', 'false');
      }
      if (el.rataGroup) el.rataGroup.hidden = false;
      if (el.pesananGroup) el.pesananGroup.hidden = true;
    } else {
      if (el.modeRataBtn) {
        el.modeRataBtn.classList.remove('patungan__seg-btn--active');
        el.modeRataBtn.setAttribute('aria-pressed', 'false');
      }
      if (el.modePesananBtn) {
        el.modePesananBtn.classList.add('patungan__seg-btn--active');
        el.modePesananBtn.setAttribute('aria-pressed', 'true');
      }
      if (el.rataGroup) el.rataGroup.hidden = true;
      if (el.pesananGroup) el.pesananGroup.hidden = false;
      updateHitungOrang();
    }
    clearError();
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/patungan/limits')
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (data) {
        if (!data) return;
        state.limits = data;
        state.limitsLoaded = true;

        if (Array.isArray(data.pembulatan_pilihan) && el.pembulatan) {
          var currentVal = el.pembulatan.value;
          el.pembulatan.innerHTML = '';
          var labels = {
            'tidak': 'Tanpa pembulatan',
            '100': 'Rp100',
            '500': 'Rp500',
            '1000': 'Rp1.000'
          };
          data.pembulatan_pilihan.forEach(function (opt) {
            var option = document.createElement('option');
            option.value = opt;
            option.textContent = labels[opt] || opt;
            el.pembulatan.appendChild(option);
          });
          if (data.pembulatan_pilihan.indexOf(currentVal) !== -1) {
            el.pembulatan.value = currentVal;
          }
        }
      })
      .catch(function () {
        // Biarkan opsi bawaan HTML bila request limits gagal
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
          message = 'Layanan bagi tagihan patungan belum tersambung ke server. Coba lagi nanti.';
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
    lines.push('BAGI TAGIHAN PATUNGAN');
    lines.push('=====================');
    lines.push('Mode: ' + (data.mode === 'rata' ? 'Bagi rata' : 'Sesuai pesanan'));
    lines.push('Jumlah orang: ' + data.jumlah_orang + ' orang');
    lines.push('Subtotal: ' + formatRupiah(data.subtotal));

    if (data.pajak_persen > 0 || data.pajak_rp > 0) {
      lines.push('Pajak (' + formatNumber(data.pajak_persen, data.pajak_persen % 1 === 0 ? 0 : 2) + '%): ' + formatRupiah(data.pajak_rp));
    }
    if (data.layanan_persen > 0 || data.layanan_rp > 0) {
      lines.push('Biaya layanan (' + formatNumber(data.layanan_persen, data.layanan_persen % 1 === 0 ? 0 : 2) + '%): ' + formatRupiah(data.layanan_rp));
    }
    if (data.tambahan > 0) {
      lines.push('Biaya tambahan: ' + formatRupiah(data.tambahan));
    }

    lines.push('Total akhir struk: ' + formatRupiah(data.total_akhir));
    var labelPembulatan = data.pembulatan === 'tidak' ? 'Tanpa pembulatan' : ('Rp' + formatNumber(data.pembulatan));
    lines.push('Pembulatan: ' + labelPembulatan);

    if (data.mode === 'rata' && data.per_orang != null) {
      lines.push('Bagian per orang: ' + formatRupiah(data.per_orang));
    }
    lines.push('Total ditagih: ' + formatRupiah(data.total_ditagih));
    if (data.kelebihan > 0) {
      lines.push('Kelebihan pembulatan: ' + formatRupiah(data.kelebihan));
    }

    if (data.mode === 'pesanan' && Array.isArray(data.orang)) {
      lines.push('');
      lines.push('Rincian per orang:');
      data.orang.forEach(function (o, idx) {
        var rincian = 'Pesanan: ' + formatRupiah(o.pesanan) +
          ', Pajak: ' + formatRupiah(o.pajak_rp) +
          ', Layanan: ' + formatRupiah(o.layanan_rp) +
          ', Tambahan: ' + formatRupiah(o.tambahan_rp);
        lines.push((idx + 1) + '. ' + o.nama + ': ' + formatRupiah(o.total) + ' (' + rincian + ')');
      });
    }

    lines.push('');
    lines.push('Catatan:');
    lines.push(data.catatan || 'Hitungan ini perkiraan untuk memudahkan patungan, bukan struk resmi.');
    return lines.join('\n');
  }

  function buildSummarySentence(data) {
    var parts = [];
    parts.push('Total akhir struk: ' + formatRupiah(data.total_akhir));
    if (data.mode === 'rata' && data.per_orang != null) {
      parts.push('Bagian per orang (' + data.jumlah_orang + ' orang): ' + formatRupiah(data.per_orang));
    } else {
      parts.push('Total ditagih (' + data.jumlah_orang + ' orang): ' + formatRupiah(data.total_ditagih));
    }
    if (data.kelebihan > 0) {
      parts.push('Kelebihan pembulatan: ' + formatRupiah(data.kelebihan));
    }
    return parts.join(' | ');
  }

  function renderResult(data) {
    state.lastResult = data;
    if (!el.result) return;
    el.result.hidden = false;

    if (data.mode === 'rata' && data.per_orang != null) {
      if (el.heroPerOrangWrap) el.heroPerOrangWrap.hidden = false;
      if (el.perOrang) el.perOrang.textContent = formatRupiah(data.per_orang);
    } else {
      if (el.heroPerOrangWrap) el.heroPerOrangWrap.hidden = true;
    }

    if (el.totalAkhir) el.totalAkhir.textContent = formatRupiah(data.total_akhir);
    if (el.ditagih) el.ditagih.textContent = formatRupiah(data.total_ditagih);
    if (el.kelebihan) el.kelebihan.textContent = formatRupiah(data.kelebihan);

    if (data.mode === 'pesanan' && Array.isArray(data.orang)) {
      if (el.tableWrap) el.tableWrap.hidden = false;
      if (el.tableBody) {
        el.tableBody.innerHTML = '';
        data.orang.forEach(function (o) {
          var tr = document.createElement('tr');

          var tdNama = document.createElement('td');
          tdNama.textContent = o.nama;

          var tdPesanan = document.createElement('td');
          tdPesanan.className = 'text-right';
          tdPesanan.textContent = formatRupiah(o.pesanan);

          var tdPajak = document.createElement('td');
          tdPajak.className = 'text-right';
          tdPajak.textContent = formatRupiah(o.pajak_rp);

          var tdLayanan = document.createElement('td');
          tdLayanan.className = 'text-right';
          tdLayanan.textContent = formatRupiah(o.layanan_rp);

          var tdTambahan = document.createElement('td');
          tdTambahan.className = 'text-right';
          tdTambahan.textContent = formatRupiah(o.tambahan_rp);

          var tdTotal = document.createElement('td');
          tdTotal.className = 'text-right';
          var strong = document.createElement('strong');
          strong.textContent = formatRupiah(o.total);
          tdTotal.appendChild(strong);

          tr.appendChild(tdNama);
          tr.appendChild(tdPesanan);
          tr.appendChild(tdPajak);
          tr.appendChild(tdLayanan);
          tr.appendChild(tdTambahan);
          tr.appendChild(tdTotal);

          el.tableBody.appendChild(tr);
        });
      }
    } else {
      if (el.tableWrap) el.tableWrap.hidden = true;
    }

    if (el.note) {
      el.note.textContent = data.catatan || '';
    }
  }

  function updateControls() {
    var disabled = state.busy;
    if (el.submit) el.submit.disabled = disabled;
    if (el.clear) el.clear.disabled = disabled;
    if (el.modeRataBtn) el.modeRataBtn.disabled = disabled;
    if (el.modePesananBtn) el.modePesananBtn.disabled = disabled;
  }

  function submitPatungan() {
    if (state.busy) return;
    clearError();

    var form = new FormData();
    form.append('mode', state.mode);

    if (state.mode === 'rata') {
      var totalVal = el.total ? el.total.value.trim() : '';
      var orangVal = el.orang ? el.orang.value.trim() : '';
      if (!totalVal) {
        showError('Total tagihan harus diisi untuk mode bagi rata.');
        if (el.total) {
          el.total.setAttribute('aria-invalid', 'true');
          el.total.focus();
        }
        return;
      }
      if (!orangVal) {
        showError('Jumlah orang harus diisi untuk mode bagi rata.');
        if (el.orang) {
          el.orang.setAttribute('aria-invalid', 'true');
          el.orang.focus();
        }
        return;
      }
      form.append('total', totalVal);
      form.append('orang', orangVal);
    } else {
      var pesananVal = el.pesanan ? el.pesanan.value.trim() : '';
      if (!pesananVal) {
        showError('Daftar pesanan harus diisi untuk mode sesuai pesanan.');
        if (el.pesanan) {
          el.pesanan.setAttribute('aria-invalid', 'true');
          el.pesanan.focus();
        }
        return;
      }
      form.append('pesanan', pesananVal);
    }

    var pajakVal = el.pajak ? el.pajak.value.trim() : '';
    var layananVal = el.layanan ? el.layanan.value.trim() : '';
    var tambahanVal = el.tambahan ? el.tambahan.value.trim() : '';
    var pembulatanVal = el.pembulatan ? el.pembulatan.value : 'tidak';

    if (pajakVal) form.append('pajak', pajakVal);
    if (layananVal) form.append('layanan', layananVal);
    if (tambahanVal) form.append('tambahan', tambahanVal);
    if (pembulatanVal) form.append('pembulatan', pembulatanVal);

    state.busy = true;
    updateControls();
    setStatus('Sedang menghitung pembagian tagihan...', 'busy');

    if (window.AbortController) {
      state.abortController = new AbortController();
    }

    fetch(serverBase + '/api/patungan', {
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
        setStatus('Perhitungan patungan selesai.', 'ok');
      })
      .catch(function (error) {
        if (error && error.name === 'AbortError') {
          setStatus('Perhitungan dibatalkan.', '');
          return;
        }
        var msg = (error && error.pesanLayanan === true && error.message)
          ? error.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        showError(msg);
        setStatus('Gagal menghitung patungan. Periksa isian formulir.', 'error');
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
      setStatus('Ringkasan patungan berhasil disalin ke papan klip.', 'ok');
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
    a.download = 'patungan.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
    setStatus('Berkas patungan.txt berhasil diunduh.', 'ok');
  }

  function resetAll() {
    if (el.total) el.total.value = '';
    if (el.orang) el.orang.value = '';
    if (el.pesanan) el.pesanan.value = '';
    if (el.pajak) el.pajak.value = '';
    if (el.layanan) el.layanan.value = '';
    if (el.tambahan) el.tambahan.value = '';
    if (el.pembulatan) el.pembulatan.value = 'tidak';
    if (el.result) el.result.hidden = true;
    state.lastResult = null;
    clearError();
    updateHitungOrang();
    setMode('rata');
    setStatus('Pilih mode, masukkan nominal tagihan, lalu tekan "Hitung patungan".', '');
    updateControls();
    if (el.total) el.total.focus();
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="patungan"]');
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
      if (state.mode === 'rata' && el.total) {
        el.total.focus();
      } else if (state.mode === 'pesanan' && el.pesanan) {
        el.pesanan.focus();
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
        submitPatungan();
      }
    }
  }

  if (el.close) el.close.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.modeRataBtn) {
    el.modeRataBtn.addEventListener('click', function () {
      setMode('rata');
    });
  }
  if (el.modePesananBtn) {
    el.modePesananBtn.addEventListener('click', function () {
      setMode('pesanan');
    });
  }

  if (el.pesanan) {
    el.pesanan.addEventListener('input', updateHitungOrang);
  }

  if (el.submit) el.submit.addEventListener('click', submitPatungan);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.copy) el.copy.addEventListener('click', copyResult);
  if (el.download) el.download.addEventListener('click', downloadResult);

  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['patungan'] = toggle;

  updateHitungOrang();
  updateControls();
})();
