#!/usr/bin/env python3
"""
Test script for Heterogeneous Traffic scenarios
Tests WRR and WLC with different traffic patterns
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
import time
import threading
import json
from datetime import datetime

class HeterogeneousTrafficTester:
    def __init__(self, algorithm="wrr"):
        self.algorithm = algorithm
        self.net = None
        self.results = {
            'scenario': '',
            'algorithm': algorithm,
            'flows': [],
            'start_time': '',
            'end_time': ''
        }
    
    def setup_network(self):
        """Setup Fat-Tree network"""
        info("\n*** Setting up Fat-Tree network ***\n")
        
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
        
        # Verify connectivity
        loss = self.net.pingAll()
        if loss > 0:
            info(f"WARNING: {loss}% packet loss in connectivity test!\n")
        else:
            info("✓ Network ready\n")
    
    def cleanup(self):
        """Cleanup network"""
        if self.net:
            self.net.stop()
    
    def run_flow(self, src_name, dst_name, bandwidth, duration, protocol='tcp', port=5001):
        """Run single iperf flow"""
        src = self.net.get(src_name)
        dst = self.net.get(dst_name)
        
        flow_id = f"{src_name}->{dst_name}"
        info(f"  Starting flow: {flow_id} ({bandwidth}, {duration}s, {protocol})\n")
        
        # Start server (use popen to avoid blocking)
        if protocol == 'tcp':
            dst.popen(f'iperf3 -s -p {port}')
        else:
            dst.popen(f'iperf3 -s -p {port}')
        
        time.sleep(1)  # Give server time to start
        
        # Start client (use popen for non-blocking execution)
        output_file = f'/tmp/iperf_{src_name}_{dst_name}_{port}.json'
        
        if protocol == 'tcp':
            client_proc = src.popen(
                f'iperf3 -c {dst.IP()} -p {port} -t {duration} -b {bandwidth} -J > {output_file}',
                shell=True
            )
        else:
            client_proc = src.popen(
                f'iperf3 -c {dst.IP()} -p {port} -u -t {duration} -b {bandwidth} -J > {output_file}',
                shell=True
            )
        
        # Wait for client to finish
        client_proc.wait()
        
        # Read results from file
        try:
            result = src.cmd(f'cat {output_file}')
            data = json.loads(result)
            
            if 'end' in data:
                if protocol == 'tcp':
                    throughput = data['end']['sum_received']['bits_per_second'] / 1e6
                else:
                    throughput = data['end']['sum']['bits_per_second'] / 1e6
                
                self.results['flows'].append({
                    'src': src_name,
                    'dst': dst_name,
                    'bandwidth_requested': bandwidth,
                    'throughput_achieved': throughput,
                    'duration': duration,
                    'protocol': protocol,
                    'port': port
                })
                info(f"    ✓ {flow_id}: {throughput:.2f} Mbps\n")
            else:
                info(f"    ✗ {flow_id}: No results in output\n")
        except Exception as e:
            info(f"    ✗ {flow_id}: Failed to parse results - {e}\n")
        
        # Cleanup
        src.cmd(f'rm -f {output_file}')
        dst.cmd(f'pkill -9 -f "iperf3 -s -p {port}"')
    
    # ========== SCENARIO 1: Mixed Bandwidth ==========
    def scenario_mixed_bandwidth(self):
        """
        Scenario 1: Mixed bandwidth workload
        - Heavy flows (100M)
        - Medium flows (10M)
        - Light flows (1M)
        - Very light flows (100K)
        """
        info("\n" + "="*60 + "\n")
        info("SCENARIO 1: Mixed Bandwidth Workload\n")
        info("="*60 + "\n")
        
        self.results['scenario'] = 'mixed_bandwidth'
        self.results['start_time'] = datetime.now().isoformat()
        
        flows = [
            # Heavy flows
            ('h1', 'h5', '100M', 60, 'tcp', 5001),
            ('h2', 'h6', '100M', 60, 'tcp', 5002),
            
            # Medium flows
            ('h3', 'h7', '10M', 60, 'tcp', 5003),
            ('h4', 'h8', '10M', 60, 'tcp', 5004),
            
            # Light flows
            ('h1', 'h9', '1M', 60, 'tcp', 5005),
            ('h2', 'h10', '1M', 60, 'tcp', 5006),
            
            # Very light flows (VoIP simulation)
            ('h3', 'h11', '100K', 60, 'udp', 5007),
            ('h4', 'h12', '100K', 60, 'udp', 5008),
        ]
        
        # Run all flows concurrently
        threads = []
        for src, dst, bw, dur, proto, port in flows:
            t = threading.Thread(target=self.run_flow, args=(src, dst, bw, dur, proto, port))
            t.start()
            threads.append(t)
            time.sleep(0.5)  # Stagger start slightly
        
        # Wait for all to complete
        for t in threads:
            t.join()
        
        self.results['end_time'] = datetime.now().isoformat()
        self.save_results()
        
        info("\n*** Scenario 1 Complete ***\n")
    
    # ========== SCENARIO 2: Elephant vs Mice ==========
    def scenario_elephant_mice(self):
        """
        Scenario 2: Elephant (long-lived) vs Mice (short-lived) flows
        """
        info("\n" + "="*60 + "\n")
        info("SCENARIO 2: Elephant vs Mice Flows\n")
        info("="*60 + "\n")
        
        self.results['scenario'] = 'elephant_mice'
        self.results['start_time'] = datetime.now().isoformat()
        
        # Start elephant flows (long-lived, high bandwidth)
        info("\n1. Starting Elephant Flows (3 minutes)...\n")
        elephant_threads = []
        elephants = [
            ('h1', 'h5', '80M', 180, 'tcp', 5001),
            ('h2', 'h6', '80M', 180, 'tcp', 5002),
        ]
        
        for src, dst, bw, dur, proto, port in elephants:
            t = threading.Thread(target=self.run_flow, args=(src, dst, bw, dur, proto, port))
            t.start()
            elephant_threads.append(t)
        
        # Inject mice flows periodically
        info("\n2. Injecting Mice Flows (every 10 seconds)...\n")
        mice_count = 0
        for round_num in range(6):  # 6 rounds over 60 seconds
            time.sleep(10)
            info(f"\n   Round {round_num + 1}: Starting 3 mice flows...\n")
            
            mice_threads = []
            for i in range(3):
                mice_count += 1
                src = f'h{(mice_count % 4) + 1}'
                dst = f'h{(mice_count % 4) + 9}'
                port = 5100 + mice_count
                
                t = threading.Thread(target=self.run_flow, 
                                   args=(src, dst, '5M', 5, 'tcp', port))
                t.start()
                mice_threads.append(t)
            
            # Wait for mice flows to complete
            for t in mice_threads:
                t.join()
        
        # Wait for elephant flows
        info("\n3. Waiting for elephant flows to complete...\n")
        for t in elephant_threads:
            t.join()
        
        self.results['end_time'] = datetime.now().isoformat()
        self.save_results()
        
        info("\n*** Scenario 2 Complete ***\n")
    
    # ========== SCENARIO 3: Bursty Traffic ==========
    def scenario_bursty_traffic(self):
        """
        Scenario 3: Bursty vs Constant traffic
        """
        info("\n" + "="*60 + "\n")
        info("SCENARIO 3: Bursty vs Constant Traffic\n")
        info("="*60 + "\n")
        
        self.results['scenario'] = 'bursty_traffic'
        self.results['start_time'] = datetime.now().isoformat()
        
        # Constant background traffic
        info("\n1. Starting constant background flows...\n")
        constant_threads = []
        constants = [
            ('h1', 'h5', '30M', 120, 'udp', 5001),
            ('h2', 'h6', '30M', 120, 'udp', 5002),
        ]
        
        for src, dst, bw, dur, proto, port in constants:
            t = threading.Thread(target=self.run_flow, args=(src, dst, bw, dur, proto, port))
            t.start()
            constant_threads.append(t)
        
        # Bursty traffic pattern
        info("\n2. Injecting bursty traffic...\n")
        burst_pattern = [
            (0, 10, '100M'),   # Burst 1
            (15, 10, '100M'),  # Burst 2
            (30, 10, '100M'),  # Burst 3
            (45, 10, '100M'),  # Burst 4
        ]
        
        burst_threads = []
        for start_delay, duration, bandwidth in burst_pattern:
            time.sleep(start_delay if start_delay == 0 else 5)
            info(f"   BURST: {bandwidth} for {duration}s\n")
            
            t = threading.Thread(target=self.run_flow,
                               args=('h3', 'h7', bandwidth, duration, 'tcp', 5003))
            t.start()
            burst_threads.append(t)
            t.join()  # Wait for this burst to complete
        
        # Wait for constant flows
        for t in constant_threads:
            t.join()
        
        self.results['end_time'] = datetime.now().isoformat()
        self.save_results()
        
        info("\n*** Scenario 3 Complete ***\n")
    
    # ========== SCENARIO 4: Load Ramp-Up ==========
    def scenario_load_rampup(self):
        """
        Scenario 4: Gradual load increase (simulating time-of-day)
        """
        info("\n" + "="*60 + "\n")
        info("SCENARIO 4: Load Ramp-Up\n")
        info("="*60 + "\n")
        
        self.results['scenario'] = 'load_rampup'
        self.results['start_time'] = datetime.now().isoformat()
        
        load_phases = [
            ("Low Load", 2, '10M'),      # 2 flows @ 10M each
            ("Medium Load", 5, '20M'),   # 5 flows @ 20M each
            ("High Load", 8, '30M'),     # 8 flows @ 30M each
            ("Peak Load", 12, '40M'),    # 12 flows @ 40M each
        ]
        
        for phase_name, num_flows, bandwidth in load_phases:
            info(f"\n{phase_name}: {num_flows} flows @ {bandwidth}\n")
            
            threads = []
            for i in range(num_flows):
                src = f'h{(i % 8) + 1}'
                dst = f'h{(i % 8) + 9}'
                port = 5000 + i
                
                t = threading.Thread(target=self.run_flow,
                                   args=(src, dst, bandwidth, 30, 'tcp', port))
                t.start()
                threads.append(t)
                time.sleep(0.2)
            
            # Wait for phase to complete
            for t in threads:
                t.join()
            
            info(f"{phase_name} complete\n")
            time.sleep(5)  # Brief pause between phases
        
        self.results['end_time'] = datetime.now().isoformat()
        self.save_results()
        
        info("\n*** Scenario 4 Complete ***\n")
    
    # ========== SCENARIO 5: VoIP + Video + Data Mix ==========
    def scenario_voip_video_data_mix(self):
        """
        Scenario 5: Realistic office/enterprise workload
        Simulates: Video conferencing + VoIP calls + File transfers + Web browsing
        """
        info("\n" + "="*60 + "\n")
        info("SCENARIO 5: VoIP + Video + Data Mix (Office Workload)\n")
        info("="*60 + "\n")
        
        self.results['scenario'] = 'voip_video_data_mix'
        self.results['start_time'] = datetime.now().isoformat()
        
        info("\nSimulating realistic office environment:\n")
        info("- 4x Video Conferences (HD 720p)\n")
        info("- 6x VoIP Calls\n")
        info("- 3x File Transfers\n")
        info("- 4x Web Browsing/Email\n")
        info("Duration: 90 seconds\n\n")
        
        flows = [
            # Video Conferencing (HD 720p: 3-5 Mbps, bidirectional)
            # Using TCP for reliability (Zoom/Teams style)
            ('h1', 'h9', '4M', 90, 'tcp', 5001),   # Video conf 1
            ('h9', 'h1', '4M', 90, 'tcp', 5002),   # Return video
            ('h2', 'h10', '4M', 90, 'tcp', 5003),  # Video conf 2
            ('h10', 'h2', '4M', 90, 'tcp', 5004),  # Return video
            ('h3', 'h11', '3M', 90, 'tcp', 5005),  # Video conf 3
            ('h11', 'h3', '3M', 90, 'tcp', 5006),  # Return video
            ('h4', 'h12', '5M', 90, 'tcp', 5007),  # Video conf 4 (higher quality)
            ('h12', 'h4', '5M', 90, 'tcp', 5008),  # Return video
            
            # VoIP Calls (64-100 Kbps, UDP for low latency)
            ('h5', 'h13', '80K', 90, 'udp', 5009),
            ('h13', 'h5', '80K', 90, 'udp', 5010),
            ('h6', 'h14', '64K', 90, 'udp', 5011),
            ('h14', 'h6', '64K', 90, 'udp', 5012),
            ('h7', 'h15', '100K', 90, 'udp', 5013),
            ('h15', 'h7', '100K', 90, 'udp', 5014),
            
            # File Transfers (Large files: 50-100 Mbps)
            ('h1', 'h16', '80M', 90, 'tcp', 5015),
            ('h2', 'h13', '100M', 90, 'tcp', 5016),
            ('h8', 'h10', '60M', 90, 'tcp', 5017),
            
            # Web Browsing / Email (Medium: 5-15 Mbps)
            ('h3', 'h14', '10M', 90, 'tcp', 5018),
            ('h4', 'h15', '8M', 90, 'tcp', 5019),
            ('h5', 'h9', '12M', 90, 'tcp', 5020),
            ('h6', 'h11', '6M', 90, 'tcp', 5021),
        ]
        
        info("Starting all flows concurrently...\n\n")
        
        threads = []
        for src, dst, bw, dur, proto, port in flows:
            t = threading.Thread(target=self.run_flow, args=(src, dst, bw, dur, proto, port))
            t.start()
            threads.append(t)
            time.sleep(0.3)  # Stagger start
        
        # Wait for all to complete
        for t in threads:
            t.join()
        
        self.results['end_time'] = datetime.now().isoformat()
        self.save_results()
        
        info("\n*** Scenario 5 Complete ***\n")
    
    # ========== SCENARIO 6: Live Streaming Platform ==========
    def scenario_live_streaming(self):
        """
        Scenario 6: Live streaming platform workload
        Simulates: Multiple quality streams (4K, 1080p, 720p, 480p)
        """
        info("\n" + "="*60 + "\n")
        info("SCENARIO 6: Live Streaming Platform\n")
        info("="*60 + "\n")
        
        self.results['scenario'] = 'live_streaming'
        self.results['start_time'] = datetime.now().isoformat()
        
        info("\nSimulating live streaming platform:\n")
        info("Phase 1: Low viewership (60s)\n")
        info("Phase 2: Peak viewership (60s)\n")
        info("Phase 3: Sustained load (60s)\n\n")
        
        # Phase 1: Low viewership
        info("=" * 50 + "\n")
        info("PHASE 1: Low Viewership (Starting...)\n")
        info("=" * 50 + "\n")
        
        phase1_flows = [
            # 2x 4K streams (25 Mbps)
            ('h1', 'h9', '25M', 60, 'tcp', 5001),
            ('h2', 'h10', '25M', 60, 'tcp', 5002),
            
            # 3x 1080p streams (8 Mbps)
            ('h3', 'h11', '8M', 60, 'tcp', 5003),
            ('h4', 'h12', '8M', 60, 'tcp', 5004),
            ('h5', 'h13', '8M', 60, 'tcp', 5005),
            
            # 4x 720p streams (5 Mbps)
            ('h6', 'h14', '5M', 60, 'tcp', 5006),
            ('h7', 'h15', '5M', 60, 'tcp', 5007),
            ('h8', 'h16', '5M', 60, 'tcp', 5008),
            ('h1', 'h10', '5M', 60, 'tcp', 5009),
        ]
        
        threads = []
        for src, dst, bw, dur, proto, port in phase1_flows:
            t = threading.Thread(target=self.run_flow, args=(src, dst, bw, dur, proto, port))
            t.start()
            threads.append(t)
            time.sleep(0.2)
        
        for t in threads:
            t.join()
        
        info("\nPhase 1 complete. Waiting 5s...\n")
        time.sleep(5)
        
        # Phase 2: Peak viewership (more streams)
        info("=" * 50 + "\n")
        info("PHASE 2: Peak Viewership (High Load!)\n")
        info("=" * 50 + "\n")
        
        phase2_flows = [
            # 4x 4K streams
            ('h1', 'h9', '25M', 60, 'tcp', 6001),
            ('h2', 'h10', '25M', 60, 'tcp', 6002),
            ('h3', 'h11', '25M', 60, 'tcp', 6003),
            ('h4', 'h12', '25M', 60, 'tcp', 6004),
            
            # 6x 1080p streams
            ('h5', 'h13', '8M', 60, 'tcp', 6005),
            ('h6', 'h14', '8M', 60, 'tcp', 6006),
            ('h7', 'h15', '8M', 60, 'tcp', 6007),
            ('h8', 'h16', '8M', 60, 'tcp', 6008),
            ('h1', 'h13', '8M', 60, 'tcp', 6009),
            ('h2', 'h14', '8M', 60, 'tcp', 6010),
            
            # 8x 720p streams
            ('h3', 'h15', '5M', 60, 'tcp', 6011),
            ('h4', 'h16', '5M', 60, 'tcp', 6012),
            ('h5', 'h9', '5M', 60, 'tcp', 6013),
            ('h6', 'h10', '5M', 60, 'tcp', 6014),
            ('h7', 'h11', '5M', 60, 'tcp', 6015),
            ('h8', 'h12', '5M', 60, 'tcp', 6016),
            ('h1', 'h14', '5M', 60, 'tcp', 6017),
            ('h2', 'h15', '5M', 60, 'tcp', 6018),
            
            # 6x 480p streams (2.5 Mbps - mobile users)
            ('h3', 'h9', '2500K', 60, 'tcp', 6019),
            ('h4', 'h10', '2500K', 60, 'tcp', 6020),
            ('h5', 'h11', '2500K', 60, 'tcp', 6021),
            ('h6', 'h12', '2500K', 60, 'tcp', 6022),
            ('h7', 'h13', '2500K', 60, 'tcp', 6023),
            ('h8', 'h14', '2500K', 60, 'tcp', 6024),
        ]
        
        threads = []
        for src, dst, bw, dur, proto, port in phase2_flows:
            t = threading.Thread(target=self.run_flow, args=(src, dst, bw, dur, proto, port))
            t.start()
            threads.append(t)
            time.sleep(0.2)
        
        for t in threads:
            t.join()
        
        info("\nPhase 2 complete. Waiting 5s...\n")
        time.sleep(5)
        
        # Phase 3: Sustained moderate load
        info("=" * 50 + "\n")
        info("PHASE 3: Sustained Load\n")
        info("=" * 50 + "\n")
        
        phase3_flows = [
            # 3x 4K
            ('h1', 'h9', '25M', 60, 'tcp', 7001),
            ('h2', 'h10', '25M', 60, 'tcp', 7002),
            ('h3', 'h11', '25M', 60, 'tcp', 7003),
            
            # 5x 1080p
            ('h4', 'h12', '8M', 60, 'tcp', 7004),
            ('h5', 'h13', '8M', 60, 'tcp', 7005),
            ('h6', 'h14', '8M', 60, 'tcp', 7006),
            ('h7', 'h15', '8M', 60, 'tcp', 7007),
            ('h8', 'h16', '8M', 60, 'tcp', 7008),
            
            # 6x 720p
            ('h1', 'h13', '5M', 60, 'tcp', 7009),
            ('h2', 'h14', '5M', 60, 'tcp', 7010),
            ('h3', 'h15', '5M', 60, 'tcp', 7011),
            ('h4', 'h16', '5M', 60, 'tcp', 7012),
            ('h5', 'h9', '5M', 60, 'tcp', 7013),
            ('h6', 'h10', '5M', 60, 'tcp', 7014),
        ]
        
        threads = []
        for src, dst, bw, dur, proto, port in phase3_flows:
            t = threading.Thread(target=self.run_flow, args=(src, dst, bw, dur, proto, port))
            t.start()
            threads.append(t)
            time.sleep(0.2)
        
        for t in threads:
            t.join()
        
        self.results['end_time'] = datetime.now().isoformat()
        self.save_results()
        
        info("\n*** Scenario 6 Complete ***\n")
    
    def save_results(self):
        """Save results to JSON file"""
        filename = f"results/heterogen_traffic/{self.algorithm}/" \
                   f"{self.results['scenario']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        import os
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        info(f"\n*** Results saved to {filename} ***\n")


def main():
    import sys
    
    if len(sys.argv) < 3:
        info("Usage: sudo python3 test_heterogeneous_traffic.py [wrr|wlc] [scenario]\n")
        info("\nScenarios:\n")
        info("  1 or mixed      - Mixed bandwidth workload\n")
        info("  2 or elephant   - Elephant vs mice flows\n")
        info("  3 or bursty     - Bursty vs constant traffic\n")
        info("  4 or rampup     - Load ramp-up\n")
        info("  5 or office     - VoIP + Video + Data Mix (Office workload)\n")
        info("  6 or streaming  - Live streaming platform\n")
        info("  all             - Run all scenarios\n")
        info("\nExample:\n")
        info("  sudo python3 test_heterogeneous_traffic.py wrr office\n")
        sys.exit(1)
    
    algorithm = sys.argv[1].lower()
    scenario = sys.argv[2].lower()
    
    if algorithm not in ['wrr', 'wlc']:
        info("Error: Algorithm must be 'wrr' or 'wlc'\n")
        sys.exit(1)
    
    info("\n" + "="*60 + "\n")
    info(f"HETEROGENEOUS TRAFFIC TESTING\n")
    info(f"Algorithm: {algorithm.upper()}\n")
    info("="*60 + "\n")
    
    info("\nIMPORTANT: Make sure controller is running!\n")
    controller_file = "weighted_round_robin_controller.py" if algorithm == 'wrr' \
                     else "weighted_least_connection_controller.py"
    info(f"Command: ryu-manager --ofp-tcp-listen-port 6653 controllers/{controller_file} --verbose\n")
    
    input("\nPress Enter when controller is ready...")
    
    tester = HeterogeneousTrafficTester(algorithm)
    
    try:
        tester.setup_network()
        
        if scenario in ['1', 'mixed']:
            tester.scenario_mixed_bandwidth()
        elif scenario in ['2', 'elephant']:
            tester.scenario_elephant_mice()
        elif scenario in ['3', 'bursty']:
            tester.scenario_bursty_traffic()
        elif scenario in ['4', 'rampup']:
            tester.scenario_load_rampup()
        elif scenario in ['5', 'office']:
            tester.scenario_voip_video_data_mix()
        elif scenario in ['6', 'streaming']:
            tester.scenario_live_streaming()
        elif scenario == 'all':
            tester.scenario_mixed_bandwidth()
            time.sleep(10)
            tester.scenario_elephant_mice()
            time.sleep(10)
            tester.scenario_bursty_traffic()
            time.sleep(10)
            tester.scenario_load_rampup()
            time.sleep(10)
            tester.scenario_voip_video_data_mix()
            time.sleep(10)
            tester.scenario_live_streaming()
        else:
            info(f"Unknown scenario: {scenario}\n")
    
    finally:
        tester.cleanup()


if __name__ == '__main__':
    setLogLevel('info')
    main()