"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const script = fs.readFileSync(path.join(__dirname, "..", "xiaomi-remote-video.user.js"), "utf8");

function setup({videos = [], focused = null, visible = true} = {}) {
  const listeners = {};
  const doc = {
    activeElement: focused,
    visibilityState: visible ? "visible" : "hidden",
    querySelectorAll(selector) {
      assert.equal(selector, "video");
      return videos;
    },
    addEventListener(name, callback) {
      (listeners[name] ||= []).push(callback);
    },
  };
  const win = {
    addEventListener(name, callback) {
      (listeners["window:" + name] ||= []).push(callback);
    },
  };
  const context = { document: doc, window: win, innerWidth: 1920, innerHeight: 1080,
    console, Promise };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(script, context);
  function key(name, {trusted = true, repeat = false, type = "keydown"} = {}) {
    const event = {code: name, key: name, repeat, isTrusted: trusted,
      prevented: false, stopped: false,
      preventDefault() {this.prevented = true;},
      stopImmediatePropagation() {this.stopped = true;}};
    for (const listener of listeners[type] || []) listener(event);
    return event;
  }
  return {key, listeners, doc};
}

function video({paused = true, width = 640, height = 360} = {}) {
  return {
    readyState: 4, ended: false, videoWidth: width, videoHeight: height,
    isConnected: true, paused, plays: 0, pauses: 0, playbackRate: 1.7,
    getBoundingClientRect() { return {left: 0, top: 0, width, height}; },
    play() { this.plays++; this.paused = false; return Promise.resolve(); },
    pause() { this.pauses++; this.paused = true; },
  };
}

const v = video();
const env = setup({videos: [v]});
assert.equal(env.key("F13").prevented, true);
assert.equal(v.plays, 1);
assert.equal(v.playbackRate, 1.7, "Global Speed remains sole speed engine");
assert.equal(env.key("F13", {repeat: true}).prevented, false);
assert.equal(env.key("F13").prevented, false);
env.key("F13", {type: "keyup"});
assert.equal(env.key("F13").prevented, true);
assert.equal(v.pauses, 1);
env.key("F13", {type: "keyup"});
assert.equal(env.key("F13", {trusted: false}).prevented, false);
assert.equal(v.plays, 1, "untrusted synthetic keys ignored");
const typed = setup({videos: [video()], focused: {tagName: "INPUT", isContentEditable: false}});
assert.equal(typed.key("F13").prevented, false);
const shadow = setup({videos: [video()], focused: {tagName: "DIV",
  shadowRoot: {activeElement: {tagName: "TEXTAREA", isContentEditable: false}}}});
assert.equal(shadow.key("F13").prevented, false);
assert.equal(setup({videos: [video()], visible: false}).key("F13").prevented, false);
assert.equal(setup({videos: []}).key("F13").prevented, false);
const hidden = video({width: 20, height: 12});
assert.equal(setup({videos: [hidden]}).key("F13").prevented, false);
const two = video({paused: true});
const playing = video({paused: false});
const multi = setup({videos: [two, playing]});
assert.equal(multi.key("F13").prevented, true);
assert.equal(playing.pauses, 1, "prefer playing over paused on same page");
assert.equal(two.plays, 0);
assert.equal(multi.key("F13", {type: "keyup"}).prevented, false);
console.log("XIAOMI_VIDEO_F13_PLAYPAUSE_TEST_PASSED");
