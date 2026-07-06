# 品牌出海热点速递

这是一个可发布到 GitHub Pages 的每日资讯网站。上线后，你只需要打开网站地址，就能看到每天自动生成的品牌出海热点。

## 它会做什么

- 每天北京时间 9:00 自动运行。
- 聚合品牌出海、跨境电商、内容电商、DTC 独立站、物流支付、合规政策等相关资讯。
- 生成一个可直接访问的网页：`public/index.html`。
- 只展示摘要、来源和链接，不转载全文。

## 发布到 GitHub Pages

1. 在 GitHub 新建一个仓库，例如 `brand-global-news`。
2. 把本目录里的文件上传到这个仓库。
3. 打开仓库的 `Settings`。
4. 进入 `Pages`。
5. 在 `Build and deployment` 里选择 `GitHub Actions`。
6. 打开仓库的 `Actions`，手动运行一次 `Daily Brand Global News`。
7. 运行成功后，GitHub Pages 会给出网站地址。

之后它会每天自动更新。默认更新时间是北京时间 9:00。

## 本地预览

如果只想先在电脑上看效果，可以运行：

```bash
python scripts/generate_site.py
```

然后打开：

```text
public/index.html
```

## 注意

这个网站默认是公开的。不要把账号、密钥、内部策略、客户名单或任何不希望公开的信息放进网页内容里。
