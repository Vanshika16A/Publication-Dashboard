// A reusable WebGL network view: sigma.js renders, ForceAtlas2 (in a web worker) lays out.
// Only a chosen subgraph is ever drawn; the caller decides which nodes and edges.
import Graph from "graphology";
import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2Layout from "graphology-layout-forceatlas2/worker";
import { fade, T } from "./lib.js";

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/** Hover label: a rounded box in the theme's tooltip colours instead of sigma's default. */
function drawHover(ctx, data, settings) {
  const size = settings.labelSize + 1;
  ctx.font = `600 ${size}px ${settings.labelFont}`;
  const label = data.hoverLabel || data.label || "";
  const width = Math.min(ctx.measureText(label).width, 420) + 18;
  const height = size + 14;
  const x = data.x + data.size + 8;
  const y = data.y - height / 2;
  ctx.beginPath();
  ctx.arc(data.x, data.y, data.size + 3.5, 0, Math.PI * 2);
  ctx.strokeStyle = T.ring;
  ctx.lineWidth = 2;
  ctx.stroke();
  if (!label) return;
  ctx.shadowColor = "rgba(0,0,0,0.25)";
  ctx.shadowBlur = 12;
  roundRect(ctx, x, y, width, height, 8);
  ctx.fillStyle = T.tipBg;
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.strokeStyle = T.tipBorder;
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = T.tipText;
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, width - 9, height);
  ctx.clip();
  ctx.fillText(label, x + 9, data.y + size / 3);
  ctx.restore();
}

export class NetworkView {
  /**
   * @param {HTMLElement} container
   * @param {{directed?: boolean, onSelect?: (key: string|null) => void, onHover?: (key: string|null) => void, onStatus?: (running: boolean) => void}} opts
   */
  constructor(container, { directed = false, onSelect = () => {}, onHover = () => {}, onStatus = () => {} } = {}) {
    this.container = container;
    this.directed = directed;
    this.onSelect = onSelect;
    this.onHover = onHover;
    this.onStatus = onStatus;
    this.graph = new Graph({ type: directed ? "directed" : "undirected", multi: false });
    this.hovered = null;
    this.selected = null;
    this.neighbors = new Set();
    this.layout = null;
    this.timer = null;
    this.renderer = new Sigma(this.graph, container, {
      defaultEdgeType: directed ? "arrow" : "line",
      labelFont: "Atkinson Hyperlegible Next, system-ui, sans-serif",
      labelSize: 12,
      labelWeight: "500",
      labelColor: { color: T.text2 },
      labelDensity: 0.6,
      labelGridCellSize: 90,
      labelRenderedSizeThreshold: 9,
      defaultDrawNodeHover: drawHover,
      zIndex: true,
      minCameraRatio: 0.03,
      maxCameraRatio: 4,
      hideEdgesOnMove: false,
      stagePadding: 40,
      nodeReducer: (node, data) => this.reduceNode(node, data),
      edgeReducer: (edge, data) => this.reduceEdge(edge, data),
    });
    this.renderer.on("enterNode", ({ node }) => { this.hover(node); this.onHover(node); this.container.style.cursor = "pointer"; });
    this.renderer.on("leaveNode", () => { this.hover(null); this.onHover(null); this.container.style.cursor = ""; });
    this.renderer.on("clickNode", ({ node }) => this.select(node));
    this.renderer.on("clickStage", () => this.select(null));
  }

  focusNode() { return this.hovered || this.selected; }

  /** Highlight a node and its links as if the pointer were on it (e.g. from a list next to the graph). */
  hover(node) {
    const next = node && this.graph.hasNode(node) ? node : null;
    if (next === this.hovered) return;
    this.hovered = next;
    this.updateFocus();
  }

  updateFocus() {
    const focus = this.focusNode();
    this.neighbors = focus && this.graph.hasNode(focus) ? new Set(this.graph.neighbors(focus)) : new Set();
    this.renderer.refresh({ skipIndexation: true });
  }

  reduceNode(node, data) {
    const focus = this.focusNode();
    const res = { ...data };
    if (focus) {
      if (node === focus) {
        res.highlighted = true;
        res.zIndex = 3;
        res.forceLabel = true;
      } else if (this.neighbors.has(node)) {
        res.zIndex = 2;
        res.forceLabel = this.neighbors.size <= 25;
      } else {
        res.color = fade(data.color, 0.86);
        res.label = "";
        res.zIndex = 0;
      }
    }
    return res;
  }

  reduceEdge(edge, data) {
    const focus = this.focusNode();
    if (!focus) return data;
    const [s, t] = this.graph.extremities(edge);
    if (s === focus || t === focus) return { ...data, color: data.focusColor || T.edgeFocus, size: Math.max(data.size, 1.2), zIndex: 2 };
    return { ...data, hidden: true };
  }

  /**
   * Replace the drawn graph.
   * nodes: [{key, label, color, size, ...}], edges: [{source, target, size, color}]
   * seed(node) may return {x, y} to start from (e.g. grouped by institution) so the layout settles faster.
   */
  setGraph(nodes, edges, { seed = null, duration = null } = {}) {
    this.stopLayout();
    this.hovered = null;
    this.selected = null;
    this.neighbors = new Set();
    this.graph.clear();
    const n = nodes.length;
    nodes.forEach((node, i) => {
      const start = seed ? seed(node, i) : null;
      const angle = Math.random() * Math.PI * 2;
      const radius = Math.sqrt(Math.random()) * 100;
      this.graph.addNode(node.key, {
        x: start ? start.x + (Math.random() - 0.5) * 20 : Math.cos(angle) * radius,
        y: start ? start.y + (Math.random() - 0.5) * 20 : Math.sin(angle) * radius,
        ...node,
      });
    });
    edges.forEach((e) => {
      if (e.source !== e.target && this.graph.hasNode(e.source) && this.graph.hasNode(e.target) && !this.graph.hasEdge(e.source, e.target)) {
        this.graph.addEdge(e.source, e.target, { size: 0.6, ...e });
      }
    });
    this.renderer.refresh();
    this.renderer.getCamera().setState({ x: 0.5, y: 0.5, ratio: 1, angle: 0 });
    if (this.graph.order > 1 && this.graph.size > 0) this.runLayout(duration ?? Math.min(2200 + n * 2.2, 8000));
  }

  runLayout(ms = 3000) {
    this.stopLayout();
    const settings = forceAtlas2.inferSettings(this.graph);
    const n = this.graph.order;
    this.layout = new FA2Layout(this.graph, {
      settings: { ...settings, barnesHutOptimize: n > 300, barnesHutTheta: 0.6, gravity: 1.2, scalingRatio: n > 800 ? 6 : 3,
        strongGravityMode: false, slowDown: 1 + Math.log(n + 1) / 2, adjustSizes: false, outboundAttractionDistribution: true },
    });
    this.layout.start();
    this.onStatus(true);
    this.timer = setTimeout(() => this.stopLayout(), ms);
  }

  stopLayout() {
    clearTimeout(this.timer);
    if (this.layout) {
      this.layout.kill();
      this.layout = null;
      this.onStatus(false);
    }
  }

  select(node) {
    this.selected = node && this.graph.hasNode(node) ? node : null;
    this.updateFocus();
    this.onSelect(this.selected);
  }

  /** Move the camera to a node (after it has a position). */
  focus(node, ratio = 0.25) {
    if (!this.graph.hasNode(node)) return;
    const data = this.renderer.getNodeDisplayData(node);
    if (data) this.renderer.getCamera().animate({ x: data.x, y: data.y, ratio }, { duration: 600 });
  }

  fit() { this.renderer.getCamera().animatedReset({ duration: 500 }); }

  kill() {
    this.stopLayout();
    this.renderer.kill();
  }
}

// ---------------------------------------------------------------- pieces shared by the two network pages

const svg = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const ICONS = {
  fit: svg('<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>'),
  relayout: svg('<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>'),
  back: svg('<path d="m15 18-6-6 6-6"/>'),
};

/** The graph pane: count badges, re-layout and fit buttons, legend and layout status. */
export const stageMarkup = () => `
  <div class="stage-badges" id="badges"></div>
  <div class="stage-tools">
    <button class="icon-btn" id="relayout" type="button" title="Run the layout again" aria-label="Run the layout again">${ICONS.relayout}</button>
    <button class="icon-btn" id="fit" type="button" title="Fit to screen" aria-label="Fit to screen">${ICONS.fit}</button>
  </div>
  <div class="sigma" id="sigma"></div>
  <div class="legend" id="legend"></div>
  <div class="layout-status" id="status"></div>`;

/** Pointing at or focusing an item <li data-i="node key"> inside root lights that node up in the graph. */
export function hoverFromList(root, view) {
  const enter = (e) => { const li = e.target.closest("li[data-i]"); if (li) view.hover(li.dataset.i); };
  const leave = (e) => { const li = e.target.closest("li[data-i]"); if (li && !li.contains(e.relatedTarget)) view.hover(null); };
  root.addEventListener("mouseover", enter);
  root.addEventListener("mouseout", leave);
  root.addEventListener("focusin", enter);
  root.addEventListener("focusout", leave);
}

/** Move class cls to the list item for key (or remove it), scrolling the list just enough to show it. */
export function markItem(list, key, cls, scroll = false) {
  list.querySelector(`li.${cls}`)?.classList.remove(cls);
  const li = key === null ? null : list.querySelector(`li[data-i="${key}"]`);
  if (!li) return;
  li.classList.add(cls);
  if (!scroll) return;
  const top = li.offsetTop, bottom = top + li.offsetHeight;
  if (top < list.scrollTop || bottom > list.scrollTop + list.clientHeight) list.scrollTop = top - list.clientHeight / 3;
}
