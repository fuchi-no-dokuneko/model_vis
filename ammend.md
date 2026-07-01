# Amendment: Source, Hierarchy, Topology, Ports, URI, and Runtime Initialization

## 1. Purpose and scope

This amendment adds mandatory requirements for source-code browsing, module
navigation, graph topology, tensor routing, application URIs, layer grouping,
and runtime parameter capture.

The output remains a static site. All model construction, tracing, source
collection, and metadata generation MUST happen during the build. The browser
MUST NOT execute Python, load models, download weights, or require a runtime
backend.

These requirements apply to every successfully built model version. Existing
generated graph, trace, source, block, and config schemas MUST be versioned or
extended as necessary. Existing model assets MUST be rebuilt when they do not
contain the required information.

## 2. Local IDE-style source-code viewer

The application MUST display the actual source code directly inside the Source
panel. A file/line reference without readable source text is not sufficient.

The build MUST:

1. Resolve the exact installed source file used by the traced model.
2. Copy the required source file into local generated static assets after the
   model build.
3. Preserve the original relative file path and line numbers.
4. Record package name, installed package version, source hash, license,
   official repository, and pinned repository tag or commit when available.
5. Generate an official repository URL for the same file and selected line
   range. The URL MUST point to a pinned tag or commit when one can be resolved.
6. Deduplicate identical source files by content hash.
7. Package all required source assets into `model_code/` and the final static
   `build/` output.

The Source panel MUST behave like a read-only IDE editor and provide:

- A source-file hierarchy.
- Syntax-highlighted source text.
- Stable line numbers.
- Vertical and horizontal scrolling.
- Highlighting of the selected and executed lines.
- Selection of a line to focus associated graph operations.
- Selection of an operation to focus its source line.
- A copy action for the selected source or visible source file.
- An external link to the corresponding file and line range in the official
  repository.

Source text MUST be escaped and displayed as text. It MUST never be evaluated
or inserted as executable HTML.

Copyright and redistribution information MUST be documented in `README.md`,
the third-party notices, and the generated license manifest. A README notice
alone is not the complete license record. The build MUST preserve all notices
required by the source package license. If required source cannot be legally
redistributed, the release build MUST report that model/source as a blocking
license failure instead of silently showing an empty source panel.

## 3. Module Hierarchy window

The application MUST include a Module Hierarchy tree similar to a file explorer.
This tree represents the instantiated PyTorch module hierarchy, not the source
file hierarchy and not a heuristic flat block list.

The hierarchy MUST be generated from the real model instance and runtime module
paths. It MUST preserve:

- Parent and child module relationships.
- Qualified module names.
- Module classes.
- Repeated layer indices.
- Runtime call instances when one module is called more than once.
- Links to graph nodes, source files, source symbols, and captured parameters.

The hierarchy UI MUST support expand, collapse, scrolling, keyboard selection,
search, and selection by qualified module path. Selecting an item MUST focus the
correct graph scope and source symbol. Selecting a graph node MUST reveal and
select the corresponding hierarchy item.

The Module Hierarchy and Source File Hierarchy MUST remain separate views, even
when they are synchronized to the same selection.

## 4. Complete topology in every computational scope

Every computational scope, including model version, repeated layer, block,
module, and operation scope, MUST be projected from one canonical runtime graph.
No scope may replace known topology with a synthetic sequential chain.

Category and family views may remain catalog/navigation views because they do
not represent one executed forward graph. From model-version scope downward,
the graph MUST preserve all observed runtime topology.

The canonical graph MUST capture:

- Parallel branches such as query, key, and value projections.
- Residual and skip connections.
- Fan-out from one tensor to multiple consumers.
- Fan-in from multiple tensors to one operation.
- Module calls, Python tensor functions, tensor methods, and ATen operations
  wherever technically observable.
- Tuple, list, dictionary, named-tuple, and model-output boundaries.
- Tensor views, aliases, copies, and in-place mutations.
- Producer-consumer relationships for every resolved tensor route.
- Module ownership, runtime call stack, source symbol, and source line.

### 4.1 Trace mode A: exact lineage trace

The normal build MUST track stable runtime tensor IDs, Python object identity,
storage identity, storage offsets, shapes, strides, view/base relationships,
mutation version where available, and producer/output to consumer/input ports.

Module hooks alone are not sufficient. The trace MAY combine module call hooks,
Torchview, Python dispatch or operator interception, and source-line tracing.
All data sources MUST be merged into the canonical graph with explicit evidence
and confidence.

Pass-through behavior MUST first be determined from identity and lineage. The
implementation MUST NOT rely only on `input == output`, because value equality
does not prove a data-flow route.

### 4.2 Trace mode B: deep recovery and brute-force search

When exact identity, storage/view lineage, or producer-consumer tracking cannot
resolve a route, the builder MUST be able to run a deeper recovery trace during
the deterministic CPU mock run.

Deep recovery MAY use targeted hooks, targeted re-execution, operator-level
capture, temporary tensor fingerprints, controlled probes, call ordering,
shape/dtype constraints, and bounded candidate search. Temporary tensor values
or fingerprints MUST NOT be shipped in static assets.

Brute-force recovery MUST be bounded and deterministic. A value match alone
MUST NOT be reported as an exact edge. Every recovered edge MUST carry one of:

- `exact`: proven by producer-consumer identity or operator capture.
- `lineage`: proven by storage, view, alias, or mutation lineage.
- `inferred`: selected by deterministic recovery with supporting evidence.
- `ambiguous`: multiple candidates remain.
- `unresolved`: no defensible route was found.

The UI MUST distinguish inferred, ambiguous, and unresolved routes. It MUST NOT
invent a sequential edge to make an incomplete graph look connected.

The two trace modes are build-time tracing modes. The generated UI MAY also
offer grouped Module view and detailed Operation view, but both views MUST use
the same canonical topology.

## 5. Application URI and address field

The first application row MUST contain an address text field. A user can type or
paste an application URI and navigate directly to the requested model scope.

The application MUST define a stable logical URI syntax capable of identifying:

- Model version.
- Module or repeated layer.
- Runtime call instance.
- Operation.
- Source file and line.
- Current graph detail mode.

The address field MUST accept both the logical application URI and the
browser-compatible static URL form. A recommended representation is:

```text
modelvis:/version/data2vec-3/module/encoder.layer.0.attention.output
https://host/#/version/data2vec-3/module/encoder.layer.0.attention.output
```

The static browser URL MUST support refresh, bookmarks, copy/paste, browser back,
and browser forward without a server-side routing dependency. The field MUST
only navigate valid internal application locations. Official source repository
links are separate external links and MUST open explicitly as external targets.

## 6. Repeated-layer detection and color grouping

A layer is defined as a concrete repeated instance of an equivalent class
structure within the model hierarchy. Examples include encoder layers, decoder
layers, repeated residual blocks, stages, and repeated expert blocks.

Repeated-layer detection MUST use a structural signature that includes at least:

- Module class and ordered child-class tree.
- Relevant parameter and buffer shapes.
- Observed operation topology.
- Observed input and output shape signatures.

Each concrete repeated layer instance MUST form a visible graph group. It MUST
have a deterministic color shared by its Module Hierarchy item, graph boundary,
and contained graph nodes. Color MUST be supplemented with a layer name and
index because color alone is not sufficient for accessibility or large layer
counts.

Nested leaf modules such as `Linear`, `Dropout`, and normalization modules remain
inside their nearest repeated-layer group unless they are explicitly selected.

## 7. Named input/output ports, shapes, and routes

Every graph node at every computational scope MUST expose all observed inputs
and outputs. A node box MUST use three stable regions:

1. The upper region is divided into N input-port columns for N inputs.
2. The middle region contains the module/function/operation identity.
3. The lower region is divided into N output-port columns for N outputs.

Each input and output port MUST record and display, when available:

- Variable or argument name.
- Positional index or keyword name.
- Tensor ID.
- Shape.
- Dtype.
- Device.
- Optional or required status.
- Container path such as `outputs.attentions[0]`.
- Alias/view/in-place status.

Input names MUST be derived by binding captured positional and keyword arguments
to the actual runtime call signature. Dictionary and model-output keys MUST be
preserved. Unnamed tuple/list outputs MUST use stable fallback names such as
`output[0]`.

Every graph route MUST connect one explicit source output port to one explicit
target input port. Edge records MUST include source node, source port, target
node, target port, tensor ID, shape, and trace confidence. One output port may
route to multiple consumers. Inputs originating outside the visible scope and
outputs leaving the visible scope MUST be represented by explicit boundary
ports or graph Input/Output nodes.

For a collapsed module or repeated layer, ports MUST represent tensors crossing
that scope boundary. Expanding the node MUST preserve those boundary routes and
reveal their internal producer-consumer paths.

Node dimensions MUST remain stable while port counts change. Nodes with many
ports MUST provide an expandable or scrollable port region without hiding route
identity or merging unrelated tensors.

## 8. Runtime constructor and call parameter capture

The build MUST capture the effective runtime values used to initialize the model
and every instantiated `nn.Module` during the deterministic CPU mock-build run.
Although module construction happens before the forward call, constructor
capture and forward tracing are one build session and one trace record.

For each model and module constructor, capture:

- Constructor class and source reference.
- Declared constructor signature.
- Positional and keyword arguments actually passed.
- Default values that became effective.
- Config-field origin when an argument was derived from config.
- Sanitized effective runtime value.
- Qualified module path assigned after construction.

For functions and operations, capture runtime call arguments rather than calling
them initialization parameters. Capture non-tensor scalar, enum, boolean,
string, shape, dimension, axis, stride, padding, and mode values when relevant.
Tensor arguments MUST store metadata and tensor IDs, not tensor contents.

Large objects and config objects MUST be represented by normalized values or
references to the generated config asset. Secrets, environment values, local
absolute paths, tensor contents, model weights, buffers, and state dictionaries
MUST NOT be serialized.

The inspector MUST expose separate sections for:

- Constructor parameters for models and modules.
- Runtime call parameters for a selected call instance or operation.
- Tensor parameter metadata such as name, shape, dtype, and trainability.
- Config values and the mapping from config fields to effective constructor
  arguments where known.

Repeated calls to the same module MUST retain one module definition and separate
runtime call records. Each call record MUST preserve its own arguments, ports,
topology, shapes, and source-line execution.

## 9. Required generated-data changes

The generated data model MUST support at least:

- A canonical graph with node, call-instance, port, tensor, and edge IDs.
- Module parent/child relationships and repeated-layer group IDs.
- Source file assets containing source text and official repository URLs.
- Constructor records and runtime call-argument records.
- Trace evidence and confidence for every edge.
- Boundary ports for every collapsible graph scope.
- URI-addressable IDs that remain stable for identical build inputs.

The graph renderer MUST NOT infer missing topology from array order. Sequential
ordering may be displayed only when the trace proves a sequential dependency.

## 10. Acceptance criteria

The amendment is complete only when all of the following pass:

1. The Source panel displays locally packaged, readable source code for a
   selected Data2Vec module and links to the matching official repository file.
2. The Module Hierarchy navigates from `data2vec-3` to
   `encoder.layer.0.attention.output` and synchronizes graph and source selection.
3. Query, key, and value branches render in parallel when observed in the trace.
4. Residual and skip tensors visibly route from their producer output ports to
   every consumer input port.
5. No block or operation scope replaces known topology with sequential edges.
6. A multi-input module displays one named, shaped port per input.
7. A multi-output operation displays one named or indexed, shaped port per
   output, and every consumed output has a visible route.
8. Collapsing and expanding a repeated layer preserves external routes.
9. Repeated layer instances have deterministic synchronized hierarchy/graph
   colors and visible labels.
10. The address field can navigate directly to a model, module, operation, and
    source line and survives browser refresh.
11. The inspector shows actual sanitized constructor values captured during the
    CPU mock-build session and actual runtime call values for operations.
12. Exact tracing automatically invokes bounded deep recovery when required,
    and unresolved or ambiguous routes remain explicitly marked.
13. The final static build requires no Python runtime, backend, database,
    external model API, or model-weight download.
14. Source redistribution notices and generated license records pass the
    project's license gate.
