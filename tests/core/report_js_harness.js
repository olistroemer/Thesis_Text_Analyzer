/* Runs the report script (tta/core/report_assets/report.js) under node with a
 * minimal fake DOM and a fake Plotly that records what would be drawn.
 *
 *   node report_js_harness.js <report.js> <payload.json> <type> <lang> <field>
 *
 * Prints {"traces": {"<div id>": [traces...]}, "notes": {"o-<group>": [texts]}}
 * as JSON. Used by tests/core/test_report.py
 * to check the band and highlight rendering without a browser.
 */
"use strict";
var fs = require("fs");
var vm = require("vm");

var args = process.argv.slice(2);
var payload = fs.readFileSync(args[1], "utf8");
var values = { "f-type": args[2], "f-lang": args[3], "f-field": args[4] };
var data = JSON.parse(payload);
Object.keys(data.groups).forEach(function (group) {
  values["m-" + group] = data.groups[group][0];
});
values["m-boxes"] = "word_count";

function element(id) {
  var e = {
    id: id, value: values[id], textContent: id === "tta-data" ? payload : "",
    disabled: false, className: "", children: [],
    addEventListener: function () {}, on: function () {},
    appendChild: function (child) { e.children.push(child); return child; },
    querySelector: function () { return null; },
    insertRow: function () { return element(); },
    insertCell: function () { return element(); },
    createTHead: function () { return element(); },
    createTBody: function () { return element(); }
  };
  return e;
}

var elements = {};
var drawn = {};
var sandbox = {
  JSON: JSON, Intl: Intl, Math: Math, Object: Object,
  document: {
    documentElement: {},
    getElementById: function (id) { return elements[id] || (elements[id] = element(id)); },
    createElement: function () { return element(); }
  },
  getComputedStyle: function () { return { getPropertyValue: function (name) { return name; } }; },
  Plotly: {
    react: function (div, traces) { drawn[div.id] = traces; },
    purge: function (div) { delete drawn[div.id]; }
  }
};
sandbox.window = sandbox;
sandbox.window.open = function () {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(args[0], "utf8"), sandbox, { filename: args[0] });
// the outside-the-band summaries under each panel, as their visible texts
function texts(e) {
  var out = e.textContent ? [e.textContent] : [];
  e.children.forEach(function (child) { out = out.concat(texts(child)); });
  return out;
}
var notes = {};
Object.keys(elements).forEach(function (id) {
  if (id.indexOf("o-") === 0) { notes[id] = texts(elements[id]); }
});
process.stdout.write(JSON.stringify({ traces: drawn, notes: notes }));
