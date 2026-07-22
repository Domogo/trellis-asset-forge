# Example catalog

`assets.yaml` demonstrates one multi-view desktop prop and one single-view mobile pickup.

Create `examples/references/` and add your own PNG, JPEG, WebP, AVIF, or GIF files under the filenames in the manifest. The repository intentionally does not ship synthetic reference art that could be mistaken for production input.

From the repository root:

```bash
uv run trellis-forge init .demo --export-root exports
uv run trellis-forge import examples/assets.yaml --workspace .demo
uv run trellis-forge assets --workspace .demo
```

Import resolves references relative to `examples/assets.yaml`, not the current shell directory.
