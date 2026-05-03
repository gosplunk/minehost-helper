const state = {
  page: location.hash.replace("#", "") || "dashboard",
  servers: [],
  selectedId: localStorage.getItem("selectedServer") || "",
  dashboard: null,
  consoleTimer: null,
  dashboardTimer: null,
  theme: document.documentElement.dataset.theme || "light",
};

const titles = {
  dashboard: "Dashboard",
  setup: "Setup Wizard",
  settings: "Server Settings",
  console: "Console",
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
    throw new Error(message);
  }
  return data;
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
      <button class="primary" onclick="go('setup')">Open Setup Wizard</button>
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
        <p class="muted">RAM ${server.ram_mb} MB · Port ${server.port} · ${process.uptime_seconds ? `Uptime ${Math.floor(process.uptime_seconds / 60)} min` : "Not running"}</p>
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
    <div class="card-grid" style="margin-top:18px">
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
  $("setup").innerHTML = `
    <div class="split">
      <form id="setup-form" class="card">
        <h2>Create a Minecraft server</h2>
        <p class="muted">Choose simple defaults now. You can change settings later without editing files.</p>
        <div class="form-grid">
          <label class="field">Server name<input name="name" required value="Family Minecraft"></label>
          <label class="field">Minecraft version<select name="version" id="version-select"><option value="latest">Latest stable release</option></select></label>
          <label class="field">RAM<select name="ramChoice"><option value="4096">4 GB recommended</option><option value="2048">2 GB small</option><option value="6144">6 GB larger</option><option value="custom">Custom</option></select></label>
          <label class="field">Custom RAM MB<input name="customRam" type="number" min="512" max="65536" value="4096"></label>
          <label class="field">Server port<input name="port" type="number" min="1" max="65535" value="25565"></label>
          <label class="field">World name<input name="world_name" value="world"></label>
          <label class="field">Gamemode<select name="gamemode"><option>survival</option><option>creative</option><option>adventure</option><option>spectator</option></select></label>
          <label class="field">Difficulty<select name="difficulty"><option>easy</option><option>normal</option><option>hard</option><option>peaceful</option></select></label>
          <label class="field">Max players<input name="max_players" type="number" min="1" max="200" value="10"></label>
          <label class="field">Message of the day<input name="motd" value="A MineHost Helper server"></label>
          <label class="field"><span><input name="online_mode" type="checkbox" checked> Online mode</span></label>
          <label class="field"><span><input name="whitelist" type="checkbox"> Whitelist</span></label>
          <label class="field"><span><input name="command_blocks" type="checkbox"> Command blocks</span></label>
          <label class="field"><span><input name="accepted_eula" type="checkbox" required> I accept the Minecraft EULA</span></label>
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
          <p id="setup-progress-message">Downloading Minecraft and writing safe defaults. This can take a few minutes.</p>
          <div class="progress-track indeterminate" role="progressbar"><div class="progress-fill"></div></div>
          <p class="muted">Keep this page open. MineHost Helper will move you to the dashboard when it is done.</p>
        </div>
      </form>
      <div class="card">
        <h2>First run checklist</h2>
        <p>MineHost Helper will:</p>
        <p class="muted">Download the selected server jar from Mojang, use bundled or system Java, write safe server.properties, and keep files in this folder.</p>
        <button onclick="installJava()">Download Temurin Java Now</button>
        <div id="java-status" class="muted" style="margin-top:12px">Checking Java...</div>
      </div>
    </div>`;
  loadVersions();
  loadJavaStatus();
  $("setup-form").addEventListener("submit", createServerFromForm);
}

async function loadVersions() {
  try {
    const data = await api("/api/minecraft/versions");
    const select = $("version-select");
    select.innerHTML = `<option value="latest">Latest stable release (${data.latest})</option>`;
    data.releases.forEach((version) => {
      select.insertAdjacentHTML("beforeend", `<option value="${version.id}">${version.id}</option>`);
    });
  } catch (error) {
    toast(`Version list unavailable: ${error.message}`, "error");
  }
}

async function loadJavaStatus() {
  try {
    const data = await api("/api/java/status");
    $("java-status").textContent = data.available ? `Java ready: ${data.version}` : "Java not found. MineHost Helper can download Temurin Java.";
  } catch {
    $("java-status").textContent = "Java status could not be checked.";
  }
}

async function installJava() {
  await runAction("Java is ready", async () => {
    $("java-status").innerHTML = `<span class="spinner inline" aria-hidden="true"></span> Downloading Java. This can take a few minutes.`;
    const data = await api("/api/java/install", { method: "POST" });
    $("java-status").textContent = `Java ready: ${data.version}`;
  });
}

async function createServerFromForm(event) {
  event.preventDefault();
  const button = $("create-server-button");
  const progress = $("setup-progress");
  button.disabled = true;
  button.textContent = "Creating...";
  progress.classList.remove("hidden");
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
  try {
    const server = await api("/api/servers", { method: "POST", body: JSON.stringify(payload) });
    state.selectedId = server.id;
    toast("Server created");
    go("dashboard");
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
    button.textContent = "Create Server";
    progress.classList.add("hidden");
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

async function renderBackups() {
  const server = selectedServer();
  if (!server) {
    $("backups").innerHTML = noServerCard();
    return;
  }
  const backups = await api(`/api/servers/${server.id}/backups`);
  $("backups").innerHTML = `
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
    </div>`;
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

function renderHelp() {
  $("help").innerHTML = `
    <div class="split">
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
}

async function render() {
  clearInterval(state.consoleTimer);
  state.consoleTimer = null;
  clearInterval(state.dashboardTimer);
  state.dashboardTimer = null;
  state.page = location.hash.replace("#", "") || "dashboard";
  if (!titles[state.page]) state.page = "dashboard";
  $("page-title").textContent = titles[state.page];
  document.querySelectorAll(".page").forEach((node) => node.classList.toggle("hidden", node.id !== state.page));
  document.querySelectorAll("nav a").forEach((node) => node.classList.toggle("active", node.dataset.page === state.page));
  try {
    await refreshData();
    if (state.page === "dashboard") {
      renderDashboard();
      startDashboardPolling();
    }
    if (state.page === "setup") renderSetup();
    if (state.page === "settings") await renderSettings();
    if (state.page === "console") renderConsole();
    if (state.page === "backups") await renderBackups();
    if (state.page === "networking") await renderNetworking();
    if (state.page === "help") renderHelp();
  } catch (error) {
    $(state.page).innerHTML = `<div class="card"><h2>Could not load this page</h2><p class="muted">${error.message}</p></div>`;
    toast(error.message, "error");
  }
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
window.addEventListener("hashchange", render);
applyTheme(state.theme);
render();
