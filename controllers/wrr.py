from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp

class WeightedRoundRobinLB(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(WeightedRoundRobinLB, self).__init__(*args, **kwargs)
        # Server pool (IP dan bobot)
        self.servers = [
            {'ip': '10.0.0.1', 'weight': 3},
            {'ip': '10.0.0.2', 'weight': 2},
            {'ip': '10.0.0.3', 'weight': 1}
        ]
        self.server_list = []
        for s in self.servers:
            self.server_list += [s['ip']] * s['weight']
        self.index = 0

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Default rule: forward to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        pkt = packet.Packet(msg.data)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if not ip_pkt:
            return

        # Jika paket dari client, pilih server tujuan
        dst_ip = self.select_server()

        # Forward ke server
        out_port = 2  # ganti sesuai port server
        actions = [parser.OFPActionOutput(out_port)]

        match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
        self.add_flow(datapath, 1, match, actions)
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=ofproto.OFP_NO_BUFFER,
                                  in_port=msg.match['in_port'],
                                  actions=actions,
                                  data=msg.data)
        datapath.send_msg(out)

    def select_server(self):
        server = self.server_list[self.index]
        self.index = (self.index + 1) % len(self.server_list)
        self.logger.info(f"Selected server: {server}")
        return server
