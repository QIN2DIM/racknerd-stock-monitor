# RackNerd Stock Monitor (RackNerd 库存监控)

🚀 **RackNerd Stock Monitor** 是一个轻量、高效的 VPS 库存监控工具，专为抢购 RackNerd 特价机（如黑五、新年、双十一闪购套餐）而生。

还在为错过高性价比的神机而拍大腿吗？本项目可以全天候自动检测指定的 RackNerd 套餐补货状态，一旦发现库存，将在毫秒级延迟内通过 Telegram、Bark 或微信等渠道向您发送补货通知，助您快人一步！

## Web Frontend

仓库现在包含一个基于 `pnpm + Vite + TypeScript + Tabulator` 的静态前端，直接读取 `data/latest.json` 渲染库存表格。

本地开发：

```bash
cd web
pnpm install
pnpm dev
```

验证：

```bash
cd web
pnpm test
pnpm build
```

部署：

- GitHub Pages workflow 位于 `.github/workflows/pages.yml`
- 当 `web/**` 或 `data/latest.json` 更新并推送到 `main` 时，会自动构建并部署
- 构建时会把 `data/latest.json` 复制到产物目录，页面通过相对路径读取数据
