# Supported toolchain and upgrades

Production and test Python dependencies are exact in `pyproject.toml`; their
active transitive closures are exact in `requirements.lock` and
`requirements-test.lock`. JavaScript has no runtime packages, but
`package-lock.json` is committed so clean installs remain locked.
`.python-version`, `.node-version`, and `package.json` define supported runtimes.
Selenium uses the system Chromium and matching ChromeDriver binaries.

Install without resolving newer versions:

```bash
python3.13 -m venv venv
./venv/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.12.0+cpu
./venv/bin/python -m pip install --requirement requirements-test.lock
npm ci --ignore-scripts
```

Dependency upgrades are deliberate batches: update direct pins, create a clean
environment, regenerate both lockfiles, run unit/browser/visual tests, and run
the Python and npm release audits. High or critical production advisories block
release. Any exception must identify the advisory, affected package, rationale,
owner, expiry date, and compensating control in `security/advisory-exceptions.json`.
The Python audit submits package names and versions to OSV with IPv4-only curl;
the Node audit verifies the reviewed zero-dependency production lock.
