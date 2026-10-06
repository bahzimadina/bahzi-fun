/* =========================================================================
   Panel alat: Pomodoro Timer
   Jadwal disusun lewat layanan backend, lalu hitung mundur berdetak di
   peramban. Pengguna bisa menjeda, melanjutkan, melewati langkah, atau
   mengatur ulang jadwal. Tidak ada aset eksternal dan tidak ada pelacakan.
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('pomodoro-panel');
  if (!panel) return;

  var metaServer = document.querySelector('meta[name="omnitools-server-base"]');
  var serverBase = (metaServer && metaServer.getAttribute('content')) || '';
  serverBase = serverBase.replace(/\/+$/, '');

  var el = {
    panel: panel,
    title: document.getElementById('pomodoro-title'),
    limits: document.getElementById('pomodoro-limits'),
    note: document.getElementById('pomodoro-note'),
    close: document.getElementById('pomodoro-close'),
    mode: document.getElementById('pomodoro-mode'),
    sesi: document.getElementById('pomodoro-sesi'),
    mulai: document.getElementById('pomodoro-mulai'),
    groupKustom: document.getElementById('pomodoro-group-kustom'),
    kerja: document.getElementById('pomodoro-kerja'),
    istirahat: document.getElementById('pomodoro-istirahat'),
    istirahatPanjang: document.getElementById('pomodoro-istirahat-panjang'),
    status: document.getElementById('pomodoro-status'),
    clear: document.getElementById('pomodoro-clear'),
    submit: document.getElementById('pomodoro-submit'),
    results: document.getElementById('pomodoro-results'),
    resultHint: document.getElementById('pomodoro-result-hint'),
    outputWrap: document.getElementById('pomodoro-output-wrap'),
    stepBadge: document.getElementById('pomodoro-step-badge'),
    posBadge: document.getElementById('pomodoro-pos-badge'),
    time: document.getElementById('pomodoro-time'),
    progressFill: document.getElementById('pomodoro-progress-fill'),
    progressBar: document.getElementById('pomodoro-progress-bar'),
    btnToggle: document.getElementById('pomodoro-btn-toggle'),
    btnSkip: document.getElementById('pomodoro-btn-skip'),
    btnResetTimer: document.getElementById('pomodoro-btn-reset-timer'),
    sound: document.getElementById('pomodoro-sound'),
    totalFokus: document.getElementById('pomodoro-total-fokus'),
    totalIstirahat: document.getElementById('pomodoro-total-istirahat'),
    totalSemua: document.getElementById('pomodoro-total-semua'),
    cardSelesai: document.getElementById('pomodoro-card-selesai'),
    estSelesai: document.getElementById('pomodoro-est-selesai'),
    timeline: document.getElementById('pomodoro-timeline')
  };

  var state = {
    modes: [],
    limitsLoaded: false,
    limitsLoading: false,
    busy: false,
    lastFocus: null,
    scheduleData: null,
    steps: [],
    currentStepIndex: 0,
    remainingSeconds: 0,
    totalStepSeconds: 0,
    timerRunning: false,
    timerPaused: false,
    timerFinished: false,
    targetEndTime: null,
    pausedRemainingMs: 0,
    intervalId: null
  };

  var audioCtx = null;

  function playCue() {
    if (!el.sound || !el.sound.checked) return;

    try {
      var AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        if (!audioCtx) {
          audioCtx = new AudioContext();
        }
        if (audioCtx.state === 'suspended') {
          audioCtx.resume();
        }
        var osc = audioCtx.createOscillator();
        var gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(659.25, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.15);
        gain.gain.setValueAtTime(0.18, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.35);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(audioCtx.currentTime);
        osc.stop(audioCtx.currentTime + 0.35);
      }
    } catch (e) {
      /* Bunyi dilewati bila tidak didukung */
    }

    try {
      if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
        navigator.vibrate([200, 100, 200]);
      }
    } catch (e) {
      /* Getaran dilewati bila tidak didukung */
    }
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

  function formatTime(sec) {
    var safeSec = Math.max(0, parseInt(sec, 10) || 0);
    var m = Math.floor(safeSec / 60);
    var s = safeSec % 60;
    return (m < 10 ? '0' + m : String(m)) + ':' + (s < 10 ? '0' + s : String(s));
  }

  function formatReadableDuration(sec) {
    var totalSec = Math.max(0, parseInt(sec, 10) || 0);
    if (totalSec === 0) return '0 menit';
    var jam = Math.floor(totalSec / 3600);
    var menit = Math.floor((totalSec % 3600) / 60);
    var parts = [];
    if (jam > 0) parts.push(jam + ' jam');
    if (menit > 0) parts.push(menit + ' menit');
    if (parts.length === 0) parts.push(totalSec + ' detik');
    return parts.join(' ');
  }

  function updateModeUI() {
    var modeVal = el.mode ? el.mode.value : 'klasik';
    if (el.groupKustom) {
      el.groupKustom.hidden = (modeVal !== 'kustom');
    }
    updateControls();
  }

  function updateControls() {
    var modeVal = el.mode ? el.mode.value : 'klasik';
    var sesiVal = el.sesi ? parseInt(el.sesi.value, 10) : 4;
    var valid = !isNaN(sesiVal) && sesiVal >= 1 && sesiVal <= 12;

    if (modeVal === 'kustom') {
      var k = el.kerja ? parseInt(el.kerja.value, 10) : NaN;
      var i = el.istirahat ? parseInt(el.istirahat.value, 10) : NaN;
      var ip = el.istirahatPanjang ? parseInt(el.istirahatPanjang.value, 10) : NaN;
      if (isNaN(k) || k < 1 || k > 180) valid = false;
      if (isNaN(i) || i < 1 || i > 60) valid = false;
      if (isNaN(ip) || ip < 1 || ip > 90) valid = false;
    }

    if (el.submit) {
      el.submit.disabled = state.busy || !valid;
      el.submit.textContent = state.busy ? 'Menyusun...' : 'Susun jadwal';
    }

    if (el.clear) {
      var hasSchedule = (state.steps.length > 0);
      var isDirty = (modeVal !== 'klasik' || (el.sesi && el.sesi.value !== '4') || (el.mulai && el.mulai.value !== ''));
      el.clear.disabled = state.busy || (!hasSchedule && !isDirty);
    }
  }

  function loadLimits() {
    if (state.limitsLoaded || state.limitsLoading) return;
    state.limitsLoading = true;

    fetch(serverBase + '/api/pomodoro/limits', {
      headers: { credentials: 'same-origin', Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limitsLoading = false;
        if (!data) return;

        if (Array.isArray(data.modes) && data.modes.length > 0) {
          state.modes = data.modes;
          if (el.mode) {
            var curMode = el.mode.value || 'klasik';
            el.mode.innerHTML = '';
            for (var i = 0; i < data.modes.length; i++) {
              var m = data.modes[i];
              var opt = document.createElement('option');
              opt.value = m.id;
              opt.textContent = m.label;
              if (m.id === curMode) opt.selected = true;
              el.mode.appendChild(opt);
            }
          }
        }

        if (data.limits && el.limits) {
          el.limits.textContent = 'Fokus 1-180 menit, 1-12 sesi berulang';
        }

        state.limitsLoaded = true;
        updateModeUI();
      })
      .catch(function () {
        state.limitsLoading = false;
        updateModeUI();
      });
  }

  function stopInterval() {
    if (state.intervalId) {
      clearInterval(state.intervalId);
      state.intervalId = null;
    }
  }

  function updateTimerDisplay() {
    var step = state.steps[state.currentStepIndex];
    if (!step) return;

    if (el.time) {
      el.time.textContent = formatTime(state.remainingSeconds);
    }

    if (el.stepBadge) {
      el.stepBadge.textContent = step.label;
      el.stepBadge.className = 'pomodoro__step-badge pomodoro__step-badge--' + step.jenis;
    }

    if (el.posBadge) {
      var totalSesi = state.scheduleData ? state.scheduleData.sesi_fokus : 4;
      if (step.jenis === 'fokus') {
        var focusCount = 0;
        for (var i = 0; i <= state.currentStepIndex; i++) {
          if (state.steps[i].jenis === 'fokus') focusCount++;
        }
        el.posBadge.textContent = 'Sesi fokus ' + focusCount + ' dari ' + totalSesi;
      } else if (step.jenis === 'istirahat_panjang') {
        el.posBadge.textContent = 'Istirahat panjang';
      } else {
        el.posBadge.textContent = 'Istirahat pendek';
      }
    }

    var progressPct = 0;
    if (state.totalStepSeconds > 0) {
      var elapsed = state.totalStepSeconds - state.remainingSeconds;
      progressPct = Math.min(100, Math.max(0, (elapsed / state.totalStepSeconds) * 100));
    }
    if (el.progressFill) {
      el.progressFill.style.width = progressPct.toFixed(1) + '%';
    }
    if (el.progressBar) {
      el.progressBar.setAttribute('aria-valuenow', Math.round(progressPct));
    }

    if (el.btnToggle) {
      if (state.timerFinished) {
        el.btnToggle.textContent = 'Mulai lagi';
        el.btnToggle.className = 'btn btn--primary';
      } else if (state.timerRunning) {
        el.btnToggle.textContent = 'Jeda';
        el.btnToggle.className = 'btn btn--ghost';
      } else if (state.timerPaused) {
        el.btnToggle.textContent = 'Lanjutkan';
        el.btnToggle.className = 'btn btn--primary';
      } else {
        el.btnToggle.textContent = 'Mulai';
        el.btnToggle.className = 'btn btn--primary';
      }
    }

    updateTimelineHighlight();
  }

  function updateTimelineHighlight() {
    if (!el.timeline) return;
    var items = el.timeline.children;
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      item.classList.remove('pomodoro__item--active', 'pomodoro__item--done');
      if (i < state.currentStepIndex) {
        item.classList.add('pomodoro__item--done');
      } else if (i === state.currentStepIndex && !state.timerFinished) {
        item.classList.add('pomodoro__item--active');
      }
    }
  }

  function tick() {
    if (!state.timerRunning || !state.targetEndTime) return;

    var diffMs = state.targetEndTime - Date.now();
    if (diffMs <= 0) {
      advanceStep(false);
      return;
    }

    state.remainingSeconds = Math.max(0, Math.ceil(diffMs / 1000));
    updateTimerDisplay();
  }

  function startCurrentStepTimer() {
    stopInterval();
    state.timerRunning = true;
    state.timerPaused = false;
    state.timerFinished = false;
    state.targetEndTime = Date.now() + (state.remainingSeconds * 1000);
    state.intervalId = setInterval(tick, 250);
    updateTimerDisplay();
  }

  function pauseTimer() {
    if (!state.timerRunning) return;
    stopInterval();
    state.timerRunning = false;
    state.timerPaused = true;
    if (state.targetEndTime) {
      state.pausedRemainingMs = Math.max(0, state.targetEndTime - Date.now());
      state.remainingSeconds = Math.max(0, Math.ceil(state.pausedRemainingMs / 1000));
    }
    updateTimerDisplay();
    setStatus('Timer dijeda. Tekan "Lanjutkan" untuk meneruskan.', '');
  }

  function resumeTimer() {
    if (!state.timerPaused) return;
    state.targetEndTime = Date.now() + (state.remainingSeconds * 1000);
    state.timerRunning = true;
    state.timerPaused = false;
    stopInterval();
    state.intervalId = setInterval(tick, 250);
    updateTimerDisplay();
    var cur = state.steps[state.currentStepIndex];
    setStatus('Sedang berjalan: ' + (cur ? cur.label : '') + '.', 'ok');
  }

  function advanceStep(manualSkip) {
    playCue();

    if (state.currentStepIndex + 1 < state.steps.length) {
      state.currentStepIndex++;
      var nextStep = state.steps[state.currentStepIndex];
      state.remainingSeconds = nextStep.durasi_detik;
      state.totalStepSeconds = nextStep.durasi_detik;

      if (state.timerRunning) {
        startCurrentStepTimer();
        setStatus((manualSkip ? 'Langkah dilewati. ' : 'Waktu habis! ') + 'Sekarang: ' + nextStep.label + '.', 'ok');
      } else {
        updateTimerDisplay();
        setStatus((manualSkip ? 'Langkah dilewati. ' : '') + 'Siap untuk ' + nextStep.label + '.', '');
      }
    } else {
      // Seluruh langkah selesai
      stopInterval();
      state.timerRunning = false;
      state.timerPaused = false;
      state.timerFinished = true;
      state.remainingSeconds = 0;
      updateTimerDisplay();
      setStatus('Seluruh rangkaian Pomodoro selesai. Selamat, kerja fokusmu tuntas!', 'ok');
    }
  }

  function resetCurrentStep() {
    var step = state.steps[state.currentStepIndex];
    if (!step) return;
    state.remainingSeconds = step.durasi_detik;
    state.totalStepSeconds = step.durasi_detik;
    if (state.timerRunning) {
      startCurrentStepTimer();
    } else {
      state.timerPaused = false;
      updateTimerDisplay();
    }
    setStatus('Langkah ' + step.label + ' diulang dari awal.', '');
  }

  function renderTimeline(steps) {
    if (!el.timeline) return;
    el.timeline.innerHTML = '';

    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      var li = document.createElement('li');
      li.className = 'pomodoro__item pomodoro__item--' + s.jenis;

      var numSpan = document.createElement('span');
      numSpan.className = 'pomodoro__item-num';
      numSpan.textContent = String(s.urutan);

      var bodyDiv = document.createElement('div');
      bodyDiv.className = 'pomodoro__item-body';

      var labelSpan = document.createElement('span');
      labelSpan.className = 'pomodoro__item-label';
      labelSpan.textContent = s.label;

      var durSpan = document.createElement('span');
      durSpan.className = 'pomodoro__item-dur';
      var durTeks = formatReadableDuration(s.durasi_detik);
      if (s.jam_mulai && s.jam_selesai) {
        durTeks += ' (' + s.jam_mulai + ' - ' + s.jam_selesai + ')';
      }
      durSpan.textContent = durTeks;

      bodyDiv.appendChild(labelSpan);
      bodyDiv.appendChild(durSpan);

      li.appendChild(numSpan);
      li.appendChild(bodyDiv);
      el.timeline.appendChild(li);
    }
  }

  function renderSchedule(data) {
    state.scheduleData = data;
    state.steps = data.langkah || [];
    state.currentStepIndex = 0;

    if (state.steps.length > 0) {
      var first = state.steps[0];
      state.remainingSeconds = first.durasi_detik;
      state.totalStepSeconds = first.durasi_detik;
    } else {
      state.remainingSeconds = 0;
      state.totalStepSeconds = 0;
    }

    state.timerRunning = false;
    state.timerPaused = false;
    state.timerFinished = false;

    if (el.totalFokus) {
      el.totalFokus.textContent = formatReadableDuration(data.total_fokus_detik);
    }
    if (el.totalIstirahat) {
      el.totalIstirahat.textContent = formatReadableDuration(data.total_istirahat_detik);
    }
    if (el.totalSemua) {
      el.totalSemua.textContent = formatReadableDuration(data.total_detik);
    }

    if (el.cardSelesai && el.estSelesai) {
      if (data.perkiraan_selesai) {
        el.cardSelesai.hidden = false;
        el.estSelesai.textContent = data.perkiraan_selesai + ' WIB';
      } else {
        el.cardSelesai.hidden = true;
      }
    }

    renderTimeline(state.steps);

    if (el.resultHint) el.resultHint.hidden = true;
    if (el.outputWrap) el.outputWrap.hidden = false;

    updateTimerDisplay();
  }

  function resetAll() {
    stopInterval();
    state.scheduleData = null;
    state.steps = [];
    state.currentStepIndex = 0;
    state.remainingSeconds = 0;
    state.totalStepSeconds = 0;
    state.timerRunning = false;
    state.timerPaused = false;
    state.timerFinished = false;

    if (el.mode) el.mode.value = 'klasik';
    if (el.sesi) el.sesi.value = '4';
    if (el.mulai) el.mulai.value = '';
    if (el.kerja) el.kerja.value = '25';
    if (el.istirahat) el.istirahat.value = '5';
    if (el.istirahatPanjang) el.istirahatPanjang.value = '15';

    updateModeUI();

    if (el.resultHint) el.resultHint.hidden = false;
    if (el.outputWrap) el.outputWrap.hidden = true;
    if (el.timeline) el.timeline.innerHTML = '';

    setStatus('Pilih mode dan jumlah sesi, lalu tekan "Susun jadwal".', '');
    updateControls();

    if (el.mode) el.mode.focus();
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
        /* Abaikan parse error */
      }

      if (!message) {
        if (response.status === 404) {
          message = 'Layanan Pomodoro belum terhubung. Coba lagi sebentar lagi.';
        } else if (response.status === 413) {
          message = 'Ukuran permintaan melebihi batas yang diperbolehkan.';
        } else {
          message = 'Terjadi kendala saat menyusun jadwal Pomodoro (HTTP ' + response.status + '). Coba lagi sebentar lagi.';
        }
      }

      var e = new Error(message);
      e.pesanLayanan = true;
      throw e;
    });
  }

  function submitSchedule() {
    if (state.busy) return;

    var modeVal = el.mode ? el.mode.value : 'klasik';
    var sesiVal = el.sesi ? el.sesi.value.trim() : '4';
    var mulaiVal = el.mulai ? el.mulai.value.trim() : '';

    var form = new FormData();
    form.append('mode', modeVal);
    form.append('sesi', sesiVal || '4');
    if (mulaiVal) {
      form.append('mulai', mulaiVal);
    }

    if (modeVal === 'kustom') {
      if (el.kerja && el.kerja.value.trim()) {
        form.append('kerja', el.kerja.value.trim());
      }
      if (el.istirahat && el.istirahat.value.trim()) {
        form.append('istirahat', el.istirahat.value.trim());
      }
      if (el.istirahatPanjang && el.istirahatPanjang.value.trim()) {
        form.append('istirahat_panjang', el.istirahatPanjang.value.trim());
      }
    }

    state.busy = true;
    stopInterval();
    updateControls();
    setStatus('Sedang menyusun jadwal...', 'busy');

    fetch(serverBase + '/api/pomodoro', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
        return response.json();
      })
      .then(function (data) {
        renderSchedule(data);
        setStatus('Jadwal siap. Tekan "Mulai" untuk memulai sesi fokus.', 'ok');
      })
      .catch(function (err) {
        var msg = (err && err.pesanLayanan === true && err.message)
          ? err.message
          : 'Koneksi ke layanan gagal. Coba lagi sebentar lagi.';
        setStatus(msg, 'error');
      })
      .finally(function () {
        state.busy = false;
        updateControls();
      });
  }

  function onToggleClick() {
    if (state.steps.length === 0) return;

    if (state.timerFinished) {
      state.currentStepIndex = 0;
      var first = state.steps[0];
      state.remainingSeconds = first.durasi_detik;
      state.totalStepSeconds = first.durasi_detik;
      startCurrentStepTimer();
      setStatus('Sesi Pomodoro dimulai lagi dari awal.', 'ok');
    } else if (state.timerRunning) {
      pauseTimer();
    } else if (state.timerPaused) {
      resumeTimer();
    } else {
      startCurrentStepTimer();
      var cur = state.steps[state.currentStepIndex];
      setStatus('Sesi ' + (cur ? cur.label : '') + ' dimulai.', 'ok');
    }
  }

  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('[data-tool-action="pomodoro"]');
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].setAttribute('aria-expanded', expanded ? 'true' : 'false');
      triggers[i].setAttribute('aria-controls', 'pomodoro-panel');
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
    } catch (e) {
      /* Abaikan */
    }

    try {
      panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      panel.scrollIntoView(true);
    }

    if (el.mode) {
      setTimeout(function () { el.mode.focus(); }, 100);
    }
  }

  function close() {
    if (panel.hidden) return;
    pauseTimer();
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

  if (el.mode) {
    el.mode.addEventListener('change', function () {
      updateModeUI();
    });
  }

  function onInputKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitSchedule();
    }
  }

  if (el.sesi) {
    el.sesi.addEventListener('input', updateControls);
    el.sesi.addEventListener('keydown', onInputKeydown);
  }
  if (el.mulai) {
    el.mulai.addEventListener('input', updateControls);
    el.mulai.addEventListener('keydown', onInputKeydown);
  }
  if (el.kerja) {
    el.kerja.addEventListener('input', updateControls);
    el.kerja.addEventListener('keydown', onInputKeydown);
  }
  if (el.istirahat) {
    el.istirahat.addEventListener('input', updateControls);
    el.istirahat.addEventListener('keydown', onInputKeydown);
  }
  if (el.istirahatPanjang) {
    el.istirahatPanjang.addEventListener('input', updateControls);
    el.istirahatPanjang.addEventListener('keydown', onInputKeydown);
  }

  if (el.submit) el.submit.addEventListener('click', submitSchedule);
  if (el.clear) el.clear.addEventListener('click', resetAll);
  if (el.btnToggle) el.btnToggle.addEventListener('click', onToggleClick);
  if (el.btnSkip) el.btnSkip.addEventListener('click', function () { advanceStep(true); });
  if (el.btnResetTimer) el.btnResetTimer.addEventListener('click', resetCurrentStep);

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
        submitSchedule();
      }
    }
  }
  document.addEventListener('keydown', onKeydown);

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && !panel.hidden && state.timerRunning) {
      tick();
    }
  });

  window.addEventListener('pageshow', function () {
    if (!panel.hidden && state.timerRunning) {
      tick();
    }
  });

  // Daftarkan ke registry global
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['pomodoro'] = toggle;

  // Inisialisasi awal
  loadLimits();
  updateModeUI();
  updateControls();

  // Dukungan buka lewat parameter ?alat=pomodoro
  function handleUrlParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('alat') !== 'pomodoro') return;

      var maxCardAttempts = 10;
      var cardIntervalMs = 100;
      var cardAttempts = 0;

      function tryOpen() {
        var trigger = document.querySelector('button.tool-card__open[data-tool-action="pomodoro"]');
        if (trigger) {
          trigger.click();
          if (panel.hidden) open();
          return;
        }

        cardAttempts++;
        if (cardAttempts < maxCardAttempts) {
          setTimeout(tryOpen, cardIntervalMs);
        } else {
          open();
        }
      }

      tryOpen();
    } catch (e) {
      /* Abaikan kegagalan pembacaan query */
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', handleUrlParam);
  } else {
    handleUrlParam();
  }
})();
