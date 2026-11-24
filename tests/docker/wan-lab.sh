#!/usr/bin/env bash
#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software. RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

set -euo pipefail

root="${WAN_LAB_ROOT:?WAN_LAB_ROOT must identify the repository root}"
topology="$root/tests/docker/wan-lab.clab.yml"
lab_dir="$root/tests/docker/clab-medtechwan"
ready_marker=/tmp/medtech-wan-ready

check_ownership() {
    local container owner containers network network_state
    containers="$(docker ps -aq --filter name='^/clab-medtechwan-')" || return 1
    if [[ -z "$containers" ]]; then
        echo "No topology-owned nodes found; inspect lab resources manually." >&2
        return 1
    fi
    while IFS= read -r container; do
        [[ -n "$container" ]] || continue
        owner="$(docker inspect --format '{{index .Config.Labels "clab-topo-file"}}' "$container")" || return 1
        if [[ "$owner" != "$topology" ]]; then
            echo "Container $container belongs to another topology; refusing cleanup." >&2
            return 1
        fi
    done <<< "$containers"
    network="$(docker network ls -q --filter name='^medtechwan-mgmt$')" || return 1
    if [[ -n "$network" ]]; then
        network_state="$(docker network inspect --format '{{index .Labels "containerlab"}} {{len .Containers}}' "$network")" || return 1
        if [[ "$network_state" != " 0" ]]; then
            echo "Unexpected lab network ownership or endpoints; refusing cleanup." >&2
            return 1
        fi
    fi
}

cleanup() {
    if [[ ! -d "$lab_dir" ]]; then
        echo "No lab directory found at $lab_dir; refusing cleanup." >&2
        return 1
    fi
    check_ownership || return 1
    containerlab destroy -t "$topology" --cleanup
}

if [[ $# != 1 || ! "$1" =~ ^(run|ready|recover)$ ]]; then
    echo "Usage: wan-lab.sh {run|ready|recover}" >&2
    exit 2
fi

docker info >/dev/null

if [[ "$1" == ready ]]; then
    [[ -f "$ready_marker" ]] || exit 1
    for node in edge-a nat-a internet nat-b edge-b cloud; do
        name="clab-medtechwan-$node"
        state="$(docker inspect --format '{{.State.Running}} {{index .Config.Labels "clab-topo-file"}}' "$name")"
        [[ "$state" == "true $topology" ]] || exit 1
    done
    exit 0
fi

if [[ "$1" == recover ]]; then
    cleanup
    exit
fi

if [[ "${RTI_LICENSE_FILE:-}" != /* || ! -f "$RTI_LICENSE_FILE" ]]; then
    echo "Set RTI_LICENSE_FILE to an existing absolute license path." >&2
    exit 1
fi
containers="$(docker ps -aq --filter name='^/clab-medtechwan-')"
network="$(docker network ls -q --filter name='^medtechwan-mgmt$')"
if [[ -e "$lab_dir" || -n "$network" || -n "$containers" ]]; then
    echo "Lab resources already exist; inspect them before deployment." >&2
    exit 1
fi

finish() {
    result=$?
    trap - EXIT
    rm -f "$ready_marker"
    if [[ -d "$lab_dir" ]]; then
        cleanup || result=1
    else
        if ! network="$(docker network ls -q --filter name='^medtechwan-mgmt$')"; then
            echo "Unable to check for remaining lab network." >&2
            result=1
        elif [[ -n "$network" ]]; then
            echo "Lab network remains but its directory is missing; inspect it manually." >&2
            result=1
        fi
    fi
    exit "$result"
}
trap finish EXIT
trap 'exit 0' INT TERM

containerlab deploy -t "$topology" --skip-labdir-acl
touch "$ready_marker"
sleep infinity &
wait "$!"
