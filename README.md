# MY Hot Radar

Malaysia's Trending Radar — surfacing what is **heating up now**, not just what happened today.

> **MVP stage.** This repository ships a static, mobile-first front end with placeholder sample content. No CMS, no live data feeds, no automated publishing.

## Structure

```
/
├── index.html          Home
├── hot/                Hot Now
├── malaysia/           Malaysia
├── viral/              Viral
├── celebrity/          Celebrity
├── food/               Food & Lifestyle
├── world/              World
├── article/example/    Sample article
├── about/              About
├── contact/            Contact
├── privacy/            Privacy
├── terms/              Terms
└── assets/
    ├── css/style.css
    ├── js/main.js
    └── img/            logo, favicon, OG default
```

## Tech

- Pure static HTML / CSS / vanilla JS
- System font stack (no external font requests)
- Mobile-first responsive layout
- Designed for AdSense slots (placeholder only)

## Development

There is no build step. Open `index.html` in a browser, or serve locally:

```bash
python -m http.server 8000
# or
npx serve .
```

## Deploy

Upload the entire directory to any static host (Cloudflare Pages, Netlify, Vercel, S3 + CloudFront, or a plain web server).

Domain: https://myhotradar.com

## Roadmap (post-MVP)

- Live data ingestion
- Article CMS
- Newsletter signup
- Comments
- Localization (Bahasa Melayu, 中文)