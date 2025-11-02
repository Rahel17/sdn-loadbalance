import json
import os
import glob
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from datetime import datetime

# Set matplotlib backend and style
matplotlib.use('Agg')
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 11


class GraphGenerator:
    """Generate various graphs from test results"""
    
    def __init__(self, use_aggregated=False):
        self.use_aggregated = use_aggregated
        
        if use_aggregated:
            self.results_dir = "results/aggregated"
            self.graphs_dir = "results/graphs_aggregated"
        else:
            self.results_dir = "results/comprehensive"
            self.graphs_dir = "results/graphs"
        
        os.makedirs(self.graphs_dir, exist_ok=True)
        
        self.colors = {
            'wrr': '#FBD9CD',
            'wlc': '#7A958F'
        }
    
    def load_all_results(self):
        """Load all result files"""
        results = {'wrr': {}, 'wlc': {}}
        
        if self.use_aggregated:
            for algorithm in ['wrr', 'wlc']:
                agg_dir = f"{self.results_dir}/{algorithm}"
                if os.path.exists(agg_dir):
                    pattern = f"{agg_dir}/*_aggregated.json"
                    files = glob.glob(pattern)
                    
                    for filepath in files:
                        try:
                            with open(filepath, 'r') as f:
                                data = json.load(f)
                            scenario = data.get('scenario', 'unknown')
                            results[algorithm][scenario] = data
                        except:
                            continue
        else:
            pattern = f"{self.results_dir}/**/*.json"
            files = glob.glob(pattern, recursive=True)
            
            for filepath in files:
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    algorithm = data.get('algorithm', 'unknown')
                    scenario = data.get('scenario', 'unknown')
                    
                    if algorithm in results:
                        results[algorithm][scenario] = data
                except:
                    continue
        
        return results
    
    def extract_metric(self, data, metric_type):
        """Extract metric value and std from data"""
        if self.use_aggregated:
            metrics = data.get('metrics', {})
            metric_data = metrics.get(metric_type, {})
            mean = metric_data.get('mean', 0)
            std = metric_data.get('std', 0)
            return mean, std
        else:
            if metric_type == 'tcp_throughput':
                tcp = data.get('throughput', {}).get('tcp', [])
                val = sum(tcp) / len(tcp) if tcp else 0
            elif metric_type == 'udp_throughput':
                udp = data.get('throughput', {}).get('udp', [])
                val = sum(udp) / len(udp) if udp else 0
            elif metric_type == 'delay':
                delays = data.get('delay', [])
                val = sum(d['avg'] for d in delays) / len(delays) if delays else 0
            elif metric_type == 'jitter':
                jitters = data.get('jitter', [])
                val = sum(jitters) / len(jitters) if jitters else 0
            elif metric_type == 'packet_loss':
                losses = data.get('packet_loss', [])
                val = sum(losses) / len(losses) if losses else 0
            elif metric_type == 'cpu':
                val = data.get('cpu_utilization', {}).get('avg', 0)
            elif metric_type == 'fairness_index':
                val = data.get('fairness_index', 0)
            elif metric_type == 'response_time':
                rts = data.get('response_time', [])
                val = sum(rts) / len(rts) if rts else 0
            else:
                val = 0
            
            return val, 0
    
    def graph_throughput_comparison(self, results):
        """Graph 1: Throughput Comparison with error bars"""
        print("\n[1/12] Generating Throughput Comparison...")
        
        scenarios = []
        wrr_tcp_means, wrr_tcp_stds = [], []
        wlc_tcp_means, wlc_tcp_stds = [], []
        wrr_udp_means, wrr_udp_stds = [], []
        wlc_udp_means, wlc_udp_stds = [], []
        
        all_scenarios = set(results['wrr'].keys()) | set(results['wlc'].keys())
        
        for scenario in sorted(all_scenarios):
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_tcp_mean, wrr_tcp_std = self.extract_metric(wrr_data, 'tcp_throughput')
            wlc_tcp_mean, wlc_tcp_std = self.extract_metric(wlc_data, 'tcp_throughput')
            wrr_tcp_means.append(wrr_tcp_mean)
            wrr_tcp_stds.append(wrr_tcp_std)
            wlc_tcp_means.append(wlc_tcp_mean)
            wlc_tcp_stds.append(wlc_tcp_std)
            
            wrr_udp_mean, wrr_udp_std = self.extract_metric(wrr_data, 'udp_throughput')
            wlc_udp_mean, wlc_udp_std = self.extract_metric(wlc_data, 'udp_throughput')
            wrr_udp_means.append(wrr_udp_mean)
            wrr_udp_stds.append(wrr_udp_std)
            wlc_udp_means.append(wlc_udp_mean)
            wlc_udp_stds.append(wlc_udp_std)
        
        if not scenarios:
            print("   No data available")
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        x = np.arange(len(scenarios))
        width = 0.35
        
        # TCP Throughput
        ax1.bar(x - width/2, wrr_tcp_means, width, yerr=wrr_tcp_stds, 
                label='WRR', color=self.colors['wrr'], alpha=0.8, capsize=5)
        ax1.bar(x + width/2, wlc_tcp_means, width, yerr=wlc_tcp_stds,
                label='WLC', color=self.colors['wlc'], alpha=0.8, capsize=5)
        ax1.set_xlabel('Scenario')
        ax1.set_ylabel('Throughput (Mbps)')
        ax1.set_title('TCP Throughput Comparison' + (' (Mean ± SD)' if self.use_aggregated else ''))
        ax1.set_xticks(x)
        ax1.set_xticklabels(scenarios, rotation=45, ha='right')
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)
        
        # UDP Throughput
        ax2.bar(x - width/2, wrr_udp_means, width, yerr=wrr_udp_stds,
                label='WRR', color=self.colors['wrr'], alpha=0.8, capsize=5)
        ax2.bar(x + width/2, wlc_udp_means, width, yerr=wlc_udp_stds,
                label='WLC', color=self.colors['wlc'], alpha=0.8, capsize=5)
        ax2.set_xlabel('Scenario')
        ax2.set_ylabel('Throughput (Mbps)')
        ax2.set_title('UDP Throughput Comparison' + (' (Mean ± SD)' if self.use_aggregated else ''))
        ax2.set_xticks(x)
        ax2.set_xticklabels(scenarios, rotation=45, ha='right')
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = f"{self.graphs_dir}/1_throughput_comparison.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_delay_jitter(self, results):
        """Graph 2: Delay and Jitter with error bars"""
        print("\n[2/12] Generating Delay & Jitter Comparison...")
        
        scenarios = []
        wrr_delay_means, wrr_delay_stds = [], []
        wlc_delay_means, wlc_delay_stds = [], []
        wrr_jitter_means, wrr_jitter_stds = [], []
        wlc_jitter_means, wlc_jitter_stds = [], []
        
        all_scenarios = set(results['wrr'].keys()) | set(results['wlc'].keys())
        
        for scenario in sorted(all_scenarios):
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_d_mean, wrr_d_std = self.extract_metric(wrr_data, 'delay')
            wlc_d_mean, wlc_d_std = self.extract_metric(wlc_data, 'delay')
            wrr_delay_means.append(wrr_d_mean)
            wrr_delay_stds.append(wrr_d_std)
            wlc_delay_means.append(wlc_d_mean)
            wlc_delay_stds.append(wlc_d_std)
            
            wrr_j_mean, wrr_j_std = self.extract_metric(wrr_data, 'jitter')
            wlc_j_mean, wlc_j_std = self.extract_metric(wlc_data, 'jitter')
            wrr_jitter_means.append(wrr_j_mean)
            wrr_jitter_stds.append(wrr_j_std)
            wlc_jitter_means.append(wlc_j_mean)
            wlc_jitter_stds.append(wlc_j_std)
        
        if not scenarios:
            print("   No data available")
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        x = np.arange(len(scenarios))
        width = 0.35
        
        # Delay
        ax1.bar(x - width/2, wrr_delay_means, width, yerr=wrr_delay_stds,
                label='WRR', color=self.colors['wrr'], alpha=0.8, capsize=5)
        ax1.bar(x + width/2, wlc_delay_means, width, yerr=wlc_delay_stds,
                label='WLC', color=self.colors['wlc'], alpha=0.8, capsize=5)
        ax1.set_xlabel('Scenario')
        ax1.set_ylabel('Delay (ms)')
        ax1.set_title('Average RTT Delay' + (' (Mean ± SD)' if self.use_aggregated else ''))
        ax1.set_xticks(x)
        ax1.set_xticklabels(scenarios, rotation=45, ha='right')
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)
        
        # Jitter
        ax2.bar(x - width/2, wrr_jitter_means, width, yerr=wrr_jitter_stds,
                label='WRR', color=self.colors['wrr'], alpha=0.8, capsize=5)
        ax2.bar(x + width/2, wlc_jitter_means, width, yerr=wlc_jitter_stds,
                label='WLC', color=self.colors['wlc'], alpha=0.8, capsize=5)
        ax2.set_xlabel('Scenario')
        ax2.set_ylabel('Jitter (ms)')
        ax2.set_title('Average Jitter' + (' (Mean ± SD)' if self.use_aggregated else ''))
        ax2.set_xticks(x)
        ax2.set_xticklabels(scenarios, rotation=45, ha='right')
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = f"{self.graphs_dir}/2_delay_jitter_comparison.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_fairness_cpu(self, results):
        """Graph 3: Fairness and CPU with error bars"""
        print("\n[3/12] Generating Fairness & CPU Comparison...")
        
        scenarios = []
        wrr_fair_means, wrr_fair_stds = [], []
        wlc_fair_means, wlc_fair_stds = [], []
        wrr_cpu_means, wrr_cpu_stds = [], []
        wlc_cpu_means, wlc_cpu_stds = [], []
        
        all_scenarios = set(results['wrr'].keys()) | set(results['wlc'].keys())
        
        for scenario in sorted(all_scenarios):
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_f_mean, wrr_f_std = self.extract_metric(wrr_data, 'fairness_index')
            wlc_f_mean, wlc_f_std = self.extract_metric(wlc_data, 'fairness_index')
            wrr_fair_means.append(wrr_f_mean)
            wrr_fair_stds.append(wrr_f_std)
            wlc_fair_means.append(wlc_f_mean)
            wlc_fair_stds.append(wlc_f_std)
            
            wrr_c_mean, wrr_c_std = self.extract_metric(wrr_data, 'cpu')
            wlc_c_mean, wlc_c_std = self.extract_metric(wlc_data, 'cpu')
            wrr_cpu_means.append(wrr_c_mean)
            wrr_cpu_stds.append(wrr_c_std)
            wlc_cpu_means.append(wlc_c_mean)
            wlc_cpu_stds.append(wlc_c_std)
        
        if not scenarios:
            print("   No data available")
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        x = np.arange(len(scenarios))
        width = 0.35
        
        # Fairness
        ax1.bar(x - width/2, wrr_fair_means, width, yerr=wrr_fair_stds,
                label='WRR', color=self.colors['wrr'], alpha=0.8, capsize=5)
        ax1.bar(x + width/2, wlc_fair_means, width, yerr=wlc_fair_stds,
                label='WLC', color=self.colors['wlc'], alpha=0.8, capsize=5)
        ax1.set_xlabel('Scenario')
        ax1.set_ylabel('Fairness Index')
        ax1.set_title('Fairness Index' + (' (Mean ± SD)' if self.use_aggregated else ''))
        ax1.set_xticks(x)
        ax1.set_xticklabels(scenarios, rotation=45, ha='right')
        ax1.set_ylim([0, 1.1])
        ax1.axhline(y=1.0, color='green', linestyle='--', alpha=0.3, label='Perfect')
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)
        
        # CPU
        ax2.bar(x - width/2, wrr_cpu_means, width, yerr=wrr_cpu_stds,
                label='WRR', color=self.colors['wrr'], alpha=0.8, capsize=5)
        ax2.bar(x + width/2, wlc_cpu_means, width, yerr=wlc_cpu_stds,
                label='WLC', color=self.colors['wlc'], alpha=0.8, capsize=5)
        ax2.set_xlabel('Scenario')
        ax2.set_ylabel('CPU Utilization (%)')
        ax2.set_title('CPU Utilization' + (' (Mean ± SD)' if self.use_aggregated else ''))
        ax2.set_xticks(x)
        ax2.set_xticklabels(scenarios, rotation=45, ha='right')
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = f"{self.graphs_dir}/3_fairness_cpu_comparison.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_packet_loss_response_time(self, results):
        """Graph 4: Packet Loss and Response Time with error bars"""
        print("\n[4/12] Generating Packet Loss & Response Time...")
        
        scenarios = []
        wrr_loss_means, wrr_loss_stds = [], []
        wlc_loss_means, wlc_loss_stds = [], []
        wrr_rt_means, wrr_rt_stds = [], []
        wlc_rt_means, wlc_rt_stds = [], []
        
        all_scenarios = set(results['wrr'].keys()) | set(results['wlc'].keys())
        
        for scenario in sorted(all_scenarios):
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_l_mean, wrr_l_std = self.extract_metric(wrr_data, 'packet_loss')
            wlc_l_mean, wlc_l_std = self.extract_metric(wlc_data, 'packet_loss')
            wrr_loss_means.append(wrr_l_mean)
            wrr_loss_stds.append(wrr_l_std)
            wlc_loss_means.append(wlc_l_mean)
            wlc_loss_stds.append(wlc_l_std)
            
            wrr_rt_mean, wrr_rt_std = self.extract_metric(wrr_data, 'response_time')
            wlc_rt_mean, wlc_rt_std = self.extract_metric(wlc_data, 'response_time')
            wrr_rt_means.append(wrr_rt_mean)
            wrr_rt_stds.append(wrr_rt_std)
            wlc_rt_means.append(wlc_rt_mean)
            wlc_rt_stds.append(wlc_rt_std)
        
        if not scenarios:
            print("   No data available")
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        x = np.arange(len(scenarios))
        width = 0.35
        
        # Packet Loss
        ax1.bar(x - width/2, wrr_loss_means, width, yerr=wrr_loss_stds,
                label='WRR', color=self.colors['wrr'], alpha=0.8, capsize=5)
        ax1.bar(x + width/2, wlc_loss_means, width, yerr=wlc_loss_stds,
                label='WLC', color=self.colors['wlc'], alpha=0.8, capsize=5)
        ax1.set_xlabel('Scenario')
        ax1.set_ylabel('Packet Loss (%)')
        ax1.set_title('Packet Loss' + (' (Mean ± SD)' if self.use_aggregated else ''))
        ax1.set_xticks(x)
        ax1.set_xticklabels(scenarios, rotation=45, ha='right')
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)
        
        # Response Time
        ax2.bar(x - width/2, wrr_rt_means, width, yerr=wrr_rt_stds,
                label='WRR', color=self.colors['wrr'], alpha=0.8, capsize=5)
        ax2.bar(x + width/2, wlc_rt_means, width, yerr=wlc_rt_stds,
                label='WLC', color=self.colors['wlc'], alpha=0.8, capsize=5)
        ax2.set_xlabel('Scenario')
        ax2.set_ylabel('Response Time (ms)')
        ax2.set_title('Response Time' + (' (Mean ± SD)' if self.use_aggregated else ''))
        ax2.set_xticks(x)
        ax2.set_xticklabels(scenarios, rotation=45, ha='right')
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        filepath = f"{self.graphs_dir}/4_packet_loss_response_time.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_performance_radar(self, results):
        """Graph 5: Performance Radar Chart"""
        print("\n[5/12] Generating Performance Radar Chart...")
        
        scenario = list(results['wrr'].keys())[0] if results['wrr'] else None
        
        if not scenario or scenario not in results['wlc']:
            print("   No data available")
            return
        
        wrr_data = results['wrr'][scenario]
        wlc_data = results['wlc'][scenario]
        
        metrics_names = ['Throughput', 'Fairness', 'Low Delay', 'Low Jitter', 'Low CPU', 'Low Loss']
        
        # Extract and normalize metrics
        wrr_tcp_mean, _ = self.extract_metric(wrr_data, 'tcp_throughput')
        wlc_tcp_mean, _ = self.extract_metric(wlc_data, 'tcp_throughput')
        max_throughput = max(wrr_tcp_mean, wlc_tcp_mean) if max(wrr_tcp_mean, wlc_tcp_mean) > 0 else 1
        
        wrr_delay_mean, _ = self.extract_metric(wrr_data, 'delay')
        wlc_delay_mean, _ = self.extract_metric(wlc_data, 'delay')
        max_delay = max(wrr_delay_mean, wlc_delay_mean) if max(wrr_delay_mean, wlc_delay_mean) > 0 else 1
        
        wrr_jitter_mean, _ = self.extract_metric(wrr_data, 'jitter')
        wlc_jitter_mean, _ = self.extract_metric(wlc_data, 'jitter')
        max_jitter = max(wrr_jitter_mean, wlc_jitter_mean) if max(wrr_jitter_mean, wlc_jitter_mean) > 0 else 1
        
        wrr_cpu_mean, _ = self.extract_metric(wrr_data, 'cpu')
        wlc_cpu_mean, _ = self.extract_metric(wlc_data, 'cpu')
        
        wrr_fair_mean, _ = self.extract_metric(wrr_data, 'fairness_index')
        wlc_fair_mean, _ = self.extract_metric(wlc_data, 'fairness_index')
        
        wrr_loss_mean, _ = self.extract_metric(wrr_data, 'packet_loss')
        wlc_loss_mean, _ = self.extract_metric(wlc_data, 'packet_loss')
        
        wrr_scores = [
            wrr_tcp_mean / max_throughput,
            wrr_fair_mean,
            1 - (wrr_delay_mean / max_delay) if max_delay > 0 else 0,
            1 - (wrr_jitter_mean / max_jitter) if max_jitter > 0 else 0,
            1 - (wrr_cpu_mean / 100),
            1 - (wrr_loss_mean / 100)
        ]
        
        wlc_scores = [
            wlc_tcp_mean / max_throughput,
            wlc_fair_mean,
            1 - (wlc_delay_mean / max_delay) if max_delay > 0 else 0,
            1 - (wlc_jitter_mean / max_jitter) if max_jitter > 0 else 0,
            1 - (wlc_cpu_mean / 100),
            1 - (wlc_loss_mean / 100)
        ]
        
        angles = np.linspace(0, 2 * np.pi, len(metrics_names), endpoint=False).tolist()
        wrr_scores += wrr_scores[:1]
        wlc_scores += wlc_scores[:1]
        angles += angles[:1]
        
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
        
        ax.plot(angles, wrr_scores, 'o-', linewidth=2, label='WRR', color=self.colors['wrr'])
        ax.fill(angles, wrr_scores, alpha=0.25, color=self.colors['wrr'])
        
        ax.plot(angles, wlc_scores, 'o-', linewidth=2, label='WLC', color=self.colors['wlc'])
        ax.fill(angles, wlc_scores, alpha=0.25, color=self.colors['wlc'])
        
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(metrics_names)
        ax.set_ylim(0, 1)
        ax.set_title(f'Performance Comparison\n({scenario.replace("_", " ").title()})', y=1.08)
        ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))
        ax.grid(True)
        
        plt.tight_layout()
        filepath = f"{self.graphs_dir}/5_performance_radar.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_summary_table(self, results):
        """Graph 6: Summary Table with mean and std"""
        print("\n[6/12] Generating Summary Table...")
        
        scenarios = []
        data_rows = []
        
        all_scenarios = set(results['wrr'].keys()) | set(results['wlc'].keys())
        
        for scenario in sorted(all_scenarios):
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_tcp_mean, wrr_tcp_std = self.extract_metric(wrr_data, 'tcp_throughput')
            wlc_tcp_mean, wlc_tcp_std = self.extract_metric(wlc_data, 'tcp_throughput')
            wrr_fair_mean, wrr_fair_std = self.extract_metric(wrr_data, 'fairness_index')
            wlc_fair_mean, wlc_fair_std = self.extract_metric(wlc_data, 'fairness_index')
            wrr_cpu_mean, wrr_cpu_std = self.extract_metric(wrr_data, 'cpu')
            wlc_cpu_mean, wlc_cpu_std = self.extract_metric(wlc_data, 'cpu')
            
            if self.use_aggregated:
                row = [
                    scenario,
                    f"{wrr_tcp_mean:.1f}±{wrr_tcp_std:.1f}",
                    f"{wlc_tcp_mean:.1f}±{wlc_tcp_std:.1f}",
                    f"{wrr_fair_mean:.3f}±{wrr_fair_std:.3f}",
                    f"{wlc_fair_mean:.3f}±{wlc_fair_std:.3f}",
                    f"{wrr_cpu_mean:.1f}±{wrr_cpu_std:.1f}",
                    f"{wlc_cpu_mean:.1f}±{wlc_cpu_std:.1f}"
                ]
            else:
                row = [
                    scenario,
                    f"{wrr_tcp_mean:.1f}",
                    f"{wlc_tcp_mean:.1f}",
                    f"{wrr_fair_mean:.3f}",
                    f"{wlc_fair_mean:.3f}",
                    f"{wrr_cpu_mean:.1f}",
                    f"{wlc_cpu_mean:.1f}"
                ]
            
            data_rows.append(row)
        
        if not data_rows:
            print("   No data available")
            return
        
        col_labels = [
            'Scenario',
            'WRR Throughput', 'WLC Throughput',
            'WRR Fairness', 'WLC Fairness',
            'WRR CPU', 'WLC CPU'
        ]
        
        fig, ax = plt.subplots(figsize=(14, 0.6 * len(data_rows) + 2))
        ax.axis('off')
        table = ax.table(cellText=data_rows, colLabels=col_labels, cellLoc='center', loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)
        
        plt.title('Summary of WRR vs WLC Performance', fontsize=14, pad=20)
        filepath = f"{self.graphs_dir}/6_summary_table.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")

    def graph_correlation(self, results):
        """Graph 7: Correlation between CPU and Throughput"""
        print("\n[7/12] Generating CPU–Throughput Correlation Graph...")
        
        cpu_vals, thr_vals, labels = [], [], []
        for algo in ['wrr', 'wlc']:
            for scenario, data in results[algo].items():
                cpu, _ = self.extract_metric(data, 'cpu')
                thr, _ = self.extract_metric(data, 'tcp_throughput')
                cpu_vals.append(cpu)
                thr_vals.append(thr)
                labels.append(f"{algo.upper()}-{scenario}")
        
        if not cpu_vals:
            print("   No data available")
            return
        
        plt.figure(figsize=(10, 7))
        plt.scatter(cpu_vals, thr_vals, c='purple', alpha=0.7)
        for i, lbl in enumerate(labels):
            plt.text(cpu_vals[i]+0.3, thr_vals[i], lbl, fontsize=8)
        
        plt.xlabel("CPU Utilization (%)")
        plt.ylabel("Throughput (Mbps)")
        plt.title("Correlation between CPU Utilization and Throughput")
        plt.grid(True, alpha=0.3)
        
        filepath = f"{self.graphs_dir}/7_cpu_throughput_correlation.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_overall_performance_score(self, results):
        """Graph 8: Weighted Overall Performance Score"""
        print("\n[8/12] Generating Weighted Performance Score...")
        
        weights = {
            'throughput': 0.3,
            'fairness_index': 0.25,
            'delay': 0.15,
            'jitter': 0.1,
            'cpu': 0.1,
            'packet_loss': 0.1
        }
        
        scores = {'wrr': [], 'wlc': []}
        labels = []
        
        all_scenarios = set(results['wrr'].keys()) | set(results['wlc'].keys())
        for scenario in sorted(all_scenarios):
            labels.append(scenario.replace('_', ' ').title())
            
            for algo in ['wrr', 'wlc']:
                data = results[algo].get(scenario)
                if not data:
                    scores[algo].append(0)
                    continue
                
                thr, _ = self.extract_metric(data, 'tcp_throughput')
                fair, _ = self.extract_metric(data, 'fairness_index')
                delay, _ = self.extract_metric(data, 'delay')
                jitter, _ = self.extract_metric(data, 'jitter')
                cpu, _ = self.extract_metric(data, 'cpu')
                loss, _ = self.extract_metric(data, 'packet_loss')
                
                score = (
                    thr * weights['throughput'] +
                    fair * 100 * weights['fairness_index'] -
                    delay * weights['delay'] -
                    jitter * weights['jitter'] -
                    cpu * weights['cpu'] -
                    loss * weights['packet_loss']
                )
                scores[algo].append(score)
        
        if not labels:
            print("   No data available")
            return
        
        x = np.arange(len(labels))
        width = 0.35
        
        plt.figure(figsize=(14, 6))
        plt.bar(x - width/2, scores['wrr'], width, label='WRR', color=self.colors['wrr'])
        plt.bar(x + width/2, scores['wlc'], width, label='WLC', color=self.colors['wlc'])
        plt.xticks(x, labels, rotation=45, ha='right')
        plt.ylabel("Weighted Performance Score")
        plt.title("Overall Performance Comparison (Weighted Composite Score)")
        plt.legend()
        plt.tight_layout()
        
        filepath = f"{self.graphs_dir}/8_weighted_performance_score.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")

    # =================== NEW: Load Intensity Line Charts =================== #
    
    def graph_throughput_vs_load(self, results):
        """Graph 9: Throughput vs Load Intensity (Line Chart)"""
        print("\n[9/12] Generating Throughput vs Load Intensity...")
        
        scenarios = []
        wrr_means, wrr_stds = [], []
        wlc_means, wlc_stds = [], []
        
        all_scenarios = sorted(set(results['wrr'].keys()) | set(results['wlc'].keys()))
        
        for scenario in all_scenarios:
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_mean, wrr_std = self.extract_metric(wrr_data, 'tcp_throughput')
            wlc_mean, wlc_std = self.extract_metric(wlc_data, 'tcp_throughput')
            
            wrr_means.append(wrr_mean)
            wrr_stds.append(wrr_std)
            wlc_means.append(wlc_mean)
            wlc_stds.append(wlc_std)
        
        if not scenarios:
            print("   No data available")
            return
        
        x = np.arange(len(scenarios))
        
        plt.figure(figsize=(14, 7))
        
        # Plot lines with markers
        plt.plot(x, wrr_means, 'o-', linewidth=2.5, markersize=8, 
                label='Weighted Round-Robin', color=self.colors['wrr'])
        plt.plot(x, wlc_means, 's-', linewidth=2.5, markersize=8,
                label='Weighted Least Connection', color=self.colors['wlc'])
        
        # Add error bars if using aggregated results
        if self.use_aggregated:
            plt.errorbar(x, wrr_means, yerr=wrr_stds, fmt='none', 
                        ecolor=self.colors['wrr'], alpha=0.3, capsize=5)
            plt.errorbar(x, wlc_means, yerr=wlc_stds, fmt='none',
                        ecolor=self.colors['wlc'], alpha=0.3, capsize=5)
        
        plt.xlabel('Load Scenario', fontsize=12)
        plt.ylabel('Average Network Throughput (Mbps)', fontsize=12)
        plt.title('Throughput Performance Across Load Scenarios', fontsize=14, fontweight='bold')
        plt.xticks(x, scenarios, rotation=45, ha='right')
        plt.legend(loc='best', fontsize=11)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.tight_layout()
        
        filepath = f"{self.graphs_dir}/9_throughput_vs_load.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_delay_vs_load(self, results):
        """Graph 10: Delay vs Load Intensity (Line Chart)"""
        print("\n[10/12] Generating Delay vs Load Intensity...")
        
        scenarios = []
        wrr_means, wrr_stds = [], []
        wlc_means, wlc_stds = [], []
        
        all_scenarios = sorted(set(results['wrr'].keys()) | set(results['wlc'].keys()))
        
        for scenario in all_scenarios:
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_mean, wrr_std = self.extract_metric(wrr_data, 'delay')
            wlc_mean, wlc_std = self.extract_metric(wlc_data, 'delay')
            
            wrr_means.append(wrr_mean)
            wrr_stds.append(wrr_std)
            wlc_means.append(wlc_mean)
            wlc_stds.append(wlc_std)
        
        if not scenarios:
            print("   No data available")
            return
        
        x = np.arange(len(scenarios))
        
        plt.figure(figsize=(14, 7))
        
        plt.plot(x, wrr_means, 'o-', linewidth=2.5, markersize=8,
                label='Weighted Round-Robin', color=self.colors['wrr'])
        plt.plot(x, wlc_means, 's-', linewidth=2.5, markersize=8,
                label='Weighted Least Connection', color=self.colors['wlc'])
        
        if self.use_aggregated:
            plt.errorbar(x, wrr_means, yerr=wrr_stds, fmt='none',
                        ecolor=self.colors['wrr'], alpha=0.3, capsize=5)
            plt.errorbar(x, wlc_means, yerr=wlc_stds, fmt='none',
                        ecolor=self.colors['wlc'], alpha=0.3, capsize=5)
        
        plt.xlabel('Load Scenario', fontsize=12)
        plt.ylabel('Average RTT Delay (ms)', fontsize=12)
        plt.title('Network Delay Across Load Scenarios', fontsize=14, fontweight='bold')
        plt.xticks(x, scenarios, rotation=45, ha='right')
        plt.legend(loc='best', fontsize=11)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.tight_layout()
        
        filepath = f"{self.graphs_dir}/10_delay_vs_load.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_cpu_vs_load(self, results):
        """Graph 11: CPU Utilization vs Load Intensity (Line Chart)"""
        print("\n[11/12] Generating CPU vs Load Intensity...")
        
        scenarios = []
        wrr_means, wrr_stds = [], []
        wlc_means, wlc_stds = [], []
        
        all_scenarios = sorted(set(results['wrr'].keys()) | set(results['wlc'].keys()))
        
        for scenario in all_scenarios:
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_mean, wrr_std = self.extract_metric(wrr_data, 'cpu')
            wlc_mean, wlc_std = self.extract_metric(wlc_data, 'cpu')
            
            wrr_means.append(wrr_mean)
            wrr_stds.append(wrr_std)
            wlc_means.append(wlc_mean)
            wlc_stds.append(wlc_std)
        
        if not scenarios:
            print("   No data available")
            return
        
        x = np.arange(len(scenarios))
        
        plt.figure(figsize=(14, 7))
        
        plt.plot(x, wrr_means, 'o-', linewidth=2.5, markersize=8,
                label='Weighted Round-Robin', color=self.colors['wrr'])
        plt.plot(x, wlc_means, 's-', linewidth=2.5, markersize=8,
                label='Weighted Least Connection', color=self.colors['wlc'])
        
        if self.use_aggregated:
            plt.errorbar(x, wrr_means, yerr=wrr_stds, fmt='none',
                        ecolor=self.colors['wrr'], alpha=0.3, capsize=5)
            plt.errorbar(x, wlc_means, yerr=wlc_stds, fmt='none',
                        ecolor=self.colors['wlc'], alpha=0.3, capsize=5)
        
        plt.xlabel('Load Scenario', fontsize=12)
        plt.ylabel('CPU Utilization (%)', fontsize=12)
        plt.title('CPU Utilization Across Load Scenarios', fontsize=14, fontweight='bold')
        plt.xticks(x, scenarios, rotation=45, ha='right')
        plt.legend(loc='best', fontsize=11)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.tight_layout()
        
        filepath = f"{self.graphs_dir}/11_cpu_vs_load.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")
    
    def graph_fairness_vs_load(self, results):
        """Graph 12: Fairness Index vs Load Intensity (Line Chart)"""
        print("\n[12/12] Generating Fairness vs Load Intensity...")
        
        scenarios = []
        wrr_means, wrr_stds = [], []
        wlc_means, wlc_stds = [], []
        
        all_scenarios = sorted(set(results['wrr'].keys()) | set(results['wlc'].keys()))
        
        for scenario in all_scenarios:
            wrr_data = results['wrr'].get(scenario)
            wlc_data = results['wlc'].get(scenario)
            
            if not wrr_data or not wlc_data:
                continue
            
            scenarios.append(scenario.replace('_', ' ').title())
            
            wrr_mean, wrr_std = self.extract_metric(wrr_data, 'fairness_index')
            wlc_mean, wlc_std = self.extract_metric(wlc_data, 'fairness_index')
            
            wrr_means.append(wrr_mean)
            wrr_stds.append(wrr_std)
            wlc_means.append(wlc_mean)
            wlc_stds.append(wlc_std)
        
        if not scenarios:
            print("   No data available")
            return
        
        x = np.arange(len(scenarios))
        
        plt.figure(figsize=(14, 7))
        
        plt.plot(x, wrr_means, 'o-', linewidth=2.5, markersize=8,
                label='Weighted Round-Robin', color=self.colors['wrr'])
        plt.plot(x, wlc_means, 's-', linewidth=2.5, markersize=8,
                label='Weighted Least Connection', color=self.colors['wlc'])
        
        if self.use_aggregated:
            plt.errorbar(x, wrr_means, yerr=wrr_stds, fmt='none',
                        ecolor=self.colors['wrr'], alpha=0.3, capsize=5)
            plt.errorbar(x, wlc_means, yerr=wlc_stds, fmt='none',
                        ecolor=self.colors['wlc'], alpha=0.3, capsize=5)
        
        # Add perfect fairness reference line
        plt.axhline(y=1.0, color='green', linestyle='--', alpha=0.5, 
                   linewidth=1.5, label='Perfect Fairness')
        
        plt.xlabel('Load Scenario', fontsize=12)
        plt.ylabel('Fairness Index (Jain\'s Index)', fontsize=12)
        plt.title('Fairness Index Across Load Scenarios', fontsize=14, fontweight='bold')
        plt.xticks(x, scenarios, rotation=45, ha='right')
        plt.ylim([0, 1.1])
        plt.legend(loc='best', fontsize=11)
        plt.grid(True, alpha=0.3, linestyle='--')
        plt.tight_layout()
        
        filepath = f"{self.graphs_dir}/12_fairness_vs_load.png"
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   Saved: {filepath}")


# ========================== Main Entry ========================== #
if __name__ == "__main__":
    print("=" * 60)
    print("  ENHANCED GRAPH GENERATOR")
    print("  WRR vs WLC Performance Analysis")
    print("=" * 60)
    
    use_agg = input("\nUse aggregated results? (y/n): ").lower().startswith('y')
    gg = GraphGenerator(use_aggregated=use_agg)
    
    print("\nLoading results...")
    results = gg.load_all_results()
    
    if not results['wrr'] and not results['wlc']:
        print("\n❌ No results found! Please run tests first.")
        exit(1)
    
    print(f"✓ Found {len(results['wrr'])} WRR scenarios")
    print(f"✓ Found {len(results['wlc'])} WLC scenarios")
    
    print("\n" + "=" * 60)
    print("  Generating Graphs...")
    print("=" * 60)
    
    # Original 8 graphs
    gg.graph_throughput_comparison(results)
    gg.graph_delay_jitter(results)
    gg.graph_fairness_cpu(results)
    gg.graph_packet_loss_response_time(results)
    gg.graph_performance_radar(results)
    gg.graph_summary_table(results)
    gg.graph_correlation(results)
    gg.graph_overall_performance_score(results)
    
    # NEW: 4 Load Intensity Line Charts
    gg.graph_throughput_vs_load(results)
    gg.graph_delay_vs_load(results)
    gg.graph_cpu_vs_load(results)
    gg.graph_fairness_vs_load(results)
    
    print("\n" + "=" * 60)
    print("✅ All 12 graphs generated successfully!")
    print(f"📁 Location: {gg.graphs_dir}/")
    print("=" * 60)