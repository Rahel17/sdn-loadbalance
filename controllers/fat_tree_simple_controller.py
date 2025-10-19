from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4
import time


class FatTreeSimple(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(FatTreeSimple, self).__init__(*args, **kwargs)
        self.logger.info("=== FatTree Simple Controller Started ===")
        self.datapaths = {}
        self.packet_count = 0
        self.last_log_time = time.time()
        
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.logger.info(f"*** Switch {dpid} connected - Installing flows ***")
        self.datapaths[dpid] = datapath

        # Delete all flows
        match = parser.OFPMatch()
        self.del_flow(datapath, match)

        # Install table-miss: send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                         ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        
        # Only install proactive flows for IP
        self.install_ip_flows(datapath, dpid)

    def install_ip_flows(self, datapath, dpid):
        """Install only IP forwarding rules, let controller handle ARP"""
        parser = datapath.ofproto_parser
        
        # Core switches (1-4)
        if 1 <= dpid <= 4:
            for pod in range(4):
                for offset in range(4):
                    host_ip = f"10.0.0.{pod * 4 + offset + 1}"
                    match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=host_ip)
                    actions = [parser.OFPActionOutput(pod + 1)]
                    self.add_flow(datapath, 10, match, actions)
            self.logger.info(f"  CORE {dpid}: Installed IP flows")
            
        # Aggregation switches (5-12)
        elif 5 <= dpid <= 12:
            pod = (dpid - 5) // 2
            for edge_offset in range(2):
                for host_offset in range(2):
                    host_num = pod * 4 + edge_offset * 2 + host_offset + 1
                    host_ip = f"10.0.0.{host_num}"
                    match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=host_ip)
                    actions = [parser.OFPActionOutput(edge_offset + 1)]
                    self.add_flow(datapath, 10, match, actions)
            
            # Default: to core
            match = parser.OFPMatch(eth_type=0x0800)
            actions = [parser.OFPActionOutput(3)]
            self.add_flow(datapath, 5, match, actions)
            self.logger.info(f"  AGG {dpid} (pod {pod}): Installed IP flows")
            
        # Edge switches (13-20)
        elif 13 <= dpid <= 20:
            edge_num = dpid - 13
            base_host = edge_num * 2 + 1
            for i in range(2):
                host_ip = f"10.0.0.{base_host + i}"
                match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=host_ip)
                actions = [parser.OFPActionOutput(i + 1)]
                self.add_flow(datapath, 10, match, actions)
            
            # Default: to agg
            match = parser.OFPMatch(eth_type=0x0800)
            actions = [parser.OFPActionOutput(3)]
            self.add_flow(datapath, 5, match, actions)
            self.logger.info(f"  EDGE {dpid}: Installed IP flows")

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
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
        """Handle ARP only - forward intelligently without flooding"""
        self.packet_count += 1
        
        # Rate limit logging
        now = time.time()
        if now - self.last_log_time > 2:  # Log every 2 seconds
            self.logger.info(f"Packets handled: {self.packet_count}")
            self.last_log_time = now
            
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Only handle ARP
        if eth.ethertype != 0x0806:
            return

        arp_pkt = pkt.get_protocol(arp.arp)
        
        # Determine output strategy based on switch type
        out_ports = []
        
        if 13 <= dpid <= 20:  # Edge
            # From host -> send to agg only
            # From agg -> send to hosts only
            if in_port <= 2:
                out_ports = [3, 4]  # Both agg uplinks
            else:
                out_ports = [1, 2]  # Both hosts
                
        elif 5 <= dpid <= 12:  # Agg
            if in_port <= 2:
                out_ports = [3, 4]  # Both cores
            else:
                out_ports = [1, 2]  # Both edges
                
        elif 1 <= dpid <= 4:  # Core
            # Forward to all agg switches
            out_ports = [1, 2, 3, 4]

        # Send packet out - IMPORTANT: Don't send back to input port!
        for port in out_ports:
            if port != in_port:  # Never send back to input port
                actions = [parser.OFPActionOutput(port)]
                out = parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=ofproto.OFP_NO_BUFFER,
                    in_port=in_port,
                    actions=actions,
                    data=msg.data
                )
                datapath.send_msg(out)