from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, arp
from ryu.lib import hub

# -------------------------------
# PILIH ALGORITMA YANG DIPAKAI
# -------------------------------
# "WRR" untuk Weighted Round Robin
# "WLC" untuk Weighted Least Connection
ALGORITHM = "WRR"

class FatTreeLoadBalancer(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(FatTreeLoadBalancer, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.server_list = {
            '10.0.0.5': {'weight': 3, 'active_conn': 0},
            '10.0.0.6': {'weight': 2, 'active_conn': 0},
            '10.0.0.7': {'weight': 1, 'active_conn': 0}
        }
        self.current_server = 0
        self.server_ips = list(self.server_list.keys())
        self.monitor_thread = hub.spawn(self._monitor)
        self.logger.info(f"=== Load Balancer started with {ALGORITHM} algorithm ===")

    def _monitor(self):
        """Thread untuk memantau koneksi aktif (simulasi monitoring beban)"""
        while True:
            hub.sleep(10)
            self.logger.info("Server status:")
            for ip, data in self.server_list.items():
                self.logger.info(f"{ip} -> active_conn={data['active_conn']} weight={data['weight']}")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Mengatur table-miss flow"""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info(f"Switch {datapath.id} terhubung.")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0, hard_timeout=0):
        """Menambahkan rule flow ke switch"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst,
                                    idle_timeout=idle_timeout,
                                    hard_timeout=hard_timeout)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst,
                                    idle_timeout=idle_timeout,
                                    hard_timeout=hard_timeout)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Menangani packet-in dari switch"""
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == 0x88cc:  # LLDP
            return
        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        in_port = msg.match['in_port']
        self.mac_to_port[dpid][src] = in_port

        # Tangani ARP dulu agar host bisa kenal IP
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            self.handle_arp(datapath, in_port, eth, arp_pkt)
            return

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if not ip_pkt:
            return

        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst

        # Jika tujuan adalah salah satu server, arahkan lewat algoritma
        if dst_ip in self.server_ips:
            selected_ip = self.select_server()
            self.logger.info(f"{ALGORITHM}: {src_ip} diarahkan ke {selected_ip}")

            # update jumlah koneksi
            self.server_list[selected_ip]['active_conn'] += 1

            # buat flow rule untuk aliran ini
            actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
            match = parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip, ipv4_dst=dst_ip)
            self.add_flow(datapath, 1, match, actions, idle_timeout=30)

        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=msg.buffer_id,
                                  in_port=in_port,
                                  actions=actions,
                                  data=data)
        datapath.send_msg(out)

    def handle_arp(self, datapath, port, eth, arp_pkt):
        """Tangani permintaan ARP"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        if arp_pkt.opcode != arp.ARP_REQUEST:
            return

        dst_ip = arp_pkt.dst_ip
        if dst_ip in self.server_ips:
            # balas ARP secara manual
            pkt = packet.Packet()
            pkt.add_protocol(ethernet.ethernet(
                ethertype=eth.ethertype,
                dst=eth.src,
                src=eth.dst))
            pkt.add_protocol(arp.arp(
                opcode=arp.ARP_REPLY,
                src_mac=eth.dst,
                src_ip=dst_ip,
                dst_mac=eth.src,
                dst_ip=arp_pkt.src_ip))
            pkt.serialize()

            actions = [parser.OFPActionOutput(port)]
            out = parser.OFPPacketOut(datapath=datapath,
                                      buffer_id=ofproto.OFP_NO_BUFFER,
                                      in_port=ofproto.OFPP_CONTROLLER,
                                      actions=actions, data=pkt.data)
            datapath.send_msg(out)

    # -------------------------------
    # IMPLEMENTASI ALGORITMA
    # -------------------------------
    def select_server(self):
        """Memilih server berdasarkan algoritma aktif"""
        if ALGORITHM == "WRR":
            return self.weighted_round_robin()
        elif ALGORITHM == "WLC":
            return self.weighted_least_connection()
        else:
            return self.server_ips[0]

    def weighted_round_robin(self):
        """Weighted Round Robin"""
        total_weight = sum(s['weight'] for s in self.server_list.values())
        self.current_server = (self.current_server + 1) % total_weight
        cum_weight = 0
        for ip, data in self.server_list.items():
            cum_weight += data['weight']
            if self.current_server < cum_weight:
                return ip
        return self.server_ips[0]

    def weighted_least_connection(self):
        """Weighted Least Connection"""
        min_ratio = float('inf')
        selected_ip = None
        for ip, data in self.server_list.items():
            ratio = data['active_conn'] / data['weight'] if data['weight'] > 0 else data['active_conn']
            if ratio < min_ratio:
                min_ratio = ratio
                selected_ip = ip
        return selected_ip
