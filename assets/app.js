/* app.js — OmniTools (demo) : data alat + render + pencarian + filter + counter.
   Satu-satunya sumber data untuk section "Roadmap Alat" adalah CATEGORIES di bawah. */
(function () {
  'use strict';

  if ('IntersectionObserver' in window) { document.documentElement.classList.add('js-reveal'); }

  // --- Data status ------------------------------------------------------
  // `server` = alat yang benar-benar berfungsi tapi diproses di server (API),
  // bukan di browser. Urutan kunci di sini juga mengurutkan chip filter & counter.
  var STATUS = {
    server: { label: 'Live (API)', short: 'Server', className: 'badge--api' },
    live: { label: 'Live (demo)', short: 'Demo', className: 'badge--live' },
    soon: { label: 'Segera', short: 'Segera', className: 'badge--soon' },
    planned: { label: 'Rencana', short: 'Rencana', className: 'badge--planned' }
  };

  // Panel alat interaktif yang tersedia (didaftarkan oleh skrip panel di bawah).
  function openTool(action) {
    if (window.OmniToolsPanels && typeof window.OmniToolsPanels[action] === 'function') {
      window.OmniToolsPanels[action]();
    }
  }

  // --- Data kategori & alat (sumber tunggal kebenaran) -------------------
  var CATEGORIES = [
    {
      id: 'media',
      name: 'Gambar/Video/Audio',
      icon: 'icon-media',
      tools: [
        { name: 'Image Resizer', desc: 'Ubah dimensi gambar langsung di browser tanpa unggah.', status: 'live' },
        { name: 'Image Converter', desc: 'Konversi format gambar umum tanpa kirim ke server.', status: 'soon' },
        { name: 'Image Editor', desc: 'Edit dasar seperti crop dan rotate di perangkat sendiri.', status: 'soon' },
        { name: 'Video Trimmer', desc: 'Potong klip video pendek tanpa upload.', status: 'soon' },
        { name: 'Video Reverser', desc: 'Balik urutan frame video secara lokal.', status: 'planned' },
        { name: 'Extract Audio', desc: 'Ambil trek audio dari file video di browser.', status: 'planned' }
      ]
    },
    {
      id: 'pdf',
      name: 'PDF',
      icon: 'icon-pdf',
      tools: [
        { name: 'PDF Splitter', desc: 'Pecah dokumen PDF menjadi beberapa berkas.', status: 'soon' },
        { name: 'PDF Merger', desc: 'Gabungkan beberapa PDF jadi satu berkas (diproses di server).', status: 'server', action: 'pdf-merge' },
        { name: 'PDF Editor', desc: 'Sunting teks dan halaman PDF secara ringan.', status: 'planned' },
        { name: 'PDF to Image', desc: 'Ubah tiap halaman PDF menjadi gambar.', status: 'soon' },
        { name: 'Compress PDF', desc: 'Perkecil ukuran berkas PDF tanpa server.', status: 'planned' }
      ]
    },
    {
      id: 'text',
      name: 'Teks & Daftar',
      icon: 'icon-text',
      tools: [
        { name: 'Case Converter', desc: 'Ubah huruf besar/kecil dan format kalimat.', status: 'live' },
        { name: 'List Shuffler', desc: 'Acak urutan baris dalam sebuah daftar.', status: 'soon' },
        { name: 'Text Formatter', desc: 'Rapikan spasi, baris, dan format teks.', status: 'soon' },
        { name: 'Word Counter', desc: 'Hitung jumlah kata, karakter, dan baris.', status: 'live' },
        { name: 'Remove Duplicates', desc: 'Hapus baris duplikat dari sebuah daftar.', status: 'soon' }
      ]
    },
    {
      id: 'datetime',
      name: 'Tanggal & Waktu',
      icon: 'icon-clock',
      tools: [
        { name: 'Date Calculator', desc: 'Hitung selisih atau tambahan antar tanggal.', status: 'soon' },
        { name: 'Time Zone Converter', desc: 'Konversi jam antar zona waktu berbeda.', status: 'planned' },
        { name: 'Countdown Timer', desc: 'Hitung mundur ke tanggal atau momen tertentu.', status: 'soon' },
        { name: 'Pomodoro Timer', desc: 'Timer fokus kerja dengan siklus istirahat.', status: 'planned' }
      ]
    },
    {
      id: 'math',
      name: 'Matematika',
      icon: 'icon-math',
      tools: [
        { name: 'Prime Number Generator', desc: 'Hasilkan daftar bilangan prima dengan cepat.', status: 'soon' },
        { name: 'Kalkulator Listrik (V/I/R)', desc: 'Hitung tegangan, arus, dan resistansi.', status: 'planned' },
        { name: 'Kalkulator Persen', desc: 'Hitung persentase, kenaikan, dan potongan.', status: 'soon' },
        { name: 'Unit Converter', desc: 'Konversi satuan panjang, berat, dan lainnya.', status: 'soon' }
      ]
    },
    {
      id: 'data',
      name: 'Data',
      icon: 'icon-data',
      tools: [
        { name: 'JSON Formatter & Validator', desc: 'Rapikan dan validasi struktur JSON.', status: 'live' },
        { name: 'CSV Tools', desc: 'Lihat, sunting, dan konversi berkas CSV.', status: 'soon' },
        { name: 'XML Tools', desc: 'Format dan validasi dokumen XML.', status: 'planned' },
        { name: 'Base64 Encoder/Decoder', desc: 'Encode dan decode teks atau berkas Base64.', status: 'live' },
        { name: 'QR & Barcode Generator', desc: 'Buat kode QR dan barcode dari teks.', status: 'soon' }
      ]
    },
    {
      id: 'ai',
      name: 'AI',
      icon: 'icon-ai',
      tools: [
        { name: 'Ringkas Teks', desc: 'Ringkas dokumen panjang jadi poin utama.', status: 'planned' },
        { name: 'Ubah/Redesign Gambar', desc: 'Ubah gaya visual gambar dengan bantuan AI.', status: 'planned' },
        { name: 'Transkripsi Audio', desc: 'Ubah rekaman suara menjadi teks.', status: 'planned' }
      ]
    }
  ];

  // --- State filter --------------------------------------------------
  var state = { query: '', category: 'all', status: 'all' };

  // --- Ambil elemen (semua dicek null) --------------------------------
  var els = {
    grid: document.getElementById('tools-grid'),
    empty: document.getElementById('tools-empty'),
    counts: document.getElementById('tool-counts'),
    search: document.getElementById('tool-search'),
    categoryFilters: document.getElementById('category-filters'),
    statusFilters: document.getElementById('status-filters'),
    reset: document.getElementById('tools-reset'),
    emptyReset: document.getElementById('tools-empty-reset'),
    tplCard: document.getElementById('tpl-tool-card'),
    tplGroup: document.getElementById('tpl-tool-group')
  };

  // Hanya jalan jika section Alat ada di halaman ini.
  if (!els.grid || !els.tplCard || !els.tplGroup) {
    return;
  }

  // --- Bangun chip filter kategori & status dari data ------------------
  function buildCategoryChips() {
    if (!els.categoryFilters) return;
    var frag = document.createDocumentFragment();
    frag.appendChild(makeChip('all', 'Semua', true));
    CATEGORIES.forEach(function (cat) {
      frag.appendChild(makeChip(cat.id, cat.name, false));
    });
    els.categoryFilters.appendChild(frag);
  }

  function buildStatusChips() {
    if (!els.statusFilters) return;
    var frag = document.createDocumentFragment();
    frag.appendChild(makeChip('all', 'Semua status', true, 'status'));
    Object.keys(STATUS).forEach(function (key) {
      frag.appendChild(makeChip(key, STATUS[key].label, false, 'status'));
    });
    els.statusFilters.appendChild(frag);
  }

  function makeChip(value, label, active, group) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chip' + (active ? ' chip--active' : '');
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    btn.setAttribute('aria-label', 'Filter ' + (group === 'status' ? 'status' : 'kategori') + ': ' + label);
    btn.dataset.value = value;
    btn.textContent = label;
    btn.addEventListener('click', function () {
      if (group === 'status') {
        state.status = value;
        updateChipGroup(els.statusFilters, value);
      } else {
        state.category = value;
        updateChipGroup(els.categoryFilters, value);
      }
      render();
    });
    return btn;
  }

  function updateChipGroup(container, activeValue) {
    if (!container) return;
    var chips = container.querySelectorAll('.chip');
    chips.forEach(function (chip) {
      var isActive = chip.dataset.value === activeValue;
      chip.classList.toggle('chip--active', isActive);
      chip.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  // --- Filter & render ---------------------------------------------------
  function getFilteredTools() {
    var q = state.query.toLowerCase().trim();
    var result = [];
    CATEGORIES.forEach(function (cat) {
      if (state.category !== 'all' && state.category !== cat.id) return;
      cat.tools.forEach(function (tool) {
        if (state.status !== 'all' && state.status !== tool.status) return;
        if (q) {
          var haystack = (tool.name + ' ' + tool.desc + ' ' + cat.name).toLowerCase();
          if (haystack.indexOf(q) === -1) return;
        }
        result.push({ tool: tool, category: cat });
      });
    });
    return result;
  }

  function groupByCategory(items) {
    var order = [];
    var map = {};
    items.forEach(function (item) {
      var id = item.category.id;
      if (!map[id]) {
        map[id] = { category: item.category, tools: [] };
        order.push(id);
      }
      map[id].tools.push(item.tool);
    });
    return order.map(function (id) { return map[id]; });
  }

  function renderTools(items) {
    els.grid.textContent = '';
    var groups = groupByCategory(items);

    if (groups.length === 0) {
      els.grid.hidden = true;
      if (els.empty) els.empty.hidden = false;
      return;
    }
    els.grid.hidden = false;
    if (els.empty) els.empty.hidden = true;

    var fragAll = document.createDocumentFragment();
    groups.forEach(function (group) {
      var groupNode = els.tplGroup.content.firstElementChild.cloneNode(true);
      var titleEl = groupNode.querySelector('.tool-group__title');
      var countEl = groupNode.querySelector('.tool-group__count');
      var listEl = groupNode.querySelector('.tool-group__list');
      var noteEl = groupNode.querySelector('.tool-group__note');

      if (titleEl) {
        titleEl.textContent = group.category.name;
        if (group.category.id === 'ai') {
          var aiBadge = document.createElement('span');
          aiBadge.className = 'badge badge--planned';
          aiBadge.textContent = STATUS.planned.label;
          titleEl.appendChild(document.createTextNode(' '));
          titleEl.appendChild(aiBadge);
        }
      }
      if (countEl) countEl.textContent = '(' + group.tools.length + ')';
      if (noteEl && group.category.id === 'ai') {
        noteEl.textContent = 'Semua alat AI masih tahap rencana.';
        noteEl.hidden = false;
      }

      group.tools.forEach(function (tool) {
        var cardNode = els.tplCard.content.firstElementChild.cloneNode(true);
        var useEl = cardNode.querySelector('use');
        var titleNode = cardNode.querySelector('.tool-card__title');
        var descNode = cardNode.querySelector('.tool-card__desc');
        var statusNode = cardNode.querySelector('.tool-card__status');
        var bodyNode = cardNode.querySelector('.tool-card__body');

        if (useEl) useEl.setAttribute('href', '#' + group.category.icon);
        if (titleNode) titleNode.textContent = tool.name;
        if (descNode) descNode.textContent = tool.desc;
        if (statusNode) {
          var info = STATUS[tool.status];
          statusNode.textContent = info.label;
          statusNode.className = 'badge ' + info.className + ' tool-card__status';
        }

        // Alat yang punya panel interaktif: kartu bisa diklik + tombol "Buka alat"
        // (tombol = jalur keyboard; klik area kartu = kenyamanan tambahan).
        if (tool.action && bodyNode) {
          cardNode.classList.add('tool-card--actionable');
          cardNode.dataset.toolAction = tool.action;

          var openBtn = document.createElement('button');
          openBtn.type = 'button';
          openBtn.className = 'tool-card__open';
          openBtn.setAttribute('aria-haspopup', 'dialog');
          openBtn.setAttribute('aria-label', 'Buka alat ' + tool.name);
          openBtn.textContent = 'Buka alat';
          openBtn.addEventListener('click', function (event) {
            event.stopPropagation();
            openTool(tool.action);
          });
          bodyNode.appendChild(openBtn);

          cardNode.addEventListener('click', function () { openTool(tool.action); });
        }

        if (listEl) listEl.appendChild(cardNode);
      });

      fragAll.appendChild(groupNode);
    });
    els.grid.appendChild(fragAll);
  }

  function updateCounts(items) {
    if (!els.counts) return;
    var counts = {};
    Object.keys(STATUS).forEach(function (key) { counts[key] = 0; });
    items.forEach(function (item) {
      if (counts[item.tool.status] !== undefined) counts[item.tool.status] += 1;
    });
    var parts = ['Total: ' + items.length];
    Object.keys(STATUS).forEach(function (key) {
      parts.push(STATUS[key].short + ': ' + counts[key]);
    });
    els.counts.textContent = parts.join(' · ');
  }

  function updateResetVisibility() {
    if (!els.reset) return;
    var hasFilter = state.query !== '' || state.category !== 'all' || state.status !== 'all';
    els.reset.hidden = !hasFilter;
  }

  function render() {
    var items = getFilteredTools();
    renderTools(items);
    updateCounts(items);
    updateResetVisibility();
  }

  // --- Pencarian dengan debounce ~120ms ----------------------------------
  var searchTimer = null;
  function onSearchInput(e) {
    var value = e.target.value;
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(function () {
      state.query = value;
      render();
    }, 120);
  }

  // --- Reset ---------------------------------------------------------
  function onReset() {
    state.query = '';
    state.category = 'all';
    state.status = 'all';
    if (els.search) els.search.value = '';
    updateChipGroup(els.categoryFilters, 'all');
    updateChipGroup(els.statusFilters, 'all');
    render();
    if (els.search) els.search.focus();
  }

  // --- Reveal animasi ringan saat masuk viewport --------------------------
  function setupReveal() {
    var targets = document.querySelectorAll('.reveal');
    if (!targets.length) return;

    // Failsafe: kalau observer tidak pernah memicu, paksa tampil setelah 2.5s.
    window.setTimeout(function () {
      document.querySelectorAll('.reveal:not(.is-visible)').forEach(function (el) {
        el.classList.add('is-visible');
      });
    }, 2500);

    if (!('IntersectionObserver' in window)) {
      targets.forEach(function (t) { t.classList.add('is-visible'); });
      return;
    }

    try {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0, rootMargin: '0px 0px -10% 0px' });
      targets.forEach(function (t) { observer.observe(t); });
    } catch (e) {
      targets.forEach(function (t) { t.classList.add('is-visible'); });
    }
  }

  // --- Init ---------------------------------------------------------
  buildCategoryChips();
  buildStatusChips();
  if (els.search) els.search.addEventListener('input', onSearchInput);
  if (els.reset) els.reset.addEventListener('click', onReset);
  if (els.emptyReset) els.emptyReset.addEventListener('click', onReset);
  setupReveal();
  render();
})();

/* =========================================================================
   Panel alat: PDF Merger
   Alat ini BENAR-BENAR diproses di server (bukan di browser): berkas dikirim
   ke POST /api/pdf/merge milik OmniTools API, digabung di memori server,
   lalu hasilnya diunduh. Karena itu tidak ada klaim "client-side" di sini.

   Skrip sengaja terpisah dari daftar alat di atas supaya keduanya tidak
   saling bergantung (daftar alat tetap jalan walau panel tidak ada).
   ========================================================================= */
(function () {
  'use strict';

  var modal = document.getElementById('pdf-merge-modal');
  if (!modal) return;

  var el = {
    dialog: document.getElementById('pdf-merge-dialog'),
    close: document.getElementById('pdf-merge-close'),
    limits: document.getElementById('pdf-merge-limits'),
    input: document.getElementById('pdf-merge-input'),
    drop: document.getElementById('pdf-merge-drop'),
    list: document.getElementById('pdf-merge-list'),
    empty: document.getElementById('pdf-merge-empty'),
    status: document.getElementById('pdf-merge-status'),
    submit: document.getElementById('pdf-merge-submit'),
    clear: document.getElementById('pdf-merge-clear'),
    download: document.getElementById('pdf-merge-download')
  };

  // Aturan bawaan: dipakai sampai /limits menjawab, atau bila API belum tersambung.
  var FALLBACK_LIMITS = { max_files: 10, max_total_mb: 25, max_total_bytes: 26214400, max_pages: 200 };

  // Awalan URL API. Kosong = same-origin (path /api/... lewat gateway).
  // Bisa diarahkan ke origin lain lewat <meta name="omnitools-api-base"> atau ?api=
  var apiBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-api-base"]');
  if (metaBase && metaBase.content) apiBase = metaBase.content.trim().replace(/\/+$/, '');
  try {
    var apiParam = new URLSearchParams(window.location.search).get('api');
    if (apiParam) apiBase = apiParam.trim().replace(/\/+$/, '');
  } catch (err) { /* URLSearchParams tidak tersedia — abaikan */ }

  var state = {
    files: [],
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    busy: false,
    downloadUrl: null,
    lastFocus: null
  };
  var focusSpec = null; // { index, act } — fokus yang dipulihkan setelah daftar digambar ulang

  // --- Pembantu ---------------------------------------------------------
  function maxFiles() { return state.limits.max_files || FALLBACK_LIMITS.max_files; }
  function maxBytes() { return state.limits.max_total_bytes || FALLBACK_LIMITS.max_total_bytes; }
  function maxPages() { return state.limits.max_pages || FALLBACK_LIMITS.max_pages; }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1).replace('.', ',') + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2).replace('.', ',') + ' MB';
  }

  function totalBytes() {
    return state.files.reduce(function (sum, file) { return sum + file.size; }, 0);
  }

  function fileKey(file) {
    return [file.name, file.size, file.lastModified].join('|');
  }

  // Saringan cepat di klien. Pemeriksaan sebenarnya tetap di server (magic bytes
  // %PDF-), jadi klien tidak bisa "menipu" server hanya dengan mengubah nama.
  function looksLikePdf(file) {
    var name = (file.name || '').toLowerCase();
    return name.slice(-4) === '.pdf' || file.type === 'application/pdf';
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

  function updateControls() {
    var hasFiles = state.files.length > 0;
    if (el.submit) {
      el.submit.disabled = state.busy || !hasFiles;
      el.submit.textContent = state.busy ? 'Memproses…' : 'Gabung PDF';
    }
    if (el.clear) el.clear.disabled = state.busy || !hasFiles;
    if (el.empty) el.empty.hidden = hasFiles;
    if (el.list) el.list.hidden = !hasFiles;
  }

  // --- Daftar berkas ----------------------------------------------------
  function makeIconButton(act, index, glyph, label, disabled) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'iconbtn' + (act === 'remove' ? ' iconbtn--danger' : '');
    btn.dataset.act = act;
    btn.dataset.index = String(index);
    btn.textContent = glyph;
    btn.setAttribute('aria-label', label);
    btn.disabled = !!disabled;
    return btn;
  }

  function renderList() {
    if (!el.list) return;
    el.list.textContent = '';

    state.files.forEach(function (file, index) {
      var item = document.createElement('li');
      item.className = 'filelist__item';

      var pos = document.createElement('span');
      pos.className = 'filelist__pos';
      pos.textContent = String(index + 1);

      var meta = document.createElement('span');
      meta.className = 'filelist__meta';
      var nameEl = document.createElement('span');
      nameEl.className = 'filelist__name';
      nameEl.textContent = file.name;
      nameEl.title = file.name;
      var sizeEl = document.createElement('span');
      sizeEl.className = 'filelist__size';
      sizeEl.textContent = formatBytes(file.size);
      meta.appendChild(nameEl);
      meta.appendChild(sizeEl);

      var actions = document.createElement('span');
      actions.className = 'filelist__actions';
      actions.appendChild(makeIconButton('up', index, '↑', 'Naikkan urutan: ' + file.name, index === 0));
      actions.appendChild(makeIconButton('down', index, '↓', 'Turunkan urutan: ' + file.name, index === state.files.length - 1));
      actions.appendChild(makeIconButton('remove', index, '✕', 'Hapus dari daftar: ' + file.name, false));

      item.appendChild(pos);
      item.appendChild(meta);
      item.appendChild(actions);
      el.list.appendChild(item);
    });

    updateControls();
    applyFocus();
  }

  function applyFocus() {
    if (!focusSpec || !el.list) return;
    var spec = focusSpec;
    focusSpec = null;
    var buttons = el.list.querySelectorAll('button[data-act="' + spec.act + '"]');
    var target = buttons[spec.index] || buttons[buttons.length - 1] || el.list.querySelector('button');
    if (target && !target.disabled) {
      target.focus();
    } else if (el.submit) {
      el.submit.focus();
    }
  }

  function moveFile(index, delta) {
    var target = index + delta;
    if (target < 0 || target >= state.files.length) return;
    var item = state.files[index];
    state.files[index] = state.files[target];
    state.files[target] = item;
    focusSpec = { index: target, act: delta < 0 ? 'up' : 'down' };
    renderList();
  }

  function removeFile(index) {
    if (index < 0 || index >= state.files.length) return;
    state.files.splice(index, 1);
    focusSpec = { index: index, act: 'remove' };
    renderList();
    setStatus(state.files.length
      ? 'Berkas dihapus. Urutan daftar = urutan halaman hasil.'
      : 'Daftar kosong. Pilih berkas PDF untuk digabung.');
  }

  function addFiles(fileList) {
    var incoming = Array.prototype.slice.call(fileList || []);
    if (!incoming.length) return;

    var rejected = [];
    var duplicate = 0;
    var tooMany = false;
    var tooBig = false;
    var added = 0;

    incoming.forEach(function (file) {
      if (!looksLikePdf(file)) { rejected.push(file.name || '(tanpa nama)'); return; }
      if (state.files.length >= maxFiles()) { tooMany = true; return; }
      var key = fileKey(file);
      var exists = state.files.some(function (item) { return fileKey(item) === key; });
      if (exists) { duplicate += 1; return; }
      if (totalBytes() + file.size > maxBytes()) { tooBig = true; return; }
      state.files.push(file);
      added += 1;
    });

    renderList();

    var notes = [];
    if (added) notes.push(added + ' berkas ditambahkan.');
    if (rejected.length) notes.push('Bukan PDF, dilewati: ' + rejected.join(', ') + '.');
    if (duplicate) notes.push(duplicate + ' berkas duplikat dilewati.');
    if (tooMany) notes.push('Batas ' + maxFiles() + ' berkas tercapai — sisanya diabaikan.');
    if (tooBig) notes.push('Total melebihi batas ' + state.limits.max_total_mb + ' MB — berkas itu tidak dimasukkan.');
    if (!notes.length) notes.push('Tidak ada berkas yang bisa ditambahkan.');

    var problem = rejected.length > 0 || tooMany || tooBig;
    setStatus(notes.join(' '), (added === 0 && problem) ? 'error' : '');
  }

  // --- Aturan dari server ------------------------------------------------
  function describeLimits(online) {
    if (!el.limits) return;
    var text = 'Maks ' + maxFiles() + ' berkas · total ' + state.limits.max_total_mb
      + ' MB · ' + maxPages() + ' halaman';
    el.limits.textContent = text + (online ? ' · aturan dari server' : ' · aturan bawaan');
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(apiBase + '/api/pdf/merge/limits', { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.limits = {
          max_files: data.max_files || FALLBACK_LIMITS.max_files,
          max_total_bytes: data.max_total_bytes || FALLBACK_LIMITS.max_total_bytes,
          max_total_mb: data.max_total_mb || FALLBACK_LIMITS.max_total_mb,
          max_pages: data.max_pages || FALLBACK_LIMITS.max_pages
        };
        state.limitsLoaded = true;
        describeLimits(true);
      })
      .catch(function () { describeLimits(false); });
  }

  // --- Kirim & proses ----------------------------------------------------
  function revokeDownload() {
    if (state.downloadUrl) {
      try { URL.revokeObjectURL(state.downloadUrl); } catch (err) { /* diabaikan */ }
      state.downloadUrl = null;
    }
  }

  function downloadName(response) {
    var disposition = response.headers.get('Content-Disposition') || '';
    var match = /filename="?([^";]+)"?/.exec(disposition);
    return (match && match[1]) ? match[1] : 'gabungan.pdf';
  }

  function readApiError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) message = parsed.error.message;
      } catch (err) { /* balasan bukan JSON (mis. halaman HTML 404 dari nginx) */ }
      if (!message) {
        message = 'Server membalas HTTP ' + response.status + '.';
        if (response.status === 404) {
          message += ' Endpoint /api/pdf/merge belum tersambung ke container omnitools-api.';
        }
      }
      throw new Error(message);
    });
  }

  function submitFiles() {
    if (state.busy) return;
    if (!state.files.length) {
      setStatus('Pilih minimal satu berkas PDF dulu.', 'error');
      return;
    }
    if (state.files.length > maxFiles()) {
      setStatus('Maksimum ' + maxFiles() + ' berkas per penggabungan.', 'error');
      return;
    }
    var total = totalBytes();
    if (total > maxBytes()) {
      setStatus('Total ukuran ' + formatBytes(total) + ' melebihi batas ' + formatBytes(maxBytes()) + '.', 'error');
      return;
    }

    var form = new FormData();
    state.files.forEach(function (file) { form.append('files', file, file.name); });

    state.busy = true;
    updateControls();
    if (el.download) el.download.hidden = true;
    revokeDownload();
    setStatus('Mengunggah ' + state.files.length + ' berkas (' + formatBytes(total) + ') dan menggabungkan di server…', 'busy');

    fetch(apiBase + '/api/pdf/merge', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readApiError(response);
        return response.blob().then(function (blob) {
          return { blob: blob, pages: response.headers.get('X-Page-Count'), name: downloadName(response) };
        });
      })
      .then(function (result) {
        state.downloadUrl = URL.createObjectURL(result.blob);
        if (el.download) {
          el.download.href = state.downloadUrl;
          el.download.download = result.name;
          el.download.hidden = false;
        }
        var pageInfo = result.pages ? ' → ' + result.pages + ' halaman' : '';
        setStatus(
          'Selesai: ' + state.files.length + ' berkas digabung' + pageInfo + ' · ' +
          formatBytes(result.blob.size) + '. Tekan "Unduh hasil" untuk menyimpan berkas.',
          'ok'
        );
        if (el.download) el.download.focus();
      })
      .catch(function (error) {
        setStatus(error && error.message ? error.message : 'Gagal menggabungkan berkas.', 'error');
      })
      .then(function () {
        state.busy = false;
        updateControls();
      });
  }

  // --- Buka / tutup panel ------------------------------------------------
  function open() {
    if (!modal.hidden) return;
    state.lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add('modal-open');
    if (el.dialog) el.dialog.focus();
    loadLimits();
    renderList();
    if (!state.files.length) {
      setStatus('Pilih berkas PDF, atur urutannya (urutan = urutan halaman), lalu tekan "Gabung PDF".');
    }
  }

  function close() {
    if (modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove('modal-open');
    revokeDownload();
    if (el.download) el.download.hidden = true;
    if (state.lastFocus && typeof state.lastFocus.focus === 'function') state.lastFocus.focus();
    state.lastFocus = null;
  }

  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

  function onKeydown(event) {
    if (modal.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab' || !el.dialog) return;
    var nodes = Array.prototype.filter.call(
      el.dialog.querySelectorAll(FOCUSABLE),
      function (node) { return node.offsetParent !== null || node === document.activeElement; }
    );
    if (!nodes.length) return;
    var first = nodes[0];
    var last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  // --- Pemasangan event --------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
  var backdrop = modal.querySelector('[data-close]');
  if (backdrop) backdrop.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);

  if (el.input) {
    el.input.addEventListener('change', function () {
      addFiles(el.input.files);
      el.input.value = ''; // supaya berkas yang sama bisa dipilih ulang
    });
  }

  if (el.drop) {
    ['dragenter', 'dragover'].forEach(function (type) {
      el.drop.addEventListener(type, function (event) {
        event.preventDefault();
        el.drop.classList.add('is-dragover');
      });
    });
    ['dragleave', 'dragend'].forEach(function (type) {
      el.drop.addEventListener(type, function () { el.drop.classList.remove('is-dragover'); });
    });
    el.drop.addEventListener('drop', function (event) {
      event.preventDefault();
      el.drop.classList.remove('is-dragover');
      if (event.dataTransfer && event.dataTransfer.files) addFiles(event.dataTransfer.files);
    });
  }

  if (el.list) {
    el.list.addEventListener('click', function (event) {
      var btn = event.target.closest ? event.target.closest('button[data-act]') : null;
      if (!btn) return;
      var index = parseInt(btn.dataset.index, 10);
      var act = btn.dataset.act;
      if (act === 'up') moveFile(index, -1);
      else if (act === 'down') moveFile(index, 1);
      else if (act === 'remove') removeFile(index);
    });
  }

  if (el.submit) el.submit.addEventListener('click', submitFiles);

  if (el.clear) {
    el.clear.addEventListener('click', function () {
      state.files = [];
      renderList();
      revokeDownload();
      if (el.download) el.download.hidden = true;
      setStatus('Daftar dikosongkan.');
    });
  }

  window.addEventListener('beforeunload', revokeDownload);

  // Daftarkan panel supaya kartu "PDF Merger" bisa membukanya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['pdf-merge'] = open;
})();
