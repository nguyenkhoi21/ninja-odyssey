"""Single-page Vietnamese Web GM Panel served at GET /gm."""
import json
from core import gm_service

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Ninja Odyssey - Bảng Điều Khiển GM</title>
<style>
  :root {
    --bg: #0e1118;
    --panel: #161b26;
    --panel-2: #1d2433;
    --border: #2a3449;
    --text: #e9eef7;
    --muted: #93a1bc;
    --accent: #ff7a1a;
    --accent-2: #ffb020;
    --ok: #26c281;
    --danger: #f0485e;
    --blue: #3b82f6;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.45;
  }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 16px; }
  .topbar {
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px;
    margin-bottom: 14px;
  }
  .brand h1 { margin: 0; font-size: 18px; color: var(--accent-2); letter-spacing: .3px; }
  .brand p { margin: 2px 0 0; color: var(--muted); font-size: 12px; }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  select, input, textarea, button {
    font: inherit; color: var(--text); background: var(--panel-2);
    border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
  }
  select:focus, input:focus, textarea:focus { outline: none; border-color: var(--accent); }
  button { cursor: pointer; font-weight: 600; transition: .15s opacity, .15s transform; }
  button:hover { opacity: .92; }
  button:active { transform: translateY(1px); }
  .btn-primary { background: linear-gradient(135deg, var(--accent), #e0530a); border-color: transparent; color: #fff; }
  .btn-ok { background: #1c8f60; border-color: transparent; color: #fff; }
  .btn-blue { background: #2563eb; border-color: transparent; color: #fff; }
  .btn-soft { background: var(--panel-2); color: var(--text); }
  .player-bar {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(125px, 1fr)); gap: 8px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
    margin-bottom: 14px;
  }
  .stat { background: var(--panel-2); border-radius: 8px; padding: 8px 10px; }
  .stat .lbl { font-size: 11px; color: var(--muted); text-transform: uppercase; }
  .stat .val { font-size: 15px; font-weight: 700; margin-top: 2px; color: #fff; }
  .badge { display: inline-block; padding: 2px 7px; border-radius: 99px; font-size: 11px; font-weight: 700; }
  .badge-on { background: rgba(38,194,129,.2); color: var(--ok); }
  .badge-off { background: rgba(147,161,188,.15); color: var(--muted); }
  .tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .tab {
    background: var(--panel); border: 1px solid var(--border); padding: 9px 14px; border-radius: 10px;
    color: var(--muted); font-weight: 600;
  }
  .tab.active { background: var(--accent); color: #fff; border-color: transparent; }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px;
    margin-bottom: 14px;
  }
  .hidden { display: none !important; }
  .preset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }
  .preset-btn {
    text-align: left; padding: 12px 14px; border-radius: 10px; background: var(--panel-2);
    border: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px;
  }
  .preset-btn.featured {
    background: linear-gradient(135deg, rgba(255,122,26,.22), rgba(255,176,32,.14));
    border-color: var(--accent);
  }
  .preset-btn strong { font-size: 14px; color: var(--accent-2); }
  .preset-btn span { font-size: 12px; color: var(--muted); font-weight: 400; }
  .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .chip {
    padding: 6px 11px; border-radius: 99px; font-size: 12px; background: var(--panel-2);
    border: 1px solid var(--border); color: var(--muted);
  }
  .chip.active { background: var(--blue); color: #fff; border-color: transparent; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  th { font-size: 12px; color: var(--muted); text-transform: uppercase; }
  .tag { font-size: 11px; padding: 2px 7px; border-radius: 6px; background: var(--panel-2); border: 1px solid var(--border); color: var(--muted); }
  .grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
  .field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
  .field label { font-size: 12px; color: var(--muted); }
  .toast {
    position: fixed; right: 16px; bottom: 16px; max-width: 420px; z-index: 99;
    background: #1a2333; border: 1px solid var(--border); border-left: 4px solid var(--ok);
    padding: 12px 14px; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,.45);
  }
  .toast.err { border-left-color: var(--danger); }
  .logbox {
    max-height: 170px; overflow-y: auto; background: #0b0e14; border: 1px solid var(--border);
    border-radius: 8px; padding: 10px; font-family: ui-monospace, Consolas, monospace; font-size: 12px;
    color: #c5d1e8;
  }
  code { background: #0b0e14; padding: 2px 6px; border-radius: 5px; color: var(--accent-2); }
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="brand">
      <h1>NINJA ODYSSEY — GM PANEL</h1>
      <p>Thêm vật phẩm, hồn tướng, tướng, chỉ số, thư hệ thống &amp; đồng bộ trực tiếp tài khoản</p>
    </div>
    <div class="controls">
      <select id="playerSelect" style="min-width:250px"></select>
      <input id="targetFallback" placeholder="Hoặc nhập ID / tên..." style="width:165px" />
      <input id="gmKeyInput" type="password" placeholder="GM Key (nếu bật)" style="width:150px" />
      <button class="btn-soft" onclick="loadPlayers()">Làm mới</button>
      <button class="btn-blue" onclick="doAction({action:'flush_db'})">Lưu Supabase</button>
    </div>
  </div>

  <div id="emptyNotice" class="card hidden" style="border-color:var(--accent-2);color:var(--accent-2)">
    Chưa có nhân vật nào trong DB. Hãy đăng nhập game bằng APK và tạo nhân vật trước, sau đó bấm <strong>Làm mới</strong>.
  </div>

  <div class="player-bar" id="playerBar">
    <div class="stat"><div class="lbl">Trạng thái</div><div class="val" id="stOnline">-</div></div>
    <div class="stat"><div class="lbl">Cấp / VIP</div><div class="val" id="stLv">-</div></div>
    <div class="stat"><div class="lbl">Vàng</div><div class="val" id="stCoin">-</div></div>
    <div class="stat"><div class="lbl">Kim Cương</div><div class="val" id="stGem">-</div></div>
    <div class="stat"><div class="lbl">Thể Lực / ĐKN</div><div class="val" id="stAp">-</div></div>
    <div class="stat"><div class="lbl">Lực Chiến / Tướng</div><div class="val" id="stPower">-</div></div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('quick', this)">Quà Nhanh (1-Click)</button>
    <button class="tab" onclick="switchTab('catalog', this)">Kho Vật Phẩm &amp; Hồn Tướng</button>
    <button class="tab" onclick="switchTab('stats', this)">Chỉnh Chỉ Số &amp; Gửi Thư</button>
    <button class="tab" onclick="switchTab('codes', this)">Mã Lệnh GM Trong Game</button>
  </div>

  <!-- TAB 1: QUICK PRESETS -->
  <div id="tab-quick" class="card">
    <div class="row" style="justify-content:space-between">
      <div><strong>Chọn gói quà tặng nhanh cho tài khoản đang chọn</strong></div>
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
        <input type="checkbox" id="viaMailPreset" /> Gửi qua Thư hệ thống (thay vì cộng thẳng túi)
      </label>
    </div>
    <div class="preset-grid">
      <button class="preset-btn featured" onclick="sendPreset('full')">
        <strong>FULL TẤT TẦN TẬT (GMFULL)</strong>
        <span>VIP 16, +100M Vàng, +1M KC, +99K Thể lực, Full Hồn x2000, Full Tiền tệ, Full Rương &amp; Nguyên liệu x999</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('gold')">
        <strong>+100.000.000 Vàng</strong>
        <span>Cộng thẳng 100 triệu Vàng (101)</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('diamond')">
        <strong>+1.000.000 Kim Cương</strong>
        <span>+1M Kim Cương (102) &amp; +100K Phiếu thay thế (2)</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('vit')">
        <strong>+99.999 Thể Lực &amp; KN</strong>
        <span>+99.999 Thể lực (99), +9.999 Điểm KN, +999 Ramen &amp; Sách KN</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('vip')">
        <strong>Mở Khóa Max VIP 16</strong>
        <span>Đặt VIP cấp 16 và mở full giới hạn VIP</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('level100')">
        <strong>Đặt Level 100</strong>
        <span>Nâng cấp đội trưởng lên Lv.100</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('soul')">
        <strong>Full 84 Hồn Tướng x2000</strong>
        <span>Nhận 2.000 mảnh hồn toàn bộ 84 nhẫn giả</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('all_roles')">
        <strong>Mở Khóa Full 84 Tướng 5★</strong>
        <span>Thêm toàn bộ nhẫn giả còn thiếu vào đội ở 5 sao</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('max_team')">
        <strong>Max Đội Hình Hiện Có</strong>
        <span>Đặt mọi tướng đang có lên Lv.100+, 5★, Thức tỉnh 10</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('currency')">
        <strong>Full 99 Tiền Tệ &amp; Cuộn SP</strong>
        <span>x99.999 cuộn SP (21..50), vé quay, xu shop, phù văn, tinh hồn</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('box')">
        <strong>Full Rương &amp; Bảo Vật x999</strong>
        <span>Toàn bộ rương ngọc, kỹ năng, bảo vật chọn</span>
      </button>
      <button class="preset-btn" onclick="sendPreset('materials')">
        <strong>Full Nguyên Liệu &amp; Đá x999</strong>
        <span>Tiến hóa, thức tỉnh, đá khảm, thần khí, trái ác quỷ, tinh tọa</span>
      </button>
    </div>
  </div>

  <!-- TAB 2: CATALOG -->
  <div id="tab-catalog" class="card hidden">
    <div class="row">
      <input id="catSearch" placeholder="Tìm theo ID (vd 50030, 102, 37) hoặc tên..." style="flex:1;min-width:220px" onkeydown="if(event.key==='Enter')loadCatalog()" />
      <label style="color:var(--muted)">SL:</label>
      <input id="catQty" type="number" min="1" value="100" style="width:95px" />
      <button class="btn-soft" onclick="setQty(1)">x1</button>
      <button class="btn-soft" onclick="setQty(100)">x100</button>
      <button class="btn-soft" onclick="setQty(999)">x999</button>
      <button class="btn-soft" onclick="setQty(2000)">x2000</button>
      <button class="btn-primary" onclick="loadCatalog()">Tìm kiếm</button>
    </div>
    <div class="chips" id="catChips"></div>
    <div style="color:var(--muted);font-size:12px;margin-bottom:8px" id="catMeta">Đang tải kho vật phẩm...</div>
    <div style="overflow-x:auto">
      <table>
        <thead>
          <tr><th>ID</th><th>Tên vật phẩm / Hồn / Tướng</th><th>Loại</th><th>Mô tả</th><th style="width:220px">Thao tác</th></tr>
        </thead>
        <tbody id="catBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 3: STATS & MAIL -->
  <div id="tab-stats" class="card hidden">
    <div class="grid-2">
      <div>
        <h3 style="margin-top:0">Cộng / Đặt Chỉ Số Tài Khoản</h3>
        <div class="row">
          <label><input type="radio" name="statMode" value="add" checked /> Cộng thêm</label>
          <label><input type="radio" name="statMode" value="set" /> Đặt thẳng (Set)</label>
        </div>
        <div class="grid-2" style="gap:8px">
          <div class="field"><label>Vàng (coin)</label><input id="inCoin" type="number" placeholder="vd 10000000" /></div>
          <div class="field"><label>Kim Cương (gem)</label><input id="inGem" type="number" placeholder="vd 500000" /></div>
          <div class="field"><label>Thể Lực (actionPoint)</label><input id="inAp" type="number" placeholder="vd 5000" /></div>
          <div class="field"><label>Điểm Kỹ Năng (skillPoint)</label><input id="inSp" type="number" placeholder="vd 500" /></div>
          <div class="field"><label>Cấp Độ (1..500)</label><input id="inLv" type="number" placeholder="vd 100" /></div>
          <div class="field"><label>VIP (0..16)</label><input id="inVip" type="number" placeholder="vd 16" /></div>
        </div>
        <button class="btn-primary" onclick="submitStats()">Áp Dụng Chỉ Số</button>
      </div>
      <div>
        <h3 style="margin-top:0">Gửi Thư Hệ Thống Kèm Vật Phẩm</h3>
        <div class="field"><label>Tiêu đề thư</label><input id="mailTitle" value="Quà tặng từ GM" /></div>
        <div class="field"><label>Nội dung thư</label><textarea id="mailBody" rows="2">Chúc bạn chơi game vui vẻ!</textarea></div>
        <div class="field">
          <label>Danh sách vật phẩm (định dạng <code>IDxSL,IDxSL</code>)</label>
          <input id="mailDrop" value="101x10000000,102x100000,50030x500,37x100" />
        </div>
        <button class="btn-ok" onclick="submitMail()">Gửi Thư Ngay</button>
      </div>
    </div>
  </div>

  <!-- TAB 4: IN-GAME GIFTCODES -->
  <div id="tab-codes" class="card hidden">
    <p style="margin-top:0;color:var(--muted)">
      Trong game bấm vào <strong>Avatar góc trên trái → Mã Quà (兑换码 / GiftCode)</strong> rồi nhập các lệnh bên dưới. Tất cả lệnh GM có thể dùng <strong>lặp lại không giới hạn số lần</strong>.
    </p>
    <div style="overflow-x:auto">
      <table>
        <thead><tr><th>Lệnh chính</th><th>Lệnh thay thế / Ví dụ</th><th>Công dụng</th><th style="width:90px">Copy</th></tr></thead>
        <tbody id="codesBody"></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <strong>Nhật ký thao tác GM</strong>
      <button class="btn-soft" style="padding:4px 8px;font-size:12px" onclick="document.getElementById('logBox').innerHTML=''">Xóa log</button>
    </div>
    <div class="logbox" id="logBox">Sẵn sàng.</div>
  </div>
</div>

<div id="toast" class="toast hidden"></div>

<script>
const GM_KEY_REQUIRED = __GM_KEY_REQUIRED__;
const GIFT_CODES = __GIFTCODES_JSON__;
const CAT_LABELS = [
  ["all", "Tất cả"],
  ["soul", "Hồn Tướng"],
  ["role", "Tướng"],
  ["money", "Tiền Tệ & Cuộn SP"],
  ["box", "Rương"],
  ["consumables", "Tiêu Hao"],
  ["stone", "Đá & Thần Khí"],
  ["material", "Nguyên Liệu"]
];

let currentCat = "all";
let playersCache = [];

const keyEl = document.getElementById("gmKeyInput");
keyEl.value = localStorage.getItem("naruto_gm_key") || "";
keyEl.addEventListener("change", () => localStorage.setItem("naruto_gm_key", keyEl.value.trim()));
if (GM_KEY_REQUIRED && !keyEl.value) {
  keyEl.style.borderColor = "#ff7a1a";
}

function gmHeaders() {
  const h = {"Content-Type": "application/json"};
  const k = keyEl.value.trim();
  if (k) h["X-GM-Key"] = k;
  return h;
}

function showToast(msg, isErr) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast" + (isErr ? " err" : "");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 4500);
}

function addLog(msg) {
  const box = document.getElementById("logBox");
  const ts = new Date().toLocaleTimeString();
  const line = document.createElement("div");
  line.textContent = `[${ts}] ${msg}`;
  box.prepend(line);
}

function selectedTarget() {
  const typed = document.getElementById("targetFallback").value.trim();
  if (typed) return typed;
  return document.getElementById("playerSelect").value;
}

function renderPlayerStats() {
  const pid = document.getElementById("playerSelect").value;
  const p = playersCache.find(x => String(x.playerId) === String(pid));
  if (!p) {
    ["stOnline","stLv","stCoin","stGem","stAp","stPower"].forEach(id => document.getElementById(id).textContent = "-");
    return;
  }
  document.getElementById("stOnline").innerHTML = p.online
    ? `<span class="badge badge-on">ONLINE</span> #${p.playerId}`
    : `<span class="badge badge-off">OFFLINE</span> #${p.playerId}`;
  document.getElementById("stLv").textContent = `Lv.${p.level} / VIP ${p.vip}`;
  document.getElementById("stCoin").textContent = Number(p.coin).toLocaleString();
  document.getElementById("stGem").textContent = Number(p.gem).toLocaleString();
  document.getElementById("stAp").textContent = `${p.actionPoint} / ${p.skillPoint}`;
  document.getElementById("stPower").textContent = `${Number(p.power).toLocaleString()} (${p.roleCount} tướng)`;
}

document.getElementById("playerSelect").addEventListener("change", renderPlayerStats);

async function loadPlayers() {
  try {
    const r = await fetch("/gm/api/players", {headers: gmHeaders()});
    const d = await r.json();
    if (!r.ok || d.code !== 200) throw new Error(d.msg || `HTTP ${r.status}`);
    playersCache = d.players || [];
    const sel = document.getElementById("playerSelect");
    const prev = sel.value;
    sel.innerHTML = "";
    document.getElementById("emptyNotice").classList.toggle("hidden", playersCache.length > 0);
    for (const p of playersCache) {
      const opt = document.createElement("option");
      opt.value = p.playerId;
      opt.textContent = `${p.online ? "[ON]" : "[OFF]"} ${p.name} (#${p.playerId}, TK:${p.userName || p.uid}, Lv.${p.level})`;
      sel.appendChild(opt);
    }
    if (prev && playersCache.some(x => String(x.playerId) === String(prev))) sel.value = prev;
    renderPlayerStats();
  } catch (e) {
    showToast("Lỗi tải danh sách nhân vật: " + e.message, true);
    addLog("ERROR loadPlayers: " + e.message);
  }
}

async function doAction(payload) {
  if (payload.action !== "flush_db" && !payload.target) {
    payload.target = selectedTarget();
  }
  if (payload.action !== "flush_db" && !payload.target) {
    showToast("Vui lòng chọn hoặc nhập nhân vật trước!", true);
    return;
  }
  try {
    const r = await fetch("/gm/api/action", {
      method: "POST",
      headers: gmHeaders(),
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    if (!r.ok || d.code !== 200) throw new Error(d.msg || `HTTP ${r.status}`);
    const pushNote = d.pushed === true ? " [Push live]" : (d.pushed === false ? " [Đã lưu DB]" : "");
    showToast((d.message || "Thành công!") + pushNote, false);
    addLog((d.message || "OK") + pushNote);
    await loadPlayers();
  } catch (e) {
    showToast("Thất bại: " + e.message, true);
    addLog("ERROR: " + e.message);
  }
}

function sendPreset(preset) {
  const viaMail = document.getElementById("viaMailPreset").checked;
  doAction({action: "preset", preset, viaMail});
}

function switchTab(name, btn) {
  document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  ["quick","catalog","stats","codes"].forEach(t => {
    document.getElementById("tab-" + t).classList.toggle("hidden", t !== name);
  });
  if (name === "catalog" && !document.getElementById("catBody").dataset.loaded) {
    loadCatalog();
  }
}

function setQty(v) { document.getElementById("catQty").value = v; }

function escHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

async function loadCatalog() {
  const q = document.getElementById("catSearch").value.trim();
  try {
    const url = `/gm/api/catalog?type=${encodeURIComponent(currentCat)}&q=${encodeURIComponent(q)}&limit=100`;
    const r = await fetch(url, {headers: gmHeaders()});
    const d = await r.json();
    if (!r.ok || d.code !== 200) throw new Error(d.msg || `HTTP ${r.status}`);
    const counts = d.counts || {};
    const chipsEl = document.getElementById("catChips");
    chipsEl.innerHTML = "";
    for (const [k, label] of CAT_LABELS) {
      const btn = document.createElement("button");
      btn.className = "chip" + (currentCat === k ? " active" : "");
      btn.textContent = `${label} (${counts[k] ?? 0})`;
      btn.onclick = () => { currentCat = k; loadCatalog(); };
      chipsEl.appendChild(btn);
    }
    const items = d.items || [];
    document.getElementById("catMeta").textContent = `Hiển thị ${items.length} / ${d.total} kết quả khớp.`;
    const body = document.getElementById("catBody");
    body.dataset.loaded = "1";
    body.innerHTML = items.map(it => {
      const actionBtns = it.type === "role"
        ? `<button class="btn-primary" style="padding:5px 9px" onclick="addOneRole(${it.kindId})">+ Add Tướng 5★</button>`
        : `<button class="btn-primary" style="padding:5px 9px" onclick="addOneItem(${it.kindId}, false)">+ Add Ngay</button>
           <button class="btn-ok" style="padding:5px 9px" onclick="addOneItem(${it.kindId}, true)">+ Thư</button>`;
      return `<tr>
        <td><code>${it.kindId}</code></td>
        <td><strong>${escHtml(it.kindName)}</strong></td>
        <td><span class="tag">${escHtml(it.type)}</span></td>
        <td style="color:var(--muted);font-size:12px">${escHtml(it.desc)}</td>
        <td><div style="display:flex;gap:6px">${actionBtns}</div></td>
      </tr>`;
    }).join("");
  } catch (e) {
    showToast("Lỗi tải kho vật phẩm: " + e.message, true);
  }
}

function addOneItem(kindId, viaMail) {
  const count = Math.max(1, parseInt(document.getElementById("catQty").value || "1", 10) || 1);
  doAction({action: "add_items", viaMail, items: [{entityId: kindId, count}]});
}

function addOneRole(kindId) {
  doAction({action: "add_role", kindId, star: 5});
}

function submitStats() {
  const mode = document.querySelector('input[name="statMode"]:checked').value;
  doAction({
    action: "set_stats",
    mode,
    coin: document.getElementById("inCoin").value,
    gem: document.getElementById("inGem").value,
    actionPoint: document.getElementById("inAp").value,
    skillPoint: document.getElementById("inSp").value,
    level: document.getElementById("inLv").value,
    vipLevel: document.getElementById("inVip").value
  });
}

function submitMail() {
  doAction({
    action: "send_mail",
    title: document.getElementById("mailTitle").value,
    body: document.getElementById("mailBody").value,
    dropDesc: document.getElementById("mailDrop").value
  });
}

function renderGiftCodes() {
  document.getElementById("codesBody").innerHTML = GIFT_CODES.map(c => `
    <tr>
      <td><code>${escHtml(c.code)}</code></td>
      <td style="color:var(--muted)">${escHtml(c.alias)}</td>
      <td>${escHtml(c.desc)}</td>
      <td><button class="btn-soft" style="padding:4px 9px" onclick="copyCode('${escHtml(c.code)}')">Copy</button></td>
    </tr>
  `).join("");
}

function copyCode(code) {
  navigator.clipboard?.writeText(code);
  showToast("Đã copy lệnh: " + code, false);
}

renderGiftCodes();
loadPlayers();
</script>
</body>
</html>
"""


def render_gm_html(gm_key_required: bool = False) -> str:
    codes_json = json.dumps(gm_service.list_giftcode_commands(), ensure_ascii=False).replace("</", "<\\/")
    return (
        _HTML_TEMPLATE
        .replace("__GM_KEY_REQUIRED__", "true" if gm_key_required else "false")
        .replace("__GIFTCODES_JSON__", codes_json)
    )
