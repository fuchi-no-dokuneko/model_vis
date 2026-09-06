# Reusable maintenance prompt

Use the following for the next maintenance pass. Read the actual manifest and
target state before choosing the next batch; do not add the same 50 again.

> Understand this repository and create a new feature branch from the current
> main branch. Read README.md, spec.txt, ammend.md, ammend2.md, ammend3.txt,
> ammend4.txt, docs/generated-assets.md, and docs/catalog-expansion.md first.
>
> Preserve networking, the local serving method, deployment methods, and all
> CI/CD workflow files. Keep security refactoring outside this task. Continue
> using the existing offline tracing and static viewer pipeline.
>
> Spend up to one hour fixing a reproducible bug that materially affects a
> user's ability to explore a model. Add a regression test that fails before
> the fix and passes afterward. Spend up to two hours implementing a useful
> feature with keyboard access, clear empty/error states, and browser validation.
> Use shared behavior and generated facts; do not add per-model frontend rules.
>
> Generate and publish 50 additional model families/versions beyond the verified
> starting target set. Preserve every existing model, choose distinct new
> structures, record the exact include list, and require successful offline
> forward traces and validated graph/source/semantic assets. Use the pinned
> official config mapping where available; visibly mark compact-config records
> without official provenance as partial. Never count failed attempts, duplicate
> aliases, an empty manifest entry, or a planned build as generated models.
>
> Run the existing unit, browser, integrity, drift, coverage, and UAT gates. Keep
> the original reference metrics and visual assertions. Update scope-dependent
> tests to verify the full resulting catalog, not just the original batch.
>
> Publish through the existing deployment workflow. Verify the deployed commit,
> target manifest, every additional model's served assets, and browser behavior.
> Finish by updating the current guide with commands that actually exist,
> accurate counts, config provenance limits, test results, and deployment
> evidence. If publication is blocked, keep the objective unfinished and report
> the precise blocking step; do not claim that local generation proves the
> target is updated.
