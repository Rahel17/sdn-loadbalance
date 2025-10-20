from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4

class WeightedLeastConnectionLB(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(WeightedLeastConnectionLB, self).__init__(*args, **kwargs)
        self.servers = [
            {'ip': '10.0.0.1', 'weight': 3, 'connections': 0},
            {'ip': '10.0.0.2', 'weight': 2, 'connections': 0},
            {'ip': '10.0.0.3', 'weight': 1, 'connections': 0}
        ]

    def select_server(self):
        # Pilih server dengan koneksi paling sedikit (dibagi bobot)
        server = min(self.servers, key=lambda s: s['connections'] / s['weight'])
        server['connections'] += 1
        self.logger.info(f"Selected server: {server['ip']} (conn={server['connections']})")
        return server['ip']

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        pkt = packet.Packet(msg.data)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if not ip_pkt:
            return

        dst_ip = self.select_server()
        actions = [parser.OFPActionOutput(2)]  # sesuaikan port server
        match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
        self.add_flow(datapath, 1, match, actions)
