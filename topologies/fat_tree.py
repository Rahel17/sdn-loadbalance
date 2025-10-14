from mininet.topo import Topo

class FatTreeTopo(Topo):
    def build(self, k=4):
        # Hitung jumlah perangkat
        core_switches = (k // 2) ** 2
        agg_switches = k * (k // 2)
        edge_switches = k * (k // 2)
        hosts = (k ** 3) // 4

        core, aggr, edge, host = [], [], [], []

        # Core layer
        for i in range(core_switches):
            sw = self.addSwitch(f'c{i+1}')
            core.append(sw)

        # Aggregation layer
        for i in range(agg_switches):
            sw = self.addSwitch(f'a{i+1}')
            aggr.append(sw)

        # Edge layer
        for i in range(edge_switches):
            sw = self.addSwitch(f'e{i+1}')
            edge.append(sw)

        # Host layer (dengan label server/client)
        for i in range(hosts):
            if i < 6:
                h = self.addHost(f'h{i+1}', ip=f'10.0.0.{i+1}', role='server')
            else:
                h = self.addHost(f'h{i+1}', ip=f'10.0.0.{i+1}', role='client')
            host.append(h)

        # Bangun koneksi antar layer
        pods = k
        half = k // 2

        # Edge ↔ Host
        for p in range(pods):
            for e in range(half):
                edge_index = p * half + e
                for h in range(half):
                    host_index = edge_index * half + h
                    self.addLink(edge[edge_index], host[host_index])

        # Aggregation ↔ Edge
        for p in range(pods):
            for a in range(half):
                agg_index = p * half + a
                for e in range(half):
                    edge_index = p * half + e
                    self.addLink(aggr[agg_index], edge[edge_index])

        # Core ↔ Aggregation
        for a in range(agg_switches):
            group = a // half
            for c in range(half):
                core_index = c * half + (a % half)
                self.addLink(core[core_index], aggr[a])

# Agar bisa dipanggil lewat Mininet
topos = {
    'fattree': (lambda: FatTreeTopo(k=4))
}
