# 每日合规推广自动化

## 结论

复用服务器已有的 n8n。每天 10:17 运行一次，只从站点
`/guides/` 选择可公开引用的指南，通过官方 API 发布到自有账号，并记录
UTM 和公开帖子 URL。动态资源详情页不会进入推广队列。

## 免费渠道

| 渠道 | 接入方式 | 费用边界 |
| --- | --- | --- |
| Bluesky | 官方 AT Protocol | 免费，需要账号和 App Password |
| Mastodon | 实例官方 REST API | 通常免费，需要实例账号令牌 |
| Telegram | 官方 Bot API | 免费，需要公开频道和管理员 Bot |
| Discord | 官方 Webhook | 免费，适合自有社区，外部获客能力有限 |

X 官方 API 的带链接发帖目前按次收费；Reddit API 需要审批并禁止 spam。
贴吧没有适合无人值守推广的公开发帖 API。因此这三类渠道不做浏览器模拟、
验证码绕过或批量群发。

## 部署

1. 把 `deploy/daily-promotion.env.example` 复制为
   `/home/ubuntu/.config/pansou-promotion.env`，权限设为 `0600`，至少配置一个渠道。
2. 给 `deploy/n8n.service` 增加：

   ```ini
   EnvironmentFile=-/home/ubuntu/.config/pansou-promotion.env
   ```

3. 重载并重启 n8n：

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart n8n
   ```

4. 导入 `deploy/n8n-daily-promotion.workflow.json`，先手动执行一次，确认返回
   `published` 和公开帖子 URL 后再激活。

## 本地验证

默认只预览，不发布：

```bash
python3 scripts/daily_promotion.py --json --state /tmp/pansou-promotion-test.json
```

只有显式传入 `--live` 才会调用平台 API。成功记录写入状态文件，部分渠道失败时
不会重复发送已经成功的渠道；下次执行只补发失败渠道。

## 运营护栏

- 仅发布自有账号和自有频道。
- 只分发站内指南，不自动推广动态资源详情页。
- 每个指南准备 7 个不同角度，避免连续重复同一文案。
- 不购买流量、不刷互动、不自动评论、不抓取平台内容。
- 每周用服务器访问日志按 UTM 和 referrer 查看真人访问；技术扫描分数不能代替流量。
