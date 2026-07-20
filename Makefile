-include common.mk

update-common:
	wget -O common.mk https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/1.10.3/common.mk

deploy: build
	docker compose run -w /code/cdk --rm devenv cdk deploy \
	--require-approval never \
	--parameters AlbCertificateArn=arn:aws:acm:us-east-1:992593896645:certificate/951d2b92-e609-4c1c-aaab-d3f07ef43971 \
	--parameters AlbIngressCidr=0.0.0.0/0 \
	--parameters AsgAmiIdv210=ami-084d5031be9bf8771 \
	--parameters AsgDataVolumeSize=102 \
	--parameters AsgReprovisionString=20241219.1 \
	--parameters AsgDiskUsageAlarmThreshold=75 \
	--parameters DnsHostname=blueskypds.dev.patterns.ordinaryexperts.com \
	--parameters DnsRoute53HostedZoneName=dev.patterns.ordinaryexperts.com \
	--parameters NotificationTopicEmail=dylan@ordinaryexperts.com \
	--parameters SesCreateDomainIdentity=false
