/* ── Интеграция с оболочкой Tauri v2 (активируется только при наличии window.__TAURI_INTERNALS__) ── */
(function () {
  "use strict";
  const TI = typeof window !== "undefined" ? window.__TAURI_INTERNALS__ : null;
  if (!TI || typeof TI.invoke !== "function") return;

  const invoke = (cmd, args) => TI.invoke(cmd, args || {});
  const plat = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || navigator.userAgent || "";
  const isMac = /Mac|iPhone|iPad/i.test(plat);
  const isWin = /Win/i.test(plat);

  document.documentElement.classList.add("is-tauri");

  const bridge = {
    isTauri: true,
    invoke,
    minimize: () => invoke("tauri_win_minimize"),
    toggleMaximize: () => invoke("tauri_win_toggle_max"),
    close: () => invoke("tauri_win_close"),
    pickFile: () => invoke("tauri_pick_file"),
    autostartGet: () => invoke("tauri_autostart_get"),
    autostartSet: (enabled) => invoke("tauri_autostart_set", { enabled: !!enabled }),
    bioVerify: (reason) => invoke("tauri_bio_verify", { reason: reason || "Подтвердите вход в TAnalytic" })
  };
  window.TAURI_BRIDGE = bridge;

  /* Совместимость с существующим мостом выбора файла (20_imp.js) и управления окном */
  if (!window.pywebview) {
    window.pywebview = {
      api: {
        pick_file: bridge.pickFile,
        minimize: bridge.minimize,
        toggle_maximize: bridge.toggleMaximize,
        close: bridge.close,
        platform: () => Promise.resolve(isMac ? "mac" : isWin ? "win" : "linux"),
        set_theme: () => Promise.resolve(true)
      }
    };
  }

  function mountTitlebar() {
    const main = document.querySelector("main");
    if (!main || document.getElementById("tauri-bar")) return;

    const bar = document.createElement("div");
    bar.id = "tauri-bar";
    bar.className = "tauri-bar noprint";
    bar.setAttribute("data-tauri-drag-region", "");

    const logoSvg =
      '<svg width="15" height="15" viewBox="0 0 32 32" fill="none" aria-hidden="true">' +
      '<rect width="32" height="32" rx="9" fill="#0f1420" stroke="rgba(255,255,255,.12)"/>' +
      '<path d="M7 9c0-1.1.9-2 2-2h14c1.1 0 2 .9 2 2v1.5c0 .55-.45 1-1 1H8c-.55 0-1-.45-1-1V9z" fill="#3b82f6"/>' +
      '<path d="M13.5 11.5h5V23c0 1.1-.9 2-2 2h-1c-1.1 0-2-.9-2-2V11.5z" fill="#2563eb"/>' +
      '<path d="M18.5 16l6-6m0 0h-4m4 0v4" stroke="#60a5fa" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>' +
      "</svg>";

    const controlsHtml = isMac
      ? ""
      : '<div class="tauri-win-btns">' +
        '<button type="button" class="tauri-btn" id="tauri-min" title="Свернуть" aria-label="Свернуть">' +
        '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 6h8"/></svg></button>' +
        '<button type="button" class="tauri-btn" id="tauri-max" title="Развернуть / восстановить" aria-label="Развернуть">' +
        '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"><rect x="2.2" y="2.2" width="7.6" height="7.6" rx="1"/></svg></button>' +
        '<button type="button" class="tauri-btn tauri-close" id="tauri-close" title="Закрыть" aria-label="Закрыть">' +
        '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2.5 2.5l7 7M9.5 2.5l-7 7"/></svg></button>' +
        "</div>";

    bar.innerHTML =
      '<div class="tauri-brand" data-tauri-drag-region="">' +
      (isMac ? "" : logoSvg + '<span data-tauri-drag-region="">TAnalytic</span>') +
      "</div>" +
      controlsHtml;

    main.prepend(bar);

    bar.addEventListener("dblclick", (e) => {
      if (e.target && e.target.closest && e.target.closest("button")) return;
      bridge.toggleMaximize().catch(() => {});
    });

    if (!isMac) {
      const bMin = document.getElementById("tauri-min");
      const bMax = document.getElementById("tauri-max");
      const bCls = document.getElementById("tauri-close");
      if (bMin) bMin.onclick = () => bridge.minimize().catch(() => {});
      if (bMax) bMax.onclick = () => bridge.toggleMaximize().catch(() => {});
      if (bCls) bCls.onclick = () => bridge.close().catch(() => {});
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountTitlebar, { once: true });
  } else {
    mountTitlebar();
  }
})();
