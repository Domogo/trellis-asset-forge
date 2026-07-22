# CLI reference

Both `trellis-forge` and `taf` invoke the same CLI.

| Command | Purpose |
| --- | --- |
| `init DIRECTORY --export-root PATH` | Create a local workspace and SQLite catalog. |
| `import MANIFEST --workspace PATH` | Validate, hash, price, and catalog a YAML plan. |
| `assets --workspace PATH` | List assets and active budgets. |
| `generate ASSET_ID --max-cost USD` | Submit every configured variant for one asset. |
| `generate-all --max-cost USD` | Cost-gate and submit the complete catalog. |
| `sync` | Poll active fal jobs and download completed GLBs. |
| `generations [--asset ID]` | List durable candidate states without contacting fal. |
| `inspect GENERATION_ID` | Measure topology against the asset profile. |
| `approve GENERATION_ID [--notes TEXT]` | Approve a candidate only when hard gates pass. |
| `reject GENERATION_ID --notes TEXT` | Reject an inspected candidate with feedback. |
| `review [--port 8765]` | Start the loopback-only visual review workspace. |
| `process GENERATION_ID [--gltfpack PATH]` | Optimize an approved GLB and build profile LODs. |
| `promote GENERATION_ID` | Export the processed LOD set and provenance sidecar. |

Run `uv run trellis-forge COMMAND --help` for argument details.

## Cost behavior

`generate` checks the complete variant cost for one asset before submitting its first candidate. `generate-all` checks the complete catalog before submitting its first candidate. Provider failures after the check remain possible; every local generation is persisted before its remote request.

Built-in estimates are USD 0.25/0.30/0.35 for 512/1024/1536 at the time of the v0.1 implementation. fal pricing can change. Override `generation.unit_cost_usd` in the manifest and keep an explicit `--max-cost` ceiling.

## Job polling

`sync` is intentionally non-blocking. Run it periodically or from a scheduler. Completed results are downloaded immediately into `.asset-forge/artifacts`; subsequent calls leave downloaded candidates untouched.
