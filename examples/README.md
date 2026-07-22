# Example catalog

`assets.yaml` demonstrates a multi-view Hunyuan 3D V3.1 Pro desktop prop and a single-view Meshy 6 Preview mobile pickup.

Create `examples/references/` and add your own PNG, JPEG, WebP, AVIF, or GIF files under the filenames in the manifest. The repository intentionally does not ship synthetic reference art that could be mistaken for production input.

From the repository root:

```bash
uv run trellis-forge init .demo --export-root exports
uv run trellis-forge import examples/assets.yaml --workspace .demo
uv run trellis-forge assets --workspace .demo
```

Import resolves references relative to `examples/assets.yaml`, not the current shell directory.
