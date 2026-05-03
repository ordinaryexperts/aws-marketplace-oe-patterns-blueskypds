"""
Health and basic connectivity tests for Bluesky PDS.

PDS exposes the AT Protocol XRPC API on `/xrpc/...`; there is no customer-facing
HTML home page. These tests assert that the API surface is up and reachable.
"""

import socket
import ssl
import time
from urllib.parse import urlparse

import pytest
import requests


class TestPdsHealth:
    """Level 1: Infrastructure and basic health tests."""

    def test_https_reachable(self, base_url):
        """Apex hostname is reachable over HTTPS."""
        # PDS returns a non-200 from `/` itself (no root handler), so we hit
        # /xrpc/_health and rely on the connect + TLS handshake to verify reach.
        response = requests.get(f"{base_url}/xrpc/_health", timeout=30)
        assert response.url.startswith("https://"), \
            f"Expected HTTPS, got {response.url}"

    def test_xrpc_health(self, base_url):
        """`/xrpc/_health` returns 200 + JSON `{version: ...}`."""
        response = requests.get(f"{base_url}/xrpc/_health", timeout=10)
        assert response.status_code == 200, \
            f"/xrpc/_health failed: {response.status_code} {response.text}"

        data = response.json()
        assert "version" in data, f"Missing 'version' in health response: {data}"

    def test_xrpc_health_version(self, base_url, config):
        """Health endpoint reports the expected upstream PDS version."""
        response = requests.get(f"{base_url}/xrpc/_health", timeout=10)
        data = response.json()

        expected_version = config["application"]["expected_version"]
        actual_version = data.get("version", "")
        assert expected_version in actual_version, \
            f"Version mismatch. Expected: {expected_version}, Got: {actual_version}"

    def test_describe_server(self, base_url):
        """`com.atproto.server.describeServer` returns server metadata."""
        url = f"{base_url}/xrpc/com.atproto.server.describeServer"
        response = requests.get(url, timeout=10)

        assert response.status_code == 200, \
            f"describeServer failed: {response.status_code} {response.text}"

        data = response.json()
        # Surface that exists on every PDS regardless of config
        assert "did" in data, f"describeServer missing 'did': {data}"

    def test_atproto_did_handler_404s_for_unknown_handle(self, base_url):
        """The .well-known/atproto-did PHP handler returns 404 for an unknown handle.

        The handler resolves the request's `Host` header → DID via the local PDS.
        For the apex hostname, no account exists by default so it must 404, not
        500 (PHP error) or 200 (something has gone wrong with handle isolation).
        """
        response = requests.get(f"{base_url}/.well-known/atproto-did", timeout=10)
        assert response.status_code == 404, \
            f"Expected 404 for unknown handle on apex, got {response.status_code}: {response.text}"

    def test_response_time(self, base_url):
        """Health endpoint responds within 5 seconds."""
        start = time.time()
        response = requests.get(f"{base_url}/xrpc/_health", timeout=30)
        elapsed = time.time() - start

        assert response.status_code == 200, "Health check failed"
        assert elapsed < 5.0, f"Response time {elapsed:.2f}s exceeds 5s"

    def test_ssl_certificate(self, base_url):
        """SSL certificate is valid for the apex hostname."""
        parsed = urlparse(base_url)
        hostname = parsed.hostname
        port = parsed.port or 443

        context = ssl.create_default_context()
        try:
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    assert cert is not None, "No SSL certificate found"
        except ssl.SSLError as e:
            pytest.fail(f"SSL certificate validation failed: {e}")


class TestPdsInfrastructure:
    """Level 2: AWS infrastructure tests."""

    def test_cloudformation_stack_complete(self, cloudformation_client, stack_name):
        response = cloudformation_client.describe_stacks(StackName=stack_name)
        assert len(response["Stacks"]) == 1
        status = response["Stacks"][0]["StackStatus"]
        assert status in ["CREATE_COMPLETE", "UPDATE_COMPLETE"], \
            f"Stack in unexpected state: {status}"

    def test_stack_has_required_outputs(self, stack_outputs):
        for output in ["DnsSiteUrlOutput"]:
            assert output in stack_outputs, f"Required output '{output}' missing"
            assert stack_outputs[output], f"Output '{output}' is empty"

    def test_ec2_instance_running(self, instance_id, ec2_client):
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        assert instance["State"]["Name"] == "running"
