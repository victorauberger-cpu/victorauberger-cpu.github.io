// Small interactive chart engine for the Research page (plain SVG, no library).
(function(){
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ease = k => 1 - Math.pow(1 - k, 3);
  function tween(ms, fn, done){
    if (reduce || ms <= 0){ fn(1); done && done(); return; }
    const t0 = performance.now();
    (function step(t){ const k = Math.min(1, (t - t0) / ms); fn(ease(k)); if (k < 1) requestAnimationFrame(step); else done && done(); })(t0);
  }
  const E = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

  function controlsHTML(cfg, state){
    return (cfg.controls || []).filter(c => c.options.length > 1).map(c => `
      <div class="vctl"><span>${E(c.label)}</span>${c.options.map(([v, l]) =>
        `<button data-k="${c.key}" data-v="${v}" class="${state[c.key] === v ? "on" : ""}">${E(l)}</button>`).join("")}</div>`).join("");
  }

  // ---------------- horizontal bars that morph between states ----------------
  function bars(root, cfg){
    const state = {}; (cfg.controls || []).forEach(c => state[c.key] = c.value);
    const keyOf = () => (cfg.controls || []).map(c => state[c.key]).join("|");
    const all = Object.values(cfg.states).flatMap(s => s.values).concat(cfg.ref ? [cfg.ref.value] : []);
    const lo = Math.min(0, ...all), hi = Math.max(0, ...all);
    const n = cfg.categories.length;
    let cur = cfg.categories.map(() => 0), shown = false;

    root.innerHTML = `<div class="vhead"><div class="vtitle">${E(cfg.title)}</div>${controlsHTML(cfg, state)}</div>
      <div class="vplot"></div><div class="vnote"></div><div class="vtip" hidden></div>`;
    const plot = root.querySelector(".vplot"), note = root.querySelector(".vnote"), tip = root.querySelector(".vtip");

    function draw(vals){
      const W = plot.clientWidth || 600, narrow = W < 520;
      const room = cfg.labelRoom || 80;
      const L0 = narrow ? 0 : Math.min(200, W * 0.32), L = L0 + (lo < 0 ? room : 0), R = room + 12, rowH = 30, T = cfg.ref ? 20 : 6;
      const labelRow = narrow ? 16 : 0, H = T + n * (rowH + labelRow) + 8;
      const x = v => L + (W - L - R) * (v - lo) / ((hi - lo) || 1);
      const st = cfg.states[keyOf()];
      let g = `<line class="vzero" x1="${x(0)}" x2="${x(0)}" y1="${T - 4}" y2="${H - 4}"/>`;
      if (cfg.ref) g += `<line class="vref" x1="${x(cfg.ref.value)}" x2="${x(cfg.ref.value)}" y1="${T - 6}" y2="${H - 4}"/>
        <text class="vax" x="${x(cfg.ref.value) + 4}" y="${T - 8}">${E(cfg.ref.label)}</text>`;
      vals.forEach((v, i) => {
        const y0 = T + i * (rowH + labelRow) + labelRow, bh = 18, x0 = Math.min(x(0), x(v)), w = Math.max(1, Math.abs(x(v) - x(0)));
        const color = cfg.colors[i % cfg.colors.length], faded = st.sig && !st.sig[i];
        const lab = narrow ? `<text class="vcat" x="0" y="${y0 - 4}">${E(cfg.categories[i])}</text>`
                           : `<text class="vcat" x="${L0 - 10}" y="${y0 + bh/2 + 4}" text-anchor="end">${E(cfg.categories[i])}</text>`;
        const vx = v >= 0 ? x(v) + 6 : x(v) - 6;
        g += `${lab}<rect class="vbar" data-i="${i}" x="${x0}" y="${y0}" width="${w}" height="${bh}" rx="3"
               style="fill:${color};opacity:${faded ? .3 : 1}"/>
              <text class="vval" x="${vx}" y="${y0 + bh/2 + 4}" text-anchor="${v >= 0 ? "start" : "end"}">${E(cfg.fmt(v))}${cfg.showExtra && st.extra ? " · " + E(st.extra[i]) : ""}</text>
              <rect class="vhit" data-i="${i}" x="0" y="${y0 - 6}" width="${W}" height="${bh + 12}"/>`;
      });
      plot.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${g}</svg>`;
      plot.querySelectorAll(".vhit").forEach(r => {
        r.addEventListener("mousemove", ev => {
          const i = +r.dataset.i, s = cfg.states[keyOf()];
          tip.hidden = false;
          tip.innerHTML = `<b>${E(cfg.categories[i])}</b><br>${E(cfg.fmt(s.values[i]))}${s.extra ? " · " + E(s.extra[i]) : ""}${s.sig && !s.sig[i] ? "<br><i>not significant</i>" : ""}`;
          const b = plot.getBoundingClientRect();
          tip.style.left = Math.min(ev.clientX - b.left + 12, b.width - tip.offsetWidth) + "px";
          tip.style.top = (ev.clientY - b.top + plot.offsetTop - 40) + "px";
        });
        r.addEventListener("mouseleave", () => tip.hidden = true);
      });
    }
    function go(ms){
      const st = cfg.states[keyOf()], from = cur.slice(), to = st.values;
      note.innerHTML = st.note || "";
      tween(ms, k => { cur = from.map((f, i) => f + (to[i] - f) * k); draw(cur); });
    }
    root.querySelectorAll(".vctl button").forEach(b => b.addEventListener("click", () => {
      state[b.dataset.k] = b.dataset.v;
      root.querySelectorAll(`.vctl button[data-k="${b.dataset.k}"]`).forEach(x => x.classList.toggle("on", x === b));
      go(700);
    }));
    draw(cur); note.innerHTML = cfg.states[keyOf()].note || "";
    root._intro = () => { if (!shown){ shown = true; go(1100); } };
    root._redraw = () => draw(cur);
  }

  // ---------------- lines revealed over time, with a scrubber ----------------
  function lines(root, cfg){
    const S = cfg.series.map(s => ({...s, pts: s.pts || s.ys.map((y, k) => ({x: cfg.yearsFrom + k, y,
      label: k === 0 ? "Start of " + cfg.yearsFrom : "End of " + (cfg.yearsFrom + k - 1)}))}));
    const xs = S.flatMap(s => s.pts.map(p => p.x)), ys = S.flatMap(s => s.pts.map(p => p.y));
    const x0 = Math.min(...xs, ...cfg.xTicks.map(t => t[0])), x1 = Math.max(...xs, ...cfg.xTicks.map(t => t[0]));
    const yt = cfg.yTicks, ylo = Math.min(yt[0], ...ys), yhi = Math.max(yt[yt.length - 1], ...ys);
    const fy = cfg.log ? Math.log : (v => v);
    let p = 0, playing = false;

    root.innerHTML = `<div class="vhead"><div class="vtitle">${E(cfg.title)}</div>
        <div class="vctl"><button class="vplay">▶ Play</button><input class="vscrub" type="range" min="0" max="1000" value="0" aria-label="Time"></div></div>
      <div class="vlegend">${S.map(s => `<span><i style="background:${s.color}"></i>${E(s.name)}</span>`).join("")}</div>
      <div class="vplot"></div><div class="vtip" hidden></div>`;
    const plot = root.querySelector(".vplot"), tip = root.querySelector(".vtip"),
          btn = root.querySelector(".vplay"), scrub = root.querySelector(".vscrub");

    function draw(){
      const W = plot.clientWidth || 600, H = 240, L = 54, R = cfg.endLabels ? 140 : 64, T = 10, B = 26;
      const X = v => L + (W - L - R) * (v - x0) / ((x1 - x0) || 1);
      const Y = v => T + (H - T - B) * (1 - (fy(v) - fy(ylo)) / ((fy(yhi) - fy(ylo)) || 1));
      const cut = x0 + (x1 - x0) * p;
      let g = "";
      yt.forEach(v => g += `<line class="vgrid" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text class="vax" x="${L - 8}" y="${Y(v) + 4}" text-anchor="end">${E(cfg.yFmt(v))}</text>`);
      cfg.xTicks.forEach(([v, l]) => g += `<text class="vax" x="${X(v)}" y="${H - 6}" text-anchor="middle">${E(l)}</text>`);
      const ends = [];
      S.forEach(s => {
        const vis = []; let last = null;
        s.pts.forEach((q, i) => {
          if (q.x <= cut){ vis.push(q); last = q; }
          else if (i > 0 && s.pts[i - 1].x <= cut && !cfg.dots){
            const a = s.pts[i - 1], t = (cut - a.x) / (q.x - a.x);
            const yv = cfg.log ? Math.exp(Math.log(a.y) + t * (Math.log(q.y) - Math.log(a.y))) : a.y + t * (q.y - a.y);
            vis.push({x: cut, y: yv, interp: true}); last = vis[vis.length - 1];
          }
        });
        if (vis.length > 1) g += `<polyline class="vline" style="stroke:${s.color}" points="${vis.map(q => X(q.x).toFixed(1) + "," + Y(q.y).toFixed(1)).join(" ")}"/>`;
        if (cfg.dots) vis.forEach(q => g += `<circle class="vdot" cx="${X(q.x)}" cy="${Y(q.y)}" r="5" style="fill:${s.color}"/>`);
        if (last) ends.push({s, q: last});
      });
      // end labels / current values, nudged apart
      ends.sort((a, b) => Y(a.q.y) - Y(b.q.y));
      let prev = -99;
      ends.forEach(e => {
        let yy = Y(e.q.y); if (yy - prev < 14) yy = prev + 14; prev = yy;
        const val = cfg.yFmt(+e.q.y.toFixed(e.q.y < 10 ? 2 : 0));
        if (cfg.endLabels) g += `<text class="velab" x="${X(e.q.x) + 8}" y="${yy + 4}"><tspan style="fill:${e.s.color};font-weight:500">${E(val)}</tspan> ${E(e.s.short || e.s.name)}</text>`;
        else g += `<text class="velab" x="${X(e.q.x) + 9}" y="${yy + 4}" style="fill:${e.s.color};font-weight:500">${E(val)}</text>`;
      });
      g += `<line class="vcross" x1="0" x2="0" y1="${T}" y2="${H - B}" visibility="hidden"/>
            <rect class="vhit" x="${L}" y="0" width="${W - L - R}" height="${H}"/>`;
      plot.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${g}</svg>`;

      const hit = plot.querySelector(".vhit"), cross = plot.querySelector(".vcross");
      hit.addEventListener("mousemove", ev => {
        const b = plot.getBoundingClientRect(), mx = ev.clientX - b.left;
        const xv = x0 + (mx - L) / (W - L - R) * (x1 - x0);
        if (xv > cut + 1e-9){ tip.hidden = true; cross.setAttribute("visibility", "hidden"); return; }
        let best = null;
        S.forEach(s => s.pts.forEach(q => { if (q.x <= cut && (!best || Math.abs(q.x - xv) < Math.abs(best.q.x - xv))) best = {s, q}; }));
        if (!best) return;
        const same = S.map(s => ({s, q: s.pts.find(q => q.x === best.q.x)})).filter(o => o.q);
        cross.setAttribute("x1", X(best.q.x)); cross.setAttribute("x2", X(best.q.x)); cross.setAttribute("visibility", "visible");
        tip.hidden = false;
        tip.innerHTML = same.length > 1
          ? `<b>${E(best.q.label)}</b>` + same.map(o => `<br><span style="color:${o.s.color}">●</span> ${E(o.s.name)}: ${E(cfg.yFmt(o.q.y))}`).join("")
          : `<span style="color:${best.s.color}">●</span> <b>${E(best.s.name)}: ${E(cfg.yFmt(best.q.y))}</b><br>${E(best.q.label)}`;
        tip.style.left = Math.min(Math.max(X(best.q.x) - tip.offsetWidth / 2, 0), b.width - tip.offsetWidth) + "px";
        tip.style.top = (plot.offsetTop - 8) + "px";
      });
      hit.addEventListener("mouseleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
    }
    function play(){
      if (playing) return; playing = true; btn.textContent = "❚❚";
      const start = p >= 1 ? 0 : p;
      tween(4200 * (1 - start), k => { p = start + (1 - start) * k; scrub.value = Math.round(p * 1000); draw(); },
            () => { playing = false; btn.textContent = "↻ Replay"; });
    }
    btn.addEventListener("click", () => { if (!playing){ if (p >= 1) p = 0; play(); } });
    scrub.addEventListener("input", () => { p = scrub.value / 1000; btn.textContent = p >= 1 ? "↻ Replay" : "▶ Play"; draw(); });
    draw();
    root._intro = () => { if (p === 0) play(); };
    root._redraw = draw;
  }

  window.renderFinding = function(el, f){
    el.innerHTML = `<div class="kstats">${f.stats.map(s => `<div class="kstat"><b>${E(s.v)}</b><span>${E(s.l)}</span></div>`).join("")}</div>
      <div class="vchart"></div>
      <p class="vexplain">${f.chart.explain || ""} <span class="vsrc">Source: ${E(f.chart.source)}.</span></p>`;
    const c = el.querySelector(".vchart");
    (f.chart.type === "lines" ? lines : bars)(c, f.chart);
    if ("IntersectionObserver" in window){
      const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting){ c._intro && c._intro(); io.disconnect(); } }), {threshold: 0.4});
      io.observe(c);
    } else c._intro && c._intro();
    let t; window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => c._redraw && c._redraw(), 150); });
  };
})();
