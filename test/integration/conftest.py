"""
Pytest configuration and shared fixtures for Bluesky PDS integration tests.
"""

import os
from pathlib import Path

import boto3
import pytest
import yaml


def pytest_addoption(parser):
    parser.addoption(
        "--base-url",
        action="store",
        default=None,
        help="Base URL for the PDS under test (overrides config + env)",
    )
    parser.addoption(
        "--stack-name",
        action="store",
        default=None,
        help="CloudFormation stack name (overrides config + env)",
    )


@pytest.fixture(scope="session")
def config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def base_url(request, config):
    url = (
        request.config.getoption("--base-url")
        or os.environ.get("TEST_BASE_URL")
        or config["urls"]["base_url"]
    )
    return url.rstrip("/")


@pytest.fixture(scope="session")
def stack_name(request, config):
    return (
        request.config.getoption("--stack-name")
        or os.environ.get("TEST_STACK_NAME")
        or config["aws"]["stack_name"]
    )


@pytest.fixture(scope="session")
def aws_region(config):
    return os.environ.get("AWS_REGION") or config["aws"]["region"]


@pytest.fixture(scope="session")
def cloudformation_client(aws_region):
    return boto3.client("cloudformation", region_name=aws_region)


@pytest.fixture(scope="session")
def ec2_client(aws_region):
    return boto3.client("ec2", region_name=aws_region)


@pytest.fixture(scope="session")
def stack_outputs(cloudformation_client, stack_name):
    try:
        response = cloudformation_client.describe_stacks(StackName=stack_name)
        stack = response["Stacks"][0]
        return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    except Exception as e:
        pytest.fail(f"Failed to get stack outputs for {stack_name}: {e}")


@pytest.fixture(scope="session")
def instance_id(ec2_client, stack_name):
    try:
        response = ec2_client.describe_instances(
            Filters=[
                {"Name": "tag:aws:cloudformation:stack-name", "Values": [stack_name]},
                {"Name": "instance-state-name", "Values": ["running"]},
            ]
        )
        if response["Reservations"]:
            return response["Reservations"][0]["Instances"][0]["InstanceId"]
        pytest.fail(f"No running instances found for stack {stack_name}")
    except Exception as e:
        pytest.fail(f"Failed to get instance ID: {e}")
