# Reference prompting for game assets

TRELLIS.2 does not accept text. These prompts are for producing or commissioning the **reference images** that TRELLIS.2 will receive.

## Base reference prompt

```text
Single isolated [ASSET] designed as a production game prop, [STYLE AND MATERIALS].
Complete readable silhouette, physically plausible thickness, broad intentional bevels,
large coherent forms, limited small surface noise, no floating pieces, no paper-thin parts,
no intersecting geometry, no hidden accessories. Centered [VIEW] reference, moderate
orthographic-like perspective, entire object visible, neutral even studio lighting,
transparent or plain neutral background, no floor, no cast shadow, no text, no labels,
no measurements, no turntable sheet, no other objects.
```

Use `[VIEW]` values such as `front three-quarter`, `rear three-quarter`, `left side`, or `top`. Generate each view as a separate image. Keep shape, scale, colors, materials, and lighting consistent.

## Negative direction

```text
Avoid dramatic perspective, depth of field, motion blur, cropped silhouette, contact sheet,
exploded view, environment, character holding the object, wispy cables, loose debris,
micro-greebles, transparent supports, decals outside the silhouette, and baked shadows.
```

## Why this is topology-oriented

Image-to-3D topology follows visible form, not textual edge-loop instructions. Large coherent volumes and explicit thickness give the model less ambiguous geometry to infer. Thin wires, overlapping silhouettes, loose debris, and baked shadows commonly become floating components or noisy surfaces.

Put asset-specific review criteria in the manifest's `topology_notes`. The forge stores those notes in the catalog and promotion sidecar so a reviewer can reject output that violates the intended form. It never sends the notes as a nonexistent TRELLIS.2 prompt.

## Multi-view checklist

- Use separate image files rather than a collage.
- Show the same object state and material treatment in every view.
- Include at least front and rear three-quarter views for asymmetrical props.
- Keep every appendage visible in at least one view.
- Prefer transparent backgrounds, otherwise use the same flat background.
- Remove captions, arrows, UI chrome, color swatches, and rulers.
- Do not submit concept sheets containing alternative designs.
