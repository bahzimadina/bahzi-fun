(function () {
  'use strict';

  var app = document.getElementById('bkv-app');
  if (!app) return;

  var el = {
    drop: document.getElementById('bkv-drop'),
    file: document.getElementById('bkv-file'),
    pilihBtn: document.getElementById('bkv-pilih-btn'),
    namaBerkas: document.getElementById('bkv-nama-berkas'),
    sumberWrap: document.getElementById('bkv-sumber-wrap'),
    sumber: document.getElementById('bkv-sumber'),
    opsiSuara: document.getElementById('bkv-opsi-suara'),
    opsiKecepatan: document.getElementById('bkv-opsi-kecepatan'),
    proses: document.getElementById('bkv-proses'),
    reset: document.getElementById('bkv-reset'),
    status: document.getElementById('bkv-status'),
    batas: document.getElementById('bkv-batas'),
    pesanGalat: document.getElementById('bkv-pesan-galat'),
    hasil: document.getElementById('bkv-hasil'),
    videoHasil: document.getElementById('bkv-video-hasil'),
    info: document.getElementById('bkv-info'),
    unduh: document.getElementById('bkv-unduh'),
    tutup: document.getElementById('bkv-tutup'),
    resetHasil: document.getElementById('bkv-reset-hasil')
  };

  var state = {
    limits: {
      max_bytes: 25 * 1024 * 1024,
      max_duration_seconds: 60,
      max_output_bytes: 100 * 1024 * 1024,
      allowed_formats: ['MP4', 'MOV', 'WEBM', 'MKV'],
      kecepatan: [
        { id: '0.5', label: 'Setengah kecepatan', desc: 'Hasil bergerak dua kali lebih lambat, cocok untuk melihat gerakan kecil.' },
        { id: '1', label: 'Kecepatan asli', desc: 'Video berjalan sesuai kecepatan normal aslinya.' },
        { id: '2', label: 'Dua kali lebih cepat', desc: 'Hasil bergerak dua kali lebih cepat, cocok untuk rekaman panjang.' }
      ],
      suara: [
        { id: 'ikut', label: 'Suara ikut dibalik', desc: 'Suaranya juga diputar mundur sehingga terdengar aneh. Pilih ini kalau suara tidak penting.' },
        { id: 'bisukan', label: 'Tanpa suara', desc: 'Hasilnya tanpa suara sama sekali. Paling aman untuk rekaman rapat atau video berisi percakapan.' }
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
    el.status.className = 'status bkv__status' + (kind ? ' status--' + kind : '');
    if (kind === 'busy') {
      var spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.setAttribute('aria-hidden', 'true');
      el.status.appendChild(spinner);
    }
    el.status.appendChild(document.createTextNode(msg));
  }

  function getSelectedSuara() {
    var radios = document.querySelectorAll('input[name="bkv-suara"]');
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) {
        return radios[i].value;
      }
    }
    return 'ikut';
  }

  function getSelectedKecepatan() {
    var radios = document.querySelectorAll('input[name="bkv-kecepatan"]');
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) {
        return radios[i].value;
      }
    }
    return '1';
  }

  function renderGroupOptions(container, groupName, items, defaultVal) {
    if (!container || !Array.isArray(items) || items.length === 0) return;
    var currentVal = defaultVal;
    var checkedRadio = container.querySelector('input[name="' + groupName + '"]:checked');
    if (checkedRadio) {
      currentVal = checkedRadio.value;
    }

    container.innerHTML = '';
    items.forEach(function (opt) {
      var label = document.createElement('label');
      label.className = 'bkv__opsi-label';

      var input = document.createElement('input');
      input.type = 'radio';
      input.name = groupName;
      input.value = opt.id;
      if (opt.id === currentVal) {
        input.checked = true;
      }

      var konten = document.createElement('span');
      konten.className = 'bkv__opsi-konten';

      var judul = document.createElement('span');
      judul.className = 'bkv__opsi-judul';
      judul.textContent = opt.label || opt.id;

      var desc = document.createElement('span');
      desc.className = 'bkv__opsi-desc';
      desc.textContent = opt.desc || '';

      konten.appendChild(judul);
      konten.appendChild(desc);

      label.appendChild(input);
      label.appendChild(konten);
      container.appendChild(label);
    });
  }

  function loadLimits() {
    fetch('/api/video/reverse/limits')
      .then(function (res) {
        if (!res.ok) throw new Error('Gagal memuat info batas');
        return res.json();
      })
      .then(function (data) {
        if (data && data.max_bytes) {
          state.limits = data;
          if (el.batas) {
            var maxMb = Math.round(data.max_bytes / (1024 * 1024));
            var maxDetik = data.max_duration_seconds;
            el.batas.textContent = 'Maksimal ' + maxMb + ' MB, durasi paling lama ' + maxDetik + ' detik.';
          }
          if (data.suara && Array.isArray(data.suara)) {
            renderGroupOptions(el.opsiSuara, 'bkv-suara', data.suara, getSelectedSuara());
          }
          if (data.kecepatan && Array.isArray(data.kecepatan)) {
            renderGroupOptions(el.opsiKecepatan, 'bkv-kecepatan', data.kecepatan, getSelectedKecepatan());
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

    var name = file.name || '';
    var dotIdx = name.lastIndexOf('.');
    var ext = dotIdx >= 0 ? name.substring(dotIdx + 1).toLowerCase() : '';
    var allowed = ['mp4', 'mov', 'webm', 'mkv'];

    if (allowed.indexOf(ext) === -1) {
      showError('Format berkas belum didukung. Gunakan video MP4, MOV, WebM, atau MKV.');
      return;
    }

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

    setStatus('Video dipilih. Tentukan kecepatan dan suara, lalu klik Balikkan video.', 'success');
  }

  if (el.sumber) {
    el.sumber.addEventListener('loadedmetadata', function () {
      var dur = el.sumber.duration;
      if (typeof dur === 'number' && !isNaN(dur) && dur > 0) {
        if (dur > state.limits.max_duration_seconds) {
          showError('Durasi video (' + formatTime(dur) + ') melebihi batas ' + state.limits.max_duration_seconds + ' detik. Potong dulu videonya.');
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
      el.drop.classList.add('bkv__drop--active');
    });

    el.drop.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('bkv__drop--active');
    });

    el.drop.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.drop.classList.remove('bkv__drop--active');
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

    if (el.videoHasil) {
      el.videoHasil.pause();
      el.videoHasil.removeAttribute('src');
      el.videoHasil.load();
    }

    if (el.hasil) el.hasil.hidden = true;
    if (el.namaBerkas) el.namaBerkas.textContent = 'Format didukung: MP4, MOV, WebM, MKV';

    var radiosSuara = document.querySelectorAll('input[name="bkv-suara"]');
    for (var i = 0; i < radiosSuara.length; i++) {
      radiosSuara[i].checked = (radiosSuara[i].value === 'ikut');
    }

    var radiosKecepatan = document.querySelectorAll('input[name="bkv-kecepatan"]');
    for (var j = 0; j < radiosKecepatan.length; j++) {
      radiosKecepatan[j].checked = (radiosKecepatan[j].value === '1');
    }

    clearError();
    setStatus('Pilih video untuk mulai membalikkan.');
    if (el.pilihBtn) el.pilihBtn.focus();
  }

  function closeResult() {
    if (el.videoHasil) {
      el.videoHasil.pause();
    }
    if (el.hasil) {
      el.hasil.hidden = true;
    }
    if (el.proses) {
      el.proses.focus();
    }
  }

  if (el.reset) {
    el.reset.addEventListener('click', resetAll);
  }

  if (el.tutup) {
    el.tutup.addEventListener('click', closeResult);
  }

  if (el.resetHasil) {
    el.resetHasil.addEventListener('click', resetAll);
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (el.hasil && !el.hasil.hidden) {
        closeResult();
      } else if (app.contains(document.activeElement)) {
        resetAll();
      }
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

      if (el.sumber && typeof el.sumber.duration === 'number' && !isNaN(el.sumber.duration) && el.sumber.duration > state.limits.max_duration_seconds) {
        showError('Durasi video (' + formatTime(el.sumber.duration) + ') melebihi batas ' + state.limits.max_duration_seconds + ' detik. Potong dulu videonya.');
        return;
      }

      var suaraVal = getSelectedSuara();
      var kecepatanVal = getSelectedKecepatan();

      state.busy = true;
      if (el.proses) el.proses.disabled = true;
      if (el.reset) el.reset.disabled = true;
      setStatus('Sedang membalik video… ini bisa memakan waktu', 'busy');

      var fd = new FormData();
      fd.append('file', state.selectedFile);
      fd.append('suara', suaraVal);
      fd.append('kecepatan', kecepatanVal);

      fetch('/api/video/reverse', {
        method: 'POST',
        body: fd
      })
        .then(function (res) {
          if (!res.ok) {
            if (res.status === 503) {
              throw new Error('Server sedang membalik video lain. Coba lagi sebentar lagi.');
            }
            if (res.status === 504) {
              throw new Error('Proses membalik video melebihi batas waktu.');
            }
            return res.json().then(function (errJson) {
              var pesan = (errJson && errJson.error && errJson.error.message)
                ? errJson.error.message
                : 'Terjadi kesalahan saat membalik video.';
              throw new Error(pesan);
            }).catch(function (parseErr) {
              if (parseErr && parseErr.message && parseErr.message.indexOf('Unexpected token') === -1) {
                throw parseErr;
              }
              throw new Error('Terjadi kesalahan saat memproses video (status ' + res.status + ').');
            });
          }

          var srcSecHeader = res.headers.get('X-Source-Seconds');
          var srcSec = srcSecHeader ? parseFloat(srcSecHeader) : null;
          var resSecHeader = res.headers.get('X-Result-Seconds');
          var resSec = resSecHeader ? parseFloat(resSecHeader) : null;
          var audioMode = res.headers.get('X-Audio-Mode') || suaraVal;
          var speed = res.headers.get('X-Speed') || kecepatanVal;

          var filename = 'video-dibalik.mp4';
          var cd = res.headers.get('Content-Disposition');
          if (cd) {
            var match = cd.match(/filename="?([^"]+)"?/);
            if (match && match[1]) {
              filename = match[1];
            }
          }

          return res.blob().then(function (blob) {
            if (state.hasilUrl) {
              URL.revokeObjectURL(state.hasilUrl);
              state.hasilUrl = null;
            }
            state.hasilUrl = URL.createObjectURL(blob);

            if (el.videoHasil) {
              el.videoHasil.src = state.hasilUrl;
            }
            if (el.unduh) {
              el.unduh.href = state.hasilUrl;
              el.unduh.download = filename;
            }
            if (el.info) {
              var sizeLabel = formatBytes(blob.size);
              var durText = (resSec !== null && !isNaN(resSec)) ? resSec + ' detik' : '-';
              var speedLabel = (speed === '0.5') ? '0.5x (lambat)' : (speed === '2' ? '2x (cepat)' : '1x (asli)');
              var suaraLabel = (audioMode === 'ikut') ? 'Suara ikut dibalik' : ((audioMode === 'tanpa suara') ? 'Tanpa suara' : 'Otomatis tanpa suara');
              el.info.textContent = 'Berkas: ' + filename + ' | Durasi: ' + durText + ' | Kecepatan: ' + speedLabel + ' | Suara: ' + suaraLabel + ' | Ukuran: ' + sizeLabel;
            }
            if (el.hasil) {
              el.hasil.hidden = false;
            }
            setStatus('Video berhasil dibalik.', 'success');
            if (el.unduh) {
              el.unduh.focus();
            }
          });
        })
        .catch(function (err) {
          var pesan = (err && err.message) ? err.message : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
          if (pesan.indexOf('Failed to fetch') !== -1 || pesan.indexOf('NetworkError') !== -1) {
            pesan = 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
          }
          showError(pesan);
          setStatus('Pembalikan video gagal.', 'error');
        })
        .finally(function () {
          state.busy = false;
          if (el.proses) el.proses.disabled = false;
          if (el.reset) el.reset.disabled = false;
        });
    });
  }

  loadLimits();
})();
