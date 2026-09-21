# 国学 × AI 全网情报站

一个部署在 GitHub Pages 的公开信息聚合站，聚焦三个主题：

- 国学：传统文化、古籍、诗词、儒释道、中医文化等
- AI：大模型、生成式 AI、智能体、产品与研究进展
- 国学 × AI：古籍数字化、知识库、文化数字人、AI 解读与创作

## 覆盖平台

微信公众号、微博、知乎、小红书、抖音、哔哩哔哩、今日头条、YouTube、X、Reddit、Hacker News、arXiv。

采集器通过 Google News 的公开 RSS 查询各平台已被公开索引的页面，不登录账号、不绕过验证码或反爬限制。因搜索引擎收录存在延迟，数据适合做内容雷达，不应当作平台完整数据库。

## 自动更新

GitHub Actions 每天北京时间 08:15 和 20:15 自动运行：

1. `scripts/collect_sources.py` 拉取公开 RSS，清洗、去重并分类。
2. `scripts/generate_site.py` 生成首页、平台矩阵、选题库和归档页。
3. 构建结果自动发布到 GitHub Pages。

也可以在 Actions 页手动运行 `Guoxue AI Radar`。

## 本地预览

```bash
python scripts/collect_sources.py  # 可选，需要联网
python scripts/generate_site.py
python -m http.server 8000 --directory public
```

打开 `http://localhost:8000`。

## 配置

编辑 `site.config.json` 即可增减平台、关键词、回看天数和每个平台的条目上限。`content/materials.json` 是最近一次快照，采集全部失败时会保留上一份数据，避免线上页面突然清空。

## 内容边界

本站只展示标题、短摘要、平台分类和原始链接。引用、转载或用于商业内容前，请回到原平台核验作者、发布时间和授权条件。
