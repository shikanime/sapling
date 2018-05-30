#!/usr/bin/env python3
#
# Copyright (c) 2004-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import os
from textwrap import dedent

from .lib.hg_extension_test_base import EdenHgTestCase, hg_test


@hg_test
class MoveTest(EdenHgTestCase):
    def populate_backing_repo(self, repo):
        repo.write_file("hello.txt", "hola")
        repo.commit("Initial commit.\n")

    def test_move_file_without_modification(self):
        self.hg("move", "hello.txt", "goodbye.txt")
        self.assert_status({"goodbye.txt": "A", "hello.txt": "R"})
        extended_status = self.hg("status", "--copies")
        self.assertEqual(
            dedent(
                """\
        A goodbye.txt
          hello.txt
        R hello.txt
        """
            ),
            extended_status,
        )
        self.assert_copy_map({"goodbye.txt": "hello.txt"})
        self.assertFalse(os.path.exists(self.get_path("hello.txt")))
        self.assertTrue(os.path.exists(self.get_path("goodbye.txt")))

        self.repo.commit("Commit copied file.\n")
        self.assert_status_empty()
        self.assert_copy_map({})

    def test_move_file_then_revert_it(self):
        self.hg("move", "hello.txt", "goodbye.txt")
        self.assert_status({"goodbye.txt": "A", "hello.txt": "R"})
        self.assert_copy_map({"goodbye.txt": "hello.txt"})
        self.assertFalse(os.path.exists(self.get_path("hello.txt")))
        self.assertTrue(os.path.exists(self.get_path("goodbye.txt")))

        self.hg("revert", "--no-backup", "--all")
        self.assert_status({"goodbye.txt": "?"})
        self.assert_copy_map({})
        self.assertTrue(os.path.exists(self.get_path("hello.txt")))
        self.assertTrue(os.path.exists(self.get_path("goodbye.txt")))

        self.hg("add", "goodbye.txt")
        extended_status = self.hg("status", "--copies")
        self.assertEqual(
            dedent(
                """\
        A goodbye.txt
        """
            ),
            extended_status,
        )

    def test_replace_after_move_file_then_revert_it(self):
        self.hg("move", "hello.txt", "goodbye.txt")
        self.assert_status({"goodbye.txt": "A", "hello.txt": "R"})
        self.assert_copy_map({"goodbye.txt": "hello.txt"})
        self.assertFalse(os.path.exists(self.get_path("hello.txt")))
        self.assertTrue(os.path.exists(self.get_path("goodbye.txt")))

        self.write_file("hello.txt", "different contents")
        self.assert_status({"goodbye.txt": "A", "hello.txt": "R"})
        self.hg("add", "hello.txt")
        self.assert_status({"goodbye.txt": "A", "hello.txt": "M"})
        self.assert_copy_map({"goodbye.txt": "hello.txt"})
        extended_status = self.hg("status", "--copies")
        self.assertEqual(
            dedent(
                """\
        M hello.txt
        A goodbye.txt
          hello.txt
        """
            ),
            extended_status,
        )

        self.hg("revert", "--no-backup", "--all")
        self.assert_status({"goodbye.txt": "?"})
        self.assert_copy_map({})
        self.assertTrue(os.path.exists(self.get_path("hello.txt")))
        self.assertTrue(os.path.exists(self.get_path("goodbye.txt")))
