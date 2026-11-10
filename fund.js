// Long/short portfolio on the Portfolio page. Reads fund.json (the book) and fund_nav.json (computed by the updater).
(function(){
  const CSS = `
  #portfolio .fhead{margin:-4px 0 18px}
  #portfolio .fhead h3{font-weight:500;font-size:24px;margin:0 0 6px}
  #portfolio .fhead .tagline{font-family:var(--mono);font-size:11px;color:var(--muted);border:1px solid var(--faint);border-radius:4px;padding:1px 7px;margin-left:10px;vertical-align:4px}
  #portfolio .facts{display:flex;flex-wrap:wrap;gap:4px 22px;font-family:var(--mono);font-size:12px;color:var(--muted)}
  #portfolio .facts b{font-weight:500;color:var(--ink)}
  #portfolio .prose p{max-width:760px;font-size:17px}
  #portfolio .sublab{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:4px 0 8px}
  #portfolio .tbl.slim{width:auto;margin-left:0;transform:none}
  #portfolio .twocol{display:grid;grid-template-columns:1fr 1fr;gap:22px;align-items:start}
  #portfolio .stats.three{grid-template-columns:repeat(3,1fr);margin-top:14px}
  #portfolio .ok{color:var(--up)} #portfolio .warn{color:#b7791f} #portfolio .bad{color:var(--down)}
  #portfolio tr.pairrow td{background:var(--bg);font-family:var(--serif);font-size:15px;white-space:normal;padding:11px 10px 7px}
  #portfolio tr.pairrow b{font-family:var(--mono);font-weight:500;font-size:12px;margin-right:8px}
  #portfolio tr.pairrow .pwhy{display:block;color:var(--muted);font-size:14px;margin-top:1px;max-width:820px}
  #portfolio tr.pairrow .ppnl{float:right;font-family:var(--mono);font-size:13px}
  #portfolio tr.pos{cursor:pointer}
  #portfolio tr.pos:hover td{background:color-mix(in srgb, var(--faint) 40%, transparent)}
  #portfolio tr.pos.closed td{opacity:.55}
  #portfolio .hedgetag{font-size:11px;padding:1px 7px;border-radius:4px;background:var(--faint);color:var(--ink)}
  #portfolio .hedgetag.h{background:var(--ink);color:var(--bg)}
  #portfolio .fut{font-size:10px;border:1px solid var(--accent);color:var(--accent);border-radius:3px;padding:0 4px;margin-left:5px;vertical-align:1px}
  #portfolio .stophit{color:var(--down);font-weight:500}
  #portfolio .attr{display:grid;grid-template-columns:minmax(120px,190px) 1fr 66px;gap:7px 10px;align-items:center;font-family:var(--mono);font-size:12.5px}
  #portfolio .attr .lab{font-family:var(--serif);font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #portfolio .attr .track{position:relative;height:14px;background:linear-gradient(var(--muted),var(--muted)) center/1px 100% no-repeat}
  #portfolio .attr .bar{position:absolute;top:2px;height:10px;border-radius:2px}
  #portfolio .attr .v{text-align:right}
  #portfolio table.risk tr.tot td{font-weight:500;border-top:1px solid var(--muted)}
  #portfolio #fundLimits td:nth-child(2),#portfolio #fundLimits th:nth-child(2){text-align:left;padding-left:18px}
  #portfolio .chart .line{stroke:var(--accent)} #portfolio .chart .bench{stroke:var(--bench)}
  @media (max-width:700px){ #portfolio .twocol{grid-template-columns:1fr} #portfolio .stats.three{grid-template-columns:1fr} }`;
  const st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);

  let F = null, N = null, open = {};
  const bp = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(Math.round(v * 1e4)) + " bp";
  const x2 = v => v == null ? "–" : v.toFixed(2) + "×";
  const sgn = v => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
  const p1 = v => v == null ? "–" : (v * 100).toFixed(1) + "%";
  const sp = (v, d = 2) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%";
  const CUR2 = {USD: "$", EUR: "€", GBP: "", CHF: "CHF ", KRW: "₩"};
  const price = (p, v) => v == null ? "–" : (CUR2[p.currency] ?? "") + Number(v).toLocaleString("en-US", {maximumFractionDigits: v >= 1000 ? 0 : 2, minimumFractionDigits: v >= 1000 ? 0 : 2}) + (p.unit == 100 ? "p" : "");
  const REG = {US: "United States", EU: "Eurozone", UK: "United Kingdom", CH: "Switzerland", KR: "South Korea", HEDGE: "Index futures"};

  async function load(){
    try { F = await getJSON("data/fund.json"); } catch(e){ return; }
    try { N = await getJSON("data/fund_nav.json"); } catch(e){ N = null; }
    render();
  }

  function stats(series){
    const pts = series.slice(1).filter(d => d[0].endsWith("23:59"));
    if (pts.length < 2) return null;
    const v = [1 + series[0][1], ...pts.map(d => 1 + d[1])], c = [1 + series[0][2], ...pts.map(d => 1 + d[2])];
    const r = v.slice(1).map((x, i) => x / v[i] - 1), rc = c.slice(1).map((x, i) => x / c[i] - 1);
    const ex = r.map((x, i) => x - rc[i]), n = ex.length, m = ex.reduce((a, b) => a + b, 0) / n;
    const sd = Math.sqrt(ex.reduce((a, b) => a + (b - m) ** 2, 0) / (n - 1));
    const mr = r.reduce((a, b) => a + b, 0) / n, vol = Math.sqrt(r.reduce((a, b) => a + (b - mr) ** 2, 0) / (n - 1)) * Math.sqrt(252);
    return {days: n, sharpe: n >= 20 && sd ? m / sd * Math.sqrt(252) : null, vol: n >= 20 ? vol : null};
  }

  function chart(){
    const box = document.getElementById("fchart"); if (!box || box.offsetParent === null || !F) return;
    box.querySelector("svg")?.remove(); box.querySelector(".empty")?.remove();
    const data = (N && N.series) || [], last = data[data.length - 1];
    if (!last || data.length < 3){
      box.insertAdjacentHTML("afterbegin", `<div class="empty">Inception ${fmtD(F.start)}. NAV history begins after the first trading day.</div>`); return;
    }
    const W = box.clientWidth, H = box.clientHeight, L = 46, R = 70, T = 10, B = 24;
    const vals = data.flatMap(d => [d[1], d[2]]);
    let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const raw = ((hi - lo) || 0.01) / 4, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(k => k * mag).find(s => s >= raw);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const t0 = +new Date(data[0][0]), t1 = +new Date(last[0]);
    const x = d => L + (W - L - R) * ((+new Date(d) - t0) / ((t1 - t0) || 1));
    const y = v => T + (H - T - B) * (1 - (v - lo) / ((hi - lo) || 1));
    let g = "";
    for (let v = lo; v <= hi + 1e-9; v += step)
      g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="ax" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${pct(v, step < 0.01 ? 1 : 0)}</text>`;
    [0, data.length - 1].forEach((i, k) => g += `<text class="ax" x="${x(data[i][0])}" y="${H - 6}" text-anchor="${k ? "end" : "start"}">${new Date(data[i][0]).toLocaleDateString("en-GB", {day: "numeric", month: "short", year: "2-digit"})}</text>`);
    const line = col => data.map(d => `${x(d[0]).toFixed(1)},${y(d[col]).toFixed(1)}`).join(" ");
    let yf = y(last[1]), yc = y(last[2]);
    if (Math.abs(yf - yc) < 14){ const m = (yf + yc) / 2, u = yf <= yc ? -1 : 1; yf = m + u * 7; yc = m - u * 7; }
    box.insertAdjacentHTML("afterbegin", `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${g}
      <line class="zero" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>
      <polyline class="bench" points="${line(2)}"/><polyline class="line" points="${line(1)}"/>
      <text class="elab" x="${W - R + 8}" y="${yf + 4}" style="fill:var(--accent)">${pct(last[1], 2)}</text>
      <text class="elab" x="${W - R + 8}" y="${yc + 4}">Cash</text></svg>`);
  }

  function render(){
    const S = N ? stats(N.series) : null, E = (N && N.exposure) || {}, R = F.rules || {};
    const live = {}; (N ? N.positions : []).forEach(r => live[r.id] = r);
    const last = N && N.series.length ? N.series[N.series.length - 1] : [null, 0, 0];
    const wNow = p => live[p.id] && live[p.id].weightNow != null ? live[p.id].weightNow : (p.exitDate ? 0 : p.weight);
    const openP = F.positions.filter(p => !(p.exitDate && p.exit != null));

    // ----- header -----
    $("#fundHead").innerHTML = `<h3>${esc(F.name)}<span class="tagline">${esc(F.status)}</span></h3>
      <div class="facts">${(F.facts || []).map(([k, v]) => `<span>${esc(k)} <b>${esc(v)}</b></span>`).join("")}</div>`;

    // ----- key figures -----
    const mdd = N ? N.maxDrawdown : null;
    $("#fundStats").innerHTML = [
      ["Return since inception", `<b class="${cls(last[1], 2)}">${pct(last[1], 2)}</b><small>net of costs</small>`],
      ["Excess return vs cash", `<b class="${cls(last[1] - last[2], 2)}">${pct(last[1] - last[2], 2)}</b><small>cash ${pct(last[2], 2)}</small>`],
      ["Volatility (ann.)", `<b>${S && S.vol != null ? p1(S.vol) : "–"}</b><small>${S && S.vol != null ? "daily returns" : "from 20 trading days"}</small>`],
      ["Sharpe ratio", `<b>${S && S.sharpe != null ? S.sharpe.toFixed(2) : "–"}</b><small>${S && S.sharpe != null ? "excess over cash" : "from 20 trading days"}</small>`],
      ["Max drawdown", `<b class="${cls(mdd || 0, 1)}">${mdd != null ? pct(mdd, 1) : "–"}</b><small>current ${N ? pct(N.drawdown, 1) : "–"}</small>`],
      ["Gross leverage", `<b>${x2(E.gross)}</b><small>long ${x2(E.long)} · short ${x2(E.short)}</small>`],
      ["Net exposure", `<b>${E.net != null ? sp(E.net, 0) : "–"}</b><small>of NAV</small>`],
      ["Net beta", `<b>${sgn(E.beta)}</b><small>target ±${(R.betaBand || .1).toFixed(2)}</small>`],
    ].map(([l, v]) => `<div class="stat"><span>${l}</span>${v}</div>`).join("");
    $("#fundNote").textContent = N ? `As of ${new Date(N.updated).toLocaleString("en-GB", {day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"})}. Net of costs.` : `Inception ${fmtD(F.start)}.`;
    chart();

    // ----- positions -----
    const order = Object.keys(F.pairs), attr = (N && N.attribution) || {};
    let h = `<thead><tr><th>Position</th><th>Side</th><th class="num">% NAV</th><th>Hedge</th><th class="num">Entry</th><th class="num">Last</th><th class="num">Return</th><th class="num">Contrib.</th><th class="num">Stop</th><th></th></tr></thead><tbody>`;
    order.forEach(k => {
      const ps = F.positions.filter(p => p.pair === k); if (!ps.length) return;
      const P = F.pairs[k];
      h += `<tr class="pairrow"><td colspan="10"><span class="ppnl ${cls(attr[k] || 0, 2)}">${N ? bp(attr[k] || 0) : ""}</span><b>${k === "H" ? "HEDGE" : esc(k)}</b>${esc(P.title)}<span class="pwhy">${esc(P.why)}</span></td></tr>`;
      ps.forEach(p => {
        const r = live[p.id] || {}, closed = p.exitDate && p.exit != null, fut = p.type === "future";
        const hedgeCell = fut ? `<span class="hedgetag h">HEDGE</span>` : `<span class="hedgetag">${esc(p.hedge.replace(/^Hedged – /, ""))}</span>`;
        const stop = fut ? `<span class="co">–</span>` : r.stop != null ? `${price(p, r.stop)}<span class="co ${r.stopHit ? "stophit" : ""}">${r.stopHit ? "STOP HIT" : r.toStop != null ? p1(r.toStop) + " away" : ""}</span>` : "–";
        h += `<tr class="pos ${closed ? "closed" : ""}" data-id="${esc(p.id)}">
          <td><span class="tick">${esc(p.ticker)}</span>${fut ? `<span class="fut">FUTURE</span>` : ""}<span class="co">${esc(p.name)}${p.exchange ? " · " + esc(p.exchange) : ""}</span></td>
          <td><span class="pill ${p.side}">${p.side.toUpperCase()}</span></td>
          <td class="num">${p1(closed ? p.weight : wNow(p))}<span class="co">at entry ${p1(p.weight)}</span></td>
          <td>${hedgeCell}</td>
          <td class="num">${price(p, p.entry)}<span class="co">${fmtDs(p.entryDate)}</span></td>
          <td class="num">${closed ? price(p, p.exit) + `<span class="co">closed ${fmtDs(p.exitDate)}</span>` : price(p, r.last)}</td>
          <td class="num ${cls(r.ret || 0)}">${r.ret != null ? pct(r.ret) : "–"}</td>
          <td class="num ${cls(r.contrib || 0, 2)}">${r.contrib != null ? bp(r.contrib) : "–"}</td>
          <td class="num">${stop}</td>
          <td class="notebtn">${open[p.id] ? "▴" : "▾"}</td></tr>`;
        if (open[p.id]) h += `<tr class="note-row"><td colspan="10"><p><b>${fut ? "Role" : "Thesis"}.</b> ${esc(p.thesis)}</p><p><b>${fut ? "Limitations" : "Key risks"}.</b> ${esc(p.wrongIf)}</p></td></tr>`;
      });
    });
    $("#fundBook").innerHTML = h + "</tbody>";
    document.querySelectorAll("#fundBook tr.pos").forEach(tr => tr.addEventListener("click", () => { open[tr.dataset.id] = !open[tr.dataset.id]; render(); }));
    $("#fundBookNote").textContent = "Contribution in basis points of NAV. Prices in local currency; UK in pence.";

    // ----- exposure by region -----
    const regs = {};
    openP.forEach(p => {
      const k = p.type === "future" ? "HEDGE" : p.region, s = p.side === "long" ? 1 : -1, w = wNow(p);
      regs[k] = regs[k] || {l: 0, s: 0, b: 0};
      if (s > 0) regs[k].l += w; else regs[k].s += w;
      regs[k].b += s * w * (p.beta ?? 1);
    });
    const rk = ["US", "EU", "UK", "CH", "KR", "HEDGE"].filter(k => regs[k]);
    const tot = rk.reduce((a, k) => ({l: a.l + regs[k].l, s: a.s + regs[k].s, b: a.b + regs[k].b}), {l: 0, s: 0, b: 0});
    $("#fundRegion").innerHTML = `<tr><th></th><th>Long</th><th>Short</th><th>Net</th><th>Beta-adj.</th></tr>` +
      rk.map(k => `<tr><td>${REG[k]}</td><td>${p1(regs[k].l)}</td><td>${p1(regs[k].s)}</td><td>${sp(regs[k].l - regs[k].s, 1)}</td><td>${sp(regs[k].b, 1)}</td></tr>`).join("") +
      `<tr class="tot"><td>Total</td><td>${p1(tot.l)}</td><td>${p1(tot.s)}</td><td>${sp(tot.l - tot.s, 1)}</td><td>${sp(tot.b, 1)}</td></tr>`;

    // ----- contribution -----
    const items = [...order.map(k => [k === "H" ? "Index hedge" : `${k} · ${F.pairs[k].title}`, attr[k] || 0]), ["Costs", attr.Costs || 0]];
    const mx = Math.max(0.0005, ...items.map(i => Math.abs(i[1])));
    $("#fundAttr").innerHTML = items.map(([l, v]) => `<div class="lab" title="${esc(l)}">${esc(l)}</div>
      <div class="track"><div class="bar" style="background:${v >= 0 ? "var(--up)" : "var(--down)"};${v >= 0 ? `left:50%;width:${v / mx * 50}%` : `right:50%;width:${-v / mx * 50}%`}"></div></div>
      <div class="v ${cls(v, 2)}">${bp(v)}</div>`).join("");

    // ----- hedge effectiveness -----
    const H = N && N.hedge;
    $("#hedgeLive").innerHTML = [
      ["European beta, unhedged", sgn(E.euBeta), "EU, UK and Swiss positions"],
      ["Futures hedge", sgn(E.hedgeBeta), E.euBeta ? `hedge ratio ${Math.round(-E.hedgeBeta / E.euBeta * 100)}%` : ""],
      ["Hedge correlation", H ? H.corr.toFixed(2) : "–", H ? `daily P&L vs European book, ${H.days} days` : "reported from 10 trading days"],
    ].map(([l, v, s]) => `<div class="stat"><span>${l}</span><b>${v}</b><small>${esc(s)}</small></div>`).join("");
    $("#hedgeLiveNote").textContent = "";

    // ----- leverage & costs -----
    const big = Math.max(0, ...openP.filter(p => p.type !== "future").map(wNow));
    $("#fundLev").innerHTML = [
      ["Gross exposure", x2(E.gross)], ["Long exposure", x2(E.long)], ["Short exposure (incl. futures)", x2(E.short)],
      ["Net exposure", E.net != null ? sp(E.net, 1) : "–"], ["Net beta", sgn(E.beta)], ["Largest single position", p1(big)],
      ["Positions (long / short)", `${openP.filter(p => p.side === "long").length} / ${openP.filter(p => p.side === "short" && p.type !== "future").length} + futures`],
    ].map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
    const costTot = (F.costs || []).reduce((a, c) => a + c[1], 0), cash = F.cashRate || 0.025;
    $("#fundCosts").innerHTML = (F.costs || []).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="${v < 0 ? "down" : "up"}">${sp(v)}</td></tr>`).join("") +
      `<tr class="tot"><td>Total running cost</td><td>${sp(costTot)}</td></tr>
       <tr><td>Return on cash (opportunity cost)</td><td>${sp(cash)}</td></tr>
       <tr class="tot"><td>Hurdle: gross alpha needed to beat cash</td><td>${sp(cash - costTot)}</td></tr>`;
    $("#fundCostNote").textContent = F.financing || "";

    // ----- risk limits -----
    const stopsHit = (N ? N.positions : []).filter(r => r.stopHit).length, dd = N ? N.drawdown : 0;
    const lim = [
      ["Gross leverage", `≤ ${x2(R.grossMax || 3)}`, x2(E.gross), E.gross == null || E.gross <= (R.grossMax || 3)],
      ["Net beta", `within ±${(R.betaBand || .1).toFixed(2)}`, sgn(E.beta), E.beta == null || Math.abs(E.beta) <= (R.betaBand || .1)],
      ["Single long", `≤ ${p1(R.singleLongMax || .2)} NAV`, p1(Math.max(0, ...openP.filter(p => p.side === "long").map(wNow))), Math.max(0, ...openP.filter(p => p.side === "long").map(wNow)) <= (R.singleLongMax || .2) + .02],
      ["Single short", `≤ ${p1(R.singleShortMax || .12)} NAV`, p1(Math.max(0, ...openP.filter(p => p.side === "short" && p.type !== "future").map(wNow))), Math.max(0, ...openP.filter(p => p.side === "short" && p.type !== "future").map(wNow)) <= (R.singleShortMax || .12) + .02],
      ["Stop-loss per position", `${((R.maxLossLong || .015) * 100).toFixed(2)}% NAV long · ${((R.maxLossShort || .0125) * 100).toFixed(2)}% short`, `${stopsHit} hit`, stopsHit === 0],
      ["Drawdown from peak", `${pct(R.ddHalve || -.05, 1)}: halve gross · ${pct(R.ddClose || -.075, 1)}: close`, pct(dd, 1), dd > (R.ddHalve || -.05)],
    ];
    $("#fundLimits").innerHTML = `<tr><th>Limit</th><th>Rule</th><th>Current</th><th>Status</th></tr>` +
      lim.map(([a, b, c, ok]) => `<tr><td>${a}</td><td>${b}</td><td>${c}</td><td class="${ok ? "ok" : "bad"}">${ok ? "Within" : "Breach"}</td></tr>`).join("");
  }

  window.drawFund = () => { if (F) chart(); };
  let t; window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(window.drawFund, 120); });
  load(); setInterval(load, 5 * 60 * 1000);
})();
