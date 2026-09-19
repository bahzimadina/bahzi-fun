/* app.js: data alat, render, pencarian, filter, dan penghitung.
   Satu-satunya sumber data untuk daftar alat adalah CATEGORIES di bawah. */
(function () {
  'use strict';

  if ('IntersectionObserver' in window) { document.documentElement.classList.add('js-reveal'); }

  // --- Data status ------------------------------------------------------
  // Status disederhanakan jadi dua: alat yang bisa dipakai sekarang, dan alat
  // yang masih disiapkan. Urutan kunci di sini juga mengurutkan chip filter & counter.
  var STATUS = {
    available: { label: 'Tersedia', short: 'Tersedia', className: 'badge--available' },
    soon: { label: 'Segera', short: 'Segera', className: 'badge--soon' }
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
        { name: 'Image Resizer', desc: 'Ubah dimensi gambar langsung di browser tanpa unggah.', status: 'available', action: 'image-resizer' },
        { name: 'Image Converter', desc: 'Konversi format gambar (PNG, JPG, WebP, SVG) di server.', status: 'available', action: 'image-converter' },
        { name: 'Image Editor', desc: 'Edit dasar seperti crop dan rotate di perangkat sendiri.', status: 'soon' },
        { name: 'Video Trimmer', desc: 'Potong klip video pendek tanpa upload.', status: 'soon' },
        { name: 'Video Reverser', desc: 'Balik urutan frame video secara lokal.', status: 'soon' },
        { name: 'Extract Audio', desc: 'Ambil trek audio dari file video di browser.', status: 'soon' }
      ]
    },
    {
      id: 'pdf',
      name: 'PDF',
      icon: 'icon-pdf',
      tools: [
        { name: 'PDF Splitter', desc: 'Pecah dokumen PDF menjadi beberapa berkas.', status: 'soon' },
        { name: 'PDF Merger', desc: 'Gabungkan beberapa PDF jadi satu berkas (diproses di server).', status: 'available', action: 'pdf-merge' },
        { name: 'PDF Editor', desc: 'Sunting teks dan halaman PDF secara ringan.', status: 'soon' },
        { name: 'PDF to Image', desc: 'Ubah tiap halaman PDF menjadi gambar.', status: 'soon' },
        { name: 'Compress PDF', desc: 'Perkecil ukuran berkas PDF tanpa server.', status: 'soon' }
      ]
    },
    {
      id: 'text',
      name: 'Teks & Daftar',
      icon: 'icon-text',
      tools: [
        { name: 'Case Converter', desc: 'Ubah huruf besar/kecil dan format kalimat.', status: 'available', action: 'case-convert' },
        { name: 'List Shuffler', desc: 'Acak urutan baris dalam sebuah daftar.', status: 'soon' },
        { name: 'Text Formatter', desc: 'Bereskan spasi, baris, dan format teks.', status: 'soon' },
        { name: 'Word Counter', desc: 'Hitung kata, karakter, kalimat, dan perkiraan waktu baca.', status: 'available', action: 'word-count' },
        { name: 'Remove Duplicates', desc: 'Hapus baris duplikat dari sebuah daftar.', status: 'soon' }
      ]
    },
    {
      id: 'datetime',
      name: 'Tanggal & Waktu',
      icon: 'icon-clock',
      tools: [
        { name: 'Date Calculator', desc: 'Hitung selisih atau tambahan antar tanggal.', status: 'soon' },
        { name: 'Time Zone Converter', desc: 'Konversi jam antar zona waktu berbeda.', status: 'soon' },
        { name: 'Countdown Timer', desc: 'Hitung mundur ke tanggal atau momen tertentu.', status: 'soon' },
        { name: 'Pomodoro Timer', desc: 'Timer fokus kerja dengan siklus istirahat.', status: 'soon' }
      ]
    },
    {
      id: 'math',
      name: 'Matematika',
      icon: 'icon-math',
      tools: [
        { name: 'Prime Number Generator', desc: 'Hasilkan daftar bilangan prima dengan cepat.', status: 'soon' },
        { name: 'Kalkulator Listrik (V/I/R)', desc: 'Hitung tegangan, arus, dan resistansi.', status: 'soon' },
        { name: 'Kalkulator Persen', desc: 'Hitung persentase, kenaikan, dan potongan.', status: 'soon' },
        { name: 'Unit Converter', desc: 'Konversi satuan panjang, berat, dan lainnya.', status: 'soon' }
      ]
    },
    {
      id: 'data',
      name: 'Data',
      icon: 'icon-data',
      tools: [
        { name: 'JSON Formatter & Validator', desc: 'Bereskan dan validasi struktur JSON.', status: 'soon' },
        { name: 'CSV Tools', desc: 'Lihat, sunting, dan konversi berkas CSV.', status: 'soon' },
        { name: 'XML Tools', desc: 'Format dan validasi dokumen XML.', status: 'soon' },
        { name: 'Base64 Encoder/Decoder', desc: 'Encode dan decode teks atau berkas Base64.', status: 'soon' },
        { name: 'QR & Barcode Generator', desc: 'Buat kode QR dan barcode dari teks.', status: 'soon' }
      ]
    },
    {
      id: 'ai',
      name: 'AI',
      icon: 'icon-ai',
      tools: [
        { name: 'Ambil teks dari gambar', desc: 'Baca teks dari gambar scan atau PDF hasil pindai.', status: 'available', href: '/ocr/' },
        { name: 'Ringkas Teks', desc: 'Ringkas dokumen panjang jadi poin utama.', status: 'soon' },
        { name: 'Ubah/Redesign Gambar', desc: 'Ubah gaya visual gambar dengan bantuan AI.', status: 'soon' },
        { name: 'Transkripsi Audio', desc: 'Ubah rekaman suara menjadi teks.', status: 'soon' }
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

  // Referensi diambil sekali: renderTools() mengosongkan #tools-grid di setiap
  // render (termasuk tiap ketikan pencarian), jadi node iklan tidak boleh
  // dibuat ulang, cukup dipindah masuk/keluar grid dengan node yang sama.
  var adMid = document.querySelector('.ad-slot[data-ad-slot="tengah"]');

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
      if (adMid) adMid.hidden = true;
      return;
    }
    els.grid.hidden = false;
    if (els.empty) els.empty.hidden = true;

    // Slot iklan tengah disisipkan setelah grup ke-4, atau setelah grup
    // terakhir kalau hasil filter kurang dari 4 grup (minimal 2 grup).
    var adInsertAfter = groups.length > 4 ? 3 : groups.length - 1;

    var fragAll = document.createDocumentFragment();
    groups.forEach(function (group, groupIndex) {
      var groupNode = els.tplGroup.content.firstElementChild.cloneNode(true);
      var titleEl = groupNode.querySelector('.tool-group__title');
      var countEl = groupNode.querySelector('.tool-group__count');
      var listEl = groupNode.querySelector('.tool-group__list');
      var noteEl = groupNode.querySelector('.tool-group__note');

      if (titleEl) titleEl.textContent = group.category.name;
      if (countEl) countEl.textContent = '(' + group.tools.length + ')';
      if (noteEl) {
        var hasAvailable = group.tools.some(function (t) { return t.status === 'available'; });
        if (!hasAvailable) {
          noteEl.textContent = 'Belum ada alat di kategori ini yang bisa dipakai.';
          noteEl.hidden = false;
        } else {
          noteEl.hidden = true;
        }
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

        // Alat yang punya tautan halaman atau panel interaktif: kartu bisa diklik + tombol "Buka alat"
        // (tombol = jalur keyboard; klik area kartu = kenyamanan tambahan).
        if (tool.href && bodyNode) {
          cardNode.classList.add('tool-card--actionable');

          var openLink = document.createElement('a');
          openLink.className = 'tool-card__open';
          openLink.href = tool.href;
          openLink.setAttribute('aria-label', 'Buka alat ' + tool.name);
          openLink.textContent = 'Buka alat';
          openLink.addEventListener('click', function (event) {
            event.stopPropagation();
          });
          bodyNode.appendChild(openLink);

          cardNode.addEventListener('click', function () {
            window.location.href = tool.href;
          });
        } else if (tool.action && bodyNode) {
          cardNode.classList.add('tool-card--actionable');
          cardNode.dataset.toolAction = tool.action;

          var openBtn = document.createElement('button');
          openBtn.type = 'button';
          openBtn.className = 'tool-card__open';
          openBtn.setAttribute('aria-expanded', 'false');
          openBtn.setAttribute('aria-controls', tool.action + '-panel');
          openBtn.dataset.toolAction = tool.action;
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
      // Selalu masukkan node iklan yang sama ke dalam grid pada posisi ini,
      // termasuk saat hasil filter menyisakan sedikit grup. Menyisipkan (bukan
      // melepas) node membuat `hidden` di bawah tetap berarti: iklan cuma
      // disembunyikan, elemennya tidak hilang dari halaman.
      if (adMid && groupIndex === adInsertAfter) fragAll.appendChild(adMid);
    });
    els.grid.appendChild(fragAll);
    if (adMid) adMid.hidden = groups.length < 2;
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

  // --- Offset toolbar sticky --------------------------------------------
  // Dipakai lewat --sticky-offset di CSS supaya panel alat dan judul grup
  // kategori tidak tertutup navbar + toolbar sticky saat halaman digulir.
  function updateStickyOffset() {
    var navbar = document.querySelector('.navbar');
    var toolbar = document.querySelector('.toolbar');
    var height = (navbar ? navbar.offsetHeight : 0) + (toolbar ? toolbar.offsetHeight : 0);
    // Batas atas dibuat longgar: di layar sempit toolbar bisa setinggi 200px
    // lebih, dan pada zoom 200% angkanya bertambah lagi.
    height = Math.max(80, Math.min(420, height));
    document.documentElement.style.setProperty('--sticky-offset', height + 'px');
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
  updateStickyOffset();

  var resizeTimer = null;
  window.addEventListener('resize', function () {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(updateStickyOffset, 150);
  });
})();

/* =========================================================================
   Panel alat: Gabung PDF
   Alat ini benar-benar diproses di server (bukan di browser): berkas dikirim
   lewat unggahan ke layanan penggabung, diproses di memori server, lalu
   hasilnya diunduh. Karena itu tidak ada klaim "diproses di perangkat" di sini.

   Skrip sengaja terpisah dari daftar alat di atas supaya keduanya tidak
   saling bergantung (daftar alat tetap jalan walau panel tidak ada).
   ========================================================================= */
(function () {
  'use strict';

  var panel = document.getElementById('pdf-merge-panel');
  if (!panel) return;

  var el = {
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

  // Aturan bawaan: dipakai sampai batas dari server diketahui, atau bila
  // layanan belum tersambung.
  var FALLBACK_LIMITS = { max_files: 10, max_total_mb: 25, max_total_bytes: 26214400, max_pages: 200 };

  // Alamat dasar layanan penggabung. Kosong berarti sama asal (path
  // /api/... lewat gateway). Bisa diarahkan ke domain lain lewat
  // <meta name="omnitools-server-base">.
  var serverBase = '';
  var metaBase = document.querySelector('meta[name="omnitools-server-base"]');
  if (metaBase && metaBase.content) serverBase = metaBase.content.trim().replace(/\/+$/, '');

  var state = {
    files: [],
    limits: FALLBACK_LIMITS,
    limitsLoaded: false,
    busy: false,
    downloadUrl: null,
    lastFocus: null
  };
  var focusSpec = null; // { index, act }: fokus yang dipulihkan setelah daftar digambar ulang

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
      target.focus({ preventScroll: true });
    } else if (el.submit) {
      el.submit.focus({ preventScroll: true });
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
    if (tooMany) notes.push('Batas ' + maxFiles() + ' berkas tercapai, sisanya diabaikan.');
    if (tooBig) notes.push('Total melebihi batas ' + state.limits.max_total_mb + ' MB, berkas itu tidak dimasukkan.');
    if (!notes.length) notes.push('Tidak ada berkas yang bisa ditambahkan.');

    var problem = rejected.length > 0 || tooMany || tooBig;
    setStatus(notes.join(' '), (added === 0 && problem) ? 'error' : '');
  }

  // --- Aturan dari server ------------------------------------------------
  function describeLimits(online) {
    if (!el.limits) return;
    var text = 'Maks ' + maxFiles() + ' berkas, total ' + state.limits.max_total_mb
      + ' MB, ' + maxPages() + ' halaman';
    el.limits.textContent = text + (online ? ', aturan dari server' : ', aturan bawaan');
  }

  function loadLimits() {
    if (state.limitsLoaded) return;
    fetch(serverBase + '/api/pdf/merge/limits', { headers: { Accept: 'application/json' } })
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

  function readServerError(response) {
    return response.text().then(function (text) {
      var message = '';
      try {
        var parsed = JSON.parse(text);
        if (parsed && parsed.error && parsed.error.message) message = parsed.error.message;
      } catch (err) { /* balasan bukan JSON (mis. halaman HTML 404 dari nginx) */ }
      if (!message) {
        message = 'Server membalas HTTP ' + response.status + '.';
        if (response.status === 404) {
          message += ' Penggabung PDF belum tersambung ke layanan di server. Coba lagi nanti.';
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

    fetch(serverBase + '/api/pdf/merge', { method: 'POST', body: form })
      .then(function (response) {
        if (!response.ok) return readServerError(response);
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
  function syncTriggers(expanded) {
    var triggers = document.querySelectorAll('.tool-card__open[data-tool-action="pdf-merge"]');
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
      renderList();
      if (!state.files.length) {
        setStatus('Pilih berkas PDF, atur urutannya (urutan = urutan halaman), lalu tekan "Gabung PDF".');
      }
      syncTriggers(true);
      panel.focus({ preventScroll: true });
    }
    panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    revokeDownload();
    if (el.download) el.download.hidden = true;
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
    }
  }

  // --- Pemasangan event --------------------------------------------------
  if (el.close) el.close.addEventListener('click', close);
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

  // Daftarkan panel supaya kartu "PDF Merger" bisa membuka/menutupnya.
  window.OmniToolsPanels = window.OmniToolsPanels || {};
  window.OmniToolsPanels['pdf-merge'] = toggle;
})();

/* =========================================================================
   Bilah persetujuan cookie (Consent Mode v2): satu baris tetap di bawah layar
   (bukan jendela terpisah, tanpa lapisan gelap di belakang). Pilihan pengunjung
   disimpan di localStorage lalu diteruskan ke Google sebagai sinyal consent —
   gtag() sudah tersedia dari skrip di <head>.
   ========================================================================= */
(function () {
  'use strict';

  var bar = document.getElementById('cookiebar');
  if (!bar) return;

  var okBtn = document.getElementById('cookiebar-ok');
  var tolakBtn = document.getElementById('cookiebar-tolak');
  var STORAGE_KEY = 'bahzi-cookie-consent';

  // localStorage bisa melempar error di mode privat / protokol file://.
  function bacaPilihan() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      if (v === 'granted' || v === 'denied') return v;
      // Nilai dari versi lama ("Mengerti") tetap dihormati sebagai persetujuan.
      if (localStorage.getItem('bahzi-cookie-ok') === '1') return 'granted';
      return null;
    } catch (err) {
      return null;
    }
  }

  function simpanPilihan(pilihan) {
    try { localStorage.setItem(STORAGE_KEY, pilihan); } catch (err) { /* mode privat: abaikan */ }
  }

  // Teruskan pilihan ke Google (GA4 + AdSense memakai sinyal yang sama).
  // Bawaannya sudah 'denied' dari <head>, jadi update ini bisa dipanggil
  // kapan saja — termasuk saat halaman dibuka oleh pengunjung yang sudah memilih.
  function kirimConsent(pilihan) {
    if (typeof window.gtag !== 'function') return;
    var izin = pilihan === 'granted' ? 'granted' : 'denied';
    window.gtag('consent', 'update', {
      ad_storage: izin,
      ad_user_data: izin,
      ad_personalization: izin,
      analytics_storage: izin
    });
  }

  var pilihanTersimpan = bacaPilihan();
  if (pilihanTersimpan) {
    // Pengunjung yang sudah memilih tidak melihat bilah lagi, tapi sinyalnya
    // tetap dikirim ulang setiap halaman dibuka.
    kirimConsent(pilihanTersimpan);
  } else {
    bar.hidden = false;
    document.body.classList.add('has-cookiebar');
    reserveCookiebarSpace();
  }

  // Tinggi bilah berbeda antara ponsel (teks membungkus) dan desktop, jadi ruang
  // yang disisihkan di bawah halaman diukur dari tinggi bilah yang sebenarnya.
  // Tanpa ini, bilah bisa menutupi bagian akhir konten di layar sempit.
  function reserveCookiebarSpace() {
    if (bar.hidden) {
      document.body.style.paddingBottom = '';
      return;
    }
    document.body.style.paddingBottom = (bar.offsetHeight + 12) + 'px';
  }

  // Kalau pengunjung menolak, hapus cookie pengukuran yang mungkin sudah ada dari
  // kunjungan sebelumnya. Consent Mode sendiri tidak menghapus cookie lama, jadi
  // ini yang membuat penolakan benar-benar berlaku. (Cookie HttpOnly tidak bisa
  // dihapus dari JavaScript — itu memang di luar jangkauan halaman.)
  function hapusCookiePengukuran() {
    var nama = ['_ga', '_gid', '_gat', '__gads', '__gpi'];
    var host = location.hostname;
    // Domain efektif: contoh "bahzi.fun" dan ".bahzi.fun" untuk subdomain.
    var domain = host.split('.').slice(-2).join('.');
    var daftar = document.cookie.split(';').map(function (c) { return c.trim().split('=')[0]; });
    daftar.forEach(function (n) {
      if (n !== '_ga' && !/^_ga_/.test(n) && nama.indexOf(n) === -1) return;
      [host, '.' + host, domain, '.' + domain].forEach(function (d) {
        document.cookie = n + '=; Max-Age=0; path=/; domain=' + d;
        document.cookie = n + '=; Max-Age=0; path=/';
      });
    });
  }

  function tutup(pilihan) {
    simpanPilihan(pilihan);
    if (pilihan === 'denied') hapusCookiePengukuran();
    kirimConsent(pilihan);
    bar.hidden = true;
    document.body.classList.remove('has-cookiebar');
    document.body.style.paddingBottom = '';
  }

  if (okBtn) okBtn.addEventListener('click', function () { tutup('granted'); });
  if (tolakBtn) tolakBtn.addEventListener('click', function () { tutup('denied'); });

  // Halaman privasi menyediakan tautan "Ubah pilihan cookie" yang menghapus
  // simpanan ini; setelah dihapus, bilah muncul lagi saat kembali ke beranda.
  window.OmniToolsCookie = { kirimConsent: kirimConsent, bacaPilihan: bacaPilihan };

  // Tinggi bilah ikut berubah saat layar diputar atau jendela diubah ukurannya.
  window.addEventListener('resize', reserveCookiebarSpace);
})();
