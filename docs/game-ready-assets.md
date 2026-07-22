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

## Initial profiles

| Profile | Candidate target | Texture | Intended use |
| --- | ---: | ---: | --- |
| `mobile-prop` | 20k triangles | 1024 | Small static props and pickups |
| `desktop-prop` | 50k triangles | 2048 | General environment and gameplay props |
| `hero-static` | 100k triangles | 2048–4096 | Large close-up non-deforming assets |

Profiles are gates, not guarantees. Silhouette, UV seams, material fidelity, non-manifold regions, disconnected components, and collision suitability still require review.

## LOD policy

The default derived ratios are 1.0, 0.5, and 0.2. Every LOD must be previewed because automatic simplification can collapse thin parts and high-contrast silhouette details.

## Animated assets

Animation-ready topology is outside automated approval. A candidate can be promoted as a visual blockout, but characters and deforming meshes require manual retopology and rigging.

