/* The professor report's script (SDD Sec. 9.8, ADR-0016 rev. 3).
 *
 * Builds every chart from the inline JSON block "tta-data" with the
 * vendored plotly.js. Every user-visible text comes from that block
 * (translated in Python, ADR-0020); every highlight level was computed in
 * Python (core.reference.band_level) - this script only picks the level
 * that matches the current filter. Nothing here touches the network.
 */
(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("tta-data").textContent);
  var S = D.strings;
  var css = getComputedStyle(document.documentElement);
  function cssVar(name) { return css.getPropertyValue(name).trim(); }
  var C = {
    ink2: cssVar("--ink-2"), ink3: cssVar("--ink-3"), grid: cssVar("--grid"),
    line: cssVar("--line"), card: cssVar("--card"),
    series: [1, 2, 3, 4, 5, 6, 7].map(function (i) { return cssVar("--series-" + i); }),
    other: cssVar("--series-x"), serious: cssVar("--serious"), critical: cssVar("--critical"),
    bandOuter: cssVar("--band-outer"), bandInner: cssVar("--band-inner")
  };
  // Offline by configuration too: no Chart Studio link, no cloud export,
  // no topojson fetch (ADR-0016 rev. 3).
  var CONFIG = {
    responsive: true, displaylogo: false, showLink: false, showSendToCloud: false,
    showEditInChartStudio: false, showTips: false, topojsonURL: "",
    modeBarButtonsToRemove: ["select2d", "lasso2d"]
  };
  var numberFormat = new Intl.NumberFormat(D.locale, { maximumSignificantDigits: 4 });
  // STATS order of the aggregates: mean, median, p05, p25, p75, p95
  var MEAN = 0, MEDIAN = 1, P05 = 2, P25 = 3, P75 = 4, P95 = 5;

  function el(id) { return document.getElementById(id); }
  function fmt(x) { return x === null || x === undefined ? "-" : numberFormat.format(x); }
  function tpl(text, values) {
    return text.replace(/\{(\w+)\}/g, function (m, key) { return key in values ? values[key] : m; });
  }

  var fType = el("f-type"), fLang = el("f-lang"), fField = el("f-field"), fHint = el("f-hint");

  function selection() {
    var type = fType.value, lang = fLang.value, field = fField.value;
    var specific = type !== "all" && lang !== "all";
    fField.disabled = !specific;
    return {
      type: type, lang: lang, field: field, specific: specific,
      // index into each thesis's level string (core.report.comparison_options)
      option: specific ? D.options.indexOf(field) : 0,
      bandKey: specific ? type + "|" + lang + "|" + field : "all|all|all"
    };
  }

  function visible(sel) {
    return D.theses.filter(function (t) {
      return (sel.type === "all" || t.type === sel.type) &&
        (sel.lang === "all" || t.lang === sel.lang);
    });
  }

  function layout(extra) {
    var base = {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      separators: D.separators, hovermode: "closest",
      font: { family: '-apple-system, "Segoe UI", Roboto, Arial, sans-serif', size: 12, color: C.ink2 },
      margin: { l: 66, r: 16, t: 12, b: 46 },
      legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", font: { size: 12 } },
      xaxis: {
        type: "linear", title: { text: S.year }, tickformat: "d", gridcolor: C.grid,
        linecolor: C.line, zeroline: false
      },
      yaxis: { type: "linear", gridcolor: C.grid, linecolor: C.line, zeroline: false }
    };
    for (var key in extra) { base[key] = extra[key]; }
    return base;
  }

  function empty(div) {
    if (window.Plotly) { Plotly.purge(div); }
    div.ttaClick = false;  // purge drops the event handlers too
    div.textContent = "";
    var p = document.createElement("p");
    p.className = "empty";
    p.textContent = S.noData;
    div.appendChild(p);
  }

  function draw(div, traces, lay) {
    if (div.querySelector("p.empty")) { div.textContent = ""; }
    Plotly.react(div, traces, lay, CONFIG);
    if (!div.ttaClick) {
      div.ttaClick = true;
      div.on("plotly_click", function (event) {
        var point = event.points && event.points[0];
        var uri = point && point.customdata && point.customdata[0];
        if (uri) { window.open(uri, "_blank"); }
      });
    }
  }

  function bandAt(sel, metric, year) {
    var series = (D.bands[sel.bandKey] || {})[metric];
    var index = D.years.indexOf(year);
    return series && index >= 0 ? series[index] : null;
  }

  // -- metrics over time ------------------------------------------------------

  var LEVELS = [
    { key: "0", name: function () { return S.level0; }, marker: function () {
      return { color: C.series[0], size: 8, symbol: "circle", line: { color: C.card, width: 1.5 } }; } },
    { key: "1", name: function () { return S.level1; }, marker: function () {
      return { color: C.serious, size: 10, symbol: "circle", line: { color: C.card, width: 1.5 } }; } },
    { key: "2", name: function () { return S.level2; }, marker: function () {
      return { color: C.critical, size: 12, symbol: "diamond", line: { color: C.card, width: 1.5 } }; } },
    { key: "-", name: function () { return S.levelNone; }, marker: function () {
      return { color: C.other, size: 8, symbol: "circle-open", line: { width: 1.5 } }; } }
  ];

  function bandTraces(sel, metric) {
    var series = (D.bands[sel.bandKey] || {})[metric];
    if (!series || !series.some(function (s) { return s; })) { return []; }
    function column(i) { return series.map(function (s) { return s ? s[i] : null; }); }
    var edge = { mode: "lines", line: { width: 0 }, hoverinfo: "skip", connectgaps: false, type: "scatter" };
    function with_(extra) { var t = {}; var k; for (k in edge) { t[k] = edge[k]; } for (k in extra) { t[k] = extra[k]; } return t; }
    return [
      with_({ x: D.years, y: column(P05), showlegend: false }),
      with_({ x: D.years, y: column(P95), fill: "tonexty", fillcolor: C.bandOuter, name: S.outer }),
      with_({ x: D.years, y: column(P25), showlegend: false }),
      with_({ x: D.years, y: column(P75), fill: "tonexty", fillcolor: C.bandInner, name: S.inner }),
      {
        x: D.years, y: column(MEDIAN), type: "scatter", mode: "lines", connectgaps: false,
        line: { color: C.ink2, width: 2 }, name: S.median,
        customdata: series.map(function (s) { return s ? [null, fmt(s[P05]), fmt(s[P25]), fmt(s[P75]), fmt(s[P95]), fmt(s[MEAN])] : null; }),
        hovertemplate: "%{x}: " + S.median + " %{y:.4~g}<br>P25-P75: %{customdata[2]} - %{customdata[3]}" +
          "<br>P5-P95: %{customdata[1]} - %{customdata[4]}<extra></extra>"
      }
    ];
  }

  function drawGroup(name, sel) {
    var metric = el("m-" + name).value, div = el("g-" + name), label = D.labels[metric];
    var byLevel = { "0": [], "1": [], "2": [], "-": [] };
    visible(sel).forEach(function (t) {
      var value = t.m[metric];
      if (value === undefined || t.x === null) { return; }
      var level = (t.lv[metric] || "").charAt(sel.option) || "-";
      byLevel[level].push(t);
    });
    var traces = bandTraces(sel, metric);
    LEVELS.forEach(function (level) {
      var list = byLevel[level.key];
      if (!list.length) { return; }
      traces.push({
        type: "scatter", mode: "markers", name: level.name(), marker: level.marker(),
        x: list.map(function (t) { return t.x; }),
        y: list.map(function (t) { return t.m[metric]; }),
        text: list.map(function (t) { return t.head; }),
        customdata: list.map(function (t) { return [t.uri]; }),
        hovertemplate: "%{text}<br>" + label + ": %{y:.4~g}<br>" + level.name() + "<extra></extra>"
      });
    });
    var points = byLevel["0"].length + byLevel["1"].length + byLevel["2"].length + byLevel["-"].length;
    if (!points && traces.length === 0) { empty(div); } else {
      draw(div, traces, layout({ yaxis: { type: "linear", title: { text: label }, gridcolor: C.grid, linecolor: C.line, zeroline: false } }));
    }
    outsideList(name, sel, metric, byLevel);
  }

  function outsideList(name, sel, metric, byLevel) {
    var box = el("o-" + name);
    box.textContent = "";
    var strong = byLevel["2"], mild = byLevel["1"];
    if (!strong.length && !mild.length) { return; }
    var details = document.createElement("details");
    var summary = document.createElement("summary");
    summary.textContent = tpl(S.outsideTitle, { count: strong.length });
    details.appendChild(summary);
    if (strong.length) {
      var wrap = document.createElement("div");
      wrap.className = "scroll";
      var table = document.createElement("table");
      var head = table.createTHead().insertRow();
      [S.colThesis, S.colYear, S.colValue, S.colBand].forEach(function (text) {
        var th = document.createElement("th"); th.textContent = text; head.appendChild(th);
      });
      var body = table.createTBody();
      strong.slice().sort(function (a, b) { return a.year - b.year || a.id - b.id; }).forEach(function (t) {
        var row = body.insertRow();
        var cell = row.insertCell();
        if (t.uri) {
          var link = document.createElement("a");
          link.href = t.uri; link.target = "_blank"; link.textContent = t.name;
          cell.appendChild(link);
        } else { cell.textContent = t.name; }
        row.insertCell().textContent = t.year;
        row.insertCell().textContent = fmt(t.m[metric]);
        var stats = bandAt(sel, metric, t.year);
        row.insertCell().textContent = stats ? fmt(stats[P05]) + " - " + fmt(stats[P95]) : "-";
      });
      wrap.appendChild(table);
      details.appendChild(wrap);
    }
    if (mild.length) {
      var more = document.createElement("p");
      more.className = "note";
      more.textContent = tpl(S.outsideMore, { count: mild.length });
      details.appendChild(more);
    }
    box.appendChild(details);
  }

  // -- coverage, boxes, tools -------------------------------------------------

  function drawCoverage(sel) {
    var div = el("g-coverage"), counts = {}, undated = 0, outside = 0;
    visible(sel).forEach(function (t) {
      if (t.year === null) { undated += 1; return; }
      counts[t.year] = (counts[t.year] || 0) + 1;
      if (t.year < D.years[0] || t.year > D.years[D.years.length - 1]) { outside += 1; }
    });
    var years = Object.keys(counts).map(Number).sort(function (a, b) { return a - b; });
    var notes = [];
    if (outside) { notes.push(tpl(S.noComparisonYears, { count: outside })); }
    if (undated) { notes.push(tpl(S.undated, { count: undated })); }
    el("n-coverage").textContent = notes.join(" ");
    if (!years.length) { empty(div); return; }
    var peak = Math.max.apply(null, years.map(function (y) { return counts[y]; }));
    draw(div, [{
      type: "bar", x: years, y: years.map(function (y) { return counts[y]; }),
      marker: { color: C.series[0] }, hovertemplate: "%{x}: %{y}<extra></extra>"
    }], layout({
      showlegend: false, bargap: 0.25,
      yaxis: { type: "linear", title: { text: S.theses }, rangemode: "tozero", gridcolor: C.grid,
        linecolor: C.line, zeroline: false, dtick: peak <= 10 ? 1 : null, tickformat: "d" }
    }));
  }

  function drawBoxes(sel) {
    var metric = el("m-boxes").value, div = el("g-boxes"), byYear = {};
    visible(sel).forEach(function (t) {
      if (t.year === null || t.m[metric] === undefined) { return; }
      (byYear[t.year] = byYear[t.year] || []).push(t.m[metric]);
    });
    var xs = [], ys = [];
    Object.keys(byYear).map(Number).sort(function (a, b) { return a - b; }).forEach(function (year) {
      if (byYear[year].length < D.minBox) { return; }
      byYear[year].forEach(function (value) { xs.push(year); ys.push(value); });
    });
    if (!xs.length) { empty(div); return; }
    draw(div, [{
      type: "box", x: xs, y: ys, boxpoints: "outliers", quartilemethod: "linear",
      marker: { color: C.series[0], size: 6 }, line: { color: C.series[0], width: 1.5 },
      name: S.theses
    }], layout({
      showlegend: false,
      yaxis: { type: "linear", title: { text: D.labels[metric] }, gridcolor: C.grid, linecolor: C.line, zeroline: false }
    }));
  }

  var TOOL_COLORS = {
    latex: 0, word: 1, libreoffice: 2, openoffice: 3, indesign: 4, ghostscript: 5
  };

  function drawTools(sel) {
    var div = el("g-tools"), counts = {}, years = {};
    visible(sel).forEach(function (t) {
      if (t.year === null) { return; }
      years[t.year] = true;
      var key = t.tool + "|" + t.year;
      counts[key] = (counts[key] || 0) + 1;
    });
    var xs = Object.keys(years).map(Number).sort(function (a, b) { return a - b; });
    if (!xs.length) { empty(div); return; }
    var traces = [];
    D.toolOrder.forEach(function (tool) {
      var ys = xs.map(function (y) { return counts[tool + "|" + y] || 0; });
      if (!ys.some(function (n) { return n; })) { return; }
      var color = tool in TOOL_COLORS ? C.series[TOOL_COLORS[tool]] : (tool === "other" ? C.other : C.ink3);
      traces.push({
        type: "bar", name: D.tools[tool], x: xs, y: ys,
        marker: { color: color, line: { color: C.card, width: 1 } },
        hovertemplate: D.tools[tool] + ": %{y}<extra>%{x}</extra>"
      });
    });
    draw(div, traces, layout({
      barmode: "stack", bargap: 0.25,
      yaxis: { type: "linear", title: { text: S.theses }, rangemode: "tozero", gridcolor: C.grid,
        linecolor: C.line, zeroline: false, tickformat: "d" }
    }));
  }

  // -- wiring -------------------------------------------------------------------

  var GROUPS = Object.keys(D.groups);

  function drawAll() {
    var sel = selection();
    fHint.textContent = sel.specific ? S.fieldHintActive : S.fieldHint;
    drawCoverage(sel);
    GROUPS.forEach(function (name) { drawGroup(name, sel); });
    drawBoxes(sel);
    drawTools(sel);
  }

  [fType, fLang, fField].forEach(function (select) { select.addEventListener("change", drawAll); });
  GROUPS.forEach(function (name) {
    el("m-" + name).addEventListener("change", function () { drawGroup(name, selection()); });
  });
  el("m-boxes").addEventListener("change", function () { drawBoxes(selection()); });
  drawAll();
})();
