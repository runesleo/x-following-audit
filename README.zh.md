# x-following-audit

English: [README.md](./README.md)

给关注列表做“低风险瘦身”的工作流：先审计、再复核、最后小批次执行。  
目标是提升信息质量，不是做高频自动化。

## 关注审计流水线

### What you get

- **静态打分分桶** — 把关注对象分成 `keep`、`maybe`、`unfollow_candidate`。
- **Recent 二次校验** — 对低置信账号补一层近期内容/活跃信号。
- **本地 HTML 审核页** — 支持搜索、筛选、勾选并导出执行清单。
- **安全批执行器** — 默认 `dry-run`，随机间隔，小批次执行，自动落日志。

### How it works

先跑只读审计，得到初筛结果；再用 recent 信号降低误伤；最后在本地 HTML 人工确认清单，再执行小批次动作。  
执行阶段默认不会真的取关，必须显式传 `--execute`。

```text
你: 我关注太多了，想安全清理掉低价值账号。

流程输出:
1) following_audit_*.json（静态分数）
2) following_audit_*_recent.json（recent 增强）
3) following_audit_*_recent.html（人工审核）
4) unfollow_run_*.json（执行日志）
```

### Setup

**Claude Code:**
```bash
git clone https://github.com/runesleo/x-following-audit.git
cd x-following-audit
npm install
```

**本地终端:**
```bash
mkdir -p data/following_audit
cp samples/approved_unfollow.sample.txt data/following_audit/approved_unfollow.txt
```

**Any other AI agent:**
直接调用同一套 shell 命令即可，不依赖特定 IDE 运行时。

### Requirements

- 已安装并可用的 `xreach`
- Node.js 18+（执行 `puppeteer` 脚本）
- 可用的 `data/x_cookies.json`（`auth_token` / `ct0`）
- 就这些。请坚持小批次 + 人工复核。

### Supported input

| 输入 | 示例 | 作用 |
|-------|---------|------------|
| 目标账号 | `--handle your_handle` | 拉取 following 列表 |
| 静态审计文件 | `following_audit_20260521_124427.json` | 生成 recent 增强版 |
| 执行清单 | 每行一个 `@handle` | 批处理执行输入 |
| 白名单 | 每行一个 `@handle` | 强制保留 / 执行跳过 |

### Data sources

| 数据源 | 提供内容 |
|-----|-----------------|
| `xreach following` | 关注列表和基础画像 |
| `xreach tweets` | 候选账号近期内容与活跃信号 |
| X 登录态 cookie | 批执行阶段的网页登录上下文 |

### Known limitations (v0.1.0)

- 基于登录态自动化，不是官方稳定 API 协议。
- X 页面或接口变动可能导致按钮识别失效。
- 本项目刻意不支持高频、大规模自动执行。

## Roadmap

**评分质量**
- [ ] 增加可插拔关键词包 — 适配不同赛道。
- [ ] 增加误判反馈回路 — 提升下一批建议质量。

**安全控制**
- [ ] 增加每日动作硬上限 — 超限自动停止。
- [ ] 增加执行前登录态探针命令 — 先验状态再开跑。

**审核体验**
- [ ] 增加 static vs recent 分数对比视图 — 更快复核。
- [ ] 增加一键导出预设（红区/人工复核）— 减少手工操作。

**API** (planned)
- [ ] REST API for all tools above — integrate into your own apps.

## About the author

*关于作者：Leo ([@runes_leo](https://x.com/runes_leo))，AI x Crypto 独立构建者。在 [Polymarket](https://polymarket.com/?r=githuball&via=runes-leo&utm_source=github&utm_content=x-following-audit) 做量化交易，用 Claude Code 和 Codex 搭建数据分析与自动化交易系统。*

*[leolabs.me](https://leolabs.me)：文章 · 社群 · 开源工具 · 独立项目 · 全平台账号*

*[X 订阅](https://x.com/runes_leo/creator-subscriptions/subscribe)：付费内容周更，或请我喝杯咖啡 😁*

*Learn in public, Build in public.*
