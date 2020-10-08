#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import pytest

from buildstream import _yaml
from .. import create_repo
from .. import cli  # pylint: disable=unused-import
from .utils import kind  # pylint: disable=unused-import

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


class WorkspaceCreator:
    def __init__(self, cli, tmpdir, datafiles, project_path=None):
        self.cli = cli
        self.tmpdir = tmpdir
        self.datafiles = datafiles

        if not project_path:
            project_path = str(datafiles)
        else:
            shutil.copytree(str(datafiles), project_path)

        self.project_path = project_path
        self.bin_files_path = os.path.join(project_path, "files", "bin-files")

        self.workspace_cmd = os.path.join(self.project_path, "workspace_cmd")

    def create_workspace_element(self, kind, suffix="", workspace_dir=None, element_attrs=None):
        element_name = "workspace-test-{}{}.bst".format(kind, suffix)
        element_path = os.path.join(self.project_path, "elements")
        if not workspace_dir:
            workspace_dir = os.path.join(self.workspace_cmd, element_name)
            if workspace_dir[-4:] == ".bst":
                workspace_dir = workspace_dir[:-4]

        # Create our repo object of the given source type with
        # the bin files, and then collect the initial ref.
        repo = create_repo(kind, str(self.tmpdir))
        ref = repo.create(self.bin_files_path)

        # Write out our test target
        element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
        if element_attrs:
            element = {**element, **element_attrs}
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        # Assert that there is no reference, a fetch is needed
        assert self.cli.get_element_state(self.project_path, element_name) == "fetch needed"
        return element_name, workspace_dir

    def open_workspace(self, kind, suffix=None, workspace_dir=None, element_attrs=None, no_checkout=False):

        element_name, workspace_dir = self.create_workspace_element(kind, suffix, workspace_dir, element_attrs)
        os.makedirs(self.workspace_cmd, exist_ok=True)

        # Now open the workspace, this should have the effect of automatically
        # fetching the source from the repo.
        args = ["workspace", "open"]

        if no_checkout:
            args.append("--no-checkout")
        if workspace_dir is not None:
            args.extend(["--directory", workspace_dir])

        args.append(element_name)
        result = self.cli.run(cwd=self.workspace_cmd, project=self.project_path, args=args)

        result.assert_success()

        if not no_checkout:
            # Assert that we are now buildable because the source is now cached.
            assert self.cli.get_element_state(self.project_path, element_name) == "buildable"

            # Check that the executable hello file is found in each workspace
            filename = os.path.join(workspace_dir, "usr", "bin", "hello")
            assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_open(cli, tmpdir, datafiles, kind):
    workspace_object = WorkspaceCreator(cli, tmpdir, datafiles)
    workspace_object.open_workspace(kind)
