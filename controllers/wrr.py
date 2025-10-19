from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4
from ryu.lib.packet import ether_types
from math import gcd


class WRRController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(WRRController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.server_list = [
            {'ip': '10.0.0.1', 'mac': None, 'weight': 3},
            {'ip': '10.0.0.2', 'mac': None, 'weight': 2},
            {'ip': '10.0.0.3', 'mac': None, 'weight': 1},
        ]
        self.vip = '10.0.0.100'
        self.current_index = 0
        self.current_weight = 0
        self.max_weight = max(s['weight'] for s in self.server_list)
        self.gcd_weight = self._gcd_list([s['weight'] for s in self.server_list])

    def _gcd_list(self, weights):
        result = weights[0]
        for w in weights[1:]:
            result = gcd(result, w)
        return result

    def _get_next_server(self):
        while True:
            self.current_index = (self.current_index + 1) % len(self.server_list)
            if self.current_index == 0:
                self.current_weight -= self.gcd_weight
                if self.current_weight <= 0:
                    self.current_weight = self.max_weight
            if self.server_list[self.current_index]['weight'] >= self.current_weight:
                return self.server_list[self.current_index]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Table-miss rule
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=0, match=match, instructions=inst)
        datapath.send_msg(mod)

        self.logger.info(f"Switch %s connected.", datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        dst = eth.dst
        src = eth.src

        self.mac_to_port[dpid][src] = in_port

        # Jika paket ARP
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            if arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip == self.vip:
                self._reply_arp(datapath, in_port, eth, arp_pkt)
                return
            elif arp_pkt.opcode == arp.ARP_REPLY:
                for s in self.server_list:
                    if s['ip'] == arp_pkt.src_ip:
                        s['mac'] = arp_pkt.src_mac

        # Jika paket IPv4
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            if ip_pkt.dst == self.vip:
                self._handle_vip(datapath, in_port, eth, ip_pkt)
                return

        # ==== basic learning switch ====
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install flow untuk trafik berikutnya
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            mod = parser.OFPFlowMod(datapath=datapath, priority=1,
                                    match=match, instructions=inst)
            datapath.send_msg(mod)

        # Kirim langsung paket saat ini
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=ofproto.OFP_NO_BUFFER,
                                  in_port=in_port, actions=actions, data=msg.data)
        datapath.send_msg(out)

    def _reply_arp(self, datapath, in_port, eth, arp_pkt):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        server = self._get_next_server()
        if not server['mac']:
            self.logger.info("Server belum diketahui MAC-nya, abaikan ARP Reply.")
            return

        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(
            ethertype=eth.ethertype, dst=eth.src, src=server['mac']))
        pkt.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY,
            src_mac=server['mac'],
            src_ip=self.vip,
            dst_mac=eth.src,
            dst_ip=arp_pkt.src_ip))
        pkt.serialize()

        actions = [parser.OFPActionOutput(in_port)]
        out = parser.OFPPacketOut(
            datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER, actions=actions, data=pkt.data)
        datapath.send_msg(out)
        self.logger.info(f"Balas ARP untuk {arp_pkt.src_ip} dengan server {server['ip']}.")

    def _handle_vip(self, datapath, in_port, eth, ip_pkt):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        server = self._get_next_server()
        if not server['mac']:
            self.logger.warning("Server MAC belum diketahui, skip.")
            return

        actions = [
            parser.OFPActionSetField(eth_dst=server['mac']),
            parser.OFPActionSetField(ipv4_dst=server['ip']),
            parser.OFPActionOutput(ofproto.OFPP_NORMAL)
        ]
        match = parser.OFPMatch(in_port=in_port, eth_type=0x0800, ipv4_dst=self.vip)
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=10, match=match, instructions=inst)
        datapath.send_msg(mod)
        self.logger.info(f"Trafik ke {self.vip} diarahkan ke {server['ip']}.")
