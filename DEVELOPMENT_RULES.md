# MY Hot Radar — Development Rules

> Hard rules for anyone (human or AI) writing code or content for MY Hot Radar.
> These rules are **constraints**, not aspirations — break only with an explicit, documented decision.

---

## Stability

1. **Keep the current live site stable.** Anything deployed to production must not regress.
2. **Do not refactor the whole project for a small change.** Touch only what the task requires.
3. **One Batch at a time.** Each batch ships one logical scope, and is verified before the next begins.

## Tech stack

4. **Vanilla HTML / CSS / JS only** by default.
5. **Do not introduce npm, bundlers, frameworks, or external runtimes** without an explicit decision.
6. **Do not introduce React, Vue, Bootstrap, Tailwind, or similar UI frameworks**.
7. **Do not import external fonts** (no Google Fonts, no font CDN).
8. **No external `<script src=>` unless explicitly part of the task** (Cloudflare Pages auto-injected Web Analytics is accepted infrastructure, not user code).
9. **No hot-linked external images** — SVG, CSS block, or local asset only.

## Quality bar

10. **Mobile-first.** Test on 360 / 375 / 390 / 412 / 768 / 1024 / 1440 widths.
11. **No horizontal overflow** on any tested width.
12. **SEO baseline on every page**: `<title>`, meta description, canonical, OG, Twitter, viewport, `lang="en"`.
13. **Accessibility baseline**: exactly one `<h1>`, clean H1→H2→H3 hierarchy, semantic landmarks, `aria-label` / `aria-hidden` where appropriate, decorative SVG marked `aria-hidden="true"`.
14. **Heading hierarchy in footer**: footer column titles must be `<p class="site-footer__heading">`, NOT `<h4>` (production rule — see `EXPERIENCE.md` for the original incident).

## Content integrity (content shown on the site or in posts)

15. **Demo content must be visibly labelled** as `SAMPLE` or `DEMO`.
16. **No fake news sources.** A Demo article's source box may say "Demo content for MY Hot Radar MVP" — never fabricate a news outlet or wire copy.
17. **No fake authors.** Author line may read "MY Hot Radar (demo)" or similar, never a real-sounding journalist name.
18. **No fake contact details.** Email / phone / address are not invented to fill the contact form.
19. **No fake engagement metrics.** Never write "全网炸锅", "全马哀悼", "X thousand views", "X percent poll" without a public, citable number.
20. **No prematurely declaring a topic viral.** Status labels are based on propagation signals, not on event importance.
21. **MVP disclaimer must remain visible** above the footer on every page.

## Git

22. **Normal Git workflow only** — `git add`, `git commit`, `git push`.
23. **NEVER use `git commit --amend`** on any commit, including empty trigger commits.
24. **NEVER use `git rebase`** (no interactive, no non-interactive, no pull-rebase into master).
25. **NEVER squash** commits.
26. **NEVER use `git push --force`** (no `--force`, no `--force-with-lease`, no `-f`).
27. **NEVER use `git reset --hard`**. Soft / mixed reset for local cleanup only.
28. **Do not destroy history.** If a commit is wrong, add a new corrective commit.
29. **One commit per logical change** (Batch scope).
30. **Commit messages must be descriptive**, in English, stating the Batch number when applicable.
31. **Do not commit working build artefacts**, lockfiles, or dependencies that aren't actually used.

## Batch discipline

32. **Each Batch ends with a QA report**. No batch is "done" without it.
33. **A failing QA must not be hand-waved.** Either fix and re-QA, or roll back.
34. **Do not start the next Batch automatically** — always wait for user confirmation.
35. **Production verification follows every merge.** Verify on the actual production URL, not just locally.

## Auto-evolution & experience library (see `EXPERIENCE.md`)

36. **Only verified, repeatable knowledge** goes into `EXPERIENCE.md`.
37. **One-time observations** stay out of the library.
38. **Pattern candidate → verified** — a candidate pattern must be observed **at least twice** in independent tasks before it becomes a rule.
39. **Unverified guesses MUST NOT** be written into `EXPERIENCE.md` as rules. They can be tracked elsewhere (notes, scratchpad) but not in the library.

## Out-of-scope for the MVP build (post-MVP only)

- Live news ingestion, crawlers, schedulers, AI writers.
- Database / persistence layer.
- Authentication, comments, members.
- Facebook / X / TikTok auto-publishing.
- Multi-language full localization.
- Analytics beyond Cloudflare Web Analytics.

These belong in the future-state documents. See `NEWS_RADAR.md`,
`CONTENT_RULES.md`, `VERIFICATION_RULES.md`, and the "Future Direction"
section of `PROJECT_CONTEXT.md`.
