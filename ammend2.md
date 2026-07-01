1)Add a persistent graph legend. Explain node kinds, layer colors,
     boundary nodes, selection colors, edge direction, and confidence line
     styles. The CSS defines these semantics, but the canvas never explains
     them.
2) Introduce semantic zoom. At low zoom show module names and major
     routes; at medium zoom show shapes; at high zoom reveal ports, dtype,
     alias, and mutation details. Currently the whole node shrinks until labels
     become unreadable.

3)Put explicit drill controls on nodes. Add visible “Open module,” “Show
     operations,” and “Go to parent” actions. Double-click and Enter drill down,
     but this behavior is not discoverable
   4)Add unified graph search. Search modules, operations, tensor IDs, port
     names, shapes, and source symbols; highlight matches on both canvas and
     minimap. The existing module search only filters the tree.
     5)Add upstream/downstream path tracing. Selecting a node or port should
     offer “trace inputs,” “trace outputs,” and “isolate path.” Highlighting
     only directly connected edges is insufficient for understanding long
     computation paths. 
     6) Make scope boundaries informative. Replace generic “Scope input/
     output” labels with the external module, tensor name, shape, and
     destination/source path.
     7) — Make ports interactive. Clicking a port should select its tensor
     route and show producer, consumers, dtype, shape, alias/view status,
     mutation history, and required/optional status.
    8) Keep virtualized routes understandable. Edges currently disappear
     unless both nodes are rendered. Use viewport-edge continuation markers such
     as “to 4 off-screen consumers.”
     9)Expose the generated block model. Add an architectural “Blocks” view
     for attention, MLP, embedding, normalization, and transformer blocks.
     blocks_ref data is produced but not used by the current UI
     10)Add a structural summary panel. Before graph exploration, show
     hierarchy depth, module count, repeated layers, parameter distribution,
     operation count, tensor-shape flow, inputs, and outputs
     ----------------------------------------

11) Add staged unique-structure tracing for models that are too large for one
    complete construction and forward pass.

    The builder MUST run a deterministic resource preflight before model
    construction. When the official configuration would exceed the configured
    CPU memory or execution budget, the builder MUST NOT allocate the complete
    model or perform one monolithic forward pass.

    Large-model tracing MUST instead:

    - Read the official configuration and constructor signatures before module
      allocation. This stage MUST NOT download or load checkpoint weights.
    - Detect every structurally unique layer or block variant. Detection MUST
      include module class, effective constructor arguments, relevant config
      fields, ordered child-module structure, parameter and buffer shape
      signatures, layer role/index, and config-controlled branches.
    - Detect heterogeneous layer schedules. A later MoE layer, sliding-window
      attention layer, cross-attention layer, expert variant, or other changed
      layer MUST NOT be treated as equivalent to an earlier dense or standard
      layer merely because their parent class or path pattern is similar.
    - Build a compact, shape-valid initialization configuration from the
      captured constructor parameters. Compact dimensions MUST preserve required
      divisibility and coupling constraints such as hidden-size/head count,
      grouped attention, expert routing, convolution groups, and residual
      boundary compatibility. The compact configuration MUST be derived from the
      official configuration through recorded, deterministic overrides; it MUST
      NOT replace or modify the stored official configuration.
    - Instantiate and execute one deterministic CPU forward for each unique
      layer or block variant rather than each repeated instance.
    - Fall back to operation-by-operation construction and execution when one
      complete layer still exceeds the resource budget.
    - Record which concrete module instances use each traced template and retain
      the original per-instance module paths, layer indices, constructor values,
      source references, and official configuration values.
    - Preserve representative boundary input/output contracts so repeated
      template instances can be connected without inventing a sequential route.
    - Distinguish operations observed in the representative forward from graph
      instances expanded from a traced template. Template-expanded instances and
      cross-instance routes MUST carry explicit provenance and MUST NOT be
      reported as independently observed runtime executions.
    - Store official dimensions separately from compact trace dimensions and
      display the difference in the UI.

    A full-model forward remains required for models that fit within the
    configured resource budget. Staged tracing is a resource-bounded fallback,
    not the default for small models.

12) Keep both the current compact trace configuration and the official Hugging
    Face configuration for every model version.

    The two configuration records MUST be clearly separated:

    - `official_config`: the exact downloaded `config.json` from the selected
      Hugging Face model repository at a pinned full commit SHA. It MUST be
      stored byte-for-byte and MUST NOT be rewritten into the trace schema.
    - `trace_config`: the compact, runnable configuration used by the current
      CPU tracing approach, including all derivations and overrides.

    The generated data and UI MUST include a field-by-field difference between
    the official and trace configurations. The UI MUST link to the official
    repository and the pinned `config.json` revision and MUST never imply that
    compact trace dimensions are the official checkpoint dimensions.

    Repository discovery and mapping MUST use this process:

    - Use browser-assisted research to find the repository maintained by the
      original model publisher or its official organization on Hugging Face.
    - Create a human-reviewable versioned mapping file for the initial 21-model
      release. Version 1 of this mapping MUST be sufficient to run the complete
      config-fetch, build, trace, validation, and static-site pipeline.
    - Record model version ID, Hugging Face repository ID, `config.json` path,
      full commit SHA, pinned browser URL, publisher, declared license metadata,
      mapping status, and review notes.
    - The build MUST consume the mapping file deterministically. It MUST NOT
      dynamically choose a different repository because search ranking or Hub
      contents changed.
    - The mapping is expected to be reviewed and corrected manually when
      necessary without changing generated-data contracts.
    - When an original publisher uses a native configuration schema that differs
      from the installed Transformers configuration class, keep the original
      config unchanged and use an explicit, versioned compatibility adapter.
      Adapter inputs, outputs, and every renamed or derived field MUST be
      recorded in `trace_config`; do not substitute a community conversion only
      to obtain matching field names.

    Config acquisition MUST be a separate network-enabled prefetch stage. The
    tracing and static-site stages MUST continue to run with network access
    disabled and use only the pinned local config copy.

    Security and download restrictions are mandatory:

    - Download only the mapped `config.json` file.
    - Do not download model weights, weight indexes, tokenizer files, processors,
      datasets, executable repository code, or arbitrary repository snapshots.
    - Do not enable or execute remote code. `trust_remote_code` MUST remain
      disabled.
    - Hash the downloaded config and record its pinned source URL and commit.
    - Preserve the agreed license metadata and attribution in the generated
      license records.
    - A missing, moved, unpinned, malformed, or architecture-incompatible config
      MUST mark that exact model's release record as partial or blocked and show
      a visible model-specific warning in the UI. It MUST NOT silently fall back
      to an unrelated repository or unrecorded configuration. Other valid models
      MAY continue through the release pipeline.
