"""
TopologyGraphBuilder

Converts a list of raw asset dicts into a TopologyGraph.

Pipeline
--------
1. Parse each asset dict → extract fields, normalise MAC, derive subnet.
2. Build TopologyNode per asset (interfaces, subnets — no edges yet).
3. Infer directed edges via subnet + port-reachability rule:
      For each ordered pair (A, B) sharing a subnet:
        For each service S exposed on B's open ports:
          If A's device class initiates S (or initiates "*"):
            emit outbound edge A→B and inbound edge B←A

Output
------
TopologyGraph with all nodes populated and edges wired bidirectionally
(outbound on A, inbound on B).
"""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from typing import Any

from .models import NetworkInterface, ServiceEdge, TopologyGraph, TopologyNode
from .registries import get_initiated_services, resolve_port


class TopologyGraphBuilder:

    def __init__(self, subnet_prefix_len: int = 24) -> None:
        self._prefix_len = subnet_prefix_len

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def build(self, assets: list[dict[str, Any]]) -> TopologyGraph:
        """
        Build and return a TopologyGraph from a list of raw asset dicts.
        """
        nodes = self._parse_nodes(assets)
        self._infer_edges(nodes)

        all_subnets = sorted({
            sub
            for node in nodes.values()
            for sub in node.subnets
        })

        graph = TopologyGraph(nodes=nodes, subnets=all_subnets)
        return graph

    # ──────────────────────────────────────────────────────────
    # Step 1 — Parse raw assets into TopologyNodes
    # ──────────────────────────────────────────────────────────

    def _parse_nodes(
        self, assets: list[dict[str, Any]]
    ) -> dict[str, TopologyNode]:
        nodes: dict[str, TopologyNode] = {}
        seen_macs: set[str] = set()
        for asset in assets:
            mac = self._resolve_mac(asset)
            if mac in seen_macs:
                continue
            seen_macs.add(mac)
            nodes[mac] = self._build_node(mac, asset)
        return nodes

    def _resolve_mac(self, asset: dict[str, Any]) -> str:
        """Return a normalised MAC for the asset, synthesising one from IP if absent."""
        mac = self._normalise_mac(str(asset.get("mac_address") or ""))
        if mac:
            return mac
        ip = str(asset.get("ip_address") or "0.0.0.0")
        return "00:00:" + ":".join(f"{int(o):02x}" for o in ip.split("."))

    def _build_node(self, mac: str, asset: dict[str, Any]) -> TopologyNode:
        """Construct a TopologyNode from a resolved MAC and raw asset dict."""
        ip_str    = str(asset.get("ip_address") or "0.0.0.0")
        subnet    = self._derive_subnet(ip_str)
        interface = NetworkInterface(mac=mac, ip=ip_str, subnet=subnet)
        open_ports: list[int] = [int(p) for p in (asset.get("open_ports") or [])]
        node = TopologyNode(
            node_id=mac,
            hostname=str(asset.get("hostname")     or ip_str),
            vendor=str(asset.get("vendor")         or "unknown"),
            product=str(asset.get("product")       or "unknown"),
            version=str(asset.get("version")       or ""),
            device_class=str(asset.get("device_class") or "unknown"),
            interfaces=[interface],
            subnets=[subnet],
        )
        node.__dict__["_open_ports"] = open_ports
        return node

    # ──────────────────────────────────────────────────────────
    # Step 2 — Infer directed edges
    # ──────────────────────────────────────────────────────────

    def _infer_edges(self, nodes: dict[str, TopologyNode]) -> None:
        by_subnet    = self._build_subnet_index(nodes)
        service_index = self._build_service_index(nodes)
        seen_edges: set[tuple[str, str, int]] = set()

        for subnet_nodes in by_subnet.values():
            for src in subnet_nodes:
                initiated = get_initiated_services(src.device_class)
                wildcard  = "*" in initiated
                for dst in subnet_nodes:
                    if src.node_id == dst.node_id:
                        continue
                    self._emit_edges(
                        src, dst, service_index[dst.node_id],
                        wildcard, initiated, seen_edges,
                    )

    def _build_subnet_index(
        self, nodes: dict[str, TopologyNode]
    ) -> dict[str, list[TopologyNode]]:
        by_subnet: dict[str, list[TopologyNode]] = defaultdict(list)
        for node in nodes.values():
            for subnet in node.subnets:
                by_subnet[subnet].append(node)
        return by_subnet

    def _build_service_index(
        self, nodes: dict[str, TopologyNode]
    ) -> dict[str, dict[str, tuple[int, str]]]:
        """Build a per-node map of service_name → (port, protocol)."""
        return {
            node.node_id: self._index_node_services(node)
            for node in nodes.values()
        }

    def _index_node_services(
        self, node: TopologyNode
    ) -> dict[str, tuple[int, str]]:
        """Map each open port on a node to its service name and protocol."""
        svc_map: dict[str, tuple[int, str]] = {}
        for port in node.__dict__.get("_open_ports", []):
            resolved = resolve_port(port)
            svc_name, proto = resolved if resolved else (f"port_{port}", "tcp")
            svc_map.setdefault(svc_name, (port, proto))
        return svc_map

    def _emit_edges(
        self,
        src: TopologyNode,
        dst: TopologyNode,
        dst_services: dict[str, tuple[int, str]],
        wildcard: bool,
        initiated: set[str],
        seen_edges: set[tuple[str, str, int]],
    ) -> None:
        """Emit outbound/inbound ServiceEdge pairs for all matching services."""
        for svc_name, (port, proto) in dst_services.items():
            if not wildcard and svc_name not in initiated:
                continue
            edge_key = (src.node_id, dst.node_id, port)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            src.outbound.append(ServiceEdge(
                peer_node=dst.node_id, port=port, service=svc_name,
                protocol=proto,  # type: ignore[arg-type]
            ))
            dst.inbound.append(ServiceEdge(
                peer_node=src.node_id, port=port, service=svc_name,
                protocol=proto,  # type: ignore[arg-type]
            ))

    # ──────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────

    def _derive_subnet(self, ip: str) -> str:
        try:
            iface = ipaddress.ip_interface(f"{ip}/{self._prefix_len}")
            return str(iface.network)
        except ValueError:
            return f"unknown/{self._prefix_len}"

    @staticmethod
    def _normalise_mac(mac: str) -> str:
        """Normalise MAC to lowercase colon-separated form."""
        # Strip separators and reformat
        digits = mac.replace(":", "").replace("-", "").replace(".", "").lower()
        if len(digits) != 12 or not all(c in "0123456789abcdef" for c in digits):
            return ""
        return ":".join(digits[i:i+2] for i in range(0, 12, 2))
