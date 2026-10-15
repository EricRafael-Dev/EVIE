/**
 * JARVIS Brave Extension - Content Script
 * Extração de dados da página, DOM, artigos, tabelas, metadados e automação.
 */

(() => {
  // Evita reinicialização duplicada
  if (window.__JARVIS_CONTENT_SCRIPT_LOADED__) return;
  window.__JARVIS_CONTENT_SCRIPT_LOADED__ = true;

  // Utilitário para verificar se elemento está visível
  function isVisible(elem) {
    if (!elem) return false;
    const style = window.getComputedStyle(elem);
    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      style.opacity !== "0" &&
      elem.offsetWidth > 0 &&
      elem.offsetHeight > 0
    );
  }

  // Extração inteligente de metadados
  function getMetadata() {
    const getMeta = (names) => {
      for (const name of names) {
        const el =
          document.querySelector(`meta[name="${name}" i]`) ||
          document.querySelector(`meta[property="${name}" i]`);
        if (el && el.getAttribute("content")) {
          return el.getAttribute("content").trim();
        }
      }
      return "";
    };

    const canonicalEl = document.querySelector('link[rel="canonical"]');
    const faviconEl =
      document.querySelector('link[rel="icon"]') ||
      document.querySelector('link[rel="shortcut icon"]');

    const bodyText = document.body ? document.body.innerText : "";
    const words = bodyText.trim().split(/\s+/).filter(Boolean).length;

    return {
      title: document.title || "",
      url: window.location.href,
      domain: window.location.hostname,
      canonical: canonicalEl ? canonicalEl.href : window.location.href,
      favicon: faviconEl ? faviconEl.href : `${window.location.origin}/favicon.ico`,
      description: getMeta(["description", "og:description", "twitter:description"]),
      keywords: getMeta(["keywords"]),
      author: getMeta(["author", "article:author", "twitter:creator"]),
      image: getMeta(["og:image", "twitter:image"]),
      type: getMeta(["og:type"]) || "website",
      language: document.documentElement.lang || "unknown",
      charset: document.characterSet || "UTF-8",
      wordCount: words,
      readingTimeMinutes: Math.max(1, Math.ceil(words / 200)),
      timestamp: new Date().toISOString()
    };
  }

  // Conversão de nó DOM para Markdown Limpo
  function domToMarkdown(rootNode) {
    const clone = rootNode.cloneNode(true);

    // Remove elementos inúteis, anúncios, scripts e estilo
    const unwantedSelectors = [
      "script", "style", "noscript", "iframe", "svg", "canvas",
      "nav", "header", "footer", "aside",
      ".ad", ".ads", ".advertisement", ".banner", ".social-share",
      ".cookie-banner", ".newsletter-popup", ".comments", "#comments",
      "[role='alert']", "[aria-hidden='true']"
    ];
    clone.querySelectorAll(unwantedSelectors.join(",")).forEach((el) => el.remove());

    function processNode(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        return node.textContent.replace(/\s+/g, " ");
      }
      if (node.nodeType !== Node.ELEMENT_NODE) {
        return "";
      }

      const tag = node.tagName.toLowerCase();
      let childrenText = Array.from(node.childNodes)
        .map(processNode)
        .join("");

      switch (tag) {
        case "h1":
          return `\n\n# ${childrenText.trim()}\n\n`;
        case "h2":
          return `\n\n## ${childrenText.trim()}\n\n`;
        case "h3":
          return `\n\n### ${childrenText.trim()}\n\n`;
        case "h4":
          return `\n\n#### ${childrenText.trim()}\n\n`;
        case "h5":
        case "h6":
          return `\n\n##### ${childrenText.trim()}\n\n`;
        case "p":
          return childrenText.trim() ? `\n\n${childrenText.trim()}\n\n` : "";
        case "blockquote":
          return `\n\n> ${childrenText.trim().replace(/\n/g, "\n> ")}\n\n`;
        case "code":
          if (node.parentElement && node.parentElement.tagName.toLowerCase() === "pre") {
            return childrenText;
          }
          return ` \`${childrenText.trim()}\` `;
        case "pre":
          return `\n\n\`\`\`\n${node.textContent.trim()}\n\`\`\`\n\n`;
        case "ul":
          return `\n\n${childrenText}\n\n`;
        case "ol":
          return `\n\n${childrenText}\n\n`;
        case "li":
          return `\n- ${childrenText.trim()}`;
        case "strong":
        case "b":
          return childrenText.trim() ? ` **${childrenText.trim()}** ` : "";
        case "em":
        case "i":
          return childrenText.trim() ? ` *${childrenText.trim()}* ` : "";
        case "a":
          const href = node.getAttribute("href");
          if (href && childrenText.trim()) {
            return ` [${childrenText.trim()}](${href}) `;
          }
          return childrenText;
        case "hr":
          return "\n\n---\n\n";
        case "br":
          return "\n";
        case "table":
          return `\n\n${tableToMarkdown(node)}\n\n`;
        default:
          return childrenText;
      }
    }

    let markdown = processNode(clone);
    // Limpar quebras de linha excessivas
    markdown = markdown
      .replace(/\n{3,}/g, "\n\n")
      .trim();

    return markdown;
  }

  // Tabela para Markdown
  function tableToMarkdown(tableEl) {
    const rows = Array.from(tableEl.querySelectorAll("tr"));
    if (rows.length === 0) return "";

    const parsedRows = rows.map((tr) => {
      const cells = Array.from(tr.querySelectorAll("th, td"));
      return cells.map((cell) => cell.innerText.replace(/[\n\r|]/g, " ").trim());
    });

    if (parsedRows.length === 0 || parsedRows[0].length === 0) return "";

    const colCount = Math.max(...parsedRows.map((r) => r.length));
    const lines = [];

    // Header
    const headerRow = parsedRows[0];
    while (headerRow.length < colCount) headerRow.push("");
    lines.push(`| ${headerRow.join(" | ")} |`);
    lines.push(`| ${headerRow.map(() => "---").join(" | ")} |`);

    // Data rows
    for (let i = 1; i < parsedRows.length; i++) {
      const row = parsedRows[i];
      while (row.length < colCount) row.push("");
      lines.push(`| ${row.join(" | ")} |`);
    }

    return lines.join("\n");
  }

  // Extração inteligente de Artigo / Conteúdo Principal
  function extractArticle() {
    // Tenta encontrar container de artigo comum
    const candidates = [
      "article",
      "main",
      "[role='main']",
      ".post-content",
      ".article-content",
      ".entry-content",
      "#content",
      ".content"
    ];

    let mainContainer = null;
    for (const sel of candidates) {
      const el = document.querySelector(sel);
      if (el && el.innerText.trim().length > 200) {
        mainContainer = el;
        break;
      }
    }

    if (!mainContainer) {
      mainContainer = document.body;
    }

    const markdown = domToMarkdown(mainContainer);
    const metadata = getMetadata();

    return {
      metadata,
      markdown,
      plainText: mainContainer.innerText.trim()
    };
  }

  // Extração de todos os Links da página
  function extractLinks() {
    const anchors = Array.from(document.querySelectorAll("a[href]"));
    const seen = new Set();
    const links = [];

    for (const a of anchors) {
      try {
        const href = new URL(a.href, window.location.href).href;
        if (href.startsWith("javascript:") || href.startsWith("mailto:") || href.startsWith("tel:")) {
          continue;
        }
        const text = (a.innerText || a.getAttribute("title") || a.getAttribute("aria-label") || "").trim();
        const key = `${href}:::${text}`;
        if (!seen.has(key)) {
          seen.add(key);
          links.push({
            text: text || "[Sem Texto]",
            href,
            isExternal: new URL(href).hostname !== window.location.hostname
          });
        }
      } catch (e) {}
    }

    return links;
  }

  // Extração de todas as tabelas em formato JSON estruturado
  function extractTables() {
    const tables = Array.from(document.querySelectorAll("table"));
    return tables.map((t, idx) => {
      const rows = Array.from(t.querySelectorAll("tr"));
      const headers = Array.from(t.querySelectorAll("th")).map((th) => th.innerText.trim());
      const data = rows.map((tr) => {
        return Array.from(tr.querySelectorAll("td")).map((td) => td.innerText.trim());
      }).filter((row) => row.length > 0);

      return {
        tableIndex: idx + 1,
        headers: headers.length > 0 ? headers : null,
        rows: data,
        markdown: tableToMarkdown(t)
      };
    });
  }

  // Extração de Formulários
  function extractForms() {
    const forms = Array.from(document.querySelectorAll("form"));
    return forms.map((f, idx) => {
      const inputs = Array.from(f.querySelectorAll("input, select, textarea"));
      return {
        formIndex: idx + 1,
        id: f.id || null,
        name: f.name || null,
        action: f.action || null,
        method: f.method || "GET",
        fields: inputs.map((input) => ({
          tag: input.tagName.toLowerCase(),
          type: input.type || null,
          name: input.name || null,
          id: input.id || null,
          placeholder: input.placeholder || null,
          value: input.value || null
        }))
      };
    });
  }

  // Extração de Mídias
  function extractMedia() {
    const images = Array.from(document.querySelectorAll("img[src]"))
      .map((img) => ({
        type: "image",
        src: img.src,
        alt: img.alt || "",
        width: img.naturalWidth || img.width,
        height: img.naturalHeight || img.height
      }))
      .filter((img) => img.src.startsWith("http"));

    const videos = Array.from(document.querySelectorAll("video, iframe[src*='youtube'], iframe[src*='vimeo']"))
      .map((v) => ({
        type: "video",
        src: v.src || v.currentSrc || ""
      }));

    return { images, videos };
  }

  // Ações de automação no DOM
  function executeDomAction(payload) {
    const { action, selector, value } = payload;

    if (action === "click") {
      const el = document.querySelector(selector);
      if (!el) throw new Error(`Elemento não encontrado: ${selector}`);
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.click();
      return { success: true, message: `Clicado em: ${selector}` };
    }

    if (action === "fill") {
      const el = document.querySelector(selector);
      if (!el) throw new Error(`Elemento não encontrado: ${selector}`);
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus();
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return { success: true, message: `Preenchido campo: ${selector}` };
    }

    if (action === "scroll") {
      if (value === "bottom") {
        window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
      } else if (value === "top") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else if (typeof value === "number") {
        window.scrollBy({ top: value, behavior: "smooth" });
      }
      return { success: true, message: `Rolagem executada: ${value}` };
    }

    throw new Error(`Ação desconhecida: ${action}`);
  }

  // Ouvinte de mensagens do Popup ou Background Script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    try {
      const { type, payload } = request;

      switch (type) {
        case "PING":
          sendResponse({ status: "OK", url: window.location.href });
          break;

        case "GET_METADATA":
          sendResponse({ ok: true, data: getMetadata() });
          break;

        case "GET_ARTICLE":
          sendResponse({ ok: true, data: extractArticle() });
          break;

        case "GET_LINKS":
          sendResponse({ ok: true, data: extractLinks() });
          break;

        case "GET_TABLES":
          sendResponse({ ok: true, data: extractTables() });
          break;

        case "GET_FORMS":
          sendResponse({ ok: true, data: extractForms() });
          break;

        case "GET_MEDIA":
          sendResponse({ ok: true, data: extractMedia() });
          break;

        case "GET_SELECTION":
          sendResponse({
            ok: true,
            data: {
              selection: window.getSelection().toString().trim(),
              url: window.location.href,
              title: document.title
            }
          });
          break;

        case "DOM_ACTION":
          const res = executeDomAction(payload || {});
          sendResponse({ ok: true, data: res });
          break;

        default:
          sendResponse({ ok: false, error: `Tipo desconhecido: ${type}` });
      }
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }

    return true; // Suporte assíncrono
  });
})();
