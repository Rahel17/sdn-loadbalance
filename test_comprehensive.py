from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
import time
import threading
import json
import os
import psutil
import csv
from datetime import datetime


class MetricsCollector:
    """Collect and manage all performance metrics"""
    
    def __init__(self, scenario_name, algorithm):
        self.scenario_name = scenario_name
        self.algorithm = algorithm
        self.results_dir = f"results/comprehensive/{algorithm}/{scenario_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.results_dir, exist_ok=True)
        
        self.metrics = {
            'scenario': scenario_name,
            'algorithm': algorithm,
            'start_time': datetime.now().isoformat(),
            'end_time': '',
            'flows': [],
            'throughput': {
                'tcp': [],
                'udp': []
            },
            'delay': [],
            'jitter': [],
            'packet_loss': [],
            'cpu_utilization': {
                'samples': [],
                'avg': 0,
                'max': 0,
                'min': 0
            },
            'fairness_index': 0,
            'response_time': []
        }
    
    def finalize(self):
        """Calculate final statistics and save"""
        self.metrics['end_time'] = datetime.now().isoformat()
        
        # Calculate CPU stats
        if self.metrics['cpu_utilization']['samples']:
            samples = self.metrics['cpu_utilization']['samples']
            self.metrics['cpu_utilization']['avg'] = sum(samples) / len(samples)
            self.metrics['cpu_utilization']['max'] = max(samples)
            self.metrics['cpu_utilization']['min'] = min(samples)
        
        self.save_results()
        self.export_to_csv()  # Auto-export to CSV
    
    def export_to_csv(self):
        """Export current test results to CSV"""
        csv_file = f"{self.results_dir}/summary.csv"
        
        # Calculate statistics
        tcp_throughput = self.metrics['throughput']['tcp']
        udp_throughput = self.metrics['throughput']['udp']
        delays = self.metrics['delay']
        jitters = self.metrics['jitter']
        packet_loss = self.metrics['packet_loss']
        cpu = self.metrics['cpu_utilization']
        response_times = self.metrics['response_time']
        
        # Prepare data
        data = {
            'Scenario': self.scenario_name,
            'Algorithm': self.algorithm,
            'TCP Throughput Avg (Mbps)': sum(tcp_throughput) / len(tcp_throughput) if tcp_throughput else 0,
            'TCP Throughput Min (Mbps)': min(tcp_throughput) if tcp_throughput else 0,
            'TCP Throughput Max (Mbps)': max(tcp_throughput) if tcp_throughput else 0,
            'UDP Throughput Avg (Mbps)': sum(udp_throughput) / len(udp_throughput) if udp_throughput else 0,
            'Delay Avg (ms)': sum(d['avg'] for d in delays) / len(delays) if delays else 0,
            'Delay Min (ms)': min(d['min'] for d in delays) if delays else 0,
            'Delay Max (ms)': max(d['max'] for d in delays) if delays else 0,
            'Jitter Avg (ms)': sum(jitters) / len(jitters) if jitters else 0,
            'Jitter Min (ms)': min(jitters) if jitters else 0,
            'Jitter Max (ms)': max(jitters) if jitters else 0,
            'Packet Loss Avg (%)': sum(packet_loss) / len(packet_loss) if packet_loss else 0,
            'Packet Loss Max (%)': max(packet_loss) if packet_loss else 0,
            'CPU Avg (%)': cpu['avg'],
            'CPU Max (%)': cpu['max'],
            'CPU Min (%)': cpu['min'],
            'Fairness Index': self.metrics['fairness_index'],
            'Response Time Avg (ms)': sum(response_times) / len(response_times) if response_times else 0,
            'Total Flows': len(self.metrics['flows']),
            'TCP Flows': len([f for f in self.metrics['flows'] if f.get('protocol') == 'tcp']),
            'UDP Flows': len([f for f in self.metrics['flows'] if f.get('protocol') == 'udp']),
            'Test Date': self.metrics['start_time']
        }
        
        # Write CSV
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data.keys())
            writer.writeheader()
            writer.writerow({k: f"{v:.4f}" if isinstance(v, float) else v for k, v in data.items()})
        
        info(f"*** CSV summary exported to {csv_file} ***\n")
        
        # Also export detailed flows (NOW WITH BANDWIDTH_REQUESTED!)
        flows_csv = f"{self.results_dir}/flows.csv"
        with open(flows_csv, 'w', newline='') as f:
            if self.metrics['flows']:
                fieldnames = ['label', 'src', 'dst', 'protocol', 'bandwidth_requested', 'throughput', 'jitter', 'packet_loss']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for flow in self.metrics['flows']:
                    writer.writerow({
                        'label': flow.get('label', ''),
                        'src': flow.get('src', ''),
                        'dst': flow.get('dst', ''),
                        'protocol': flow.get('protocol', ''),
                        'bandwidth_requested': flow.get('bandwidth_requested', 'N/A'),
                        'throughput': f"{flow.get('throughput', 0):.2f}",
                        'jitter': f"{flow.get('jitter', 0):.4f}",
                        'packet_loss': f"{flow.get('packet_loss', 0):.4f}"
                    })
        
        info(f"*** Flow details exported to {flows_csv} ***\n")
    
    def save_results(self):
        """Save metrics to JSON file"""
        filepath = f"{self.results_dir}/metrics.json"
        with open(filepath, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        info(f"\n*** Results saved to {filepath} ***\n")
    
    def calculate_fairness_index(self, values):
        """
        Calculate Jain's Fairness Index
        FI = (sum(xi))^2 / (n * sum(xi^2))
        """
        if not values or len(values) == 0:
            return 0
        
        n = len(values)
        sum_x = sum(values)
        sum_x2 = sum(x**2 for x in values)
        
        if sum_x2 == 0:
            return 0
        
        fairness = (sum_x ** 2) / (n * sum_x2)
        return fairness
    
    def calculate_normalized_fairness(self):
        """
        Calculate fairness normalized by requested bandwidth
        More accurate for heterogeneous traffic
        """
        flow_ratios = []
        
        for flow in self.metrics['flows']:
            throughput_achieved = flow.get('throughput', 0)
            bandwidth_requested = flow.get('bandwidth_requested', None)
            
            if not bandwidth_requested:
                # Fallback: skip this flow for fairness calculation
                continue
            
            # Parse bandwidth string (e.g., "100M" -> 100, "500K" -> 0.5)
            if isinstance(bandwidth_requested, str):
                if 'M' in bandwidth_requested:
                    requested = float(bandwidth_requested.replace('M', ''))
                elif 'K' in bandwidth_requested:
                    requested = float(bandwidth_requested.replace('K', '')) / 1000
                else:
                    try:
                        requested = float(bandwidth_requested)
                    except:
                        continue
            else:
                requested = float(bandwidth_requested)
            
            if requested > 0 and throughput_achieved > 0:
                # Calculate achievement ratio (remove capping to see true variance)
                ratio = throughput_achieved / requested
                flow_ratios.append(ratio)
        
        if not flow_ratios or len(flow_ratios) < 2:
            # Cannot calculate fairness with 0 or 1 flow
            info("   Warning: Not enough flows with bandwidth info for fairness calculation\n")
            return 0
        
        # Debug output
        info(f"   DEBUG: {len(flow_ratios)} flows in fairness calculation\n")
        info(f"   DEBUG: Ratios - Min: {min(flow_ratios):.4f}, Max: {max(flow_ratios):.4f}, Avg: {sum(flow_ratios)/len(flow_ratios):.4f}\n")
        
        # Calculate Jain's Fairness Index on ratios
        return self.calculate_fairness_index(flow_ratios)
    
    def print_summary(self):
        """Print comprehensive test summary"""
        info("\n" + "="*70 + "\n")
        info(f"RESULTS SUMMARY - {self.scenario_name.upper()}\n")
        info("="*70 + "\n")
        
        # Throughput
        if self.metrics['throughput']['tcp']:
            tcp_avg = sum(self.metrics['throughput']['tcp']) / len(self.metrics['throughput']['tcp'])
            info(f"📊 Throughput (TCP): {tcp_avg:.2f} Mbps (avg of {len(self.metrics['throughput']['tcp'])} flows)\n")
        
        if self.metrics['throughput']['udp']:
            udp_avg = sum(self.metrics['throughput']['udp']) / len(self.metrics['throughput']['udp'])
            info(f"📊 Throughput (UDP): {udp_avg:.2f} Mbps (avg of {len(self.metrics['throughput']['udp'])} flows)\n")
        
        # Delay
        if self.metrics['delay']:
            avg_delays = [d['avg'] for d in self.metrics['delay']]
            info(f"⏱️  Delay (RTT): {sum(avg_delays)/len(avg_delays):.2f} ms (avg)\n")
            info(f"    Min: {min([d['min'] for d in self.metrics['delay']]):.2f} ms, "
                 f"Max: {max([d['max'] for d in self.metrics['delay']]):.2f} ms\n")
        
        # Jitter
        if self.metrics['jitter']:
            non_zero = [j for j in self.metrics['jitter'] if j > 0]
            if non_zero:
                info(f"📶 Jitter: {sum(non_zero)/len(non_zero):.4f} ms (avg of {len(non_zero)} UDP flows)\n")
            else:
                info(f"📶 Jitter: N/A (no UDP flows measured)\n")
        else:
            info(f"📶 Jitter: N/A (no data)\n")
        
        # Packet Loss
        if self.metrics['packet_loss']:
            non_zero = [p for p in self.metrics['packet_loss'] if p > 0]
            if non_zero:
                info(f"📉 Packet Loss: {sum(non_zero)/len(non_zero):.4f}% (avg)\n")
            else:
                info(f"📉 Packet Loss: 0.00% (no loss detected)\n")
        
        # CPU
        cpu = self.metrics['cpu_utilization']
        if cpu['avg'] > 0:
            info(f"💻 CPU Utilization: {cpu['avg']:.2f}% (avg), {cpu['max']:.2f}% (max), {cpu['min']:.2f}% (min)\n")
        
        # Fairness
        info(f"⚖️  Fairness Index: {self.metrics['fairness_index']:.4f}\n")
        
        # Response Time
        if self.metrics['response_time']:
            avg_rt = sum(self.metrics['response_time']) / len(self.metrics['response_time'])
            info(f"⚡ Response Time: {avg_rt:.2f} ms (avg)\n")
        
        info("="*70 + "\n")


class ComprehensiveTester:
    """Main tester class combining heterogeneous traffic with complete metrics"""
    
    def __init__(self, algorithm="wrr"):
        self.algorithm = algorithm
        self.net = None
        self.cpu_monitor_thread = None
        self.cpu_monitoring = False
        
    def setup_network(self):
        """Setup Fat-Tree network"""
        info(f"\n*** Setting up Fat-Tree network with {self.algorithm.upper()} ***\n")
        
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
        info("*** Waiting for network to stabilize...\n")
        time.sleep(5)
        
        # Connectivity test
        info("*** Testing connectivity...\n")
        loss = self.net.pingAll()
        if loss > 0:
            info(f"WARNING: {loss}% packet loss!\n")
        else:
            info("✓ Network ready\n")
    
    def cleanup(self):
        """Cleanup network"""
        self.stop_cpu_monitoring()
        if self.net:
            info("\n*** Cleaning up network...\n")
            self.net.stop()
    
    def start_cpu_monitoring(self, collector):
        """Start background CPU monitoring"""
        self.cpu_monitoring = True
        
        def monitor():
            while self.cpu_monitoring:
                cpu = self.get_controller_cpu()
                if cpu > 0:
                    collector.metrics['cpu_utilization']['samples'].append(cpu)
                time.sleep(1)
        
        self.cpu_monitor_thread = threading.Thread(target=monitor, daemon=True)
        self.cpu_monitor_thread.start()
    
    def stop_cpu_monitoring(self):
        """Stop CPU monitoring"""
        self.cpu_monitoring = False
        if self.cpu_monitor_thread:
            self.cpu_monitor_thread.join(timeout=2)
    
    def get_controller_cpu(self):
        """Get CPU usage of Ryu controller"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                if 'ryu-manager' in proc.info['name'] or 'python' in proc.info['name']:
                    cmdline = proc.cmdline()
                    if any('ryu-manager' in cmd or 'controller' in cmd for cmd in cmdline):
                        return proc.info['cpu_percent']
        except:
            pass
        return 0
    
    def measure_response_time(self, src, dst):
        """Measure initial connection response time"""
        start = time.time()
        result = src.cmd(f'ping -c 1 -W 2 {dst.IP()}')
        elapsed = (time.time() - start) * 1000  # Convert to ms
        
        if '1 received' in result or '1 packets received' in result:
            return elapsed
        return None
    
    def measure_delay(self, src, dst, count=50):
        """Measure RTT delay using ping"""
        result = src.cmd(f'ping -c {count} -i 0.01 {dst.IP()}')
        
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
    
    def run_iperf_flow(self, src_name, dst_name, bandwidth, duration, protocol='tcp', port=5001):
        """Run single iperf flow and return results"""
        src = self.net.get(src_name)
        dst = self.net.get(dst_name)
        
        # Start server
        dst.popen(f'iperf3 -s -p {port}', shell=True)
        time.sleep(0.5)
        
        # Run client
        output_file = f'/tmp/iperf_{src_name}_{dst_name}_{port}.json'
        
        if protocol == 'tcp':
            cmd = f'iperf3 -c {dst.IP()} -p {port} -t {duration} -b {bandwidth} -J > {output_file}'
        else:
            cmd = f'iperf3 -c {dst.IP()} -p {port} -u -t {duration} -b {bandwidth} -J > {output_file}'
        
        client_proc = src.popen(cmd, shell=True)
        client_proc.wait()
        
        # Parse results
        result_data = {
            'throughput': 0,
            'jitter': 0,
            'packet_loss': 0
        }
        
        try:
            result = src.cmd(f'cat {output_file}')
            data = json.loads(result)
            
            if 'end' in data:
                end_data = data['end']
                
                # Throughput
                if protocol == 'tcp' and 'sum_received' in end_data:
                    result_data['throughput'] = end_data['sum_received']['bits_per_second'] / 1e6
                elif protocol == 'udp' and 'sum' in end_data:
                    result_data['throughput'] = end_data['sum']['bits_per_second'] / 1e6
                    result_data['jitter'] = end_data['sum'].get('jitter_ms', 0)
                    result_data['packet_loss'] = end_data['sum'].get('lost_percent', 0)
        except Exception as e:
            pass
        
        # Cleanup
        src.cmd(f'rm -f {output_file}')
        dst.cmd(f'pkill -9 -f "iperf3 -s -p {port}"')
        
        return result_data
    
    def get_flow_distribution(self):
        """Get flow distribution for fairness calculation"""
        flow_counts = []
        
        # Check edge switches uplink ports
        for switch_num in range(13, 21):
            switch_name = f's{switch_num}'
            try:
                result = self.net.get(switch_name).cmd(
                    f'ovs-ofctl dump-flows {switch_name} -O OpenFlow13'
                )
                
                port3_packets = 0
                port4_packets = 0
                
                for line in result.split('\n'):
                    if 'priority=10' in line and 'n_packets=' in line:
                        try:
                            packets = int(line.split('n_packets=')[1].split(',')[0])
                            if 'output:3' in line or 'output:"s' in line and '-eth3"' in line:
                                port3_packets += packets
                            elif 'output:4' in line or 'output:"s' in line and '-eth4"' in line:
                                port4_packets += packets
                        except:
                            pass
                
                if port3_packets > 0:
                    flow_counts.append(port3_packets)
                if port4_packets > 0:
                    flow_counts.append(port4_packets)
            except:
                pass
        
        return flow_counts
    
    def run_traffic_with_metrics(self, flows, collector, measure_all_metrics=True):
        """
        Run traffic flows and measure all metrics
        flows: list of (src, dst, bandwidth, duration, protocol, port, label)
        """
        info(f"\nRunning {len(flows)} flows with complete metrics measurement...\n")
        
        hosts = {f'h{i}': self.net.get(f'h{i}') for i in range(1, 17)}
        
        # 1. Measure Response Time (first packet latency)
        if measure_all_metrics:
            info("\nPhase 1: Measuring Response Time...\n")
            sample_flows = flows[:min(5, len(flows))]  # Sample first 5 flows
            for src, dst, bw, _, _, _, label in sample_flows:
                rt = self.measure_response_time(hosts[src], hosts[dst])
                if rt:
                    collector.metrics['response_time'].append(rt)
                    info(f"   {src}->{dst}: {rt:.2f} ms\n")
        
        # 2. Measure Delay (RTT) before traffic starts
        if measure_all_metrics:
            info("\nPhase 2: Measuring Baseline Delay...\n")
            sample_flows = flows[:min(5, len(flows))]  # Sample
            for src, dst, _, _, _, _, label in sample_flows:
                delay = self.measure_delay(hosts[src], hosts[dst], count=30)
                if delay:
                    collector.metrics['delay'].append(delay)
                    info(f"   {src}->{dst}: {delay['avg']:.2f} ms (avg)\n")
        
        # 3. Start CPU monitoring
        info("\nPhase 3: Starting traffic and monitoring...\n")
        self.start_cpu_monitoring(collector)
        
        # 4. Run flows concurrently
        threads = []
        flow_results = []
        
        for src, dst, bw, dur, proto, port, label in flows:
            def run_flow(s, d, bandwidth, duration, protocol, p, lbl):
                info(f"  Starting {lbl}: {s}->{d} ({bandwidth}, {duration}s, {protocol.upper()})\n")
                result = self.run_iperf_flow(s, d, bandwidth, duration, protocol, p)
                result['label'] = lbl
                result['src'] = s
                result['dst'] = d
                result['protocol'] = protocol
                result['bandwidth_requested'] = bandwidth
                flow_results.append(result)
            
            t = threading.Thread(
                target=run_flow, 
                args=(src, dst, bw, dur, proto, port, label)
            )
            t.start()
            threads.append(t)
            time.sleep(0.3)  # Stagger start
        
        # Wait for all flows to complete
        for t in threads:
            t.join()
        
        # 5. Stop CPU monitoring
        self.stop_cpu_monitoring()
        
        # 6. Collect metrics from flow results
        info("\nPhase 4: Collecting flow metrics...\n")
        for result in flow_results:
            # Record flow info
            collector.metrics['flows'].append({
                'src': result['src'],
                'dst': result['dst'],
                'protocol': result['protocol'],
                'throughput': result['throughput'],
                'jitter': result['jitter'],
                'packet_loss': result['packet_loss'],
                'label': result['label'],
                'bandwidth_requested': result['bandwidth_requested']
            })
            
            # Aggregate metrics
            if result['protocol'] == 'tcp':
                if result['throughput'] > 0:
                    collector.metrics['throughput']['tcp'].append(result['throughput'])
            else:
                if result['throughput'] > 0:
                    collector.metrics['throughput']['udp'].append(result['throughput'])
                if result['jitter'] > 0:
                    collector.metrics['jitter'].append(result['jitter'])
                if result['packet_loss'] >= 0:
                    collector.metrics['packet_loss'].append(result['packet_loss'])
            
            info(f"   Done {result['label']}: {result['throughput']:.2f} Mbps")
            if result['protocol'] == 'udp':
                info(f", Jitter: {result['jitter']:.4f} ms, Loss: {result['packet_loss']:.2f}%")
            info("\n")
        
        # 7. Measure Delay after traffic (see if there's impact)
        if measure_all_metrics:
            info("\nPhase 5: Measuring Post-Traffic Delay...\n")
            sample_flows = flows[:min(3, len(flows))]
            for src, dst, _, _, _, _, label in sample_flows:
                delay = self.measure_delay(hosts[src], hosts[dst], count=30)
                if delay:
                    collector.metrics['delay'].append(delay)
                    info(f"   {src}->{dst}: {delay['avg']:.2f} ms\n")
        
        # 8. Calculate Normalized Fairness Index
        info("\nPhase 6: Calculating Normalized Fairness Index...\n")
        collector.metrics['fairness_index'] = collector.calculate_normalized_fairness()
        info(f"   Fairness Index: {collector.metrics['fairness_index']:.4f}\n")
    
    # ==================== SCENARIOS ====================
    
    def scenario_voip_video_data_mix(self):
        """Scenario 1: VoIP + Video Conference + File Transfer + Web"""
        info("\n" + "="*70 + "\n")
        info("SCENARIO 1: VoIP + Video Conference + Data Mix\n")
        info("="*70 + "\n")
        
        collector = MetricsCollector("voip_video_data_mix", self.algorithm)
        
        # Define flows with proper TCP/UDP mix
        flows = [
            # Video Conferences (TCP, bidirectional)
            ('h1', 'h9', '4M', 90, 'tcp', 5001, 'VideoConf-1-Out'),
            ('h9', 'h1', '4M', 90, 'tcp', 5002, 'VideoConf-1-Return'),
            ('h2', 'h10', '5M', 90, 'tcp', 5003, 'VideoConf-2-Out'),
            ('h10', 'h2', '5M', 90, 'tcp', 5004, 'VideoConf-2-Return'),
            
            # VoIP Calls (UDP for jitter measurement!)
            ('h5', 'h13', '80K', 90, 'udp', 5009, 'VoIP-1-Out'),
            ('h13', 'h5', '80K', 90, 'udp', 5010, 'VoIP-1-Return'),
            ('h6', 'h14', '100K', 90, 'udp', 5011, 'VoIP-2-Out'),
            ('h14', 'h6', '100K', 90, 'udp', 5012, 'VoIP-2-Return'),
            
            # File Transfers (TCP)
            ('h3', 'h11', '80M', 90, 'tcp', 5015, 'FileTransfer-1'),
            ('h4', 'h12', '100M', 90, 'tcp', 5016, 'FileTransfer-2'),
            
            # Web Browsing (TCP)
            ('h7', 'h15', '10M', 90, 'tcp', 5017, 'Web-1'),
            ('h8', 'h16', '8M', 90, 'tcp', 5018, 'Web-2'),
        ]
        
        self.run_traffic_with_metrics(flows, collector)
        
        collector.finalize()
        collector.print_summary()
        
        return collector.metrics
    
    def scenario_live_streaming(self):
        """Scenario 2: Live Streaming Platform (Multiple Qualities)"""
        info("\n" + "="*70 + "\n")
        info("SCENARIO 2: Live Streaming Platform\n")
        info("="*70 + "\n")
        
        collector = MetricsCollector("live_streaming", self.algorithm)
        
        info("\nSimulating streaming platform with mixed quality streams...\n")
        
        flows = [
            # 4K Streams (TCP)
            ('h1', 'h9', '25M', 60, 'tcp', 6001, '4K-Stream-1'),
            ('h2', 'h10', '25M', 60, 'tcp', 6002, '4K-Stream-2'),
            
            # 1080p Streams (TCP)
            ('h3', 'h11', '8M', 60, 'tcp', 6003, '1080p-Stream-1'),
            ('h4', 'h12', '8M', 60, 'tcp', 6004, '1080p-Stream-2'),
            ('h5', 'h13', '8M', 60, 'tcp', 6005, '1080p-Stream-3'),
            
            # 720p Streams (TCP)
            ('h6', 'h14', '5M', 60, 'tcp', 6006, '720p-Stream-1'),
            ('h7', 'h15', '5M', 60, 'tcp', 6007, '720p-Stream-2'),
            ('h8', 'h16', '5M', 60, 'tcp', 6008, '720p-Stream-3'),
            
            # 480p Streams (TCP) - Mobile users
            ('h1', 'h13', '2500K', 60, 'tcp', 6009, '480p-Stream-1'),
            ('h2', 'h14', '2500K', 60, 'tcp', 6010, '480p-Stream-2'),
            
            # Add some UDP streaming (like live sports/gaming)
            ('h3', 'h15', '10M', 60, 'udp', 6011, 'LiveSports-UDP-1'),
            ('h4', 'h16', '10M', 60, 'udp', 6012, 'LiveSports-UDP-2'),
        ]
        
        self.run_traffic_with_metrics(flows, collector)
        
        collector.finalize()
        collector.print_summary()
        
        return collector.metrics
    
    def scenario_elephant_mice(self):
        """Scenario 3: Elephant vs Mice Flows"""
        info("\n" + "="*70 + "\n")
        info("SCENARIO 3: Elephant vs Mice Flows\n")
        info("="*70 + "\n")
        
        collector = MetricsCollector("elephant_mice", self.algorithm)
        
        info("\nPhase 1: Starting Elephant flows...\n")
        
        # Elephant flows (long-lived, high bandwidth)
        elephant_flows = [
            ('h1', 'h9', '80M', 120, 'tcp', 7001, 'Elephant-TCP-1'),
            ('h2', 'h10', '80M', 120, 'tcp', 7002, 'Elephant-TCP-2'),
            ('h3', 'h11', '50M', 120, 'udp', 7003, 'Elephant-UDP-1'),
        ]
        
        # Start elephant flows
        elephant_threads = []
        for src, dst, bw, dur, proto, port, label in elephant_flows:
            def run_elephant(s, d, bandwidth, duration, protocol, p, lbl):
                info(f"  {lbl}: {s}->{d} ({bandwidth}, {duration}s)\n")
                result = self.run_iperf_flow(s, d, bandwidth, duration, protocol, p)
                collector.metrics['flows'].append({
                    'src': s, 'dst': d, 'protocol': protocol,
                    'throughput': result['throughput'],
                    'jitter': result['jitter'],
                    'packet_loss': result['packet_loss'],
                    'label': lbl,
                    'bandwidth_requested': bandwidth
                })
                
                if protocol == 'tcp':
                    collector.metrics['throughput']['tcp'].append(result['throughput'])
                else:
                    collector.metrics['throughput']['udp'].append(result['throughput'])
                    if result['jitter'] > 0:
                        collector.metrics['jitter'].append(result['jitter'])
                    collector.metrics['packet_loss'].append(result['packet_loss'])
            
            t = threading.Thread(target=run_elephant, 
                               args=(src, dst, bw, dur, proto, port, label))
            t.start()
            elephant_threads.append(t)
        
        # Start CPU monitoring
        self.start_cpu_monitoring(collector)
        
        # Inject mice flows periodically
        info("\nPhase 2: Injecting Mice flows (every 10 seconds)...\n")
        for round_num in range(6):
            time.sleep(10)
            info(f"\n   Round {round_num + 1}: Starting mice flows...\n")
            
            mice_flows = [
                (f'h{(round_num % 4) + 4}', f'h{(round_num % 4) + 12}', '5M', 5, 'tcp', 7100+round_num*2, f'Mouse-TCP-R{round_num+1}'),
                (f'h{(round_num % 4) + 5}', f'h{(round_num % 4) + 13}', '3M', 5, 'udp', 7101+round_num*2, f'Mouse-UDP-R{round_num+1}'),
            ]
            
            mice_threads = []
            for src, dst, bw, dur, proto, port, label in mice_flows:
                def run_mouse(s, d, bandwidth, duration, protocol, p, lbl):
                    info(f"  {lbl}: {s}->{d} ({bandwidth}, {duration}s)\n")
                    result = self.run_iperf_flow(s, d, bandwidth, duration, protocol, p)
                    collector.metrics['flows'].append({
                        'src': s, 'dst': d, 'protocol': protocol,
                        'throughput': result['throughput'],
                        'jitter': result['jitter'],
                        'packet_loss': result['packet_loss'],
                        'label': lbl,
                        'bandwidth_requested': bandwidth
                    })
                    
                    if protocol == 'tcp':
                        collector.metrics['throughput']['tcp'].append(result['throughput'])
                    else:
                        collector.metrics['throughput']['udp'].append(result['throughput'])
                        if result['jitter'] > 0:
                            collector.metrics['jitter'].append(result['jitter'])
                        collector.metrics['packet_loss'].append(result['packet_loss'])
                
                t = threading.Thread(target=run_mouse,
                                   args=(src, dst, bw, dur, proto, port, label))
                t.start()
                mice_threads.append(t)
            
            # Wait for mice to finish
            for t in mice_threads:
                t.join()
        
        # Wait for elephants
        info("\nPhase 3: Waiting for elephant flows to complete...\n")
        for t in elephant_threads:
            t.join()
        
        self.stop_cpu_monitoring()
        
        # Measure final metrics
        info("\nMeasuring final metrics...\n")
        sample_pairs = [('h1', 'h9'), ('h2', 'h10'), ('h3', 'h11')]
        for src, dst in sample_pairs:
            hosts = self.net.get(src), self.net.get(dst)
            delay = self.measure_delay(hosts[0], hosts[1], count=30)
            if delay:
                collector.metrics['delay'].append(delay)
        
        # Calculate Normalized Fairness
        collector.metrics['fairness_index'] = collector.calculate_normalized_fairness()
        
        collector.finalize()
        collector.print_summary()
        
        return collector.metrics
    
    def scenario_mixed_load(self):
        """Scenario 4: Mixed Load (Light, Medium, Heavy bandwidth)"""
        info("\n" + "="*70 + "\n")
        info("SCENARIO 4: Mixed Load Test\n")
        info("="*70 + "\n")
        
        collector = MetricsCollector("mixed_load", self.algorithm)
        
        flows = [
            # Heavy flows (TCP)
            ('h1', 'h9', '100M', 60, 'tcp', 8001, 'Heavy-TCP-1'),
            ('h2', 'h10', '100M', 60, 'tcp', 8002, 'Heavy-TCP-2'),
            
            # Medium flows (TCP)
            ('h3', 'h11', '30M', 60, 'tcp', 8003, 'Medium-TCP-1'),
            ('h4', 'h12', '30M', 60, 'tcp', 8004, 'Medium-TCP-2'),
            ('h5', 'h13', '30M', 60, 'tcp', 8005, 'Medium-TCP-3'),
            
            # Light flows (TCP)
            ('h6', 'h14', '5M', 60, 'tcp', 8006, 'Light-TCP-1'),
            ('h7', 'h15', '5M', 60, 'tcp', 8007, 'Light-TCP-2'),
            
            # Very light flows (UDP - for jitter!)
            ('h8', 'h16', '500K', 60, 'udp', 8008, 'VeryLight-UDP-1'),
            ('h1', 'h13', '500K', 60, 'udp', 8009, 'VeryLight-UDP-2'),
            ('h2', 'h14', '1M', 60, 'udp', 8010, 'VeryLight-UDP-3'),
        ]
        
        self.run_traffic_with_metrics(flows, collector)
        
        collector.finalize()
        collector.print_summary()
        
        return collector.metrics


def main():
    import sys
    
    if len(sys.argv) < 3:
        info("\n" + "="*70 + "\n")
        info("Comprehensive Load Balancing Test\n")
        info("="*70 + "\n")
        info("\nUsage: sudo python3 test_comprehensive.py [wrr|wlc] [scenario]\n")
        info("\nScenarios:\n")
        info("  1 or office      - VoIP + Video Conference + Data Mix\n")
        info("  2 or streaming   - Live Streaming Platform (4K/1080p/720p/480p)\n")
        info("  3 or elephant    - Elephant vs Mice Flows\n")
        info("  4 or mixed       - Mixed Load (Heavy/Medium/Light)\n")
        info("  all              - Run all scenarios\n")
        info("\nFeatures:\n")
        info("  - Complete metrics: Throughput, Delay, Jitter, Packet Loss\n")
        info("  - CPU Utilization monitoring\n")
        info("  - Normalized Fairness Index calculation\n")
        info("  - Response Time measurement\n")
        info("  - TCP + UDP traffic mix\n")
        info("  - Real-world heterogeneous traffic patterns\n")
        info("  - Auto-export to CSV\n")
        info("\nExample:\n")
        info("  sudo python3 test_comprehensive.py wrr office\n")
        info("  sudo python3 test_comprehensive.py wlc all\n")
        info("\n" + "="*70 + "\n")
        sys.exit(1)
    
    algorithm = sys.argv[1].lower()
    scenario = sys.argv[2].lower()
    
    if algorithm not in ['wrr', 'wlc']:
        info("Error: Algorithm must be 'wrr' or 'wlc'\n")
        sys.exit(1)
    
    info("\n" + "="*70 + "\n")
    info(f"COMPREHENSIVE LOAD BALANCING TEST\n")
    info(f"Algorithm: {algorithm.upper()}\n")
    info(f"Scenario: {scenario}\n")
    info("="*70 + "\n")
    
    info("\nIMPORTANT: Make sure Ryu controller is running!\n")
    controller_file = "weighted_round_robin_controller.py" if algorithm == 'wrr' \
                     else "weighted_least_connection_controller.py"
    info(f"Command: ryu-manager --ofp-tcp-listen-port 6653 controllers/{controller_file} --verbose\n")
    
    input("\nPress Enter when controller is ready...")
    
    tester = ComprehensiveTester(algorithm)
    
    try:
        tester.setup_network()
        
        results_summary = []
        
        if scenario in ['1', 'office']:
            result = tester.scenario_voip_video_data_mix()
            results_summary.append(('Office Workload', result))
            
        elif scenario in ['2', 'streaming']:
            result = tester.scenario_live_streaming()
            results_summary.append(('Live Streaming', result))
            
        elif scenario in ['3', 'elephant']:
            result = tester.scenario_elephant_mice()
            results_summary.append(('Elephant vs Mice', result))
            
        elif scenario in ['4', 'mixed']:
            result = tester.scenario_mixed_load()
            results_summary.append(('Mixed Load', result))
            
        elif scenario == 'all':
            info("\n" + "="*70 + "\n")
            info("RUNNING ALL SCENARIOS (This will take ~30-40 minutes)\n")
            info("="*70 + "\n")
            
            result1 = tester.scenario_voip_video_data_mix()
            results_summary.append(('Office Workload', result1))
            time.sleep(10)
            
            result2 = tester.scenario_live_streaming()
            results_summary.append(('Live Streaming', result2))
            time.sleep(10)
            
            result3 = tester.scenario_elephant_mice()
            results_summary.append(('Elephant vs Mice', result3))
            time.sleep(10)
            
            result4 = tester.scenario_mixed_load()
            results_summary.append(('Mixed Load', result4))
            
            # Print overall summary
            info("\n" + "="*70 + "\n")
            info("OVERALL SUMMARY - ALL SCENARIOS\n")
            info("="*70 + "\n")
            
            for name, result in results_summary:
                info(f"\n{name}:\n")
                if result['throughput']['tcp']:
                    tcp_avg = sum(result['throughput']['tcp']) / len(result['throughput']['tcp'])
                    info(f"  - TCP Throughput: {tcp_avg:.2f} Mbps\n")
                if result['throughput']['udp']:
                    udp_avg = sum(result['throughput']['udp']) / len(result['throughput']['udp'])
                    info(f"  - UDP Throughput: {udp_avg:.2f} Mbps\n")
                if result['jitter']:
                    jitter_avg = sum(result['jitter']) / len(result['jitter'])
                    info(f"  - Jitter: {jitter_avg:.4f} ms\n")
                if result['delay']:
                    delay_avg = sum(d['avg'] for d in result['delay']) / len(result['delay'])
                    info(f"  - Delay: {delay_avg:.2f} ms\n")
                info(f"  - CPU: {result['cpu_utilization']['avg']:.2f}%\n")
                info(f"  - Fairness Index: {result['fairness_index']:.4f}\n")
            
            info("\n" + "="*70 + "\n")
            
        else:
            info(f"Unknown scenario: {scenario}\n")
            sys.exit(1)
        
        info("\nALL TESTS COMPLETED SUCCESSFULLY!\n")
        info(f"Results saved in: results/comprehensive/{algorithm}/\n\n")
        
    except KeyboardInterrupt:
        info("\n\nTest interrupted by user\n")
    except Exception as e:
        info(f"\n\nError occurred: {e}\n")
        import traceback
        traceback.print_exc()
    finally:
        tester.cleanup()


if __name__ == '__main__':
    setLogLevel('info')
    main()