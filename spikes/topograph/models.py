"""
Topology graph data models.

Design principles
-----------------
- A Node represents one physical/virtual device asset.
- Identity is MAC-anchored: the node_id is the primary MAC address.
- A device may have multiple NetworkInterface objects (one per NIC).
- A device is a member of one or more subnets (derived from interface IPs).
- Directed edges are encoded as inbound/outbound neighbor lists on each node.
- No security semantics: no CVEs, no TTPs, no access levels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Protocol = Literal["tcp", "udp"]
Direction = Literal["inbound", "outbound"]


@dataclass
class NetworkInterface:
    """
    A single network interface on a device.

    mac    : MAC address — the stable hardware identity (e.g. "00:17:23:AB:CD:EF")
    ip     : IPv4 address assigned to this interface
    subnet : CIDR network this interface belongs to (e.g. "10.0.1.0/24")
    """
    mac:    str
    ip:     str
    subnet: str

    def to_dict(self) -> dict[str, Any]:
        return {"mac": self.mac, "ip": self.ip, "subnet": self.subnet}


@dataclass
class ServiceEdge:
    """
    A directed communication edge between two nodes on a specific service.

    For outbound edges: peer_node is the destination.
    For inbound edges:  peer_node is the source.

    port     : destination port number
    service  : logical service name (e.g. "dicom", "http", "ssh")
    protocol : transport protocol
    """
    peer_node: str        # node_id (MAC) of the remote end
    port:      int
    service:   str
    protocol:  Protocol

    def to_dict(self) -> dict[str, Any]:
        return {
            "peer_node": self.peer_node,
            "port":      self.port,
            "service":   self.service,
            "protocol":  self.protocol,
        }


@dataclass
class TopologyNode:
    """
    A device node in the topology graph.

    node_id     : primary MAC address — stable, hardware-level identity
    hostname    : DNS hostname or asset label
    vendor      : hardware/software vendor
    product     : product name/model
    version     : firmware/software version
    device_class: semantic role (e.g. "patient_monitor", "gateway")
    interfaces  : list of network interfaces on this device
    subnets     : deduplicated list of subnet CIDRs this device is a member of
    inbound     : edges where remote assets initiate connections TO this node
    outbound    : edges where this node initiates connections TO remote assets
    """
    node_id:      str                        # primary MAC
    hostname:     str
    vendor:       str
    product:      str
    version:      str
    device_class: str
    interfaces:   list[NetworkInterface]    = field(default_factory=list)
    subnets:      list[str]                 = field(default_factory=list)
    inbound:      list[ServiceEdge]         = field(default_factory=list)
    outbound:     list[ServiceEdge]         = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id":      self.node_id,
            "hostname":     self.hostname,
            "vendor":       self.vendor,
            "product":      self.product,
            "version":      self.version,
            "device_class": self.device_class,
            "interfaces":   [i.to_dict() for i in self.interfaces],
            "subnets":      self.subnets,
            "inbound": [
                {
                    "from_node": e.peer_node,
                    "port":      e.port,
                    "service":   e.service,
                    "protocol":  e.protocol,
                }
                for e in self.inbound
            ],
            "outbound": [
                {
                    "to_node":  e.peer_node,
                    "port":     e.port,
                    "service":  e.service,
                    "protocol": e.protocol,
                }
                for e in self.outbound
            ],
        }


@dataclass
class TopologyGraph:
    """
    The complete topology graph: a collection of TopologyNode objects.

    nodes    : dict keyed by node_id (primary MAC)
    subnets  : all distinct subnet CIDRs present in the graph
    """
    nodes:   dict[str, TopologyNode]  = field(default_factory=dict)
    subnets: list[str]                = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subnets": self.subnets,
            "nodes":   [n.to_dict() for n in self.nodes.values()],
        }
