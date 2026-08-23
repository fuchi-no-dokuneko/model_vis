# Generated asset ownership

The repository keeps `model_code/` because it is the static viewer's deployable
runtime data. A clean checkout must include it. `src/model_builder/`,
`src/schemas/`, `profiles/`, `model.txt`, and `official_configs/` are its source
inputs; `scripts/build-ui.mjs` copies the viewer and runtime data into `build/`.

`build/`, `build_cache/`, `.wrangler/`, browser profiles, test reports, virtual
environments, and package installation directories are transient and ignored.
Redistributed package license texts under `license/source-packages/` are reviewed
inputs and are committed when their corresponding source assets are published.

Regenerate semantic catalog files without running model inference:

```bash
./venv/bin/python -m src.model_builder.semantics --model-code model_code
```

Build the deployable site:

```bash
npm run build-ui -- --model-code model_code --out build
```

The drift check introduced with ADR-249 is the authoritative clean-tree check.
It normalizes documented volatile metadata before comparing two independent
generations and the checked-in runtime catalog.
