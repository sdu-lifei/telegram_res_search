import html

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pansou_py.api.auth import verify_token
from pansou_py.core.transfer import transfer_service
from pansou_py.models.schemas import AdminStatsResponse, OpenResourceResponse, TransferStatusResponse

router = APIRouter()


@router.post("/api/resources/{resource_id}/open", response_model=OpenResourceResponse)
async def open_resource(
    resource_id: int,
    background_tasks: BackgroundTasks,
    wait: bool = Query(False),
):
    result = await transfer_service.open_resource(resource_id, enqueue=not wait)
    if result.get("status") == "pending" and result.get("job_id"):
        background_tasks.add_task(transfer_service.run_job_safely, result["job_id"])
    return result


@router.get("/api/resources/{resource_id}/status", response_model=TransferStatusResponse)
async def resource_transfer_status(resource_id: int):
    return await transfer_service.status(resource_id)


@router.get("/r/{resource_id}")
async def redirect_resource(resource_id: int, background_tasks: BackgroundTasks, request: Request):
    result = await transfer_service.open_resource(resource_id, enqueue=True)
    if result.get("status") == "ready" and result.get("url"):
        return RedirectResponse(result["url"], status_code=302)

    if result.get("status") == "pending" and result.get("job_id"):
        background_tasks.add_task(transfer_service.run_job_safely, result["job_id"])

    if "application/json" in request.headers.get("accept", ""):
        return result

    message = html.escape(result.get("message") or "资源正在检查，请稍后刷新。")
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>正在准备资源</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --surface: #ffffff;
      --text: #17212b;
      --muted: #607080;
      --line: #dce3ea;
      --primary: #1769e0;
      --success: #168a55;
      --danger: #c0352b;
      --shadow: 0 18px 50px rgba(23, 33, 43, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      min-height: 100vh;
      margin: 0;
      display: grid;
      place-items: center;
      padding: 22px;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }}
    main {{
      width: min(520px, 100%);
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 24px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 11px;
      margin-bottom: 18px;
    }}
    .mark {{
      display: grid;
      place-items: center;
      width: 38px;
      height: 38px;
      border-radius: 8px;
      background: var(--text);
      color: #fff;
      font-weight: 800;
    }}
    h1 {{ margin: 0; font-size: 22px; line-height: 1.3; font-weight: 760; }}
    p {{ line-height: 1.7; margin: 0 0 16px; color: var(--muted); }}
    .bar {{ height: 8px; background: #e7edf3; border-radius: 999px; overflow: hidden; margin: 18px 0 10px; }}
    .fill {{ width: 3%; height: 100%; background: var(--success); transition: width .25s ease; }}
    .progress-text {{ min-height: 22px; color: var(--muted); font-size: 13px; }}
    .actions {{ display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }}
    a {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 40px;
      padding: 0 14px;
      border-radius: 8px;
      background: #eaf2ff;
      color: var(--primary);
      text-decoration: none;
      font-weight: 650;
      font-size: 14px;
    }}
    .secondary {{ background: #f8fafc; color: #405160; border: 1px solid var(--line); }}
    @media (max-width: 520px) {{
      body {{ padding: 12px; place-items: start center; }}
      main {{ margin-top: 18px; padding: 18px; }}
      h1 {{ font-size: 20px; }}
      .actions {{ display: grid; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="brand">
      <div class="mark">搜</div>
      <div>
        <h1>正在准备资源</h1>
      </div>
    </div>
    <p id="message">{message}</p>
    <div class="bar"><div id="fill" class="fill"></div></div>
    <div class="progress-text" id="progressText">任务已提交 · 3%</div>
    <div class="actions">
      <a href="/r/{resource_id}">重新检查</a>
      <a class="secondary" href="/">返回搜索</a>
    </div>
  </main>
  <script>
    const messageEl = document.getElementById('message');
    const fillEl = document.getElementById('fill');
    const progressTextEl = document.getElementById('progressText');
    const startedAt = Date.now();
    const timeoutMs = 180000;

    async function poll() {{
      try {{
        const response = await fetch('/api/resources/{resource_id}/status', {{ headers: {{ accept: 'application/json' }} }});
        const data = await response.json();
        const progress = Math.max(3, Math.min(Number(data.progress) || 3, 100));
        fillEl.style.width = progress + '%';
        progressTextEl.textContent = (data.message || '正在处理') + ' · ' + progress + '%';

        if (data.message) {{
          messageEl.textContent = data.message;
        }}

        if (data.status === 'ready' && data.url) {{
          fillEl.style.width = '100%';
          progressTextEl.textContent = '资源可用 · 100%';
          messageEl.textContent = '资源可用，正在打开...';
          window.location.replace(data.url);
          return;
        }}

        if (data.status === 'failed') {{
          messageEl.textContent = data.message || '资源暂时不可用，请稍后重试。';
          progressTextEl.textContent = '检查失败';
          return;
        }}
      }} catch (error) {{
        messageEl.textContent = '正在等待服务响应...';
        progressTextEl.textContent = '连接重试中';
      }}

      if (Date.now() - startedAt < timeoutMs) {{
        setTimeout(poll, 2000);
      }} else {{
        messageEl.textContent = '仍在检查，可保持此页面或手动重试。';
        progressTextEl.textContent = '仍在处理中';
      }}
    }}

    setTimeout(poll, 1200);
  </script>
</body>
</html>"""
    return HTMLResponse(page, status_code=202 if result.get("status") == "pending" else 404)


@router.get("/api/admin/stats", response_model=AdminStatsResponse)
async def admin_stats(_=Depends(verify_token)):
    return await transfer_service.stats()
