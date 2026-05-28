"""Web-based real-time monitor for ytb-downloader.

Serves a dashboard at http://localhost:PORT that shows download progress
for all categories with progress bars, logs, and stall detection.
"""
import http.server
import json
import os
import sys
from pathlib import Path

PORT = int(os.environ.get("MONITOR_PORT", "8080"))
HOST = os.environ.get("MONITOR_HOST", "0.0.0.0")
STATE_FILE = "download_state.json"

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ytb-downloader 监控面板</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, 'Segoe UI', 'PingFang SC', sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }
  h1 { font-size: 1.4rem; margin-bottom: 4px; color: #38bdf8; display: flex; align-items: center; gap: 12px; }
  h1 small { font-size: 0.8rem; color: #64748b; font-weight: normal; }
  .subtitle { color: #64748b; font-size: 0.85rem; margin-bottom: 20px; }
  .stats-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 20px; }
  .stat-card { background: #1e293b; border-radius: 10px; padding: 14px 16px; text-align: center; border: 1px solid #334155; }
  .stat-card .value { font-size: 1.8rem; font-weight: 700; color: #38bdf8; line-height: 1.2; }
  .stat-card .label { font-size: 0.75rem; color: #94a3b8; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-card.running .value { color: #f59e0b; }
  .stat-card.done .value { color: #22c55e; }
  .stat-card.error .value { color: #ef4444; }
  .current-box { background: #1e293b; border-radius: 10px; padding: 14px 18px; margin-bottom: 16px; border: 1px solid #334155; display: flex; align-items: center; gap: 12px; }
  .current-box .spinner { width: 12px; height: 12px; border: 2px solid #38bdf8; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; flex-shrink: 0; }
  .current-box .cat-name { font-weight: 600; color: #38bdf8; }
  .current-box .detail { color: #94a3b8; font-size: 0.85rem; }
  .current-box .detail .vid { color: #e2e8f0; font-family: 'Courier New', monospace; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .stall-banner { background: #450a0a; border: 1px solid #ef4444; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; color: #fca5a5; font-size: 0.9rem; font-weight: 600; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .stall-actions { display: flex; gap: 8px; align-items: center; margin-left: auto; }
  .stall-actions button { background: #ef4444; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 600; }
  .stall-actions button:hover { background: #dc2626; }
  .stall-hint { color: #94a3b8; font-size: 0.75rem; font-weight: normal; }
  .stall-ok { background: #052e16; border: 1px solid #22c55e; border-radius: 8px; padding: 8px 14px; margin-bottom: 16px; color: #86efac; font-size: 0.8rem; display: inline-block; }
  .table-wrap { overflow-x: auto; margin-bottom: 20px; border-radius: 10px; border: 1px solid #334155; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { background: #1e293b; color: #94a3b8; font-weight: 600; padding: 10px 14px; text-align: left; position: sticky; top: 0; white-space: nowrap; }
  td { padding: 8px 14px; border-top: 1px solid #1e293b; }
  tr:hover td { background: rgba(56, 189, 248, 0.03); }
  .progress-wrap { display: flex; align-items: center; gap: 10px; min-width: 160px; }
  .progress-bar { flex: 1; height: 8px; background: #334155; border-radius: 4px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 4px; background: #3b82f6; transition: width 0.5s ease; }
  .progress-fill.complete { background: #22c55e; }
  .progress-fill.partial { background: #f59e0b; }
  .progress-text { white-space: nowrap; font-size: 0.8rem; color: #94a3b8; min-width: 65px; text-align: right; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
  .badge.running { background: #3b82f6; }
  .badge.completed { background: #22c55e; }
  .badge.pending { background: #475569; }
  .badge.partial { background: #f59e0b; color: #0f172a; }
  .badge.error { background: #ef4444; }
  .failed-num { color: #ef4444; font-size: 0.8rem; text-align: center; }
  .log-section { background: #1e293b; border-radius: 10px; border: 1px solid #334155; overflow: hidden; }
  .log-header { padding: 10px 14px; color: #94a3b8; font-size: 0.8rem; font-weight: 600; border-bottom: 1px solid #334155; text-transform: uppercase; letter-spacing: 0.5px; }
  .log-body { max-height: 300px; overflow-y: auto; padding: 4px 0; }
  .log-entry { padding: 3px 14px; font-size: 0.78rem; font-family: 'Courier New', monospace; color: #94a3b8; }
  .log-entry:nth-child(odd) { background: rgba(255,255,255,0.015); }
  .log-entry .t { color: #475569; margin-right: 8px; }
  .config-summary { color: #64748b; font-size: 0.75rem; margin-bottom: 16px; display: flex; gap: 16px; flex-wrap: wrap; }
  .config-summary span { background: #1e293b; padding: 4px 10px; border-radius: 4px; }
  .footer { text-align: center; color: #475569; font-size: 0.75rem; margin-top: 16px; }
  @media (max-width: 768px) {
    body { padding: 12px; }
    h1 { font-size: 1.1rem; }
    .stats-row { grid-template-columns: repeat(3, 1fr); }
    .stat-card .value { font-size: 1.3rem; }
    .progress-wrap { min-width: 100px; }
  }
</style>
</head>
<body>
<h1>ytb-downloader 监控面板 <small id="refresh-info"></small></h1>
<div class="subtitle">YouTube 批量下载 · 实时刷新</div>
<div id="config-info" class="config-summary"></div>
<div id="stats" class="stats-row"><div class="stat-card"><div class="value">—</div><div class="label">加载中...</div></div></div>
<div id="current"></div>
<div id="stall-warn"></div>
<div id="table-container"></div>
<div class="log-section">
  <div class="log-header">运行日志</div>
  <div id="log" class="log-body"></div>
</div>
<div class="footer">ytb-downloader · Auto-refresh every 2s</div>

<script>
const REFRESH_MS = 2000;
const STALL_WARN_SEC = 180;
let lastTotalDownloaded = -1;
let lastIncreaseTime = Date.now();

async function fetchState() {
  try {
    const r = await fetch('/api/state?' + Date.now());
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

function fmt(s) { return (s || '').toString().replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function render() {
  fetchState().then(state => {
    if (!state) {
      document.getElementById('stats').innerHTML = '<div class="stat-card error"><div class="value">—</div><div class="label">连接失败</div></div>';
      document.getElementById('refresh-info').textContent = '连接失败';
      return;
    }
    const o = state.overall || {};
    const cats = state.categories || {};
    const cur = state.current || {};
    const cfg = state.config || {};
    const entries = Object.entries(cats);
    const completed = entries.filter(([,c]) => c.status === 'completed' || c.downloaded >= c.target).length;
    const totalDownloaded = entries.reduce((s, [,c]) => s + c.downloaded, 0);
    const totalFailed = entries.reduce((s, [,c]) => s + (c.failed || 0), 0);
    const totalTarget = entries.reduce((s, [,c]) => s + c.target, 0);
    const running = entries.filter(([,c]) => c.status === 'running').length;

    // Stall detection
    const now = Date.now();
    if (lastTotalDownloaded >= 0 && totalDownloaded > lastTotalDownloaded) lastIncreaseTime = now;
    if (lastTotalDownloaded < 0) { lastTotalDownloaded = totalDownloaded; lastIncreaseTime = now; }
    lastTotalDownloaded = totalDownloaded;
    const stallSec = (now - lastIncreaseTime) / 1000;
    const isStalled = o.is_running && stallSec > STALL_WARN_SEC && running > 0;
    const stallMin = Math.floor(stallSec / 60);

    // Config info
    document.getElementById('config-info').innerHTML = `
      <span>Worker: ${cfg.workers || '?'}</span>
      <span>Proxy: ${cfg.proxy || 'off'}</span>
      <span>时长上限: ${cfg.max_duration || '?'}s</span>
    `;

    // Stats
    document.getElementById('stats').innerHTML = `
      <div class="stat-card"><div class="value">${completed}/${entries.length}</div><div class="label">类别完成</div></div>
      <div class="stat-card"><div class="value">${totalDownloaded}</div><div class="label">已下载</div></div>
      <div class="stat-card"><div class="value">${totalTarget}</div><div class="label">目标总量</div></div>
      <div class="stat-card ${totalFailed > 0 ? 'error' : ''}"><div class="value">${totalFailed}</div><div class="label">失败</div></div>
      <div class="stat-card ${o.is_running ? 'running' : 'done'}"><div class="value">${o.is_running ? '运行中' : '已完成'}</div><div class="label">${running > 0 ? running + ' 活跃' : '状态'}</div></div>
    `;
    document.getElementById('refresh-info').textContent = new Date().toLocaleTimeString();

    // Current activity
    const cd = document.getElementById('current');
    if (cur.category && cur.status !== 'completed' && cur.status !== 'initializing') {
      cd.innerHTML = `<div class="current-box">
        <div class="spinner"></div>
        <div>
          <span class="cat-name">${fmt(cur.category)}</span>
          ${cur.video_id ? ` <span class="detail">· <span class="vid">${fmt(cur.video_id)}</span> ${fmt(cur.title ? '— ' + cur.title : '')}</span>` : ''}
          ${cur.message ? ` <span class="detail">· ${fmt(cur.message)}</span>` : ''}
          <span class="detail">· ${fmt(cur.status)}</span>
        </div>
      </div>`;
    } else if (o.is_running) {
      cd.innerHTML = `<div class="current-box"><div class="spinner"></div><div><span style="color:#94a3b8">等待中...</span></div></div>`;
    } else {
      cd.innerHTML = `<div class="current-box"><div style="color:#22c55e;font-weight:600">全部完成</div></div>`;
    }

    // Stall warning
    const warnEl = document.getElementById('stall-warn');
    if (isStalled) {
      warnEl.innerHTML = `<div class="stall-banner">
        下载已停止（${stallMin} 分钟无新增视频）
        <div class="stall-actions">
          <button onclick="checkCookie()">检查 Cookie</button>
          <button onclick="checkProxy()">检查代理</button>
          <span class="stall-hint">复制信息 → 排查</span>
        </div>
      </div>`;
      warnEl.style.display = 'block';
    } else if (o.is_running && running > 0) {
      const idleMin = Math.floor(stallSec / 60);
      const idleSec = Math.floor(stallSec % 60);
      warnEl.innerHTML = `<div class="stall-ok">${idleMin > 0 ? idleMin+'分' : ''}${idleSec}秒前有新增视频</div>`;
      warnEl.style.display = 'block';
    } else {
      warnEl.style.display = 'none';
    }

    // Table
    let html = '<div class="table-wrap"><table><thead><tr><th>类别</th><th>状态</th><th>进度</th><th>失败</th></tr></thead><tbody>';
    for (const [name, cat] of entries) {
      const pct = cat.target > 0 ? Math.min(100, Math.round((cat.downloaded / cat.target) * 100)) : 0;
      const badge = cat.status === 'completed' || cat.downloaded >= cat.target ? 'completed' : cat.status === 'running' ? 'running' : cat.status === 'partial' ? 'partial' : 'pending';
      const fill = cat.status === 'completed' || cat.downloaded >= cat.target ? 'complete' : cat.status === 'partial' ? 'partial' : '';
      html += `<tr>
        <td>${fmt(name)}</td>
        <td><span class="badge ${badge}">${badge === 'running' ? '下载中' : badge === 'completed' ? '已完成' : badge === 'partial' ? '部分' : '等待中'}</span></td>
        <td><div class="progress-wrap"><div class="progress-bar"><div class="progress-fill ${fill}" style="width:${pct}%"></div></div><span class="progress-text">${cat.downloaded}/${cat.target}</span></div></td>
        <td class="failed-num">${cat.failed || 0}</td>
      </tr>`;
    }
    html += '</tbody></table></div>';
    const tc = document.getElementById('table-container');
    const existing = tc.querySelector('table');
    if (existing) existing.outerHTML = html.match(/<table>[\s\S]*<\/table>/)?.[0] || '';
    else tc.innerHTML = html;

    // Log
    const logs = state.log || [];
    const logEl = document.getElementById('log');
    logEl.innerHTML = logs.slice(-80).reverse().map(l =>
      `<div class="log-entry"><span class="t">${(l.time || '').slice(11,19)}</span>${fmt(l.message)}</div>`
    ).join('');
  });
}

function checkCookie() {
  const info = `【Cookie 排查】
1. 浏览器打开 youtube.com → 确认登录状态
2. 用 Get cookies.txt 扩展导出 Netscape 格式
3. 覆盖项目根目录 cookies.txt
4. 如需检查 cookie 文件，发 cookies.txt 给我`;
  navigator.clipboard.writeText(info).catch(()=>{});
  alert(info);
}

function checkProxy() {
  const info = `【代理排查】
1. Clash / V2Ray 是否运行？代理端口是否正确？
2. 浏览器访问 google.com 确认能翻墙
3. 尝试切换节点
4. 如问题持续，查看 Clash 日志或联系我`;
  navigator.clipboard.writeText(info).catch(()=>{});
  alert(info);
}

render();
setInterval(render, REFRESH_MS);
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            self._json_response()
        elif path == "/":
            self._html_response()
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            state = json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
            self.wfile.write(json.dumps(state, ensure_ascii=False).encode("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.wfile.write(b'{"error":"state_file_not_found"}')

    def _html_response(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))


def serve(port: int | None = None, host: str | None = None) -> None:
    """Start the web monitor server (blocking)."""
    bind_host = host or HOST
    bind_port = port or PORT
    server = http.server.HTTPServer((bind_host, bind_port), Handler)
    url = f"http://localhost:{bind_port}"
    print(f"\n{'='*50}")
    print(f"  ytb-downloader 监控面板")
    print(f"  {url}")
    print(f"{'='*50}")
    print(f"  Ctrl+C 退出\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down monitor...")
        server.shutdown()
