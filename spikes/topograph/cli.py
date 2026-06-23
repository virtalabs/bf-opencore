"""
CLI for building topology graphs from fixture asset files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import TopologyGraphBuilder
from .models import TopologyGraph
from .visualize import render_html


def load_assets(assets_path: Path) -> list[dict[str, Any]]:
    if not assets_path.is_file():
        print(f"error: assets file not found: {assets_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(assets_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in {assets_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print(f"error: expected a JSON array in {assets_path}", file=sys.stderr)
        sys.exit(1)

    return data


def _group_by_peer(edges: list) -> dict[str, list[str]]:
    """Group edge service labels by peer node ID."""
    groups: dict[str, list[str]] = {}
    for e in edges:
        groups.setdefault(e.peer_node, []).append(
            f"{e.service}:{e.port}/{e.protocol}"
        )
    return groups


def _print_edge_section(
    label: str,
    arrow: str,
    edges: list,
    nodes: dict,
) -> None:
    if not edges:
        print(f"  │  {label}: (none)")
        return
    peers = _group_by_peer(edges)
    print(f"  │  {label} ({len(edges)} edges):")
    for peer_mac, svcs in peers.items():
        peer = nodes[peer_mac]
        print(f"  │    {arrow} {peer.hostname}  [{', '.join(svcs)}]")


def print_summary(graph: TopologyGraph) -> None:
    print(f"\n{'═'*62}")
    print(f"  Topology Graph — {len(graph.nodes)} nodes, "
          f"{len(graph.subnets)} subnet(s)")
    print(f"{'═'*62}")
    print(f"  Subnets: {', '.join(graph.subnets)}")
    print()

    for node in graph.nodes.values():
        iface = node.interfaces[0]
        print(f"  ┌─ {node.hostname}  [{node.device_class}]")
        print(f"  │  node_id : {node.node_id}")
        print(f"  │  ip/mac  : {iface.ip}  /  {iface.mac}")
        print(f"  │  subnet  : {iface.subnet}")
        print(f"  │  vendor  : {node.vendor}  {node.product}  {node.version}")
        _print_edge_section("outbound", "→", node.outbound, graph.nodes)
        _print_edge_section("inbound ", "←", node.inbound,  graph.nodes)
        print(f"  └{'─'*58}")

    total_edges = sum(len(n.outbound) for n in graph.nodes.values())
    print(f"\n  Total directed edges: {total_edges}")
    print(f"{'═'*62}\n")


def run(assets_path: Path, subnet_prefix_len: int = 24) -> None:
    assets = load_assets(assets_path)
    results_dir = assets_path.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    graph = TopologyGraphBuilder(subnet_prefix_len=subnet_prefix_len).build(assets)
    print_summary(graph)

    json_path = results_dir / "topology_graph.json"
    html_path = results_dir / "topology_graph.html"

    json_path.write_text(json.dumps(graph.to_dict(), indent=2))
    html_path.write_text(render_html(graph))

    print(f"  JSON written to {json_path}")
    print(f"  HTML written to {html_path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build a topology graph from a fixture assets.json file.",
    )
    parser.add_argument(
        "assets_path",
        type=Path,
        help="Path to assets.json (e.g. topograph/fixtures/topology/demo1/assets.json)",
    )
    parser.add_argument(
        "--prefix-len",
        type=int,
        default=24,
        dest="subnet_prefix_len",
        help="Subnet prefix length for IP-to-CIDR derivation (default: 24)",
    )
    args = parser.parse_args(argv)
    run(args.assets_path.resolve(), subnet_prefix_len=args.subnet_prefix_len)
