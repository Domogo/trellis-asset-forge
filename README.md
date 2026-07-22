# Trellis Asset Forge

[![CI](https://github.com/Domogo/trellis-asset-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/Domogo/trellis-asset-forge/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Trellis Asset Forge is a local-first production utility for turning reference images into cataloged, reviewable, game-optimized 3D assets through multiple fal image-to-3D APIs.

It gives a game team the missing production layer around generation: asset manifests, multi-asset batches, cost ceilings, reproducible seeds, private local artifact storage, topology inspection, visual approval, LOD processing, and deterministic exports with provenance.

> [!IMPORTANT]
> The supported endpoints are image-conditioned. A prompt cannot force clean edge flow. The forge optimizes for game development through purpose-built reference images, model-aware geometry controls, measurable topology gates, human review, and `gltfpack` LODs. `brief` and `topology_notes` guide reference creation and review; they are deliberately not sent to fal as a fake prompt.

## What it does

```text
reference images → validated manifest → catalog-wide cost gate → fal queue
      → private local GLB → topology inspection → human approval
      → gltfpack optimization + LODs → game export + provenance
```

- Generates one asset or a complete catalog with TRELLIS.2, Meshy 6 Preview, Hunyuan3D V3, or Hunyuan 3D V3.1 Pro.
- Records reference hashes, endpoint, seed, parameters, price estimate, remote job, and local artifact.
- Keeps `FAL_KEY` server-side and never exposes it to the review browser.
- Requests no fal payload retention, uses short media lifetimes, and downloads results immediately.
- Measures triangles, vertices, components, degenerate faces, boundary edges, non-manifold edges, bounds, materials, textures, and watertightness.
- Blocks approval when hard topology or platform-budget gates fail.
- Builds profile-defined GLB LODs with `gltfpack`, preserving named nodes, materials, and glTF extras.
- Promotes only approved, processed candidates to a clean engine-neutral export tree.
- Emits a JSON sidecar with hashes, review notes, LOD metrics, scale, pivot, and collision intent.

## Install

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- A [fal API key](https://fal.ai/dashboard/keys)
- [`gltfpack`](https://github.com/zeux/meshoptimizer/tree/master/gltf) for optimization and LOD generation

```bash
git clone https://github.com/Domogo/trellis-asset-forge.git
cd trellis-asset-forge
uv sync
export FAL_KEY="your-key"
```

You can install `gltfpack` from meshoptimizer releases/builds or its npm package:

```bash
npm install -g gltfpack
```

All examples below use `uv run trellis-forge`; `uv run taf` is the shorter alias.

## Quick start

Create a workspace whose promoted assets will land in `res://generated` of a Godot project:

```bash
uv run trellis-forge init ~/projects/my-game-assets \
  --export-root ~/projects/my-game/generated
```

Copy [the example manifest](examples/assets.yaml), add your reference images, then catalog it:

```bash
uv run trellis-forge import ~/projects/my-game-assets/assets.yaml \
  --workspace ~/projects/my-game-assets
uv run trellis-forge assets --workspace ~/projects/my-game-assets
```

Generate one asset with a hard spend ceiling, or submit the whole catalog behind one aggregate ceiling:

```bash
uv run trellis-forge generate props.scrap-crate \
  --workspace ~/projects/my-game-assets --max-cost 2.00

uv run trellis-forge generate-all \
  --workspace ~/projects/my-game-assets --max-cost 10.00
```

`generate-all` is spend-idempotent: it skips every asset that already has a local
generation attempt. Use `generate ASSET_ID` explicitly when you intend to pay for
a retry or an additional candidate.

Poll until completed candidates have been downloaded locally:

```bash
uv run trellis-forge sync --workspace ~/projects/my-game-assets
uv run trellis-forge generations --workspace ~/projects/my-game-assets
```

Review candidates in the private loopback workspace:

```bash
uv run trellis-forge review --workspace ~/projects/my-game-assets
# open http://127.0.0.1:8765
```

The UI previews each GLB, runs the topology inspection, shows profile evidence, and records approval or rejection notes. The same workflow is available from the CLI:

```bash
uv run trellis-forge inspect GENERATION_ID --workspace ~/projects/my-game-assets
uv run trellis-forge approve GENERATION_ID \
  --workspace ~/projects/my-game-assets --notes "silhouette and UVs approved"
```

Process the approved candidate, then promote it to the game export root:

```bash
uv run trellis-forge process GENERATION_ID --workspace ~/projects/my-game-assets
uv run trellis-forge promote GENERATION_ID --workspace ~/projects/my-game-assets
```

For `props/scrap-crate.glb`, promotion produces:

```text
generated/
└── props/
    ├── scrap-crate.glb
    ├── scrap-crate.lod1.glb
    ├── scrap-crate.lod2.glb
    └── scrap-crate.asset-forge.json
```

## Manifest

```yaml
version: 1
project: scrapshift
assets:
  - id: props.scrap-crate
    name: Scrap Crate
    category: props
    brief: Chunky welded salvage crate with a readable silhouette.
    topology_notes: Keep broad bevels; reject floating shards and noisy underside geometry.
    profile: desktop-prop
    game:
      scale_meters: 1.2
      pivot: base-center
      collision: convex
    references:
      - path: references/scrap-crate-front.png
        view: front-three-quarter
      - path: references/scrap-crate-rear.png
        view: rear-three-quarter
    generation:
      model: fal-ai/hunyuan-3d/v3.1/pro/image-to-3d
      variants: 3
      seed: 4200
      # Optional when fal pricing changes:
      # unit_cost_usd: 0.525
    export: props/scrap-crate.glb
```

Reference paths resolve relative to the manifest. Each image is hashed during import. `generation.model` defaults to `fal-ai/trellis-2`, so existing manifests remain valid.

### Generation models

| `generation.model` | References | Model-aware request behavior | Built-in estimate per variant |
| --- | --- | --- | ---: |
| `fal-ai/trellis-2` | One or more | Selects the single or multi endpoint automatically; sends seed, resolution, texture size, decimation target, and remesh. | $0.25 / $0.30 / $0.35 at 512 / 1024 / 1536 |
| `fal-ai/meshy/v6-preview/image-to-3d` | Exactly one | Maps `decimation_target` to `target_polycount` and `remesh` to `should_remesh`. | $0.80 |
| `fal-ai/hunyuan3d-v3/image-to-3d` | Front plus optional back, left, and right | Uses Hunyuan's default normal textured generation settings. | $0.375, plus $0.15 for multi-view |
| `fal-ai/hunyuan-3d/v3.1/pro/image-to-3d` | Front plus optional back, left, right, top, bottom, front-left, and front-right | Uses Hunyuan's default normal textured generation settings. | $0.375, plus $0.15 for multi-view |

For both Hunyuan models, the first reference is the primary/front image. Name additional reference `view` values `back` or `rear`, `left`, and `right`. V3.1 Pro additionally accepts `top`, `bottom`, `front-left`, and `front-right`; three-quarter synonyms such as `rear-three-quarter` and `front-left-three-quarter` are also accepted. Unsupported or duplicate views fail manifest import before any paid request.

Hunyuan's `face_count`, PBR, and generation-type controls are left at provider defaults in this release. `resolution`, `texture_size`, `decimation_target`, `remesh`, and `seed` are not sent to Hunyuan. Meshy does not accept a seed, resolution, or texture-size input. The local catalog still assigns a seed to distinguish variants, but only TRELLIS.2 currently receives it for deterministic inference.

`brief` and `topology_notes` belong in the catalog and exported provenance. They are not transmitted to a provider as generation prompts.

## Game profiles

| Profile | Candidate geometry target | Local triangle gate | Texture | Materials | Components | LOD ratios |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `mobile-prop` | 10,000 | 20,000 | 1024 | 2 | 8 | 1.0 / 0.5 / 0.2 |
| `desktop-prop` | 25,000 | 50,000 | 2048 | 4 | 16 | 1.0 / 0.5 / 0.2 |
| `hero-static` | 50,000 | 100,000 | 4096 | 6 | 24 | 1.0 / 0.6 / 0.3 |

The current profiles target static props. Automatic approval is intentionally unavailable for deforming characters, authored modular seams, skeletal rigs, or exact semantic collision. Those need a DCC retopology/rigging pass.

`game.scale_meters`, `game.pivot`, and `game.collision` are portable import intent recorded in the sidecar. They do not destructively rewrite the generated mesh. An engine importer can use them to set scene scale, choose a base-centered pivot workflow, and generate convex or trimesh collision.

See [Game-ready assets](docs/game-ready-assets.md) and [Reference prompting](docs/reference-prompting.md) for the production contract.

## Storage and privacy

Each workspace contains:

```text
asset-forge.toml              # paths only; safe to commit if desired
.asset-forge/
├── catalog.sqlite3           # local generation/review history
└── artifacts/                # references are not copied; generated GLBs stay here
```

The review server always binds to `127.0.0.1`. It has no public-host option and never sends `FAL_KEY` to browser JavaScript. Generated models are served only by catalog generation ID.

fal is still a remote processor: submitted references leave your machine during inference. The client sets `X-Fal-Store-IO: 0`, requests a short object lifecycle, and uses data URIs so reference images do not need public hosting. Review fal's current terms before sending confidential or third-party material.

## API and MCP use

The stable automation surface is the `AssetForge` Python interface plus the CLI. A game tool, CI job, Codex task, or MCP server can call those without duplicating provider and catalog logic:

```python
from decimal import Decimal
from pathlib import Path

from trellis_asset_forge.fal import FalGenerator
from trellis_asset_forge.forge import AssetForge

forge = AssetForge.open(Path("~/projects/my-game-assets").expanduser())
jobs = forge.submit_all(
    generator=FalGenerator.from_environment(),
    max_cost_usd=Decimal("10.00"),
)
```

An MCP transport is intentionally not bundled in v0.1: MCP should be a thin adapter over this interface, not a second workflow implementation. The local review app is human-facing and has its OpenAPI endpoints disabled.

## Limitations

- Generative topology is suitable for measured static-mesh candidates, not guaranteed production topology.
- For TRELLIS.2, `decimation_target` is a target vertex count; for Meshy it becomes `target_polycount`. The local profile gate always measures actual output triangles.
- LOD simplification can damage thin parts, UVs, normals, or silhouettes, so the approved source and produced LODs still need visual QA.
- Collision intent is metadata. Exact gameplay collision remains engine/DCC work.
- Prices can change. Use `unit_cost_usd` in a manifest when the built-in estimate is stale and retain `--max-cost` as the hard gate.
- The review viewer loads Google's `<model-viewer>` module from a CDN; GLB files remain served from loopback.

## Development

```bash
uv sync --all-groups
uv run pytest --cov=trellis_asset_forge
uv run ruff check .
uv run mypy src
```

See [Architecture](docs/architecture.md), [CLI reference](docs/cli.md), [Contributing](CONTRIBUTING.md), and [Security](SECURITY.md).

## License

[MIT](LICENSE). The forge is open source; fal and its hosted models are separate services with their own terms and pricing.
