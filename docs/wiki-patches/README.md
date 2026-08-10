# Pending wiki patches

The [GitHub wiki](https://github.com/wschosta/dod-budget-analysis/wiki) lives in
a separate repository (`dod-budget-analysis.wiki.git`) that automated sessions
cannot be granted push access to — GitHub does not expose wikis through the app
authorization that covers the code repository. Wiki edits made by an agent
therefore land here as patches for a human to apply.

## Applying

```bash
git clone https://github.com/wschosta/dod-budget-analysis.wiki.git
cd dod-budget-analysis.wiki
git am < ../dod-budget-analysis/docs/wiki-patches/0001-*.patch
git push origin master
```

Delete a patch file once it has been applied and pushed.

## Pending

| Patch | Page | Summary |
|---|---|---|
| `0001-deployment-refresh-command-and-fly-hosting.patch` | `Deployment.md` | Corrects `refresh_data.py` → `python -m pipeline.refresh` (the documented command never existed); adds Section 13 on Fly.io hosting and the single-machine constraint; documents `APP_FEEDBACK_PATH`, `APP_HOST`, `APP_DOCS_DIR`, `BACKUP_DIR`; removes `SUPPORTED_FISCAL_YEARS`, which appears nowhere in the codebase. |
