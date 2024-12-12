#!/bin/bash

# aws cloudwatch
cat <<EOF > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root",
    "logfile": "/opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log"
  },
  "metrics": {
    "metrics_collected": {
      "collectd": {
        "metrics_aggregation_interval": 60
      },
      "disk": {
        "measurement": ["used_percent"],
        "metrics_collection_interval": 60,
        "resources": ["*"]
      },
      "mem": {
        "measurement": ["mem_used_percent"],
        "metrics_collection_interval": 60
      }
    },
    "append_dimensions": {
      "ImageId": "\${!aws:ImageId}",
      "InstanceId": "\${!aws:InstanceId}",
      "InstanceType": "\${!aws:InstanceType}",
      "AutoScalingGroupName": "\${!aws:AutoScalingGroupName}"
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/dpkg.log",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/dpkg.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/apt/history.log",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/apt/history.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/cloud-init.log",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/cloud-init.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/cloud-init-output.log",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/cloud-init-output.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/auth.log",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/auth.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/syslog",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/syslog",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/amazon/ssm/amazon-ssm-agent.log",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/amazon/ssm/amazon-ssm-agent.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/amazon/ssm/errors.log",
            "log_group_name": "${AsgSystemLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/amazon/ssm/errors.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/nginx/access.log",
            "log_group_name": "${AsgAppLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/nginx/access.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/nginx/error.log",
            "log_group_name": "${AsgAppLogGroup}",
            "log_stream_name": "{instance_id}-/var/log/nginx/error.log",
            "timezone": "UTC"
          }
        ]
      }
    },
    "log_stream_name": "{instance_id}"
  }
}
EOF
systemctl enable amazon-cloudwatch-agent
systemctl start amazon-cloudwatch-agent

openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/ssl/private/nginx-selfsigned.key \
  -out /etc/ssl/certs/nginx-selfsigned.crt \
  -subj '/CN=localhost'

# move to AMI
apt-get update && apt-get install -y nginx
# setup nginx config
cat <<EOF > /etc/nginx/sites-enabled/blueskypds
server {
    listen 443 ssl;
    server_name ${Hostname};

    # SSL certificate configuration
    ssl_certificate /etc/ssl/certs/nginx-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/nginx-selfsigned.key;

    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host ${Hostname};
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
}
EOF
# remove default site
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

curl --silent --show-error --fail \
     --output "/usr/local/bin/pdsadmin" \
     "https://raw.githubusercontent.com/bluesky-social/pds/refs/tags/v0.4.74/pdsadmin.sh"
chmod +x /usr/local/bin/pdsadmin

mkdir -p /opt/oe/patterns
# end move to AMI

# TODO make this EBS mount
mkdir -p /pds
chmod 700 /pds


# TODO move to AMI
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

/root/check-secrets.py ${AWS::Region} ${InstanceSecretName}

aws ssm get-parameter \
    --name "/aws/reference/secretsmanager/${InstanceSecretName}" \
    --with-decryption \
    --query Parameter.Value \
| jq -r . > /opt/oe/patterns/instance.json

PDS_JWT_SECRET=$(cat /opt/oe/patterns/instance.json | jq -r .pds_jwt_secret)
PDS_ADMIN_PASSWORD=$(cat /opt/oe/patterns/instance.json | jq -r .pds_admin_password)
PDS_PLC_ROTATION_KEY_K256_PRIVATE_KEY_HEX=$(cat /opt/oe/patterns/instance.json | jq -r .pds_plc_rotation_key_k256_private_key_hex)

cat <<PDS_CONFIG >"/pds/pds.env"
PDS_HOSTNAME="${Hostname}"
PDS_JWT_SECRET="$PDS_JWT_SECRET"
PDS_ADMIN_PASSWORD="$PDS_ADMIN_PASSWORD"
PDS_PLC_ROTATION_KEY_K256_PRIVATE_KEY_HEX="$PDS_PLC_ROTATION_KEY_K256_PRIVATE_KEY_HEX"
PDS_DATA_DIRECTORY="/pds"
PDS_BLOBSTORE_DISK_LOCATION="/pds/blocks"
PDS_BLOB_UPLOAD_LIMIT=52428800
PDS_DID_PLC_URL="https://plc.directory"
PDS_BSKY_APP_VIEW_URL="https://api.bsky.app"
PDS_BSKY_APP_VIEW_DID="did:web:api.bsky.app"
PDS_REPORT_SERVICE_URL="https://mod.bsky.app"
PDS_REPORT_SERVICE_DID="did:plc:ar7c4by46qjdydhdevvrndac"
PDS_CRAWLERS="https://bsky.network"
LOG_ENABLED=true
PDS_CONFIG

cat <<EOF > /pds/compose.yaml
version: '3.9'
services:
  pds:
    container_name: pds
    image: ghcr.io/bluesky-social/pds:0.4
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - type: bind
        source: /pds
        target: /pds
    env_file:
      - /pds/pds.env
EOF

systemctl enable pds
systemctl restart pds

echo hi
success=$?
cfn-signal --exit-code $success --stack ${AWS::StackName} --resource Asg --region ${AWS::Region}
