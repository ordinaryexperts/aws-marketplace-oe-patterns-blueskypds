# Integration tests

Smoke tests for a deployed Bluesky PDS stack. Run after `make deploy`.

## Run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Defaults from config.yaml — override with env vars or CLI flags
TEST_BASE_URL=https://blueskypds-yourname.dev.patterns.ordinaryexperts.com \
TEST_STACK_NAME=oe-patterns-blueskypds-yourname \
AWS_PROFILE=oe-patterns-dev \
pytest -v
```

## What it covers

- `/xrpc/_health` returns 200 + JSON containing the upstream PDS version
- `/xrpc/com.atproto.server.describeServer` returns server metadata
- `/.well-known/atproto-did` PHP handler 404s on the apex hostname (no account)
- SSL handshake succeeds for the apex hostname
- CloudFormation stack is in `*_COMPLETE` and has the expected outputs
- EC2 instance is running

## Not covered (yet)

- pdsadmin account create + login flow (requires writes to PLC directory and SES sandbox exit)
- Federation / firehose connectivity
- Wildcard handle resolution after account creation
