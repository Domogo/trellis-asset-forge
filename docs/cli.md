# CLI reference

Both `trellis-forge` and `taf` invoke the same CLI.

| Command | Purpose |
| --- | --- |
| `init DIRECTORY --export-root PATH` | Create a local workspace and SQLite catalog. |
| `import MANIFEST --workspace PATH` | Validate, hash, price, and catalog a YAML plan. |
| `assets --workspace PATH` | List assets and active budgets. |
| `generate ASSET_ID --max-cost USD` | Submit every configured variant for one asset. |
| `generate-all --max-cost USD` | Cost-gate and submit catalog assets that have never been attempted. |
| `audio OUTPUT --prompt TEXT [--model ENDPOINT]` | Cost-gate, generate, wait for, and download one music or SFX file. |
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

`generate` checks the complete variant cost for one asset before submitting its first candidate. `generate-all` checks the never-attempted portion of the catalog before submitting its first candidate, so rerunning it cannot silently duplicate prior spend. Retry a failed or rejected asset explicitly with `generate ASSET_ID`. Provider failures after the check remain possible; every local generation is persisted before its remote request.

Built-in per-variant estimates are USD 0.25/0.30/0.35 for TRELLIS.2 at 512/1024/1536, USD 0.80 for Meshy 6 Preview, and USD 0.375 for either Hunyuan model plus USD 0.15 for multi-view input. fal pricing can change. Override `generation.unit_cost_usd` in the manifest and keep an explicit `--max-cost` ceiling.

`audio` checks one request before reading `FAL_KEY` or contacting fal. Its built-in estimates follow each provider's billing unit: fixed per output for Stable Audio, started minutes for ElevenLabs music, seconds for ElevenLabs SFX, and output minutes for CassetteAI. Audio prices can change, so keep `--max-cost` explicit.

## Audio generation

`audio` supports these full endpoint identifiers:

```text
fal-ai/stable-audio-3/medium/text-to-audio
fal-ai/elevenlabs/music
fal-ai/elevenlabs/sound-effects/v2
fal-ai/stable-audio-3/small/sfx/text-to-audio
cassetteai/music-generator
```

The default is Stable Audio 3 Medium. Stable Audio accepts `--seed`, `--negative-prompt`, and simple container names through `--format`. ElevenLabs music accepts `--instrumental` or `--allow-vocals`; ElevenLabs SFX accepts `--loop` and `--prompt-influence`. CassetteAI always produces WAV. Run `uv run taf audio --help` for every option.

The destination extension is validated against the requested provider format before submission, and an existing destination is never replaced. The command polls until completion or `--timeout`, downloads through HTTPS from approved fal media storage, and does not send the fal authorization header to that storage host.

## Job polling

`sync` is intentionally non-blocking. Run it periodically or from a scheduler. Completed results are downloaded immediately into `.asset-forge/artifacts`; subsequent calls leave downloaded candidates untouched.
