#!/usr/bin/env python3
"""
Automatic Analysis and Visualization
- Load all test results (JSON)
- Export to CSV
- Generate graphs (PNG)
- Create comparison tables
- Generate summary report
"""

import json
import os
import glob
import csv
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import pandas as pd

class AutoAnalyzer:
    def __init__(self, results_dir='results'):
        self.results_dir = results_dir
        self.output_dir = f"analysis_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.data = {
            'wrr_homogen': [],
            'wlc_homogen': [],
            'wrr_heterogen': [],
            'wlc_heterogen': []
        }
        
        print(f"\n{'='*60}")
        print("AUTOMATIC ANALYSIS & VISUALIZATION")
        print(f"{'='*60}\n")
        print(f"Output directory: {self.output_dir}")
    
    def load_all_results(self):
        """Load all JSON results"""
        print("\n1. Loading test results...")
        
        # Load homogeneous traffic results
        for algo in ['wrr', 'wlc']:
            pattern = f"{self.results_dir}/{algo}/**/metrics.json"
            files = glob.glob(pattern, recursive=True)
            
            for filepath in files:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    self.data[f'{algo}_homogen'].append(data)
            
            print(f"   - Loaded {len(files)} {algo.upper()} homogeneous results")
        
        # Load heterogeneous traffic results
        for algo in ['wrr', 'wlc']:
            pattern = f"{self.results_dir}/heterogen_traffic/{algo}/**/*.json"
            files = glob.glob(pattern, recursive=True)
            
            for filepath in files:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    self.data[f'{algo}_heterogen'].append(data)
            
            print(f"   - Loaded {len(files)} {algo.upper()} heterogeneous results")
    
    def export_to_csv(self):
        """Export results to CSV files"""
        print("\n2. Exporting to CSV...")
        
        # ===== HOMOGENEOUS TRAFFIC CSV =====
        csv_homogen = f"{self.output_dir}/results_homogeneous_traffic.csv"
        
        with open(csv_homogen, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Algorithm', 'Scenario', 'Throughput_Avg_Mbps', 'Throughput_Std',
                'Delay_Avg_ms', 'Delay_Std', 'Jitter_Avg_ms', 'Jitter_Std',
                'Packet_Loss_%', 'CPU_Avg_%', 'CPU_Max_%',
                'Fairness_Index', 'Response_Time_Avg_ms'
            ])
            
            # WRR data
            for result in self.data['wrr_homogen']:
                row = self.extract_metrics_row('WRR', result)
                writer.writerow(row)
            
            # WLC data
            for result in self.data['wlc_homogen']:
                row = self.extract_metrics_row('WLC', result)
                writer.writerow(row)
        
        print(f"   ✓ Saved: {csv_homogen}")
        
        # ===== HETEROGENEOUS TRAFFIC CSV =====
        csv_heterogen = f"{self.output_dir}/results_heterogeneous_traffic.csv"
        
        with open(csv_heterogen, 'w', newline='') as f:
            writer = csv.writer(f)
            
            writer.writerow([
                'Algorithm', 'Scenario', 'Flow_Type', 
                'Bandwidth_Requested', 'Throughput_Achieved_Mbps',
                'Duration_sec', 'Protocol'
            ])
            
            for algo in ['wrr', 'wlc']:
                for result in self.data[f'{algo}_heterogen']:
                    scenario = result.get('scenario', 'unknown')
                    for flow in result.get('flows', []):
                        writer.writerow([
                            algo.upper(),
                            scenario,
                            f"{flow['src']}->{flow['dst']}",
                            flow.get('bandwidth_requested', 'N/A'),
                            flow.get('throughput_achieved', 0),
                            flow.get('duration', 0),
                            flow.get('protocol', 'tcp')
                        ])
        
        print(f"   ✓ Saved: {csv_heterogen}")
    
    def extract_metrics_row(self, algorithm, result):
        """Extract metrics from result dict to CSV row"""
        # Determine scenario from result structure
        scenario = "unknown"
        # You can determine from various fields
        
        # Throughput
        throughput_list = result.get('throughput', [])
        throughput_avg = np.mean(throughput_list) if throughput_list else 0
        throughput_std = np.std(throughput_list) if throughput_list else 0
        
        # Delay
        delay_list = result.get('delay', [])
        if delay_list and isinstance(delay_list[0], dict):
            delay_avgs = [d['avg'] for d in delay_list]
            delay_avg = np.mean(delay_avgs) if delay_avgs else 0
            delay_std = np.std(delay_avgs) if delay_avgs else 0
        else:
            delay_avg = delay_std = 0
        
        # Jitter
        jitter_list = result.get('jitter', [])
        jitter_list = [j for j in jitter_list if j > 0]
        jitter_avg = np.mean(jitter_list) if jitter_list else 0
        jitter_std = np.std(jitter_list) if jitter_list else 0
        
        # Packet loss
        loss_list = result.get('packet_loss', [])
        loss_avg = np.mean(loss_list) if loss_list else 0
        
        # CPU
        cpu = result.get('cpu_utilization', {})
        if isinstance(cpu, dict):
            cpu_avg = cpu.get('avg', 0)
            cpu_max = cpu.get('max', 0)
        else:
            cpu_avg = cpu_max = 0
        
        # Fairness
        fairness = result.get('fairness_index', 0)
        
        # Response time
        rt_list = result.get('response_time', [])
        rt_avg = np.mean(rt_list) if rt_list else 0
        
        return [
            algorithm, scenario,
            f"{throughput_avg:.2f}", f"{throughput_std:.2f}",
            f"{delay_avg:.2f}", f"{delay_std:.2f}",
            f"{jitter_avg:.2f}", f"{jitter_std:.2f}",
            f"{loss_avg:.2f}",
            f"{cpu_avg:.2f}", f"{cpu_max:.2f}",
            f"{fairness:.4f}", f"{rt_avg:.2f}"
        ]
    
    def generate_comparison_graphs(self):
        """Generate comparison graphs"""
        print("\n3. Generating graphs...")
        
        # Create graphs directory
        graphs_dir = f"{self.output_dir}/graphs"
        os.makedirs(graphs_dir, exist_ok=True)
        
        # Load CSV for easier plotting
        try:
            df_homogen = pd.read_csv(f"{self.output_dir}/results_homogeneous_traffic.csv")
            self.plot_homogeneous_comparison(df_homogen, graphs_dir)
        except Exception as e:
            print(f"   ⚠ Warning: Could not generate homogeneous graphs: {e}")
        
        try:
            df_heterogen = pd.read_csv(f"{self.output_dir}/results_heterogeneous_traffic.csv")
            self.plot_heterogeneous_comparison(df_heterogen, graphs_dir)
        except Exception as e:
            print(f"   ⚠ Warning: Could not generate heterogeneous graphs: {e}")
    
    def plot_homogeneous_comparison(self, df, graphs_dir):
        """Plot homogeneous traffic comparison"""
        
        # Group by algorithm
        wrr_data = df[df['Algorithm'] == 'WRR']
        wlc_data = df[df['Algorithm'] == 'WLC']
        
        metrics = [
            ('Throughput_Avg_Mbps', 'Throughput (Mbps)', 'throughput.png'),
            ('Delay_Avg_ms', 'Average Delay (ms)', 'delay.png'),
            ('Jitter_Avg_ms', 'Average Jitter (ms)', 'jitter.png'),
            ('Packet_Loss_%', 'Packet Loss (%)', 'packet_loss.png'),
            ('CPU_Avg_%', 'CPU Utilization (%)', 'cpu.png'),
            ('Fairness_Index', 'Fairness Index', 'fairness.png'),
            ('Response_Time_Avg_ms', 'Response Time (ms)', 'response_time.png'),
        ]
        
        for metric, ylabel, filename in metrics:
            if metric not in df.columns:
                continue
            
            plt.figure(figsize=(10, 6))
            
            # Bar chart
            x = np.arange(len(wrr_data))
            width = 0.35
            
            try:
                wrr_values = wrr_data[metric].astype(float)
                wlc_values = wlc_data[metric].astype(float)
                
                plt.bar(x - width/2, wrr_values, width, label='WRR', alpha=0.8)
                plt.bar(x + width/2, wlc_values, width, label='WLC', alpha=0.8)
                
                plt.xlabel('Test Run')
                plt.ylabel(ylabel)
                plt.title(f'{ylabel} - WRR vs WLC')
                plt.legend()
                plt.grid(True, alpha=0.3)
                plt.tight_layout()
                
                filepath = f"{graphs_dir}/{filename}"
                plt.savefig(filepath, dpi=300, bbox_inches='tight')
                plt.close()
                
                print(f"   ✓ Generated: {filename}")
            except Exception as e:
                print(f"   ⚠ Could not plot {metric}: {e}")
                plt.close()
    
    def plot_heterogeneous_comparison(self, df, graphs_dir):
        """Plot heterogeneous traffic comparison"""
        
        scenarios = df['Scenario'].unique()
        
        for scenario in scenarios:
            scenario_data = df[df['Scenario'] == scenario]
            
            # Group by algorithm
            wrr_data = scenario_data[scenario_data['Algorithm'] == 'WRR']
            wlc_data = scenario_data[scenario_data['Algorithm'] == 'WLC']
            
            # Plot throughput comparison
            plt.figure(figsize=(12, 6))
            
            try:
                wrr_throughput = wrr_data['Throughput_Achieved_Mbps'].astype(float)
                wlc_throughput = wlc_data['Throughput_Achieved_Mbps'].astype(float)
                
                x_wrr = range(len(wrr_throughput))
                x_wlc = range(len(wlc_throughput))
                
                plt.subplot(1, 2, 1)
                plt.plot(x_wrr, wrr_throughput, 'o-', label='WRR', alpha=0.7)
                plt.xlabel('Flow Index')
                plt.ylabel('Throughput (Mbps)')
                plt.title(f'WRR - {scenario}')
                plt.grid(True, alpha=0.3)
                plt.legend()
                
                plt.subplot(1, 2, 2)
                plt.plot(x_wlc, wlc_throughput, 's-', label='WLC', alpha=0.7, color='orange')
                plt.xlabel('Flow Index')
                plt.ylabel('Throughput (Mbps)')
                plt.title(f'WLC - {scenario}')
                plt.grid(True, alpha=0.3)
                plt.legend()
                
                plt.tight_layout()
                
                filename = f"heterogen_{scenario}_throughput.png"
                filepath = f"{graphs_dir}/{filename}"
                plt.savefig(filepath, dpi=300, bbox_inches='tight')
                plt.close()
                
                print(f"   ✓ Generated: {filename}")
            except Exception as e:
                print(f"   ⚠ Could not plot {scenario}: {e}")
                plt.close()
    
    def generate_summary_table(self):
        """Generate summary comparison table"""
        print("\n4. Generating summary tables...")
        
        summary_file = f"{self.output_dir}/summary_comparison.txt"
        
        with open(summary_file, 'w') as f:
            f.write("="*80 + "\n")
            f.write("LOAD BALANCING ALGORITHM COMPARISON SUMMARY\n")
            f.write("="*80 + "\n\n")
            
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Homogeneous Traffic Summary
            f.write("1. HOMOGENEOUS TRAFFIC RESULTS\n")
            f.write("-"*80 + "\n")
            
            try:
                df = pd.read_csv(f"{self.output_dir}/results_homogeneous_traffic.csv")
                
                # Group by algorithm
                wrr_avg = df[df['Algorithm'] == 'WRR'].select_dtypes(include=[np.number]).mean()
                wlc_avg = df[df['Algorithm'] == 'WLC'].select_dtypes(include=[np.number]).mean()
                
                f.write(f"\nWRR Average Metrics:\n")
                f.write(wrr_avg.to_string())
                f.write(f"\n\nWLC Average Metrics:\n")
                f.write(wlc_avg.to_string())
                f.write("\n\n")
                
                # Winner determination
                f.write("WINNER by Metric:\n")
                for metric in wrr_avg.index:
                    if 'loss' in metric.lower() or 'delay' in metric.lower() or 'jitter' in metric.lower():
                        # Lower is better
                        winner = 'WRR' if wrr_avg[metric] < wlc_avg[metric] else 'WLC'
                    else:
                        # Higher is better
                        winner = 'WRR' if wrr_avg[metric] > wlc_avg[metric] else 'WLC'
                    
                    f.write(f"  {metric}: {winner}\n")
                
            except Exception as e:
                f.write(f"Error processing homogeneous data: {e}\n")
            
            f.write("\n" + "="*80 + "\n\n")
            
            # Heterogeneous Traffic Summary
            f.write("2. HETEROGENEOUS TRAFFIC RESULTS\n")
            f.write("-"*80 + "\n")
            
            try:
                df = pd.read_csv(f"{self.output_dir}/results_heterogeneous_traffic.csv")
                
                for scenario in df['Scenario'].unique():
                    f.write(f"\nScenario: {scenario}\n")
                    f.write("-"*40 + "\n")
                    
                    scenario_data = df[df['Scenario'] == scenario]
                    
                    wrr_throughput = scenario_data[scenario_data['Algorithm'] == 'WRR']['Throughput_Achieved_Mbps'].astype(float)
                    wlc_throughput = scenario_data[scenario_data['Algorithm'] == 'WLC']['Throughput_Achieved_Mbps'].astype(float)
                    
                    f.write(f"  WRR: Avg={wrr_throughput.mean():.2f} Mbps, Std={wrr_throughput.std():.2f}\n")
                    f.write(f"  WLC: Avg={wlc_throughput.mean():.2f} Mbps, Std={wlc_throughput.std():.2f}\n")
                    
                    winner = 'WRR' if wrr_throughput.mean() > wlc_throughput.mean() else 'WLC'
                    f.write(f"  Winner: {winner}\n")
            
            except Exception as e:
                f.write(f"Error processing heterogeneous data: {e}\n")
            
            f.write("\n" + "="*80 + "\n")
        
        print(f"   ✓ Saved: {summary_file}")
        
        # Also print to console
        with open(summary_file, 'r') as f:
            print("\n" + f.read())
    
    def run_full_analysis(self):
        """Run complete analysis pipeline"""
        self.load_all_results()
        self.export_to_csv()
        self.generate_comparison_graphs()
        self.generate_summary_table()
        
        print(f"\n{'='*60}")
        print("ANALYSIS COMPLETE!")
        print(f"{'='*60}")
        print(f"\nAll outputs saved to: {self.output_dir}/")
        print("\nContents:")
        print("  - results_homogeneous_traffic.csv")
        print("  - results_heterogeneous_traffic.csv")
        print("  - graphs/ (PNG files)")
        print("  - summary_comparison.txt")
        print("\n")


def main():
    analyzer = AutoAnalyzer()
    analyzer.run_full_analysis()


if __name__ == '__main__':
    main()