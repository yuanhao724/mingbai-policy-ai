(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const numberFormat = new Intl.NumberFormat("zh-CN");

  const state = {
    documents: [],
    currentDocId: null,
    card: null,
    persona: "resident",
    history: [],
    streaming: false,
    checklist: new Map(),
    deleteArmed: false,
    deleteTimer: null,
    statusTimer: null,
    largeText: false,
    speaking: false,
  };

  const ESCAPE_MAP = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ESCAPE_MAP[char]);
  }

  async function api(path, options = {}) {
    const { headers, ...rest } = options;
    const response = await fetch(path, {
      ...rest,
      headers: {
        Accept: "application/json",
        ...(headers || {}),
      },
    });
    if (!response.ok) {
      let detail = `请求失败（${response.status}）`;
      try {
        const payload = await response.json();
        if (payload && payload.detail) {
          detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
        }
      } catch {
        // Keep the status message when the response is not JSON.
      }
      throw new Error(detail);
    }
    return response.json();
  }

  function setStatus(message) {
    const element = $("#upload-status");
    if (!element) return;
    element.textContent = message;
    window.clearTimeout(state.statusTimer);
    state.statusTimer = window.setTimeout(() => {
      element.textContent = "";
    }, 6000);
  }

  function scrollChat() {
    const log = $("#chat-log");
    if (log) log.scrollTop = log.scrollHeight;
  }

  function autoGrow(textarea) {
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 128)}px`;
  }

  function setupNav() {
    const toggle = $(".menu-toggle");
    const menu = $("#mobile-menu");
    if (!toggle || !menu) return;
    let lastFocus = null;

    const openMenu = () => {
      lastFocus = document.activeElement;
      menu.hidden = false;
      window.requestAnimationFrame(() => menu.classList.add("is-open"));
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "关闭菜单");
      document.body.style.overflow = "hidden";
      const firstLink = menu.querySelector("a");
      if (firstLink) firstLink.focus();
    };

    const closeMenu = () => {
      menu.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "打开菜单");
      document.body.style.overflow = "";
      window.setTimeout(() => {
        if (!menu.classList.contains("is-open")) menu.hidden = true;
      }, 450);
      if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
    };

    toggle.addEventListener("click", () => {
      if (toggle.getAttribute("aria-expanded") === "true") closeMenu();
      else openMenu();
    });

    $$("a", menu).forEach((link) => link.addEventListener("click", closeMenu));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !menu.hidden) closeMenu();
    });
    window.addEventListener("resize", () => {
      if (window.innerWidth > 900 && !menu.hidden) closeMenu();
    });
  }

  function setupReveal() {
    const elements = $$(".reveal");
    if (!elements.length) return;
    if (reduceMotion.matches) {
      elements.forEach((element) => element.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    elements.forEach((element, index) => {
      element.style.setProperty("--i", String(index % 4));
      observer.observe(element);
    });
  }

  function setupParallax() {
    const visual = $(".hero-visual");
    if (!visual || reduceMotion.matches || !window.matchMedia("(hover: hover)").matches) return;
    let frame = 0;
    let targetX = 0;
    let targetY = 0;

    const render = () => {
      visual.style.setProperty("--px", targetX.toFixed(3));
      visual.style.setProperty("--py", targetY.toFixed(3));
      frame = 0;
    };

    visual.addEventListener(
      "pointermove",
      (event) => {
        const rect = visual.getBoundingClientRect();
        targetX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        targetY = ((event.clientY - rect.top) / rect.height) * 2 - 1;
        if (!frame) frame = window.requestAnimationFrame(render);
      },
      { passive: true }
    );

    visual.addEventListener("pointerleave", () => {
      targetX = 0;
      targetY = 0;
      if (!frame) frame = window.requestAnimationFrame(render);
    });
  }

  function setupModeSwitch() {
    $$(".mode-switch button").forEach((button) => {
      button.addEventListener("click", () => {
        state.persona = button.dataset.persona || "resident";
        const workbench = $("#workbench");
        if (workbench) workbench.dataset.persona = state.persona;
        $$(".mode-switch button").forEach((item) => {
          const active = item === button;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-pressed", String(active));
        });
        renderWorkerKit();
      });
    });
  }

  function setupAccessibility() {
    const largeTextButton = $("#large-text-toggle");
    const speakButton = $("#speak-toggle");
    const workbench = $("#workbench");

    if (largeTextButton && workbench) {
      largeTextButton.addEventListener("click", () => {
        state.largeText = !state.largeText;
        workbench.classList.toggle("is-large", state.largeText);
        largeTextButton.setAttribute("aria-pressed", String(state.largeText));
      });
    }

    if (speakButton) {
      speakButton.addEventListener("click", () => {
        if (!("speechSynthesis" in window)) {
          setStatus("当前浏览器不支持朗读，可以换用 Edge 或 Chrome。");
          return;
        }
        if (state.speaking) {
          window.speechSynthesis.cancel();
          state.speaking = false;
          speakButton.textContent = "朗读";
          speakButton.setAttribute("aria-pressed", "false");
          return;
        }
        if (!state.card) {
          setStatus("请先选择一份政策。");
          return;
        }
        const text = buildSpeechText(state.card);
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "zh-CN";
        utterance.rate = 0.92;
        utterance.onend = () => {
          state.speaking = false;
          speakButton.textContent = "朗读";
          speakButton.setAttribute("aria-pressed", "false");
        };
        utterance.onerror = () => {
          state.speaking = false;
          speakButton.textContent = "朗读";
          speakButton.setAttribute("aria-pressed", "false");
        };
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
        state.speaking = true;
        speakButton.textContent = "停止朗读";
        speakButton.setAttribute("aria-pressed", "true");
      });
    }
  }

  function buildSpeechText(card) {
    const parts = [`明白卡：${card.title}`, card.one_liner];
    if (card.audience.length) {
      parts.push(`谁能办：${card.audience.map((item) => item.text).join("；")}`);
    }
    if (card.benefit.length) {
      parts.push(`能领什么：${card.benefit.map((item) => item.text).join("；")}`);
    }
    if (card.materials.length) {
      parts.push(`需要带：${card.materials.map((item) => item.text).join("；")}`);
    }
    if (card.steps.length) {
      parts.push(`办理流程：${card.steps.map((item, index) => `${index + 1}，${item.text}`).join("；")}`);
    }
    if (card.deadline.length) {
      parts.push(`时间：${card.deadline.map((item) => item.text).join("；")}`);
    }
    parts.push(card.disclaimer);
    return parts.join("。");
  }

  function setupChat() {
    const form = $("#chat-form");
    const input = $("#question");
    if (!form || !input) return;

    input.addEventListener("input", () => autoGrow(input));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = input.value.trim();
      if (!question || state.streaming) return;
      await sendQuestion(question);
    });
  }

  function setInputEnabled(enabled) {
    const send = $("#send-btn");
    const input = $("#question");
    if (send) send.disabled = !enabled;
    if (input) input.disabled = !enabled && !state.currentDocId;
  }

  function appendUserMessage(text) {
    const log = $("#chat-log");
    if (!log) return;
    const message = document.createElement("div");
    message.className = "msg user";
    const body = document.createElement("div");
    body.className = "msg-body";
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.textContent = text;
    body.appendChild(bubble);
    message.appendChild(body);
    log.appendChild(message);
    scrollChat();
  }

  function createAssistantMessage() {
    const log = $("#chat-log");
    const message = document.createElement("div");
    message.className = "msg assistant";
    message.innerHTML = `
      <span class="msg-avatar" aria-hidden="true">明</span>
      <div class="msg-body">
        <div class="msg-bubble"><span class="typing"><i></i><i></i><i></i></span></div>
        <div class="msg-meta">正在检索政策原文…</div>
        <div class="msg-actions" hidden></div>
      </div>
    `;
    log.appendChild(message);
    scrollChat();
    return {
      element: message,
      bubble: $(".msg-bubble", message),
      meta: $(".msg-meta", message),
      actions: $(".msg-actions", message),
      raw: "",
      sources: [],
      latency: 0,
      done: false,
      renderPending: false,
      notice: null,
    };
  }

  function inlineRich(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[(\d+)\]/g, (_, number) => {
        return `<button type="button" class="cite" data-cite="${number}" aria-label="查看来源 ${number}">[${number}]</button>`;
      });
  }

  function renderRich(text) {
    const escaped = escapeHtml(text);
    const lines = escaped.split("\n");
    const output = [];
    let inList = false;
    for (const line of lines) {
      if (line.startsWith("- ")) {
        if (!inList) {
          output.push('<span class="bullet-list">');
          inList = true;
        }
        output.push(`<span class="bullet">${inlineRich(line.slice(2))}</span>`);
      } else {
        if (inList) {
          output.push("</span>");
          inList = false;
        }
        if (line.trim()) output.push(`<span class="para">${inlineRich(line)}</span>`);
      }
    }
    if (inList) output.push("</span>");
    return output.join("");
  }

  function scheduleRender(context) {
    if (context.renderPending || context.done) return;
    context.renderPending = true;
    window.requestAnimationFrame(() => {
      context.renderPending = false;
      if (context.done) return;
      context.bubble.innerHTML = `${renderRich(context.raw)}<span class="stream-caret" aria-hidden="true"></span>`;
      scrollChat();
    });
  }

  function finalizeAssistant(context) {
    if (context.done) return;
    context.done = true;
    const text = context.raw.trim() || "这次没有生成内容，请再问一次。";
    context.bubble.innerHTML = renderRich(text);
    const seconds = context.latency ? (context.latency / 1000).toFixed(1) : "0.0";
    context.meta.textContent = `用时 ${seconds} 秒 · 引用 ${context.sources.length} 个片段`;
    context.actions.hidden = false;
    context.actions.innerHTML = "";
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.textContent = "复制回答";
    copyButton.addEventListener("click", async () => {
      const ok = await copyText(text);
      setStatus(ok ? "回答已复制。" : "复制失败，请手动选择文本。");
    });
    context.actions.appendChild(copyButton);
    state.history.push({ role: "assistant", content: text });
    state.streaming = false;
    setInputEnabled(true);
    loadStats();
    scrollChat();
  }

  function parseSseChunk(chunk, context) {
    let eventName = "message";
    const dataLines = [];
    for (const rawLine of chunk.split(/\r?\n/)) {
      if (rawLine.startsWith("event:")) eventName = rawLine.slice(6).trim();
      else if (rawLine.startsWith("data:")) dataLines.push(rawLine.slice(5).trim());
    }
    if (!dataLines.length) return;
    let data;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }

    if (eventName === "meta") {
      context.sources = Array.isArray(data.sources) ? data.sources : [];
      const badge = $("#mode-badge");
      if (badge) {
        const online = data.mode === "openai";
        badge.textContent = online ? "在线模型" : "本地模式";
        badge.classList.toggle("openai", online);
      }
      return;
    }

    if (eventName === "token") {
      context.raw += data.text || "";
      scheduleRender(context);
      return;
    }

    if (eventName === "notice") {
      const notice = document.createElement("div");
      notice.className = "notice";
      notice.textContent = data.message || "已切换回答模式。";
      context.element.querySelector(".msg-body").appendChild(notice);
      context.notice = notice;
      return;
    }

    if (eventName === "done") {
      context.latency = Number(data.latency_ms) || 0;
      if (Array.isArray(data.sources)) context.sources = data.sources;
      finalizeAssistant(context);
    }
  }

  async function streamChat(question, history, context) {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doc_id: state.currentDocId,
        question,
        history,
        persona: state.persona,
      }),
    });

    if (!response.ok) {
      let detail = `请求失败（${response.status}）`;
      try {
        const payload = await response.json();
        if (payload && payload.detail) detail = payload.detail;
      } catch {
        // Keep the status message.
      }
      throw new Error(detail);
    }

    if (!response.body) throw new Error("当前浏览器不支持流式回答。");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split(/\r?\n\r?\n/);
      buffer = chunks.pop() || "";
      for (const chunk of chunks) parseSseChunk(chunk, context);
    }
    if (buffer.trim()) parseSseChunk(buffer, context);
    finalizeAssistant(context);
  }

  async function sendQuestion(question) {
    if (!state.currentDocId) {
      setStatus("请先选择或上传一份政策。");
      return;
    }
    if (state.streaming) return;

    const input = $("#question");
    const historyForRequest = state.history.slice();
    appendUserMessage(question);
    state.history.push({ role: "user", content: question });
    state.streaming = true;
    setInputEnabled(false);
    if (input) {
      input.value = "";
      autoGrow(input);
    }

    const context = createAssistantMessage();
    try {
      await streamChat(question, historyForRequest, context);
    } catch (error) {
      context.done = true;
      context.bubble.innerHTML = `<span class="error-text">${escapeHtml(error.message || "回答失败，请稍后重试。")}</span>`;
      context.meta.textContent = "请求失败";
      state.streaming = false;
      setInputEnabled(true);
      setStatus(error.message || "回答失败，请稍后重试。");
    }
  }

  function citeButton(number) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cite";
    button.dataset.cite = String(number);
    button.textContent = `[${number}]`;
    button.setAttribute("aria-label", `查看来源 ${number}`);
    return button;
  }

  function fillList(element, items, withCitation = true) {
    element.innerHTML = "";
    if (!items || !items.length) {
      const empty = document.createElement("li");
      empty.className = "is-empty";
      empty.textContent = "政策原文里没有找到这一项，建议向窗口确认。";
      element.appendChild(empty);
      return;
    }
    for (const item of items) {
      const li = document.createElement("li");
      const span = document.createElement("span");
      span.textContent = item.text;
      li.appendChild(span);
      if (withCitation && item.citation) li.appendChild(citeButton(item.citation));
      element.appendChild(li);
    }
  }

  function renderCard(card) {
    state.card = card;
    $("#card-title").textContent = card.title;
    $("#one-liner").textContent = card.one_liner;
    fillList($("#audience-list"), card.audience);
    fillList($("#benefit-list"), card.benefit);
    fillList($("#deadline-list"), card.deadline);
    fillList($("#pitfalls-list"), card.pitfalls);
    renderSteps(card.steps);
    $("#steps-count").textContent = `${card.steps.length} 步`;
    $("#source-count").textContent = `${card.sources.length} 段`;
    $("#disclaimer").textContent = card.disclaimer;
    renderMaterials(card);
    renderSources(card);
    renderWorkerKit();
  }

  function renderSteps(steps) {
    const list = $("#steps-list");
    list.innerHTML = "";
    if (!steps || !steps.length) {
      const empty = document.createElement("li");
      empty.className = "is-empty";
      empty.textContent = "政策原文里没有找到明确的办理步骤，建议向窗口确认。";
      list.appendChild(empty);
      return;
    }
    for (const item of steps) {
      const li = document.createElement("li");
      const span = document.createElement("span");
      span.className = "step-text";
      span.textContent = item.text;
      if (item.citation) span.appendChild(citeButton(item.citation));
      li.appendChild(span);
      list.appendChild(li);
    }
  }

  function renderMaterials(card) {
    const list = $("#materials-list");
    list.innerHTML = "";
    const checked = state.checklist.get(card.doc_id) || new Set();
    card.materials.forEach((item, index) => {
      const li = document.createElement("li");
      const row = document.createElement("div");
      row.className = "material-row";
      const label = document.createElement("label");
      label.className = "material-label";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = checked.has(index);
      input.addEventListener("change", () => {
        const set = state.checklist.get(card.doc_id) || new Set();
        if (input.checked) set.add(index);
        else set.delete(index);
        state.checklist.set(card.doc_id, set);
        updateChecklistProgress();
      });
      const span = document.createElement("span");
      span.textContent = item.text;
      label.append(input, span);
      row.appendChild(label);
      if (item.citation) row.appendChild(citeButton(item.citation));
      li.appendChild(row);
      list.appendChild(li);
    });
    updateChecklistProgress();
  }

  function updateChecklistProgress() {
    const card = state.card;
    if (!card) return;
    const total = card.materials.length;
    const checked = (state.checklist.get(card.doc_id) || new Set()).size;
    $("#checklist-progress").textContent = `${checked} / ${total}`;
  }

  function renderSources(card) {
    const wrap = $("#sources-list");
    wrap.innerHTML = "";
    if (!card.sources.length) {
      const empty = document.createElement("p");
      empty.className = "disclaimer";
      empty.textContent = "这份政策还没有可引用的片段。";
      wrap.appendChild(empty);
      return;
    }
    for (const source of card.sources) {
      const details = document.createElement("details");
      details.id = `source-${source.index}`;
      const summary = document.createElement("summary");
      summary.textContent = `来源 ${source.index} · 第 ${source.chunk_index + 1} 段`;
      const text = document.createElement("p");
      text.textContent = source.snippet;
      details.append(summary, text);
      wrap.appendChild(details);
    }
  }

  function renderWorkerKit() {
    const kit = $("#worker-kit");
    if (!kit) return;
    const worker = state.persona === "worker";
    kit.hidden = !worker;
    if (!worker || !state.card) return;
    const card = state.card;
    const clean = (value) => String(value).replace(/[。；;，,]$/, "");
    const parts = [`您好，根据《${card.title}》，${card.one_liner}`];
    if (card.materials.length) {
      parts.push(`需要准备：${card.materials.map((item) => clean(item.text)).join("、")}。`);
    }
    if (card.steps.length) {
      parts.push(`办理流程：${card.steps.map((item, index) => `${index + 1}. ${clean(item.text)}`).join(" ")}`);
    }
    if (card.deadline.length) {
      parts.push(`时间：${card.deadline.map((item) => clean(item.text)).join("；")}。`);
    }
    parts.push("具体以当地官方最新发布为准。");
    $("#worker-reply").textContent = parts.join("\n");
  }

  function setupSuggestions() {
    const wrap = $("#suggestions");
    wrap.innerHTML = "";
    const questions = ["需要准备哪些材料？", "多久能办完？", "有哪些容易忽略的注意事项？"];
    for (const question of questions) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = question;
      button.addEventListener("click", () => {
        const input = $("#question");
        input.value = question;
        autoGrow(input);
        $("#chat-form").requestSubmit();
      });
      wrap.appendChild(button);
    }
  }

  function resetChatForDoc() {
    state.history = [];
    const log = $("#chat-log");
    log.innerHTML = `
      <div class="welcome-note">
        <strong>只回答这份政策里的内容。</strong>
        拿不准的地方，会直接告诉你，并建议去社区窗口或拨打 12345 确认。
      </div>
    `;
  }

  async function loadDocuments(preferredId = null) {
    const select = $("#policy-select");
    const docs = await api("/api/documents");
    state.documents = docs;
    select.innerHTML = "";

    if (!docs.length) {
      const option = document.createElement("option");
      option.textContent = "还没有政策";
      select.appendChild(option);
      $("#card-title").textContent = "先上传一份政策";
      $("#one-liner").textContent = "支持 txt / md。上传后会自动生成明白卡。";
      $("#card-content").querySelectorAll("ul, ol").forEach((list) => {
        list.innerHTML = "";
      });
      $("#sources-list").innerHTML = "";
      $("#chat-form").querySelector("textarea").disabled = true;
      $("#send-btn").disabled = true;
      return;
    }

    for (const doc of docs) {
      const option = document.createElement("option");
      option.value = doc.id;
      option.textContent = doc.title;
      select.appendChild(option);
    }

    const previous = preferredId || state.currentDocId;
    const chosen = docs.some((doc) => doc.id === previous) ? previous : docs[0].id;
    select.value = chosen;
    $("#chat-form").querySelector("textarea").disabled = false;
    $("#send-btn").disabled = false;
    await loadCard(chosen);
  }

  async function loadCard(docId) {
    if (!docId) return;
    if (state.speaking) {
      window.speechSynthesis.cancel();
      state.speaking = false;
      const speakButton = $("#speak-toggle");
      if (speakButton) {
        speakButton.textContent = "朗读";
        speakButton.setAttribute("aria-pressed", "false");
      }
    }

    state.currentDocId = docId;
    resetDeleteState();
    $("#card-loading").hidden = false;
    $("#card-content").style.opacity = "0.35";
    $("#worker-kit").hidden = true;
    resetChatForDoc();

    try {
      const card = await api(`/api/policy/${docId}/card`);
      renderCard(card);
      $("#card-content").style.opacity = "1";
    } catch (error) {
      state.card = null;
      $("#card-title").textContent = "这张卡暂时没生成出来";
      $("#one-liner").textContent = error.message || "请稍后重试。";
      $("#card-content").style.opacity = "1";
      setStatus(error.message || "生成明白卡失败。");
    } finally {
      $("#card-loading").hidden = true;
    }
  }

  function scrollToSource(number) {
    const details = document.getElementById(`source-${number}`);
    if (!details) return;
    details.open = true;
    details.classList.add("is-flash");
    details.scrollIntoView({
      behavior: reduceMotion.matches ? "auto" : "smooth",
      block: "center",
    });
    window.setTimeout(() => details.classList.remove("is-flash"), 1200);
  }

  function setupGlobalHandlers() {
    document.addEventListener("click", (event) => {
      const cite = event.target.closest("[data-cite]");
      if (cite) {
        event.preventDefault();
        scrollToSource(Number(cite.dataset.cite));
      }
      const followup = event.target.closest("[data-followup]");
      if (followup) {
        const input = $("#question");
        input.value = followup.dataset.followup;
        autoGrow(input);
        $("#chat-form").requestSubmit();
      }
    });
  }

  function setupSelect() {
    $("#policy-select").addEventListener("change", (event) => {
      loadCard(event.target.value);
    });
  }

  function setupUpload() {
    const input = $("#file-input");
    const label = $(".upload-label");
    if (!input || !label) return;

    input.addEventListener("change", () => {
      uploadFiles(Array.from(input.files || []));
      input.value = "";
    });

    ["dragenter", "dragover"].forEach((name) => {
      label.addEventListener(name, (event) => {
        event.preventDefault();
        label.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      label.addEventListener(name, (event) => {
        event.preventDefault();
        label.classList.remove("is-dragover");
      });
    });
    label.addEventListener("drop", (event) => {
      const files = Array.from(event.dataTransfer?.files || []);
      if (files.length) uploadFiles(files);
    });
  }

  async function uploadFiles(files) {
    if (!files.length) return;
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    setStatus("正在读取、切分并生成明白卡…");
    try {
      const response = await fetch("/api/documents", { method: "POST", body: form });
      if (!response.ok) {
        let detail = `上传失败（${response.status}）`;
        try {
          const payload = await response.json();
          if (payload && payload.detail) detail = payload.detail;
        } catch {
          // Keep the status message.
        }
        throw new Error(detail);
      }
      const created = await response.json();
      const firstId = created.length ? created[0].id : null;
      await loadDocuments(firstId);
      await loadStats();
      setStatus(`已生成 ${created.length} 张明白卡。`);
    } catch (error) {
      setStatus(error.message || "上传失败，请重试。");
    }
  }

  function resetDeleteState() {
    state.deleteArmed = false;
    window.clearTimeout(state.deleteTimer);
    const button = $("#delete-policy");
    if (!button) return;
    button.classList.remove("is-armed");
    button.textContent = "删除当前政策";
  }

  function setupDelete() {
    const button = $("#delete-policy");
    if (!button) return;
    button.addEventListener("click", async () => {
      if (!state.currentDocId) {
        setStatus("还没有可删除的政策。");
        return;
      }
      if (!state.deleteArmed) {
        state.deleteArmed = true;
        button.classList.add("is-armed");
        button.textContent = "再点一次确认删除";
        state.deleteTimer = window.setTimeout(resetDeleteState, 4000);
        return;
      }
      const docId = state.currentDocId;
      resetDeleteState();
      try {
        const response = await fetch(`/api/documents/${docId}`, { method: "DELETE" });
        if (!response.ok) throw new Error("删除失败");
        state.currentDocId = null;
        await loadDocuments();
        await loadStats();
        setStatus("已删除当前政策。");
      } catch (error) {
        setStatus(error.message || "删除失败，请重试。");
      }
    });
  }

  function buildMarkdown(card) {
    const checked = state.checklist.get(card.doc_id) || new Set();
    const lines = [
      `# 明白卡：${card.title}`,
      "",
      `> ${card.one_liner}`,
      "",
      "## 谁能办",
      "",
      ...card.audience.map((item) => `- ${item.text}`),
      "",
      "## 能领什么",
      "",
      ...card.benefit.map((item) => `- ${item.text}`),
      "",
      "## 要带什么",
      "",
      ...card.materials.map((item, index) => `- [${checked.has(index) ? "x" : " "}] ${item.text}`),
      "",
      "## 怎么办",
      "",
      ...card.steps.map((item, index) => `${index + 1}. ${item.text}`),
      "",
      "## 什么时候截止",
      "",
      ...card.deadline.map((item) => `- ${item.text}`),
      "",
      "## 常见坑",
      "",
      ...card.pitfalls.map((item) => `- ${item.text}`),
      "",
      "## 找谁问",
      "",
      ...card.contact.map((item) => `- ${item.text}`),
      "",
      "## 原文出处",
      "",
      ...card.sources.map((source) => `${source.index}. ${source.snippet}`),
      "",
      `> ${card.disclaimer}`,
      "",
    ];
    return lines.join("\n");
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function safeFilename(value) {
    return String(value).replace(/[\\/:*?"<>|]/g, "").replace(/\s+/g, "_").slice(0, 60);
  }

  function setupExport() {
    const exportButton = $("#export-btn");
    const printButton = $("#print-btn");
    const copyReplyButton = $("#copy-reply-btn");

    if (exportButton) {
      exportButton.addEventListener("click", () => {
        if (!state.card) {
          setStatus("请先生成一张明白卡。");
          return;
        }
        downloadText(`明白卡_${safeFilename(state.card.title)}.md`, buildMarkdown(state.card));
        setStatus("明白卡已导出。");
      });
    }

    if (printButton) {
      printButton.addEventListener("click", () => {
        $$("#sources-list details").forEach((details) => {
          details.open = true;
        });
        window.print();
      });
    }

    if (copyReplyButton) {
      copyReplyButton.addEventListener("click", async () => {
        const text = $("#worker-reply").textContent || "";
        const ok = await copyText(text);
        setStatus(ok ? "回复已复制。" : "复制失败，请手动选择文本。");
      });
    }
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch {
        ok = false;
      }
      area.remove();
      return ok;
    }
  }

  async function loadHealth() {
    try {
      const health = await api("/api/health");
      const badge = $("#mode-badge");
      if (!badge) return;
      const online = health.mode === "openai";
      badge.textContent = online ? "在线模型" : "本地模式";
      badge.classList.toggle("openai", online);
    } catch {
      // Health is decorative; the card request will surface real errors.
    }
  }

  async function loadStats() {
    try {
      const stats = await api("/api/stats");
      $("#stat-docs").textContent = numberFormat.format(stats.documents || 0);
      $("#stat-chunks").textContent = numberFormat.format(stats.chunks || 0);
      $("#stat-queries").textContent = numberFormat.format(stats.queries || 0);
      $("#stat-saved").textContent = numberFormat.format(Math.round(stats.time_saved_minutes || 0));
    } catch {
      // The proof strip keeps its demo values when stats are unavailable.
    }
  }

  async function init() {
    setupNav();
    setupReveal();
    setupParallax();
    setupModeSwitch();
    setupAccessibility();
    setupChat();
    setupSuggestions();
    setupGlobalHandlers();
    setupSelect();
    setupUpload();
    setupDelete();
    setupExport();
    await Promise.all([loadHealth(), loadStats()]);
    try {
      await loadDocuments();
    } catch (error) {
      $("#card-title").textContent = "暂时连接不上后端";
      $("#one-liner").textContent = error.message || "请确认服务已经启动。";
      setStatus(error.message || "请确认服务已经启动。");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
