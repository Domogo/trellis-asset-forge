# Security policy

Please report security issues privately through GitHub's security advisory feature instead of opening a public issue.

## Credentials

- Keep `FAL_KEY` in the environment or a local `.env` file.
- Never put fal credentials in manifests, the catalog, logs, URLs, screenshots, or browser code.
- The local web workspace binds to loopback by default and is not an authentication server.

## Reference privacy

fal is a remote processor. Inputs leave the local machine during inference. The utility disables fal request-payload retention and requests short media lifetimes, but users should still avoid submitting material they are not authorized to process.

