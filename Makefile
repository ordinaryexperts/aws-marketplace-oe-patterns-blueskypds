-include common.mk

update-common:
	wget -O common.mk https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/1.6.0/common.mk

deploy: build
	docker compose run -w /code/cdk --rm devenv cdk deploy \
	--require-approval never \
	--parameters AlbCertificateArn=arn:aws:acm:us-east-1:992593896645:certificate/5cdb3607-4cef-4d17-90b1-f6592e322277 \
	--parameters AlbIngressCidr=0.0.0.0/0 \
	--parameters AsgDataVolumeSize=102 \
	--parameters AsgDataVolumeSnapshot=snap-00837f782589a35ad \
	--parameters AsgReprovisionString=20241219.1 \
	--parameters AsgDiskUsageAlarmThreshold=75 \
	--parameters DnsHostname=blueskypds.dev.patterns.ordinaryexperts.com \
	--parameters DnsRoute53HostedZoneName=dev.patterns.ordinaryexperts.com \
	--parameters NotificationTopicEmail=dylan@ordinaryexperts.com \
	--parameters VpcId=vpc-00425deda4c835455 \
	--parameters VpcPrivateSubnet1Id=subnet-030c94b9795c6cb96 \
	--parameters VpcPrivateSubnet2Id=subnet-079290412ce63c4d5 \
	--parameters VpcPublicSubnet1Id=subnet-0c2f5d4daa1792c8d \
	--parameters VpcPublicSubnet2Id=subnet-060c39a6ded9e89d7
