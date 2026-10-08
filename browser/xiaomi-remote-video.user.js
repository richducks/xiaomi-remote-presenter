// ==UserScript==
// @name         小米遥控器 2 Pro · Windows/macOS 浏览器视频 OK
// @namespace    https://github.com/richducks/xiaomi-remote-presenter
// @version      1.0.0
// @description  小米遥控器设备级映射 OK→F13 后，控制当前视频的播放/暂停；不修改 Global Speed 的 playbackRate
// @match        https://*/*
// @match        http://*/*
// @grant        none
// @run-at       document-start
// @all-frames   true
// ==/UserScript==

(() => {
  "use strict";
  const tag = "__xiaomiRemoteVideoOkF13_v1";
  if (globalThis[tag]) return;
  globalThis[tag] = true;

  let pressed = false;

  function focusIsEditable() {
    let el = document.activeElement;
    // Walk nested shadow roots; YouTube's input can live inside components.
    for (let depth = 0; depth < 8 && el?.shadowRoot?.activeElement; depth++)
      el = el.shadowRoot.activeElement;
    if (!el) return false;
    if (el.isContentEditable) return true;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(String(el.tagName).toUpperCase()))
      return true;
    try {
      return Boolean(el.closest?.('[contenteditable]:not([contenteditable="false"])'));
    } catch {
      return false;
    }
  }

  function findVisibleVideo() {
    const results = [];
    for (const video of document.querySelectorAll("video")) {
      if (!video.isConnected || video.ended || video.readyState < 1)
        continue;
      if ((video.videoWidth || 0) < 80 && (video.videoHeight || 0) < 80)
        continue;
      const box = video.getBoundingClientRect();
      if (box.width < 80 || box.height < 45)
        continue;
      const centerX = box.left + box.width / 2;
      const centerY = box.top + box.height / 2;
      // A hidden frame or off-screen preload must not control video in
      // another tab. Videos partly visible may still qualify.
      if (centerX < -100 || centerY < -100 ||
          centerX > innerWidth + 100 || centerY > innerHeight + 100)
        continue;
      results.push({ video, area: box.width * box.height });
    }
    // Prefer the already-playing video, then the largest visible player.
    results.sort((a, b) => Number(a.video.paused) - Number(b.video.paused) ||
      b.area - a.area);
    return results[0]?.video || null;
  }

  document.addEventListener("keydown", event => {
    if (event.code !== "F13" && event.key !== "F13") return;
    if (event.repeat || pressed) return;
    // Synthetic in-page scripts may not impersonate the physical remote.
    if (!event.isTrusted) return;
    if (document.visibilityState !== "visible" || focusIsEditable()) return;
    const video = findVisibleVideo();
    if (!video) return;
    pressed = true;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (video.paused) {
      Promise.resolve(video.play()).catch(err =>
        console.warn("[Xiaomi Remote] Play rejected:", err));
    } else {
      video.pause();
    }
  }, true);

  document.addEventListener("keyup", event => {
    if (event.code !== "F13" && event.key !== "F13") return;
    pressed = false;
  }, true);

  window.addEventListener("blur", () => { pressed = false; });
})();
