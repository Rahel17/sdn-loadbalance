from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4


class FatTreeNoLoop(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(FatTreeNoLoop, self).__init__(*args, **kwargs)
        self.logger.info("=== FatTree No-Loop Controller Started ===")
        self.mac_to_port = {}
        self.arp_table = {}
        self.datapaths = {}
        self.handled_arps = set()
        
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.logger.info(f"*** Switch {dpid} connected ***")
        self.datapaths[dpid] = datapath
        self.mac_to_port.setdefault(dpid, {})

        # Delete all flows
        self.del_flow(datapath, parser.OFPMatch())

        # Drop IPv6
        match = parser.OFPMatch(eth_type=0x86dd)
        actions = []
        self.add_flow(datapath, 200, match, actions)

        # Table-miss
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, 128)]
        self.add_flow(datapath, 0, match, actions)
        
        self.install_proactive_flows(datapath, dpid)

    def install_proactive_flows(self, datapath, dpid):
        """Install IP forwarding flows"""
        parser = datapath.ofproto_parser
        
        if 1 <= dpid <= 4:  # Core
            for pod in range(4):
                for offset in range(4):
                    dst_ip = f"10.0.0.{pod * 4 + offset + 1}"
                    match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
                    actions = [parser.OFPActionOutput(pod + 1)]
                    self.add_flow(datapath, 100, match, actions)
            self.logger.info(f"  Core {dpid}: Installed IP flows")
            
        elif 5 <= dpid <= 12:  # Agg
            pod = (dpid - 5) // 2
            for edge_offset in range(2):
                for host_offset in range(2):
                    host_num = pod * 4 + edge_offset * 2 + host_offset + 1
                    dst_ip = f"10.0.0.{host_num}"
                    match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
                    actions = [parser.OFPActionOutput(edge_offset + 1)]
                    self.add_flow(datapath, 100, match, actions)
            
            match = parser.OFPMatch(eth_type=0x0800)
            actions = [parser.OFPActionOutput(3)]
            self.add_flow(datapath, 50, match, actions)
            self.logger.info(f"  Agg {dpid} (pod {pod}): Installed IP flows")
            
        elif 13 <= dpid <= 20:  # Edge
            edge_num = dpid - 13
            for i in range(2):
                dst_ip = f"10.0.0.{edge_num * 2 + i + 1}"
                match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
                actions = [parser.OFPActionOutput(i + 1)]
                self.add_flow(datapath, 100, match, actions)
            
            match = parser.OFPMatch(eth_type=0x0800)
            actions = [parser.OFPActionOutput(3)]
            self.add_flow(datapath, 50, match, actions)
            self.logger.info(f"  Edge {dpid}: Installed IP flows")

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst,
                                idle_timeout=idle_timeout)
        datapath.send_msg(mod)

    def del_flow(self, datapath, match):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(datapath=datapath,
                               command=ofproto.OFPFC_DELETE,
                               out_port=ofproto.OFPP_ANY,
                               out_group=ofproto.OFPG_ANY,
                               match=match)
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
        
        if eth.ethertype == 0x88cc:  # LLDP
            return

        src = eth.src
        self.mac_to_port[dpid][src] = in_port

        if eth.ethertype == 0x0806:  # ARP
            self.handle_arp(datapath, in_port, pkt, eth)
            return

        # Handle other packets with learned MAC
        dst = eth.dst
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            self.logger.info(f"[DPID {dpid}] Unknown dst {dst}, dropping")
            return

        actions = [parser.OFPActionOutput(out_port)]
        
        if out_port != ofproto.OFPP_CONTROLLER:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self.add_flow(datapath, 10, match, actions, idle_timeout=30)

        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def handle_arp(self, datapath, in_port, pkt, eth):
        """Handle ARP with intelligent forwarding"""
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        arp_pkt = pkt.get_protocol(arp.arp)
        src_ip = arp_pkt.src_ip
        dst_ip = arp_pkt.dst_ip
        src_mac = arp_pkt.src_mac
        
        self.arp_table[src_ip] = src_mac
        
        arp_key = (dpid, src_ip, dst_ip, arp_pkt.opcode)
        if arp_key in self.handled_arps:
            return
        
        self.handled_arps.add(arp_key)
        if len(self.handled_arps) > 100:
            self.handled_arps.clear()
        
        self.logger.info(f"[DPID {dpid}] ARP: {src_ip} asks {dst_ip} on port {in_port}")
        
        out_ports = []
        
        if 13 <= dpid <= 20:  # Edge
            edge_num = dpid - 13
            local_host1_ip = f"10.0.0.{edge_num * 2 + 1}"
            local_host2_ip = f"10.0.0.{edge_num * 2 + 2}"
            
            if in_port <= 2:  # From host
                if dst_ip == local_host1_ip:
                    out_ports = [1]
                elif dst_ip == local_host2_ip:
                    out_ports = [2]
                else:
                    out_ports = [3, 4]  # To agg
            else:  # From agg
                out_ports = [1, 2]  # To hosts
                
        elif 5 <= dpid <= 12:  # Agg
            pod = (dpid - 5) // 2
            pod_start_ip = pod * 4 + 1
            pod_end_ip = pod * 4 + 4
            
            if in_port <= 2:  # From edge
                if dst_ip.startswith('10.0.0.'):
                    host_num = int(dst_ip.split('.')[-1])
                    if pod_start_ip <= host_num <= pod_end_ip:
                        # Local pod
                        edge_offset = (host_num - pod_start_ip) // 2
                        out_ports = [edge_offset + 1]
                    else:
                        # Remote pod
                        out_ports = [3, 4]  # To core
                else:
                    out_ports = [3, 4]
            else:  # From core
                out_ports = [1, 2]  # To edges
                
        elif 1 <= dpid <= 4:  # Core
            if dst_ip.startswith('10.0.0.'):
                host_num = int(dst_ip.split('.')[-1])
                if 1 <= host_num <= 16:
                    target_pod = (host_num - 1) // 4
                    out_ports = [target_pod + 1]
                else:
                    out_ports = [1, 2, 3, 4]
            else:
                out_ports = [1, 2, 3, 4]

        # Send ARP (avoid input port)
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