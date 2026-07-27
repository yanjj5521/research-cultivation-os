(() => {
  const menu = document.getElementById('menuButton');
  menu?.addEventListener('click', () => document.body.classList.toggle('sidebar-open'));
  document.querySelector('.main-shell')?.addEventListener('click', event => {
    if (window.innerWidth <= 820 && document.body.classList.contains('sidebar-open') && !event.target.closest('#menuButton')) {
      document.body.classList.remove('sidebar-open');
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

  setTimeout(() => document.querySelectorAll('.flash').forEach(el => el.remove()), 4200);
})();
