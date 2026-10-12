/* =========================================================================
   Alat: Video Trimmer (Potong Video)
   Semua berkas diproses di layanan lewat memori/tmpfs, lalu langsung dibuang.
   ========================================================================= */
(function () {
  'use strict';

  var app = document.getElementById('ptv-app');
  if (!app) return;

  var el = {
    drop: document.getElementById('ptv-drop'),
    file: document.getElementById('ptv-file'),
    pilihBtn: document.getElementById('ptv-pilih-btn'),
    namaBerkas: document.getElementById('ptv-nama-berkas'),
    sumber: document.getElementById('ptv-sumber'),
    mulai: document.getElementById('ptv-mulai'),
    ambilMulai: document.getElementById('ptv-ambil-mulai'),
    akhir: document.getElementById('ptv-akhir'),
    ambilAkhir: document.getElementById('ptv-ambil-akhir'),
    proses: document.getElementById('ptv-proses'),
    reset: document.getElementById('ptv-reset'),
    status: document.getElementById('ptv-status'),
    batas: document.getElementById('ptv-batas'),
    pesanGalat: document.getElementById('ptv-pesan-galat'),
    hasil: document.getElementById('ptv-hasil'),
    pratinjau: document.getElementById('ptv-pratinjau'),
    info: document.getElementById('ptv-info'),
    unduh: document.getElementById('ptv-unduh'),
    modeRadios: document.querySelectorAll('input[name="ptv-mode"]')
  };

  var state = {
    limits: {
      max_bytes: 25 * 1024 * 1024,
      max_duration_seconds: 300,
      min_clip_seconds: 1,
      max_clip_seconds: 120,
      max_output_bytes: 100 * 1024 * 1024,
      allowed_formats: ['MP4', 'MOV', 'WEBM', 'MKV']
    },
    selectedFile: null,
    sumberUrl: null,
    hasilUrl: null,
    busy: false
  };

  function formatBytes(bytes) {
    if (typeof bytes !== 'number' || isNaN(bytes)) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) {
      return (bytes / 1024).toLocaleString('id-ID', { maximumFractionDigits: 1 }) + ' KB';
    }
    return (bytes / 1048576).toLocaleString('id-ID', { maximumFractionDigits: 1 }) + ' MB';
  }

  function formatTime(sec) {
    if (typeof sec !== 'number' || isNaN(sec) || sec < 0) return '00:00';
    var totalSec = Math.floor(sec);
    var h = Math.floor(totalSec / 3600);
    var m = Math.floor((totalSec % 3600) / 60);
    var s = totalSec % 60;
    var sStr = (s < 10 ? '0' : '') + s;

    if (h > 0) {
      var mStr = (m < 10 ? '0' : '') + m;
      return (h < 10 ? '0' : '') + h + ':' + mStr + ':' + sStr;
    }
    return (m < 10 ? '0' : '') + m + ':' + sStr;
  }

  function showError(msg) {
    if (!el.pesanGalat) return;
    el.pesanGalat.textContent = msg;
    el.pesanGalat.hidden = false;
  }

  function clearError() {
    if (!el.pesanGalat) return;
    el.pesanGalat.textContent = '';
    el.pesanGalat.hidden = true;
  }

  function setStatus(msg, kind) {
    if (!el.status) return;
    el.status.textContent = '';
    el.status.className = 'status ptv__status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(msg));
  }

  function getSelectedMode() {
    for (var i = 0; i < el.modeRadios.length; i++) {
      if (el.modeRadios[i].checked) {
        return el.modeRadios[i].value;
      }
    }
    return 'cepat';
  }

  function loadLimits() {
    fetch('/api/video/trim/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('Gagal memuat info batas');
        return res.json();
      })
      .then(function (data) {
        if (data && data.max_bytes) {
          state.limits = data;
          if (el.batas) {
            var maxMb = Math.round(data.max_bytes / (1024 * 1024));
            var maxMenit = Math.round(data.max_duration_seconds / 60);
            el.batas.textContent = 'Maksimal ' + maxMb + ' MB, paling lama ' + maxMenit + ' menit, potongan ' + data.min_clip_seconds + ' sampai ' + data.max_clip_seconds + ' detik.';
          }
        }
      })
      .catch(function () {
        // Biarkan teks batas statis tetap terlihat bila fetch gagal
      });
  }

  function handleFile(file) {
    if (!file) return;
    clearError();

    // Validasi ekstensi
    var name = file.name || '';
    var dotIdx = name.lastIndexOf('.');
    var ext = dotIdx >= 0 ? name.substring(dotIdx + 1).toLowerCase() : '';
    var allowed = ['mp4', 'mov', 'webm', 'mkv'];

    if (allowed.indexOf(ext) === -1) {
      showError('Format berkas belum didukung. Gunakan video MP4, MOV, WebM, atau MKV.');
      return;
    }

    // Validasi ukuran
    if (file.size > state.limits.max_bytes) {
      var maxMb = Math.round(state.limits.max_bytes / (1024 * 1024));
      showError('Ukuran video melebihi batas ' + maxMb + ' MB.');
      return;
    }

    if (file.size === 0) {
      showError('Berkas video kosong.');
      return;
    }

    if (state.sumberUrl) {
      URL.revokeObjectURL(state.sumberUrl);
      state.sumberUrl = null;
    }

    state.selectedFile = file;
    state.sumberUrl = URL.createObjectURL(file);

    if (el.sumber) {
      el.sumber.src = state.sumberUrl;
      el.sumber.hidden = false;
    }

    if (el.namaBerkas) {
      el.namaBerkas.textContent = file.name + ' (' + formatBytes(file.size) + ')';
    }

    setStatus('Video dimuat. Tentukan detik mulai dan selesai, lalu potong.', 'success');
  }

  if (el.sumber) {
    el.sumber.addEventListener('loadedmetadata', function () {
      var dur = el.sumber.duration;
      if (typeof dur === 'number' && !isNaN(dur) && dur > 0) {
        if (dur > state.limits.max_duration_seconds) {
          showError('Durasi video (' + Math.round(dur) + ' detik) melebihi batas 5 menit.');
        }
        if (el.mulai) el.mulai.value = '00:00';
        if (el.akhir) el.akhir.value = formatTime(dur);
      }
    });
  }

  if (el.drop) {
    el.drop.addEventListener('click', function (e) {
      if (e.target !== el.file) {
        if (el.file) el.file.click();
      }
    });

    el.drop.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        if (el.file) el.file.click();
      }
    });

    el.drop.addEventListener('dragover', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.add('ptv__drop--active');
    });

    el.drop.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('ptv__drop--active');
    });

    el.drop.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('ptv__drop--active');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
      }
    });
  }

  if (el.file) {
    el.file.addEventListener('change', function () {
      if (el.file.files && el.file.files.length > 0) {
        handleFile(el.file.files[0]);
      }
    });
  }

  if (el.pilihBtn) {
    el.pilihBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (el.file) el.file.click();
    });
  }

  if (el.ambilMulai) {
    el.ambilMulai.addEventListener('click', function () {
      if (!el.sumber) return;
      var cur = el.sumber.currentTime || 0;
      if (el.mulai) el.mulai.value = formatTime(cur);
    });
  }

  if (el.ambilAkhir) {
    el.ambilAkhir.addEventListener('click', function () {
      if (!el.sumber) return;
      var cur = el.sumber.currentTime || 0;
      if (el.akhir) el.akhir.value = formatTime(cur);
    });
  }

  function resetAll() {
    if (el.file) el.file.value = '';
    state.selectedFile = null;

    if (state.sumberUrl) {
      URL.revokeObjectURL(state.sumberUrl);
      state.sumberUrl = null;
    }

    if (el.sumber) {
      el.sumber.pause();
      el.sumber.removeAttribute('src');
      el.sumber.load();
      el.sumber.hidden = true;
    }

    if (state.hasilUrl) {
      URL.revokeObjectURL(state.hasilUrl);
      state.hasilUrl = null;
    }

    if (el.pratinjau) {
      el.pratinjau.pause();
      el.pratinjau.removeAttribute('src');
      el.pratinjau.load();
    }

    if (el.hasil) el.hasil.hidden = true;
    if (el.namaBerkas) el.namaBerkas.textContent = 'Format didukung: MP4, MOV, WebM, MKV';
    if (el.mulai) el.mulai.value = '00:00';
    if (el.akhir) el.akhir.value = '';

    for (var i = 0; i < el.modeRadios.length; i++) {
      el.modeRadios[i].checked = el.modeRadios[i].value === 'cepat';
    }

    clearError();
    setStatus('Pilih video untuk mulai memotong.');
    if (el.pilihBtn) el.pilihBtn.focus();
  }

  if (el.reset) {
    el.reset.addEventListener('click', resetAll);
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && app.contains(document.activeElement)) {
      resetAll();
    }
  });

  if (el.proses) {
    el.proses.addEventListener('click', function () {
      if (state.busy) return;
      clearError();

      if (!state.selectedFile) {
        showError('Pilih berkas video terlebih dahulu.');
        return;
      }

      var mulaiVal = el.mulai ? el.mulai.value.trim() : '';
      var akhirVal = el.akhir ? el.akhir.value.trim() : '';

      if (!mulaiVal) {
        showError('Waktu mulai belum diisi.');
        return;
      }
      if (!akhirVal) {
        showError('Waktu selesai belum diisi.');
        return;
      }

      var modeVal = getSelectedMode();

      state.busy = true;
      if (el.proses) el.proses.disabled = true;
      if (el.reset) el.reset.disabled = true;
      setStatus('Sedang memotong…', 'busy');

      var fd = new FormData();
      fd.append('file', state.selectedFile);
      fd.append('mulai', mulaiVal);
      fd.append('akhir', akhirVal);
      fd.append('mode', modeVal);

      fetch('/api/video/trim', {
        method: 'POST',
        body: fd
      })
        .then(function (res) {
          if (!res.ok) {
            return res.json().then(function (errJson) {
              var pesan = (errJson && errJson.error && errJson.error.message)
                ? errJson.error.message
                : 'Terjadi kesalahan saat memproses video.';
              throw new Error(pesan);
            }).catch(function (parseErr) {
              if (parseErr && parseErr.message && parseErr.message !== 'Unexpected token') {
                throw parseErr;
              }
              throw new Error('Terjadi kesalahan saat memproses video (status ' + res.status + ').');
            });
          }

          var clipSec = res.headers.get('X-Clip-Seconds') || '-';
          var outBytesHeader = res.headers.get('X-Output-Bytes');
          var outBytes = outBytesHeader ? parseInt(outBytesHeader, 10) : 0;
          var outMode = res.headers.get('X-Mode') || modeVal;
          var modeLabel = outMode === 'presisi' ? 'potong presisi' : 'potong cepat';

          var filename = 'potongan.mp4';
          var cd = res.headers.get('Content-Disposition');
          if (cd) {
            var match = cd.match(/filename="?([^"]+)"?/);
            if (match && match[1]) {
              filename = match[1];
            }
          } else if (outMode === 'cepat' && state.selectedFile && (state.selectedFile.name.endsWith('.webm') || state.selectedFile.name.endsWith('.mkv'))) {
            filename = 'potongan.webm';
          }

          return res.blob().then(function (blob) {
            if (state.hasilUrl) {
              URL.revokeObjectURL(state.hasilUrl);
              state.hasilUrl = null;
            }
            state.hasilUrl = URL.createObjectURL(blob);

            if (el.pratinjau) {
              el.pratinjau.src = state.hasilUrl;
            }
            if (el.unduh) {
              el.unduh.href = state.hasilUrl;
              el.unduh.download = filename;
            }
            if (el.info) {
              var sizeLabel = formatBytes(outBytes > 0 ? outBytes : blob.size);
              el.info.textContent = 'Durasi: ' + clipSec + ' detik | Ukuran: ' + sizeLabel + ' | Mode: ' + modeLabel;
            }
            if (el.hasil) {
              el.hasil.hidden = false;
            }
            setStatus('Pemotongan video selesai.', 'success');
          });
        })
        .catch(function (err) {
          var pesan = (err && err.message) ? err.message : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
          if (pesan.indexOf('Failed to fetch') !== -1 || pesan.indexOf('NetworkError') !== -1) {
            pesan = 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
          }
          showError(pesan);
          setStatus('Pemotongan gagal.', 'error');
        })
        .finally(function () {
          state.busy = false;
          if (el.proses) el.proses.disabled = false;
          if (el.reset) el.reset.disabled = false;
        });
    });
  }

  // Muat info batas awal
  loadLimits();
})();
