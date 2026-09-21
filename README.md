# 国学内容与合规情报站

一个部署在 GitHub Pages 的公开情报站，服务两件事：

- 内容趋势：追踪经典文化、非遗民俗、易学民俗、中医文化和数字国学相关内容。
- 合规雷达：监测主要内容平台的官方规则页面，提示与国学创作相关的迷信、健康、宗教、营销和夸大承诺风险。

## 覆盖范围

内容来源包括微信公众号、微博、知乎、小红书、抖音、哔哩哔哩、今日头条、YouTube 和 X。采集器通过公开搜索 RSS 建立索引，不登录账号、不绕过验证码、反爬或付费墙。

合规来源优先使用抖音、小红书、微博、哔哩哔哩、微信公众平台和今日头条的官方规则或帮助页面。页面指纹变化只代表“疑似有变化”，必须打开官方规则人工确认。

## 自动更新

GitHub Actions 每天北京时间 08:15 和 20:15 自动运行：

1. `scripts/collect_sources.py` 拉取、清洗、去重并分类国学公开内容。
2. `scripts/collect_policies.py` 核验官方规则页面并记录变化状态。
3. `scripts/generate_site.py` 生成内容流、合规雷达、平台矩阵、选题库和归档。
4. 构建结果自动发布到 GitHub Pages。

也可以在 Actions 页手动运行 `Guoxue Content and Compliance Radar`。

## 本地预览

```bash
python scripts/collect_sources.py   # 可选，需要联网
python scripts/collect_policies.py  # 可选，需要联网
python scripts/generate_site.py
python -m http.server 8000 --directory public
```

打开 `http://localhost:8000`。

## 配置与边界

编辑 `site.config.json` 可增减内容来源、主题和官方规则页面。`content/materials.json` 与 `content/policies.json` 是最近一次快照。

本站仅展示公开信息索引与运营风险提示，不构成法律意见，也不保证平台最终审核结果。引用、转载或发布商业内容前，请回到原始内容及平台官方规则核验。
