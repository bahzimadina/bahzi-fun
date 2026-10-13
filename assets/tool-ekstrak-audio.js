/* =========================================================================
   Alat: Ambil Audio dari Video (Ekstrak Audio)
   Semua berkas diproses di layanan lewat memori/tmpfs, lalu langsung dibuang.
   ========================================================================= */
(function () {
  'use strict';

  var app = document.getElementById('eka-app');
  if (!app) return;

  var el = {
    drop: document.getElementById('eka-drop'),
    file: document.getElementById('eka-file'),
    pilihBtn: document.getElementById('eka-pilih-btn'),
    namaBerkas: document.getElementById('eka-nama-berkas'),
    sumberWrap: document.getElementById('eka-sumber-wrap'),
    sumber: document.getElementById('eka-sumber'),
    formatPilihan: document.getElementById('eka-format-pilihan'),
    proses: document.getElementById('eka-proses'),
    reset: document.getElementById('eka-reset'),
    status: document.getElementById('eka-status'),
    batas: document.getElementById('eka-batas'),
    pesanGalat: document.getElementById('eka-pesan-galat'),
    hasil: document.getElementById('eka-hasil'),
    audio: document.getElementById('eka-audio'),
    info: document.getElementById('eka-info'),
    unduh: document.getElementById('eka-unduh'),
    mulaiLagi: document.getElementById('eka-mulai-lagi')
  };

  var state = {
    limits: {
      max_bytes: 25 * 1024 * 1024,
      max_duration_seconds: 300,
      max_output_bytes: 100 * 1024 * 1024,
      allowed_formats: ['MP4', 'MOV', 'WEBM', 'MKV'],
      outputs: [
        { id: 'mp3', label: 'MP3', desc: 'Paling umum dipakai, bisa diputar hampir di semua aplikasi. 192 kbps.', ext: 'mp3' },
        { id: 'm4a', label: 'M4A', desc: 'Kualitas bagus dengan berkas yang lebih kecil (AAC 192 kbps).', ext: 'm4a' },
        { id: 'wav', label: 'WAV', desc: 'Tanpa kompresi, berkas paling besar (PCM 16-bit, 44,1 kHz).', ext: 'wav' }
      ]
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
    el.status.className = 'status eka__status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(msg));
  }

  function getSelectedFormat() {
    var radios = document.querySelectorAll('input[name="eka-format"]');
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) {
        return radios[i].value;
      }
    }
    return 'mp3';
  }

  function renderOutputs(outputs) {
    if (!el.formatPilihan || !Array.isArray(outputs) || outputs.length === 0) return;
    var currentVal = getSelectedFormat();
    el.formatPilihan.innerHTML = '';

    outputs.forEach(function (opt) {
      var label = document.createElement('label');
      label.className = 'eka__format-label';

      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'eka-format';
      input.value = opt.id;
      if (opt.id === currentVal || (!currentVal && opt.id === 'mp3')) {
        input.checked = true;
      }

      var konten = document.createElement('span');
      konten.className = 'eka__format-konten';

      var judul = document.createElement('span');
      judul.className = 'eka__format-judul';
      judul.textContent = opt.label || opt.id.toUpperCase();

      var desc = document.createElement('span');
      desc.className = 'eka__format-desc';
      desc.textContent = opt.desc || '';

      konten.appendChild(judul);
      konten.appendChild(desc);

      label.appendChild(input);
      label.appendChild(konten);
      el.formatPilihan.appendChild(label);
    });
  }

  function loadLimits() {
    fetch('/api/audio/extract/limits')
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
            el.batas.textContent = 'Maksimal ' + maxMb + ' MB, durasi paling lama ' + maxMenit + ' menit.';
          }
          if (data.outputs && Array.isArray(data.outputs)) {
            renderOutputs(data.outputs);
          }
        }
      })
      .catch(function () {
        // Biarkan batas statis tetap aktif bila gagal memuat
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
      if (el.sumberWrap) el.sumberWrap.hidden = false;
    }

    if (el.namaBerkas) {
      el.namaBerkas.textContent = file.name + ' (' + formatBytes(file.size) + ')';
    }

    setStatus('Video dipilih. Tentukan format hasil audio, lalu klik Ambil suaranya.', 'success');
  }

  if (el.sumber) {
    el.sumber.addEventListener('loadedmetadata', function () {
      var dur = el.sumber.duration;
      if (typeof dur === 'number' && !isNaN(dur) && dur > 0) {
        if (dur > state.limits.max_duration_seconds) {
          showError('Durasi video (' + formatTime(dur) + ') melebihi batas 5 menit.');
        }
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
      el.drop.classList.add('eka__drop--active');
    });

    el.drop.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('eka__drop--active');
    });

    el.drop.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('eka__drop--active');
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
    }
    if (el.sumberWrap) el.sumberWrap.hidden = true;

    if (state.hasilUrl) {
      URL.revokeObjectURL(state.hasilUrl);
      state.hasilUrl = null;
    }

    if (el.audio) {
      el.audio.pause();
      el.audio.removeAttribute('src');
      el.audio.load();
    }

    if (el.hasil) el.hasil.hidden = true;
    if (el.namaBerkas) el.namaBerkas.textContent = 'Format didukung: MP4, MOV, WebM, MKV';

    var radios = document.querySelectorAll('input[name="eka-format"]');
    for (var i = 0; i < radios.length; i++) {
      radios[i].checked = radios[i].value === 'mp3';
    }

    clearError();
    setStatus('Pilih video untuk mulai mengambil audio.');
    if (el.pilihBtn) el.pilihBtn.focus();
  }

  if (el.reset) {
    el.reset.addEventListener('click', resetAll);
  }

  if (el.mulaiLagi) {
    el.mulaiLagi.addEventListener('click', resetAll);
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

      var formatVal = getSelectedFormat();

      state.busy = true;
      if (el.proses) el.proses.disabled = true;
      if (el.reset) el.reset.disabled = true;
      setStatus('Sedang mengambil audio…', 'busy');

      var fd = new FormData();
      fd.append('file', state.selectedFile);
      fd.append('format', formatVal);

      fetch('/api/audio/extract', {
        method: 'POST',
        body: fd
      })
        .then(function (res) {
          if (!res.ok) {
            if (res.status === 503) {
              throw new Error('Server sedang memproses audio lain. Coba lagi sebentar lagi.');
            }
            if (res.status === 504) {
              throw new Error('Proses mengambil audio melebihi batas waktu.');
            }
            return res.json().then(function (errJson) {
              var pesan = (errJson && errJson.error && errJson.error.message)
                ? errJson.error.message
                : 'Terjadi kesalahan saat memproses audio.';
              throw new Error(pesan);
            }).catch(function (parseErr) {
              if (parseErr && parseErr.message && parseErr.message !== 'Unexpected token') {
                throw parseErr;
              }
              throw new Error('Terjadi kesalahan saat memproses video (status ' + res.status + ').');
            });
          }

          var audioSecHeader = res.headers.get('X-Audio-Seconds');
          var audioSec = audioSecHeader ? parseFloat(audioSecHeader) : null;
          var outBytesHeader = res.headers.get('X-Output-Bytes');
          var outBytes = outBytesHeader ? parseInt(outBytesHeader, 10) : 0;
          var outFormat = res.headers.get('X-Output-Format') || formatVal;

          var filename = 'suara.' + outFormat;
          var cd = res.headers.get('Content-Disposition');
          if (cd) {
            var match = cd.match(/filename="?([^"]+)"?/);
            if (match && match[1]) {
              filename = match[1];
            }
          }

          return res.blob().then(function (blob) {
            // Cabut object URL lama setiap kali ada hasil baru
            if (state.hasilUrl) {
              URL.revokeObjectURL(state.hasilUrl);
              state.hasilUrl = null;
            }
            state.hasilUrl = URL.createObjectURL(blob);

            if (el.audio) {
              el.audio.src = state.hasilUrl;
            }
            if (el.unduh) {
              el.unduh.href = state.hasilUrl;
              el.unduh.download = filename;
            }
            if (el.info) {
              var sizeLabel = formatBytes(outBytes > 0 ? outBytes : blob.size);
              var durText = (audioSec !== null && !isNaN(audioSec)) ? audioSec + ' detik' : '-';
              el.info.textContent = 'Berkas: ' + filename + ' | Durasi: ' + durText + ' | Ukuran: ' + sizeLabel + ' | Format: ' + outFormat.toUpperCase();
            }
            if (el.hasil) {
              el.hasil.hidden = false;
            }
            setStatus('Audio berhasil diambil.', 'success');
          });
        })
        .catch(function (err) {
          var pesan = (err && err.message) ? err.message : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
          if (pesan.indexOf('Failed to fetch') !== -1 || pesan.indexOf('NetworkError') !== -1) {
            pesan = 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
          }
          showError(pesan);
          setStatus('Pengambilan audio gagal.', 'error');
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
