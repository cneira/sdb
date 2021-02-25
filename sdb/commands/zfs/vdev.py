#
# Copyright 2019 Delphix
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# pylint: disable=missing-docstring

import argparse
from typing import Iterable, List, Optional

import drgn
import sdb
from sdb.commands.zfs.internal import enum_lookup
from sdb.commands.zfs.metaslab import Metaslab
from sdb.commands.zfs.histograms import ZFSHistogram


class Vdev(sdb.Locator, sdb.PrettyPrinter):
    names = ["vdev"]
    input_type = "vdev_t *"
    output_type = "vdev_t *"

    @classmethod
    def _init_parser(cls, name: str) -> argparse.ArgumentParser:
        parser = super()._init_parser(name)
        parser.add_argument(
            "-m",
            "--metaslab",
            action="store_true",
            default=False,
            help="metaslab flag",
        )

        parser.add_argument(
            "-H",
            "--histogram",
            action="store_true",
            default=False,
            help="histogram flag",
        )

        parser.add_argument("-w",
                            "--weight",
                            action="store_true",
                            default=False,
                            help="weight flag")

        parser.add_argument("vdev_ids", nargs="*", type=int)
        return parser

    def __init__(self,
                 args: Optional[List[str]] = None,
                 name: str = "_") -> None:
        super().__init__(args, name)
        self.arg_list: List[str] = []
        if self.args.histogram:
            self.arg_list.append("-H")
        if self.args.weight:
            self.arg_list.append("-w")

    def pretty_print(self,
                     vdevs: Iterable[drgn.Object],
                     indent: int = 0) -> None:
        print(
            "".ljust(indent),
            "ADDR".ljust(18),
            "STATE".ljust(7),
            "AUX".ljust(4),
            "DESCRIPTION",
        )
        print("".ljust(indent), "-" * 60)

        for vdev in vdevs:
            level = 0
            pvd = vdev.vdev_parent
            while pvd:
                level += 2
                pvd = pvd.vdev_parent

            if int(vdev.vdev_path) != 0:
                print(
                    "".ljust(indent),
                    hex(vdev).ljust(18),
                    enum_lookup("vdev_state_t", vdev.vdev_state).ljust(7),
                    enum_lookup("vdev_aux_t", vdev.vdev_stat.vs_aux).ljust(4),
                    "".ljust(level),
                    vdev.vdev_path.string_().decode("utf-8"),
                )

            else:
                print(
                    "".ljust(indent),
                    hex(vdev).ljust(18),
                    enum_lookup("vdev_state_t", vdev.vdev_state).ljust(7),
                    enum_lookup("vdev_aux_t", vdev.vdev_stat.vs_aux).ljust(4),
                    "".ljust(level),
                    vdev.vdev_ops.vdev_op_type.string_().decode("utf-8"),
                )
            if self.args.histogram:
                if not sdb.is_null(vdev.vdev_mg):
                    ZFSHistogram.print_histogram(vdev.vdev_mg.mg_histogram, 0,
                                                 indent + 5)

            if self.args.metaslab:
                metaslabs = sdb.execute_pipeline([vdev], [Metaslab()])
                Metaslab(self.arg_list).pretty_print(metaslabs, indent + 5)

    @sdb.InputHandler("spa_t*")
    def from_spa(self, spa: drgn.Object) -> Iterable[drgn.Object]:
        if self.args.vdev_ids:
            # yield the requested top-level vdevs
            for i in self.args.vdev_ids:
                if i >= spa.spa_root_vdev.vdev_children:
                    raise sdb.CommandError(
                        self.name,
                        "vdev id {} not valid; there are only {} vdevs in {}".
                        format(i, int(spa.spa_root_vdev.vdev_children),
                               spa.spa_name.string_().decode("utf-8")))
                yield spa.spa_root_vdev.vdev_child[i]
        else:
            yield from self.from_vdev(spa.spa_root_vdev)

    @sdb.InputHandler("vdev_t*")
    def from_vdev(self, vdev: drgn.Object) -> Iterable[drgn.Object]:
        if self.args.vdev_ids:
            raise sdb.CommandError(
                self.name, "when providing a vdev, "
                "specific child vdevs can not be requested")
        yield vdev
        for cid in range(int(vdev.vdev_children)):
            cvd = vdev.vdev_child[cid]
            yield from self.from_vdev(cvd)
