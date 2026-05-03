const state = {
  page: location.hash.replace("#", "") || "dashboard",
  servers: [],
  selectedId: localStorage.getItem("selectedServer") || "",
  dashboard: null,
  consoleTimer: null,
  dashboardTimer: null,
  quickDrawerTimer: null,
  quickDrawerCollapsed: localStorage.getItem("quickDrawerCollapsed") === "true",
  theme: document.documentElement.dataset.theme || "light",
  discoveredServers: [],
  filePath: "",
  setupMode: "choice",
  setupStep: 1,
  setupVersions: null,
  guidedDraft: {
    name: "Family Minecraft",
    version: "latest",
    ramChoice: "4096",
    customRam: 4096,
    port: 25565,
    world_name: "world",
    gamemode: "survival",
    difficulty: "normal",
    max_players: 10,
    motd: "A MineHost Helper server",
    online_mode: true,
    whitelist: false,
    command_blocks: false,
    accepted_eula: false,
  },
};

const titles = {
  dashboard: "Dashboard",
  "command-center": "Command Center",
  setup: "Get Started",
  settings: "Server Settings",
  players: "Players",
  console: "Console",
  files: "Files",
  "world-map": "World Map",
  backups: "Backups",
  networking: "Networking",
  help: "Help",
};

const $ = (id) => document.getElementById(id);

function applyTheme(theme) {
  state.theme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = state.theme;
  localStorage.setItem("minehostTheme", state.theme);
  const text = $("theme-toggle-text");
  const button = $("theme-toggle");
  if (text) text.textContent = state.theme === "dark" ? "Light mode" : "Dark mode";
  if (button) button.setAttribute("aria-label", `Switch to ${state.theme === "dark" ? "light" : "dark"} mode`);
}

function toggleTheme() {
  applyTheme(state.theme === "dark" ? "light" : "dark");
}

function toast(message, type = "ok") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  $("toast-root").appendChild(node);
  setTimeout(() => node.remove(), 5200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  const rawBody = await response.text();
  let data = null;
  if (rawBody) {
    try {
      data = JSON.parse(rawBody);
    } catch {
      data = rawBody;
    }
  }
  if (!response.ok) {
    const detail = data?.detail;
    const message = detail?.message || detail || (typeof data === "string" ? data : null) || `Request failed with HTTP ${response.status}.`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

function renderLogin(authStatus) {
  const setupRequired = !authStatus?.configured;
  document.body.innerHTML = `
    <main class="auth-screen">
      <section class="auth-card">
        <div class="brand auth-brand">
          <div class="brand-mark">MH</div>
          <div>
            <strong>MineHost Helper</strong>
            <span>Private local control center</span>
          </div>
        </div>
        <p class="eyebrow">${setupRequired ? "Create web login" : "Sign in"}</p>
        <h1>${setupRequired ? "Protect this manager" : "Welcome back"}</h1>
        <p class="muted">${setupRequired ? "Create a username and password for this PC. Friends should never need this password." : "Enter the MineHost Helper login created during setup."}</p>
        <form id="auth-form" class="stack">
          <label class="field">Username<input name="username" autocomplete="username" required value="${escapeHtml(authStatus?.username || "")}"></label>
          <label class="field">Password<input name="password" type="password" autocomplete="${setupRequired ? "new-password" : "current-password"}" required minlength="${setupRequired ? "8" : "1"}"></label>
          ${setupRequired ? `<p class="callout info">Use at least 8 characters. This only protects the local manager web UI; it does not change your Minecraft account.</p>` : ""}
          <button class="primary" type="submit">${setupRequired ? "Create Login" : "Sign In"}</button>
        </form>
        <p id="auth-error" class="callout danger hidden"></p>
      </section>
    </main>`;
  $("auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const endpoint = setupRequired ? "/api/auth/setup" : "/api/auth/login";
    try {
      const payload = {
        username: String(form.get("username") || ""),
        password: String(form.get("password") || ""),
      };
      await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
      if (setupRequired) {
        await api("/api/auth/login", { method: "POST", body: JSON.stringify(payload) });
      }
      location.reload();
    } catch (error) {
      const node = $("auth-error");
      node.textContent = error.message;
      node.classList.remove("hidden");
    }
  });
}

async function ensureAuthenticated() {
  const status = await api("/api/auth/status");
  if (!status.configured || !status.authenticated) {
    renderLogin(status);
    return false;
  }
  return true;
}

function selectedServer() {
  return state.servers.find((server) => server.id === state.selectedId) || state.servers[0] || null;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value > 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function statusPill(status) {
  return `<span class="pill ${status || "stopped"}">${status || "stopped"}</span>`;
}

function formatUptime(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  if (!total) return "Not running";
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${Math.max(1, minutes)}m`;
}

function quickStat(label, value) {
  return `<div class="quick-stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function jsArg(value) {
  return encodeURIComponent(String(value ?? ""));
}

function operationCard(operation) {
  if (!operation) return "";
  const percent = Number.isInteger(operation.percent) ? operation.percent : null;
  const activeClass = operation.active ? " active" : "";
  return `
    <div class="progress-card${activeClass}">
      <div class="progress-card-head">
        <div>
          <p class="eyebrow">${operation.active ? "Working" : "Last action"}</p>
          <h3>${operation.title || "Working on it"}</h3>
        </div>
        ${operation.active ? `<span class="spinner" aria-hidden="true"></span>` : ""}
      </div>
      <p>${operation.message || "MineHost Helper is waiting for Minecraft to finish this step."}</p>
      <div class="progress-track ${percent === null ? "indeterminate" : ""}" role="progressbar" aria-valuemin="0" aria-valuemax="100" ${percent === null ? "" : `aria-valuenow="${percent}"`}>
        <div class="progress-fill" style="${percent === null ? "" : `width:${percent}%`}"></div>
      </div>
      <p class="muted">${operation.active ? "Do not close the app while this is running. First start can take several minutes." : "This step has finished."}</p>
    </div>`;
}

function portResolutionCard(portCheck, serverStatus) {
  if (!portCheck || portCheck.available || serverStatus === "running") return "";
  const owner = portCheck.owner || {};
  const ownerText = owner.name
    ? `${owner.name}${owner.pid ? ` (PID ${owner.pid})` : ""}`
    : "another app";
  const nextPortText = portCheck.next_port ? `Use Open Port ${portCheck.next_port}` : "Find Another Port";
  return `
    <div class="resolution-card">
      <div>
        <p class="eyebrow">Start check</p>
        <h3>Port ${portCheck.port} needs attention</h3>
        <p>${escapeHtml(portCheck.message)}</p>
        <p class="muted">Detected owner: <strong>${escapeHtml(ownerText)}</strong></p>
        <p class="muted">${escapeHtml(portCheck.resolution)}</p>
      </div>
      <div class="actions">
        ${portCheck.can_stop_owner ? `<button class="primary" onclick="fixPortConflict('stop-owner')">Stop Old Server Process</button>` : ""}
        ${portCheck.next_port ? `<button onclick="fixPortConflict('use-next-port')">${escapeHtml(nextPortText)}</button>` : ""}
        <button onclick="go('settings')">Change Port Manually</button>
      </div>
    </div>`;
}

async function refreshData() {
  state.dashboard = await api(`/api/dashboard${state.selectedId ? `?server_id=${state.selectedId}` : ""}`);
  state.servers = state.dashboard.servers || [];
  const validSelected = state.servers.some((server) => server.id === state.selectedId);
  if (state.dashboard.selected?.id) {
    state.selectedId = state.dashboard.selected.id;
  } else if (!validSelected && state.servers[0]) {
    state.selectedId = state.servers[0].id;
  } else if (!state.servers.length) {
    state.selectedId = "";
  }
  if (state.selectedId) {
    localStorage.setItem("selectedServer", state.selectedId);
  } else {
    localStorage.removeItem("selectedServer");
  }
  renderServerSelect();
}

function renderServerSelect() {
  const select = $("server-select");
  select.innerHTML = "";
  if (!state.servers.length) {
    select.innerHTML = `<option>No servers yet</option>`;
    select.disabled = true;
    return;
  }
  select.disabled = false;
  state.servers.forEach((server) => {
    const option = document.createElement("option");
    option.value = server.id;
    option.textContent = server.name;
    option.selected = server.id === state.selectedId;
    select.appendChild(option);
  });
}

function renderQuickDrawer() {
  const drawer = $("quick-drawer");
  if (!drawer) return;
  const server = selectedServer();
  if (!server) {
    drawer.className = "quick-drawer empty";
    drawer.innerHTML = `
      <button class="drawer-handle" type="button" onclick="toggleQuickDrawer()" aria-label="Toggle quick drawer"></button>
      <div class="drawer-content">
        <div>
          <span class="drawer-label">Quick Controls</span>
          <strong>No server yet</strong>
        </div>
        <button class="primary" onclick="go('setup')">Create or Import Server</button>
      </div>`;
    return;
  }
  const dash = state.dashboard || {};
  const process = dash.process || {};
  const players = dash.players || {};
  const onlineCount = Array.isArray(players.online) ? players.online.length : 0;
  const running = server.status === "running";
  const busy = ["starting", "stopping"].includes(server.status) || server.operation?.active;
  drawer.className = `quick-drawer${state.quickDrawerCollapsed ? " collapsed" : ""}`;
  drawer.innerHTML = `
    <button class="drawer-handle" type="button" onclick="toggleQuickDrawer()" aria-label="${state.quickDrawerCollapsed ? "Expand" : "Collapse"} quick drawer"></button>
    <div class="drawer-content">
      <div class="drawer-status">
        <span class="drawer-label">Server Status</span>
        ${statusPill(server.status)}
      </div>
      <div class="drawer-metric">
        <span>User Count</span>
        <strong>${onlineCount} online</strong>
      </div>
      <div class="drawer-metric">
        <span>Server Uptime</span>
        <strong>${formatUptime(process.uptime_seconds)}</strong>
      </div>
      <div class="drawer-actions">
        <button type="button" onclick="serverAction('restart')" ${running && !busy ? "" : "disabled"}>Restart Server</button>
        <button class="primary" type="button" onclick="setTimeDay()" ${running ? "" : "disabled"}>Set Day</button>
      </div>
    </div>`;
}

function toggleQuickDrawer() {
  state.quickDrawerCollapsed = !state.quickDrawerCollapsed;
  localStorage.setItem("quickDrawerCollapsed", String(state.quickDrawerCollapsed));
  renderQuickDrawer();
}

function startQuickDrawerPolling() {
  if (state.quickDrawerTimer) return;
  state.quickDrawerTimer = setInterval(async () => {
    if (!$("quick-drawer")) return;
    try {
      await refreshData();
      renderQuickDrawer();
      if (state.page === "dashboard") renderDashboard();
    } catch {
      renderQuickDrawer();
    }
  }, 5000);
}

async function runAction(label, fn) {
  try {
    await fn();
    toast(label);
    await render();
  } catch (error) {
    toast(error.message, "error");
  }
}

function noServerCard() {
  return `
    <div class="card">
      <h2>Create your first server</h2>
      <p class="muted">MineHost Helper will download the Minecraft server jar from Mojang and help set the basics safely.</p>
      <button class="primary" onclick="go('setup')">Get Started</button>
    </div>`;
}

function renderDashboard() {
  const server = selectedServer();
  const page = $("dashboard");
  if (!server) {
    page.innerHTML = noServerCard();
    return;
  }
  const dash = state.dashboard;
  const process = dash.process || {};
  const portCheck = dash.port_check || {};
  const running = server.status === "running";
  const busy = ["starting", "stopping"].includes(server.status) || server.operation?.active;
  const portBlocked = !running && portCheck.available === false;
  page.innerHTML = `
    <div class="status-card">
      <div>
        <p class="eyebrow">${server.name}</p>
        <h2>${statusPill(server.status)} Minecraft ${server.version}</h2>
        <div class="quick-stats">
          ${quickStat("RAM", `${server.ram_mb} MB`)}
          ${quickStat("Port", server.port)}
          ${quickStat("Uptime", formatUptime(process.uptime_seconds))}
        </div>
        <div class="actions">
          <button class="primary" ${running || busy || portBlocked ? "disabled" : ""} onclick="serverAction('start')">Start Server</button>
          <button class="warning" ${running ? "" : "disabled"} onclick="serverAction('stop')">Stop</button>
          <button ${busy ? "disabled" : ""} onclick="serverAction('restart')">Restart</button>
          <button class="danger" onclick="forceKill()">Emergency Kill</button>
        </div>
      </div>
      <div class="address-box">
        <strong>Address for friends outside your house</strong>
        <code>${dash.server_address}</code>
        <button onclick="copyText('${dash.server_address}')">Copy Friend Address</button>
      </div>
    </div>
    ${portResolutionCard(portCheck, server.status)}
    ${operationCard(server.operation)}
    <div class="card-grid dashboard-grid" style="margin-top:18px">
      <div class="card"><h3>Local Address</h3><p>${dash.local_address}</p><p class="muted">Use this for people on your Wi-Fi.</p></div>
      <div class="card"><h3>Public IP</h3><p>${dash.public_ip || "Unknown"}</p><p class="muted">Router forwarding is needed for friends outside.</p></div>
      <div class="card"><h3>Process</h3><p>${process.memory_mb ? `${process.memory_mb} MB RAM` : "No process info yet"}</p><p class="muted">Player count is planned for a later query/RCON pass.</p></div>
    </div>
    <div class="split" style="margin-top:18px">
      <div class="card"><h3>Recent Console</h3><pre class="console">${(dash.recent_console || []).join("\n") || "Console output appears after the server starts."}</pre></div>
      <div class="card">
        <h3>Next best step</h3>
        <p class="muted">If friends cannot connect, use the Networking page. It checks the local port, Windows Firewall rule, and explains router forwarding.</p>
        <div class="actions">
          <button onclick="go('networking')">Networking</button>
          <button onclick="go('settings')">Settings</button>
          <button onclick="go('backups')">Backups</button>
        </div>
      </div>
    </div>`;
}

function renderSetup() {
  if (state.setupMode === "import") {
    renderImportSetup();
    return;
  }
  if (state.setupMode === "guided") {
    renderGuidedSetup();
    return;
  }
  if (state.setupMode === "manual") {
    renderManualSetup();
    return;
  }
  renderSetupChoice();
}

function renderSetupChoice() {
  $("setup").innerHTML = `
    <div class="setup-hero">
      <div>
        <p class="eyebrow">First thing</p>
        <h2>What do you want to do?</h2>
        <p class="muted">Choose the path that matches your situation. MineHost Helper will keep the technical parts out of the way.</p>
      </div>
      <div id="java-status" class="setup-java-status">Checking Java...</div>
    </div>
    <div class="choice-grid">
      <button class="choice-card primary-choice" type="button" onclick="chooseSetupMode('import')">
        <span class="choice-icon">I</span>
        <strong>Import existing Minecraft server</strong>
        <span>Search this PC for server folders and add one without moving your world.</span>
      </button>
      <button class="choice-card" type="button" onclick="chooseSetupMode('guided')">
        <span class="choice-icon">G</span>
        <strong>Setup new server, guided</strong>
        <span>Recommended. Step-by-step questions with safe defaults.</span>
      </button>
      <button class="choice-card" type="button" onclick="chooseSetupMode('manual')">
        <span class="choice-icon">M</span>
        <strong>Setup new server, manual</strong>
        <span>One advanced form if you already know what you want.</span>
      </button>
    </div>
    <div class="card setup-note">
      <h3>What happens next?</h3>
      <p class="muted">MineHost Helper prepares Java, downloads the official Minecraft server jar from Mojang, writes safe settings, and shows the exact address to give friends.</p>
    </div>`;
  loadJavaStatus();
}

function chooseSetupMode(mode) {
  state.setupMode = mode;
  state.setupStep = 1;
  renderSetup();
  if (mode === "import") {
    scanExistingServers();
  }
}

function backToSetupChoice() {
  state.setupMode = "choice";
  state.setupStep = 1;
  renderSetup();
}

async function loadVersions(selectId = "version-select", selected = "latest") {
  try {
    const data = state.setupVersions || await api("/api/minecraft/versions");
    state.setupVersions = data;
    const select = $(selectId);
    if (!select) return;
    select.innerHTML = `<option value="latest">Latest stable release (${data.latest})</option>`;
    data.releases.forEach((version) => {
      const isSelected = version.id === selected ? " selected" : "";
      select.insertAdjacentHTML("beforeend", `<option value="${version.id}"${isSelected}>${version.id}</option>`);
    });
    select.value = selected || "latest";
  } catch (error) {
    toast(`Version list unavailable: ${error.message}`, "error");
  }
}

function renderImportSetup() {
  $("setup").innerHTML = `
    <div class="setup-flow">
      <div class="setup-flow-head">
        <button type="button" onclick="backToSetupChoice()">Back</button>
        <div>
          <p class="eyebrow">Import existing server</p>
          <h2>Step 1: Find Minecraft server folders</h2>
          <p class="muted">MineHost Helper searches common folders like Desktop, Downloads, Documents, and Games. It does not move or delete anything.</p>
        </div>
      </div>
      <div class="split">
        <div class="card">
          <h3>Search this PC</h3>
          <p class="muted">If a server is found, choose Add to MineHost. Stop any old server window first so MineHost Helper can control it cleanly.</p>
          <div class="actions">
            <button class="primary" onclick="scanExistingServers()">Search Again</button>
            <button onclick="chooseSetupMode('guided')">Create New Instead</button>
          </div>
          <div id="discovery-results" class="stack" style="margin-top:16px"></div>
        </div>
        <div class="card">
          <h3>What counts as a server?</h3>
          <p class="muted">A folder with a Minecraft server jar, <code>server.properties</code>, or an existing world folder. Imported servers stay where they are.</p>
          <p class="callout info">After import, the Dashboard will show Start, Stop, Console, Backups, and Networking for that server.</p>
        </div>
      </div>
    </div>`;
}

function renderGuidedSetup() {
  const draft = state.guidedDraft;
  const step = state.setupStep;
  const steps = ["Basics", "Size", "World", "Friends", "Finish"];
  $("setup").innerHTML = `
    <div class="setup-flow">
      <div class="setup-flow-head">
        <button type="button" onclick="backToSetupChoice()">Back</button>
        <div>
          <p class="eyebrow">Guided setup</p>
          <h2>Step ${step}: ${steps[step - 1]}</h2>
          <p class="muted">${guidedStepHelp(step)}</p>
        </div>
      </div>
      <div class="stepper">${steps.map((label, index) => `<span class="${index + 1 === step ? "active" : index + 1 < step ? "done" : ""}">${index + 1}. ${label}</span>`).join("")}</div>
      <form id="guided-form" class="card">
        ${guidedStepFields(step, draft)}
        <div class="actions" style="margin-top:18px">
          ${step > 1 ? `<button type="button" onclick="guidedBack()">Back</button>` : ""}
          ${step < 5 ? `<button class="primary" type="button" onclick="guidedNext()">Next Step</button>` : `<button id="guided-create-button" class="primary" type="button" onclick="guidedCreateServer()">Create Server</button>`}
        </div>
        <div id="setup-progress" class="progress-card active hidden" style="margin-top:16px">
          <div class="progress-card-head">
            <div>
              <p class="eyebrow">Creating</p>
              <h3>Setting up your server</h3>
            </div>
            <span class="spinner" aria-hidden="true"></span>
          </div>
          <p>Downloading Minecraft and writing safe defaults. This can take a few minutes.</p>
          <div class="progress-track indeterminate" role="progressbar"><div class="progress-fill"></div></div>
          <p class="muted">Keep this page open. MineHost Helper will move you to the dashboard when it is done.</p>
        </div>
      </form>
    </div>`;
  if (step === 1) {
    loadVersions("guided-version-select", draft.version);
  }
}

function guidedStepHelp(step) {
  return {
    1: "Name the server and pick a Minecraft version. Latest stable is best for most families.",
    2: "Choose how much memory to give Minecraft and how many friends can join.",
    3: "Pick the world name and basic gameplay rules.",
    4: "Choose the port and friend access options. The default port is easiest.",
    5: "Review the safe defaults, accept the Minecraft EULA, then create the server.",
  }[step];
}

function option(value, label, selected) {
  return `<option value="${escapeHtml(value)}" ${String(value) === String(selected) ? "selected" : ""}>${escapeHtml(label)}</option>`;
}

function checked(value) {
  return value ? "checked" : "";
}

function fieldLabel(label, tip) {
  return `<span class="field-label">${escapeHtml(label)}</span><span class="field-hint">${escapeHtml(tip)}</span>`;
}

function checkboxLabel(label, tip) {
  return `<span class="checkbox-copy"><strong>${escapeHtml(label)}</strong><small>${escapeHtml(tip)}</small></span>`;
}

function guidedStepFields(step, draft) {
  if (step === 1) {
    return `
      <div class="form-grid">
        <label class="field">${fieldLabel("Server name", "The friendly name MineHost Helper shows in the app. Friends do not type this to join.")}<input name="name" required value="${escapeHtml(draft.name)}" placeholder="Family Minecraft"></label>
        <label class="field">${fieldLabel("Minecraft version", "Latest stable is recommended. Pick a specific version only if friends or mods require it.")}<select name="version" id="guided-version-select"><option value="latest">Latest stable release</option></select></label>
      </div>
      <p class="callout info">Use a name people recognize. You can rename it later.</p>`;
  }
  if (step === 2) {
    return `
      <div class="choice-grid compact">
        <label class="choice-card radio-choice"><input type="radio" name="ramChoice" value="2048" ${draft.ramChoice === "2048" ? "checked" : ""}><strong>2 GB</strong><span>Small server, a few friends.</span><small class="choice-help">Good for a small vanilla server. Use more if the world lags.</small></label>
        <label class="choice-card radio-choice"><input type="radio" name="ramChoice" value="4096" ${draft.ramChoice === "4096" ? "checked" : ""}><strong>4 GB</strong><span>Recommended for most servers.</span><small class="choice-help">Best default for home servers without wasting too much PC memory.</small></label>
        <label class="choice-card radio-choice"><input type="radio" name="ramChoice" value="6144" ${draft.ramChoice === "6144" ? "checked" : ""}><strong>6 GB</strong><span>Bigger worlds or more players.</span><small class="choice-help">Use this for heavier exploration or more friends if your PC has free memory.</small></label>
        <label class="choice-card radio-choice"><input type="radio" name="ramChoice" value="custom" ${draft.ramChoice === "custom" ? "checked" : ""}><strong>Custom</strong><span>Choose your own memory amount.</span><small class="choice-help">Advanced. Enter memory in MB. 4096 MB equals 4 GB.</small></label>
      </div>
      <div class="form-grid" style="margin-top:16px">
        <label class="field">${fieldLabel("Custom RAM MB", "Only used when Custom is selected. 2048=2 GB, 4096=4 GB, 6144=6 GB.")}<input name="customRam" type="number" min="512" max="65536" value="${escapeHtml(draft.customRam)}"></label>
        <label class="field">${fieldLabel("Max players", "The maximum number of people allowed online at once. It does not reserve performance by itself.")}<input name="max_players" type="number" min="1" max="200" value="${escapeHtml(draft.max_players)}"></label>
      </div>`;
  }
  if (step === 3) {
    return `
      <div class="form-grid">
        <label class="field">${fieldLabel("World name", "The folder name for the Minecraft world. Keep it simple, like world or family-world.")}<input name="world_name" value="${escapeHtml(draft.world_name)}"></label>
        <label class="field">${fieldLabel("Gamemode", "Survival is normal Minecraft. Creative gives unlimited blocks. Adventure/Spectator are special modes.")}<select name="gamemode">
          ${option("survival", "Survival", draft.gamemode)}
          ${option("creative", "Creative", draft.gamemode)}
          ${option("adventure", "Adventure", draft.gamemode)}
          ${option("spectator", "Spectator", draft.gamemode)}
        </select></label>
        <label class="field">${fieldLabel("Difficulty", "Controls hostile mobs and damage. Normal is a good default; Peaceful removes hostile mob pressure.")}<select name="difficulty">
          ${option("peaceful", "Peaceful", draft.difficulty)}
          ${option("easy", "Easy", draft.difficulty)}
          ${option("normal", "Normal", draft.difficulty)}
          ${option("hard", "Hard", draft.difficulty)}
        </select></label>
        <label class="field">${fieldLabel("Message of the day", "The short message players see in their Minecraft multiplayer server list.")}<input name="motd" value="${escapeHtml(draft.motd)}"></label>
      </div>`;
  }
  if (step === 4) {
    return `
      <div class="form-grid">
        <label class="field">${fieldLabel("Minecraft port", "The network door Minecraft listens on. 25565 is the default and easiest for router forwarding.")}<input name="port" type="number" min="1" max="65535" value="${escapeHtml(draft.port)}"></label>
        <label class="field"><span><input name="online_mode" type="checkbox" ${checked(draft.online_mode)}> ${checkboxLabel("Require real Minecraft accounts", "Recommended. Keeps cracked/offline usernames from joining and lets Minecraft verify players.")}</span></label>
        <label class="field"><span><input name="whitelist" type="checkbox" ${checked(draft.whitelist)}> ${checkboxLabel("Use a whitelist", "Only players you add can join. Best for family/friend servers.")}</span></label>
        <label class="field"><span><input name="command_blocks" type="checkbox" ${checked(draft.command_blocks)}> ${checkboxLabel("Allow command blocks", "Advanced. Needed for some maps, but command blocks can run powerful in-game commands.")}</span></label>
      </div>
      <p class="callout">Keep port <code>25565</code> unless you have a reason to change it. Friends outside your house still need router forwarding.</p>`;
  }
  return `
    <div class="review-grid">
      ${quickStat("Name", draft.name)}
      ${quickStat("Version", draft.version === "latest" ? "Latest stable" : draft.version)}
      ${quickStat("RAM", `${draft.ramChoice === "custom" ? draft.customRam : draft.ramChoice} MB`)}
      ${quickStat("Port", draft.port)}
      ${quickStat("Mode", draft.gamemode)}
      ${quickStat("Difficulty", draft.difficulty)}
    </div>
    <p class="callout">Minecraft requires EULA acceptance before the server can start. MineHost Helper writes <code>eula=true</code> only after you explicitly check this box.</p>
    <label class="field"><span><input name="accepted_eula" type="checkbox" ${checked(draft.accepted_eula)} required> ${checkboxLabel("I accept the Minecraft EULA", "Required by Mojang. MineHost Helper will not start a server until you explicitly accept it.")}</span></label>`;
}

function saveGuidedStep() {
  const form = $("guided-form");
  if (!form) return true;
  const data = new FormData(form);
  const step = state.setupStep;
  const draft = state.guidedDraft;
  if (step === 1) {
    draft.name = String(data.get("name") || "").trim();
    draft.version = String(data.get("version") || "latest");
    if (!draft.name) {
      toast("Give the server a name first.", "error");
      return false;
    }
  }
  if (step === 2) {
    draft.ramChoice = String(data.get("ramChoice") || "4096");
    draft.customRam = Number(data.get("customRam") || 4096);
    draft.max_players = Number(data.get("max_players") || 10);
  }
  if (step === 3) {
    draft.world_name = String(data.get("world_name") || "world").trim() || "world";
    draft.gamemode = String(data.get("gamemode") || "survival");
    draft.difficulty = String(data.get("difficulty") || "normal");
    draft.motd = String(data.get("motd") || "A MineHost Helper server");
  }
  if (step === 4) {
    draft.port = Number(data.get("port") || 25565);
    draft.online_mode = data.has("online_mode");
    draft.whitelist = data.has("whitelist");
    draft.command_blocks = data.has("command_blocks");
  }
  if (step === 5) {
    draft.accepted_eula = data.has("accepted_eula");
    if (!draft.accepted_eula) {
      toast("Accept the Minecraft EULA before creating the server.", "error");
      return false;
    }
  }
  return true;
}

function guidedNext() {
  if (!saveGuidedStep()) return;
  state.setupStep = Math.min(5, state.setupStep + 1);
  renderGuidedSetup();
}

function guidedBack() {
  saveGuidedStep();
  state.setupStep = Math.max(1, state.setupStep - 1);
  renderGuidedSetup();
}

function guidedPayload() {
  const draft = state.guidedDraft;
  const ramMb = draft.ramChoice === "custom" ? Number(draft.customRam) : Number(draft.ramChoice);
  return {
    name: draft.name,
    version: draft.version,
    ram_mb: ramMb,
    port: Number(draft.port),
    world_name: draft.world_name,
    gamemode: draft.gamemode,
    difficulty: draft.difficulty,
    online_mode: draft.online_mode,
    whitelist: draft.whitelist,
    command_blocks: draft.command_blocks,
    max_players: Number(draft.max_players),
    motd: draft.motd,
    accepted_eula: draft.accepted_eula,
  };
}

async function guidedCreateServer() {
  if (!saveGuidedStep()) return;
  const button = $("guided-create-button");
  const progress = $("setup-progress");
  await createServer(guidedPayload(), button, progress);
}

function renderManualSetup() {
  $("setup").innerHTML = `
    <div class="setup-flow">
      <div class="setup-flow-head">
        <button type="button" onclick="backToSetupChoice()">Back</button>
        <div>
          <p class="eyebrow">Manual setup</p>
          <h2>One-page server setup</h2>
          <p class="muted">Advanced path. Use this if you already know the settings you want.</p>
        </div>
      </div>
      <form id="setup-form" class="card">
        <div class="form-grid">
          <label class="field">${fieldLabel("Server name", "The friendly name MineHost Helper shows in the app. Friends do not type this to join.")}<input name="name" required value="Family Minecraft"></label>
          <label class="field">${fieldLabel("Minecraft version", "Latest stable is recommended. Pick a specific version only if friends or mods require it.")}<select name="version" id="manual-version-select"><option value="latest">Latest stable release</option></select></label>
          <label class="field">${fieldLabel("RAM", "How much memory Minecraft can use. 4 GB is recommended for most home servers.")}<select name="ramChoice"><option value="4096">4 GB recommended</option><option value="2048">2 GB small</option><option value="6144">6 GB larger</option><option value="custom">Custom</option></select></label>
          <label class="field">${fieldLabel("Custom RAM MB", "Only used when Custom is selected. 2048=2 GB, 4096=4 GB, 6144=6 GB.")}<input name="customRam" type="number" min="512" max="65536" value="4096"></label>
          <label class="field">${fieldLabel("Server port", "The network door Minecraft listens on. 25565 is the default and easiest for router forwarding.")}<input name="port" type="number" min="1" max="65535" value="25565"></label>
          <label class="field">${fieldLabel("World name", "The folder name for the Minecraft world. Keep it simple, like world or family-world.")}<input name="world_name" value="world"></label>
          <label class="field">${fieldLabel("Gamemode", "Survival is normal Minecraft. Creative gives unlimited blocks. Adventure/Spectator are special modes.")}<select name="gamemode"><option value="survival">Survival</option><option value="creative">Creative</option><option value="adventure">Adventure</option><option value="spectator">Spectator</option></select></label>
          <label class="field">${fieldLabel("Difficulty", "Controls hostile mobs and damage. Normal is a good default; Peaceful removes hostile mob pressure.")}<select name="difficulty"><option value="peaceful">Peaceful</option><option value="easy">Easy</option><option value="normal" selected>Normal</option><option value="hard">Hard</option></select></label>
          <label class="field">${fieldLabel("Max players", "The maximum number of people allowed online at once. It does not reserve performance by itself.")}<input name="max_players" type="number" min="1" max="200" value="10"></label>
          <label class="field">${fieldLabel("Message of the day", "The short message players see in their Minecraft multiplayer server list.")}<input name="motd" value="A MineHost Helper server"></label>
          <label class="field"><span><input name="online_mode" type="checkbox" checked> ${checkboxLabel("Require real Minecraft accounts", "Recommended. Keeps cracked/offline usernames from joining and lets Minecraft verify players.")}</span></label>
          <label class="field"><span><input name="whitelist" type="checkbox"> ${checkboxLabel("Use a whitelist", "Only players you add can join. Best for family/friend servers.")}</span></label>
          <label class="field"><span><input name="command_blocks" type="checkbox"> ${checkboxLabel("Allow command blocks", "Advanced. Needed for some maps, but command blocks can run powerful in-game commands.")}</span></label>
          <label class="field"><span><input name="accepted_eula" type="checkbox" required> ${checkboxLabel("I accept the Minecraft EULA", "Required by Mojang. MineHost Helper will not start a server until you explicitly accept it.")}</span></label>
        </div>
        <p class="callout">Minecraft requires EULA acceptance before the server can start. MineHost Helper writes <code>eula=true</code> only after you explicitly check this box.</p>
        <button id="create-server-button" class="primary" type="submit">Create Server</button>
        <div id="setup-progress" class="progress-card active hidden" style="margin-top:16px">
          <div class="progress-card-head">
            <div>
              <p class="eyebrow">Creating</p>
              <h3>Setting up your server</h3>
            </div>
            <span class="spinner" aria-hidden="true"></span>
          </div>
          <p>Downloading Minecraft and writing safe defaults. This can take a few minutes.</p>
          <div class="progress-track indeterminate" role="progressbar"><div class="progress-fill"></div></div>
          <p class="muted">Keep this page open. MineHost Helper will move you to the dashboard when it is done.</p>
        </div>
      </form>
    </div>`;
  loadVersions("manual-version-select");
  $("setup-form").addEventListener("submit", createServerFromForm);
}

async function scanExistingServers() {
  const target = $("discovery-results");
  if (!target) return;
  target.innerHTML = `<p class="muted"><span class="spinner inline" aria-hidden="true"></span> Searching common folders like Desktop, Downloads, Documents, and Games...</p>`;
  try {
    state.discoveredServers = await api("/api/servers/discovery");
    renderDiscoveryResults();
  } catch (error) {
    target.innerHTML = `<p class="callout danger">${escapeHtml(error.message)}</p>`;
  }
}

function renderDiscoveryResults() {
  const target = $("discovery-results");
  if (!target) return;
  if (!state.discoveredServers.length) {
    target.innerHTML = `<p class="callout">No existing Minecraft Java server folders were found in common locations. You can still create a new guided setup instead.</p>`;
    return;
  }
  target.innerHTML = state.discoveredServers.map((server, index) => `
    <div class="list-item discovery-item">
      <div>
        <strong>${escapeHtml(server.name)}</strong>
        <p class="muted">${escapeHtml(server.path)}</p>
        <p class="muted">Jar: ${escapeHtml(server.jar_name || "Unknown")} | Port: ${escapeHtml(server.port)} | EULA: ${server.eula_accepted ? "accepted" : "not accepted yet"}</p>
      </div>
      <button ${server.already_added ? "disabled" : ""} onclick="adoptExistingServer(${index})">${server.already_added ? "Already Added" : "Add to MineHost"}</button>
    </div>
  `).join("");
}

async function adoptExistingServer(index) {
  const candidate = state.discoveredServers[index];
  if (!candidate) return;
  const name = prompt("What should MineHost Helper call this server?", candidate.name) || candidate.name;
  await runAction("Existing server added", async () => {
    const server = await api("/api/servers/adopt", {
      method: "POST",
      body: JSON.stringify({ path: candidate.path, name, ram_mb: 4096 }),
    });
    state.selectedId = server.id;
    localStorage.setItem("selectedServer", server.id);
    await refreshData();
    go("dashboard");
  });
}

async function loadJavaStatus() {
  const target = $("java-status");
  if (!target) return;
  try {
    const data = await api("/api/java/status");
    target.textContent = data.available ? `Java ready: ${data.version}` : "Java not found. MineHost Helper can download Temurin Java.";
  } catch {
    target.textContent = "Java status could not be checked.";
  }
}

async function installJava() {
  await runAction("Java is ready", async () => {
    if ($("java-status")) $("java-status").innerHTML = `<span class="spinner inline" aria-hidden="true"></span> Downloading Java. This can take a few minutes.`;
    const data = await api("/api/java/install", { method: "POST" });
    if ($("java-status")) $("java-status").textContent = `Java ready: ${data.version}`;
  });
}

async function createServerFromForm(event) {
  event.preventDefault();
  const button = $("create-server-button");
  const progress = $("setup-progress");
  const form = new FormData(event.target);
  const ramChoice = form.get("ramChoice");
  const payload = {
    name: form.get("name"),
    version: form.get("version"),
    ram_mb: ramChoice === "custom" ? Number(form.get("customRam")) : Number(ramChoice),
    port: Number(form.get("port")),
    world_name: form.get("world_name"),
    gamemode: form.get("gamemode"),
    difficulty: form.get("difficulty"),
    online_mode: form.has("online_mode"),
    whitelist: form.has("whitelist"),
    command_blocks: form.has("command_blocks"),
    max_players: Number(form.get("max_players")),
    motd: form.get("motd"),
    accepted_eula: form.has("accepted_eula"),
  };
  await createServer(payload, button, progress);
}

async function createServer(payload, button, progress) {
  if (button) {
    button.disabled = true;
    button.textContent = "Creating...";
  }
  if (progress) {
    progress.classList.remove("hidden");
  }
  try {
    const server = await api("/api/servers", { method: "POST", body: JSON.stringify(payload) });
    state.selectedId = server.id;
    localStorage.setItem("selectedServer", server.id);
    await refreshData();
    toast("Server created");
    go("dashboard");
  } catch (error) {
    toast(error.message, "error");
    if (button) {
      button.disabled = false;
      button.textContent = "Create Server";
    }
    if (progress) {
      progress.classList.add("hidden");
    }
  }
}

async function renderSettings() {
  const server = selectedServer();
  if (!server) {
    $("settings").innerHTML = noServerCard();
    return;
  }
  const [props, versionData, appSettings] = await Promise.all([
    api(`/api/servers/${server.id}/properties`),
    api("/api/minecraft/versions").catch(() => ({ latest: server.version, releases: [{ id: server.version, type: "release" }] })),
    api("/api/app-settings"),
  ]);
  const versionOptions = versionData.releases?.length ? versionData.releases : [{ id: server.version, type: "release" }];
  const autoStartIds = appSettings.auto_start_server_ids || [];
  const autoStartsThisServer = autoStartIds.includes(server.id);
  $("settings").innerHTML = `
    <div class="row">
      <div class="card">
        <h2>Tray agent and startup</h2>
        <p class="muted">MineHost Helper can stay running near the Windows clock, start when you sign in, and start this Minecraft server automatically.</p>
        <div class="form-grid">
          <label class="field"><span><input id="agent-close-to-tray" type="checkbox" ${appSettings.close_to_tray ? "checked" : ""}> Close button hides to tray</span></label>
          <label class="field"><span><input id="agent-auto-open-browser" type="checkbox" ${appSettings.auto_open_browser ? "checked" : ""}> Open browser when launched manually</span></label>
          <label class="field"><span><input id="agent-start-on-boot" type="checkbox" ${appSettings.start_on_boot ? "checked" : ""}> Start MineHost Helper when I sign in</span></label>
          <label class="field"><span><input id="agent-auto-start-server" type="checkbox" ${autoStartsThisServer ? "checked" : ""}> Auto-start this Minecraft server</span></label>
        </div>
        <p class="callout info">Startup uses your Windows account only. The manager UI still binds to this PC only, and Minecraft auto-start uses the same safe Start flow as the Dashboard.</p>
        <div class="actions">
          <button class="primary" onclick="saveAgentSettings()">Save Agent Settings</button>
        </div>
      </div>
      <div class="card">
        <h2>Server version</h2>
        <p class="muted">Current version: Minecraft ${server.version}. Stop the server before changing versions. Downgrading can damage worlds, so make a backup first.</p>
        <div class="form-grid">
          <label class="field">Minecraft version
            <select id="server-version-select">
              ${versionOptions.map((version) => `<option value="${version.id}" ${version.id === server.version ? "selected" : ""}>${version.id}${version.id === versionData.latest ? " (latest)" : ""}</option>`).join("")}
            </select>
          </label>
        </div>
        <p class="callout info">MineHost Helper downloads server jars using Mojang's official version manifest and backs up the current server jar before replacing it.</p>
        <div class="actions">
          <button class="primary" onclick="changeServerVersion()" ${["running", "starting", "stopping"].includes(server.status) ? "disabled" : ""}>Change Version</button>
          <button onclick="createBackup()">Create Backup First</button>
        </div>
      </div>
      <form id="settings-form" class="card">
        <h2>Friendly settings</h2>
        <p class="muted">Changes to most Minecraft properties need a restart. Use Save and Restart when players are ready.</p>
        <div class="form-grid">
          ${selectField("difficulty", "Difficulty", props["difficulty"], [
            ["peaceful", "Peaceful"],
            ["easy", "Easy"],
            ["normal", "Normal"],
            ["hard", "Hard"],
          ])}
          ${selectField("gamemode", "Gamemode", props["gamemode"], [
            ["survival", "Survival"],
            ["creative", "Creative"],
            ["adventure", "Adventure"],
            ["spectator", "Spectator"],
          ])}
          ${field("max-players", "Max players", props["max-players"], "number")}
          ${field("server-port", "Server port", props["server-port"], "number")}
          ${field("motd", "MOTD", props["motd"])}
          ${field("spawn-protection", "Spawn protection", props["spawn-protection"], "number")}
          ${field("view-distance", "View distance", props["view-distance"], "number")}
          ${field("simulation-distance", "Simulation distance", props["simulation-distance"], "number")}
        </div>
        <div class="form-grid" style="margin-top:14px">
          ${check("white-list", "Whitelist", props["white-list"])}
          ${check("online-mode", "Online mode", props["online-mode"])}
          ${check("enable-command-block", "Command blocks", props["enable-command-block"])}
          ${check("pvp", "PvP", props["pvp"])}
          ${check("allow-flight", "Allow flight", props["allow-flight"])}
          ${check("enable-rcon", "Enable RCON (advanced)", props["enable-rcon"])}
        </div>
        <details class="advanced">
          <summary>Advanced key/value editor</summary>
          <p class="muted">One property per line as <code>key=value</code>. Keep this closed unless you know what you are changing.</p>
          <textarea id="advanced-props">${Object.entries(props).map(([key, value]) => `${key}=${value}`).join("\n")}</textarea>
        </details>
        <div class="actions" style="margin-top:16px">
          <button class="primary" type="submit">Save</button>
          <button type="button" onclick="saveSettings(true)">Save and Restart</button>
        </div>
      </form>
    </div>`;
  $("settings-form").addEventListener("submit", (event) => {
    event.preventDefault();
    saveSettings(false);
  });
}

function field(name, label, value, type = "text") {
  return `<label class="field">${label}<input name="${name}" type="${type}" value="${value ?? ""}"></label>`;
}

function selectField(name, label, value, options) {
  const normalized = String(value ?? "").toLowerCase();
  return `
    <label class="field">${label}
      <select name="${name}">
        ${options.map(([optionValue, optionLabel]) => `<option value="${optionValue}" ${optionValue === normalized ? "selected" : ""}>${optionLabel}</option>`).join("")}
      </select>
    </label>`;
}

function check(name, label, checked) {
  return `<label class="field"><span><input name="${name}" type="checkbox" ${checked ? "checked" : ""}> ${label}</span></label>`;
}

function collectSettings() {
  const form = new FormData($("settings-form"));
  const props = {};
  $("advanced-props").value.split(/\r?\n/).forEach((line) => {
    if (!line.trim() || !line.includes("=")) return;
    const [key, ...rest] = line.split("=");
    props[key.trim()] = rest.join("=").trim();
  });
  ["difficulty", "gamemode", "motd"].forEach((key) => props[key] = form.get(key));
  ["max-players", "server-port", "spawn-protection", "view-distance", "simulation-distance"].forEach((key) => props[key] = Number(form.get(key)));
  ["white-list", "online-mode", "enable-command-block", "pvp", "allow-flight", "enable-rcon"].forEach((key) => props[key] = form.has(key));
  return props;
}

async function saveAgentSettings() {
  const server = selectedServer();
  if (!server) return;
  const current = await api("/api/app-settings");
  let autoStartIds = current.auto_start_server_ids || [];
  const wantsAutoStart = $("agent-auto-start-server").checked;
  if (wantsAutoStart && !autoStartIds.includes(server.id)) {
    autoStartIds = [...autoStartIds, server.id];
  }
  if (!wantsAutoStart) {
    autoStartIds = autoStartIds.filter((id) => id !== server.id);
  }
  await runAction("Agent settings saved", async () => {
    await api("/api/app-settings", {
      method: "PUT",
      body: JSON.stringify({
        close_to_tray: $("agent-close-to-tray").checked,
        auto_open_browser: $("agent-auto-open-browser").checked,
        start_on_boot: $("agent-start-on-boot").checked,
        auto_start_server_ids: autoStartIds,
      }),
    });
  });
}

async function saveSettings(restart) {
  const server = selectedServer();
  await runAction(restart ? "Settings saved and server restarted" : "Settings saved", async () => {
    await api(`/api/servers/${server.id}/properties${restart ? "/save-and-restart" : ""}`, {
      method: restart ? "POST" : "PUT",
      body: JSON.stringify({ properties: collectSettings() }),
    });
  });
}

async function changeServerVersion() {
  const server = selectedServer();
  const version = $("server-version-select")?.value;
  if (!server || !version || version === server.version) {
    toast("Choose a different Minecraft version first.");
    return;
  }
  if (!confirm(`Change this server from Minecraft ${server.version} to ${version}? Make a backup first if this world matters. The server must be stopped.`)) {
    return;
  }
  await runAction(`Minecraft version changed to ${version}`, async () => {
    await api(`/api/servers/${server.id}/version`, {
      method: "POST",
      body: JSON.stringify({ version }),
    });
  });
}

function renderConsole() {
  const server = selectedServer();
  if (!server) {
    $("console").innerHTML = noServerCard();
    return;
  }
  $("console").innerHTML = `
    <div class="card">
      <h2>Live-ish Console</h2>
      <p class="callout">Only send Minecraft server commands. Dangerous commands can affect worlds or players.</p>
      <div id="console-helper"></div>
      <pre id="console-lines" class="console">Loading...</pre>
      <div class="actions" style="margin-top:14px">
        <input id="command-input" placeholder="Example: say Server restarting in 5 minutes">
        <button class="primary" onclick="sendCommand()">Send</button>
        <button onclick="clearConsole()">Clear Display</button>
        <a class="button" href="/api/servers/${server.id}/log">Download Log</a>
      </div>
    </div>`;
  refreshConsole();
  clearInterval(state.consoleTimer);
  state.consoleTimer = setInterval(refreshConsole, 2500);
}

function consoleHelperForLines(lines) {
  const recent = lines.slice(-20).join("\n").toLowerCase();
  if (recent.includes("unpacking ") && recent.includes(".jar")) {
    return operationCard({
      active: true,
      title: "Minecraft is unpacking files",
      message: "This is normal during first start after a Minecraft update. It can sit here for a few minutes while Minecraft expands its own server files.",
      percent: null,
    });
  }
  const match = recent.match(/preparing spawn area:\s*(\d+)%/);
  if (match) {
    const percent = Number(match[1]);
    return operationCard({
      active: true,
      title: "Preparing spawn area",
      message: `Minecraft is building the initial world spawn area: ${percent}%.`,
      percent: 70 + Math.round(percent * 0.25),
    });
  }
  if (recent.includes("done (") && recent.includes("for help")) {
    return operationCard({
      active: false,
      title: "Server ready",
      message: "Minecraft finished starting. Friends can connect once networking is configured.",
      percent: 100,
    });
  }
  return "";
}

async function refreshConsole() {
  const server = selectedServer();
  if (!server || state.page !== "console") return;
  try {
    const data = await api(`/api/servers/${server.id}/console?limit=400`);
    $("console-helper").innerHTML = consoleHelperForLines(data.lines || []);
    $("console-lines").textContent = data.lines.join("\n") || "No console output yet.";
  } catch (error) {
    $("console-lines").textContent = error.message;
  }
}

async function sendCommand() {
  const server = selectedServer();
  const input = $("command-input");
  if (!input.value.trim()) return;
  await runAction("Command sent", async () => {
    await api(`/api/servers/${server.id}/command`, { method: "POST", body: JSON.stringify({ command: input.value }) });
    input.value = "";
    await refreshConsole();
  });
}

function clearConsole() {
  $("console-lines").textContent = "";
}

function resourceMeter(label, value, detail) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));
  return `
    <div class="resource-meter">
      <div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(detail)}</span></div>
      <div class="meter-track"><div class="meter-fill" style="width:${percent}%"></div></div>
    </div>`;
}

function commandButton(label, action, extra = {}) {
  const payload = encodeURIComponent(JSON.stringify({ action, ...extra }));
  return `<button type="button" onclick="runAdminCommand('${payload}')">${escapeHtml(label)}</button>`;
}

async function renderCommandCenter() {
  const server = selectedServer();
  if (!server) {
    $("command-center").innerHTML = noServerCard();
    return;
  }
  const data = await api(`/api/servers/${server.id}/command-center`);
  const resources = data.resources || {};
  const process = resources.process || {};
  const system = resources.system || {};
  const players = data.players || {};
  const onlinePlayers = players.online || [];
  const playerOptions = onlinePlayers.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
  const running = data.server?.status === "running";
  $("command-center").innerHTML = `
    <div class="command-hero card">
      <div>
        <p class="eyebrow">Admin command center</p>
        <h2>Fast controls for ${escapeHtml(data.server?.name || server.name)}</h2>
        <p class="muted">Use these buttons for common admin tasks without typing console commands. The Minecraft server must be running.</p>
      </div>
      <div class="actions">
        ${statusPill(data.server?.status)}
        <button class="primary" onclick="serverAction('start')" ${running ? "disabled" : ""}>Start Server</button>
        <button onclick="serverAction('stop')" ${running ? "" : "disabled"}>Stop Server</button>
      </div>
    </div>
    <div class="command-grid">
      <div class="card">
        <h2>Time</h2>
        <p class="muted">Change the world time for everyone.</p>
        <div class="quick-button-grid">
          ${commandButton("Day", "time-day")}
          ${commandButton("Noon", "time-noon")}
          ${commandButton("Night", "time-night")}
          ${commandButton("Midnight", "time-midnight")}
        </div>
      </div>
      <div class="card">
        <h2>Weather</h2>
        <p class="muted">Set the current world weather.</p>
        <div class="quick-button-grid">
          ${commandButton("Clear", "weather-clear")}
          ${commandButton("Rain", "weather-rain")}
          ${commandButton("Thunder", "weather-thunder")}
        </div>
      </div>
      <div class="card">
        <h2>Player action</h2>
        <p class="muted">Kick, ban, whitelist, or change admin status for one player.</p>
        <div class="form-grid">
          <label class="field">Player name<input id="admin-player" list="online-player-list" placeholder="Steve"></label>
          <label class="field">Reason, optional<input id="admin-reason" placeholder="Be kind"></label>
        </div>
        <datalist id="online-player-list">${playerOptions}</datalist>
        <div class="actions" style="margin-top:16px">
          <button onclick="runPlayerAdminCommand('kick')">Kick</button>
          <button class="danger" onclick="runPlayerAdminCommand('ban')">Ban</button>
          <button onclick="runPlayerAdminCommand('pardon')">Unban</button>
          <button onclick="runPlayerAdminCommand('whitelist-add')">Whitelist</button>
          <button onclick="runPlayerAdminCommand('op')">Make OP</button>
          <button onclick="runPlayerAdminCommand('deop')">Remove OP</button>
        </div>
        <p class="callout warning">Only give OP to people you trust. OP players can run powerful commands.</p>
      </div>
      <div class="card">
        <h2>Teleport</h2>
        <p class="muted">Move one online player to another player.</p>
        <div class="form-grid">
          <label class="field">Move player<input id="teleport-player" list="online-player-list" placeholder="Player to move"></label>
          <label class="field">To player<input id="teleport-target" list="online-player-list" placeholder="Destination player"></label>
        </div>
        <button class="primary" style="margin-top:16px" onclick="teleportPlayer()">Teleport Player</button>
      </div>
      <div class="card">
        <h2>Useful commands</h2>
        <p class="muted">Common admin utilities that are safer as buttons.</p>
        <div class="quick-button-grid">
          ${commandButton("Save World", "save-all")}
          ${commandButton("List Players", "list-players")}
          ${commandButton("Reload Whitelist", "whitelist-reload")}
          ${commandButton("Keep Inventory On", "keep-inventory-on")}
          ${commandButton("Keep Inventory Off", "keep-inventory-off")}
          ${commandButton("Daylight Cycle On", "daylight-cycle-on")}
          ${commandButton("Daylight Cycle Off", "daylight-cycle-off")}
          ${commandButton("Weather Cycle On", "weather-cycle-on")}
          ${commandButton("Weather Cycle Off", "weather-cycle-off")}
        </div>
      </div>
      <form id="announcement-form" class="card">
        <h2>Announcement</h2>
        <p class="muted">Send a visible server message to everyone online.</p>
        <label class="field">Message<input id="announcement-message" maxlength="200" placeholder="Server restarting in 5 minutes"></label>
        <button class="primary" style="margin-top:16px" type="submit">Send Announcement</button>
      </form>
      <div class="card">
        <h2>Resources</h2>
        <p class="muted">Quick health snapshot for this PC and Minecraft process.</p>
        <div class="resource-stack">
          ${system.available ? resourceMeter("PC CPU", system.cpu_percent, `${system.cpu_percent}% used`) : `<p class="muted">PC resource details are unavailable.</p>`}
          ${system.available ? resourceMeter("PC Memory", system.memory_percent, `${formatBytes((system.memory_used_mb || 0) * 1024 * 1024)} / ${formatBytes((system.memory_total_mb || 0) * 1024 * 1024)}`) : ""}
          ${system.available ? resourceMeter("Disk", system.disk_percent, `${system.disk_free_gb} GB free`) : ""}
          ${process.running ? resourceMeter("Minecraft RAM", Math.min(100, ((process.memory_mb || 0) / (data.server?.ram_mb || 4096)) * 100), `${process.memory_mb || 0} MB / ${data.server?.ram_mb || 4096} MB`) : `<p class="callout info">Minecraft is not running, so process CPU/RAM is unavailable.</p>`}
          <div class="list-item"><strong>Server folder</strong><span>${formatBytes(resources.server_disk?.bytes || 0)} · ${resources.server_disk?.files || 0} files</span></div>
        </div>
      </div>
      <div class="card">
        <h2>Online players</h2>
        <p class="muted">${onlinePlayers.length ? onlinePlayers.map(escapeHtml).join(", ") : "No online players detected yet. The server must log joins/leaves for this list."}</p>
        <pre class="console mini-console">${(data.recent_console || []).map(escapeHtml).join("\n") || "No recent console output."}</pre>
      </div>
    </div>`;
  $("announcement-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = $("announcement-message").value.trim();
    if (!message) {
      toast("Enter an announcement first.", "error");
      return;
    }
    await runAdminCommand(encodeURIComponent(JSON.stringify({ action: "announce", message })));
    $("announcement-message").value = "";
  });
}

async function runAdminCommand(encodedPayload) {
  const server = selectedServer();
  const payload = JSON.parse(decodeURIComponent(encodedPayload));
  await runAction("Admin command sent", async () => {
    await api(`/api/servers/${server.id}/admin-command`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  });
}

async function setTimeDay() {
  await runAdminCommand(encodeURIComponent(JSON.stringify({ action: "time-day" })));
}

async function runPlayerAdminCommand(action) {
  const player = $("admin-player").value.trim();
  const reason = $("admin-reason").value.trim();
  if (!player) {
    toast("Enter a player name first.", "error");
    return;
  }
  await runAdminCommand(encodeURIComponent(JSON.stringify({ action, player, reason })));
}

async function teleportPlayer() {
  const player = $("teleport-player").value.trim();
  const target = $("teleport-target").value.trim();
  if (!player || !target) {
    toast("Enter both player names first.", "error");
    return;
  }
  await runAdminCommand(encodeURIComponent(JSON.stringify({ action: "teleport-to-player", player, target })));
}

async function renderBackups() {
  const server = selectedServer();
  if (!server) {
    $("backups").innerHTML = noServerCard();
    return;
  }
  const [backups, schedule] = await Promise.all([
    api(`/api/servers/${server.id}/backups`),
    api(`/api/servers/${server.id}/backup-schedule`),
  ]);
  $("backups").innerHTML = `
    <div class="split">
      <div class="card">
        <h2>Backups</h2>
        <p class="muted">Create a backup before big changes. Restore requires the server to be stopped.</p>
        <button class="primary" onclick="createBackup()">Create Backup Now</button>
        <div class="table-list" style="margin-top:16px">
          ${backups.length ? backups.map((backup) => `
            <div class="list-item">
              <div><strong>${backup.name}</strong><br><span class="muted">${formatBytes(backup.size_bytes)} · ${new Date(backup.created_at).toLocaleString()}</span></div>
              <div class="actions">
                <button onclick="restoreBackup('${backup.name}')">Restore</button>
                <button class="danger" onclick="deleteBackup('${backup.name}')">Delete</button>
              </div>
            </div>`).join("") : `<p class="muted">No backups yet.</p>`}
        </div>
      </div>
      <form id="backup-schedule-form" class="card">
        <h2>Automatic backups</h2>
        <p class="muted">Runs only while MineHost Helper is open. If the server is running at backup time, MineHost Helper waits and tries again later.</p>
        <div class="form-grid">
          <label class="field"><span><input name="enabled" type="checkbox" ${schedule.enabled ? "checked" : ""}> Turn on automatic backups</span></label>
          <label class="field">Every how many hours<input name="interval_hours" type="number" min="1" max="168" value="${schedule.interval_hours}"></label>
          <label class="field">Keep how many backups<input name="retention_count" type="number" min="1" max="100" value="${schedule.retention_count}"></label>
        </div>
        <p class="callout info">Last backup: ${schedule.last_run_at ? new Date(schedule.last_run_at).toLocaleString() : "not yet"}<br>Next backup: ${schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "not scheduled"}</p>
        <button class="primary" type="submit">Save Schedule</button>
      </form>
    </div>`;
  $("backup-schedule-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    await runAction("Backup schedule saved", async () => {
      await api(`/api/servers/${server.id}/backup-schedule`, {
        method: "PUT",
        body: JSON.stringify({
          enabled: form.has("enabled"),
          interval_hours: Number(form.get("interval_hours")),
          retention_count: Number(form.get("retention_count")),
        }),
      });
    });
  });
}

async function renderPlayers() {
  const server = selectedServer();
  if (!server) {
    $("players").innerHTML = noServerCard();
    return;
  }
  const data = await api(`/api/servers/${server.id}/players`);
  const listNames = (items) => items.map((item) => escapeHtml(item.name || item.uuid || JSON.stringify(item))).join(", ") || "None";
  $("players").innerHTML = `
    <div class="split">
      <div class="card">
        <h2>Player controls</h2>
        <p class="muted">These buttons send safe Minecraft console commands. The server must be running for changes.</p>
        <div class="form-grid">
          <label class="field">Player name<input id="player-name" placeholder="Steve"></label>
          <label class="field">Reason, optional<input id="player-reason" placeholder="Be kind"></label>
        </div>
        <div class="actions" style="margin-top:16px">
          <button onclick="playerAction('whitelist-add')">Whitelist</button>
          <button onclick="playerAction('op')">Make OP</button>
          <button onclick="playerAction('deop')">Remove OP</button>
          <button onclick="playerAction('kick')">Kick</button>
          <button class="danger" onclick="playerAction('ban')">Ban</button>
          <button onclick="playerAction('pardon')">Unban</button>
        </div>
        <p class="callout">Avoid giving OP to people you do not fully trust. OP players can change worlds and run powerful commands.</p>
      </div>
      <div class="card">
        <h2>Known players</h2>
        <div class="table-list">
          <div class="list-item"><strong>Recently online</strong><span>${data.online.map(escapeHtml).join(", ") || "None detected yet"}</span></div>
          <div class="list-item"><strong>Whitelist</strong><span>${listNames(data.whitelist)}</span></div>
          <div class="list-item"><strong>OPs</strong><span>${listNames(data.ops)}</span></div>
          <div class="list-item"><strong>Banned</strong><span>${listNames(data.banned_players)}</span></div>
        </div>
      </div>
    </div>`;
}

async function playerAction(action) {
  const server = selectedServer();
  const player = $("player-name").value.trim();
  const reason = $("player-reason").value.trim();
  if (!player) {
    toast("Enter a player name first.", "error");
    return;
  }
  await runAction("Player command sent", async () => {
    await api(`/api/servers/${server.id}/players/${action}`, {
      method: "POST",
      body: JSON.stringify({ player, reason }),
    });
  });
}

async function renderFiles() {
  const server = selectedServer();
  if (!server) {
    $("files").innerHTML = noServerCard();
    return;
  }
  const data = await api(`/api/servers/${server.id}/files?path=${encodeURIComponent(state.filePath || "")}`);
  const parent = data.path ? data.path.split("/").slice(0, -1).join("/") : "";
  $("files").innerHTML = `
    <div class="split">
      <div class="card">
        <h2>Server files</h2>
        <p class="muted">Safe browser for this server folder. Text/config files can be opened and saved with an automatic backup copy.</p>
        <p class="callout info">Current folder: ${escapeHtml(data.path || "/")}</p>
        <div class="table-list">
          ${data.path ? `<div class="list-item"><strong>..</strong><button onclick="openFolder('${jsArg(parent)}')">Up</button></div>` : ""}
          ${data.entries.map((entry) => `
            <div class="list-item">
              <div><strong>${entry.type === "folder" ? "Folder" : "File"} ${escapeHtml(entry.name)}</strong><br><span class="muted">${entry.size_bytes ? formatBytes(entry.size_bytes) : ""}</span></div>
              <div class="actions">
                ${entry.type === "folder" ? `<button onclick="openFolder('${jsArg(entry.path)}')">Open</button>` : ""}
                ${entry.editable ? `<button onclick="openFile('${jsArg(entry.path)}')">Edit</button>` : ""}
              </div>
            </div>`).join("")}
        </div>
      </div>
      <div class="card">
        <h2>Editor</h2>
        <p id="file-editor-path" class="muted">Choose an editable text/config file.</p>
        <textarea id="file-editor" placeholder="File contents will appear here"></textarea>
        <div class="actions" style="margin-top:12px">
          <button class="primary" onclick="saveOpenFile()">Save File</button>
        </div>
      </div>
    </div>`;
}

function openFolder(path) {
  state.filePath = decodeURIComponent(path || "");
  renderFiles();
}

async function openFile(path) {
  const server = selectedServer();
  const decodedPath = decodeURIComponent(path || "");
  const data = await api(`/api/servers/${server.id}/files/read?path=${encodeURIComponent(decodedPath)}`);
  $("file-editor-path").textContent = data.path;
  $("file-editor-path").dataset.path = data.path;
  $("file-editor").value = data.content;
}

async function saveOpenFile() {
  const server = selectedServer();
  const path = $("file-editor-path").dataset.path;
  if (!path) {
    toast("Open a file first.", "error");
    return;
  }
  await runAction("File saved", async () => {
    await api(`/api/servers/${server.id}/files/write?path=${encodeURIComponent(path)}`, {
      method: "PUT",
      body: JSON.stringify({ content: $("file-editor").value }),
    });
  });
}

async function renderWorldMap() {
  const server = selectedServer();
  if (!server) {
    $("world-map").innerHTML = noServerCard();
    return;
  }
  const dimension = state.mapDimension || "overworld";
  const data = await api(`/api/servers/${server.id}/world-map?dimension=${encodeURIComponent(dimension)}`);
  state.mapDimension = data.dimension || dimension;
  $("world-map").innerHTML = `
    <div class="map-layout">
      <div class="card">
        <div class="map-head">
          <div>
            <p class="eyebrow">Vanilla world explorer</p>
            <h2>${escapeHtml(data.label)} explored map</h2>
            <p class="muted">Shows chunks saved in vanilla Minecraft region files. This is an explored-area overview, not a live terrain render.</p>
          </div>
          <div class="actions">
            <button class="primary" onclick="renderWorldMap()">Refresh Map</button>
          </div>
        </div>
        <div class="dimension-tabs">
          ${(data.dimensions || []).map((item) => `
            <button class="${item.id === data.dimension ? "primary" : ""}" onclick="selectMapDimension('${escapeHtml(item.id)}')" ${item.available ? "" : "disabled"}>
              ${escapeHtml(item.label)}${item.available ? "" : " (not found)"}
            </button>
          `).join("")}
        </div>
        <div class="map-canvas-wrap">
          <canvas id="world-map-canvas" width="1100" height="720" aria-label="Explored chunk map"></canvas>
        </div>
        <p class="callout info">${escapeHtml(data.safe_refresh_note || data.note || "Use Refresh Map after players explore new areas.")}</p>
      </div>
      <div class="card">
        <h2>Map details</h2>
        <div class="table-list">
          <div class="list-item"><strong>World folder</strong><span>${escapeHtml(data.world_name || "world")}</span></div>
          <div class="list-item"><strong>Dimension</strong><span>${escapeHtml(data.label)}</span></div>
          <div class="list-item"><strong>Explored chunks</strong><span>${data.chunk_count}</span></div>
          <div class="list-item"><strong>Region files with chunks</strong><span>${data.region_count}</span></div>
          <div class="list-item"><strong>Server status</strong><span>${escapeHtml(data.server_status || server.status)}</span></div>
        </div>
        <p class="callout warning">For the safest full refresh, stop the server first. Reading headers while running is lightweight, but Minecraft may save newly explored chunks after this scan.</p>
        <h3 style="margin-top:18px">How to read this map</h3>
        <p class="muted">Each square is one generated chunk. North is up. The crosshair marks chunk 0,0 near world spawn for most vanilla worlds.</p>
      </div>
    </div>`;
  drawWorldMap(data);
}

function selectMapDimension(dimension) {
  state.mapDimension = dimension;
  renderWorldMap();
}

function drawWorldMap(data) {
  const canvas = $("world-map-canvas");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const cssWidth = Math.max(720, Math.floor(rect.width || 1100));
  const cssHeight = 720;
  canvas.width = Math.floor(cssWidth * ratio);
  canvas.height = Math.floor(cssHeight * ratio);
  canvas.style.height = `${cssHeight}px`;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, cssWidth, cssHeight);
  const chunks = data.chunks || [];
  const gradient = context.createLinearGradient(0, 0, cssWidth, cssHeight);
  gradient.addColorStop(0, "rgba(223, 240, 200, 0.92)");
  gradient.addColorStop(1, "rgba(248, 234, 209, 0.92)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, cssWidth, cssHeight);
  drawMapGrid(context, cssWidth, cssHeight);
  if (!chunks.length) {
    context.fillStyle = "#657360";
    context.font = "800 22px Bahnschrift, Segoe UI, sans-serif";
    context.textAlign = "center";
    context.fillText(data.available ? "No explored chunks found yet." : "No vanilla region folder found for this dimension.", cssWidth / 2, cssHeight / 2);
    return;
  }
  const bounds = data.bounds || {};
  const minX = Number(bounds.min_x);
  const maxX = Number(bounds.max_x);
  const minZ = Number(bounds.min_z);
  const maxZ = Number(bounds.max_z);
  const padding = 44;
  const spanX = Math.max(1, maxX - minX + 1);
  const spanZ = Math.max(1, maxZ - minZ + 1);
  const cell = Math.max(2, Math.min((cssWidth - padding * 2) / spanX, (cssHeight - padding * 2) / spanZ));
  const mapWidth = spanX * cell;
  const mapHeight = spanZ * cell;
  const startX = (cssWidth - mapWidth) / 2;
  const startY = (cssHeight - mapHeight) / 2;
  context.fillStyle = "rgba(31, 111, 67, 0.9)";
  for (const chunk of chunks) {
    const x = startX + (chunk.x - minX) * cell;
    const y = startY + (chunk.z - minZ) * cell;
    context.fillRect(x, y, Math.max(1, cell - 0.35), Math.max(1, cell - 0.35));
  }
  drawAxis(context, startX, startY, cell, minX, minZ, spanX, spanZ, cssWidth, cssHeight);
}

function drawMapGrid(context, width, height) {
  context.save();
  context.strokeStyle = "rgba(90, 56, 35, 0.08)";
  context.lineWidth = 1;
  for (let x = 0; x <= width; x += 38) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  for (let y = 0; y <= height; y += 38) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }
  context.restore();
}

function drawAxis(context, startX, startY, cell, minX, minZ, spanX, spanZ, width, height) {
  context.save();
  context.strokeStyle = "rgba(226, 76, 67, 0.7)";
  context.fillStyle = "rgba(18, 23, 19, 0.8)";
  context.lineWidth = 2;
  if (minX <= 0 && minX + spanX > 0) {
    const zeroX = startX + (0 - minX) * cell + cell / 2;
    context.beginPath();
    context.moveTo(zeroX, Math.max(0, startY - 20));
    context.lineTo(zeroX, Math.min(height, startY + spanZ * cell + 20));
    context.stroke();
  }
  if (minZ <= 0 && minZ + spanZ > 0) {
    const zeroY = startY + (0 - minZ) * cell + cell / 2;
    context.beginPath();
    context.moveTo(Math.max(0, startX - 20), zeroY);
    context.lineTo(Math.min(width, startX + spanX * cell + 20), zeroY);
    context.stroke();
  }
  context.font = "800 13px Bahnschrift, Segoe UI, sans-serif";
  context.fillText(`X ${minX} to ${minX + spanX - 1}`, 18, height - 22);
  context.fillText(`Z ${minZ} to ${minZ + spanZ - 1}`, 18, height - 42);
  context.restore();
}

async function createBackup() {
  const server = selectedServer();
  await runAction("Backup created", async () => api(`/api/servers/${server.id}/backups`, { method: "POST" }));
}

async function restoreBackup(name) {
  if (!confirm("Restore this backup? The server must be stopped. MineHost Helper creates a safety backup first.")) return;
  const server = selectedServer();
  await runAction("Backup restored", async () => api(`/api/servers/${server.id}/backups/${encodeURIComponent(name)}/restore`, { method: "POST" }));
}

async function deleteBackup(name) {
  if (!confirm("Delete this backup permanently?")) return;
  const server = selectedServer();
  await runAction("Backup deleted", async () => api(`/api/servers/${server.id}/backups/${encodeURIComponent(name)}`, { method: "DELETE" }));
}

async function renderNetworking() {
  const data = await api(`/api/networking/status${state.selectedId ? `?server_id=${state.selectedId}` : ""}`);
  $("networking").innerHTML = `
    <div class="split">
      <div class="card">
        <h2>Connection Check</h2>
        <div class="table-list">
          <div class="list-item"><strong>Local IP</strong><span>${data.local_ip || "Unknown"}</span></div>
          <div class="list-item"><strong>Public IP</strong><span>${data.public_ip || "Unknown"}</span></div>
          <div class="list-item"><strong>Minecraft TCP port</strong><span>${data.port}</span></div>
          <div class="list-item"><strong>Local port test</strong><span>${data.local_open ? "Open" : "Closed"}</span></div>
          <div class="list-item"><strong>Windows Firewall rule</strong><span>${data.firewall.exists ? "Found" : "Missing"}</span></div>
          <div class="list-item"><strong>Public test</strong><span>${data.public.state}</span></div>
        </div>
        <div class="actions" style="margin-top:16px">
          <button class="primary" onclick="fixFirewall(${data.port})">Fix Windows Firewall</button>
          <button onclick="testLocalPort(${data.port})">Test Local Port</button>
          <button onclick="testPublicPort(${data.port})">Test Public Port</button>
          <button onclick="tryUpnp()">Try Automatic Router Setup</button>
          <button onclick="copyText('${data.public_ip || "PUBLIC_IP"}:${data.port}')">Copy Server Address</button>
        </div>
        <p class="callout info">${data.public.details}</p>
        <div id="public-test-result" class="callout hidden" style="margin-top:12px"></div>
      </div>
      <div class="card">
        <h2>Router instructions</h2>
        <ol>${data.router_instructions.map((step) => `<li>${step}</li>`).join("")}</ol>
        <p class="callout">If public testing still fails after firewall and router forwarding, you may have CGNAT or double NAT. The Help page explains what that means.</p>
      </div>
    </div>`;
}

async function fixFirewall(port) {
  if (!confirm(`Create a Windows Firewall inbound TCP rule only for port ${port}? Windows may require Administrator permission.`)) return;
  await runAction("Firewall rule attempted", async () => {
    const data = await api("/api/networking/firewall/fix", { method: "POST", body: JSON.stringify({ port }) });
    if (!data.success) throw new Error(`Run as Administrator or copy this command: ${data.admin_command}`);
  });
}

async function testLocalPort(port) {
  await runAction("Local port checked", async () => {
    const data = await api(`/api/networking/local-port-test?port=${port}`);
    toast(data.open ? "Local Minecraft port is open" : "Local port is closed. Start the server first.", data.open ? "ok" : "error");
  });
}

async function testPublicPort(port) {
  await runAction("Public test checked", async () => {
    const data = await api(`/api/networking/public-port-test?port=${port}`);
    const result = $("public-test-result");
    const type = data.reachable === true ? "ok" : data.reachable === false ? "error" : "warning";
    if (result) {
      result.className = `callout ${type === "error" ? "danger" : type === "warning" ? "warning" : "success"}`;
      result.innerHTML = `<strong>${escapeHtml(data.state)}</strong><br>${escapeHtml(data.details)}`;
    }
    toast(`${data.state}: ${data.details}`, type);
  });
}

async function tryUpnp() {
  await runAction("Router setup checked", async () => {
    const data = await api("/api/networking/router/upnp", { method: "POST" });
    if (!data.success) throw new Error(data.message);
  });
}

async function renderHelp() {
  const server = selectedServer();
  const [update, diagnostics, discord] = await Promise.all([
    api("/api/app/update-check"),
    server ? api(`/api/servers/${server.id}/diagnostics`) : Promise.resolve(null),
    api("/api/discord/settings"),
  ]);
  $("help").innerHTML = `
    <div class="split">
      <div class="card">
        <h2>App update</h2>
        <p class="muted">Installed version: ${escapeHtml(update.current_version)}<br>Latest version: ${escapeHtml(update.latest_version || "unknown")}</p>
        ${update.error ? `<p class="callout warning">Could not check GitHub right now: ${escapeHtml(update.error)}</p>` : ""}
        ${update.update_available ? `<p class="callout success">A newer MineHost Helper is available.</p>` : `<p class="callout info">MineHost Helper appears up to date.</p>`}
        <div class="actions">
          <button class="primary" onclick="window.open('${escapeHtml(update.download_url)}', '_blank')">Download Latest Installer</button>
          ${update.release_url ? `<button onclick="window.open('${escapeHtml(update.release_url)}', '_blank')">Release Notes</button>` : ""}
        </div>
      </div>
      <form id="discord-form" class="card">
        <h2>Discord notifications</h2>
        <p class="muted">Paste a Discord webhook and MineHost Helper can post simple server updates for your friend group.</p>
        <p class="callout ${discord.configured ? "success" : "info"}">${discord.configured ? "Discord webhook is saved. The full URL is hidden for safety." : "No Discord webhook is configured yet."}</p>
        <div class="form-grid">
          <label class="field">Webhook URL
            <span class="field-hint">Discord: Server Settings > Integrations > Webhooks > Copy Webhook URL.</span>
            <input name="webhook_url" type="password" placeholder="${discord.configured ? "Leave blank to keep current webhook" : "https://discord.com/api/webhooks/..."}" autocomplete="off">
          </label>
          <label class="field">Bot name
            <span class="field-hint">This is the name Discord shows for MineHost messages.</span>
            <input name="webhook_name" value="${escapeHtml(discord.webhook_name || "MineHost Helper")}">
          </label>
          <label class="field"><span><input name="enabled" type="checkbox" ${discord.enabled ? "checked" : ""}> Enable Discord notifications</span></label>
        </div>
        <p class="callout warning">Treat webhook URLs like passwords. Anyone with the URL can post into that Discord channel.</p>
        <div class="actions" style="margin-top:16px">
          <button class="primary" type="submit">Save Discord Setup</button>
          <button type="button" onclick="testDiscord()">Send Test Message</button>
          <button type="button" onclick="clearDiscord()">Clear Webhook</button>
        </div>
      </form>
      <div class="card">
        <h2>Problem explainer</h2>
        <p class="muted">MineHost Helper scans recent logs for common Minecraft startup problems.</p>
        ${diagnostics ? `
          <div class="table-list">
            <div class="list-item"><strong>Server folder size</strong><span>${formatBytes(diagnostics.disk.bytes)} · ${diagnostics.disk.files} files</span></div>
            ${diagnostics.findings.map((finding) => `
              <div class="list-item">
                <div><strong>${escapeHtml(finding.title)}</strong><br><span class="muted">${escapeHtml(finding.advice)}</span>${finding.evidence ? `<br><code>${escapeHtml(finding.evidence)}</code>` : ""}</div>
                <span class="pill ${finding.severity === "ok" ? "running" : finding.severity === "warning" ? "warning" : "error"}">${escapeHtml(finding.severity)}</span>
              </div>`).join("")}
          </div>` : `<p class="muted">Create or select a server to see diagnostics.</p>`}
      </div>
      <div class="card">
        <h2>Plain-English hosting notes</h2>
        <p>Friends inside your house use your local IP, usually like <code>192.168.1.50:25565</code>.</p>
        <p>Friends outside your house usually use your public IP, like <code>73.x.x.x:25565</code>.</p>
        <p>Your router must forward TCP port 25565, or your configured port, to this PC's local IP.</p>
        <p>Give this PC a DHCP reservation in your router so its local IP does not change.</p>
      </div>
      <div class="card">
        <h2>Troubleshooting</h2>
        <p><strong>CGNAT:</strong> Your internet provider may not give you a real public IPv4 address. Port forwarding may not work until they provide one.</p>
        <p><strong>Double NAT:</strong> Two routers in a row can block forwarding. Put one router in bridge mode or forward on both.</p>
        <p><strong>Firewall:</strong> MineHost Helper opens only the configured Minecraft TCP port when you ask it to.</p>
        <p><strong>RCON:</strong> Disabled by default. Only enable it with a strong password.</p>
      </div>
    </div>`;
  $("discord-form").addEventListener("submit", (event) => {
    event.preventDefault();
    saveDiscord();
  });
}

async function saveDiscord() {
  const form = new FormData($("discord-form"));
  const payload = {
    enabled: form.has("enabled"),
    webhook_name: String(form.get("webhook_name") || "MineHost Helper"),
  };
  const webhookUrl = String(form.get("webhook_url") || "").trim();
  if (webhookUrl) payload.webhook_url = webhookUrl;
  await runAction("Discord setup saved", async () => {
    await api("/api/discord/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    await renderHelp();
  });
}

async function testDiscord() {
  await runAction("Discord test sent", async () => {
    await api("/api/discord/test", { method: "POST" });
  });
}

async function clearDiscord() {
  if (!confirm("Clear the saved Discord webhook? MineHost Helper will stop sending Discord notifications.")) return;
  await runAction("Discord webhook cleared", async () => {
    await api("/api/discord/settings", {
      method: "PUT",
      body: JSON.stringify({ clear: true }),
    });
    await renderHelp();
  });
}

async function serverAction(action) {
  const server = selectedServer();
  if (action === "start" && state.dashboard?.port_check?.available === false) {
    toast("Fix the port conflict first. Use the buttons in the Port needs attention card.", "error");
    return;
  }
  await runAction(`Server ${action} requested`, async () => {
    await api(`/api/servers/${server.id}/${action}`, { method: "POST" });
    if (action === "start" || action === "restart" || action === "stop") {
      startDashboardPolling();
    }
  });
}

async function fixPortConflict(action) {
  const server = selectedServer();
  if (!server) return;
  const labels = {
    "stop-owner": "Old server process stopped",
    "use-next-port": "Server changed to an open port",
  };
  if (action === "stop-owner" && !confirm("Stop the old MineHost Minecraft process using this port? This is safe for an orphaned MineHost server, but connected players on that old process will be disconnected.")) {
    return;
  }
  if (action === "use-next-port" && !confirm("Change this Minecraft server to the next open port? Friends will need the new address shown on the Dashboard.")) {
    return;
  }
  await runAction(labels[action] || "Port conflict fixed", async () => {
    await api(`/api/servers/${server.id}/port-conflict/${action}`, { method: "POST" });
  });
}

async function forceKill() {
  if (!confirm("Force kill is only for emergencies. Use Stop first when possible. Continue?")) return;
  await serverAction("kill");
}

async function copyText(text) {
  await navigator.clipboard.writeText(text);
  toast("Copied to clipboard");
}

function go(page) {
  location.hash = page;
  if (page === "setup") {
    state.setupMode = "choice";
    state.setupStep = 1;
  }
}

async function render() {
  clearInterval(state.consoleTimer);
  state.consoleTimer = null;
  clearInterval(state.dashboardTimer);
  state.dashboardTimer = null;
  const requestedPage = location.hash.replace("#", "") || "dashboard";
  state.page = titles[requestedPage] ? requestedPage : "dashboard";
  try {
    await refreshData();
    if (!state.servers.length && state.page === "dashboard") {
      state.page = "setup";
      state.setupMode = "choice";
      state.setupStep = 1;
    }
    $("page-title").textContent = titles[state.page];
    document.querySelectorAll(".page").forEach((node) => node.classList.toggle("hidden", node.id !== state.page));
    document.querySelectorAll("nav a").forEach((node) => node.classList.toggle("active", node.dataset.page === state.page));
    renderQuickDrawer();
    startQuickDrawerPolling();
    if (state.page === "dashboard") {
      renderDashboard();
      startDashboardPolling();
    }
    if (state.page === "command-center") await renderCommandCenter();
    if (state.page === "setup") renderSetup();
    if (state.page === "settings") await renderSettings();
    if (state.page === "console") renderConsole();
    if (state.page === "players") await renderPlayers();
    if (state.page === "files") await renderFiles();
    if (state.page === "world-map") await renderWorldMap();
    if (state.page === "backups") await renderBackups();
    if (state.page === "networking") await renderNetworking();
    if (state.page === "help") await renderHelp();
  } catch (error) {
    if (error.status === 401) {
      const status = await api("/api/auth/status");
      renderLogin(status);
      return;
    }
    $("page-title").textContent = titles[state.page] || "MineHost Helper";
    document.querySelectorAll(".page").forEach((node) => node.classList.toggle("hidden", node.id !== state.page));
    document.querySelectorAll("nav a").forEach((node) => node.classList.toggle("active", node.dataset.page === state.page));
    $(state.page).innerHTML = `<div class="card"><h2>Could not load this page</h2><p class="muted">${error.message}</p></div>`;
    toast(error.message, "error");
  }
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" }).catch(() => null);
  location.reload();
}

function startDashboardPolling() {
  if (state.page !== "dashboard" || state.dashboardTimer) return;
  const server = selectedServer();
  const shouldPoll = server && (["starting", "running", "stopping"].includes(server.status) || server.operation?.active);
  if (!shouldPoll) return;
  state.dashboardTimer = setInterval(async () => {
    if (state.page !== "dashboard") {
      clearInterval(state.dashboardTimer);
      state.dashboardTimer = null;
      return;
    }
    try {
      await refreshData();
      renderQuickDrawer();
      renderDashboard();
      const current = selectedServer();
      if (!current || (!["starting", "running", "stopping"].includes(current.status) && !current.operation?.active)) {
        clearInterval(state.dashboardTimer);
        state.dashboardTimer = null;
      }
    } catch {
      clearInterval(state.dashboardTimer);
      state.dashboardTimer = null;
    }
  }, 2500);
}

$("server-select").addEventListener("change", (event) => {
  state.selectedId = event.target.value;
  localStorage.setItem("selectedServer", state.selectedId);
  render();
});

$("theme-toggle").addEventListener("click", toggleTheme);
$("logout-button").addEventListener("click", logout);
window.addEventListener("hashchange", render);
applyTheme(state.theme);
ensureAuthenticated().then((authenticated) => {
  if (authenticated) render();
});
