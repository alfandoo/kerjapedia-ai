# Repository Guidelines

## Project Structure & Module Organization

This repository contains product documentation and source legal documents for KerjaPedia AI, a RAG-based Indonesian employment regulation assistant.

- `docs/PRD_KerjaPedia_AI.md` is the first reference for scope, user flows, and retrieval requirements.
- `dataset/` stores official regulation PDFs grouped by topic, such as `Pengupahan dan THR`, `Keselamatan dan kesehatan kerja`, and `BPJS dan jaminan sosial ketenagakerjaan`.
- Keep new documents inside the closest topic folder. Add a folder only when no existing category fits.

## Build, Test, and Development Commands

Monorepo FastAPI (`apps/api`) + Next.js (`apps/web`):

- Backend: `cd apps/api && .venv\Scripts\python -m pytest` (tests), `ruff check app tests` (lint)
- Frontend: `cd apps/web && npm run lint`, `npm run build`, `npm run test:e2e`
- Retrieval Upstash: `apps\api\.venv\Scripts\python scripts\index_upstash.py --dry-run`
- `git status` checks pending changes.

## Coding Style & Naming Conventions

For Markdown, use clear headings, short paragraphs, and numbered lists for ordered workflows. Keep terminology consistent with the PRD.

For dataset files, prefer descriptive legal names that include regulation type, number, and year, for example `PP Nomor 35 Tahun 2021.pdf`. Avoid renaming source PDFs unless the new name improves traceability.

Future source code should follow its configured formatter and linter. Keep module names lowercase and descriptive, such as `retrieval`, `ingestion`, or `citations`.

## Testing Guidelines

Automated suites: `apps/api/tests` (pytest: ingestion, retrieval, answering, eval, security) and `apps/web/tests` (Playwright E2E). For RAG work, test document ingestion, metadata extraction, retrieval ranking, citation formatting, and refusal behavior. Use small excerpts instead of full PDFs where possible.

Name tests after behavior, for example `test_retrieves_latest_upah_minimum_rule`.

## Commit & Pull Request Guidelines

No local Git history is available to infer an existing convention. Use concise, imperative commit messages such as `Migrate vector pipeline to Upstash hosted hybrid embeddings`.

Pull requests should include a short summary, affected folders, validation performed, and screenshots only when UI changes are introduced. For dataset updates, mention the document source URL and whether the regulation replaces or amends an older file.

## Security & Configuration Tips

Do not commit secrets, API keys, private notes, or generated vector indexes unless explicitly required. Prefer official government or BPK regulation sources and preserve enough metadata for users to verify citations.

<!-- antislop:start -->
## antislop
For UI, copy, people, mobile layout, or code comments work, read `.opencode/skills/antislop/SKILL.md` (core) and then the skill for the task:
- UI / visual: `.opencode/skills/antislop-ui/SKILL.md`
- Copy & text: `.opencode/skills/antislop-copywriting/SKILL.md`
- People: `.opencode/skills/antislop-human/SKILL.md`
- Mobile / responsive: `.opencode/skills/antislop-layoutmobile/SKILL.md`
- Code comments: `.opencode/skills/antislop-code/SKILL.md`
Before starting, ask the user when antislop applies: during the work, or after it is done.
Standing mode (user-approved): DURING. Apply all antislop skills automatically to relevant work without asking first; still ask only where the rules require a user decision (design direction, asset creation, audit approvals).
<!-- antislop:end -->
