from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp
from collections import defaultdict
import random

class WeightedRoundRobin(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install default rule (send all unmatched packets to controller)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        mod = parser.OFPFlowMod(datapath=datapath,
                                priority=0,
                                match=match,
                                instructions=inst)
        datapath.send_msg(mod)

        self.logger.info(f"Switch %s connected, default flow installed", datapath.id)

    def __init__(self, *args, **kwargs):
        super(WeightedRoundRobin, self).__init__(*args, **kwargs)
        self.server_list = ['10.0.0.1', '10.0.0.2', '10.0.0.3']
        self.weights = {'10.0.0.1': 3, '10.0.0.2': 2, '10.0.0.3': 1}
        self.current_index = -1
        self.current_weight = 0
        self.max_weight = max(self.weights.values())
        self.gcd_weight = 1  # bisa dihitung otomatis jika ingin dinamis

    def get_next_server(self):
        servers = self.server_list
        while True:
            self.current_index = (self.current_index + 1) % len(servers)
            if self.current_index == 0:
                self.current_weight -= self.gcd_weight
                if self.current_weight <= 0:
                    self.current_weight = self.max_weight
            if self.weights[servers[self.current_index]] >= self.current_weight:
                return servers[self.current_index]

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        ip = pkt.get_protocol(ipv4.ipv4)

        if not ip:
            return

        src_ip = ip.src
        dst_ip = ip.dst

        selected_server = self.get_next_server()
        self.logger.info(f"Client {src_ip} diarahkan ke Server {selected_server}")

                # Tentukan output port (sementara contoh sederhana)
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]

        # Buat flow entry sederhana agar traffic berikutnya tidak masuk controller lagi
        match = parser.OFPMatch(in_port=in_port, eth_type=0x0800,
                                ipv4_src=src_ip, ipv4_dst=dst_ip)
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        mod = parser.OFPFlowMod(datapath=datapath, priority=1,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

        # Kirim packet_out agar paket pertama langsung dikirim
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)


        # Kirim flow mod (belum lengkap — nanti kita tambahkan bagian forwarding-nya)
