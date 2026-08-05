# 出海内容素材雷达

一个部署在 GitHub Pages 上的个人内容素材工作台，面向出海品牌内容运营。

它不追新闻，只收集三类能直接变成选题的原料：

- **竞品广告素材**：竞品在 Meta / TikTok 正在投放的广告，每条附「可用角度」
- **用户痛点原话**：Amazon 评论、Reddit、社媒评论区里的用户原话，每条附「可改写成的选题」
- **趋势信号**：品类关键词的热度变化，附行动建议

素材进一步沉淀为**选题库**（topics.html，按 待做/进行中/已发布/已验证 推进），每日素材自动归档进**沉淀库**（archive.html）。

## 它是配置驱动的

赛道没定也能先用。确定赛道后只需要改 `site.config.json`：

```json
{
  "niche": "你的品类，如：宠物智能用品",
  "competitors": ["竞品品牌A", "竞品品牌B"],
  "keywords": ["品类英文关键词"]
}
```

## 每天怎么用

1. 让 AI 助手（如 WorkBuddy）按 `site.config.json` 里的竞品和关键词，去 Meta Ad Library、Amazon 评论、Google Trends 等来源收集素材
2. 素材写入 `content/materials.json`（格式见 `content/examples/materials.example.json`），`report_date` 改成当天
3. 推送到 main 分支，GitHub Actions 自动生成并发布网站

## 本地预览

```
python scripts/generate_site.py
```

然后打开 `public/index.html`。

## 注意

- 素材报告超过 7 天未更新时，部署会被拦截（保留线上已有版本）
- 网站默认公开，不要放入账号、密钥、客户信息等内容
