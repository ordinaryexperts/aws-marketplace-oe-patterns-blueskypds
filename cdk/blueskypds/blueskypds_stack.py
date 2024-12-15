import os
import subprocess

from aws_cdk import (
    Aws,
    aws_iam,
    CfnMapping,
    CfnOutput,
    CfnParameter,
    Stack
)
from constructs import Construct

from oe_patterns_cdk_common.alb import Alb
from oe_patterns_cdk_common.asg import Asg
from oe_patterns_cdk_common.assets_bucket import AssetsBucket
from oe_patterns_cdk_common.aurora_cluster import AuroraPostgresql
from oe_patterns_cdk_common.db_secret import DbSecret
from oe_patterns_cdk_common.dns import Dns
from oe_patterns_cdk_common.elasticache_cluster import ElasticacheRedis
from oe_patterns_cdk_common.open_search_service import OpenSearchService
from oe_patterns_cdk_common.ses import Ses
from oe_patterns_cdk_common.util import Util
from oe_patterns_cdk_common.vpc import Vpc

if 'TEMPLATE_VERSION' in os.environ:
    template_version = os.environ['TEMPLATE_VERSION']
else:
    try:
        template_version = subprocess.check_output(["git", "describe"]).strip().decode('ascii')
    except:
        template_version = "CICD"

# AMI list generated by:
# make TEMPLATE_VERSION=2.1.0 ami-ec2-build
# on Tue Oct 29 00:14:28 UTC 2024.
AMI_ID="ami-01242c4a2bc5762a1"
AMI_NAME="ordinary-experts-patterns-blueskypds-e4c221d-20241215-0315"
generated_ami_ids = {
    "af-south-1": "ami-XXXXXXXXXXXXXXXXX",
    "ap-east-1": "ami-XXXXXXXXXXXXXXXXX",
    "ap-northeast-1": "ami-XXXXXXXXXXXXXXXXX",
    "ap-northeast-2": "ami-XXXXXXXXXXXXXXXXX",
    "ap-northeast-3": "ami-XXXXXXXXXXXXXXXXX",
    "ap-south-1": "ami-XXXXXXXXXXXXXXXXX",
    "ap-southeast-1": "ami-XXXXXXXXXXXXXXXXX",
    "ap-southeast-2": "ami-XXXXXXXXXXXXXXXXX",
    "ap-southeast-3": "ami-XXXXXXXXXXXXXXXXX",
    "ca-central-1": "ami-XXXXXXXXXXXXXXXXX",
    "eu-central-1": "ami-XXXXXXXXXXXXXXXXX",
    "eu-central-2": "ami-XXXXXXXXXXXXXXXXX",
    "eu-north-1": "ami-XXXXXXXXXXXXXXXXX",
    "eu-south-1": "ami-XXXXXXXXXXXXXXXXX",
    "eu-south-2": "ami-XXXXXXXXXXXXXXXXX",
    "eu-west-1": "ami-XXXXXXXXXXXXXXXXX",
    "eu-west-2": "ami-XXXXXXXXXXXXXXXXX",
    "eu-west-3": "ami-XXXXXXXXXXXXXXXXX",
    "me-central-1": "ami-XXXXXXXXXXXXXXXXX",
    "me-south-1": "ami-XXXXXXXXXXXXXXXXX",
    "sa-east-1": "ami-XXXXXXXXXXXXXXXXX",
    "us-east-2": "ami-XXXXXXXXXXXXXXXXX",
    "us-west-1": "ami-XXXXXXXXXXXXXXXXX",
    "us-west-2": "ami-XXXXXXXXXXXXXXXXX",
    "us-east-1": "ami-01242c4a2bc5762a1"
}
# End generated code block.

class BlueskypdsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # vpc
        vpc = Vpc(
            self,
            "Vpc"
        )

        # dns
        dns = Dns(self, "Dns")

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
            default_instance_type="t4g.small",
            secret_arns=[ses.secret_arn()],
            singleton = True,
            use_data_volume = True,
            user_data_contents=user_data,
            user_data_variables={
                "Hostname": dns.hostname(),
                "HostedZoneName": dns.route_53_hosted_zone_name_param.value_as_string,
                "InstanceSecretName": Aws.STACK_NAME + "/instance/credentials"
            },
            vpc=vpc
        )

        ami_mapping={ "AMI": { "OEAMI": AMI_NAME } }
        for region in generated_ami_ids.keys():
            ami_mapping[region] = { "AMI": generated_ami_ids[region] }
        CfnMapping(
            self,
            "AWSAMIRegionMap",
            mapping=ami_mapping
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
TODO
"""
        )

        parameter_groups = []
        parameter_groups += alb.metadata_parameter_group()
        parameter_groups += dns.metadata_parameter_group()
        parameter_groups += asg.metadata_parameter_group()
        parameter_groups += ses.metadata_parameter_group()
        parameter_groups += vpc.metadata_parameter_group()

        # AWS::CloudFormation::Interface
        self.template_options.metadata = {
            "OE::Patterns::TemplateVersion": template_version,
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": parameter_groups,
                "ParameterLabels": {
                    **alb.metadata_parameter_labels(),
                    **dns.metadata_parameter_labels(),
                    **asg.metadata_parameter_labels(),
                    **ses.metadata_parameter_labels(),
                    **vpc.metadata_parameter_labels()
                }
            }
        }
