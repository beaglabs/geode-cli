# geode-cli

`geode-cli` is a Python command-line client for working with Geode vaults, a cloud-native workflow for versioning scientific and geospatial datasets.

The CLI is built around a familiar local/remote model:

- a local directory acts as your workspace
- `.geode/config.yaml` stores the remote, vault id, and tracked head commit
- `push` uploads local changes to a remote vault
- `clone` materializes a vault into a local directory
- `sync` updates a local workspace to the remote vault head
- `status` and `diff` help you understand divergence between local, tracked base, and remote

It behaves much more like "Git for data directories" than a generic file uploader. The code is especially focused on geospatial formats, including automatic normalization of several source formats to Zarr or Arrow before upload.

## What The CLI Does

Geode tracks a workspace as a set of file entries with hashes and metadata.

For regular files, the CLI hashes and uploads the file contents directly.

For supported scientific and geospatial formats, the CLI also produces normalized outputs before upload:

- raster and multidimensional formats are normalized to Zarr
- vector formats are normalized to Arrow IPC streams
- original source files are still included alongside normalized outputs

This gives the server enough structure to deduplicate uploads, understand file types, and build commit history around dataset contents.

## Repository Layout

```text
.
├── geode                  # thin launcher script
├── main.py                # argparse entrypoint
├── commands/              # CLI subcommands
│   ├── clone.py
│   ├── diff.py
│   ├── init.py
│   ├── push.py
│   ├── status.py
│   ├── sync.py
│   └── vault.py
└── lib/
    ├── archive.py         # tar extraction and safe replacement helpers
    ├── cache.py           # local conversion cache under .geode/cache/
    ├── config.py          # .geode/config.yaml read/write helpers
    ├── hasher.py          # BLAKE3 hashing
    ├── ignore.py          # .geodeignore parsing
    ├── pusher.py          # remote HTTP API client
    ├── workspace.py       # workspace scanning and diff/planning logic
    └── converters/        # format-specific converters
```

## Workspace Model

Each initialized or cloned workspace stores Geode metadata under `.geode/`.

Expected files and directories:

- `.geode/config.yaml`: workspace configuration
- `.geode/cache/`: cached conversion outputs reused across pushes
- `.geodeignore`: optional ignore file in gitignore-compatible syntax

The config file may contain:

```yaml
remote: https://geode.example.com
vault_id: 00000000-0000-0000-0000-000000000000
head_commit_id: 11111111111111111111111111111111
```

Field meanings:

- `remote`: base server URL used for API requests
- `vault_id`: vault UUID to read from and write to
- `head_commit_id`: the commit the local directory is currently based on

That tracked head commit is what makes `status`, `diff`, `push`, and `sync` work like version-control operations instead of blind upload/download commands.

## Command Reference

The CLI defines these top-level commands:

- `geode init`
- `geode clone`
- `geode push`
- `geode status`
- `geode diff`
- `geode sync`
- `geode vault ...`

### `geode init`

Initialize a directory as a Geode workspace.

Arguments and flags:

- `directory`: target directory, defaults to `.`
- `--remote`: base remote URL, or a full vault URL
- `--vault-id`: explicit vault UUID
- `--token`: auth token, otherwise `GEODE_TOKEN`
- `--force`: overwrite existing config values when re-initializing
- `--no-ignorefile`: skip creation of a starter `.geodeignore`

Behavior:

- creates `.geode/config.yaml`
- optionally creates a starter `.geodeignore`
- if `--remote` is a full vault URL like `https://host/owner/vault`, the CLI attempts to resolve the vault id automatically
- if `--force` is used, the tracked `head_commit_id` is cleared before new remote settings are written

Example:

```bash
geode init . --remote https://geode.example.com --vault-id <vault-uuid>
```

### `geode clone`

Clone a remote vault into a local directory.

Accepted source formats:

- full URL: `https://geode.example.com/owner/vault-slug`
- shorthand: `owner/vault-slug`

Arguments and flags:

- `source`: vault URL or `owner/vault`
- `directory`: destination directory, defaults to the vault slug
- `--remote`: required when using `owner/vault` shorthand unless a workspace remote already exists
- `--token`: auth token, otherwise `GEODE_TOKEN`
- `--force`: allow cloning into a non-empty destination directory

Behavior:

- resolves the vault id from owner/slug
- downloads the remote archive
- extracts it into the destination directory
- writes `.geode/config.yaml` with `remote`, `vault_id`, and `head_commit_id`

Examples:

```bash
geode clone https://geode.example.com/jane/wildfire-forecast
geode clone jane/wildfire-forecast --remote https://geode.example.com
geode clone jane/wildfire-forecast data/wildfire --remote https://geode.example.com
```

### `geode push`

Push the current directory to the configured remote vault.

Flags:

- `-m, --message`: commit message, defaults to `Push data`
- `--dry-run`: preview what would be pushed
- `--token`: auth token, otherwise `GEODE_TOKEN`

High-level push flow implemented in `commands/push.py`:

1. scan the workspace while respecting `.geodeignore`
2. skip `.geode/` internals
3. convert supported file types to Zarr or Arrow
4. cache normalized outputs under `.geode/cache/`
5. hash source and normalized artifacts with BLAKE3
6. call `POST /api/vaults/{vault_id}/push/start`
7. receive dedup information and a presigned upload URL
8. tar only the required content bytes
9. upload the tar to object storage
10. call `POST /api/vaults/{vault_id}/push/{run_id}/complete`
11. poll run status until success, failure, cancellation, or timeout
12. update `head_commit_id` when the push completes successfully

Important push semantics:

- if the local workspace has no tracked `head_commit_id` but the remote vault already has history, push is rejected
- if the remote has advanced since the tracked base, the push may be rejected with a conflict-like `409` response
- `--dry-run` predicts whether the push would be `fast-forward`, `auto-merge`, or `conflict` when base metadata is available

Examples:

```bash
geode push -m "Refresh June land cover tiles"
geode push --dry-run
GEODE_TOKEN=... geode push -m "Publish latest model output"
```

### `geode status`

Show the relationship between:

- the tracked base commit in `.geode/config.yaml`
- the current local workspace contents
- the remote vault head

Flags:

- `--token`: auth token, otherwise `GEODE_TOKEN`

Output includes:

- tracked head
- remote head
- local changes relative to base
- remote changes relative to base
- predicted push outcome: `fast-forward`, `auto-merge`, or `conflict`
- predicted sync outcome: clean apply or conflict

This is the best command to run before either `push` or `sync`.

Example:

```bash
geode status
```

### `geode diff`

Show summary diffs against the tracked base commit.

Modes:

- `--local`: local workspace vs tracked base
- `--remote`: remote head vs tracked base
- `--staged-push`: current local workspace vs tracked base

Flags:

- `--token`: auth token, otherwise `GEODE_TOKEN`

Output is a path-only summary grouped into:

- added
- modified
- deleted

Examples:

```bash
geode diff --local
geode diff --remote
geode diff --staged-push
```

### `geode sync`

Update the current directory to the remote vault head.

Flags:

- `--token`: auth token, otherwise `GEODE_TOKEN`
- `--dry-run`: preview additions, updates, deletions, and conflicts
- `--discard-local`: discard local changes and replace tracked contents completely

Behavior:

- computes a three-way sync plan from base, local, and remote metadata
- rejects non-forced syncs when local and remote changed the same paths
- downloads a remote archive and applies only the non-conflicting remote changes
- when `--discard-local` is used, replaces the working directory wholesale while preserving `.geode` and `.git`
- updates `head_commit_id` after a successful sync

Examples:

```bash
geode sync --dry-run
geode sync
geode sync --discard-local
```

### `geode vault`

Vault-related configuration commands.

Subcommands currently implemented:

- `geode vault set-url <url> [--vault-id <id>]`
- `geode vault create`

`set-url` behavior:

- writes the remote URL into workspace config
- clears the tracked `head_commit_id`
- stores a new vault id when `--vault-id` is passed
- if `<url>` is a full vault URL like `https://host/owner/vault`, the CLI attempts to resolve the vault id automatically

`create` behavior:

- currently a stub that prints `implementation pending`

Example:

```bash
geode vault set-url https://geode.example.com --vault-id <vault-uuid>
geode vault set-url https://geode.example.com/jane/wildfire-forecast
```

## Supported File Conversion

The converter dispatch table lives in `lib/converters/__init__.py`.

### Converted To Zarr

- `.tif`, `.tiff` via `rasterio` + `xarray`
- `.nc` via `xarray`
- `.grib`, `.grb` via `xarray` with `cfgrib`
- `.las`, `.laz` via `laspy` + `xarray`

### Converted To Arrow IPC

- `.shp`
- `.geojson`
- `.parquet`

These vector conversions use `geopandas` and `pyarrow`.

### Passed Through As Blobs

Anything not matched by the converter table is treated as a generic blob and uploaded without normalization.

### Type Detection Notes

The CLI also recognizes existing Zarr-like paths as `zarr` outputs when a path contains markers such as:

- `.zarray`
- `.zgroup`
- `zarr.json`
- `.zarr/`

## Ignore Rules

Ignore handling is implemented in `lib/ignore.py`.

The `.geodeignore` file uses a gitignore-like syntax with support for:

- comments
- blank lines
- glob patterns
- directory suffixes like `build/`
- negation with `!pattern`

The default ignore file created by `geode init` includes common junk and workspace-local content such as:

- `__pycache__/`
- `*.pyc`
- `.DS_Store`
- `node_modules/`
- `.geode/`
- `venv/`
- `.env`
- `dist/`
- `build/`
- `.git/`
- `*.log`

## Remote API Surface

All remote calls are constructed as `<remote>/api/...` in `lib/pusher.py`.

Endpoints used by the CLI:

- `GET /api/vaults/{vault_id}`
- `GET /api/vaults/by-path/{owner}/{vault_slug}`
- `GET /api/vaults/{vault_id}/tree-metadata`
- `GET /api/vaults/{vault_id}/archive`
- `POST /api/vaults/{vault_id}/push/start`
- `POST /api/vaults/{vault_id}/push/{run_id}/complete`
- `GET /api/vaults/{vault_id}/push/{run_id}`

Authentication is optional at the HTTP layer and is sent as:

```text
Authorization: Bearer <token>
```

The CLI looks for a token in this order:

1. `--token`
2. `GEODE_TOKEN`

## Typical Workflows

### Start A New Workspace

```bash
geode init . --remote https://geode.example.com --vault-id <vault-uuid>
geode status
geode push -m "Initial dataset import"
```

### Clone And Update An Existing Vault

```bash
geode clone jane/climate-run-2026 --remote https://geode.example.com
cd climate-run-2026
geode status
geode sync
```

### Inspect Divergence Before A Push

```bash
geode status
geode diff --local
geode diff --remote
geode push --dry-run
```

### Discard Local Changes And Reset To Remote

```bash
geode sync --discard-local
```

Use this carefully. In forced sync mode, the CLI removes everything in the working directory except `.geode` and `.git` before extracting the remote archive.

## Development Notes

### Runtime Dependencies

The repository does not currently include packaging metadata such as `pyproject.toml`, `setup.py`, or a pinned `requirements.txt`, so dependencies have to be inferred from imports.

Core dependencies:

- `httpx`
- `PyYAML`
- `blake3`

Conversion-related dependencies loaded lazily when needed:

- `rasterio`
- `xarray`
- `numpy`
- `geopandas`
- `pyarrow`
- `laspy`
- `cfgrib`

If you are setting up a development environment manually, you will also need Python 3 and whatever native libraries those geospatial packages require on your platform.

### Current Repository State

The command implementation is present in this repository, but the project is not yet packaged as a standard installable Python CLI.

Two practical consequences of the current tree:

- there is no install metadata for `pip install -e .`
- the repo-local `geode` launcher currently imports `cli.main`, which does not exist in this checkout

So this repository currently documents the intended CLI and contains the implementation logic, but it still needs packaging and entrypoint cleanup before it works as a polished installable tool.

## Limitations And Caveats

- `geode vault create` is not implemented yet
- `diff` is a summary-by-path command, not a content diff viewer
- `push` waits up to 5 minutes for server-side completion before giving up polling
- `sync` detects conflicts at the path level, not by line or structured merge rules
- conversion cache invalidation is versioned only by source path, source hash, and a fixed converter version string
- extracting remote archives rejects symlinks and unsafe archive paths for safety

## License

MIT. See `LICENSE`.
