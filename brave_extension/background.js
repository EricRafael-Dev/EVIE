/**
 * JARVIS Brave Extension - Background Service Worker
 * Gerenciamento centralizado de guias, capturas, extração e ponte WebSocket com o JARVIS (Python).
 */

const DEFAULT_WS_URL = "ws://127.0.0.1:8765";

let ws = null;
let wsUrl = DEFAULT_WS_URL;
let wsConnected = false;
let reconnectTimer = null;
let heartbeatTimer = null;
let reconnectDelay = 3000;
const MAX_RECONNECT_DELAY = 15000;

// Inicializa configurações salvas
chrome.storage.local.get(["wsUrl"], (res) => {
  if (res.wsUrl) {
    wsUrl = res.wsUrl;
  }
  connectWebSocket();
});

// Alarm para manter o Service Worker ativo (Evita suspensão pelo Chrome/Brave)
chrome.alarms.create("keepAlive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "keepAlive") {
    // A chamada a qualquer API do Chrome reinicia o temporizador de suspensão do Service Worker
    chrome.storage.local.get(["wsUrl"], () => {
      ensureWebSocketConnected();
    });
  }
});

function ensureWebSocketConnected() {
  if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
    connectWebSocket();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. CONEXÃO WEBSOCKET COM O JARVIS (PYTHON / LOCALHOST)
// ─────────────────────────────────────────────────────────────────────────────

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log(`[JARVIS Background] Conectado ao servidor JARVIS: ${wsUrl}`);
      wsConnected = true;
      reconnectDelay = 3000; // Reset backoff
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }

      // Envia identificação do navegador
      ws.send(JSON.stringify({
        type: "client_hello",
        client: "brave_extension",
        timestamp: Date.now()
      }));

      startHeartbeat();
    };

    ws.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);

        // Responde a pings do servidor
        if (message.type === "ping") {
          ws.send(JSON.stringify({ type: "pong", timestamp: Date.now() }));
          return;
        }

        const response = await handleRemoteCommand(message);
        if (response && message.id) {
          response.id = message.id;
          ws.send(JSON.stringify(response));
        }
      } catch (err) {
        console.error("[JARVIS Background] Erro ao processar mensagem WS:", err);
      }
    };

    ws.onclose = () => {
      wsConnected = false;
      stopHeartbeat();
      scheduleReconnect();
    };

    ws.onerror = () => {
      wsConnected = false;
      stopHeartbeat();
    };
  } catch (e) {
    wsConnected = false;
    stopHeartbeat();
    scheduleReconnect();
  }
}

function startHeartbeat() {
  stopHeartbeat();
  // Envia ping a cada 15 segundos para manter a conexão e o Service Worker ativos
  heartbeatTimer = setInterval(async () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping", timestamp: Date.now() }));
      // Chamada rápida à API do Chrome para resetar o idle timer do Manifest V3
      await chrome.storage.local.get(["wsUrl"]);
    } else {
      stopHeartbeat();
    }
  }, 15000);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (!wsConnected) {
      connectWebSocket();
      // Backoff progressivo para não sobrecarregar
      reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT_DELAY);
    }
  }, reconnectDelay);
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. EXECUTOR DE COMANDOS REMOTOS (VINDO DO JARVIS VIA WEBSOCKET)
// ─────────────────────────────────────────────────────────────────────────────

async function handleRemoteCommand(cmd) {
  const { action, payload = {} } = cmd;

  switch (action) {
    case "ping":
      return { ok: true, result: "pong", timestamp: Date.now() };

    case "list_tabs": {
      const tabs = await listAllTabs();
      return { ok: true, result: tabs };
    }

    case "switch_tab": {
      const { tabId, query } = payload;
      let targetId = tabId;
      if (!targetId && query) {
        const found = await findTabByQuery(query);
        if (found) targetId = found.id;
      }
      if (!targetId) return { ok: false, error: "Aba não encontrada" };
      await switchTab(targetId);
      return { ok: true, message: `Aba ${targetId} ativada com sucesso` };
    }

    case "close_tabs": {
      const { tabIds, domain, query, duplicatesOnly } = payload;
      let closedCount = 0;

      if (duplicatesOnly) {
        closedCount = await closeDuplicateTabs();
      } else if (domain) {
        closedCount = await closeTabsByDomain(domain);
      } else if (query) {
        closedCount = await closeTabsByQuery(query);
      } else if (Array.isArray(tabIds) && tabIds.length > 0) {
        await chrome.tabs.remove(tabIds);
        closedCount = tabIds.length;
      }

      return { ok: true, closedCount };
    }

    case "create_tab": {
      const { url = "about:blank", active = true } = payload;
      const newTab = await chrome.tabs.create({ url, active });
      return { ok: true, tab: sanitizeTab(newTab) };
    }

    case "reload_tab": {
      const { tabId } = payload;
      const targetId = tabId || (await getActiveTab())?.id;
      if (targetId) {
        await chrome.tabs.reload(targetId);
        return { ok: true, message: `Aba ${targetId} recarregada` };
      }
      return { ok: false, error: "Nenhuma aba ativa para recarregar" };
    }

    case "extract_content": {
      const { tabId, mode = "article" } = payload;
      const targetId = tabId || (await getActiveTab())?.id;
      if (!targetId) return { ok: false, error: "Nenhuma aba ativa para extração" };
      const data = await extractContentFromTab(targetId, mode);
      return { ok: true, data };
    }

    case "capture_screenshot": {
      const { tabId } = payload;
      const targetId = tabId || (await getActiveTab())?.id;
      if (targetId) {
        await switchTab(targetId);
      }
      const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: "png" });
      return { ok: true, screenshotBase64: dataUrl };
    }

    case "execute_action": {
      const { tabId, domAction, selector, value } = payload;
      const targetId = tabId || (await getActiveTab())?.id;
      if (!targetId) return { ok: false, error: "Nenhuma aba ativa" };
      const res = await sendTabMessage(targetId, {
        type: "DOM_ACTION",
        payload: { action: domAction, selector, value }
      });
      return res;
    }

    case "control_media": {
      const { mediaAction = "toggle" } = payload;
      return await executeMediaControl(mediaAction);
    }

    default:
      return { ok: false, error: `Comando desconhecido: ${action}` };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 2.1 CONTROLE DE MÍDIA EM SEGUNDO PLANO (YOUTUBE / SPOTIFY / ETC.)
// ─────────────────────────────────────────────────────────────────────────────

async function executeMediaControl(mediaAction) {
  try {
    // Busca todas as abas do YouTube e todas as abas emitindo áudio
    const ytTabs = await chrome.tabs.query({ url: ["*://*.youtube.com/*", "*://music.youtube.com/*"] });
    const audibleTabs = await chrome.tabs.query({ audible: true });

    // Junta candidatos sem duplicatas
    const candidateMap = new Map();
    // Prioridade 1: Abas emitindo som (audible: true)
    for (const t of audibleTabs) candidateMap.set(t.id, t);
    // Prioridade 2: Abas do YouTube
    for (const t of ytTabs) {
      if (!candidateMap.has(t.id)) candidateMap.set(t.id, t);
    }

    const candidateTabs = Array.from(candidateMap.values());
    if (candidateTabs.length === 0) {
      // Fallback: aba ativa no momento
      const active = await getActiveTab();
      if (active) candidateTabs.push(active);
    }

    if (candidateTabs.length === 0) {
      return { ok: false, error: "Nenhuma aba do YouTube ou com mídia foi encontrada." };
    }

    // Se a ação for "pause":
    // Procura especificamente qual aba está reproduzindo vídeo (não pausada) e pausa!
    if (mediaAction === "pause") {
      let pausedTabTitle = "";
      let foundPlaying = false;

      // Primeiro testa nas abas emitindo som (audible), depois nas demais
      const sortedTabs = [...candidateTabs].sort((a, b) => (b.audible ? 1 : 0) - (a.audible ? 1 : 0));

      for (const tab of sortedTabs) {
        try {
          const [injection] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const video = document.querySelector("video.video-stream") || document.querySelector("video") || document.querySelector("audio");
              if (video && !video.paused) {
                video.pause();
                return { success: true, title: document.title };
              }
              // Se não achou video ou já está pausado, tenta o botão de pause se estiver ativo
              const playBtn = document.querySelector(".ytp-play-button");
              if (playBtn && playBtn.getAttribute("data-title-no-tooltip") === "Pause") {
                playBtn.click();
                return { success: true, title: document.title };
              }
              return { success: false };
            }
          });

          if (injection?.result?.success) {
            foundPlaying = true;
            pausedTabTitle = injection.result.title || tab.title;
            // Se encontrou a aba que estava tocando e pausou, encerra a busca
            break;
          }
        } catch (e) {
          // Ignora abas protegidas ou sem permissão
        }
      }

      if (foundPlaying) {
        return { ok: true, state: "paused", title: pausedTabTitle };
      }

      // Se nenhum vídeo estava explicitamente tocando, força pausa na primeira aba candidata
      const firstTab = sortedTabs[0];
      await chrome.scripting.executeScript({
        target: { tabId: firstTab.id },
        func: () => {
          const video = document.querySelector("video") || document.querySelector("audio");
          if (video) video.pause();
        }
      });
      return { ok: true, state: "paused", title: firstTab.title };
    }

    // Se a ação for "play" ou "resume":
    // Dá play na aba mais recentemente ativa ou na aba ativa
    let targetTab = candidateTabs.find((t) => t.active) || candidateTabs[0];

    const injectionResults = await chrome.scripting.executeScript({
      target: { tabId: targetTab.id },
      func: (act) => {
        const video = document.querySelector("video.video-stream") || document.querySelector("video") || document.querySelector("audio");
        if (!video) {
          const playBtn = document.querySelector(".ytp-play-button");
          if (playBtn) {
            playBtn.click();
            return { state: "toggled", title: document.title };
          }
          return { error: "Nenhum elemento de vídeo encontrado." };
        }

        if (act === "play" || act === "resume") {
          video.play();
          return { state: "playing", title: document.title };
        } else if (act === "next") {
          const nextBtn = document.querySelector(".ytp-next-button");
          if (nextBtn) nextBtn.click();
          return { state: "next", title: document.title };
        } else if (act === "mute") {
          video.muted = !video.muted;
          return { state: video.muted ? "muted" : "unmuted", title: document.title };
        } else {
          // Toggle
          if (video.paused) {
            video.play();
            return { state: "playing", title: document.title };
          } else {
            video.pause();
            return { state: "paused", title: document.title };
          }
        }
      },
      args: [mediaAction]
    });

    const result = injectionResults?.[0]?.result;
    if (result && result.error) {
      return { ok: false, error: result.error };
    }

    return {
      ok: true,
      state: result?.state || mediaAction,
      title: result?.title || targetTab.title
    };
  } catch (err) {
    return { ok: false, error: `Falha no controle de mídia: ${err.message}` };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. FUNÇÕES UTILITÁRIAS DE CONTROLE DE GUIAS
// ─────────────────────────────────────────────────────────────────────────────

function sanitizeTab(t) {
  return {
    id: t.id,
    windowId: t.windowId,
    title: t.title || "Nova Guia",
    url: t.url || "",
    active: t.active,
    pinned: t.pinned,
    muted: t.mutedInfo ? t.mutedInfo.muted : false,
    favIconUrl: t.favIconUrl || ""
  };
}

async function listAllTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.map(sanitizeTab);
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab || null;
}

async function switchTab(tabId) {
  const tab = await chrome.tabs.get(tabId);
  if (!tab) throw new Error("Aba não encontrada");
  await chrome.tabs.update(tabId, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
  return true;
}

async function findTabByQuery(query) {
  const q = query.toLowerCase().trim();
  const tabs = await chrome.tabs.query({});
  return tabs.find(
    (t) =>
      (t.title && t.title.toLowerCase().includes(q)) ||
      (t.url && t.url.toLowerCase().includes(q))
  );
}

async function closeDuplicateTabs() {
  const tabs = await chrome.tabs.query({});
  const seenUrls = new Map();
  const toClose = [];

  for (const tab of tabs) {
    if (!tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("brave://")) {
      continue;
    }
    const cleanUrl = tab.url.split("#")[0]; // ignora âncoras
    if (seenUrls.has(cleanUrl)) {
      toClose.push(tab.id);
    } else {
      seenUrls.set(cleanUrl, tab.id);
    }
  }

  if (toClose.length > 0) {
    await chrome.tabs.remove(toClose);
  }
  return toClose.length;
}

async function closeTabsByDomain(domain) {
  const cleanDomain = domain.toLowerCase().replace(/^(https?:\/\/)?(www\.)?/, "").split("/")[0];
  const tabs = await chrome.tabs.query({});
  const toClose = [];

  for (const tab of tabs) {
    if (tab.url) {
      try {
        const u = new URL(tab.url);
        if (u.hostname.toLowerCase().includes(cleanDomain)) {
          toClose.push(tab.id);
        }
      } catch (e) {}
    }
  }

  if (toClose.length > 0) {
    await chrome.tabs.remove(toClose);
  }
  return toClose.length;
}

async function closeTabsByQuery(query) {
  const q = query.toLowerCase().trim();
  const tabs = await chrome.tabs.query({});
  const toClose = [];

  for (const tab of tabs) {
    if (
      (tab.title && tab.title.toLowerCase().includes(q)) ||
      (tab.url && tab.url.toLowerCase().includes(q))
    ) {
      toClose.push(tab.id);
    }
  }

  if (toClose.length > 0) {
    await chrome.tabs.remove(toClose);
  }
  return toClose.length;
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. EXTRAÇÃO DE CONTEÚDO E COMUNICAÇÃO COM CONTENT SCRIPT
// ─────────────────────────────────────────────────────────────────────────────

async function ensureContentScriptInjected(tabId) {
  try {
    const res = await chrome.tabs.sendMessage(tabId, { type: "PING" });
    if (res && res.status === "OK") return true;
  } catch (e) {
    // Content script não injetado ainda, vamos injetar
  }

  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"]
    });
    return true;
  } catch (err) {
    console.warn(`[JARVIS Background] Não foi possível injetar content script na aba ${tabId}:`, err);
    return false;
  }
}

async function sendTabMessage(tabId, message) {
  await ensureContentScriptInjected(tabId);
  return await chrome.tabs.sendMessage(tabId, message);
}

async function extractContentFromTab(tabId, mode) {
  let msgType = "GET_ARTICLE";
  if (mode === "metadata") msgType = "GET_METADATA";
  else if (mode === "links") msgType = "GET_LINKS";
  else if (mode === "tables") msgType = "GET_TABLES";
  else if (mode === "forms") msgType = "GET_FORMS";
  else if (mode === "media") msgType = "GET_MEDIA";
  else if (mode === "selection") msgType = "GET_SELECTION";

  const res = await sendTabMessage(tabId, { type: msgType });
  if (res && res.ok) {
    return res.data;
  }
  throw new Error(res?.error || "Falha na extração de conteúdo da aba.");
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. OUvinte DE MENSAGENS LOCAIS (POPUP UI)
// ─────────────────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const { action, payload = {} } = request;

  (async () => {
    try {
      switch (action) {
        case "POPUP_GET_STATE": {
          ensureWebSocketConnected();
          const tabs = await listAllTabs();
          const active = await getActiveTab();
          sendResponse({
            ok: true,
            tabs,
            activeTabId: active?.id,
            wsConnected,
            wsUrl
          });
          break;
        }

        case "POPUP_SWITCH_TAB": {
          await switchTab(payload.tabId);
          sendResponse({ ok: true });
          break;
        }

        case "POPUP_CLOSE_TAB": {
          await chrome.tabs.remove(payload.tabId);
          sendResponse({ ok: true });
          break;
        }

        case "POPUP_CLOSE_DUPLICATES": {
          const count = await closeDuplicateTabs();
          sendResponse({ ok: true, closedCount: count });
          break;
        }

        case "POPUP_CLOSE_DOMAIN": {
          const count = await closeTabsByDomain(payload.domain);
          sendResponse({ ok: true, closedCount: count });
          break;
        }

        case "POPUP_CREATE_TAB": {
          const tab = await chrome.tabs.create({ url: payload.url || "about:blank" });
          sendResponse({ ok: true, tab: sanitizeTab(tab) });
          break;
        }

        case "POPUP_TOGGLE_PIN": {
          const tab = await chrome.tabs.get(payload.tabId);
          await chrome.tabs.update(payload.tabId, { pinned: !tab.pinned });
          sendResponse({ ok: true, pinned: !tab.pinned });
          break;
        }

        case "POPUP_TOGGLE_MUTE": {
          const tab = await chrome.tabs.get(payload.tabId);
          const isMuted = tab.mutedInfo ? tab.mutedInfo.muted : false;
          await chrome.tabs.update(payload.tabId, { muted: !isMuted });
          sendResponse({ ok: true, muted: !isMuted });
          break;
        }

        case "POPUP_EXTRACT": {
          const targetId = payload.tabId || (await getActiveTab())?.id;
          if (!targetId) throw new Error("Nenhuma aba ativa");
          const data = await extractContentFromTab(targetId, payload.mode || "article");
          sendResponse({ ok: true, data });
          break;
        }

        case "POPUP_CLIP_TO_SECOND_BRAIN": {
          const targetId = payload?.tabId || (await getActiveTab())?.id;
          if (!targetId) throw new Error("Nenhuma aba ativa");
          const data = await extractContentFromTab(targetId, "article");
          const activeTab = await getActiveTab();
          const clipPayload = {
            url: activeTab?.url || data?.metadata?.url || "",
            title: activeTab?.title || data?.metadata?.title || "Artigo Web",
            content: data?.markdown || data?.text || "",
          };

          // 1. Tenta enviar via rota REST do dashboard
          let sent = false;
          try {
            const res = await fetch("http://127.0.0.1:8000/api/clipper/ingest", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(clipPayload),
            });
            if (res.ok) sent = true;
          } catch (_e) {
            // Fallback via WS
          }

          // 2. Se falhar ou WS ativo, notifica pelo WebSocket
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: "command",
              text: `Indexe este artigo no meu segundo cérebro: ${clipPayload.title} (${clipPayload.url})`,
              clip: clipPayload
            }));
            sent = true;
          }

          sendResponse({ ok: sent, title: clipPayload.title });
          break;
        }

        case "POPUP_SCREENSHOT": {
          const targetId = payload.tabId || (await getActiveTab())?.id;
          if (targetId) await switchTab(targetId);
          const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: "png" });
          sendResponse({ ok: true, dataUrl });
          break;
        }

        case "POPUP_MEDIA_CONTROL": {
          const res = await executeMediaControl(payload.mediaAction || "toggle");
          sendResponse(res);
          break;
        }

        case "POPUP_SET_WS_URL": {
          wsUrl = payload.url || DEFAULT_WS_URL;
          await chrome.storage.local.set({ wsUrl });
          if (ws) {
            ws.close();
          }
          connectWebSocket();
          sendResponse({ ok: true, wsUrl });
          break;
        }

        default:
          sendResponse({ ok: false, error: `Ação não reconhecida: ${action}` });
      }
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
  })();

  return true; // Comunicação assíncrona
});
