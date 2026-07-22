# Architecture

Trellis Asset Forge separates project policy from remote generation and file processing. The external interfaces remain small while provenance, persistence, privacy headers, retries, and state transitions stay inside their owning modules.

## Modules

### Workspace

Locates configuration, the SQLite catalog, private artifacts, and the project export root. All file paths are resolved relative to an explicit workspace directory; the process working directory is never treated as implicit authority for destructive operations.

### Manifest

Loads and validates a versioned YAML asset plan. A manifest describes intent: references, target platform profile, variant count, generation parameters, and export path. It never contains provider credentials.

### Catalog

Owns durable asset, generation, review, and promotion state. Callers use catalog operations rather than writing SQL. State transitions are validated so rejected or unreviewed artifacts cannot be promoted accidentally.

### Generation

Accepts a validated generation request, enforces its cost ceiling, submits it through a generator adapter, and records the remote job before returning. The fal adapter owns authentication, data-URI encoding, retention headers, queue polling, result parsing, and immediate downloads.

### Mesh quality

Inspects downloaded GLB files and produces a report for the selected game profile: triangle and vertex counts, scene bounds, materials, textures, mesh components, watertightness signals, and file size. It reports evidence; it does not relabel a poor mesh as game-ready.

### Processing

Optimizes approved candidates and derives LODs through `gltfpack`. Named nodes, named materials, and glTF extras are preserved. Processing is explicit because simplification can damage silhouettes, UVs, or modular seams.

### Promotion

Atomically copies an approved processed LOD set and a provenance sidecar to a configured export root. Export paths must remain beneath that root. The sidecar carries portable scale, pivot, and collision intent without pretending those policies were baked into the mesh.

### Review workspace

Provides a loopback-only FastAPI application for previewing local GLBs, comparing reports, and recording approval decisions. It does not expose provider keys to the browser or offer a public bind address.

## Generation state

```text
planned → submitted → running → downloaded → inspected
                                      ├──→ rejected
                                      └──→ approved → processed → promoted
```

Remote failure and local validation failure are recorded separately. Every planned candidate is durable before remote submission, so a provider failure cannot erase the attempted parameters. A failed quality gate requires a new candidate or explicit profile change.

## Engine neutrality

Profiles describe budgets and processing policy, not engine import metadata. Promotion emits standard GLB plus JSON provenance. Engine-specific import configuration can be added later as an adapter without changing manifests or the catalog.
