# Phase 1: Research Notes

## 1.1 HL7/MLLP Analyzer Assessment

### Existing analyzers

TODO: Search packages.zeek.org and GitHub for HL7/MLLP analyzers.

### Custom analysis paths

**Zeek scripting (`tcp_contents` event):**

TODO: Evaluate feasibility of detecting MLLP framing (0x0B...0x1C0D) via raw
TCP payload analysis in a .zeek script.

**Spicy analyzer:**

TODO: Evaluate effort for a declarative MLLP grammar in Spicy.

---

## 1.2 Zeek Logs vs. BlueFlow Asset Fields

| Zeek Log | BlueFlow Field(s) | Assessment |
|---|---|---|
| `conn.log` | `ip_address`, `open_ports_tcp`, topology edges | TODO |
| `dns.log` | `hostname` | TODO |
| `dhcp.log` | MAC-IP binding | TODO — can this replace tshark? |
| `ssl.log` | `manufacturer`, cert-based device ID | TODO |
| `known_hosts.log` | Entity resolution | TODO |
| `known_services.log` | Service fingerprinting | TODO |

---

## 1.3 Deployment Viability

### Resource footprint

TODO: Document CPU/memory/disk for ~500-device network.

### Installation paths

TODO: Evaluate apt, brew, Docker.

### Operational complexity

TODO: Compare Zeek daemon model vs. tcpflow periodic invocation.

### Single-box deployment

TODO: Can Zeek coexist on the same VM as BlueFlow?

### Licensing

Zeek is BSD-licensed — compatible with BlueFlow's deployment model.
