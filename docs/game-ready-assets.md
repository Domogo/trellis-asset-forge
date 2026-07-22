# Game-ready assets

“Generated” and “game-ready” are different states.

TRELLIS.2 infers a textured mesh from one or more images. It does not accept a text prompt and cannot be instructed to produce edge loops for deformation, exact modular dimensions, authored pivots, or semantic collision shapes. The forge therefore treats generation as candidate creation followed by measured processing and review.

## Reference contract

- One object per image.
- Transparent background whenever practical.
- Consistent scale, lighting, and material appearance across multi-view references.
- Front, rear, side, and three-quarter views supplied as separate files—not a contact sheet.
- No labels, swatches, accessories, shadows, or floor plane unless they are intended geometry.
- Moderate perspective and complete silhouettes.

The model cannot read `topology_notes`. Encode topology-friendly intent visually: use a clean silhouette, make thickness visible, avoid ambiguous overlaps, and omit decorative clutter that would become disconnected geometry.

## Initial profiles

| Profile | Fal vertex target | Triangle gate | Texture | Intended use |
| --- | ---: | ---: | ---: | --- |
| `mobile-prop` | 10k | 20k | 1024 | Small static props and pickups |
| `desktop-prop` | 25k | 50k | 2048 | General environment and gameplay props |
| `hero-static` | 50k | 100k | 4096 | Large close-up non-deforming assets |

fal's `decimation_target` is a vertex target, while the local gate counts actual triangles. Defaults request roughly one vertex per two allowed triangles; the measured output still decides whether the candidate passes. Profiles are gates, not guarantees. Silhouette, UV seams, material fidelity, non-manifold regions, disconnected components, and collision suitability still require review.

Hard failures are triangle/material/component budget overruns, degenerate faces, non-manifold edges, and invalid bounds. Open boundaries and missing embedded textures are warnings because legitimate assets such as leaves or cloth can be open and material workflows differ.

## LOD policy

The default derived ratios are 1.0, 0.5, and 0.2 (`hero-static` uses 1.0, 0.6, and 0.3). `gltfpack` optimizes every output and requests the declared simplification ratio. Every LOD must be previewed because automatic simplification can collapse thin parts and high-contrast silhouette details.

## Scale, pivot, and collision

The manifest records import intent instead of rewriting a textured GLB through a lossy generic transform:

- `scale_meters` documents the target size for an engine importer.
- `pivot` can be `source`, `center`, or `base-center`.
- `collision` can be `none`, `convex`, or `trimesh`.

The promotion sidecar carries this policy beside the GLB. Engine-specific import adapters can apply it deterministically; exact authored collision and socket placement remain manual responsibilities.

## Animated assets

Animation-ready topology is outside automated approval. A candidate can be promoted as a visual blockout, but characters and deforming meshes require manual retopology and rigging.
