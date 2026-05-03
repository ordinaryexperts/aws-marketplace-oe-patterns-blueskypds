# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AWS Marketplace pattern that deploys a production-ready [Bluesky PDS](https://github.com/bluesky-social/pds) (Personal Data Server) on AWS. Ships as a CloudFormation template plus a custom AMI:

1. **Custom AMI** built with Packer (Ubuntu 24.04 **arm64 / Graviton**, with Docker, nginx, PHP-FPM, and the PDS Docker image pre-pulled).
2. **CDK Infrastructure** (Python) that synthesizes to CloudFormation.
3. **Marketplace product** (id `prod-ufpvcz32f2pdq`) — `prod-` style, not the older UUID format.

The deployed stack is intentionally small: a **singleton** Auto Scaling Group (one instance) with a **persistent EBS data volume** that survives instance replacement, fronted by an ALB. There is no Aurora, no Redis, no OpenSearch — PDS uses on-disk SQLite. Other components: VPC, Route53, ACM, SES (with Easy DKIM), Secrets Manager, IAM, CloudWatch.

There is a sibling Terraform wrapper at `../terraform-aws-marketplace-oe-patterns-blueskypds`.

## Upgrade Workflow

For upgrading the upstream PDS version, follow the cross-pattern process in [aws-marketplace-utilities/UPGRADE.md](https://github.com/ordinaryexperts/aws-marketplace-utilities/blob/main/UPGRADE.md). The blueskypds-specific notes below supplement that doc.

### Blueskypds-specific notes

- **Single version variable.** `PDS_VERSION` in `packer/ubuntu_2404_appinstall.sh` controls everything — both the `pdsadmin` script downloaded from `raw.githubusercontent.com/bluesky-social/pds/refs/tags/v$PDS_VERSION/pdsadmin.sh` and the `ghcr.io/bluesky-social/pds:$PDS_VERSION` Docker image pulled at AMI bake time. Bump the variable; that's it. (Bluesky uses bare-numeric tags like `0.4.219` — no leading `v` in the tag itself, although the `pdsadmin.sh` URL prefixes one.)
- **No GitHub Releases for upstream.** `bluesky-social/pds` does not publish GitHub Releases — `gh release list` returns nothing. Use `gh api repos/bluesky-social/pds/tags --jq '.[].name' | head -20` (or check the dashboard's `foss_latest_version`, which falls back to highest semver-shaped tag).
- **Graviton / arm64.** The packer preinstall is invoked with `--use-graviton`; the recommended instance is `t4g.small`. Don't switch to x86 without also rebuilding the base image / updating recommended instance type in `marketplace_config.yaml`.
- **Singleton + EBS data volume.** `singleton=True` and `use_data_volume=True` on the `Asg` construct. All PDS state (SQLite DB, blob store) lives at `/data/pds` on the EBS volume, symlinked to `/pds`. Replacing the instance does not lose data; resizing the volume forces a reprovision via `AsgDataVolumeSize` change reflected in `user_data.sh`.
- **Secrets are generated in-place.** `/root/check-secrets.py` (baked into the AMI by the packer script) lazily fills three keys into the instance secret on first boot if missing: `pds_jwt_secret`, `pds_admin_password`, `pds_plc_rotation_key_k256_private_key_hex`. The IAM role grants `secretsmanager:UpdateSecret` for this. **Don't pre-populate these secret keys** — let first-boot generation run, or you'll have a chicken-and-egg with the SES Lambda which also writes to the same secret.
- **`.well-known/atproto-did` PHP handler.** nginx fronts `:443` with a self-signed cert and proxies most paths to PDS on `:3000`, but `/.well-known/atproto-did` is handled by a small PHP script (`php-fpm` 8.3) that resolves user handles → DIDs via the local PDS xrpc API. Don't remove the PHP block from `user_data.sh` or the nginx site config — handle resolution will break.
- **Crawl request.** `RequestCrawlFromBluesky` parameter (default `true`) controls a `sleep 60 && pdsadmin request-crawl bsky.network` call at the end of user_data, registering the new PDS with the public Bluesky network. Disable for private/test stacks.
- **Health check path.** ALB target group health check is `/xrpc/_health`.

## Development Environment

All development goes through Docker via `docker-compose` so host Python/CDK versions don't matter. **Don't run `cdk` / `packer` directly on the host** — use `make` targets, which wrap `docker compose run`.

Two compose services:
- `devenv` — main dev image (CDK, AWS CLI, taskcat, marketplace.py, etc.). Built from the root `Dockerfile`, which extends `ordinaryexperts/aws-marketplace-patterns-devenv`.
- `ami` — packer image. Built from `packer/Dockerfile`.

`~/.aws` is mounted into the container, so `AWS_PROFILE=...` works:

```bash
AWS_PROFILE=oe-patterns-dev make deploy
```

### First-time setup

`common.mk` is **not** checked in — it lives in `aws-marketplace-utilities` and is downloaded on demand. Before any `make` target works, run:

```bash
make update-common
```

This wgets `common.mk` at the version pinned in the root `Makefile` (currently `1.6.0` — bump along with devenv image upgrades). Most `make` targets are defined there.

## Common Commands

(See `common.mk` after `make update-common` for the full list.)

- `make build` / `make rebuild` — build (or no-cache rebuild) the devenv image
- `make bash` — interactive shell in the devenv container
- `make synth` / `make synth-to-file` — synthesize CFN; writes `dist/template.yaml` for the `-to-file` variant
- `make diff` — diff against deployed stack
- `make lint`
- `make deploy` / `make destroy` — single dev stack via the hardcoded params in this repo's `Makefile`
- `make test-main` — taskcat run (see `test/main-test/.taskcat.yml`)
- `make ami-ec2-build TEMPLATE_VERSION=<v>` — build AMI under the current `AWS_PROFILE`
- `make ami-docker-bash` — shell inside the packer container
- `make publish TEMPLATE_VERSION=<v>` / `make publish-diagram TEMPLATE_VERSION=<v>` — push CFN template / diagram to S3 (`oe-patterns-dev` profile)
- `make marketplace-validate` / `make marketplace-submit` / `make marketplace-status` — Catalog API workflow (`oe-patterns-prod` profile)
- `make clean-snapshots-tcat` / `make clean-logs-tcat` / `make clean-buckets-tcat` — taskcat cleanup

## Architecture

### CDK stack

`cdk/blueskypds/blueskypds_stack.py` composes the following common-library constructs (from `oe-patterns-cdk-common`):

- `Vpc` — bring-your-own or stack-created VPC
- `Dns` — Route53 hosted-zone integration; `add_alb(alb, add_wildcard=True)` provisions both the apex and a wildcard record (handles need wildcard subdomain resolution under the PDS hostname)
- `NotificationTopic` — SNS topic for stack notifications
- `Ses` — SES domain identity + Easy DKIM, with a Lambda that writes the SMTP password into the instance secret
- `Asg` — singleton EC2 ASG with persistent data volume
- `Alb` — ALB with ACM cert, target group health check `/xrpc/_health`

The `Asg` is wired with an extra IAM policy (`AllowUpdateInstanceSecret`) so the instance's first-boot script can extend the secret with PDS-generated keys. It also `add_dependency(ses.generate_smtp_password_custom_resource)` so the SES Lambda has finished writing the SMTP password before the instance boots and reads it.

### AMI build

`packer/ami.json` + `packer/ubuntu_2404_appinstall.sh`. The install script:

1. Runs the shared preinstall (`ubuntu_2204_2404_preinstall.sh` from `aws-marketplace-utilities` at `SCRIPT_VERSION`) with `--use-graviton`.
2. Installs Docker CE, nginx, php-fpm 8.3, sqlite3.
3. Drops the `.well-known/atproto-did` PHP handler.
4. Downloads `pdsadmin` for `v$PDS_VERSION`.
5. Bakes `/root/check-secrets.py` (the lazy-secret-fill script) and the `pds.service` systemd unit.
6. Pre-pulls `ghcr.io/bluesky-social/pds:$PDS_VERSION`.
7. Runs the shared postinstall (`ubuntu_2204_2404_postinstall.sh`).

The hardcoded `AMI_ID` and `AMI_NAME` constants near the top of `cdk/blueskypds/blueskypds_stack.py` are updated after every build.

### User data

`cdk/blueskypds/user_data.sh` runs at instance boot (templated via CFN `${...}` substitution). It:

- Configures the CloudWatch agent (system + nginx logs split between `AsgSystemLogGroup` and `AsgAppLogGroup`).
- Generates the self-signed cert at `/etc/ssl/{certs,private}/nginx-selfsigned.{crt,key}`.
- Writes the nginx site config that proxies `/` → `localhost:3000` and routes `/.well-known/atproto-did` to PHP.
- Calls `/root/check-secrets.py` to lazy-fill PDS keys into the instance secret.
- Reads the secret via SSM (`/aws/reference/secretsmanager/${InstanceSecretName}`), URL-encodes the SMTP password, and writes `/data/pds/pds.env`.
- Appends the runtime restart/awslogs/ports/volume block to the AMI-baked `compose.yaml` (the AMI version only has `services.pds.image`; user-data adds the rest so awslogs picks up the per-stack log group).
- `cfn-signal`s success.
- Optionally calls `pdsadmin request-crawl bsky.network` based on `RequestCrawlFromBluesky`.

## Versioning conventions

- **Pattern version** — set by git tag (`1.0.0`, etc.) and `git describe`. CDK reads it via `TEMPLATE_VERSION` env var or `git describe`.
- **PDS version** — `PDS_VERSION` in `packer/ubuntu_2404_appinstall.sh`.
- **Common-library** — pinned in `cdk/requirements.txt` (`oe-patterns-cdk-common@<tag>`). This pattern uses the **plain `requirements.txt`** convention (no `setup.py` / `-e .`).

## Dependencies

`cdk/requirements.txt`:
- `aws-cdk-lib==2.120.0`
- `constructs>=10.0.0,<11.0.0`
- `oe-patterns-cdk-common@4.1.9`

`Dockerfile` base: `ordinaryexperts/aws-marketplace-patterns-devenv:2.5.3`.

These pins are old and need to be bumped before the next release — see the planning notes in this repo's open `feature/upgrade` work.

## Files to update when releasing

1. `packer/ubuntu_2404_appinstall.sh` — `PDS_VERSION`
2. `cdk/blueskypds/blueskypds_stack.py` — `AMI_ID`, `AMI_NAME`
3. `Makefile` `deploy` target — AMI parameter (currently bare `AsgAmiId` is implicit; should become `AsgAmiIdv<version>` once the convention is introduced)
4. `cdk/requirements.txt` — common-library / cdk-lib bumps
5. `Dockerfile` — devenv image
6. `CHANGELOG.md`
7. `marketplace_config.yaml` — once introduced (this repo currently only has the deprecated `plf_config.yaml`)
8. Git tag

## Git workflow

- Default branches: `main`, `develop`. Active feature work currently on `feature/upgrade`.
- Releases follow git-flow: `feature/* → develop → release/X.Y.Z → main + tag`.
- **Don't `git commit` from Claude** — the user always commits manually (per global instructions).
- **Don't add commands to `common.mk`** — that file is managed in `aws-marketplace-utilities`.

## Known gaps in this repo

These are deltas from the current pattern conventions used by mastodon/discourse/open-webui — likely worth addressing in the active upgrade work:

- `Dockerfile` pins devenv `2.5.3`; `UPGRADE.md` requires `2.8.3+` for the Marketplace Catalog API workflow and current `marketplace.py` fixes. The Dockerfile also lacks `--break-system-packages` on `pip3 install` (needed for devenv `2.7.0+` / Ubuntu 24.04 / PEP 668).
- `marketplace_config.yaml` does **not** exist — only the deprecated `plf_config.yaml`. `make marketplace-*` will not run until this is added.
- `cdk/blueskypds/blueskypds_stack.py` uses the **bare `AsgAmiId`** parameter — no `NEXT_RELEASE_PREFIX` / `ami_id_param_name_suffix=` in the `Asg(...)` call. Convention is now `AsgAmiIdv<version>` so CFN sees AMI swaps as real parameter changes.
- `aws-cdk-lib==2.120.0` and `oe-patterns-cdk-common==4.1.9` are well behind the current shared baseline.
- No `diagram.png` at the repo root (it lives at `docs/aws-diagram.png`); `make publish-diagram` and the marketplace `architecture_diagram_url` need this.
- No `test/integration/` playwright suite — only the taskcat smoke test.
- `Makefile` `deploy` target hardcodes a `VpcId` / `VpcPrivateSubnet*Id` / `VpcPublicSubnet*Id` set; if those VPC IDs no longer exist in `oe-patterns-dev`, remove the parameters and let CDK create a fresh VPC (matches taskcat behavior).
