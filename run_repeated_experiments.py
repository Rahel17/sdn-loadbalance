import subprocess
import time
import json
import os
import glob
from datetime import datetime
import numpy as np


class RepeatedExperimentRunner:
    """Run experiments multiple times and aggregate results"""
    
    def __init__(self, algorithm="wrr", num_runs=5):
        self.algorithm = algorithm
        self.num_runs = num_runs
        self.base_results_dir = f"results/comprehensive/{algorithm}"
        self.aggregate_dir = f"results/aggregated/{algorithm}"
        os.makedirs(self.aggregate_dir, exist_ok=True)
        
        self.scenarios = ['office', 'streaming', 'elephant', 'mixed']
        self.scenario_names = {
            'office': 'voip_video_data_mix',
            'streaming': 'live_streaming',
            'elephant': 'elephant_mice',
            'mixed': 'mixed_load'
        }
    
    def run_single_experiment(self, scenario, run_number):
        """Run a single experiment"""
        print(f"\n{'='*70}")
        print(f"RUN {run_number}/{self.num_runs}: {scenario.upper()}")
        print(f"Algorithm: {self.algorithm.upper()}")
        print(f"{'='*70}\n")
        
        # Run test_comprehensive.py
        cmd = [
            'sudo', 'python3', 'test_comprehensive.py',
            self.algorithm, scenario
        ]
        
        try:
            # Run the command
            result = subprocess.run(
                cmd,
                input='\n',  # Auto-press Enter for controller ready prompt
                text=True,
                capture_output=False,
                timeout=600  # 10 minutes timeout per scenario
            )
            
            if result.returncode == 0:
                print(f"\nRun {run_number} completed successfully!")
                return True
            else:
                print(f"\nRun {run_number} failed with return code {result.returncode}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"\nRun {run_number} timed out!")
            return False
        except Exception as e:
            print(f"\nRun {run_number} failed with error: {e}")
            return False
    
    def collect_results_for_scenario(self, scenario):
        """Collect all results for a specific scenario"""
        scenario_name = self.scenario_names[scenario]
        pattern = f"{self.base_results_dir}/{scenario_name}_*/metrics.json"
        files = sorted(glob.glob(pattern))
        
        # Get the last N files (most recent runs)
        if len(files) > self.num_runs:
            files = files[-self.num_runs:]
        
        results = []
        for filepath in files:
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    results.append(data)
            except:
                continue
        
        return results
    
    def aggregate_metrics(self, results_list):
        """Aggregate metrics from multiple runs"""
        if not results_list:
            return None
        
        aggregated = {
            'scenario': results_list[0]['scenario'],
            'algorithm': results_list[0]['algorithm'],
            'num_runs': len(results_list),
            'metrics': {}
        }
        
        # TCP Throughput
        tcp_throughputs = []
        for result in results_list:
            tcp = result.get('throughput', {}).get('tcp', [])
            if tcp:
                tcp_throughputs.append(sum(tcp) / len(tcp))
        
        if tcp_throughputs:
            aggregated['metrics']['tcp_throughput'] = {
                'mean': np.mean(tcp_throughputs),
                'std': np.std(tcp_throughputs),
                'min': np.min(tcp_throughputs),
                'max': np.max(tcp_throughputs),
                'values': tcp_throughputs
            }
        
        # UDP Throughput
        udp_throughputs = []
        for result in results_list:
            udp = result.get('throughput', {}).get('udp', [])
            if udp:
                udp_throughputs.append(sum(udp) / len(udp))
        
        if udp_throughputs:
            aggregated['metrics']['udp_throughput'] = {
                'mean': np.mean(udp_throughputs),
                'std': np.std(udp_throughputs),
                'min': np.min(udp_throughputs),
                'max': np.max(udp_throughputs),
                'values': udp_throughputs
            }
        
        # Delay
        delays = []
        for result in results_list:
            delay_data = result.get('delay', [])
            if delay_data:
                avg_delay = sum(d['avg'] for d in delay_data) / len(delay_data)
                delays.append(avg_delay)
        
        if delays:
            aggregated['metrics']['delay'] = {
                'mean': np.mean(delays),
                'std': np.std(delays),
                'min': np.min(delays),
                'max': np.max(delays),
                'values': delays
            }
        
        # Jitter
        jitters = []
        for result in results_list:
            jitter_data = result.get('jitter', [])
            if jitter_data:
                avg_jitter = sum(jitter_data) / len(jitter_data)
                jitters.append(avg_jitter)
        
        if jitters:
            aggregated['metrics']['jitter'] = {
                'mean': np.mean(jitters),
                'std': np.std(jitters),
                'min': np.min(jitters),
                'max': np.max(jitters),
                'values': jitters
            }
        
        # Packet Loss
        losses = []
        for result in results_list:
            loss_data = result.get('packet_loss', [])
            if loss_data:
                avg_loss = sum(loss_data) / len(loss_data)
                losses.append(avg_loss)
        
        if losses:
            aggregated['metrics']['packet_loss'] = {
                'mean': np.mean(losses),
                'std': np.std(losses),
                'min': np.min(losses),
                'max': np.max(losses),
                'values': losses
            }
        
        # CPU Utilization
        cpus = []
        for result in results_list:
            cpu = result.get('cpu_utilization', {}).get('avg', 0)
            if cpu > 0:
                cpus.append(cpu)
        
        if cpus:
            aggregated['metrics']['cpu'] = {
                'mean': np.mean(cpus),
                'std': np.std(cpus),
                'min': np.min(cpus),
                'max': np.max(cpus),
                'values': cpus
            }
        
        # Fairness Index
        fairness = []
        for result in results_list:
            fi = result.get('fairness_index', 0)
            if fi > 0:
                fairness.append(fi)
        
        if fairness:
            aggregated['metrics']['fairness_index'] = {
                'mean': np.mean(fairness),
                'std': np.std(fairness),
                'min': np.min(fairness),
                'max': np.max(fairness),
                'values': fairness
            }
        
        # Response Time
        response_times = []
        for result in results_list:
            rt_data = result.get('response_time', [])
            if rt_data:
                avg_rt = sum(rt_data) / len(rt_data)
                response_times.append(avg_rt)
        
        if response_times:
            aggregated['metrics']['response_time'] = {
                'mean': np.mean(response_times),
                'std': np.std(response_times),
                'min': np.min(response_times),
                'max': np.max(response_times),
                'values': response_times
            }
        
        # Store individual run details
        aggregated['individual_runs'] = []
        for i, result in enumerate(results_list):
            run_summary = {
                'run_number': i + 1,
                'timestamp': result.get('start_time', 'unknown'),
                'tcp_throughput': sum(result.get('throughput', {}).get('tcp', [])) / len(result.get('throughput', {}).get('tcp', [1])),
                'fairness_index': result.get('fairness_index', 0),
                'cpu_avg': result.get('cpu_utilization', {}).get('avg', 0)
            }
            aggregated['individual_runs'].append(run_summary)
        
        return aggregated
    
    def save_aggregated_results(self, scenario, aggregated):
        """Save aggregated results to JSON"""
        filepath = f"{self.aggregate_dir}/{scenario}_aggregated.json"
        
        with open(filepath, 'w') as f:
            json.dump(aggregated, f, indent=2, default=str)
        
        print(f"\nAggregated results saved to: {filepath}")
    
    def print_aggregated_summary(self, scenario, aggregated):
        """Print summary of aggregated results"""
        print(f"\n{'='*70}")
        print(f"AGGREGATED RESULTS: {scenario.upper()}")
        print(f"Algorithm: {self.algorithm.upper()}")
        print(f"Number of runs: {aggregated['num_runs']}")
        print(f"{'='*70}\n")
        
        metrics = aggregated['metrics']
        
        if 'tcp_throughput' in metrics:
            m = metrics['tcp_throughput']
            print(f"TCP Throughput:")
            print(f"  Mean:   {m['mean']:.2f} ± {m['std']:.2f} Mbps")
            print(f"  Range:  [{m['min']:.2f}, {m['max']:.2f}] Mbps")
            print(f"  Values: {[f'{v:.2f}' for v in m['values']]}")
        
        if 'udp_throughput' in metrics:
            m = metrics['udp_throughput']
            print(f"\nUDP Throughput:")
            print(f"  Mean:   {m['mean']:.4f} ± {m['std']:.4f} Mbps")
            print(f"  Range:  [{m['min']:.4f}, {m['max']:.4f}] Mbps")
        
        if 'delay' in metrics:
            m = metrics['delay']
            print(f"\nDelay (RTT):")
            print(f"  Mean:   {m['mean']:.2f} ± {m['std']:.2f} ms")
            print(f"  Range:  [{m['min']:.2f}, {m['max']:.2f}] ms")
        
        if 'jitter' in metrics:
            m = metrics['jitter']
            print(f"\nJitter:")
            print(f"  Mean:   {m['mean']:.4f} ± {m['std']:.4f} ms")
            print(f"  Range:  [{m['min']:.4f}, {m['max']:.4f}] ms")
        
        if 'packet_loss' in metrics:
            m = metrics['packet_loss']
            print(f"\nPacket Loss:")
            print(f"  Mean:   {m['mean']:.4f} ± {m['std']:.4f} %")
            print(f"  Range:  [{m['min']:.4f}, {m['max']:.4f}] %")
        
        if 'cpu' in metrics:
            m = metrics['cpu']
            print(f"\nCPU Utilization:")
            print(f"  Mean:   {m['mean']:.2f} ± {m['std']:.2f} %")
            print(f"  Range:  [{m['min']:.2f}, {m['max']:.2f}] %")
        
        if 'fairness_index' in metrics:
            m = metrics['fairness_index']
            print(f"\nFairness Index:")
            print(f"  Mean:   {m['mean']:.4f} ± {m['std']:.4f}")
            print(f"  Range:  [{m['min']:.4f}, {m['max']:.4f}]")
            print(f"  Values: {[f'{v:.4f}' for v in m['values']]}")
        
        if 'response_time' in metrics:
            m = metrics['response_time']
            print(f"\nResponse Time:")
            print(f"  Mean:   {m['mean']:.2f} ± {m['std']:.2f} ms")
            print(f"  Range:  [{m['min']:.2f}, {m['max']:.2f}] ms")
        
        print(f"\n{'='*70}\n")
    
    def export_aggregated_to_csv(self):
        """Export all aggregated results to CSV"""
        import csv
        
        csv_file = f"{self.aggregate_dir}/aggregated_summary.csv"
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Scenario',
                'Algorithm',
                'Num Runs',
                'TCP Throughput Mean',
                'TCP Throughput StdDev',
                'Fairness Mean',
                'Fairness StdDev',
                'Delay Mean',
                'Delay StdDev',
                'Jitter Mean',
                'Jitter StdDev',
                'CPU Mean',
                'CPU StdDev',
                'Packet Loss Mean',
                'Packet Loss StdDev'
            ])
            
            # Data rows
            for scenario in self.scenarios:
                filepath = f"{self.aggregate_dir}/{scenario}_aggregated.json"
                
                if not os.path.exists(filepath):
                    continue
                
                with open(filepath, 'r') as jf:
                    data = json.load(jf)
                
                metrics = data['metrics']
                
                row = [
                    scenario,
                    self.algorithm,
                    data['num_runs'],
                    f"{metrics.get('tcp_throughput', {}).get('mean', 0):.2f}",
                    f"{metrics.get('tcp_throughput', {}).get('std', 0):.2f}",
                    f"{metrics.get('fairness_index', {}).get('mean', 0):.4f}",
                    f"{metrics.get('fairness_index', {}).get('std', 0):.4f}",
                    f"{metrics.get('delay', {}).get('mean', 0):.2f}",
                    f"{metrics.get('delay', {}).get('std', 0):.2f}",
                    f"{metrics.get('jitter', {}).get('mean', 0):.4f}",
                    f"{metrics.get('jitter', {}).get('std', 0):.4f}",
                    f"{metrics.get('cpu', {}).get('mean', 0):.2f}",
                    f"{metrics.get('cpu', {}).get('std', 0):.2f}",
                    f"{metrics.get('packet_loss', {}).get('mean', 0):.4f}",
                    f"{metrics.get('packet_loss', {}).get('std', 0):.4f}"
                ]
                
                writer.writerow(row)
        
        print(f"\nAggregated CSV saved to: {csv_file}")
    
    def run_all_experiments(self):
        """Run all experiments multiple times"""
        print(f"\n{'='*70}")
        print(f"REPEATED EXPERIMENTS")
        print(f"{'='*70}")
        print(f"\nAlgorithm: {self.algorithm.upper()}")
        print(f"Number of runs per scenario: {self.num_runs}")
        print(f"Scenarios: {', '.join(self.scenarios)}")
        print(f"\nTotal experiments: {len(self.scenarios)} scenarios × {self.num_runs} runs = {len(self.scenarios) * self.num_runs} tests")
        print(f"Estimated time: ~{len(self.scenarios) * self.num_runs * 5} minutes")
        print(f"\n{'='*70}\n")
        
        print("\nIMPORTANT: Make sure controller is running!")
        controller_file = "weighted_round_robin_controller.py" if self.algorithm == 'wrr' else "weighted_least_connection_controller.py"
        print(f"Command: ryu-manager --ofp-tcp-listen-port 6653 controllers/{controller_file} --verbose\n")
        
        input("Press Enter to start repeated experiments...")
        
        # Run experiments
        for scenario in self.scenarios:
            print(f"\n\n{'#'*70}")
            print(f"# SCENARIO: {scenario.upper()}")
            print(f"{'#'*70}\n")
            
            successful_runs = 0
            
            for run_num in range(1, self.num_runs + 1):
                success = self.run_single_experiment(scenario, run_num)
                
                if success:
                    successful_runs += 1
                
                # Wait between runs
                if run_num < self.num_runs:
                    print(f"\nWaiting 10 seconds before next run...")
                    time.sleep(10)
            
            print(f"\n{scenario.upper()} completed: {successful_runs}/{self.num_runs} successful runs")
            
            # Aggregate results for this scenario
            print(f"\nAggregating results for {scenario}...")
            results = self.collect_results_for_scenario(scenario)
            
            if len(results) >= 2:
                aggregated = self.aggregate_metrics(results)
                self.save_aggregated_results(scenario, aggregated)
                self.print_aggregated_summary(scenario, aggregated)
            else:
                print(f"Warning: Not enough successful runs to aggregate ({len(results)} runs)")
        
        # Export all to CSV
        print(f"\n{'='*70}")
        print("EXPORTING AGGREGATED RESULTS TO CSV")
        print(f"{'='*70}\n")
        self.export_aggregated_to_csv()
        
        print(f"\n{'='*70}")
        print("ALL REPEATED EXPERIMENTS COMPLETED!")
        print(f"{'='*70}\n")
        print(f"Results saved in: {self.aggregate_dir}/")
        print("\nGenerated files:")
        print("  - <scenario>_aggregated.json (detailed metrics with mean, std, etc.)")
        print("  - aggregated_summary.csv (summary table)")
        print("\n")


def main():
    import sys
    
    if len(sys.argv) < 2:
        print("\nUsage: sudo python3 run_repeated_experiments.py [wrr|wlc] [num_runs]")
        print("\nArguments:")
        print("  algorithm  - wrr or wlc")
        print("  num_runs   - number of repetitions (default: 5)")
        print("\nExamples:")
        print("  sudo python3 run_repeated_experiments.py wrr 5")
        print("  sudo python3 run_repeated_experiments.py wlc 3")
        print("\n")
        sys.exit(1)
    
    algorithm = sys.argv[1].lower()
    num_runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    if algorithm not in ['wrr', 'wlc']:
        print("Error: Algorithm must be 'wrr' or 'wlc'")
        sys.exit(1)
    
    if num_runs < 2:
        print("Error: num_runs must be at least 2")
        sys.exit(1)
    
    try:
        import numpy
    except ImportError:
        print("\nError: numpy is not installed!")
        print("Install it with: pip3 install numpy")
        sys.exit(1)
    
    runner = RepeatedExperimentRunner(algorithm, num_runs)
    runner.run_all_experiments()


if __name__ == '__main__':
    main()