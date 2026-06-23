"""
HTML visualization for topology graphs using vis-network.
"""

from __future__ import annotations

import json
import math
from html import escape

from .models import TopologyGraph

VIS_NETWORK_CDN = (
    "https://unpkg.com/vis-network@9.1.9"
    "/standalone/umd/vis-network.min.js"
)

GROUP_COLORS = [
    "#4e79a7",
    "#f28e2b",
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#ff9da7",
]


def _layout_nodes(nodes: list[dict], subnets: list[str]) -> list[dict]:
    """Assign fixed x/y positions: one circle per subnet cluster."""
    by_group: dict[str, list[dict]] = {subnet: [] for subnet in subnets}
    for node in nodes:
        by_group.setdefault(node["group"], []).append(node)

    for cluster_index, subnet in enumerate(subnets):
        cluster = by_group.get(subnet, [])
        if not cluster:
            continue
        cx = cluster_index * 350
        cy = 0
        n = len(cluster)
        radius = 120 + 15 * n
        for i, node in enumerate(cluster):
            angle = (2 * math.pi * i) / n
            node["x"] = round(cx + radius * math.cos(angle))
            node["y"] = round(cy + radius * math.sin(angle))
            node["fixed"] = True

    return nodes


def _build_vis_data(graph: TopologyGraph) -> dict:
    nodes = []
    for node in graph.nodes.values():
        iface = node.interfaces[0]
        subnet = node.subnets[0] if node.subnets else iface.subnet
        title = (
            f"{node.hostname}\n"
            f"Class: {node.device_class}\n"
            f"IP: {iface.ip}\n"
            f"Subnet: {subnet}\n"
            f"Vendor: {node.vendor} {node.product}"
        )
        nodes.append({
            "id":    node.node_id,
            "label": node.hostname,
            "group": subnet,
            "title": title,
        })

    nodes = _layout_nodes(nodes, graph.subnets)

    # Collapse parallel edges: one arrow per (from, to) direction.
    grouped: dict[tuple[str, str], list[tuple[str, str, int]]] = {}
    seen_port: set[tuple[str, str, int]] = set()
    for node in graph.nodes.values():
        for e in node.outbound:
            key = (node.node_id, e.peer_node, e.port)
            if key in seen_port:
                continue
            seen_port.add(key)
            pair = (node.node_id, e.peer_node)
            grouped.setdefault(pair, []).append((e.service, e.protocol, e.port))

    edges = []
    for (src, dst), services in grouped.items():
        parts = sorted(f"{svc}:{port}" for svc, _proto, port in services)
        label = "{" + ", ".join(parts) + "}" if len(parts) > 1 else parts[0]
        title_lines = sorted(f"{svc} ({proto}/{port})" for svc, proto, port in services)
        edges.append({
            "from":   src,
            "to":     dst,
            "label":  label,
            "title":  "\n".join(title_lines),
            "arrows": "to",
        })

    return {"nodes": nodes, "edges": edges}


def _group_styles(subnets: list[str]) -> dict[str, dict[str, str]]:
    return {
        subnet: {
            "color": GROUP_COLORS[i % len(GROUP_COLORS)],
            "border": GROUP_COLORS[i % len(GROUP_COLORS)],
        }
        for i, subnet in enumerate(subnets)
    }


def render_html(graph: TopologyGraph) -> str:
    """Return a self-contained HTML document visualizing the topology graph."""
    vis_data = _build_vis_data(graph)
    node_count = len(graph.nodes)
    arrow_count = len(vis_data["edges"])
    subnet_count = len(graph.subnets)
    group_styles = _group_styles(graph.subnets)

    data_json = json.dumps(vis_data)
    groups_json = json.dumps(group_styles)
    subnets_html = "".join(
        f'<span class="legend-item">'
        f'<span class="swatch" style="background:{GROUP_COLORS[i % len(GROUP_COLORS)]}"></span>'
        f'{escape(subnet)}</span>'
        for i, subnet in enumerate(graph.subnets)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Topology Graph</title>
  <script src="{VIS_NETWORK_CDN}"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ height: 100%; overflow: hidden; }}
    body {{ font-family: system-ui, sans-serif; display: flex; flex-direction: column; height: 100vh; }}
    header {{
      background: #1e293b; color: #f8fafc; padding: 12px 20px;
      display: flex; flex-wrap: wrap; align-items: center; gap: 16px;
    }}
    header h1 {{ font-size: 1.1rem; font-weight: 600; }}
    .stats {{ font-size: 0.85rem; color: #94a3b8; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; font-size: 0.8rem; }}
    .legend-item {{ display: flex; align-items: center; gap: 6px; }}
    .swatch {{ width: 12px; height: 12px; border-radius: 2px; }}
    #network {{ flex: 1; min-height: 0; overflow: hidden; position: relative; background: #f8fafc; }}
  </style>
</head>
<body>
  <header>
    <h1>Network Topology</h1>
    <span class="stats">{node_count} nodes &middot; {arrow_count} arrows &middot; {subnet_count} subnet(s)</span>
    <div class="legend">{subnets_html}</div>
  </header>
  <div id="network"></div>
  <script>
    const data = {data_json};
    const groups = {groups_json};

    const container = document.getElementById("network");
    const viz = new vis.Network(container, data, {{
      groups: groups,
      nodes: {{
        shape: "dot",
        size: 18,
        font: {{ size: 13, color: "#1e293b" }},
        borderWidth: 2,
      }},
      edges: {{
        width: 1,
        font: {{ size: 10, align: "middle", color: "#64748b" }},
        color: {{ color: "#94a3b8", highlight: "#475569" }},
        smooth: {{ type: "continuous" }},
      }},
      physics: {{ enabled: false }},
      interaction: {{
        hover: true,
        tooltipDelay: 100,
        navigationButtons: true,
      }},
    }});
    viz.fit({{ animation: false }});
  </script>
</body>
</html>
"""
