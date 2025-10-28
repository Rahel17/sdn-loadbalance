from mininet.topo import Topo

class FatTreeFixed(Topo):
    def build(self, k=4):
        pods = k
        half = k // 2
        core_switches = (half) ** 2
        agg_switches = k * half
        edge_switches = k * half
        hosts = (k ** 3) // 4

        core, aggr, edge, host = [], [], [], []

        print("\n=== Creating Switches with explicit DPID ===")

        # === Core Layer (DPID 1-4) ===
        for i in range(core_switches):
            dpid_hex = format(i + 1, '016x')  # Convert to 16-digit hex
            sw = self.addSwitch(f's{i+1}', dpid=dpid_hex)
            core.append(sw)
            print(f"Core: s{i+1} (c{i+1}) = DPID {i+1}")

        # === Aggregation Layer (DPID 5-12) ===
        for i in range(agg_switches):
            dpid = i + 5
            dpid_hex = format(dpid, '016x')
            sw = self.addSwitch(f's{dpid}', dpid=dpid_hex)
            aggr.append(sw)
            print(f"Agg: s{dpid} (a{i+1}) = DPID {dpid}")

        # === Edge Layer (DPID 13-20) ===
        for i in range(edge_switches):
            dpid = i + 13
            dpid_hex = format(dpid, '016x')
            sw = self.addSwitch(f's{dpid}', dpid=dpid_hex)
            edge.append(sw)
            print(f"Edge: s{dpid} (e{i+1}) = DPID {dpid}")

        # === Host Layer ===
        print("\n=== Creating Hosts ===")
        for i in range(hosts):
            mac = f'00:00:00:00:00:{format(i+1, "02x")}'
            h = self.addHost(f'h{i+1}', 
                           ip=f'10.0.0.{i+1}/24',
                           mac=mac)
            host.append(h)
            print(f"Host: h{i+1} = IP 10.0.0.{i+1}, MAC {mac}")

        print("\n=== Building Links ===")

        # === Edge ↔ Host Links ===
        # Each edge connects to 2 hosts
        for e_idx in range(edge_switches):
            for h_offset in range(half):
                host_idx = e_idx * half + h_offset
                self.addLink(edge[e_idx], host[host_idx])
                print(f"Link: s{e_idx+13} (e{e_idx+1}) port {h_offset+1} <-> h{host_idx+1}")

        # === Aggregation ↔ Edge Links ===
        # Each pod has 2 agg and 2 edge switches
        for pod in range(pods):
            for a_offset in range(half):
                agg_idx = pod * half + a_offset
                for e_offset in range(half):
                    edge_idx = pod * half + e_offset
                    self.addLink(aggr[agg_idx], edge[edge_idx])
                    print(f"Link: s{agg_idx+5} (a{agg_idx+1}) <-> s{edge_idx+13} (e{edge_idx+1})")

        # === Core ↔ Aggregation Links ===
        for c_idx in range(core_switches):
            core_col = c_idx % half
            for pod in range(pods):
                aggr_idx = pod * half + core_col
                self.addLink(core[c_idx], aggr[aggr_idx])
                print(f"Link: s{c_idx+1} (c{c_idx+1}) <-> s{aggr_idx+5} (a{aggr_idx+1})")

        print("\n=== Topology Summary ===")
        print(f"DPID 1-4: Core switches (c1-c4)")
        print(f"DPID 5-12: Aggregation switches (a1-a8)")
        print(f"DPID 13-20: Edge switches (e1-e8)")
        print(f"Total: {len(core)} core, {len(aggr)} agg, {len(edge)} edge, {len(host)} hosts")

topos = {'fattree': (lambda: FatTreeFixed(k=4))}