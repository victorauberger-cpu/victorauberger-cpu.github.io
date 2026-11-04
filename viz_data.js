// Key findings shown on the Research page. Every number comes from the paper's own tables or text.
// Keys match the start of each paper's title.
const FINDINGS = {

  "Betting on Everything": {
    stats: [
      {v: "$0.79bn → $40bn", l: "Kalshi's valuation, autumn 2024 to October 2026"},
      {v: "79%", l: "of Kalshi and Polymarket volume in July 2026 was sports"},
      {v: "8M → 99bn", l: "Kalshi contracts traded, 2021 vs 2026 (to 27 Oct)"},
    ],
    chart: {
      type: "lines", title: "Valuation at each funding round ($bn, log scale)",
      log: true, yTicks: [0.5, 1, 2, 5, 10, 20, 50], yFmt: v => "$" + v + "bn",
      xTicks: [[2024.75, "Oct 24"], [2025.25, "Apr 25"], [2025.75, "Oct 25"], [2026.25, "Apr 26"], [2026.79, "Oct 26"]],
      xFmt: x => x.label, play: true, dots: true,
      series: [
        {name: "Kalshi", color: "var(--s1)", pts: [
          {x: 2024.79, y: 0.79, label: "Autumn 2024"}, {x: 2025.42, y: 2, label: "June 2025 · $185m from Paradigm"},
          {x: 2025.79, y: 5, label: "October 2025 · $300m, Sequoia & a16z"}, {x: 2025.92, y: 11, label: "December 2025 · $1bn, Paradigm"},
          {x: 2026.17, y: 22, label: "March 2026 · $1bn, Coatue"}, {x: 2026.79, y: 40, label: "October 2026 · $1bn, Wellington & Sequoia"}]},
        {name: "Polymarket", color: "var(--s2)", pts: [
          {x: 2025.42, y: 1, label: "June 2025 · about $200m (reported)"}, {x: 2025.79, y: 8, label: "October 2025 · ICE's pre-money valuation"},
          {x: 2026.58, y: 21, label: "August 2026 · $1bn, 1789 Capital"}]},
      ],
      source: "Table 2 and Figure 3",
    },
  },

  "The House Edge Without a House": {
    stats: [
      {v: "−84%", l: "return for buyers of 1–10¢ long shots at the last trade before close"},
      {v: "+1.89% vs +0.32%", l: "makers vs takers selling those long shots on Kalshi"},
      {v: "−70%", l: "per dollar for buyers of one-day crash insurance"},
    ],
    chart: {
      type: "bars", title: "A 1–10¢ long shot on Kalshi: what buyers pay vs what it pays back",
      categories: ["Average price paid", "Paid back on average"], unit: "¢",
      fmt: v => v.toFixed(2) + "¢", colors: ["var(--s2)", "var(--s1)"],
      controls: [{key: "t", label: "Bought", options: [["7d", "7 days before close"], ["24h", "24 hours before"], ["1h", "1 hour before"], ["last", "At the last trade"]], value: "24h"}],
      states: {
        "7d":   {values: [2.98, 1.99], note: "Won 1.99% of the time · buyers' return before fees: <b class='down'>−43.4%</b> · 7,202 contracts"},
        "24h":  {values: [3.55, 2.94], note: "Won 2.94% of the time · buyers' return before fees: <b class='down'>−26.9%</b> · 29,723 contracts"},
        "1h":   {values: [2.36, 1.37], note: "Won 1.37% of the time · buyers' return before fees: <b class='down'>−58.7%</b> · 60,522 contracts"},
        "last": {values: [1.85, 0.44], note: "Won 0.44% of the time · buyers' return before fees: <b class='down'>−84.2%</b> · 71,774 contracts"},
      },
      explain: "“Paid back on average” is the share of contracts that won, times $1. The gap is what long-shot buyers give up.",
      source: "Table 5 (Kalshi, to November 2025)",
    },
  },

  "Do Volatility-Managed Portfolios": {
    stats: [
      {v: "12.80% → 0.51%", l: "yearly alpha of managed momentum, before vs after 2016"},
      {v: "6 of 6", l: "original alphas reproduced within half a standard error"},
      {v: "0 of 6", l: "factors with a significant alpha out of sample"},
    ],
    chart: {
      type: "bars", title: "Alpha of the volatility-managed factor (% per year)",
      categories: ["Market", "Size", "Value", "Momentum", "Profitability", "Investment"],
      fmt: v => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2) + "%", colors: ["var(--s1)"],
      controls: [
        {key: "p", label: "Period", options: [["pre", "Before 2016"], ["post", "2016–2026"]], value: "pre"},
        {key: "c", label: "Trading costs", options: [["g", "None"], ["10", "10 bps"], ["25", "25 bps"]], value: "g"},
      ],
      states: {
        "pre|g":  {values: [4.88, -0.58, 1.65, 12.80, 2.81, 0.28]},
        "post|g": {values: [1.48, -0.71, -1.11, 0.51, 0.36, -0.81], note: "No alpha is significantly positive after 2016 (127 months)."},
        "pre|10": {values: [3.97, -1.24, 0.83, 11.67, 2.06, -0.40]},
        "post|10":{values: [0.63, -0.93, -1.32, 0.25, 0.16, -1.10], note: "No alpha is significantly positive after 2016 (127 months)."},
        "pre|25": {values: [2.62, -2.23, -0.41, 9.98, 0.94, -1.43]},
        "post|25":{values: [-0.65, -1.26, -1.63, -0.14, -0.13, -1.54], note: "No alpha is significantly positive after 2016 (127 months)."},
      },
      explain: "Switch the period to watch the alphas shrink once the strategy is tested on data it has never seen.",
      source: "Table 7 (pre-2016 alphas with c estimated before January 2016)",
    },
  },

  "Les États doivent-ils": {
    stats: [
      {v: "$226 vs $660", l: "$100 invested in 2008: hedge funds after fees vs the S&P 500"},
      {v: "≈ half", l: "of gross gains taken by managers in fees"},
      {v: "$5,200bn", l: "hedge fund industry net assets"},
    ],
    chart: {
      type: "lines", title: "What $100 invested at the start of 2008 became",
      yTicks: [0, 100, 200, 300, 400, 500, 600, 700], yFmt: v => "$" + v,
      xTicks: [[2008, "2008"], [2012, "2012"], [2016, "2016"], [2020, "2020"], [2024, "2024"], [2026, "2026"]],
      xFmt: x => x.label, play: true, dots: false, endLabels: true,
      series: [
        {name: "S&P 500", color: "var(--s1)", ys: [100, 63.0, 79.7, 91.7, 93.6, 108.6, 143.7, 163.4, 165.7, 185.5, 226.0, 216.1, 284.1, 336.4, 433.0, 354.6, 447.8, 559.9, 660.0]},
        {name: "Hedge funds before fees", short: "before fees", color: "var(--s3)", ys: [100, 82.5, 100.2, 113.8, 109.5, 118.4, 133.6, 140.6, 141.2, 152.5, 171.1, 165.6, 187.6, 218.2, 249.1, 242.4, 266.1, 302.7, 354.6]},
        {name: "Hedge funds after fees", short: "after fees", color: "var(--s2)", ys: [100, 81.0, 97.1, 107.1, 101.5, 107.9, 117.8, 121.3, 119.9, 126.5, 137.3, 130.8, 144.5, 161.6, 178.0, 170.5, 183.3, 201.3, 226.4]},
      ],
      yearsFrom: 2008, // ys[0] = start of 2008, ys[k] = end of year 2007+k
      explain: "Press play or drag the slider. Hedge funds lost less in 2008 and 2022 but never caught up with the index; fees cut their final value from $355 to $226.",
      source: "Tableau 7 (HFRI Fund Weighted Composite; pre-fee returns reconstructed by the author)",
    },
  },

  "Determinants of Market Value": {
    stats: [
      {v: "+158%", l: "higher market value for players joining the Premier League vs the Bundesliga"},
      {v: "+65%", l: "extra paid above Transfermarkt value by Premier League buyers vs the Bundesliga"},
      {v: "795", l: "permanent transfers into the top 5 leagues, 2021–2023"},
    ],
    chart: {
      type: "bars", title: "Effect of each factor, all else equal (%)",
      categories: ["Premier League", "Serie A", "Ligue 1", "La Liga", "Forward", "Midfielder", "Age (+1 year)", "Injury days (+100)"],
      fmt: v => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%", colors: ["var(--s1)"],
      controls: [{key: "m", label: "Explaining", options: [["a", "Market value"], ["b", "Fee paid above market value"]], value: "a"}],
      states: {
        a: {values: [157.8, 0.5, -14.4, -5.2, -40.0, -18.8, -12.2, -3.0], sig: [1, 0, 1, 0, 1, 1, 1, 0],
            note: "Model A4, R² = 0.51. Faded bars are not statistically significant."},
        b: {values: [64.7, 35.3, 32.2, 14.6, 31.3, 7.0, 3.7, 22.1], sig: [1, 1, 1, 0, 1, 0, 1, 1],
            note: "Model B4, R² = 0.10. Faded bars are not statistically significant."},
      },
      explain: "Leagues compared with the Bundesliga, positions with defenders. Effects converted from the log coefficients as e<sup>β</sup> − 1.",
      source: "Tables 8 and 9, column 4",
    },
  },

  "Picking Up Nickels": {
    stats: [
      {v: "−25.7%", l: "portfolio loss from the Russian default to the week after the rescue"},
      {v: "8.9σ", l: "size of the worst day of 1998, in standard deviations"},
      {v: "0.05 → 0.42", l: "average correlation between the trades, before vs during 1998"},
    ],
    chart: {
      type: "bars", title: "Days the loss broke each model's 99% value-at-risk, 1995–2025",
      categories: ["Normal, 5-year (LTCM-style)", "EWMA (RiskMetrics)", "Historical simulation", "GARCH-t filtered HS", "Extreme value (GPD)", "GARCH-EVT (post hoc)"],
      fmt: v => v.toFixed(0) + " days", colors: ["var(--s2)"], showExtra: true, labelRoom: 130, ref: {value: 76.5, label: "Expected: 76.5"},
      controls: [{key: "l", label: "VaR level", options: [["99", "99%"]], value: "99"}],
      states: {
        "99": {values: [173, 172, 108, 94, 99, 86], extra: ["2.26% of days", "2.25% of days", "1.41% of days", "1.23% of days", "1.29% of days", "1.12% of days"],
               note: "A correct model is exceeded on 1% of 7,654 days. The LTCM-style model failed more than twice as often."},
      },
      explain: "Hover a bar for the exceedance rate. Only the GARCH-EVT model, added after the results were seen, passes.",
      source: "Table 8",
    },
  },

  "Forget Miltank": {
    stats: [
      {v: "Level 54", l: "to beat the Elite Four and Lance (his strongest is 50)"},
      {v: "+75%", l: "more experience per minute from the Elite Four rematch than Mt. Silver"},
      {v: "91.5%", l: "win rate against Red at level 84 (81% at 82)"},
    ],
    chart: {
      type: "bars", title: "Levels above (+) or below (−) the boss's strongest Pokémon, at a 90%+ win rate",
      categories: ["Whitney (19)", "Clair (41)", "Lance (50)", "Blue (60)"],
      fmt: v => { const r = Math.round(v); return (r > 0 ? "+" : r < 0 ? "−" : "±") + Math.abs(r); }, colors: ["var(--s1)"], showExtra: true, labelRoom: 130,
      controls: [{key: "t", label: "Team", options: [["fer", "Feraligatr"], ["typ", "Typhlosion"], ["meg", "Meganium"], ["noi", "Feraligatr, no items"]], value: "fer"}],
      states: {
        fer: {values: [-1, -3, 4, -3], extra: ["Lv 18 · 92%", "Lv 38 · 90%", "Lv 54 · 90%", "Lv 57 · 91%"]},
        typ: {values: [1, -3, 4, -4], extra: ["Lv 20 · 99%", "Lv 38 · 93%", "Lv 54 · 94%", "Lv 56 · 94%"]},
        meg: {values: [0, 1, 5, 0], extra: ["Lv 19 · 98%", "Lv 42 · 91%", "Lv 55 · 90%", "Lv 60 · 97%"]},
        noi: {values: [-1, -1, 7, 0], extra: ["Lv 18 · 91%", "Lv 40 · 99%", "Lv 57 · 100%", "Lv 60 · 94%"]},
      },
      explain: "Below zero means the team wins while under the boss's level. The Elite Four is the one wall every team must train for.",
      source: "Table 6 (HeartGold, 400 battles per level)",
    },
  },
};
