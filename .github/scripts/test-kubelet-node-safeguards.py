#!/usr/bin/env python3
"""Regression test for the kubelet node safeguards drop-in.

k3s configures the kubelet with a two-entry evictionHard map and no reserved
resources, so a node reports all of its memory as schedulable and has no memory
or inode eviction threshold. roles/kubelet_safeguards renders a kubelet
drop-in that adds those back. The risky parts are:

* kubelet replaces map fields wholesale, so evictionHard must be complete and
  keep the two thresholds k3s already sets.
* enforceNodeAllocatable must keep the "pods" entry, because that entry is
  the mechanism that stops workloads from consuming the reserved memory;
  reducing allocatable without it only shrinks reported capacity.
* an empty mapping must not render a drop-in at all, so inventories that do not
  opt in keep the previous behaviour.

This renders the template and asserts all three cases.
"""

from __future__ import print_function

import os
import subprocess

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


def repo_root():
    return subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()


def fail(message):
    raise SystemExit("Kubelet node safeguards test failed: " + message)


def render(env, safeguards, enforcement=None):
    template = env.get_template("kubelet-node-safeguards.conf.j2")
    return template.render(
        kubelet_node_safeguards=safeguards,
        kubelet_safeguards_enforcement_settings=enforcement or ["pods"],
    )


def main():
    root = repo_root()
    template_dir = os.path.join(root, "roles", "kubelet_safeguards", "templates")
    # trim_blocks matches Ansible's template module; without it every block
    # tag leaves a blank line inside the rendered YAML maps.
    env = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=StrictUndefined,
        trim_blocks=True,
    )

    safeguards = {
        "reservations": {"memory": "1Gi", "cpu": "250m"},
        "eviction_hard": {
            "memory.available": "512Mi",
            "nodefs.available": "10%",
            "nodefs.inodesFree": "5%",
            "imagefs.available": "10%",
            "imagefs.inodesFree": "5%",
        },
    }

    output = render(env, safeguards)
    config = yaml.safe_load(output)

    if config.get("apiVersion") != "kubelet.config.k8s.io/v1beta1":
        fail("drop-in is not a kubelet v1beta1 configuration")
    if config.get("kind") != "KubeletConfiguration":
        fail("drop-in is not a KubeletConfiguration")

    # evictionHard must be complete and keep the thresholds k3s already sets.
    # Dropping either of these is exactly the regression this test guards.
    eviction_hard = config.get("evictionHard", {})
    for signal in ("imagefs.available", "nodefs.available"):
        if signal not in eviction_hard:
            fail("evictionHard is missing the k3s threshold " + signal)
    expected = {
        "memory.available": "512Mi",
        "nodefs.inodesFree": "5%",
        "imagefs.inodesFree": "5%",
    }
    for signal, threshold in expected.items():
        if eviction_hard.get(signal) != threshold:
            fail("evictionHard." + signal + " was not rendered as " + threshold)

    # Reservations are quantities, so unquoted input must survive as strings.
    for field in ("kubeReserved", "systemReserved"):
        reserved = config.get(field, {})
        if str(reserved.get("memory")) != "1Gi":
            fail(field + ".memory was not rendered as 1Gi")
        if str(reserved.get("cpu")) != "250m":
            fail(field + ".cpu was not rendered as 250m")

    if config.get("enforceNodeAllocatable") != ["pods"]:
        fail("enforceNodeAllocatable did not default to ['pods']")

    # The pod cgroup entry is not optional: it is the mechanism behind the
    # reduced allocatable and must survive any caller-provided list.
    output = render(env, safeguards, ["pods", "system-reserved"])
    config = yaml.safe_load(output)
    if "pods" not in config.get("enforceNodeAllocatable", []):
        fail("enforceNodeAllocatable lost the pods entry")

    # An empty mapping must not claim to configure anything.
    config = yaml.safe_load(render(env, {}))
    for field in ("evictionHard", "kubeReserved", "systemReserved"):
        if field in config:
            fail("empty kubelet_node_safeguards rendered " + field)

    print("Kubelet node safeguards regression test passed")


if __name__ == "__main__":
    main()
