# Roadmap: 3.1.0 Release

**Target release:** 3.1.0  
**Current version:** 3.0.0  
**Epic:** [#13](https://github.com/virtalabs/bf-opencore/issues/13)  
**Milestone:** [v3.1.0](https://github.com/virtalabs/bf-opencore/milestone/1)

## Overview

Epic to improve bf-opencore app-level configuration and developer experience. This epic focuses on **app-level concerns only** - middleware, logging, documentation, and CI for app testing. Production deployment concerns (production settings, gunicorn, health checks) belong in the blueflow-saas repo (virtalabs/blueflow), not this library.

## Goals

1. **App configuration** — Whitenoise middleware, structured logging
2. **Automation** — CI pipeline for app tests and migration checks
3. **Developer experience** — Clear onboarding via `.env.example` and structure
4. **Structure** — Documented project layout and conventions

## Themes

- **Config:** Whitenoise middleware, structured logging
- **Documentation:** `.env.example` for contributors
- **CI:** GitHub Actions for app testing, `makemigrations --check`
- **Structure:** Document/formalize app structure

## Child Issues

| #   | Issue                                                     | Title                                                              | Type  | Status |
| --- | --------------------------------------------------------- | ------------------------------------------------------------------ | ----- | ------ |
| 14  | [#14](https://github.com/virtalabs/bf-opencore/issues/14) | feat: Add Whitenoise for static file serving in production         | feat  | Open   |
| 18  | [#18](https://github.com/virtalabs/bf-opencore/issues/18) | feat: Configure structured logging with configurable log level     | feat  | Open   |
| 19  | [#19](https://github.com/virtalabs/bf-opencore/issues/19) | chore: Add GitHub Actions CI pipeline                              | chore | Open   |
| 20  | [#20](https://github.com/virtalabs/bf-opencore/issues/20) | chore: Add .env.example documenting required environment variables | chore | Open   |
| 21  | [#21](https://github.com/virtalabs/bf-opencore/issues/21) | chore: Run makemigrations --check and check --deploy in CI         | chore | Open   |

## Suggested Implementation Order

1. **chore: Add .env.example** (#20) — Foundation for documentation and onboarding
2. **feat: Add Whitenoise** (#14) — Static file serving middleware configuration
3. **feat: Configure structured logging** (#18) — Production logging practices
4. **chore: Add GitHub Actions CI pipeline** (#19) — Automation foundation
5. **chore: Run makemigrations --check in CI** (#21) — Migration validation

## Success Criteria

- [ ] All child issues closed and merged
- [ ] CI passes on push (lint, tests, migration check)
- [ ] New contributors can bootstrap from `.env.example`
- [ ] App-level configuration is production-ready (Whitenoise, logging)

## Notes

- **STATIC_ROOT fix** is tracked in 3.0.0 milestone, not 3.1.0
- **Production deployment issues** (#15, #16, #17) were moved to [blueflow repo](https://github.com/virtalabs/blueflow):
  - Production settings → [blueflow#2744](https://github.com/virtalabs/blueflow/issues/2744)
  - Gunicorn configuration → [blueflow#2745](https://github.com/virtalabs/blueflow/issues/2745)
  - Health check endpoint → [blueflow#2746](https://github.com/virtalabs/blueflow/issues/2746)
- All remaining issues are linked as sub-issues to epic #13
- All remaining issues are assigned to milestone v3.1.0
- **Out of scope:** Production deployment concerns belong in blueflow-saas repo, not bf-opencore library
