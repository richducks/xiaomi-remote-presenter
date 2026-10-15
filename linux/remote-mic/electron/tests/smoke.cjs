"use strict";
const fs=require("node:fs"),assert=require("node:assert/strict"),path=require("node:path");
const base=path.resolve(__dirname,"..");
assert.equal(JSON.parse(fs.readFileSync(path.join(base,"package.json"),"utf8")).main,"main.cjs");
const main=fs.readFileSync(path.join(base,"main.cjs"),"utf8");
const preload=fs.readFileSync(path.join(base,"preload.cjs"),"utf8");
const renderer=fs.readFileSync(path.join(base,"renderer.cjs"),"utf8");
for(const name of ["state","readRules","saveRules","logs","restart","reconnect"]){
  assert.ok(main.includes(name));assert.ok(preload.includes(name));
}
assert.ok(main.includes("contextIsolation:true")&&main.includes("sandbox:true")&&main.includes("nodeIntegration:false"));
assert.ok(main.includes("Trusted:")&&main.includes("2717p32b8"));
assert.ok(main.includes("xiaomi-remote-gatt-key-bridge.service"));
assert.ok(main.includes("Xiaomi RC003 GATT Key Proxy"));
assert.ok(renderer.includes("textContent")&&!renderer.includes("innerHTML"));
assert.ok(main.includes('fs.writeFileSync(dest.filePath,raw,{mode:0o600});'), "Export should preserve valid JSON without literal backslash-n");
console.log("Electron contracts passed");
