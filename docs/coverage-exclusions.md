# Coverage scope and reviewed exclusions

Reviewed by the repository owner on 2026-08-23 for ADR-254. The enforced core
contains deterministic catalog, configuration provenance, guard, registry,
serialization, data-store, and graph-projection code. Every included report must
clear 95% line and branch coverage independently.

The following maintained files are excluded from the instrumented Sonar coverage
gate but remain covered by named real tests:

| Files | Reason | Required evidence |
| --- | --- | --- |
| `src/ui/app.js` | Browser event orchestration; Chromium precise coverage has no stable semantic JavaScript branch IDs. | Full Selenium suite, ten visual cases, four reviewed viewports, and daily real Gherkin run. |
| `src/model_builder/builder.py`, `factory.py`, `tracing.py`, `introspection.py`, `blocks.py` | Model construction and tracing deliberately replace Python frame tracing and execute native Torch/Transformers paths. | Real generated-artifact, tracing/block, catalog, drift, and packaged-site tests. |
| `src/model_builder/semantics.py`, `staged.py`, `hf_config.py` | Generated semantic/catalog integration is validated as parsed artifacts and across all published models. | Semantic, staged, configuration, schema, deterministic generation, browser, and UAT tests. |
| `src/model_builder/validate.py`, `drift.py`, `__main__.py` | CLI and full-catalog integration paths operate on the 244 MB checked-in runtime catalog. | Real CLI fixture tests plus the mandatory full drift command in CI. |
| `src/__init__.py`, `src/model_builder/__init__.py` | Package markers and schema constant contain no decision logic. | Import and build tests. |

An exclusion may be removed only when its replacement report preserves real model
execution and supplies stable line and branch identifiers. Changes to this table
require review in the same pull request as the coverage configuration.
