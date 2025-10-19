from mininet.topo import Topo

class FatTree(Topo):
    """
    Fat-tree topology for k=4 (supports 16 hosts, 20 switches)
    4 pods, each pod has 2 aggregation + 2 edge switches
    4 core switches connect all pods
    """

    def __init__(self, k=4):
        super(FatTree, self).__init__()

        core_switches = []
        agg_switches = []
        edge_switches = []
        hosts = []

        # Create core switches
        for i in range(int((k / 2) ** 2)):
            core = self.addSwitch('s{}'.format(i + 1))
            core_switches.append(core)

        # Create aggregation and edge switches + hosts
        sw_id = len(core_switches)
        for pod in range(k):
            agg_per_pod = []
            edge_per_pod = []

            # aggregation switches
            for a in range(int(k / 2)):
                sw_id += 1
                agg = self.addSwitch('s{}'.format(sw_id))
                agg_per_pod.append(agg)
                agg_switches.append(agg)

            # edge switches
            for e in range(int(k / 2)):
                sw_id += 1
                edge = self.addSwitch('s{}'.format(sw_id))
                edge_per_pod.append(edge)
                edge_switches.append(edge)

            # connect edge to aggregation
            for edge in edge_per_pod:
                for agg in agg_per_pod:
                    self.addLink(edge, agg)

            # connect hosts to edge
            for e, edge in enumerate(edge_per_pod):
                for h in range(int(k / 2)):
                    host_id = len(hosts) + 1
                    host = self.addHost('h{}'.format(host_id), ip='10.0.0.{}'.format(host_id))
                    hosts.append(host)
                    self.addLink(edge, host)

        # connect aggregation to core
        core_per_pod = int(k / 2)
        for pod in range(k):
            for a in range(int(k / 2)):
                agg = agg_switches[pod * int(k / 2) + a]
                for c in range(core_per_pod):
                    core = core_switches[a * core_per_pod + c]
                    self.addLink(agg, core)


topos = {'fattree': (lambda: FatTree())}
