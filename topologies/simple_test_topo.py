from mininet.topo import Topo

class SimpleTestTopo(Topo):
    """Simple linear topology to test basic connectivity"""
    
    def build(self):
        # Add switches with explicit DPID
        s1 = self.addSwitch('s1', dpid='0000000000000001')
        s2 = self.addSwitch('s2', dpid='0000000000000002')
        
        # Add hosts
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        h4 = self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')
        
        # Connect hosts to switches (NO LOOPS!)
        self.addLink(s1, h1)  # s1 port 1
        self.addLink(s1, h2)  # s1 port 2
        self.addLink(s2, h3)  # s2 port 1
        self.addLink(s2, h4)  # s2 port 2
        
        # Connect switches together
        self.addLink(s1, s2)  # s1 port 3 <-> s2 port 3

topos = {'simpletest': SimpleTestTopo}