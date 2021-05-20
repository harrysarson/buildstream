# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.exceptions import ErrorDomain
from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains


pytestmark = pytest.mark.remoteexecution


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# Test building an executable with remote-execution and remote-cache enabled
@pytest.mark.datafiles(DATA_DIR)
def test_remote_autotools_build(cli, datafiles, remote_services):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_name = "autotools/amhello.bst"

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    # Enable remote cache and remove explicit remote execution CAS configuration.
    cli.configure({"cache": {"remote-cache": {"url": remote_services.storage_service}}})
    del cli.config["remote-execution"]["storage-service"]

    # Build element with remote execution.
    result = cli.run(project=project, args=["build", element_name])
    result.assert_success()

    # Attempt checkout from local cache by temporarily disabling remote cache.
    # This should fail as the build result shouldn't have been downloaded to the local cache.
    del cli.config["cache"]["remote-cache"]
    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_main_error(ErrorDomain.STREAM, "uncached-checkout-attempt")

    # Re-enable remote cache and attempt checkout again.
    cli.configure({"cache": {"remote-cache": {"url": remote_services.storage_service}}})
    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_success()

    assert_contains(
        checkout,
        [
            "/usr",
            "/usr/lib",
            "/usr/bin",
            "/usr/share",
            "/usr/bin/hello",
            "/usr/share/doc",
            "/usr/share/doc/amhello",
            "/usr/share/doc/amhello/README",
        ],
    )
