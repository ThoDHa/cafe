/*
 * Print-time root font scaler for the published menu pages.
 *
 * The build injects a print root (style#print-fit) fitted by weasyprint;
 * it is the CI budget oracle and the no-JS fallback. This script refines
 * that root for the visitor's actual browser at print time: it re-lays the
 * page out under its own print styles inside a hidden iframe sized to the
 * Letter page area, then searches for the largest root that keeps the page
 * budget, modelled as a greedy pack of the top-level blocks into pages.
 * Scaling is uniform root-only, so the type ramp, palette, and chrome are
 * untouched. Letter is the binding paper; A4 is taller and keeps its
 * geometric remainder. On any doubt the script does nothing and the
 * build-injected fit stands.
 */
(function () {
  "use strict";

  var PAPERS = { letter: { widthMm: 215.9, heightMm: 279.4 } };
  var MM_TO_PX = 96 / 25.4;
  var BUILD_ROOT_DEFAULT = 16;
  var ROOT_FLOOR = 11;
  var ROOT_STEP = 0.25;
  // Fraction of the page content box kept clear of ink, so rounding and
  // metric drift between measuring and printing cannot spill a page.
  var PRINT_FILL_SAFETY = 0.01;
  var FONTS_TIMEOUT_MS = 3000;
  var FIT_STYLE_ID = "print-fit";
  var LIVE_STYLE_ID = "print-scaler-live";
  var EPSILON = 1e-9;

  function round2(value) {
    return Math.round(value * 100) / 100;
  }

  function geometry(config) {
    var paper = PAPERS[config.paper];
    var margins = config.pageMarginsMm;
    if (!paper || !margins || margins.length !== 2) return null;
    if (!(margins[0] >= 0) || !(margins[1] >= 0)) return null;
    var capacity = (paper.heightMm - margins[0] - margins[1]) * MM_TO_PX;
    var areaWidth = (paper.widthMm - 2 * margins[0]) * MM_TO_PX;
    if (!(capacity > 0) || !(areaWidth > 0)) return null;
    return { capacity: capacity, areaWidth: areaWidth };
  }

  function flattenMedia(css) {
    return css
      .replace(/@media\s+print\b/g, "@media all")
      .replace(/@media\s+screen\b/g, "@media not all");
  }

  // Greedy pack of unbreakable top-level blocks into page content boxes.
  // Sections carry break-inside: avoid, so treating header/footer as
  // unbreakable too can only overestimate the page count. Blocks taller
  // than a page are fragmented, as engines do despite break-inside: avoid.
  function estimatePageCount(blocks, pageLead, pageTail, capacity, safety) {
    var usable = capacity * (1 - safety);
    if (!(usable > 0) || pageLead + pageTail > usable) return Infinity;
    var pages = 1;
    var fill = pageLead;
    for (var i = 0; i < blocks.length; i++) {
      var h = blocks[i].h;
      if (blocks[i].breakBefore && i > 0) {
        pages += 1;
        fill = 0;
      }
      if (fill + h <= usable + EPSILON) {
        fill += h;
      } else if (h <= usable + EPSILON) {
        pages += 1;
        fill = h;
      } else {
        var carry = h - (usable - fill);
        var extra = Math.ceil(carry / usable);
        pages += extra;
        fill = carry - (extra - 1) * usable;
      }
    }
    if (fill + pageTail > usable + EPSILON) pages += 1;
    return pages;
  }

  // Walks measure(root) from the build-injected fit toward the largest
  // root in [floor, cap] that stays within the budget. Every loop is
  // bounded by (cap - floor) / step. Single-page budgets get one
  // interpolation refinement toward a full page, re-verified by measure.
  function solveRoot(measure, opts) {
    var floor = typeof opts.floor === "number" ? opts.floor : ROOT_FLOOR;
    var step = typeof opts.step === "number" ? opts.step : ROOT_STEP;
    var safety =
      typeof opts.safety === "number" ? opts.safety : PRINT_FILL_SAFETY;
    if (!(step > 0) || !(opts.capacity > 0) || !(opts.cap >= floor)) {
      return null;
    }
    var failed = false;
    function fits(root) {
      var layout = measure(root);
      if (!layout) {
        failed = true;
        return false;
      }
      return (
        estimatePageCount(
          layout.blocks,
          layout.pageLead,
          layout.pageTail,
          opts.capacity,
          safety
        ) <= opts.budget
      );
    }
    var startRoot = Math.min(Math.max(opts.start, floor), opts.cap);
    var root;
    if (fits(startRoot)) {
      root = startRoot;
    } else {
      root = null;
      for (
        var r = round2(startRoot - step);
        r >= floor - EPSILON;
        r = round2(r - step)
      ) {
        if (fits(r)) {
          root = r;
          break;
        }
      }
      if (root === null) return null;
    }
    var next = round2(root + step);
    while (next <= opts.cap + EPSILON && fits(next)) {
      root = next;
      next = round2(root + step);
    }
    if (failed) return null;
    if (opts.budget === 1 && next <= opts.cap + EPSILON) {
      root = refineFullPage(root, next, measure, fits, opts.capacity, safety);
    }
    if (failed) return null;
    return round2(root);
  }

  function refineFullPage(root, overflowingRoot, measure, fits, capacity, safety) {
    var base = measure(root);
    var over = measure(overflowingRoot);
    if (!base || !over || !(over.total > base.total)) return root;
    var target = capacity * (1 - safety);
    var exact =
      root + ((target - base.total) * (overflowingRoot - root)) / (over.total - base.total);
    var refined = Math.floor(exact * 20) / 20;
    for (var attempt = 0; attempt < 3 && refined > root; attempt++) {
      if (fits(refined)) return refined;
      refined = round2(refined - 0.05);
    }
    return root;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      MM_TO_PX: MM_TO_PX,
      geometry: geometry,
      flattenMedia: flattenMedia,
      estimatePageCount: estimatePageCount,
      solveRoot: solveRoot
    };
    return;
  }

  function readConfig() {
    var script =
      document.currentScript ||
      document.querySelector("script[data-print-fit]");
    if (!script) return null;
    try {
      var config = JSON.parse(script.getAttribute("data-print-fit"));
    } catch (error) {
      return null;
    }
    if (
      !config ||
      typeof config.budget !== "number" ||
      typeof config.cap !== "number" ||
      !Array.isArray(config.pageMarginsMm)
    ) {
      return null;
    }
    return config;
  }

  function buildInjectedRoot() {
    var style = document.querySelector('style[id="' + FIT_STYLE_ID + '"]');
    if (!style) return BUILD_ROOT_DEFAULT;
    var match = style.textContent.match(/font-size:\s*([0-9.]+)px/);
    return match ? parseFloat(match[1]) : BUILD_ROOT_DEFAULT;
  }

  function emulationDocument() {
    var styleText = [];
    var styles = document.querySelectorAll("style");
    for (var i = 0; i < styles.length; i++) {
      styleText.push(flattenMedia(styles[i].textContent));
    }
    var links = [];
    var sheets = document.querySelectorAll('link[rel="stylesheet"]');
    for (var j = 0; j < sheets.length; j++) {
      links.push(sheets[j].outerHTML);
    }
    var content = [];
    var children = document.body.children;
    for (var k = 0; k < children.length; k++) {
      if (children[k].tagName === "SCRIPT") continue;
      content.push(children[k].outerHTML);
    }
    return (
      '<!DOCTYPE html><html lang="' + document.documentElement.lang +
      '"><head>' + links.join("") + "<style>" + styleText.join("\n") +
      "</style></head><body>" + content.join("") + "</body></html>"
    );
  }

  function isForcedBreak(style) {
    var value = style.breakBefore || style.pageBreakBefore;
    return (
      value === "page" || value === "always" || value === "left" ||
      value === "right"
    );
  }

  function measureIn(frame) {
    return function (root) {
      var doc = frame.contentDocument;
      if (!doc || !doc.body) return null;
      doc.documentElement.style.fontSize = root + "px";
      var card = doc.querySelector(".card");
      if (!card) return null;
      var view = frame.contentWindow;
      var cardStyle = view.getComputedStyle(card);
      var pageLead = parseFloat(cardStyle.paddingTop);
      var pageTail = parseFloat(cardStyle.paddingBottom);
      if (!isFinite(pageLead) || !isFinite(pageTail)) return null;
      var blocks = [];
      var total = pageLead + pageTail;
      for (var i = 0; i < card.children.length; i++) {
        var el = card.children[i];
        var style = view.getComputedStyle(el);
        if (style.display === "none" || style.position === "fixed") continue;
        var h = el.getBoundingClientRect().height;
        if (!isFinite(h)) return null;
        blocks.push({ h: h, breakBefore: isForcedBreak(style) });
        total += h;
      }
      if (blocks.length === 0 || !(total > 0)) return null;
      return {
        blocks: blocks,
        pageLead: pageLead,
        pageTail: pageTail,
        total: total
      };
    };
  }

  function timeout(ms) {
    return new Promise(function (_, reject) {
      setTimeout(reject, ms);
    });
  }

  function solveInFrame(config, geometryInfo) {
    var frame = document.createElement("iframe");
    frame.setAttribute("aria-hidden", "true");
    frame.setAttribute("tabindex", "-1");
    frame.setAttribute("title", "");
    frame.style.cssText =
      "position:fixed;visibility:hidden;border:0;pointer-events:none;" +
      "left:-200vw;top:0;width:" + Math.floor(geometryInfo.areaWidth) +
      "px;height:" + Math.ceil(geometryInfo.capacity) + "px";
    var loaded = new Promise(function (resolve) {
      frame.addEventListener("load", resolve, { once: true });
    });
    document.body.appendChild(frame);
    frame.srcdoc = emulationDocument();
    return loaded
      .then(function () {
        var doc = frame.contentDocument;
        if (!doc || !doc.body) return Promise.reject(new Error("no document"));
        doc.documentElement.style.overflow = "hidden";
        if (doc.fonts && doc.fonts.ready) {
          doc.fonts.ready.catch(function () {});
          return Promise.race([doc.fonts.ready, timeout(FONTS_TIMEOUT_MS)]);
        }
        return Promise.resolve();
      })
      .then(function () {
        return solveRoot(measureIn(frame), {
          start: buildInjectedRoot(),
          cap: config.cap,
          budget: config.budget,
          capacity: geometryInfo.capacity
        });
      })
      .catch(function () {
        return null;
      })
      .then(function (result) {
        frame.remove();
        return typeof result === "number" && isFinite(result) ? result : null;
      });
  }

  function applyPrintRoot(root) {
    restorePrintRoot();
    var style = document.createElement("style");
    style.id = LIVE_STYLE_ID;
    style.textContent =
      "@media print { html { font-size: " + round2(root) + "px; } }";
    document.head.appendChild(style);
  }

  function restorePrintRoot() {
    var existing = document.getElementById(LIVE_STYLE_ID);
    if (existing) existing.remove();
  }

  var config = readConfig();
  var fittedRoot = null;
  if (config) {
    var geometryInfo = geometry(config);
    if (geometryInfo) {
      var kick = function () {
        solveInFrame(config, geometryInfo).then(function (root) {
          if (
            root !== null &&
            Math.abs(root - buildInjectedRoot()) >= 0.01
          ) {
            fittedRoot = root;
          }
        });
      };
      if (typeof window.requestIdleCallback === "function") {
        window.requestIdleCallback(kick, { timeout: 2000 });
      } else {
        window.setTimeout(kick, 200);
      }
    }
  }

  window.addEventListener("beforeprint", function () {
    if (fittedRoot !== null) applyPrintRoot(fittedRoot);
  });
  window.addEventListener("afterprint", restorePrintRoot);
})();
