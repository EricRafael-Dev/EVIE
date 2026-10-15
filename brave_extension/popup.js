/**
 * JARVIS Brave Extension - Popup Controller
 * Gerencia a interface, abas, extração, capturas e comandos rápidos.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Estado local
  let allTabs = [];
  let currentActiveTabId = null;
  let activeTabDomain = "";
  let lastExtractedContent = "";
  let lastExtractedFilename = "extracao.txt";
  let lastScreenshotDataUrl = null;

  // Elementos do DOM
  const wsBadge = document.getElementById("wsBadge");
  const wsStatusText = document.getElementById("wsStatusText");
  const searchInput = document.getElementById("searchInput");
  const clearSearchBtn = document.getElementById("clearSearchBtn");
  const tabsCount = document.getElementById("tabsCount");
  const tabsList = document.getElementById("tabsList");
  const navTabs = document.querySelectorAll(".nav-tab");
  const panels = document.querySelectorAll(".tab-panel");
  const toast = document.getElementById("toast");

  // Botões de Ação em Lote
  const btnNewTab = document.getElementById("btnNewTab");
  const btnCloseDuplicates = document.getElementById("btnCloseDuplicates");
  const btnCloseDomain = document.getElementById("btnCloseDomain");
  const btnToggleMedia = document.getElementById("btnToggleMedia");

  // Painel de Extração
  const extractButtons = document.querySelectorAll(".extract-btn");
  const extractResultArea = document.getElementById("extractResultArea");
  const resultTitle = document.getElementById("resultTitle");
  const resultOutput = document.getElementById("resultOutput");
  const btnCopyResult = document.getElementById("btnCopyResult");
  const btnDownloadResult = document.getElementById("btnDownloadResult");
  const btnClipToSecondBrain = document.getElementById("btnClipToSecondBrain");
  const btnClipActiveTab = document.getElementById("btnClipActiveTab");
  const btnDirectClipSecondBrain = document.getElementById("btnDirectClipSecondBrain");

  // Painel de Captura
  const btnTakeScreenshot = document.getElementById("btnTakeScreenshot");
  const screenshotPreviewArea = document.getElementById("screenshotPreviewArea");
  const screenshotImg = document.getElementById("screenshotImg");
  const btnCopyScreenshot = document.getElementById("btnCopyScreenshot");
  const btnDownloadScreenshot = document.getElementById("btnDownloadScreenshot");

  // Painel de Configurações
  const wsUrlInput = document.getElementById("wsUrlInput");
  const btnSaveWs = document.getElementById("btnSaveWs");
  const activityLogs = document.getElementById("activityLogs");
  const btnClearLogs = document.getElementById("btnClearLogs");

  // ───────────────────────────────────────────────────────────────────────────
  // 1. CARREGAMENTO INICIAL DE ESTADO
  // ───────────────────────────────────────────────────────────────────────────

  function loadState() {
    chrome.runtime.sendMessage({ action: "POPUP_GET_STATE" }, (response) => {
      if (!response || !response.ok) {
        showToast("Erro ao conectar ao serviço da extensão");
        return;
      }

      allTabs = response.tabs || [];
      currentActiveTabId = response.activeTabId;

      // Identifica o domínio da aba ativa atual
      const activeTab = allTabs.find((t) => t.id === currentActiveTabId);
      if (activeTab && activeTab.url) {
        try {
          activeTabDomain = new URL(activeTab.url).hostname;
        } catch (e) {
          activeTabDomain = "";
        }
      }

      // Atualiza badge de WebSocket
      updateWsBadge(response.wsConnected, response.wsUrl);
      if (response.wsUrl) {
        wsUrlInput.value = response.wsUrl;
      }

      renderTabs(allTabs);
    });
  }

  function updateWsBadge(isConnected, url) {
    if (isConnected) {
      wsBadge.className = "status-badge connected";
      wsStatusText.textContent = "JARVIS CONECTADO";
      wsBadge.title = `Conectado ao JARVIS: ${url}`;
    } else {
      wsBadge.className = "status-badge disconnected";
      wsStatusText.textContent = "JARVIS OFFLINE";
      wsBadge.title = `Tentando reconectar em: ${url}`;
    }
  }

  // Atualiza o status em tempo real enquanto o popup estiver aberto
  setInterval(() => {
    chrome.runtime.sendMessage({ action: "POPUP_GET_STATE" }, (res) => {
      if (res && res.ok) {
        updateWsBadge(res.wsConnected, res.wsUrl);
      }
    });
  }, 2500);

  // ───────────────────────────────────────────────────────────────────────────
  // 2. RENDERIZAÇÃO DA LISTA DE GUIAS
  // ───────────────────────────────────────────────────────────────────────────

  function renderTabs(tabsToRender) {
    tabsCount.textContent = tabsToRender.length;
    tabsList.innerHTML = "";

    if (tabsToRender.length === 0) {
      tabsList.innerHTML = `
        <div class="loading-state">
          <span>Nenhuma guia encontrada</span>
        </div>
      `;
      return;
    }

    tabsToRender.forEach((tab) => {
      const isCurrent = tab.id === currentActiveTabId;
      const tabCard = document.createElement("div");
      tabCard.className = `tab-item ${isCurrent ? "active-tab" : ""}`;
      tabCard.dataset.id = tab.id;

      // Favicon com fallback
      const faviconSrc =
        tab.favIconUrl && !tab.favIconUrl.startsWith("chrome://")
          ? tab.favIconUrl
          : "icons/icon16.png";

      let cleanUrl = tab.url;
      try {
        const u = new URL(tab.url);
        cleanUrl = u.hostname + (u.pathname.length > 1 ? u.pathname : "");
      } catch (e) {}

      tabCard.innerHTML = `
        <img class="tab-favicon" src="${faviconSrc}" onerror="this.src='icons/icon16.png'" />
        <div class="tab-info" title="${escapeHtml(tab.title)}\n${escapeHtml(tab.url)}">
          <div class="tab-title">${escapeHtml(tab.title || "Nova Guia")}</div>
          <div class="tab-url">${escapeHtml(cleanUrl)}</div>
        </div>
        <div class="tab-tools">
          <button class="tab-tool-btn pin" title="${tab.pinned ? 'Desafixar' : 'Fixar'}">
            ${tab.pinned ? '📌' : '📍'}
          </button>
          <button class="tab-tool-btn mute" title="${tab.muted ? 'Ativar Som' : 'Silenciar'}">
            ${tab.muted ? '🔇' : '🔊'}
          </button>
          <button class="tab-tool-btn close" title="Fechar Guia">✕</button>
        </div>
      `;

      // Clique no corpo do card -> Alterna para a guia
      tabCard.addEventListener("click", (e) => {
        if (e.target.closest(".tab-tool-btn")) return;
        switchTab(tab.id);
      });

      // Ações dos botões da aba
      tabCard.querySelector(".pin").addEventListener("click", (e) => {
        e.stopPropagation();
        togglePin(tab.id);
      });

      tabCard.querySelector(".mute").addEventListener("click", (e) => {
        e.stopPropagation();
        toggleMute(tab.id);
      });

      tabCard.querySelector(".close").addEventListener("click", (e) => {
        e.stopPropagation();
        closeTab(tab.id);
      });

      tabsList.appendChild(tabCard);
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 3. AÇÕES DE GUIA
  // ───────────────────────────────────────────────────────────────────────────

  function switchTab(tabId) {
    chrome.runtime.sendMessage({ action: "POPUP_SWITCH_TAB", payload: { tabId } }, () => {
      showToast("Guia alternada");
      currentActiveTabId = tabId;
      loadState();
    });
  }

  function closeTab(tabId) {
    chrome.runtime.sendMessage({ action: "POPUP_CLOSE_TAB", payload: { tabId } }, () => {
      allTabs = allTabs.filter((t) => t.id !== tabId);
      renderTabs(allTabs);
      showToast("Guia fechada");
    });
  }

  function togglePin(tabId) {
    chrome.runtime.sendMessage({ action: "POPUP_TOGGLE_PIN", payload: { tabId } }, () => {
      loadState();
    });
  }

  function toggleMute(tabId) {
    chrome.runtime.sendMessage({ action: "POPUP_TOGGLE_MUTE", payload: { tabId } }, () => {
      loadState();
    });
  }

  // Ações em Lote
  btnNewTab.addEventListener("click", () => {
    chrome.runtime.sendMessage({ action: "POPUP_CREATE_TAB", payload: { url: "about:blank" } }, () => {
      loadState();
      showToast("Nova guia criada");
    });
  });

  btnCloseDuplicates.addEventListener("click", () => {
    chrome.runtime.sendMessage({ action: "POPUP_CLOSE_DUPLICATES" }, (res) => {
      const count = res?.closedCount || 0;
      showToast(count > 0 ? `${count} guias duplicadas fechadas!` : "Nenhuma duplicada encontrada");
      loadState();
    });
  });

  btnCloseDomain.addEventListener("click", () => {
    if (!activeTabDomain) {
      showToast("Domínio não identificado");
      return;
    }
    if (confirm(`Fechar todas as guias de: ${activeTabDomain}?`)) {
      chrome.runtime.sendMessage(
        { action: "POPUP_CLOSE_DOMAIN", payload: { domain: activeTabDomain } },
        (res) => {
          showToast(`${res?.closedCount || 0} guias fechadas`);
          loadState();
        }
      );
    }
  });

  if (btnToggleMedia) {
    btnToggleMedia.addEventListener("click", () => {
      chrome.runtime.sendMessage(
        { action: "POPUP_MEDIA_CONTROL", payload: { mediaAction: "toggle" } },
        (res) => {
          if (res && res.ok) {
            const state = res.state === "paused" ? "Vídeo pausado" : "Vídeo em reprodução";
            showToast(`YouTube: ${state}`);
          } else {
            showToast(res?.error || "Nenhum player encontrado");
          }
        }
      );
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 4. PESQUISA & COMANDOS RÁPIDOS
  // ───────────────────────────────────────────────────────────────────────────

  searchInput.addEventListener("input", () => {
    const query = searchInput.value.trim().toLowerCase();
    clearSearchBtn.style.display = query ? "block" : "none";

    // Se for comando rápido não filtra a lista ainda
    if (query.startsWith(":")) return;

    const filtered = allTabs.filter(
      (t) =>
        (t.title && t.title.toLowerCase().includes(query)) ||
        (t.url && t.url.toLowerCase().includes(query))
    );
    renderTabs(filtered);
  });

  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    clearSearchBtn.style.display = "none";
    renderTabs(allTabs);
    searchInput.focus();
  });

  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const val = searchInput.value.trim().toLowerCase();
      if (!val) return;

      // Execução de comandos rápidos
      if (val === ":dup" || val === "fechar duplicadas") {
        btnCloseDuplicates.click();
        searchInput.value = "";
      } else if (val === ":shot" || val === "screenshot" || val === "print") {
        switchPanel("capture");
        btnTakeScreenshot.click();
        searchInput.value = "";
      } else if (val === ":md" || val === ":artigo") {
        switchPanel("extract");
        runExtraction("article");
        searchInput.value = "";
      } else if (val.startsWith("fechar ")) {
        const query = val.replace("fechar ", "").trim();
        const targets = allTabs.filter(
          (t) =>
            (t.title && t.title.toLowerCase().includes(query)) ||
            (t.url && t.url.toLowerCase().includes(query))
        );
        if (targets.length > 0) {
          const ids = targets.map((t) => t.id);
          chrome.tabs.remove(ids, () => {
            showToast(`${ids.length} guias fechadas`);
            searchInput.value = "";
            loadState();
          });
        } else {
          showToast(`Nenhuma guia corresponde a: ${query}`);
        }
      } else {
        // Se houver uma lista filtrada, ativa o primeiro resultado
        const firstCard = tabsList.querySelector(".tab-item");
        if (firstCard) {
          const id = parseInt(firstCard.dataset.id, 10);
          if (id) switchTab(id);
        }
      }
    }
  });

  // ───────────────────────────────────────────────────────────────────────────
  // 5. NAVEGAÇÃO ENTRE PAINÉIS
  // ───────────────────────────────────────────────────────────────────────────

  navTabs.forEach((tabBtn) => {
    tabBtn.addEventListener("click", () => {
      const targetPanel = tabBtn.dataset.tab;
      switchPanel(targetPanel);
    });
  });

  function switchPanel(panelName) {
    navTabs.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === panelName));
    panels.forEach((p) => p.classList.toggle("active", p.id === `panel-${panelName}`));
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 6. PAINEL DE EXTRAÇÃO DE DADOS
  // ───────────────────────────────────────────────────────────────────────────

  extractButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.mode;
      runExtraction(mode);
    });
  });

  function runExtraction(mode) {
    resultOutput.textContent = "Extraindo dados da página...";
    extractResultArea.style.display = "block";

    chrome.runtime.sendMessage(
      { action: "POPUP_EXTRACT", payload: { mode } },
      (response) => {
        if (!response || !response.ok) {
          resultOutput.textContent = `Erro na extração: ${response?.error || "Página indisponível"}`;
          return;
        }

        const data = response.data;
        formatAndDisplayExtraction(mode, data);
      }
    );
  }

  function formatAndDisplayExtraction(mode, data) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");

    if (mode === "article") {
      resultTitle.textContent = `Artigo: ${data.metadata.title}`;
      lastExtractedContent = `# ${data.metadata.title}\nURL: ${data.metadata.url}\n\n${data.markdown}`;
      lastExtractedFilename = `artigo_${timestamp}.md`;
      resultOutput.textContent = lastExtractedContent;
    } else if (mode === "metadata") {
      resultTitle.textContent = "Metadados & SEO";
      lastExtractedContent = JSON.stringify(data, null, 2);
      lastExtractedFilename = `metadados_${timestamp}.json`;
      resultOutput.textContent = lastExtractedContent;
    } else if (mode === "links") {
      resultTitle.textContent = `Links Encontrados (${data.length})`;
      lastExtractedContent = data.map((l) => `${l.text} -> ${l.href}`).join("\n");
      lastExtractedFilename = `links_${timestamp}.txt`;
      resultOutput.textContent = lastExtractedContent;
    } else if (mode === "tables") {
      resultTitle.textContent = `Tabelas Estruturadas (${data.length})`;
      lastExtractedContent = JSON.stringify(data, null, 2);
      lastExtractedFilename = `tabelas_${timestamp}.json`;
      resultOutput.textContent = lastExtractedContent;
    } else if (mode === "forms") {
      resultTitle.textContent = `Formulários (${data.length})`;
      lastExtractedContent = JSON.stringify(data, null, 2);
      lastExtractedFilename = `formularios_${timestamp}.json`;
      resultOutput.textContent = lastExtractedContent;
    } else if (mode === "selection") {
      resultTitle.textContent = "Texto Selecionado";
      lastExtractedContent = data.selection || "[Nenhum texto selecionado na página]";
      lastExtractedFilename = `selecao_${timestamp}.txt`;
      resultOutput.textContent = lastExtractedContent;
    }

    showToast("Extração concluída!");
  }

  btnCopyResult.addEventListener("click", () => {
    if (!lastExtractedContent) return;
    navigator.clipboard.writeText(lastExtractedContent).then(() => {
      showToast("Copiado para a área de transferência!");
    });
  });

  btnDownloadResult.addEventListener("click", () => {
    if (!lastExtractedContent) return;
    const blob = new Blob([lastExtractedContent], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = lastExtractedFilename;
    a.click();
    URL.revokeObjectURL(url);
    showToast(`Arquivo salvo: ${lastExtractedFilename}`);
  });

  function triggerSecondBrainClip() {
    showToast("Enviando para o Second Brain...");
    chrome.runtime.sendMessage({ action: "POPUP_CLIP_TO_SECOND_BRAIN" }, (res) => {
      if (res && res.ok) {
        showToast(`Artigo '${res.title}' indexado no Second Brain!`);
        addLog(`Página clipada para o Second Brain: ${res.title}`, "sys");
      } else {
        showToast(`Erro ao indexar: ${res?.error || "Servidor offline"}`);
      }
    });
  }

  if (btnClipToSecondBrain) {
    btnClipToSecondBrain.addEventListener("click", triggerSecondBrainClip);
  }
  if (btnClipActiveTab) {
    btnClipActiveTab.addEventListener("click", triggerSecondBrainClip);
  }
  if (btnDirectClipSecondBrain) {
    btnDirectClipSecondBrain.addEventListener("click", triggerSecondBrainClip);
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 7. PAINEL DE CAPTURA DE TELA (SCREENSHOT)
  // ───────────────────────────────────────────────────────────────────────────

  btnTakeScreenshot.addEventListener("click", () => {
    btnTakeScreenshot.textContent = "Capturando...";
    chrome.runtime.sendMessage({ action: "POPUP_SCREENSHOT" }, (res) => {
      btnTakeScreenshot.textContent = "📸 Capturar Aba Ativa Agora";
      if (!res || !res.ok) {
        showToast("Falha ao capturar tela");
        return;
      }
      lastScreenshotDataUrl = res.dataUrl;
      screenshotImg.src = res.dataUrl;
      screenshotPreviewArea.style.display = "block";
      showToast("Screenshot capturado com sucesso!");
    });
  });

  btnDownloadScreenshot.addEventListener("click", () => {
    if (!lastScreenshotDataUrl) return;
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const a = document.createElement("a");
    a.href = lastScreenshotDataUrl;
    a.download = `screenshot_${timestamp}.png`;
    a.click();
    showToast("Download da imagem iniciado!");
  });

  btnCopyScreenshot.addEventListener("click", async () => {
    if (!lastScreenshotDataUrl) return;
    try {
      const response = await fetch(lastScreenshotDataUrl);
      const blob = await response.blob();
      await navigator.clipboard.write([
        new ClipboardItem({ [blob.type]: blob })
      ]);
      showToast("Imagem copiada para a área de transferência!");
    } catch (err) {
      showToast("Erro ao copiar imagem");
    }
  });

  // ───────────────────────────────────────────────────────────────────────────
  // 8. PAINEL DE CONFIGURAÇÕES & LOGS (JARVIS LINK)
  // ───────────────────────────────────────────────────────────────────────────

  btnSaveWs.addEventListener("click", () => {
    const url = wsUrlInput.value.trim();
    if (!url) return;
    chrome.runtime.sendMessage({ action: "POPUP_SET_WS_URL", payload: { url } }, (res) => {
      showToast("Configuração salva. Reconectando...");
      addLog(`Servidor configurado para: ${url}`, "sys");
      setTimeout(loadState, 1500);
    });
  });

  btnClearLogs.addEventListener("click", () => {
    activityLogs.innerHTML = "";
  });

  function addLog(text, type = "normal") {
    const entry = document.createElement("div");
    entry.className = `log-entry ${type}`;
    const time = new Date().toLocaleTimeString();
    entry.textContent = `[${time}] ${text}`;
    activityLogs.appendChild(entry);
    activityLogs.scrollTop = activityLogs.scrollHeight;
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 9. FEEDBACK VISUAL (TOAST)
  // ───────────────────────────────────────────────────────────────────────────

  let toastTimer = null;
  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove("show");
    }, 2400);
  }

  function escapeHtml(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Iniciar
  loadState();
});
