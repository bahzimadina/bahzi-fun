/* app.js — OmniTools (demo) : data alat + render + pencarian + filter + counter.
   Satu-satunya sumber data untuk section "Roadmap Alat" adalah CATEGORIES di bawah. */
(function () {
  'use strict';

  if ('IntersectionObserver' in window) { document.documentElement.classList.add('js-reveal'); }

  // --- Data status ------------------------------------------------------
  var STATUS = {
    live: { label: 'Live (demo)', className: 'badge--live' },
    soon: { label: 'Segera', className: 'badge--soon' },
    planned: { label: 'Rencana', className: 'badge--planned' }
  };

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
        { name: 'PDF Merger', desc: 'Gabungkan beberapa PDF jadi satu berkas.', status: 'live' },
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
    var options = [
      { id: 'all', label: 'Semua status' },
      { id: 'live', label: STATUS.live.label },
      { id: 'soon', label: STATUS.soon.label },
      { id: 'planned', label: STATUS.planned.label }
    ];
    var frag = document.createDocumentFragment();
    options.forEach(function (opt, i) {
      frag.appendChild(makeChip(opt.id, opt.label, i === 0, 'status'));
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

        if (useEl) useEl.setAttribute('href', '#' + group.category.icon);
        if (titleNode) titleNode.textContent = tool.name;
        if (descNode) descNode.textContent = tool.desc;
        if (statusNode) {
          var info = STATUS[tool.status];
          statusNode.textContent = info.label;
          statusNode.className = 'badge ' + info.className + ' tool-card__status';
        }
        if (listEl) listEl.appendChild(cardNode);
      });

      fragAll.appendChild(groupNode);
    });
    els.grid.appendChild(fragAll);
  }

  function updateCounts(items) {
    if (!els.counts) return;
    var counts = { live: 0, soon: 0, planned: 0 };
    items.forEach(function (item) { counts[item.tool.status]++; });
    var total = items.length;
    els.counts.textContent =
      'Total: ' + total + ' · Live: ' + counts.live + ' · Segera: ' + counts.soon + ' · Rencana: ' + counts.planned;
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
