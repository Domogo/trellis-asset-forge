# Trellis Asset Forge

Trellis Asset Forge is a local-first production utility for turning reference images into cataloged, reviewable, game-optimized 3D assets with fal's TRELLIS.2 endpoints.

It is designed for teams that want reproducibility and topology gates around generative 3D workflows—not a folder full of anonymous GLB downloads.

> [!IMPORTANT]
> TRELLIS.2 is image-conditioned. It does not accept a text prompt. Game readiness comes from clean reference views, constrained generation settings, remeshing, measured topology budgets, LOD generation, validation, and human approval.

## Planned workflow

```text
reference images → manifest → cost gate → fal queue → local GLB
                 → topology review → optimize/LOD → approve → promote
```

The repository is being implemented in small, atomic commits. See [Architecture](docs/architecture.md) for the module design and [Game-ready assets](docs/game-ready-assets.md) for the quality contract.

## Principles

- Local catalog and artifact ownership.
- Exact provenance: references, hashes, endpoint, seed, parameters, cost, and review history.
- Explicit cost ceilings before remote generation.
- Privacy-aware fal requests with request-payload storage disabled and short media lifetimes.
- Human approval before an artifact reaches a game project.
- Engine-neutral exports; Godot, Unity, Unreal, and custom engines consume ordinary GLB files.
- Provider details stay behind one generation module so the catalog and review workflow remain reusable.

## Scope

Trellis Asset Forge targets static props, pickups, environment dressing, hard-surface concepts, and other assets that can be evaluated as textured meshes.

Generated meshes are not assumed to be animation-ready. Rigged characters, modular pieces with exact interfaces, and gameplay-critical collision meshes require additional authoring and should fail the approval gate when they do not meet project constraints.

## License

[MIT](LICENSE)

