# what2eat-tokyo 🍜

> 小红书数据抓取当周东京圈好评的中餐厅，结合 Tabelog、谷歌地图数据，生成东京圈每日美食推荐。

---

## 功能概述

| 数据源 | 内容 |
|---|---|
| **小红书 (Xiaohongshu)** | 抓取当周东京圈高互动量的中餐厅帖子 |
| **Tabelog** | 爬取东京圈中餐厅评分与评价数量 |
| **Google Maps Places API** | 获取餐厅坐标、营业时间、谷歌评分 |

三方数据融合后，计算综合评分，每日推荐 Top-N 家餐厅，结果输出为 **JSON** 和 **Markdown** 文件。

---

## 项目结构

```
what2eat-tokyo/
├── main.py                      # 主入口
├── config.py                    # 配置（读取 .env）
├── requirements.txt
├── .env.example                 # 环境变量示例
├── scrapers/
│   ├── xiaohongshu.py           # 小红书抓取
│   ├── tabelog.py               # Tabelog 抓取
│   └── google_maps.py           # Google Maps Places API
├── processors/
│   └── data_merger.py           # 三方数据融合 + 评分
├── recommender/
│   └── daily_recommender.py     # 每日推荐生成
├── output/                      # 输出目录（JSON / Markdown）
├── tests/                       # 单元测试
└── .github/workflows/
    └── daily_recommendation.yml # GitHub Actions 每日自动运行
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写以下内容：

| 变量 | 说明 |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Google Maps Places API 密钥 |
| `XHS_COOKIE` | 登录小红书后，从浏览器开发者工具复制的完整 Cookie 字符串 |
| `XHS_SEARCH_KEYWORD` | 小红书搜索关键词（默认：`东京 中餐厅`） |
| `DAILY_TOP_N` | 每日推荐餐厅数量（默认：`5`） |

> **小红书 Cookie 获取方式**：浏览器打开 [xiaohongshu.com](https://www.xiaohongshu.com)，登录后打开开发者工具（F12）→ Network → 任意 XHR 请求 → 复制 `cookie:` 请求头的值。

### 3. 运行

```bash
# 完整模式（需要所有 API 密钥）
python main.py

# 仅使用 Tabelog（无需 API 密钥）
python main.py --tabelog-only

# 指定日期
python main.py --date 2024-04-16

# 仅打印结果，不写文件
python main.py --dry-run

# 推荐 Top 10
python main.py --top-n 10
```

输出文件位于 `output/` 目录：

- `recommendations_YYYY-MM-DD.json` — 结构化数据
- `recommendations_YYYY-MM-DD.md` — 人类可读的 Markdown 报告

---

## 评分算法

综合评分（0–10 分）由三个信号加权计算：

```
综合评分 = (Tabelog评分×0.4 + Google地图评分×0.35 + 小红书互动×0.25) / 总权重
```

- **Tabelog**：原始评分（1–5）归一化至 0–10
- **Google Maps**：原始评分（1–5）归一化至 0–10，并以评价数量进行对数修正
- **小红书**：`点赞×1 + 评论×2 + 分享×1.5`，上限修正后归一化至 0–10

每日推荐采用**轮转机制**：根据当天日期偏移排名列表，确保不同日期推荐不同餐厅。

---

## GitHub Actions 自动化

本项目内置 GitHub Actions 工作流，每天 08:00 JST（UTC 23:00）自动：

1. 抓取三方数据
2. 生成当日推荐
3. 将 `output/` 目录下的结果文件提交回仓库

**配置 Secrets（在仓库 Settings → Secrets and variables → Actions）**：

| Secret | 说明 |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Google Maps API 密钥 |
| `XHS_COOKIE` | 小红书登录 Cookie |

也可手动在 Actions 页面触发工作流（支持指定日期和仅 Tabelog 模式）。

---

## 运行测试

```bash
python -m pytest tests/ -v
```

---

## 注意事项

- **小红书**：需要有效的登录 Cookie，且 Cookie 有过期时间，需定期更新
- **Tabelog**：请遵守 Tabelog 使用条款，勿过于频繁抓取
- **Google Maps**：Places API 有免费额度限制，超出后收费
- 所有抓取均内置重试机制（指数退避）和礼貌延迟，降低对目标服务器的压力
