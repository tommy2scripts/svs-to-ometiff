(function() {
  'use strict';
  const $ = id => document.getElementById(id);
  const dropzone = $('dropzone'), fileInput = $('fileInput'), inputPath = $('inputPath');
  const outputPath = $('outputPath'), convertBtn = $('convertBtn');
  const settingsToggle = $('settingsToggle'), settingsBody = $('settingsBody'), settingsArrow = $('settingsArrow');
  const progressPanel = $('progressPanel'), progressContent = $('progressContent');
  const idlePlaceholder = $('idlePlaceholder'), progressRingFill = $('progressRingFill');
  const progressPct = $('progressPct'), progressMsg = $('progressMsg');
  const completionBox = $('completionBox'), errorBox = $('errorBox');
  const openFolderBtn = $('openFolderBtn'), logConsole = $('logConsole');
  const slideInfo = $('slideInfo'), slideInfoGrid = $('slideInfoGrid');
  const convertibleBadge = $('convertibleBadge');
  const CIRC = 2 * Math.PI * 52; // stroke-dasharray
  let currentRequestId = null, inspectTimer = null, inspectAbort = null;

  function escapeHTML(str) {
    return String(str).replace(/[&<>"']/g, function (m) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
  }

  // Batch specific UI
  let mode = 'single';
  const tabSingle = $('tabSingle'), tabBatch = $('tabBatch');
  const contentSingle = $('contentSingle'), contentBatch = $('contentBatch');
  const batchInputs = $('batchInputs'), batchOutputDir = $('batchOutputDir'), batchQueue = $('batchQueue');

  tabSingle.addEventListener('click', () => {
    mode = 'single';
    tabSingle.classList.add('active'); tabBatch.classList.remove('active');
    contentSingle.classList.add('active'); contentBatch.classList.remove('active');
    updateOutput();
  });
  tabBatch.addEventListener('click', () => {
    mode = 'batch';
    tabBatch.classList.add('active'); tabSingle.classList.remove('active');
    contentBatch.classList.add('active'); contentSingle.classList.remove('active');
    updateBatchStatus();
  });

  function updateBatchStatus() {
    const lines = batchInputs.value.split('\n').map(l => l.trim()).filter(l => l);
    convertBtn.disabled = lines.length === 0;
  }
  batchInputs.addEventListener('input', updateBatchStatus);

  function deriveOutput(p) {
    if (!p) return '';
    const dot = p.lastIndexOf('.');
    const base = (dot > p.lastIndexOf('/') && dot > p.lastIndexOf('\\')) ? p.substring(0, dot) : p;
    return base + '.ome.tiff';
  }

  function updateOutput() {
    if (mode === 'batch') return;
    const v = inputPath.value.trim();
    if (v) outputPath.value = deriveOutput(v);
    else outputPath.value = '';
    convertBtn.disabled = !v;
  }

  // Inspect slide on path change (debounced)
  function scheduleInspect() {
    clearTimeout(inspectTimer);
    const v = inputPath.value.trim();
    if (!v) { slideInfo.classList.remove('visible'); return; }
    inspectTimer = setTimeout(() => fetchInspect(v), 400);
  }

  function fetchInspect(path) {
    if (inspectAbort) inspectAbort.abort();
    inspectAbort = new AbortController();
    fetch('/inspect?path=' + encodeURIComponent(path), { signal: inspectAbort.signal })
      .then(r => r.json())
      .then(data => {
        if (data.error) { slideInfo.classList.remove('visible'); return; }
        const mag = data.magnification;
        const magStr = mag != null ? (mag === Math.floor(mag) ? mag + 'X' : mag + 'X') : '—';
        const items = [
          ['Dimensions', data.width + ' × ' + data.height],
          ['MPP', data.mpp != null ? data.mpp + ' µm/px' : '—'],
          ['Magnification', magStr],
          ['Compression', String(data.compression)],
          ['Tile Size', data.src_tile_width + ' × ' + data.src_tile_height],
          ['Tile Count', String(data.tile_count)],
        ];
        slideInfoGrid.innerHTML = items.map(([l,v]) =>
          '<div class="slide-info-item"><span class="label">'+escapeHTML(l)+'</span><span class="value">'+escapeHTML(v)+'</span></div>'
        ).join('');
        if (data.convertible) {
          convertibleBadge.className = 'badge badge-ok';
          convertibleBadge.textContent = '✓ Convertible';
        } else {
          convertibleBadge.className = 'badge badge-warn';
          convertibleBadge.textContent = '✗ Not supported';
        }
        slideInfo.classList.add('visible');
      })
      .catch(err => {
        if (err.name !== 'AbortError') slideInfo.classList.remove('visible');
      });
  }

  inputPath.addEventListener('input', () => { updateOutput(); scheduleInspect(); });
  inputPath.addEventListener('focus', () => $('pathHint').classList.add('hidden'));

  // Browse buttons using Native Dialog endpoints
  $('browseBtn').addEventListener('click', e => { 
    e.preventDefault(); 
    const btn = $('browseBtn');
    const prevText = btn.textContent;
    btn.textContent = '...'; btn.disabled = true;
    fetch('/browse_file').then(r => r.json()).then(d => {
       btn.textContent = prevText; btn.disabled = false;
       if (d.path) {
           inputPath.value = d.path; updateOutput();
           scheduleInspect(); $('pathHint').classList.add('hidden');
       }
    }).catch(err => {
       btn.textContent = prevText; btn.disabled = false;
       fileInput.click(); // Fallback to browser standard
    });
  });

  const batchBrowseBtn = $('batchBrowseBtn');
  if (batchBrowseBtn) {
    batchBrowseBtn.addEventListener('click', e => {
      e.preventDefault();
      const prevText = batchBrowseBtn.textContent;
      batchBrowseBtn.textContent = '...'; batchBrowseBtn.disabled = true;
      fetch('/browse_files').then(r => r.json()).then(d => {
         batchBrowseBtn.textContent = prevText; batchBrowseBtn.disabled = false;
         if (d.paths && d.paths.length > 0) {
             const existing = batchInputs.value.trim();
             const toAdd = d.paths.join('\n');
             batchInputs.value = existing ? existing + '\n' + toAdd : toAdd;
             updateBatchStatus();
         }
      }).catch(err => {
         batchBrowseBtn.textContent = prevText; batchBrowseBtn.disabled = false;
      });
    });
  }
  fileInput.addEventListener('change', () => {
    const f = fileInput.files[0];
    if (f) { inputPath.value = f.name; updateOutput(); scheduleInspect(); $('pathHint').classList.remove('hidden'); }
  });

  // Drag & drop
  dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
  dropzone.addEventListener('dragleave', e => { e.preventDefault(); dropzone.classList.remove('drag-over'); });
  dropzone.addEventListener('drop', e => {
    e.preventDefault(); dropzone.classList.remove('drag-over');
    const f = e.dataTransfer.files;
    if (f && f.length) { inputPath.value = f[0].name; updateOutput(); scheduleInspect(); $('pathHint').classList.remove('hidden'); }
  });
  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });

  // Settings toggle
  settingsToggle.addEventListener('click', () => {
    settingsBody.classList.toggle('open');
    settingsArrow.classList.toggle('open');
  });
  settingsToggle.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      settingsToggle.click();
    }
  });

  // Progress ring helper
  function setProgress(pct) {
    const clamped = Math.min(Math.max(pct, 0), 100);
    const offset = CIRC - (clamped / 100) * CIRC;
    progressRingFill.style.strokeDashoffset = offset;
    progressPct.textContent = Math.round(clamped) + '%';
  }

  function addLog(msg) {
    // Remove "Waiting" placeholder on first real message
    if (logConsole.children.length === 1 && logConsole.children[0].textContent === 'Waiting for conversion...') {
      logConsole.innerHTML = '';
    }
    const el = document.createElement('div');
    el.className = 'log-line fresh';
    el.textContent = '> ' + msg;
    logConsole.appendChild(el);
    logConsole.scrollTop = logConsole.scrollHeight;
    setTimeout(() => el.classList.remove('fresh'), 1500);
  }

  // Convert
  convertBtn.addEventListener('click', () => {
    let payload = {}, url = '/convert';

    if (mode === 'single') {
      const inp = inputPath.value.trim();
      if (!inp) return;
      payload = {
        input_path: inp,
        output_path: outputPath.value.trim() || undefined,
      };
    } else {
      const lines = batchInputs.value.split('\n').map(l => l.trim()).filter(l => l);
      if (lines.length === 0) return;
      payload = {
        inputs: lines,
        output_dir: batchOutputDir.value.trim() || undefined,
      };
      url = '/convert/batch';

      // Render initial queue
      batchQueue.innerHTML = lines.map((l, i) => `
        <div class="batch-item" id="batch-item-${i}">
          <span class="name" title="${escapeHTML(l)}">${escapeHTML(l.split('/').pop().split('\\').pop())}</span>
          <span class="status status-pending">Pending</span>
        </div>
      `).join('');
      batchQueue.classList.remove('hidden');
    }

    Object.assign(payload, {
      tile_size: parseInt($('tileSize').value, 10),
      compression: $('compression').value,
      num_levels: parseInt($('numLevels').value, 10),
      downsample_factor: parseInt($('downsampleFactor').value, 10),
      edge_mode: $('edgeMode').value,
    });

    convertBtn.disabled = true; convertBtn.textContent = 'Converting…';
    completionBox.classList.remove('visible'); errorBox.classList.remove('visible');
    idlePlaceholder.classList.add('hidden'); progressContent.classList.remove('hidden');
    if (mode === 'single') batchQueue.classList.add('hidden');
    setProgress(0); progressMsg.textContent = 'Starting conversion…';
    logConsole.innerHTML = '<div class="log-line" style="color:var(--text-muted);">Waiting for conversion...</div>';

    fetch(url, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) })
      .then(r => { if (!r.ok) return r.json().then(d => { throw new Error(d.error || 'Request failed'); }); return r.json(); })
      .then(data => { currentRequestId = data.request_id; listenProgress(data.request_id); })
      .catch(err => {
        progressContent.classList.add('hidden'); idlePlaceholder.classList.remove('hidden');
        errorBox.textContent = err.message; errorBox.classList.add('visible');
        convertBtn.textContent = 'Convert'; convertBtn.disabled = false;
      });
  });

  function listenProgress(rid) {
    const es = new EventSource('/progress/' + encodeURIComponent(rid));
    es.addEventListener('progress', e => {
      try {
        const d = JSON.parse(e.data);
        if (d.message) { progressMsg.textContent = d.message; addLog(d.message); }
        
        // Progress parsing
        if (typeof d.overall_percent === 'number') {
           setProgress(d.overall_percent);
        } else if (typeof d.percent === 'number') {
           setProgress(d.percent);
        }

        // Batch Queue Updates
        if (typeof d.file_idx === 'number') {
           const bItem = $(`batch-item-${d.file_idx}`);
           if (bItem) {
               const statusSpan = bItem.querySelector('.status');
               if (d.percent === 100) {
                   statusSpan.className = 'status status-done';
                   statusSpan.textContent = 'Done';
               } else {
                   statusSpan.className = 'status status-running';
                   statusSpan.textContent = Math.round(d.percent) + '%';
               }
           }
        }
      } catch(_) {}
    });
    es.addEventListener('complete', () => {
      es.close(); setProgress(100);
      progressContent.classList.add('hidden'); idlePlaceholder.classList.add('hidden');
      completionBox.classList.add('visible');
      addLog('✓ Conversion complete');
      convertBtn.textContent = 'Convert'; convertBtn.disabled = false;
      currentRequestId = null;
    });
    es.addEventListener('error', e => {
      let msg = 'Connection lost or conversion failed';
      try { const d = JSON.parse(e.data); msg = d.error || msg; } catch(_) {}
      es.close();
      progressContent.classList.add('hidden'); idlePlaceholder.classList.add('hidden');
      errorBox.textContent = msg; errorBox.classList.add('visible');
      addLog('✗ Error: ' + msg);
      convertBtn.textContent = 'Convert'; convertBtn.disabled = false;
      currentRequestId = null;
    });
  }

  // Open folder
  openFolderBtn.addEventListener('click', () => {
    let out = '';
    if (mode === 'single') out = outputPath.value.trim();
    else out = batchOutputDir.value.trim() || batchInputs.value.split('\n')[0].trim();
    if (!out) return;
    let dir = out.substring(0, out.lastIndexOf('/')); if (!dir) dir = '.';
    fetch('/open_folder', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({path:dir}) }).catch(()=>{});
  });

  // Enter key
  inputPath.addEventListener('keydown', e => { if (e.key === 'Enter' && !convertBtn.disabled) convertBtn.click(); });
})();
