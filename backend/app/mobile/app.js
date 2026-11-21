const login = document.querySelector("#login");
const home = document.querySelector("#home");
const notice = document.querySelector("#notice");
const signout = document.querySelector("#signout");
const sheet = document.querySelector("#sheet");
const form = document.querySelector("#action-form");
const receipt = document.querySelector("#receipt");
let mfaToken = "";
let homeBody = null;
let action = null;
let generation = 0;

function headers(json) {
  const value = { "X-Tradeguard-Request": "1" };
  if (json) value["Content-Type"] = "application/json";
  return value;
}

function errorText(body, fallback) {
  const detail = body && body.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const text = detail.map((item) => item.msg || item.message || "").filter(Boolean).join(" ");
    if (text) return text;
  }
  return fallback;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: headers(Boolean(options.body)),
    ...options,
  });
  const text = await response.text();
  let body = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new Error("The wallet did not answer. Refresh and try again.");
    }
  }
  if (!response.ok) throw new Error(errorText(body, "That did not go through"));
  return body;
}

function showNotice(text) {
  notice.hidden = !text;
  notice.textContent = text || "";
}

function signedIn(on) {
  login.hidden = on;
  home.hidden = !on;
  signout.hidden = !on;
  const opening = on && !document.body.classList.contains("in");
  document.body.classList.toggle("in", on);
  document.querySelector("#menu").hidden = !on;
  if (opening) showView("wallet");
  else if (!on) document.querySelector("#title").textContent = "Sign in";
  const theme = document.querySelector('meta[name="theme-color"]');
  if (theme) theme.setAttribute("content", on ? "#071018" : (document.body.classList.contains("gate-dark") ? "#0e1217" : "#f4f6f8"));
}

const savedTheme = localStorage.getItem("maestro-phone-theme") === "dark" ? "dark" : "light";
document.body.classList.toggle("gate-dark", savedTheme === "dark");

function money(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value || "0");
  return number.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function coinName(value) {
  if (!value || value === "usdttrc20" || value === "usdt") return "USDT";
  return String(value).toUpperCase();
}

function statusText(row) {
  if (row.direction === "withdraw" && row.status === "paused") return "Paused";
  if (row.direction === "withdraw" && (row.status === "requested" || row.status === "pending")) return "Processing internal transactions";
  if (row.direction === "deposit" && row.status === "pending") return "Waiting for payment";
  if (row.status === "requested") return "Waiting for approval";
  if (row.status === "pending") return "Sending";
  if (row.status === "posted") return row.direction === "deposit" ? "Added" : "Sent";
  if (row.status === "rejected" || row.status === "failed") return "Rejected";
  return row.status || "";
}

function statusClass(row) {
  const text = statusText(row).toLowerCase();
  if (text === "added" || text === "sent") return "ok";
  if (text.startsWith("processing") || text === "paused" || text.includes("waiting") || text === "sending") return "wait";
  return "";
}

function directionText(row) {
  if (row.purpose_label) return row.purpose_label;
  if (row.direction === "withdraw") return "Withdrawal";
  if (row.direction === "contract") return "Contract";
  if (row.direction === "expense") return "Expense";
  return "Deposit";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function miningAccounts() {
  return (homeBody?.accounts || []).filter((account) => account.action === "convert");
}

const SECTIONS = {
  trading: [["accounts", "Accounts"], ["trades", "Trades"], ["journal", "Journal"]],
  wallet: [["wallet", "Wallet"]],
  connect: [["contracts", "Contracts"], ["passprops", "Pass Props"], ["coin", "Project Coin"], ["payments", "Payments"], ["telegram", "Telegram"], ["webhooks", "Webhooks"]],
  more: [["approvals", "Approvals"], ["password", "Password"]],
};
const TITLES = { wallet: "Wallet", accounts: "Accounts", trades: "Trades", journal: "Journal", contracts: "Contracts", passprops: "Pass Props", coin: "Project Coin", payments: "Payments", telegram: "Telegram", webhooks: "Webhooks", approvals: "Approvals", password: "Password" };

function groupFor(section) {
  return Object.keys(SECTIONS).find((group) => SECTIONS[group].some(([id]) => id === section)) || "wallet";
}

function visibleItems(group) {
  return SECTIONS[group].filter(([id]) => (id !== "webhooks" && id !== "approvals") || Boolean(homeBody?.user?.admin));
}

function showView(name) {
  const group = groupFor(name);
  const items = visibleItems(group);
  const section = items.some(([id]) => id === name) ? name : items[0][0];
  document.querySelectorAll("[data-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== section;
  });
  document.querySelectorAll("#menu button").forEach((button) => {
    button.classList.toggle("on", button.dataset.group === group);
  });
  const subnav = document.querySelector("#subnav");
  subnav.hidden = items.length < 2;
  subnav.innerHTML = items.map(([id, label]) => `<button type="button" data-section="${id}" class="${id === section ? "on" : ""}">${label}</button>`).join("");
  document.querySelector("#title").textContent = TITLES[section] || "Wallet";
  const loaders = { trades: loadTrades, journal: loadJournal, passprops: loadPassProps, payments: loadPayments, telegram: loadTelegram, webhooks: loadWebhooks, approvals: loadApprovals };
  if (loaders[section]) loaders[section]().catch((error) => showNotice(error.message));
}

function listOrEmpty(rows, card, empty) {
  return rows.length ? rows.map(card).join("") : `<p class="muted">${empty}</p>`;
}

async function loadTrades() {
  const body = await api("/api/v1/trades");
  const rows = body.trades || [];
  document.querySelector("#trades").innerHTML = listOrEmpty(rows, (row) => `
    <article class="account">
      <strong>${escapeHtml(row.symbol)} · ${escapeHtml(row.direction)}</strong>
      <span class="meta">${escapeHtml(row.account_name || "")} · lot ${escapeHtml(row.lot)}</span>
      <span class="pill">${escapeHtml(row.floating_pl ?? "")}</span>
    </article>`, "No open trades.");
}

async function loadJournal() {
  const accounts = await api("/api/v1/journal/accounts");
  if (!accounts.length) {
    document.querySelector("#journal").innerHTML = `<p class="muted">No trading account to journal yet.</p>`;
    return;
  }
  const journal = await api(`/api/v1/journal?account_id=${accounts[0].id}`);
  const summary = journal.summary || {};
  const days = (journal.days || []).slice(0, 8);
  document.querySelector("#journal").innerHTML = `
    <article class="account"><strong>${escapeHtml(journal.account_name || accounts[0].display_name)}</strong><span class="meta">Net ${escapeHtml(summary.net || "0")} ${escapeHtml(journal.currency || "")} · ${escapeHtml(summary.trades || 0)} trades</span></article>
    ${listOrEmpty(days, (day) => `<article class="account"><strong>${escapeHtml(String(day.date).slice(0, 10))}</strong><span class="meta">${escapeHtml(day.trade_count)} trades · ${escapeHtml(day.net)}</span><span class="pill ${day.result === "profit" ? "ok" : day.result === "loss" ? "wait" : ""}">${escapeHtml(day.result)}</span></article>`, "No closed days yet.")}`;
}

async function loadPassProps() {
  const rows = (await api("/api/v1/accounts")).filter((row) => row.connection_method === "passprop");
  document.querySelector("#passprops").innerHTML = listOrEmpty(rows, (row) => `
    <article class="account">
      <strong>${escapeHtml(row.passprop?.firm_name || row.display_name)}</strong>
      <span class="meta">${escapeHtml(row.passprop?.account_size || row.account_number)} · ${escapeHtml(row.equity || "")} ${escapeHtml(row.currency || "")}</span>
      <span class="pill">${escapeHtml(row.status)}</span>
    </article>`, "No Pass Props account yet. Add one in the desk software.");
}

async function loadPayments() {
  const rows = await api("/api/v1/payments");
  document.querySelector("#payments").innerHTML = listOrEmpty(rows, (row) => `
    <article class="account">
      <strong>${escapeHtml(row.purpose || "Payment")} · ${escapeHtml(row.price_amount)} ${escapeHtml(row.price_currency)}</strong>
      <span class="meta">${escapeHtml(row.provider || "")}</span>
      <span class="pill">${escapeHtml(row.status)}</span>
    </article>`, "No payments yet.");
}

async function loadTelegram() {
  const body = await api("/api/v1/telegram");
  document.querySelector("#telegram").innerHTML = `
    <article class="account"><strong>Telegram</strong><span class="meta">${body.account_connected ? "Phone is signed in" : "Phone is not signed in"}</span><span class="pill">${body.auto_execute ? "Auto execute on" : "Auto execute off"}</span></article>
    <p class="muted">Signing in and choosing signal chats stays in the desk software.</p>`;
}

async function loadWebhooks() {
  const rows = (await api("/api/v1/accounts")).filter((row) => row.connection_method === "webhook");
  document.querySelector("#webhooks").innerHTML = listOrEmpty(rows, (row) => `
    <article class="account"><strong>${escapeHtml(row.display_name)}</strong><span class="meta">${escapeHtml(row.account_number)}</span><span class="pill">${escapeHtml(row.status)}</span></article>`, "No webhook accounts.");
}

function accountButton(account) {
  if (account.action === "convert") return `<button class="ghost" type="button" data-action="convert" data-id="${account.id}">Convert to USDT</button>`;
  if (account.action === "contract") return `<button class="ghost" type="button" data-action="fund" data-id="${account.id}">Transfer in</button>`;
  if (account.method === "local_mt5") return `<p class="meta">MT5 ${escapeHtml(account.number)} · ${escapeHtml(account.status)}</p>`;
  return `<p class="meta">Shown from the broker. Cash moves through the USDT wallet.</p>`;
}

function accountCard(account) {
  return `
    <article class="account">
      <strong>${escapeHtml(account.name)}</strong>
      <span class="meta">${money(account.balance)} ${account.currency}</span>
      <span class="pill">${account.status}</span>
      ${accountButton(account)}
    </article>
  `;
}

function render(body) {
  homeBody = body;
  document.querySelector("#who").hidden = false;
  document.querySelector("#who").textContent = body.user.full_name || body.user.email;
  document.querySelector("#usdt").textContent = money(body.usdt);
  document.querySelector("#pcoin").textContent = `${body.pcoin} PCoin`;
  document.querySelector("#pcoin-usdt").textContent = `≈ ${money(body.pcoin_usdt)} USDT`;
  document.querySelector("#rate").textContent = body.rate || "";
  const payout = document.querySelector("#payout-address");
  payout.textContent = body.payout_address || "Not set";
  payout.classList.toggle("muted", !body.payout_address);
  const trading = body.accounts.filter((account) => account.action !== "convert");
  const mining = body.accounts.filter((account) => account.action === "convert");
  document.querySelector("#accounts").innerHTML = trading.map(accountCard).join("") || `<p class="muted">No contract or trading accounts yet.</p>`;
  document.querySelector("#coin-accounts").innerHTML = mining.map(accountCard).join("") || `<p class="muted">No Project Coin accounts yet.</p>`;
  document.querySelector("#contracts").innerHTML = body.contracts.map((row) => `
    <article class="account">
      <strong>${row.account}</strong>
      <span class="meta">${money(row.held)} USDT held</span>
      <span class="pill">${row.status}</span>
      ${row.can_withdraw ? `<button class="ghost" type="button" data-action="release" data-id="${row.id}">Withdraw to wallet</button>` : `<p class="meta">Locked until ${String(row.unlock_at || "").slice(0, 10)}</p>`}
    </article>
  `).join("") || `<p class="muted">No contract transfers.</p>`;
  const transfers = body.transfers || [];
  document.querySelector("#activity").innerHTML = transfers.map((row) => `
    <article class="activity">
      <strong>${directionText(row)} · ${money(row.amount)} ${coinName(row.currency)}</strong>
      <span class="pill ${statusClass(row)}">${statusText(row)}</span>
      ${row.direction === "deposit" && row.status === "pending" ? `<button class="ghost" type="button" data-action="pay" data-id="${row.id}">Show address</button>` : ""}
    </article>
  `).join("") || `<p class="muted">Deposits and withdrawals show up here.</p>`;
}

async function load() {
  const mine = ++generation;
  const body = await api("/api/v1/mobile/home");
  if (mine !== generation) return;
  signedIn(true);
  render(body);
}

function closeSheet() {
  sheet.hidden = true;
  document.body.style.overflow = "";
}

function openSheet(next) {
  action = next;
  const titles = { deposit: "Deposit USDT", withdraw: "Withdraw USDT", convert: "Convert Project Coin", fund: "Transfer to contract", address: "Your wallet address", "add-contract": "Add contract", "add-mt5": "Add MetaTrader", "add-coin": "Add Project Coin" };
  document.querySelector("#sheet-title").textContent = titles[next.kind];
  document.querySelector("#sheet-help").textContent = next.help || "";
  const addressLabel = document.querySelector("#address-label");
  addressLabel.hidden = next.kind !== "withdraw" && next.kind !== "address";
  document.querySelector("#address").required = next.kind === "withdraw" || next.kind === "address";
  const detailsOnly = next.kind === "address" || next.kind === "add-contract" || next.kind === "add-mt5" || next.kind === "add-coin";
  const extra = document.querySelector("#extra");
  extra.hidden = true;
  extra.innerHTML = "";
  if (next.kind === "add-contract" || next.kind === "add-coin") {
    extra.hidden = false;
    extra.innerHTML = `<label>Name<input name="name" maxlength="160" placeholder="Optional name" /></label><label class="check"><input type="checkbox" name="terms" required /><span>${escapeHtml(next.terms || "")}</span></label>`;
  }
  if (next.kind === "add-mt5") {
    extra.hidden = false;
    extra.innerHTML = `<label>Name<input name="name" maxlength="160" placeholder="Optional name" /></label><label>Broker<input name="broker" placeholder="Broker" /></label><label>Login<input name="login" inputmode="numeric" autocomplete="off" required /></label><label>Password<input name="mt5_password" type="password" autocomplete="new-password" required /></label><label>Server<input name="server" autocomplete="off" required /></label>`;
  }
  const amountOnly = !detailsOnly;
  document.querySelector("#amount-label").hidden = !amountOnly;
  document.querySelector("#amount").required = amountOnly;
  const chips = document.querySelector("#chips");
  chips.hidden = next.kind !== "deposit";
  chips.innerHTML = next.kind === "deposit" ? ["50", "100", "500", "1000"].map((value) => `<button class="ghost" type="button" data-chip="${value}">${value}</button>`).join("") : "";
  document.querySelector("#sheet-error").hidden = true;
  document.querySelector("#account-pick").hidden = true;
  document.querySelector("#available-line").hidden = true;
  document.querySelector("#sheet-submit").hidden = false;
  document.querySelector("#sheet-submit").textContent = next.kind === "address" ? "Save address" : String(next.kind).startsWith("add-") ? "Save account" : "Continue";
  form.hidden = false;
  receipt.hidden = true;
  form.reset();
  if (next.kind === "withdraw" || next.kind === "address") {
    document.querySelector("#address").value = homeBody?.payout_address || "";
  }
  sheet.hidden = false;
  document.body.style.overflow = "hidden";
  if (String(next.kind).startsWith("add-")) extra.querySelector("input")?.focus();
  else if (next.kind === "address" || next.kind === "withdraw") document.querySelector("#address").focus();
  else if (next.kind !== "convert") document.querySelector("#amount").focus();
}

function selectedMining() {
  return miningAccounts().find((account) => account.id === action?.id) || null;
}

function usdtFromPcoin(amount) {
  const rate = Number(homeBody?.rate_value || 1000);
  const pcoin = Number(amount);
  if (!rate || !Number.isFinite(pcoin) || pcoin <= 0) return "0";
  const units = Math.floor((pcoin / rate) * 1000000);
  const whole = Math.floor(units / 1000000);
  const frac = String(units % 1000000).padStart(6, "0").replace(/0+$/, "");
  return frac ? `${whole}.${frac}` : String(whole);
}

function openConvert(accountId) {
  const accounts = miningAccounts();
  if (!accounts.length) {
    showNotice("This login has no Project Coin account.");
    return;
  }
  const chosen = accounts.find((account) => account.id === accountId);
  action = { kind: "convert", step: chosen ? "amount" : "pick", id: chosen ? chosen.id : "" };
  document.querySelector("#address-label").hidden = true;
  document.querySelector("#address").required = false;
  document.querySelector("#sheet-error").hidden = true;
  form.hidden = false;
  receipt.hidden = true;
  form.reset();
  sheet.hidden = false;
  document.body.style.overflow = "hidden";
  showConvert();
}

function showConvert() {
  const pick = document.querySelector("#account-pick");
  const available = document.querySelector("#available-line");
  const amountLabel = document.querySelector("#amount-label");
  const amount = document.querySelector("#amount");
  const chips = document.querySelector("#chips");
  const submit = document.querySelector("#sheet-submit");
  const account = selectedMining();
  document.querySelector("#sheet-title").textContent = "Convert Project Coin";
  pick.hidden = action.step !== "pick";
  available.hidden = action.step === "pick";
  amountLabel.hidden = action.step !== "amount";
  amount.required = action.step === "amount";
  chips.hidden = action.step !== "amount";
  submit.hidden = action.step === "pick";
  submit.textContent = action.step === "confirm" ? "Confirm conversion" : "Continue";
  if (action.step === "pick") {
    document.querySelector("#sheet-help").textContent = "Choose the Project Coin account to convert from.";
    pick.innerHTML = miningAccounts().map((row) => `
      <button type="button" data-pick="${row.id}">
        <strong>${escapeHtml(row.name)}</strong>
        <span>${escapeHtml(row.balance)} PCoin available</span>
      </button>
    `).join("");
    return;
  }
  if (!account) {
    action.step = "pick";
    showConvert();
    return;
  }
  const change = miningAccounts().length > 1 ? `<button class="text" type="button" id="change-account">Change account</button>` : "";
  if (action.step === "amount") {
    document.querySelector("#sheet-help").textContent = `Minimum ${homeBody?.min_pcoin || "1000"} PCoin. ${homeBody?.rate || ""}`;
    available.innerHTML = `<span class="label">Available on ${escapeHtml(account.name)}</span><strong>${escapeHtml(account.balance)} PCoin</strong><span class="muted">${escapeHtml(homeBody?.rate || "")}</span>${change}`;
    chips.innerHTML = `<button class="ghost" type="button" data-chip="all">Use all available</button>`;
    amount.placeholder = "PCoin to convert";
    amount.focus();
    return;
  }
  document.querySelector("#sheet-help").textContent = "This moves PCoin from the account into USDT on the wallet.";
  const fee = Number(homeBody?.fee_bps || 0);
  const feeLine = fee ? `<span class="muted">Fee ${fee / 100}% is added to the PCoin used.</span>` : "";
  available.innerHTML = `
    <span class="label">${escapeHtml(account.name)}</span>
    <strong>${escapeHtml(action.amount)} PCoin</strong>
    <span class="muted">You receive ${escapeHtml(action.usdt)} USDT</span>
    ${feeLine}
    <button class="text" type="button" id="change-amount">Change amount</button>
    ${change}
  `;
}

function showReceipt(row) {
  form.hidden = true;
  receipt.hidden = false;
  document.querySelector("#receipt-title").textContent = "Send USDT";
  document.querySelector("#receipt-amount").textContent = `${money(row.amount)} ${coinName(row.currency)}`;
  const address = String(row.address || "").trim();
  document.querySelector("#address-box").hidden = !address;
  document.querySelector("#pay-address").textContent = address;
  const link = document.querySelector("#invoice-link");
  if (row.invoice_url) {
    link.hidden = false;
    link.href = row.invoice_url;
  } else {
    link.hidden = true;
    link.removeAttribute("href");
  }
  document.querySelector("#receipt-note").textContent = address
    ? "The USDT is added after the network confirms this payment."
    : "No deposit address came back. Open the payment page, or try the amount again.";
  sheet.hidden = false;
  document.body.style.overflow = "hidden";
}

const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-submit");
const loginError = document.querySelector("#login-error");
let signingIn = false;
const rememberedEmail = localStorage.getItem("maestro-phone-email");
if (rememberedEmail) document.querySelector("#login-email").value = rememberedEmail;

function press(button) {
  button.addEventListener("pointerdown", () => button.classList.add("pressed"));
  button.addEventListener("pointerup", () => button.classList.remove("pressed"));
  button.addEventListener("pointercancel", () => button.classList.remove("pressed"));
}
press(loginButton);

document.querySelector("#theme-toggle").addEventListener("click", () => {
  const dark = !document.body.classList.contains("gate-dark");
  document.body.classList.toggle("gate-dark", dark);
  localStorage.setItem("maestro-phone-theme", dark ? "dark" : "light");
  const theme = document.querySelector('meta[name="theme-color"]');
  if (theme && !document.body.classList.contains("in")) theme.setAttribute("content", dark ? "#0e1217" : "#f4f6f8");
});

function showLoginError(text) {
  loginError.hidden = !text;
  loginError.textContent = text || "";
  showNotice(text);
}

loginForm.addEventListener("invalid", (event) => {
  event.preventDefault();
  showLoginError(event.target.validationMessage || "Enter your email and password.");
}, true);

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (signingIn) return;
  signingIn = true;
  const data = new FormData(loginForm);
  const email = String(data.get("email") || "").trim();
  loginButton.disabled = true;
  loginButton.textContent = "Signing in…";
  showLoginError("");
  showNotice("Signing in…");
  try {
    const body = await api("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password: data.get("password") }),
    });
    localStorage.setItem("maestro-phone-email", email);
    if (body.mfa_required) {
      mfaToken = body.mfa_token;
      document.querySelector("#mfa-form").hidden = false;
      showNotice("Enter the authentication code from your authenticator.");
      return;
    }
    signedIn(true);
    document.querySelector("#who").hidden = false;
    document.querySelector("#who").textContent = (body.user && (body.user.full_name || body.user.email)) || email;
    showNotice("Opening your wallet…");
    await load();
    showNotice("");
  } catch (error) {
    if (!home.hidden) showNotice(error.message);
    else showLoginError(error.message);
  } finally {
    signingIn = false;
    loginButton.disabled = false;
    loginButton.textContent = "Enter desk";
  }
});

document.querySelector("#mfa-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  if (button.disabled) return;
  button.disabled = true;
  button.textContent = "Checking…";
  showNotice("Checking the code…");
  const data = new FormData(event.currentTarget);
  try {
    await api("/api/v1/auth/mfa", { method: "POST", body: JSON.stringify({ mfa_token: mfaToken, code: data.get("code") }) });
    signedIn(true);
    showNotice("Loading your wallet…");
    await load();
    showNotice("");
  } catch (error) {
    showNotice(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Confirm";
  }
});

document.querySelector("#menu").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button?.dataset.group) return;
  const items = visibleItems(button.dataset.group);
  showView(items[0][0]);
});

document.querySelector("#subnav").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (button?.dataset.section) showView(button.dataset.section);
});

document.querySelector("#password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.querySelector("#password-error");
  const button = document.querySelector("#password-submit");
  const data = new FormData(form);
  error.hidden = true;
  if (data.get("new_password") !== data.get("confirm_password")) {
    error.hidden = false;
    error.textContent = "The new passwords do not match.";
    return;
  }
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    await api("/api/v1/mobile/password", {
      method: "POST",
      body: JSON.stringify({ current_password: data.get("current_password"), new_password: data.get("new_password") }),
    });
    form.reset();
    showNotice("Password changed.");
  } catch (err) {
    error.hidden = false;
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    button.textContent = "Save password";
  }
});

signout.addEventListener("click", async () => {
  generation += 1;
  await api("/api/v1/auth/logout", { method: "POST" }).catch(() => {});
  signedIn(false);
  document.querySelector("#who").hidden = true;
});

function approvalCard(row, kind, title, detail) {
  return `<article class="account"><strong>${escapeHtml(title)}</strong><span class="meta">${escapeHtml(detail)}</span><div class="actions add-actions"><button class="primary" type="button" data-review="${kind}" data-decision="approve" data-id="${row.id}">Approve</button><button class="ghost" type="button" data-review="${kind}" data-decision="reject" data-id="${row.id}">Reject</button></div></article>`;
}

async function loadApprovals() {
  const body = await api("/api/v1/mobile/approvals");
  const fill = (id, rows, card) => {
    document.querySelector(id).innerHTML = rows.length ? rows.map(card).join("") : `<p class="muted">Nothing waiting.</p>`;
  };
  fill("#approval-credits", body.credits || [], (row) => approvalCard(row, "credits", row.full_name || row.email, `${row.amount} PCoin · ${row.source}`));
  fill("#approval-withdrawals", body.withdrawals || [], (row) => approvalCard(row, "withdrawals", row.full_name || row.email, `${money(row.amount)} ${coinName(row.currency)}`));
  fill("#approval-applications", body.applications || [], (row) => approvalCard(row, "applications", row.full_name || row.email, row.kind));
  fill("#approval-capital", body.capital || [], (row) => approvalCard(row, "capital", row.email, `${money(row.amount)} · ${row.fund || row.kind}`));
}

home.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.review) {
    button.disabled = true;
    api(`/api/v1/mobile/approvals/${button.dataset.review}/${button.dataset.id}`, { method: "POST", body: JSON.stringify({ decision: button.dataset.decision }) })
      .then(() => {
        showNotice(button.dataset.decision === "approve" ? "Approved." : "Rejected.");
        return loadApprovals();
      })
      .catch((error) => showNotice(error.message));
    return;
  }
  const kind = button.dataset.open || button.dataset.action;
  if (kind === "deposit") {
    if (homeBody && homeBody.payments_ready === false) {
      showNotice("Deposits are not ready on this wallet yet.");
      return;
    }
    openSheet({ kind, help: "Enter the USDT amount. The next screen shows the TRC20 address to pay." });
  }
  if (kind === "address") openSheet({ kind, help: "This TRC20 address is saved on your login and used for withdrawals." });
  if (kind === "add-contract") openSheet({ kind, help: "Agree to add a contract account. A private key is not stored.", terms: "I agree. Maestro reads public balances only and does not store a private key." });
  if (kind === "add-mt5") openSheet({ kind, help: "Save the MetaTrader login, password, and server. The live terminal is checked from the desk software." });
  if (kind === "add-coin") openSheet({ kind, help: "Agree to add a Project Coin account on this login.", terms: "I agree. Project Coin is mined on this server. It is not Bitcoin." });
  if (kind === "withdraw") openSheet({ kind, help: homeBody?.payout_address ? "This withdrawal uses your saved TRC20 address." : "Enter your TRC20 address. It is saved on your login." });
  if (kind === "convert") openConvert(button.dataset.id || "");
  if (kind === "fund") openSheet({ kind, id: button.dataset.id, help: "Moves USDT from the wallet onto this contract." });
  if (kind === "release") {
    api("/api/v1/mobile/contracts/withdraw", { method: "POST", body: JSON.stringify({ stake_id: button.dataset.id }) })
      .then((body) => { showNotice(`Returned ${body.returned} USDT to the wallet.`); return load(); })
      .catch((error) => showNotice(error.message));
  }
  if (kind === "pay") {
    const row = (homeBody?.transfers || []).find((item) => item.id === button.dataset.id);
    if (row) showReceipt(row);
  }
});

document.querySelector("#chips").addEventListener("click", (event) => {
  const button = event.target.closest("[data-chip]");
  if (!button) return;
  if (button.dataset.chip === "all") {
    const account = selectedMining();
    document.querySelector("#amount").value = account ? account.balance : "";
    return;
  }
  document.querySelector("#amount").value = button.dataset.chip;
});

form.addEventListener("click", (event) => {
  const pick = event.target.closest("[data-pick]");
  if (pick && action?.kind === "convert") {
    action.id = pick.dataset.pick;
    action.step = "amount";
    showConvert();
    return;
  }
  if (event.target.closest("#change-account") && action?.kind === "convert") {
    action.step = "pick";
    action.id = "";
    showConvert();
    return;
  }
  if (event.target.closest("#change-amount") && action?.kind === "convert") {
    action.step = "amount";
    showConvert();
  }
});

document.querySelector("#close-sheet").addEventListener("click", closeSheet);
document.querySelector("#done-receipt").addEventListener("click", () => {
  closeSheet();
  load().catch((error) => showNotice(error.message));
});

document.querySelector("#copy-address").addEventListener("click", async () => {
  const text = document.querySelector("#pay-address").textContent.trim();
  if (!text) return;
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
    else {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    document.querySelector("#copy-address").textContent = "Copied";
  } catch {
    document.querySelector("#copy-address").textContent = "Select the address and copy it";
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.querySelector("#sheet-error");
  error.hidden = true;
  const data = new FormData(form);
  const amount = String(data.get("amount") || "").trim().replace(/,/g, "");
  const adding = action?.kind === "add-contract" || action?.kind === "add-mt5" || action?.kind === "add-coin";
  if (!adding && action?.kind !== "address" && (!amount || Number(amount) <= 0)) {
    error.hidden = false;
    error.textContent = "Enter an amount greater than 0.";
    return;
  }
  const submit = document.querySelector("#sheet-submit");
  submit.disabled = true;
  try {
    if (adding) {
      const kind = action.kind === "add-contract" ? "contract" : action.kind === "add-coin" ? "project_coin" : "mt5";
      const saved = await api("/api/v1/mobile/accounts", {
        method: "POST",
        body: JSON.stringify({
          kind,
          name: String(data.get("name") || "").trim(),
          broker: String(data.get("broker") || "").trim(),
          login: String(data.get("login") || "").trim(),
          password: String(data.get("mt5_password") || ""),
          server: String(data.get("server") || "").trim(),
          accepted_terms: data.get("terms") === "on",
        }),
      });
      showNotice(`${saved.name} added.`);
      closeSheet();
      if (kind === "project_coin") showView("coin");
      else showView("accounts");
    } else if (action.kind === "deposit") {
      const body = await api("/api/v1/mobile/deposit", { method: "POST", body: JSON.stringify({ amount }) });
      showReceipt(body);
      showNotice("");
    } else if (action.kind === "address") {
      const saved = await api("/api/v1/mobile/payout-address", { method: "POST", body: JSON.stringify({ address: String(data.get("address") || "").trim() }) });
      showNotice("Wallet address saved.");
      closeSheet();
      homeBody = { ...(homeBody || {}), payout_address: saved.address };
    } else if (action.kind === "withdraw") {
      const body = await api("/api/v1/mobile/withdraw", { method: "POST", body: JSON.stringify({ amount, address: String(data.get("address") || "").trim(), currency: "usdttrc20" }) });
      showNotice(body.status === "paused" ? "Paused." : "Processing internal transactions.");
      closeSheet();
    } else if (action.kind === "convert" && action.step === "amount") {
      const account = selectedMining();
      const available = Number(String(account?.balance || "0").replace(/,/g, ""));
      const minimum = Number(homeBody?.min_pcoin || 0);
      if (minimum && Number(amount) < minimum) {
        error.hidden = false;
        error.textContent = `The minimum is ${homeBody.min_pcoin} PCoin.`;
        return;
      }
      if (Number.isFinite(available) && Number(amount) > available) {
        error.hidden = false;
        error.textContent = `Available on ${account?.name || "this account"} is ${account?.balance || "0"} PCoin.`;
        return;
      }
      action.amount = amount;
      action.usdt = usdtFromPcoin(amount);
      if (action.usdt === "0") {
        error.hidden = false;
        error.textContent = "That amount is too small to convert.";
        return;
      }
      action.step = "confirm";
      showConvert();
      return;
    } else if (action.kind === "convert") {
      const body = await api("/api/v1/mobile/convert", { method: "POST", body: JSON.stringify({ amount }) });
      const account = selectedMining();
      showNotice(`Converted ${body.pcoin} PCoin from ${account?.name || "Project Coin"} to ${body.usdt} USDT.`);
      closeSheet();
    } else if (action.kind === "fund") {
      const body = await api("/api/v1/mobile/contracts/fund", { method: "POST", body: JSON.stringify({ account_id: action.id, amount }) });
      showNotice(`Transferred ${body.position.principal} USDT to the contract.`);
      closeSheet();
    }
    await load();
  } catch (err) {
    error.hidden = false;
    error.textContent = err.message;
  } finally {
    submit.disabled = false;
    document.querySelector("#copy-address").textContent = "Copy address";
  }
});

load().catch(() => {});
