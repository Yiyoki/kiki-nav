# Kiki 工具导航

可爱猫娘风格的静态工具导航页，计划通过 GitHub + Cloudflare Pages 部署。

## 当前入口

- kikiapi: https://kikiapi.980822.xyz
- image 图片生成: https://kimage.980822.xyz
- grok 搜索: https://kikigrok.980822.xyz/webui
- OpenWebUI: https://webgpt.980822.xyz
- Ki梯挂了吗: ./pages/ki-ti-gua-le-ma.html

## 本地文件

```text
index.html
assets/styles.css
data/links.json
pages/tutorials.html
_headers
README.md
```

## Cloudflare Pages 设置

纯静态部署：

```text
Framework preset: None
Build command: 留空
Output directory: /
Production branch: main
```

## 注意

不要在前端写入任何 API key、访问密码或私密 token。
