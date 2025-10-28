from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp, udp
import time


class WeightedRoundRobinController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(WeightedRoundRobinController, self).__init__(*args, **kwargs)
        self.logger.info("=== Weighted Round Robin Controller Started ===")
        
        self.datapaths = {}
        self.mac_to_port = {}
        self.arp_table = {}
        self.arp_cache = {}
        
        # WRR state per switch
        self.wrr_state = {}  # {dpid: {'counter': int, 'current_port': int}}
        
        # Port weights (capacity-based)
        # Higher weight = higher capacity = more traffic
        self.port_weights = {
            # Edge switches: uplink ports 3,4 to agg
            'edge_uplinks': {3: 3, 4: 2},  # Port 3 gets 3x, port 4 gets 2x
            # Agg switches: uplink ports 3,4 to core
            'agg_uplinks': {3: 3, 4: 2},   # Port 3 gets 3x, port 4 gets 2x
        }
        
        self.flow_counter = 0  # Total flows distributed
        
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.logger.info(f"*** Switch {dpid} connected ***")
        self.datapaths[dpid] = datapath
        self.mac_to_port.setdefault(dpid, {})
        
        # Initialize WRR state
        self.wrr_state[dpid] = {
            'counter': 0,
            'current_port': 3,  # Start with port 3
            'port_sequence': []  # Will be populated based on weights
        }

        # Delete all flows
        self.del_flow(datapath, parser.OFPMatch())

        # Drop IPv6
        match = parser.OFPMatch(eth_type=0x86dd)
        self.add_flow(datapath, 200, match, [])

        # Table-miss
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, 128)]
        self.add_flow(datapath, 0, match, actions)
        
        # Install proactive IP flows (local traffic only)
        self.install_proactive_flows(datapath, dpid)
        
        # Build WRR sequence
        self.build_wrr_sequence(dpid)

    def build_wrr_sequence(self, dpid):
        """Build port sequence based on weights for WRR"""
        if 13 <= dpid <= 20:  # Edge
            weights = self.port_weights['edge_uplinks']
        elif 5 <= dpid <= 12:  # Agg
            weights = self.port_weights['agg_uplinks']
        else:
            return
        
        # Build sequence: [3,3,3,4,4] if weights are {3:3, 4:2}
        sequence = []
        for port, weight in weights.items():
            sequence.extend([port] * weight)
        
        self.wrr_state[dpid]['port_sequence'] = sequence
        self.logger.info(f"  Switch {dpid} WRR sequence: {sequence}")

    def get_next_uplink_port(self, dpid):
        """Get next uplink port using WRR"""
        state = self.wrr_state[dpid]
        sequence = state['port_sequence']
        
        if not sequence:
            return 3  # Default
        
        # Get current port from sequence
        port = sequence[state['counter'] % len(sequence)]
        
        # Increment counter
        state['counter'] += 1
        
        return port

    def install_proactive_flows(self, datapath, dpid):
        """Install proactive flows for local traffic"""
        parser = datapath.ofproto_parser
        
        if 1 <= dpid <= 4:  # Core
            # Core uses simple routing (no load balancing needed here)
            for pod in range(4):
                for offset in range(4):
                    dst_ip = f"10.0.0.{pod * 4 + offset + 1}"
                    match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
                    actions = [parser.OFPActionOutput(pod + 1)]
                    self.add_flow(datapath, 100, match, actions)
            self.logger.info(f"  Core {dpid}: Installed flows")
            
        elif 5 <= dpid <= 12:  # Agg
            # Local pod traffic (no load balancing)
            pod = (dpid - 5) // 2
            for edge_offset in range(2):
                for host_offset in range(2):
                    host_num = pod * 4 + edge_offset * 2 + host_offset + 1
                    dst_ip = f"10.0.0.{host_num}"
                    match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
                    actions = [parser.OFPActionOutput(edge_offset + 1)]
                    self.add_flow(datapath, 100, match, actions)
            
            # Remote traffic: handled reactively with load balancing
            self.logger.info(f"  Agg {dpid}: Installed local flows, remote uses WRR")
            
        elif 13 <= dpid <= 20:  # Edge
            # Local hosts (no load balancing)
            edge_num = dpid - 13
            for i in range(2):
                dst_ip = f"10.0.0.{edge_num * 2 + i + 1}"
                match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
                actions = [parser.OFPActionOutput(i + 1)]
                self.add_flow(datapath, 100, match, actions)
            
            # Remote traffic: handled reactively with load balancing
            self.logger.info(f"  Edge {dpid}: Installed local flows, remote uses WRR")

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)

    def del_flow(self, datapath, match):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=match
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        
        if eth.ethertype == 0x88cc:
            return

        src = eth.src
        self.mac_to_port[dpid][src] = in_port

        # Handle ARP
        if eth.ethertype == 0x0806:
            self.handle_arp(datapath, in_port, pkt, eth)
            return

        # Handle IP packets with WRR load balancing
        if eth.ethertype == 0x0800:
            self.handle_ip_with_wrr(datapath, in_port, pkt, eth, msg)
            return

    def handle_ip_with_wrr(self, datapath, in_port, pkt, eth, msg):
        """Handle IP packets with WRR load balancing"""
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if not ip_pkt:
            return
        
        dst_ip = ip_pkt.dst
        src_ip = ip_pkt.src
        
        # Determine output port based on switch type and WRR
        out_port = None
        use_wrr = False
        
        if 13 <= dpid <= 20:  # Edge
            edge_num = dpid - 13
            local_start = edge_num * 2 + 1
            local_end = local_start + 1
            
            if in_port <= 2:  # From host
                host_num = int(dst_ip.split('.')[-1])
                if local_start <= host_num <= local_end:
                    # Local traffic
                    out_port = (host_num - local_start) + 1
                else:
                    # Remote traffic - use WRR
                    out_port = self.get_next_uplink_port(dpid)
                    use_wrr = True
            else:  # From agg
                # Check learned MAC
                dst_mac = eth.dst
                if dst_mac in self.mac_to_port[dpid]:
                    out_port = self.mac_to_port[dpid][dst_mac]
                else:
                    out_port = 1  # Default to port 1
                    
        elif 5 <= dpid <= 12:  # Agg
            pod = (dpid - 5) // 2
            pod_start = pod * 4 + 1
            pod_end = pod * 4 + 4
            
            if in_port <= 2:  # From edge
                host_num = int(dst_ip.split('.')[-1])
                if pod_start <= host_num <= pod_end:
                    # Local pod - route to edge
                    edge_offset = (host_num - pod_start) // 2
                    out_port = edge_offset + 1
                else:
                    # Remote pod - use WRR to core
                    out_port = self.get_next_uplink_port(dpid)
                    use_wrr = True
            else:  # From core
                # Route to edge based on destination
                host_num = int(dst_ip.split('.')[-1])
                edge_offset = (host_num - pod_start) // 2
                out_port = edge_offset + 1
                
        elif 1 <= dpid <= 4:  # Core
            # Route to appropriate pod
            host_num = int(dst_ip.split('.')[-1])
            target_pod = (host_num - 1) // 4
            out_port = target_pod + 1
        
        if out_port is None:
            return
        
        # Log WRR decision
        if use_wrr:
            self.flow_counter += 1
            self.logger.info(f"[WRR] Switch {dpid}: Flow {self.flow_counter} "
                           f"{src_ip}->{dst_ip} via port {out_port}")
        
        # Install flow and forward
        actions = [parser.OFPActionOutput(out_port)]
        
        # Create match based on 5-tuple for better granularity
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        udp_pkt = pkt.get_protocol(udp.udp)
        
        if tcp_pkt:
            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=6,
                tcp_src=tcp_pkt.src_port,
                tcp_dst=tcp_pkt.dst_port
            )
        elif udp_pkt:
            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=17,
                udp_src=udp_pkt.src_port,
                udp_dst=udp_pkt.dst_port
            )
        else:
            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip
            )
        
        # Install flow with timeout
        self.add_flow(datapath, 10, match, actions, idle_timeout=60)
        
        # Send packet
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    def handle_arp(self, datapath, in_port, pkt, eth):
        """Handle ARP - simplified version"""
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        arp_pkt = pkt.get_protocol(arp.arp)
        src_ip = arp_pkt.src_ip
        dst_ip = arp_pkt.dst_ip
        src_mac = arp_pkt.src_mac
        
        self.arp_table[src_ip] = src_mac
        
        # Simple ARP forwarding
        arp_key = (dpid, src_ip, dst_ip, arp_pkt.opcode)
        current_time = time.time()
        
        if arp_key in self.arp_cache:
            if current_time - self.arp_cache[arp_key] < 5:
                return
        
        self.arp_cache[arp_key] = current_time
        
        # Determine output ports
        out_ports = []
        
        if 13 <= dpid <= 20:  # Edge
            edge_num = dpid - 13
            local_ips = [f"10.0.0.{edge_num * 2 + 1}", f"10.0.0.{edge_num * 2 + 2}"]
            
            if in_port <= 2:
                if dst_ip in local_ips:
                    out_ports = [local_ips.index(dst_ip) + 1]
                else:
                    out_ports = [3, 4]
            else:
                out_ports = [1, 2]
                
        elif 5 <= dpid <= 12:  # Agg
            pod = (dpid - 5) // 2
            pod_start = pod * 4 + 1
            pod_end = pod * 4 + 4
            
            if in_port <= 2:
                host_num = int(dst_ip.split('.')[-1])
                if pod_start <= host_num <= pod_end:
                    edge_offset = (host_num - pod_start) // 2
                    out_ports = [edge_offset + 1]
                else:
                    out_ports = [3, 4]
            else:
                out_ports = [1, 2]
                
        elif 1 <= dpid <= 4:  # Core
            host_num = int(dst_ip.split('.')[-1])
            if 1 <= host_num <= 16:
                target_pod = (host_num - 1) // 4
                out_ports = [target_pod + 1]
            else:
                out_ports = [1, 2, 3, 4]
        
        # Send ARP
        for port in out_ports:
            if port != in_port:
                actions = [parser.OFPActionOutput(port)]
                out = parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=ofproto.OFP_NO_BUFFER,
                    in_port=in_port,
                    actions=actions,
                    data=pkt.data
                )
                datapath.send_msg(out)