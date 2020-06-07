# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import create_repo


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "junctions",)


def update_project(project_path, updated_configuration):
    project_conf_path = os.path.join(project_path, "project.conf")
    project_conf = _yaml.roundtrip_load(project_conf_path)

    project_conf.update(updated_configuration)

    _yaml.roundtrip_dump(project_conf, project_conf_path)


#
# Test behavior of `bst show` on a junction element
#
@pytest.mark.datafiles(DATA_DIR)
def test_simple_show(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "simple")
    assert cli.get_element_state(project, "subproject.bst") == "junction"


#
# Test that we can build build a pipeline with a junction
#
@pytest.mark.datafiles(DATA_DIR)
def test_simple_build(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "simple")

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file from the subproject
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))


#
# Test failure when there is a missing project.conf
#
@pytest.mark.datafiles(DATA_DIR)
def test_junction_missing_project_conf(cli, datafiles):
    project = os.path.join(str(datafiles), "simple")

    # Just remove the project.conf from the simple test and assert the error
    os.remove(os.path.join(project, "subproject", "project.conf"))

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)
    assert "target.bst [line 4 column 2]" in result.stderr


#
# Test failure when there is a missing project.conf in a workspaced junction
#
@pytest.mark.datafiles(DATA_DIR)
def test_workspaced_junction_missing_project_conf(cli, datafiles):
    project = os.path.join(str(datafiles), "simple")

    workspace_dir = os.path.join(project, "workspace")

    result = cli.run(project=project, args=["workspace", "open", "subproject.bst", "--directory", workspace_dir])
    result.assert_success()

    # Remove the project.conf from the workspace directory
    os.remove(os.path.join(workspace_dir, "project.conf"))

    # Assert the same missing project.conf error
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)

    # Assert that we have the expected provenance encoded into the error
    assert "target.bst [line 4 column 2]" in result.stderr


#
# Test successful builds of deeply nested targets
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,expected",
    [("target.bst", ["sub.txt", "subsub.txt"]), ("deeptarget.bst", ["sub.txt", "subsub.txt", "subsubsub.txt"]),],
    ids=["simple", "deep"],
)
def test_nested(cli, tmpdir, datafiles, target, expected):
    project = os.path.join(str(datafiles), "nested")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from all subprojects
    for filename in expected:
        assert os.path.exists(os.path.join(checkoutdir, filename))


#
# Test missing elements/junctions in subprojects
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,provenance",
    [
        ("target.bst", "target.bst [line 4 column 2]"),
        ("sub-target.bst", "junction-A.bst:target.bst [line 4 column 2]"),
        ("bad-junction.bst", "bad-junction.bst [line 3 column 2]"),
        ("sub-target-bad-junction.bst", "junction-A.bst:bad-junction-target.bst [line 4 column 2]"),
    ],
    ids=["subproject-target", "subsubproject-target", "local-junction", "subproject-junction"],
)
def test_missing_files(cli, datafiles, target, provenance):
    project = os.path.join(str(datafiles), "missing-element")
    result = cli.run(project=project, args=["show", target])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert provenance in result.stderr


#
# Test various invalid junction configuraions
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,reason,provenance",
    [
        # Test a junction which itself has dependencies
        ("junction-with-deps.bst", LoadErrorReason.INVALID_JUNCTION, "base-with-deps.bst [line 6 column 2]"),
        # Test having a dependency directly on a junction
        ("junction-dep.bst", LoadErrorReason.INVALID_DATA, "junction-dep.bst [line 3 column 2]"),
        # Test that we error correctly when we junction-depend on a non-junction
        (
            "junctiondep-not-a-junction.bst",
            LoadErrorReason.INVALID_DATA,
            "junctiondep-not-a-junction.bst [line 3 column 2]",
        ),
    ],
    ids=["junction-with-deps", "deps-on-junction", "use-element-as-junction"],
)
def test_invalid(cli, datafiles, target, reason, provenance):
    project = os.path.join(str(datafiles), "invalid")
    result = cli.run(project=project, args=["build", target])
    result.assert_main_error(ErrorDomain.LOAD, reason)
    assert provenance in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,expect_exists,expect_not_exists",
    [("target-default.bst", "pony.txt", "horsy.txt"), ("target-explicit.bst", "horsy.txt", "pony.txt"),],
    ids=["check-values", "set-explicit-values"],
)
def test_options(cli, tmpdir, datafiles, target, expect_exists, expect_not_exists):
    project = os.path.join(str(datafiles), "options")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    assert os.path.exists(os.path.join(checkoutdir, expect_exists))
    assert not os.path.exists(os.path.join(checkoutdir, expect_not_exists))


#
# Test propagation of options through a junction
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "animal,expect_exists,expect_not_exists",
    [("pony", "pony.txt", "horsy.txt"), ("horsy", "horsy.txt", "pony.txt"),],
    ids=["pony", "horsy"],
)
def test_options_propagate(cli, tmpdir, datafiles, animal, expect_exists, expect_not_exists):
    project = os.path.join(str(datafiles), "options")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    update_project(
        project,
        {
            "options": {
                "animal": {
                    "type": "enum",
                    "description": "The kind of animal",
                    "values": ["pony", "horsy"],
                    "default": "pony",
                    "variable": "animal",
                }
            }
        },
    )

    # Build, checkout
    result = cli.run(project=project, args=["--option", "animal", animal, "build", "target-propagate.bst"])
    result.assert_success()
    result = cli.run(
        project=project,
        args=[
            "--option",
            "animal",
            animal,
            "artifact",
            "checkout",
            "target-propagate.bst",
            "--directory",
            checkoutdir,
        ],
    )
    result.assert_success()

    assert os.path.exists(os.path.join(checkoutdir, expect_exists))
    assert not os.path.exists(os.path.join(checkoutdir, expect_not_exists))


#
# A lot of testing is using local sources for the junctions for
# speed and convenience, however there are some internal optimizations
# for local sources, so we need to test some things using a real
# source which involves triggering fetches.
#
# We use the tar source for this since it is a core plugin.
#
@pytest.mark.datafiles(DATA_DIR)
def test_tar_show(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "use-repo")

    # Create the repo from 'baserepo' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "baserepo"))

    # Write out junction element with tar source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    # Check that bst show succeeds with implicit subproject fetching and the
    # pipeline includes the subproject element
    element_list = cli.get_pipeline(project, ["target.bst"])
    assert "base.bst:target.bst" in element_list


@pytest.mark.datafiles(DATA_DIR)
def test_tar_build(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "use-repo")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'baserepo' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "baserepo"))

    # Write out junction element with tar source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    # Build (with implicit fetch of subproject), checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file from the subproject
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_tar_missing_project_conf(cli, tmpdir, datafiles):
    project = datafiles / "use-repo"

    # Remove the project.conf from this repo
    os.remove(datafiles / "use-repo" / "baserepo" / "project.conf")

    # Create the repo from 'base' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "baserepo"))

    # Write out junction element with tar source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, str(project / "base.bst"))

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)

    # Assert that we have the expected provenance encoded into the error
    assert "target.bst [line 3 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_build_tar_cross_junction_names(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "use-repo")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'base' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "baserepo"))

    # Write out junction element with tar source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    # Build (with implicit fetch of subproject), checkout
    result = cli.run(project=project, args=["build", "base.bst:target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "base.bst:target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from both projects
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target",
    [
        "junction-full-path.bst",
        "element-full-path.bst",
        "subproject.bst:subsubproject.bst:subsubsubproject.bst:target.bst",
    ],
    ids=["junction", "element", "command-line"],
)
def test_full_path(cli, tmpdir, datafiles, target):
    project = os.path.join(str(datafiles), "full-path")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file from base
    assert os.path.exists(os.path.join(checkoutdir, "subsubsub.txt"))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,provenance",
    [
        ("junction-full-path-notfound.bst", "junction-full-path-notfound.bst [line 3 column 2]"),
        ("element-full-path-notfound.bst", "element-full-path-notfound.bst [line 3 column 2]"),
        ("subproject.bst:subsubproject.bst:pony.bst", None),
    ],
    ids=["junction", "element", "command-line"],
)
def test_full_path_not_found(cli, tmpdir, datafiles, target, provenance):
    project = os.path.join(str(datafiles), "full-path")

    # Build
    result = cli.run(project=project, args=["build", target])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Check that provenance was provided if expected
    if provenance:
        assert provenance in result.stderr
