import json
import os
import glob
from datetime import datetime
import csv


class ResultsExporter:
    """Export test results to Excel and CSV"""
    
    def __init__(self, results_dir="results/comprehensive"):
        self.results_dir = results_dir
        self.export_dir = "results/exports"
        os.makedirs(self.export_dir, exist_ok=True)
    
    def find_all_results(self):
        """Find all JSON result files"""
        pattern = f"{self.results_dir}/**/*.json"
        files = glob.glob(pattern, recursive=True)
        return files
    
    def load_json(self, filepath):
        """Load JSON file"""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except:
            return None
    
    def export_summary_csv(self, results_files):
        """Export summary of all tests to CSV"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_file = f"{self.export_dir}/summary_{timestamp}.csv"
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Scenario',
                'Algorithm',
                'TCP Throughput Avg (Mbps)',
                'TCP Throughput Min (Mbps)',
                'TCP Throughput Max (Mbps)',
                'UDP Throughput Avg (Mbps)',
                'UDP Throughput Min (Mbps)',
                'UDP Throughput Max (Mbps)',
                'Delay Avg (ms)',
                'Delay Min (ms)',
                'Delay Max (ms)',
                'Jitter Avg (ms)',
                'Jitter Min (ms)',
                'Jitter Max (ms)',
                'Packet Loss Avg (%)',
                'Packet Loss Max (%)',
                'CPU Avg (%)',
                'CPU Max (%)',
                'CPU Min (%)',
                'Fairness Index',
                'Response Time Avg (ms)',
                'Total Flows',
                'TCP Flows',
                'UDP Flows',
                'Test Date'
            ])
            
            # Data rows
            for filepath in results_files:
                data = self.load_json(filepath)
                if not data:
                    continue
                
                # Calculate statistics
                tcp_throughput = data.get('throughput', {}).get('tcp', [])
                udp_throughput = data.get('throughput', {}).get('udp', [])
                delays = data.get('delay', [])
                jitters = data.get('jitter', [])
                packet_loss = data.get('packet_loss', [])
                cpu = data.get('cpu_utilization', {})
                response_times = data.get('response_time', [])
                flows = data.get('flows', [])
                
                # TCP Throughput stats
                tcp_avg = sum(tcp_throughput) / len(tcp_throughput) if tcp_throughput else 0
                tcp_min = min(tcp_throughput) if tcp_throughput else 0
                tcp_max = max(tcp_throughput) if tcp_throughput else 0
                
                # UDP Throughput stats
                udp_avg = sum(udp_throughput) / len(udp_throughput) if udp_throughput else 0
                udp_min = min(udp_throughput) if udp_throughput else 0
                udp_max = max(udp_throughput) if udp_throughput else 0
                
                # Delay stats
                if delays:
                    delay_avgs = [d['avg'] for d in delays]
                    delay_avg = sum(delay_avgs) / len(delay_avgs)
                    delay_min = min([d['min'] for d in delays])
                    delay_max = max([d['max'] for d in delays])
                else:
                    delay_avg = delay_min = delay_max = 0
                
                # Jitter stats
                jitter_avg = sum(jitters) / len(jitters) if jitters else 0
                jitter_min = min(jitters) if jitters else 0
                jitter_max = max(jitters) if jitters else 0
                
                # Packet loss stats
                loss_avg = sum(packet_loss) / len(packet_loss) if packet_loss else 0
                loss_max = max(packet_loss) if packet_loss else 0
                
                # Response time
                rt_avg = sum(response_times) / len(response_times) if response_times else 0
                
                # Flow counts
                tcp_flows = len([f for f in flows if f.get('protocol') == 'tcp'])
                udp_flows = len([f for f in flows if f.get('protocol') == 'udp'])
                
                writer.writerow([
                    data.get('scenario', 'unknown'),
                    data.get('algorithm', 'unknown'),
                    f"{tcp_avg:.2f}",
                    f"{tcp_min:.2f}",
                    f"{tcp_max:.2f}",
                    f"{udp_avg:.4f}",
                    f"{udp_min:.4f}",
                    f"{udp_max:.4f}",
                    f"{delay_avg:.2f}",
                    f"{delay_min:.2f}",
                    f"{delay_max:.2f}",
                    f"{jitter_avg:.4f}",
                    f"{jitter_min:.4f}",
                    f"{jitter_max:.4f}",
                    f"{loss_avg:.4f}",
                    f"{loss_max:.4f}",
                    f"{cpu.get('avg', 0):.2f}",
                    f"{cpu.get('max', 0):.2f}",
                    f"{cpu.get('min', 0):.2f}",
                    f"{data.get('fairness_index', 0):.4f}",
                    f"{rt_avg:.2f}",
                    len(flows),
                    tcp_flows,
                    udp_flows,
                    data.get('start_time', 'unknown')
                ])
        
        print(f"✅ Summary exported to: {csv_file}")
        return csv_file
    
    def export_detailed_flows_csv(self, results_files):
        """Export detailed per-flow data to CSV"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_file = f"{self.export_dir}/detailed_flows_{timestamp}.csv"
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Scenario',
                'Algorithm',
                'Flow Label',
                'Source',
                'Destination',
                'Protocol',
                'Throughput (Mbps)',
                'Jitter (ms)',
                'Packet Loss (%)',
                'Test Date'
            ])
            
            # Data rows
            for filepath in results_files:
                data = self.load_json(filepath)
                if not data:
                    continue
                
                scenario = data.get('scenario', 'unknown')
                algorithm = data.get('algorithm', 'unknown')
                test_date = data.get('start_time', 'unknown')
                
                for flow in data.get('flows', []):
                    writer.writerow([
                        scenario,
                        algorithm,
                        flow.get('label', 'unknown'),
                        flow.get('src', 'unknown'),
                        flow.get('dst', 'unknown'),
                        flow.get('protocol', 'unknown'),
                        f"{flow.get('throughput', 0):.2f}",
                        f"{flow.get('jitter', 0):.4f}",
                        f"{flow.get('packet_loss', 0):.4f}",
                        test_date
                    ])
        
        print(f"✅ Detailed flows exported to: {csv_file}")
        return csv_file
    
    def export_comparison_csv(self, wrr_files, wlc_files):
        """Export side-by-side comparison of WRR vs WLC"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_file = f"{self.export_dir}/comparison_wrr_vs_wlc_{timestamp}.csv"
        
        # Group by scenario
        wrr_by_scenario = {}
        wlc_by_scenario = {}
        
        for filepath in wrr_files:
            data = self.load_json(filepath)
            if data:
                scenario = data.get('scenario', 'unknown')
                wrr_by_scenario[scenario] = data
        
        for filepath in wlc_files:
            data = self.load_json(filepath)
            if data:
                scenario = data.get('scenario', 'unknown')
                wlc_by_scenario[scenario] = data
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Scenario',
                'Metric',
                'WRR',
                'WLC',
                'Difference',
                'Better Algorithm'
            ])
            
            # Compare each scenario
            all_scenarios = set(wrr_by_scenario.keys()) | set(wlc_by_scenario.keys())
            
            for scenario in sorted(all_scenarios):
                wrr_data = wrr_by_scenario.get(scenario)
                wlc_data = wlc_by_scenario.get(scenario)
                
                if not wrr_data or not wlc_data:
                    continue
                
                # TCP Throughput
                wrr_tcp = wrr_data.get('throughput', {}).get('tcp', [])
                wlc_tcp = wlc_data.get('throughput', {}).get('tcp', [])
                if wrr_tcp and wlc_tcp:
                    wrr_avg = sum(wrr_tcp) / len(wrr_tcp)
                    wlc_avg = sum(wlc_tcp) / len(wlc_tcp)
                    diff = wlc_avg - wrr_avg
                    better = 'WLC' if wlc_avg > wrr_avg else 'WRR'
                    writer.writerow([
                        scenario,
                        'TCP Throughput (Mbps)',
                        f"{wrr_avg:.2f}",
                        f"{wlc_avg:.2f}",
                        f"{diff:+.2f}",
                        better
                    ])
                
                # Delay
                wrr_delay = wrr_data.get('delay', [])
                wlc_delay = wlc_data.get('delay', [])
                if wrr_delay and wlc_delay:
                    wrr_avg = sum(d['avg'] for d in wrr_delay) / len(wrr_delay)
                    wlc_avg = sum(d['avg'] for d in wlc_delay) / len(wlc_delay)
                    diff = wlc_avg - wrr_avg
                    better = 'WRR' if wrr_avg < wlc_avg else 'WLC'  # Lower is better
                    writer.writerow([
                        scenario,
                        'Delay (ms)',
                        f"{wrr_avg:.2f}",
                        f"{wlc_avg:.2f}",
                        f"{diff:+.2f}",
                        better
                    ])
                
                # Jitter
                wrr_jitter = wrr_data.get('jitter', [])
                wlc_jitter = wlc_data.get('jitter', [])
                if wrr_jitter and wlc_jitter:
                    wrr_avg = sum(wrr_jitter) / len(wrr_jitter)
                    wlc_avg = sum(wlc_jitter) / len(wlc_jitter)
                    diff = wlc_avg - wrr_avg
                    better = 'WRR' if wrr_avg < wlc_avg else 'WLC'  # Lower is better
                    writer.writerow([
                        scenario,
                        'Jitter (ms)',
                        f"{wrr_avg:.4f}",
                        f"{wlc_avg:.4f}",
                        f"{diff:+.4f}",
                        better
                    ])
                
                # Packet Loss
                wrr_loss = wrr_data.get('packet_loss', [])
                wlc_loss = wlc_data.get('packet_loss', [])
                if wrr_loss and wlc_loss:
                    wrr_avg = sum(wrr_loss) / len(wrr_loss)
                    wlc_avg = sum(wlc_loss) / len(wlc_loss)
                    diff = wlc_avg - wrr_avg
                    better = 'WRR' if wrr_avg < wlc_avg else 'WLC'  # Lower is better
                    writer.writerow([
                        scenario,
                        'Packet Loss (%)',
                        f"{wrr_avg:.4f}",
                        f"{wlc_avg:.4f}",
                        f"{diff:+.4f}",
                        better
                    ])
                
                # CPU
                wrr_cpu = wrr_data.get('cpu_utilization', {}).get('avg', 0)
                wlc_cpu = wlc_data.get('cpu_utilization', {}).get('avg', 0)
                if wrr_cpu > 0 and wlc_cpu > 0:
                    diff = wlc_cpu - wrr_cpu
                    better = 'WRR' if wrr_cpu < wlc_cpu else 'WLC'  # Lower is better
                    writer.writerow([
                        scenario,
                        'CPU Utilization (%)',
                        f"{wrr_cpu:.2f}",
                        f"{wlc_cpu:.2f}",
                        f"{diff:+.2f}",
                        better
                    ])
                
                # Fairness
                wrr_fair = wrr_data.get('fairness_index', 0)
                wlc_fair = wlc_data.get('fairness_index', 0)
                if wrr_fair > 0 and wlc_fair > 0:
                    diff = wlc_fair - wrr_fair
                    better = 'WLC' if wlc_fair > wrr_fair else 'WRR'  # Higher is better
                    writer.writerow([
                        scenario,
                        'Fairness Index',
                        f"{wrr_fair:.4f}",
                        f"{wlc_fair:.4f}",
                        f"{diff:+.4f}",
                        better
                    ])
                
                # Add blank row between scenarios
                writer.writerow([])
        
        print(f"✅ Comparison exported to: {csv_file}")
        return csv_file
    
    def export_all(self):
        """Export all formats"""
        print("\n" + "="*70)
        print("📊 EXPORTING RESULTS TO CSV")
        print("="*70 + "\n")
        
        # Find all result files
        all_files = self.find_all_results()
        
        if not all_files:
            print("❌ No result files found!")
            print(f"   Looking in: {self.results_dir}")
            return
        
        print(f"Found {len(all_files)} result file(s)\n")
        
        # Separate WRR and WLC files
        wrr_files = [f for f in all_files if '/wrr/' in f]
        wlc_files = [f for f in all_files if '/wlc/' in f]
        
        print(f"  • WRR results: {len(wrr_files)}")
        print(f"  • WLC results: {len(wlc_files)}\n")
        
        # Export summary
        print("1️⃣  Exporting summary...")
        self.export_summary_csv(all_files)
        
        # Export detailed flows
        print("\n2️⃣  Exporting detailed flows...")
        self.export_detailed_flows_csv(all_files)
        
        # Export comparison if both WRR and WLC exist
        if wrr_files and wlc_files:
            print("\n3️⃣  Exporting WRR vs WLC comparison...")
            self.export_comparison_csv(wrr_files, wlc_files)
        else:
            print("\n⚠️  Skipping comparison (need both WRR and WLC results)")
        
        print("\n" + "="*70)
        print("✅ EXPORT COMPLETED!")
        print(f"📁 All CSV files saved to: {self.export_dir}/")
        print("="*70 + "\n")


def main():
    import sys
    
    # Check if custom directory provided
    if len(sys.argv) > 1:
        results_dir = sys.argv[1]
    else:
        results_dir = "results/comprehensive"
    
    print("\n" + "="*70)
    print("📊 Test Results Export Tool")
    print("="*70)
    print(f"\n📂 Source directory: {results_dir}")
    print(f"📁 Export directory: results/exports/\n")
    
    if not os.path.exists(results_dir):
        print(f"❌ Error: Directory '{results_dir}' not found!")
        print("\nUsage:")
        print("  python3 export_results_to_excel.py [results_directory]")
        print("\nExample:")
        print("  python3 export_results_to_excel.py results/comprehensive")
        sys.exit(1)
    
    exporter = ResultsExporter(results_dir)
    exporter.export_all()
    
    print("\n💡 TIP: You can now open these CSV files in:")
    print("   • Microsoft Excel")
    print("   • Google Sheets")
    print("   • LibreOffice Calc")
    print("   • Python pandas for further analysis\n")


if __name__ == '__main__':
    main()