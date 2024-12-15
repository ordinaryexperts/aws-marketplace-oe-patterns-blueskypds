SCRIPT_VERSION=1.6.0
SCRIPT_PREINSTALL=ubuntu_2204_2404_preinstall.sh
SCRIPT_POSTINSTALL=ubuntu_2204_2404_postinstall.sh

# preinstall steps
curl -O "https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/$SCRIPT_VERSION/packer_provisioning_scripts/$SCRIPT_PREINSTALL"
chmod +x $SCRIPT_PREINSTALL
./$SCRIPT_PREINSTALL --use-graviton
rm $SCRIPT_PREINSTALL

#
# Bluesky PDS
#  * https://github.com/bluesky-social/pds?tab=readme-ov-file#self-hosting-pds
#

PDS_VERSION=0.4.74

apt-get update && apt-get upgrade -y

# prereqs
apt-get install -y curl wget gnupg apt-transport-https lsb-release ca-certificates sqlite3 xxd

# docker
mkdir -m 0755 -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

cat <<DOCKERD_CONFIG >/etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "500m",
    "max-file": "4"
  }
}
DOCKERD_CONFIG

apt-get update && apt-get install -y nginx
# remove default site
rm -f /etc/nginx/sites-enabled/default

curl --silent --show-error --fail \
     --output "/usr/local/bin/pdsadmin" \
     "https://raw.githubusercontent.com/bluesky-social/pds/refs/tags/v$PDS_VERSION/pdsadmin.sh"
chmod +x /usr/local/bin/pdsadmin

mkdir -p /opt/oe/patterns

apt-get update && apt-get install -y python3-boto3
cat <<EOF > /root/check-secrets.py
#!/usr/bin/env python3

import boto3
import json
import subprocess
import sys

region_name = sys.argv[1]
secret_name = sys.argv[2]

client = boto3.client("secretsmanager", region_name=region_name)
response = client.list_secrets(
  Filters=[{"Key": "name", "Values": [secret_name]}]
)
arn = response["SecretList"][0]["ARN"]
response = client.get_secret_value(
  SecretId=arn
)
current_secret = json.loads(response["SecretString"])
needs_update = False
if not 'pds_jwt_secret' in current_secret:
  needs_update = True
  cmd = 'openssl rand --hex 16'
  output = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True).stdout.decode('utf-8').strip()
  current_secret['pds_jwt_secret'] = output
if not 'pds_admin_password' in current_secret:
  needs_update = True
  cmd = 'openssl rand --hex 16'
  output = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True).stdout.decode('utf-8').strip()
  current_secret['pds_admin_password'] = output
if not 'pds_plc_rotation_key_k256_private_key_hex' in current_secret:
  needs_update = True
  cmd = 'openssl ecparam --name secp256k1 --genkey --noout --outform DER | tail --bytes=+8 | head --bytes=32 | xxd --plain --cols 32'
  output = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True).stdout.decode('utf-8').strip()
  current_secret['pds_plc_rotation_key_k256_private_key_hex'] = output
if needs_update:
  client.update_secret(
    SecretId=arn,
    SecretString=json.dumps(current_secret)
  )
else:
  print('Secrets already generated - no action needed.')
EOF
chown root:root /root/check-secrets.py
chmod 744 /root/check-secrets.py

cat <<SYSTEMD_UNIT_FILE >/etc/systemd/system/pds.service
[Unit]
Description=Bluesky PDS Service
Documentation=https://github.com/bluesky-social/pds
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/pds
ExecStart=/usr/bin/docker compose --file /root/compose.yaml up --detach
ExecStop=/usr/bin/docker compose --file /root/compose.yaml down

[Install]
WantedBy=default.target
SYSTEMD_UNIT_FILE

systemctl daemon-reload

# pull the image
cat <<EOF > /root/compose.yaml
services:
  pds:
    container_name: pds
    image: ghcr.io/bluesky-social/pds:$PDS_VERSION
EOF
docker compose --file /root/compose.yaml pull

# post install steps
curl -O "https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/$SCRIPT_VERSION/packer_provisioning_scripts/$SCRIPT_POSTINSTALL"
chmod +x "$SCRIPT_POSTINSTALL"
./"$SCRIPT_POSTINSTALL"
rm $SCRIPT_POSTINSTALL
