import os
import subprocess

from aws_cdk import (
    Aws,
    aws_cloudwatch,
    aws_iam,
    CfnOutput,
    CfnParameter,
    Stack
)
from constructs import Construct

from oe_patterns_cdk_common.alb import Alb
from oe_patterns_cdk_common.asg import Asg
from oe_patterns_cdk_common.dns import Dns
from oe_patterns_cdk_common.notification_topic import NotificationTopic
from oe_patterns_cdk_common.ses import Ses
from oe_patterns_cdk_common.vpc import Vpc

if 'TEMPLATE_VERSION' in os.environ:
    template_version = os.environ['TEMPLATE_VERSION']
else:
    try:
        template_version = subprocess.check_output(["git", "describe"]).strip().decode('ascii')
    except:
        template_version = "CICD"

AMI_ID = "ami-084d5031be9bf8771"  # ordinary-experts-patterns-blueskypds-2.1.0-20260720-0351 (dev — for taskcat)
NEXT_RELEASE_PREFIX = "v210"

class BlueskypdsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # vpc
        vpc = Vpc(
            self,
            "Vpc"
        )

        self.request_crawl_from_bluesky_param = CfnParameter(
            self,
            "RequestCrawlFromBluesky",
            allowed_values=[ "true", "false" ],
            default="true",
            description="Request that this PDS be crawled by Bluesky network"
        )

        # dns
        dns = Dns(self, "Dns")

        # notification topic
        notification_topic = NotificationTopic(
            self,
            "NotificationTopic"
        )

        ses = Ses(
            self,
            "Ses",
            hosted_zone_name=dns.route_53_hosted_zone_name_param.value_as_string
        )

        asg_update_secret_policy = aws_iam.CfnRole.PolicyProperty(
            policy_document=aws_iam.PolicyDocument(
                statements=[
                    aws_iam.PolicyStatement(
                        effect=aws_iam.Effect.ALLOW,
                        actions=[
                            "secretsmanager:UpdateSecret"
                        ],
                        resources=[ses.secret_arn()]
                    )
                ]
            ),
            policy_name="AllowUpdateInstanceSecret"
        )

        # asg
        with open("blueskypds/user_data.sh") as f:
            user_data = f.read()
        asg = Asg(
            self,
            "Asg",
            additional_iam_role_policies=[asg_update_secret_policy],
            ami_id=AMI_ID,
            ami_id_param_name_suffix=NEXT_RELEASE_PREFIX,
            default_instance_type="t4g.small",
            notification_topic_arn=notification_topic.notification_topic_arn(),
            secret_arns=[ses.secret_arn()],
            singleton=True,
            use_data_volume=True,
            user_data_contents=user_data,
            user_data_variables={
                "Hostname": dns.hostname(),
                "HostedZoneName": dns.route_53_hosted_zone_name_param.value_as_string,
                "InstanceSecretName": Aws.STACK_NAME + "/instance/credentials"
            },
            vpc=vpc
        )

        alb = Alb(
            self,
            "Alb",
            asg=asg,
            health_check_path = "/xrpc/_health",
            vpc=vpc
        )

        asg.asg.target_group_arns = [ alb.target_group.ref ]

        asg.asg.node.add_dependency(ses.generate_smtp_password_custom_resource)

        dns.add_alb(alb, add_wildcard=True)

        CfnOutput(
            self,
            "FirstUseInstructions",
            description="Instructions for getting started",
            value="""
To create an initial user, log into the EC2 instance using SSM Sessions Manager, then run the following:

sudo pdsadmin account create

For more information, see the GitHub repository:

https://github.com/ordinaryexperts/aws-marketplace-oe-patterns-blueskypds
"""
        )

        parameter_groups = [
            {
                "Label": {
                    "default": "Application Config"
                },
                "Parameters": [
                    self.request_crawl_from_bluesky_param.logical_id
                ]
            }
        ]
        parameter_groups += alb.metadata_parameter_group()
        parameter_groups += dns.metadata_parameter_group()
        parameter_groups += asg.metadata_parameter_group()
        parameter_groups += ses.metadata_parameter_group()
        parameter_groups += notification_topic.metadata_parameter_group()
        parameter_groups += vpc.metadata_parameter_group()

        # AWS::CloudFormation::Interface
        self.template_options.metadata = {
            "OE::Patterns::TemplateVersion": template_version,
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": parameter_groups,
                "ParameterLabels": {
                    self.request_crawl_from_bluesky_param.logical_id: {
                        "default": "Request Crawl From Bluesky Network"
                    },
                    **alb.metadata_parameter_labels(),
                    **dns.metadata_parameter_labels(),
                    **asg.metadata_parameter_labels(),
                    **ses.metadata_parameter_labels(),
                    **notification_topic.metadata_parameter_labels(),
                    **vpc.metadata_parameter_labels()
                }
            }
        }
