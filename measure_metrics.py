#!/usr/bin/env python3
"""
Test script untuk membandingkan WRR dan WLC load balancing
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink
import time
import sys

def test_load_balancing(controller_name="wrr"):
    """
    Test load balancing dengan traffic generation
    
    Args:
        controller_name: "wrr" atau "wlc"
    """
    
    info(f"\n*** Testing {controller_name.upper()} Load Balancing ***\n")
    
    # Load topology
    from topologies.fat_tree_fixed import FatTreeFixed
    
    topo = FatTreeFixed(k=4)
    
    # Create network with remote controller
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(
            name, ip='127.0.0.1', port=6653
        ),
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True
    )
    
    info("*** Starting network\n")
    net.start()
    
    info("*** Waiting for controller to install flows...\n")
    time.sleep(5)
    
    # Test 1: Basic connectivity
    info("\n*** Test 1: Basic Connectivity (pingall) ***\n")
    loss = net.pingAll()
    info(f"Packet loss: {loss}%\n")
    
    if loss > 0:
        info("WARNING: Network has connectivity issues!\n")
    
    # Test 2: Ping test antar pod
    info("\n*** Test 2: Cross-pod Latency Test ***\n")
    h1 = net.get('h1')
    h5 = net.get('h5')
    h9 = net.get('h9')
    h13 = net.get('h13')
    
    for dst_host in [h5, h9, h13]:
        result = h1.cmd(f'ping -c 10 {dst_host.IP()}')
        info(f"h1 -> {dst_host.name}: ")
        # Extract avg latency
        lines = result.split('\n')
        for line in lines:
            if 'rtt min/avg/max' in line:
                info(line + '\n')
                break
    
    # Test 3: Bandwidth test dengan iperf
    info("\n*** Test 3: Bandwidth Test (iperf) ***\n")
    
    # Start iperf servers pada beberapa host
    info("Starting iperf servers...\n")
    h5.cmd('iperf -s &')
    h9.cmd('iperf -s &')
    h13.cmd('iperf -s &')
    time.sleep(2)
    
    # Run iperf clients
    info("Running iperf clients...\n")
    
    info("h1 -> h5: ")
    result = h1.cmd(f'iperf -c {h5.IP()} -t 5')
    for line in result.split('\n'):
        if 'Mbits/sec' in line:
            info(line.strip() + '\n')
            break
    
    info("h2 -> h9: ")
    h2 = net.get('h2')
    result = h2.cmd(f'iperf -c {h9.IP()} -t 5')
    for line in result.split('\n'):
        if 'Mbits/sec' in line:
            info(line.strip() + '\n')
            break
    
    # Test 4: Concurrent connections
    info("\n*** Test 4: Concurrent Connections Test ***\n")
    info("Starting 4 concurrent iperf flows...\n")
    
    h1.cmd(f'iperf -c {h5.IP()} -t 10 &')
    h2.cmd(f'iperf -c {h9.IP()} -t 10 &')
    h3 = net.get('h3')
    h3.cmd(f'iperf -c {h13.IP()} -t 10 &')
    h4 = net.get('h4')
    h7 = net.get('h7')
    h4.cmd(f'iperf -c {h7.IP()} -t 10 &')
    
    time.sleep(12)
    info("Concurrent test completed\n")
    
    # Test 5: Check flow distribution
    info("\n*** Test 5: Flow Distribution Analysis ***\n")
    info("Checking flow statistics on switches...\n")
    
    # Check edge switch s13
    info("\nEdge Switch s13 (e1) flows:\n")
    result = net.get('s13').cmd('ovs-ofctl dump-flows s13 -O OpenFlow13')
    for line in result.split('\n'):
        if 'n_packets' in line and 'priority=10' in line:
            info(line + '\n')
    
    # Check agg switch s5
    info("\nAgg Switch s5 (a1) flows:\n")
    result = net.get('s5').cmd('ovs-ofctl dump-flows s5 -O OpenFlow13')
    for line in result.split('\n'):
        if 'n_packets' in line and 'priority=10' in line:
            info(line + '\n')
    
    # Interactive CLI for manual testing
    info("\n*** Entering CLI for manual testing ***\n")
    info("Commands you can try:\n")
    info("  - iperf h1 h5\n")
    info("  - h1 ping -c 100 h5\n")
    info("  - sh ovs-ofctl dump-flows s13 -O OpenFlow13\n")
    info("  - xterm h1 h5 (for tcpdump)\n\n")
    
    CLI(net)
    
    # Cleanup
    info("*** Stopping network\n")
    net.stop()


def compare_algorithms():
    """
    Compare WRR and WLC algorithms
    """
    info("\n" + "="*60 + "\n")
    info("Load Balancing Algorithm Comparison\n")
    info("="*60 + "\n\n")
    
    info("This script will help you compare:\n")
    info("1. Weighted Round Robin (WRR)\n")
    info("2. Weighted Least Connection (WLC)\n\n")
    
    info("Steps:\n")
    info("1. Start the controller in a separate terminal:\n")
    info("   For WRR: ryu-manager --ofp-tcp-listen-port 6653 weighted_round_robin_controller.py --verbose\n")
    info("   For WLC: ryu-manager --ofp-tcp-listen-port 6653 weighted_least_connection_controller.py --verbose\n\n")
    info("2. Run this script with the controller name:\n")
    info("   sudo python3 test_load_balancing.py wrr\n")
    info("   sudo python3 test_load_balancing.py wlc\n\n")
    
    info("Key Differences:\n")
    info("- WRR: Fixed round-robin sequence based on weights\n")
    info("      Best for: Uniform traffic, known link capacities\n")
    info("      Pro: Simple, predictable\n")
    info("      Con: Doesn't adapt to actual load\n\n")
    
    info("- WLC: Dynamic selection based on active connections\n")
    info("      Best for: Variable traffic, long-lived connections\n")
    info("      Pro: Adaptive, considers actual load\n")
    info("      Con: More complex, slight overhead\n\n")


if __name__ == '__main__':
    setLogLevel('info')
    
    if len(sys.argv) < 2:
        compare_algorithms()
        sys.exit(0)
    
    controller = sys.argv[1].lower()
    
    if controller not in ['wrr', 'wlc']:
        info("Error: Controller must be 'wrr' or 'wlc'\n")
        info("Usage: sudo python3 test_load_balancing.py [wrr|wlc]\n")
        sys.exit(1)
    
    test_load_balancing(controller)