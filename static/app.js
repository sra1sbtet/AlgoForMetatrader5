const state = {
  symbol: document.querySelector("#symbol").value,
  timeframe: document.querySelector("#timeframe").value,
};

const $ = (selector) => document.querySelector(selector);

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.message || "Request failed");
  }
  return body;
}

function tradePayload(side) {
  return {
    symbol: $("#symbol").value.trim().toUpperCase(),
    side,
    volume: Number($("#volume").value || 0.01),
  };
}

function strategyPayload() {
  return {
    symbol: $("#symbol").value.trim().toUpperCase(),
    timeframe: $("#timeframe").value,
    volume: Number($("#volume").value || 0.01),
    fast_ema: Number($("#fastEma").value || 9),
    slow_ema: Number($("#slowEma").value || 21),
    poll_seconds: Number($("#pollSeconds").value || 10),
    trade_enabled: $("#tradeEnabled").checked,
  };
}

function connectPayload() {
  return {
    login: $("#mt5Login").value.trim(),
    password: $("#mt5Password").value,
    server: $("#mt5Server").value.trim(),
  };
}

function setConnection(status) {
  const account = status.mt5.account;
  $("#connectionText").textContent = status.mt5.connected
    ? `MT5 online${account ? ` | ${account.login} | ${account.server}` : ""}`
    : "MT5 offline";
}

function renderTick(data) {
  if (!data) return;
  $("#bid").textContent = Number(data.bid || 0).toFixed(5);
  $("#ask").textContent = Number(data.ask || 0).toFixed(5);
  $("#spread").textContent = Number((data.ask || 0) - (data.bid || 0)).toFixed(5);
}

function renderPositions(positions) {
  const body = $("#positionsBody");
  body.innerHTML = "";
  if (!positions || positions.length === 0) {
    body.innerHTML = '<tr><td colspan="6">No open positions</td></tr>';
    return;
  }

  for (const position of positions) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${position.ticket}</td>
      <td>${position.symbol}</td>
      <td>${position.type === 0 ? "BUY" : "SELL"}</td>
      <td>${position.volume}</td>
      <td>${Number(position.profit || 0).toFixed(2)}</td>
      <td><button class="secondary" data-close="${position.ticket}">Close</button></td>
    `;
    body.appendChild(row);
  }
}

function renderWatchlist(symbols) {
  const body = $("#watchlistBody");
  body.innerHTML = "";
  if (!symbols || symbols.length === 0) {
    body.innerHTML = '<tr><td colspan="3">No saved symbols</td></tr>';
    return;
  }

  for (const item of symbols) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><button class="link-button" data-load-symbol="${item.symbol}" data-load-timeframe="${item.timeframe}">${item.symbol}</button></td>
      <td>${item.timeframe}</td>
      <td><button class="secondary" data-delete-watch="${item.id}">Remove</button></td>
    `;
    body.appendChild(row);
  }
}

function renderSignals(signals) {
  const body = $("#signalsBody");
  body.innerHTML = "";
  $("#signalsCount").textContent = String((signals || []).length);
  if (!signals || signals.length === 0) {
    body.innerHTML = '<tr><td colspan="5">No saved signals</td></tr>';
    return;
  }

  for (const item of signals.slice(0, 20)) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${item.signal_time.replace("T", " ")}</td>
      <td>${item.symbol}</td>
      <td>${item.timeframe}</td>
      <td>${item.signal}</td>
      <td>${item.price === null ? "-" : Number(item.price).toFixed(5)}</td>
    `;
    body.appendChild(row);
  }
}

function renderOrderHistory(orders) {
  const body = $("#ordersBody");
  body.innerHTML = "";
  $("#ordersCount").textContent = String((orders || []).length);
  if (!orders || orders.length === 0) {
    body.innerHTML = '<tr><td colspan="6">No saved orders</td></tr>';
    return;
  }

  for (const item of orders.slice(0, 30)) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${item.order_time.replace("T", " ")}</td>
      <td>${item.symbol}</td>
      <td>${item.order_type}</td>
      <td>${Number(item.volume || 0).toFixed(2)}</td>
      <td>${item.ticket || "-"}</td>
      <td>${item.status || item.comment || "-"}</td>
    `;
    body.appendChild(row);
  }
}

function renderCandles(candles) {
  const wrap = $("#candles");
  wrap.innerHTML = "";
  for (const candle of (candles || []).slice(-30).reverse()) {
    const node = document.createElement("div");
    node.className = `candle ${Number(candle.close) >= Number(candle.open) ? "up" : "down"}`;
    node.innerHTML = `
      <time>${candle.time.slice(11, 16)}</time>
      <strong>${Number(candle.close).toFixed(5)}</strong>
      <span>H ${Number(candle.high).toFixed(5)}</span>
      <span>L ${Number(candle.low).toFixed(5)}</span>
    `;
    wrap.appendChild(node);
  }
  $("#lastUpdate").textContent = new Date().toLocaleTimeString();
}

function renderStrategy(strategy) {
  $("#signal").textContent = strategy.last_signal || "-";
  $("#logs").textContent = (strategy.logs || [])
    .map((line) => `[${line.time}] ${line.message}`)
    .join("\n");
  $("#logs").scrollTop = $("#logs").scrollHeight;
}

async function refreshHistory() {
  const [watchlist, signals, orders] = await Promise.all([
    request("/api/watchlist"),
    request("/api/signals?limit=100"),
    request("/api/orders?limit=100"),
  ]);
  renderWatchlist(watchlist.data);
  renderSignals(signals.data);
  renderOrderHistory(orders.data);
}

async function refresh() {
  const status = await request("/api/status");
  setConnection(status);
  renderStrategy(status.strategy);

  const symbol = $("#symbol").value.trim().toUpperCase();
  if (!symbol || !status.mt5.package_available) return;

  try {
    const tick = await request(`/api/tick/${symbol}`);
    renderTick(tick.data);
  } catch {
    $("#bid").textContent = "-";
    $("#ask").textContent = "-";
    $("#spread").textContent = "-";
  }

  try {
    const positions = await request(`/api/positions?symbol=${encodeURIComponent(symbol)}`);
    renderPositions(positions.data);
  } catch {
    renderPositions([]);
  }
}

async function loadCandles() {
  const symbol = $("#symbol").value.trim().toUpperCase();
  const timeframe = $("#timeframe").value;
  const result = await request(`/api/candles/${symbol}?timeframe=${timeframe}&bars=120`);
  renderCandles(result.data);
}

$("#connectForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await request("/api/connect", {
      method: "POST",
      body: JSON.stringify(connectPayload()),
    });
    await refresh();
    await loadCandles();
  } catch (error) {
    await refresh();
  }
});

$("#disconnectBtn").addEventListener("click", async () => {
  await request("/api/disconnect", { method: "POST" }).catch(() => {});
  await refresh();
});

$("#symbolForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await refresh();
  await loadCandles().catch((error) => {
    $("#lastUpdate").textContent = error.message;
  });
});

$("#addWatchBtn").addEventListener("click", async () => {
  await request("/api/watchlist", {
    method: "POST",
    body: JSON.stringify({
      symbol: $("#symbol").value.trim().toUpperCase(),
      timeframe: $("#timeframe").value,
    }),
  });
  await refreshHistory();
});

$("#watchlistBody").addEventListener("click", async (event) => {
  const deleteId = event.target.dataset.deleteWatch;
  if (deleteId) {
    await request(`/api/watchlist/${deleteId}`, { method: "DELETE" });
    await refreshHistory();
    return;
  }

  const loadSymbol = event.target.dataset.loadSymbol;
  if (!loadSymbol) return;
  $("#symbol").value = loadSymbol;
  $("#timeframe").value = event.target.dataset.loadTimeframe;
  await refresh();
  await loadCandles().catch((error) => {
    $("#lastUpdate").textContent = error.message;
  });
});

$("#buyBtn").addEventListener("click", async () => {
  await request("/api/order", { method: "POST", body: JSON.stringify(tradePayload("BUY")) });
  await refresh();
  await refreshHistory();
});

$("#sellBtn").addEventListener("click", async () => {
  await request("/api/order", { method: "POST", body: JSON.stringify(tradePayload("SELL")) });
  await refresh();
  await refreshHistory();
});

$("#positionsBody").addEventListener("click", async (event) => {
  const ticket = event.target.dataset.close;
  if (!ticket) return;
  await request(`/api/positions/${ticket}/close`, { method: "POST" });
  await refresh();
});

$("#startStrategyBtn").addEventListener("click", async () => {
  await request("/api/strategy/start", {
    method: "POST",
    body: JSON.stringify(strategyPayload()),
  });
  await refresh();
});

$("#stopStrategyBtn").addEventListener("click", async () => {
  await request("/api/strategy/stop", { method: "POST" }).catch(() => {});
  await refresh();
});

function closeAllPanelMenus(except) {
  document.querySelectorAll(".panel-menu.open").forEach((menu) => {
    if (menu !== except) menu.classList.remove("open");
  });
}

function initPanelMenus() {
  // Inject a three-dot menu into every panel/band that has a .panel-head
  document.querySelectorAll(".panel, .band").forEach((container) => {
    const head = container.querySelector(".panel-head");
    if (!head || head.dataset.menuReady) return;
    head.dataset.menuReady = "true";

    const menu = document.createElement("div");
    menu.className = "panel-menu";
    menu.innerHTML = `
      <button type="button" class="panel-menu-btn" title="Panel options">⋮</button>
      <div class="panel-menu-dropdown">
        <button type="button" data-action="toggle">Minimize</button>
      </div>
    `;
    head.appendChild(menu);

    const toggleBtn = menu.querySelector(".panel-menu-btn");
    const actionBtn = menu.querySelector('[data-action="toggle"]');

    toggleBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = menu.classList.contains("open");
      closeAllPanelMenus();
      menu.classList.toggle("open", !isOpen);
    });

    actionBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      const collapsed = container.classList.toggle("collapsed");
      actionBtn.textContent = collapsed ? "Maximize" : "Minimize";
      menu.classList.remove("open");
    });
  });

  document.addEventListener("click", () => closeAllPanelMenus());
}

function setAllPanelsCollapsed(collapsed) {
  document.querySelectorAll(".panel, .band").forEach((container) => {
    container.classList.toggle("collapsed", collapsed);
    const actionBtn = container.querySelector('[data-action="toggle"]');
    if (actionBtn) actionBtn.textContent = collapsed ? "Maximize" : "Minimize";
  });
}

function initGlobalPanelMenu() {
  const menu = $("#globalPanelMenu");
  const btn = $("#globalPanelMenuBtn");
  if (!menu || !btn) return;

  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    const isOpen = menu.classList.contains("open");
    closeAllPanelMenus();
    menu.classList.toggle("open", !isOpen);
  });

  $("#collapseAllBtn").addEventListener("click", (event) => {
    event.stopPropagation();
    setAllPanelsCollapsed(true);
    menu.classList.remove("open");
  });

  $("#expandAllBtn").addEventListener("click", (event) => {
    event.stopPropagation();
    setAllPanelsCollapsed(false);
    menu.classList.remove("open");
  });
}

initPanelMenus();
initGlobalPanelMenu();

refresh();
refreshHistory();
setInterval(refresh, 3000);
setInterval(refreshHistory, 10000);
setInterval(() => loadCandles().catch(() => {}), 15000);
