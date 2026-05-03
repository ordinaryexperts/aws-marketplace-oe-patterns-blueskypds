# Unreleased

# 2.0.0

* Upgrade Bluesky PDS from `0.4.74` to `0.4.219` (latest upstream)
* Rebrand to **Bluesky PDS on AWS by FOSSonCloud** (README + Marketplace product metadata)
* Add `marketplace_config.yaml` for the AWS Marketplace Catalog API workflow (`plf_config.yaml` is deprecated)
* Bump devenv image `2.5.3 to 2.8.3` (Ubuntu 24.04 / Python 3.12 / PEP 668)
* Bump `aws-cdk-lib` `2.120.0 to 2.225.0`
* Bump `oe-patterns-cdk-common` `4.1.9 to 4.5.0`
* Switch CloudFormation AMI parameter from `AsgAmiId` to `AsgAmiIdv200` (versioned parameter convention) so stack updates surface AMI changes correctly
* `docker-compose.yml` now mounts `~/.aws` and forwards `AWS_PROFILE` (matches mastodon/discourse/open-webui)
* Add `test/integration/` smoke-test suite: `/xrpc/_health`, `com.atproto.server.describeServer`, `.well-known/atproto-did` PHP handler, SSL handshake, CloudFormation + EC2 sanity checks
* Drop the legacy `generated_ami_ids` regional map and `AWSAMIRegionMap` `CfnMapping` -- AWS Marketplace Catalog API now handles multi-region AMI replication automatically
* Drop stale `VpcId` / `VpcPrivateSubnet*Id` / `VpcPublicSubnet*Id` / `AsgDataVolumeSnapshot` from the Makefile `deploy` target (the IDs no longer exist; CDK creates a fresh VPC)
* Add `CLAUDE.md` documenting blueskypds-specific conventions

## Migration notes

* **Existing subscribers updating an in-place stack from 1.0.0 must update the parameter name** in their stack-update wizard from `AsgAmiId` to `AsgAmiIdv200`. CloudFormation treats this as a real parameter change so the AMI swap is correctly applied.
* No data-format or upstream config breaking changes between PDS `0.4.74` and `0.4.219` -- `pds.env` shape is unchanged and the SQLite + blob store on the EBS data volume are read by the new image as-is.

# 1.0.0

* Initial development
