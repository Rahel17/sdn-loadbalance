#!/usr/bin/env python3
"""
Automated Testing Script for Load Balancing Metrics
Tests: Throughput, Delay, Jitter, Packet Loss, CPU, Fairness, Response Time
"""

import time
import json
import os
import subprocess
import psutil
from datetime import datetime
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info

class MetricsCollector:
    def __init__(self, test_name, algorithm):
        self.test_name = test_name
        self.algorithm = algorithm
        self.results_dir = f"results/{algorithm}/{test_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.results_dir, exist_ok=True)
        
        self.metrics = {
            'throughput': [],
            'delay': [],
            'jitter': [],
            'packet_loss': [],
            'cpu_utilization': [],
            'fairness_index': 0,
            'response_time': []
        }
    
    def save_results(self):
        """Save metrics to JSON file"""
        filepath = f"{self.results_dir}/metrics.json"
        with open(filepath, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        info(f"\n*** Results saved to {filepath} ***\n")
    
    def calculate_fairness_index(self, flow_counts):
        """
        Calculate Jain's Fairness Index
        FI = (sum(xi))^2 / (n * sum(xi^2))
        where xi is throughput of flow i
        """
        if not flow_counts:
            return 0
        
        n = len(flow_counts)
        sum_x = sum(flow_counts)
        sum_x2 = sum(x**2 for x in flow_counts)
        
        if sum_x2 == 0:
            return 0
        
        fairness = (sum_x ** 2) / (n * sum_x2)
        return fairness


class LoadBalancingTester:
    def __init__(self, algorithm="wrr"):
        self.algorithm = algorithm
        self.net = None
        self.controller_process = None
        
    def setup_network(self):
        """Setup Fat-Tree network"""
        info(f"\n*** Setting up Fat-Tree with {self.algorithm.upper()} ***\n")
        
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
        info("*** Waiting for controller to install flows...\n")
        time.sleep(5)
        
        # Basic connectivity test
        info("*** Testing basic connectivity...\n")
        loss = self.net.pingAll()
        if loss > 0:
            info(f"WARNING: {loss}% packet loss in initial pingall!\n")
        else:
            info("✓ Network connectivity OK\n")
    
    def cleanup(self):
        """Cleanup network"""
        if self.net:
            self.net.stop()
    
    def get_controller_cpu(self):
        """Get CPU usage of Ryu controller process"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                if 'ryu-manager' in proc.info['name']:
                    return proc.info['cpu_percent']
        except:
            pass
        return 0
    
    def measure_response_time(self, src_host, dst_host):
        """Measure connection setup time"""
        start_time = time.time()
        
        # First packet (triggers flow installation)
        result = src_host.cmd(f'ping -c 1 -W 1 {dst_host.IP()}')
        
        response_time = time.time() - start_time
        
        # Check if successful
        if '1 received' in result:
            return response_time * 1000  # Convert to ms
        return None
    
    def run_iperf_test(self, src, dst, duration=10, bandwidth='50M', protocol='tcp'):
        """Run iperf test and collect metrics"""
        info(f"  Running iperf {protocol.upper()}: {src.name} -> {dst.name} ({bandwidth}, {duration}s)\n")
        
        # Start iperf server
        port = 5001 + int(dst.name[1:])  # Unique port per host
        dst.cmd(f'iperf3 -s -p {port} -D')  # Daemon mode
        time.sleep(1)
        
        # Run iperf client
        if protocol == 'udp':
            result = src.cmd(f'iperf3 -c {dst.IP()} -p {port} -u -b {bandwidth} -t {duration} -J')
        else:
            result = src.cmd(f'iperf3 -c {dst.IP()} -p {port} -t {duration} -J')
        
        # Kill server
        dst.cmd(f'pkill -9 -f "iperf3 -s -p {port}"')
        
        # Parse results
        try:
            data = json.loads(result)
            
            if 'end' in data:
                end_data = data['end']
                
                # Throughput (bits/sec)
                if 'sum_received' in end_data:
                    throughput = end_data['sum_received']['bits_per_second'] / 1e6  # Mbps
                elif 'sum' in end_data:
                    throughput = end_data['sum']['bits_per_second'] / 1e6
                else:
                    throughput = 0
                
                # Packet loss (UDP only)
                packet_loss = 0
                if protocol == 'udp' and 'sum' in end_data:
                    packet_loss = end_data['sum'].get('lost_percent', 0)
                
                # Jitter (UDP only)
                jitter = 0
                if protocol == 'udp' and 'sum' in end_data:
                    jitter = end_data['sum'].get('jitter_ms', 0)
                
                return {
                    'throughput': throughput,
                    'packet_loss': packet_loss,
                    'jitter': jitter
                }
        except:
            pass
        
        return None
    
    def measure_delay(self, src, dst, count=100):
        """Measure RTT delay using ping"""
        info(f"  Measuring delay: {src.name} -> {dst.name} ({count} pings)\n")
        
        result = src.cmd(f'ping -c {count} -i 0.01 {dst.IP()}')
        
        # Parse results
        delays = []
        for line in result.split('\n'):
            if 'time=' in line:
                try:
                    time_str = line.split('time=')[1].split()[0]
                    delays.append(float(time_str))
                except:
                    pass
        
        if delays:
            return {
                'min': min(delays),
                'avg': sum(delays) / len(delays),
                'max': max(delays),
                'count': len(delays)
            }
        
        return None
    
    def get_flow_distribution(self):
        """Get flow distribution across ports for fairness calculation"""
        flow_counts = {}
        
        # Check edge switches (s13-s20) port 3 and 4
        for switch_num in range(13, 21):
            switch_name = f's{switch_num}'
            result = self.net.get(switch_name).cmd(
                f'ovs-ofctl dump-flows {switch_name} -O OpenFlow13'
            )
            
            port3_count = 0
            port4_count = 0
            
            for line in result.split('\n'):
                if 'priority=10' in line and 'n_packets=' in line:
                    if 'output:3' in line or 'output:"s' in line and '-eth3"' in line:
                        try:
                            packets = int(line.split('n_packets=')[1].split(',')[0])
                            port3_count += packets
                        except:
                            pass
                    elif 'output:4' in line or 'output:"s' in line and '-eth4"' in line:
                        try:
                            packets = int(line.split('n_packets=')[1].split(',')[0])
                            port4_count += packets
                        except:
                            pass
            
            if port3_count > 0 or port4_count > 0:
                flow_counts[f'{switch_name}_port3'] = port3_count
                flow_counts[f'{switch_name}_port4'] = port4_count
        
        return list(flow_counts.values())
    
    # ============ TEST SCENARIOS ============
    
    def scenario_light_load(self):
        """Scenario 1: Light Load (2-4 flows)"""
        info("\n" + "="*60 + "\n")
        info("*** SCENARIO 1: Light Load ***\n")
        info("="*60 + "\n")
        
        collector = MetricsCollector("scenario1_light_load", self.algorithm)
        
        hosts = [self.net.get(f'h{i}') for i in range(1, 17)]
        
        # Test pairs
        test_pairs = [
            (hosts[0], hosts[4]),   # h1 -> h5 (cross-pod)
            (hosts[1], hosts[8]),   # h2 -> h9 (cross-pod)
            (hosts[2], hosts[12]),  # h3 -> h13 (cross-pod)
            (hosts[3], hosts[6]),   # h4 -> h7 (cross-pod)
        ]
        
        # Response time measurement
        info("\n1. Measuring Response Time...\n")
        for src, dst in test_pairs:
            rt = self.measure_response_time(src, dst)
            if rt:
                collector.metrics['response_time'].append(rt)
                info(f"   {src.name} -> {dst.name}: {rt:.2f} ms\n")
        
        # Delay measurement
        info("\n2. Measuring Delay (RTT)...\n")
        for src, dst in test_pairs[:2]:  # Sample 2 pairs
            delay_data = self.measure_delay(src, dst, count=50)
            if delay_data:
                collector.metrics['delay'].append(delay_data)
                info(f"   {src.name} -> {dst.name}: avg={delay_data['avg']:.2f}ms\n")
        
        # Start CPU monitoring
        info("\n3. Starting traffic and monitoring...\n")
        cpu_samples = []
        
        # Start iperf servers
        for _, dst in test_pairs:
            port = 5001 + int(dst.name[1:])
            dst.cmd(f'iperf3 -s -p {port} -D')
        time.sleep(1)
        
        # Start iperf clients in background
        for src, dst in test_pairs:
            port = 5001 + int(dst.name[1:])
            src.cmd(f'iperf3 -c {dst.IP()} -p {port} -t 60 -b 10M &')
        
        # Monitor for 60 seconds
        start_time = time.time()
        while time.time() - start_time < 60:
            cpu = self.get_controller_cpu()
            cpu_samples.append(cpu)
            time.sleep(1)
        
        # Wait for iperf to finish
        time.sleep(5)
        
        # Collect final metrics
        info("\n4. Collecting final metrics...\n")
        
        # Run final iperf tests to get accurate throughput
        for src, dst in test_pairs:
            result = self.run_iperf_test(src, dst, duration=10, bandwidth='10M')
            if result:
                collector.metrics['throughput'].append(result['throughput'])
                collector.metrics['packet_loss'].append(result['packet_loss'])
                collector.metrics['jitter'].append(result['jitter'])
        
        # CPU utilization
        if cpu_samples:
            collector.metrics['cpu_utilization'] = {
                'avg': sum(cpu_samples) / len(cpu_samples),
                'max': max(cpu_samples),
                'min': min(cpu_samples)
            }
        
        # Fairness index
        flow_counts = self.get_flow_distribution()
        collector.metrics['fairness_index'] = collector.calculate_fairness_index(flow_counts)
        
        # Save results
        collector.save_results()
        
        info("\n*** Scenario 1 Complete ***\n")
        self.print_summary(collector.metrics)
        
        return collector.metrics
    
    def scenario_medium_load(self):
        """Scenario 2: Medium Load (8-12 flows)"""
        info("\n" + "="*60 + "\n")
        info("*** SCENARIO 2: Medium Load ***\n")
        info("="*60 + "\n")
        
        collector = MetricsCollector("scenario2_medium_load", self.algorithm)
        
        hosts = [self.net.get(f'h{i}') for i in range(1, 17)]
        
        # Create 10 test pairs
        test_pairs = [
            (hosts[i], hosts[(i+4) % 16]) for i in range(10)
        ]
        
        info("\n1. Starting medium load test (10 concurrent flows)...\n")
        
        # Start iperf servers
        for _, dst in test_pairs:
            port = 5001 + int(dst.name[1:])
            dst.cmd(f'iperf3 -s -p {port} -D')
        time.sleep(1)
        
        # Start flows with varying bandwidths
        bandwidths = ['20M', '30M', '40M', '50M', '20M', '30M', '40M', '50M', '30M', '40M']
        for (src, dst), bw in zip(test_pairs, bandwidths):
            port = 5001 + int(dst.name[1:])
            src.cmd(f'iperf3 -c {dst.IP()} -p {port} -t 120 -b {bw} &')
        
        # Monitor CPU
        cpu_samples = []
        start_time = time.time()
        while time.time() - start_time < 120:
            cpu = self.get_controller_cpu()
            cpu_samples.append(cpu)
            time.sleep(1)
        
        time.sleep(5)
        
        # Collect metrics
        info("\n2. Collecting metrics...\n")
        for i, (src, dst) in enumerate(test_pairs):
            result = self.run_iperf_test(src, dst, duration=10, bandwidth=bandwidths[i])
            if result:
                collector.metrics['throughput'].append(result['throughput'])
                collector.metrics['packet_loss'].append(result['packet_loss'])
        
        # Delay test on sample pairs
        for src, dst in test_pairs[:3]:
            delay_data = self.measure_delay(src, dst, count=30)
            if delay_data:
                collector.metrics['delay'].append(delay_data)
        
        # CPU and fairness
        if cpu_samples:
            collector.metrics['cpu_utilization'] = {
                'avg': sum(cpu_samples) / len(cpu_samples),
                'max': max(cpu_samples)
            }
        
        flow_counts = self.get_flow_distribution()
        collector.metrics['fairness_index'] = collector.calculate_fairness_index(flow_counts)
        
        collector.save_results()
        info("\n*** Scenario 2 Complete ***\n")
        self.print_summary(collector.metrics)
        
        return collector.metrics
    
    def scenario_heavy_load(self):
        """Scenario 3: Heavy Load (16+ flows)"""
        info("\n" + "="*60 + "\n")
        info("*** SCENARIO 3: Heavy Load ***\n")
        info("="*60 + "\n")
        
        collector = MetricsCollector("scenario3_heavy_load", self.algorithm)
        
        hosts = [self.net.get(f'h{i}') for i in range(1, 17)]
        
        # All-to-all communication (16 flows)
        test_pairs = [
            (hosts[i], hosts[(i+8) % 16]) for i in range(16)
        ]
        
        info(f"\n1. Starting heavy load test ({len(test_pairs)} concurrent flows)...\n")
        
        # Start servers
        for _, dst in test_pairs:
            port = 5001 + int(dst.name[1:])
            dst.cmd(f'iperf3 -s -p {port} -D')
        time.sleep(1)
        
        # Start clients with high bandwidth
        for src, dst in test_pairs:
            port = 5001 + int(dst.name[1:])
            src.cmd(f'iperf3 -c {dst.IP()} -p {port} -t 180 -b 50M &')
        
        # Monitor
        cpu_samples = []
        start_time = time.time()
        while time.time() - start_time < 180:
            cpu = self.get_controller_cpu()
            cpu_samples.append(cpu)
            time.sleep(1)
        
        time.sleep(5)
        
        # Collect metrics
        info("\n2. Collecting metrics (this may take a while)...\n")
        for src, dst in test_pairs:
            result = self.run_iperf_test(src, dst, duration=5, bandwidth='50M')
            if result:
                collector.metrics['throughput'].append(result['throughput'])
                collector.metrics['packet_loss'].append(result['packet_loss'])
        
        # CPU and fairness
        if cpu_samples:
            collector.metrics['cpu_utilization'] = {
                'avg': sum(cpu_samples) / len(cpu_samples),
                'max': max(cpu_samples),
                'std': (sum((x - sum(cpu_samples)/len(cpu_samples))**2 for x in cpu_samples) / len(cpu_samples))**0.5
            }
        
        flow_counts = self.get_flow_distribution()
        collector.metrics['fairness_index'] = collector.calculate_fairness_index(flow_counts)
        
        collector.save_results()
        info("\n*** Scenario 3 Complete ***\n")
        self.print_summary(collector.metrics)
        
        return collector.metrics
    
    def print_summary(self, metrics):
        """Print test summary"""
        info("\n" + "="*60 + "\n")
        info("RESULTS SUMMARY\n")
        info("="*60 + "\n")
        
        if metrics['throughput']:
            avg_throughput = sum(metrics['throughput']) / len(metrics['throughput'])
            info(f"Throughput: {avg_throughput:.2f} Mbps (avg)\n")
        
        if metrics['delay']:
            avg_delays = [d['avg'] for d in metrics['delay']]
            if avg_delays:
                info(f"Delay: {sum(avg_delays)/len(avg_delays):.2f} ms (avg)\n")
        
        if metrics['jitter']:
            non_zero_jitter = [j for j in metrics['jitter'] if j > 0]
            if non_zero_jitter:
                info(f"Jitter: {sum(non_zero_jitter)/len(non_zero_jitter):.2f} ms (avg)\n")
        
        if metrics['packet_loss']:
            avg_loss = sum(metrics['packet_loss']) / len(metrics['packet_loss'])
            info(f"Packet Loss: {avg_loss:.2f}%\n")
        
        if isinstance(metrics['cpu_utilization'], dict):
            info(f"CPU Utilization: {metrics['cpu_utilization']['avg']:.2f}% (avg), "
                 f"{metrics['cpu_utilization']['max']:.2f}% (max)\n")
        
        info(f"Fairness Index: {metrics['fairness_index']:.4f}\n")
        
        if metrics['response_time']:
            avg_rt = sum(metrics['response_time']) / len(metrics['response_time'])
            info(f"Response Time: {avg_rt:.2f} ms (avg)\n")
        
        info("="*60 + "\n")


def main():
    import sys
    
    if len(sys.argv) < 3:
        info("Usage: sudo python3 test_metrics.py [wrr|wlc] [scenario]\n")
        info("\nScenarios:\n")
        info("  1 or light   - Light load (4 flows)\n")
        info("  2 or medium  - Medium load (10 flows)\n")
        info("  3 or heavy   - Heavy load (16 flows)\n")
        info("  all          - Run all scenarios\n")
        info("\nExample:\n")
        info("  sudo python3 test_metrics.py wrr 1\n")
        info("  sudo python3 test_metrics.py wlc all\n")
        sys.exit(1)
    
    algorithm = sys.argv[1].lower()
    scenario = sys.argv[2].lower()
    
    if algorithm not in ['wrr', 'wlc']:
        info("Error: Algorithm must be 'wrr' or 'wlc'\n")
        sys.exit(1)
    
    info("\n" + "="*60 + "\n")
    info(f"LOAD BALANCING METRICS TESTING\n")
    info(f"Algorithm: {algorithm.upper()}\n")
    info("="*60 + "\n")
    
    info("\nIMPORTANT: Make sure controller is running!\n")
    info(f"Command: ryu-manager --ofp-tcp-listen-port 6653 "
         f"controllers/weighted_{'round_robin' if algorithm == 'wrr' else 'least_connection'}_controller.py --verbose\n")
    
    input("\nPress Enter when controller is ready...")
    
    tester = LoadBalancingTester(algorithm)
    
    try:
        tester.setup_network()
        
        if scenario in ['1', 'light']:
            tester.scenario_light_load()
        elif scenario in ['2', 'medium']:
            tester.scenario_medium_load()
        elif scenario in ['3', 'heavy']:
            tester.scenario_heavy_load()
        elif scenario == 'all':
            tester.scenario_light_load()
            time.sleep(10)
            tester.scenario_medium_load()
            time.sleep(10)
            tester.scenario_heavy_load()
        else:
            info(f"Unknown scenario: {scenario}\n")
    
    finally:
        tester.cleanup()


if __name__ == '__main__':
    setLogLevel('info')
    main()