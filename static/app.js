(() => {
  const menu = document.getElementById('menuButton');
  const scrim = document.getElementById('sidebarScrim');
  const closeMenu = () => document.body.classList.remove('sidebar-open');
  menu?.addEventListener('click', () => document.body.classList.toggle('sidebar-open'));
  scrim?.addEventListener('click', closeMenu);
  document.querySelectorAll('[data-open-menu]').forEach(button => {
    button.addEventListener('click', () => document.body.classList.add('sidebar-open'));
  });
  document.querySelector('.main-shell')?.addEventListener('click', event => {
    const drawerMode = window.innerWidth <= 820 || document.body.classList.contains('landing-mode');
    if (drawerMode && document.body.classList.contains('sidebar-open') && !event.target.closest('#menuButton') && !event.target.closest('[data-open-menu]')) {
      closeMenu();
    }
  });

  const input = document.getElementById('fileInput');
  const zone = document.getElementById('dropzone');
  const list = document.getElementById('fileList');
  const renderFiles = () => {
    if (!input || !list) return;
    list.innerHTML = '';
    [...input.files].forEach(file => {
      const span = document.createElement('span');
      span.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
      list.appendChild(span);
    });
  };
  input?.addEventListener('change', renderFiles);
  if (zone && input) {
    ['dragenter', 'dragover'].forEach(type => zone.addEventListener(type, event => {
      event.preventDefault(); zone.classList.add('dragover');
    }));
    ['dragleave', 'drop'].forEach(type => zone.addEventListener(type, event => {
      event.preventDefault(); zone.classList.remove('dragover');
    }));
    zone.addEventListener('drop', event => {
      const transfer = new DataTransfer();
      [...event.dataTransfer.files].forEach(file => transfer.items.add(file));
      input.files = transfer.files;
      renderFiles();
    });
  }

  const folderInput = document.getElementById('foundationFolderInput');
  const pathsInput = document.getElementById('foundationRelativePaths');
  const preview = document.getElementById('foundationFolderPreview');
  if (folderInput && pathsInput && preview) {
    folderInput.addEventListener('change', () => {
      const files = [...folderInput.files];
      const paths = files.map(file => file.webkitRelativePath || file.name);
      pathsInput.value = JSON.stringify(paths);
      const total = files.reduce((sum, file) => sum + file.size, 0);
      preview.innerHTML = files.length
        ? `<strong>${paths[0]?.split('/')[0] || '文件夹'}</strong><br><span>${files.length} 个文件 · ${(total / 1024 / 1024).toFixed(2)} MB</span><br><small>${paths.slice(0, 4).join('<br>')}${paths.length > 4 ? '<br>…' : ''}</small>`
        : '';
    });
  }

  const copyButton = document.getElementById('copyPromptButton');
  const promptText = document.getElementById('promptText');
  const copyFeedback = document.getElementById('copyFeedback');
  copyButton?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(promptText?.value || '');
      if (copyFeedback) copyFeedback.textContent = '已复制，直接粘贴到 ChatGPT 即可。';
    } catch {
      promptText?.select();
      document.execCommand('copy');
      if (copyFeedback) copyFeedback.textContent = '已复制。';
    }
  });

  const retreatTime = document.getElementById('retreatTime');
  if (retreatTime) {
    const storageKey = 'research-cultivation-retreat-v1';
    const minutesInput = document.getElementById('retreatMinutes');
    const focusInput = document.getElementById('retreatFocus');
    const focusLabel = document.getElementById('retreatFocusLabel');
    const stateLabel = document.getElementById('retreatState');
    const progress = document.getElementById('retreatProgress');
    const startButton = document.getElementById('retreatStart');
    const pauseButton = document.getElementById('retreatPause');
    const resetButton = document.getElementById('retreatReset');
    const finishLinks = document.getElementById('retreatFinishLinks');
    const presets = [...document.querySelectorAll('[data-minutes]')];
    const circumference = 2 * Math.PI * 108;
    let ticker = null;
    let timer = {
      durationMs: 25 * 60 * 1000,
      remainingMs: 25 * 60 * 1000,
      endAt: 0,
      running: false,
      paused: false,
      completed: false,
      focus: '',
    };

    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (saved && typeof saved === 'object') timer = {...timer, ...saved};
    } catch {
      // The timer still works in memory when browser storage is unavailable.
    }
    const retreatParams = new URLSearchParams(window.location.search);
    if (!timer.running && !timer.paused && !timer.completed) {
      const requestedMinutes = Number.parseInt(retreatParams.get('minutes') || '', 10);
      const requestedFocus = (retreatParams.get('focus') || '').trim().slice(0, 80);
      if (Number.isFinite(requestedMinutes) && requestedMinutes > 0) {
        timer.durationMs = Math.max(1, Math.min(480, requestedMinutes)) * 60 * 1000;
        timer.remainingMs = timer.durationMs;
      }
      if (requestedFocus) timer.focus = requestedFocus;
    }

    const persist = () => {
      try { localStorage.setItem(storageKey, JSON.stringify(timer)); } catch {}
    };
    const clampMinutes = value => Math.max(1, Math.min(480, Number.parseInt(value, 10) || 25));
    const remainingNow = () => timer.running ? Math.max(0, timer.endAt - Date.now()) : Math.max(0, timer.remainingMs);
    const formatTime = milliseconds => {
      const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      return hours
        ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
        : `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    };
    const stopTicker = () => {
      if (ticker) window.clearInterval(ticker);
      ticker = null;
    };
    const markPreset = () => {
      const minutes = clampMinutes(minutesInput.value);
      presets.forEach(button => button.classList.toggle('active', Number(button.dataset.minutes) === minutes));
    };
    const complete = () => {
      stopTicker();
      timer.running = false;
      timer.paused = false;
      timer.completed = true;
      timer.remainingMs = 0;
      timer.endAt = 0;
      persist();
    };
    const render = () => {
      const remaining = remainingNow();
      if (timer.running && remaining <= 0) complete();
      const current = remainingNow();
      retreatTime.textContent = formatTime(current);
      focusLabel.textContent = timer.focus || '请选择闭关所修';
      stateLabel.textContent = timer.completed ? '功行圆满' : timer.running ? '闭关中' : timer.paused ? '暂歇' : '尚未入定';
      startButton.textContent = timer.paused ? '继续闭关' : timer.running ? '闭关中' : '开始闭关';
      startButton.disabled = timer.running;
      pauseButton.disabled = !timer.running;
      finishLinks.hidden = !timer.completed;
      const ratio = timer.durationMs > 0 ? Math.min(1, current / timer.durationMs) : 0;
      progress.style.strokeDashoffset = String(circumference * (1 - ratio));
      document.title = timer.running ? `${formatTime(current)} · 入定闭关` : '入定闭关';
      persist();
    };
    const startTicker = () => {
      stopTicker();
      ticker = window.setInterval(render, 500);
    };

    focusInput.value = timer.focus || '';
    minutesInput.value = String(Math.max(1, Math.round(timer.durationMs / 60000)));
    if (timer.running && timer.endAt <= Date.now()) complete();
    if (timer.running) startTicker();
    markPreset();
    render();

    presets.forEach(button => button.addEventListener('click', () => {
      if (timer.running) return;
      minutesInput.value = button.dataset.minutes;
      timer.durationMs = clampMinutes(button.dataset.minutes) * 60 * 1000;
      timer.remainingMs = timer.durationMs;
      timer.paused = false;
      timer.completed = false;
      markPreset();
      render();
    }));
    minutesInput.addEventListener('change', () => {
      if (timer.running) return;
      const minutes = clampMinutes(minutesInput.value);
      minutesInput.value = String(minutes);
      timer.durationMs = minutes * 60 * 1000;
      timer.remainingMs = timer.durationMs;
      timer.paused = false;
      timer.completed = false;
      markPreset();
      render();
    });
    focusInput.addEventListener('input', () => {
      timer.focus = focusInput.value.trim().slice(0, 80);
      render();
    });
    startButton.addEventListener('click', () => {
      timer.focus = focusInput.value.trim().slice(0, 80);
      if (!timer.paused) {
        const minutes = clampMinutes(minutesInput.value);
        timer.durationMs = minutes * 60 * 1000;
        timer.remainingMs = timer.durationMs;
      }
      timer.endAt = Date.now() + timer.remainingMs;
      timer.running = true;
      timer.paused = false;
      timer.completed = false;
      startTicker();
      render();
    });
    pauseButton.addEventListener('click', () => {
      timer.remainingMs = remainingNow();
      timer.running = false;
      timer.paused = true;
      timer.endAt = 0;
      stopTicker();
      render();
    });
    resetButton.addEventListener('click', () => {
      stopTicker();
      const minutes = clampMinutes(minutesInput.value);
      timer = {
        durationMs: minutes * 60 * 1000,
        remainingMs: minutes * 60 * 1000,
        endAt: 0,
        running: false,
        paused: false,
        completed: false,
        focus: focusInput.value.trim().slice(0, 80),
      };
      render();
    });
    document.addEventListener('visibilitychange', render);
  }

  setTimeout(() => document.querySelectorAll('.flash').forEach(el => el.remove()), 4200);
})();
