from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
import time
import json


class AlgorithmVerifier:
    """Verify load balancing algorithm correctness"""
    
    def __init__(self, algorithm="wrr"):
        self.algorithm = algorithm
        self.net = None
    
    def setup_network(self):
        """Setup Fat-Tree network"""
        info(f"\nSetting up network for {self.algorithm.upper()} verification...\n")
        
        from topologies.fat_tree_fixed import FatTreeFixed
        topo = FatTreeFixed(k=4)
        
        self.net = Mininet(
            topo=topo,
            controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6653),
            switch=OVSSwitch,
            link=TCLink,
            autoSetMacs=True
        )
        
        self.net.start()
        time.sleep(5)
        
        loss = self.net.pingAll()
        if loss > 0:
            info(f"WARNING: {loss}% packet loss!\n")
        else:
            info("Network ready\n")
    
    def cleanup(self):
        if self.net:
            self.net.stop()
    
    def check_weights_configured(self):
        """Check 1: Verify weights are configured in controller"""
        info("\n" + "="*70 + "\n")
        info("CHECK 1: Verifying Weight Configuration\n")
        info("="*70 + "\n")
        
        if self.algorithm == 'wrr':
            info("\nExpected WRR weights:\n")
            info("  Edge switches (s13-s20):\n")
            info("    - Port 3 (uplink to agg): weight = 3 (60%)\n")
            info("    - Port 4 (uplink to agg): weight = 2 (40%)\n")
            info("  Aggregation switches (s5-s12):\n")
            info("    - Port 3 (uplink to core): weight = 3 (60%)\n")
            info("    - Port 4 (uplink to core): weight = 2 (40%)\n")
            info("\nSequence should be: [3, 3, 3, 4, 4] repeating\n")
        else:
            info("\nExpected WLC weights:\n")
            info("  Same weight configuration as WRR\n")
            info("  But distribution based on active connections, not round-robin\n")
            info("  Port with lower (connections/weight) ratio gets next flow\n")
        
        info("\nTo verify: Check controller logs for weight configuration\n")
        info("Result: MANUAL CHECK REQUIRED\n")
    
    def check_flow_distribution(self):
        """Check 2: Verify actual flow distribution matches weights"""
        info("\n" + "="*70 + "\n")
        info("CHECK 2: Verifying Flow Distribution\n")
        info("="*70 + "\n")
        
        info("\nRunning 20 test flows to check distribution...\n")
        
        # Run test flows
        flows_sent = 0
        for i in range(20):
            src_num = (i % 8) + 1
            dst_num = (i % 8) + 9
            src = self.net.get(f'h{src_num}')
            dst = self.net.get(f'h{dst_num}')
            
            # Start iperf server
            port = 6000 + i
            dst.popen(f'iperf3 -s -p {port}')
            time.sleep(0.2)
            
            # Send traffic (short duration)
            src.cmd(f'iperf3 -c {dst.IP()} -p {port} -t 2 -b 10M > /dev/null 2>&1 &')
            flows_sent += 1
            time.sleep(0.3)
        
        # Wait for flows to complete
        info(f"\nSent {flows_sent} flows. Waiting for completion...\n")
        time.sleep(5)
        
        # Check distribution on edge switches
        info("\nChecking flow distribution on edge switches:\n")
        info("-" * 70 + "\n")
        
        total_port3 = 0
        total_port4 = 0
        
        for switch_num in range(13, 21):
            switch_name = f's{switch_num}'
            switch = self.net.get(switch_name)
            
            # Get flow statistics
            result = switch.cmd(f'ovs-ofctl dump-flows {switch_name} -O OpenFlow13')
            
            port3_packets = 0
            port4_packets = 0
            port3_bytes = 0
            port4_bytes = 0
            
            for line in result.split('\n'):
                if 'priority=10' in line and 'n_packets=' in line:
                    try:
                        packets = int(line.split('n_packets=')[1].split(',')[0])
                        bytes_count = int(line.split('n_bytes=')[1].split(',')[0])
                        
                        if 'output:3' in line or ('output:"' in line and '-eth3"' in line):
                            port3_packets += packets
                            port3_bytes += bytes_count
                        elif 'output:4' in line or ('output:"' in line and '-eth4"' in line):
                            port4_packets += packets
                            port4_bytes += bytes_count
                    except:
                        pass
            
            total_port3 += port3_packets
            total_port4 += port4_packets
            
            if port3_packets > 0 or port4_packets > 0:
                total = port3_packets + port4_packets
                port3_pct = (port3_packets / total * 100) if total > 0 else 0
                port4_pct = (port4_packets / total * 100) if total > 0 else 0
                
                info(f"{switch_name}:\n")
                info(f"  Port 3: {port3_packets:6d} packets ({port3_pct:5.1f}%) - {port3_bytes:10d} bytes\n")
                info(f"  Port 4: {port4_packets:6d} packets ({port4_pct:5.1f}%) - {port4_bytes:10d} bytes\n")
        
        # Calculate overall distribution
        info("\n" + "-" * 70 + "\n")
        info("OVERALL DISTRIBUTION:\n")
        info("-" * 70 + "\n")
        
        total_packets = total_port3 + total_port4
        if total_packets > 0:
            port3_pct = (total_port3 / total_packets) * 100
            port4_pct = (total_port4 / total_packets) * 100
            
            info(f"Port 3 Total: {total_port3:8d} packets ({port3_pct:.1f}%)\n")
            info(f"Port 4 Total: {total_port4:8d} packets ({port4_pct:.1f}%)\n")
            info(f"\nExpected ratio: 60:40 (3:2)\n")
            info(f"Actual ratio:   {port3_pct:.1f}:{port4_pct:.1f}\n")
            
            # Verify if distribution is close to expected
            expected_port3 = 60.0
            expected_port4 = 40.0
            tolerance = 10.0  # Allow 10% deviation
            
            port3_ok = abs(port3_pct - expected_port3) <= tolerance
            port4_ok = abs(port4_pct - expected_port4) <= tolerance
            
            if port3_ok and port4_ok:
                info(f"\nResult: PASS - Distribution matches expected weights!\n")
                return True
            else:
                info(f"\nResult: FAIL - Distribution deviates from expected weights!\n")
                info(f"  Port 3 deviation: {abs(port3_pct - expected_port3):.1f}%\n")
                info(f"  Port 4 deviation: {abs(port4_pct - expected_port4):.1f}%\n")
                return False
        else:
            info("Result: FAIL - No traffic detected!\n")
            return False
    
    def check_wrr_sequence(self):
        """Check 3: Verify WRR sequence pattern (WRR only)"""
        if self.algorithm != 'wrr':
            return
        
        info("\n" + "="*70 + "\n")
        info("CHECK 3: Verifying WRR Sequence Pattern\n")
        info("="*70 + "\n")
        
        info("\nExpected WRR sequence: [3, 3, 3, 4, 4]\n")
        info("This means:\n")
        info("  Flow 1 -> Port 3\n")
        info("  Flow 2 -> Port 3\n")
        info("  Flow 3 -> Port 3\n")
        info("  Flow 4 -> Port 4\n")
        info("  Flow 5 -> Port 4\n")
        info("  Flow 6 -> Port 3 (cycle repeats)\n")
        info("  ...\n")
        
        info("\nRunning 10 sequential flows to verify sequence...\n")
        
        # Clear existing flows first
        for switch_num in range(13, 21):
            switch_name = f's{switch_num}'
            switch = self.net.get(switch_name)
            switch.cmd(f'ovs-ofctl del-flows {switch_name} -O OpenFlow13 priority=10')
        
        time.sleep(2)
        
        # Send flows one by one
        for i in range(10):
            src = self.net.get('h1')
            dst = self.net.get('h9')
            port = 7000 + i
            
            # Start server
            dst.popen(f'iperf3 -s -p {port}')
            time.sleep(0.2)
            
            # Send single packet/short flow
            src.cmd(f'iperf3 -c {dst.IP()} -p {port} -t 1 -b 1M > /dev/null 2>&1')
            
            info(f"  Flow {i+1} sent\n")
            time.sleep(0.5)
        
        info("\nCheck controller logs for flow routing decisions\n")
        info("Look for messages like: '[WRR] Switch X: Flow Y via port Z'\n")
        info("\nResult: CHECK CONTROLLER LOGS\n")
    
    def check_wlc_connection_tracking(self):
        """Check 4: Verify WLC connection tracking (WLC only)"""
        if self.algorithm != 'wlc':
            return
        
        info("\n" + "="*70 + "\n")
        info("CHECK 4: Verifying WLC Connection Tracking\n")
        info("="*70 + "\n")
        
        info("\nWLC should:\n")
        info("  1. Track active connections per port\n")
        info("  2. Calculate score = connections / weight\n")
        info("  3. Route to port with LOWEST score\n")
        info("\nExample:\n")
        info("  Port 3: 2 connections, weight=3 -> score = 0.67\n")
        info("  Port 4: 1 connection, weight=2 -> score = 0.50 (WINNER!)\n")
        info("  Next flow -> Port 4\n")
        
        info("\nRunning test with sequential flows...\n")
        
        # Start long-lived flows
        info("\nStarting 3 long-lived flows (elephants)...\n")
        elephants = []
        for i in range(3):
            src = self.net.get(f'h{i+1}')
            dst = self.net.get(f'h{i+9}')
            port = 8000 + i
            
            dst.popen(f'iperf3 -s -p {port}')
            time.sleep(0.2)
            
            proc = src.popen(f'iperf3 -c {dst.IP()} -p {port} -t 30 -b 50M')
            elephants.append(proc)
            info(f"  Elephant {i+1} started (h{i+1} -> h{i+9})\n")
            time.sleep(2)
        
        # Send short flows (mice)
        info("\nSending 5 short flows (mice)...\n")
        for i in range(5):
            src = self.net.get('h4')
            dst = self.net.get('h12')
            port = 8100 + i
            
            dst.popen(f'iperf3 -s -p {port}')
            time.sleep(0.2)
            
            src.cmd(f'iperf3 -c {dst.IP()} -p {port} -t 2 -b 10M > /dev/null 2>&1')
            info(f"  Mouse {i+1} sent\n")
            time.sleep(1)
        
        # Wait for elephants to finish
        info("\nWaiting for elephant flows to complete...\n")
        for proc in elephants:
            proc.wait()
        
        info("\nWLC should distribute mice flows to less loaded ports\n")
        info("Check controller logs for connection tracking messages\n")
        info("\nResult: CHECK CONTROLLER LOGS\n")
    
    def check_flow_table_rules(self):
        """Check 5: Verify flow table has correct rules"""
        info("\n" + "="*70 + "\n")
        info("CHECK 5: Verifying Flow Table Rules\n")
        info("="*70 + "\n")
        
        info("\nChecking edge switch s13 flow table...\n")
        switch = self.net.get('s13')
        result = switch.cmd('ovs-ofctl dump-flows s13 -O OpenFlow13')
        
        info("\nFlow table entries:\n")
        info("-" * 70 + "\n")
        
        flow_count = 0
        port3_flows = 0
        port4_flows = 0
        
        for line in result.split('\n'):
            if 'priority=10' in line and 'ipv4' in line:
                flow_count += 1
                
                # Truncate long lines
                if len(line) > 100:
                    display_line = line[:100] + "..."
                else:
                    display_line = line
                
                info(f"{display_line}\n")
                
                if 'output:3' in line:
                    port3_flows += 1
                elif 'output:4' in line:
                    port4_flows += 1
        
        info("-" * 70 + "\n")
        info(f"Total flows: {flow_count}\n")
        info(f"  Port 3: {port3_flows} flows\n")
        info(f"  Port 4: {port4_flows} flows\n")
        
        if flow_count > 0:
            port3_ratio = port3_flows / flow_count * 100
            port4_ratio = port4_flows / flow_count * 100
            info(f"\nFlow distribution:\n")
            info(f"  Port 3: {port3_ratio:.1f}%\n")
            info(f"  Port 4: {port4_ratio:.1f}%\n")
            
            if 50 <= port3_ratio <= 70:
                info(f"\nResult: PASS - Flow distribution looks correct\n")
            else:
                info(f"\nResult: WARNING - Flow distribution may be incorrect\n")
        else:
            info(f"\nResult: No active flows found\n")
    
    def run_all_checks(self):
        """Run all verification checks"""
        info("\n" + "="*70 + "\n")
        info(f"ALGORITHM VERIFICATION: {self.algorithm.upper()}\n")
        info("="*70 + "\n")
        
        info("\nThis tool will verify:\n")
        info("  1. Weight configuration\n")
        info("  2. Flow distribution matches weights (3:2 ratio)\n")
        info("  3. WRR sequence pattern (if WRR)\n")
        info("  4. WLC connection tracking (if WLC)\n")
        info("  5. Flow table rules\n")
        
        input("\nPress Enter to start verification...")
        
        try:
            self.setup_network()
            
            # Run checks
            self.check_weights_configured()
            distribution_ok = self.check_flow_distribution()
            
            if self.algorithm == 'wrr':
                self.check_wrr_sequence()
            else:
                self.check_wlc_connection_tracking()
            
            self.check_flow_table_rules()
            
            # Summary
            info("\n" + "="*70 + "\n")
            info("VERIFICATION SUMMARY\n")
            info("="*70 + "\n")
            
            if distribution_ok:
                info("\nPrimary Check: PASSED\n")
                info("  Flow distribution matches expected weights (60:40)\n")
                info(f"  {self.algorithm.upper()} algorithm is working correctly!\n")
            else:
                info("\nPrimary Check: FAILED\n")
                info("  Flow distribution does NOT match expected weights\n")
                info("  Possible issues:\n")
                info("  1. Controller not running\n")
                info("  2. Wrong controller loaded\n")
                info("  3. Weights not configured correctly\n")
                info("  4. Flow timeout too short\n")
            
            info("\nAdditional checks require manual verification of:\n")
            info("  - Controller logs\n")
            info("  - Flow table entries\n")
            info("\n")
            
        finally:
            self.cleanup()


def main():
    import sys
    
    if len(sys.argv) < 2:
        info("\nUsage: sudo python3 verify_algorithm.py [wrr|wlc]\n")
        info("\nExample:\n")
        info("  sudo python3 verify_algorithm.py wrr\n")
        info("  sudo python3 verify_algorithm.py wlc\n")
        sys.exit(1)
    
    algorithm = sys.argv[1].lower()
    
    if algorithm not in ['wrr', 'wlc']:
        info("Error: Algorithm must be 'wrr' or 'wlc'\n")
        sys.exit(1)
    
    info("\nIMPORTANT: Make sure the correct controller is running!\n")
    if algorithm == 'wrr':
        info("Command: ryu-manager --ofp-tcp-listen-port 6653 controllers/weighted_round_robin_controller.py --verbose\n")
    else:
        info("Command: ryu-manager --ofp-tcp-listen-port 6653 controllers/weighted_least_connection_controller.py --verbose\n")
    
    input("\nPress Enter when controller is ready...")
    
    verifier = AlgorithmVerifier(algorithm)
    verifier.run_all_checks()


if __name__ == '__main__':
    setLogLevel('info')
    main()