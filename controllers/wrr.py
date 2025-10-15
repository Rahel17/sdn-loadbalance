# controllers/wrr.py
# Ryu OpenFlow 1.3 - WRR load balancer with ECMP on fat-tree
# - Uses a VIP (10.0.0.100) and balances to real servers via WRR
# - ECMP = all shortest paths only (no explosive all-paths)
# - Precompute/update paths only when topology/hosts change
# - Replies ARP for VIP and does simple IP+MAC rewriting on edge switches

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, arp
from ryu.lib.packet import ether_types
from ryu.topology import event
from ryu.topology.api import get_all_link
from collections import deque
import logging
import random
import time

class WRRController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    FLOW_IDLE = 30  # seconds (idle timeout)

    # ---- Load balancer config ----
    VIP_IP = '10.0.0.100'
    VIP_MAC = '00:00:00:00:01:00'  # virtual MAC we will advertise by ARP

    # Real backend servers (hosts in your fat-tree)
    SERVER_LIST = ['10.0.0.1', '10.0.0.2', '10.0.0.3']
    WEIGHTS = {'10.0.0.1': 3, '10.0.0.2': 2, '10.0.0.3': 1}

    def __init__(self, *args, **kwargs):
        super(WRRController, self).__init__(*args, **kwargs)
        self.logger.setLevel(logging.INFO)

        # Runtime state
        self.datapaths = {}       # dpid -> datapath
        self.adj = {}             # dpid -> {neighbor_dpid: port_no_to_neighbor}
        self.hosts = {}           # ip -> (dpid, port_no, mac)
        self.paths_cache = {}     # (src_dpid, dst_dpid) -> [paths]

        # WRR state
        self.server_list = list(self.SERVER_LIST)
        self.weights = dict(self.WEIGHTS)
        self.current_index = -1
        self.current_weight = 0
        self.max_weight = max(self.weights.values())
        self.gcd_weight = 1  # simple; weights above are small

    # -------------------------
    # WRR selection
    # -------------------------
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

    # -------------------------
    # Datapath lifecycle
    # -------------------------
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if dp.id not in self.datapaths:
                self.datapaths[dp.id] = dp
                self.logger.info("Register datapath: %s", dp.id)
        elif ev.state == DEAD_DISPATCHER:
            if dp.id in self.datapaths:
                del self.datapaths[dp.id]
                self.logger.info("Unregister datapath: %s", dp.id)
            # cleanup minor caches
            self.adj.pop(dp.id, None)
            # paths cache may contain entries via this dpid; easiest is to drop all
            self.paths_cache.clear()

    # -------------------------
    # Default table-miss: send to controller
    # -------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=0,
                                match=match, instructions=inst)
        datapath.send_msg(mod)
        self.logger.info("Switch %s connected. Default rule installed.", datapath.id)

    # -------------------------
    # Topology building
    # -------------------------
    @set_ev_cls(event.EventSwitchEnter)
    def handle_switch_enter(self, ev):
        self._build_topology()

    @set_ev_cls(event.EventLinkAdd)
    def handle_link_add(self, ev):
        l = ev.link
        s1, s2 = l.src, l.dst
        self.adj.setdefault(s1.dpid, {})[s2.dpid] = s1.port_no
        self.adj.setdefault(s2.dpid, {})[s1.dpid] = s2.port_no
        self.paths_cache.clear()  # topology changed -> clear cache
        self.logger.debug("Link added: %s:%s -> %s:%s", s1.dpid, s1.port_no, s2.dpid, s2.port_no)

    def _build_topology(self):
        self.adj = {}
        links = get_all_link(self)
        for l in links:
            s1 = l.src; s2 = l.dst
            self.adj.setdefault(s1.dpid, {})[s2.dpid] = s1.port_no
            self.adj.setdefault(s2.dpid, {})[s1.dpid] = s2.port_no
        self.paths_cache.clear()
        self.logger.info("Topology built. switches: %s", sorted(self.adj.keys()))

    # -------------------------
    # ECMP shortest paths (BFS)
    # -------------------------
    def ecmp_paths(self, src, dst):
        key = (src, dst)
        if key in self.paths_cache:
            return self.paths_cache[key][:]
        # BFS to collect all shortest paths only
        if src == dst:
            self.paths_cache[key] = [[src]]
            return [[src]]
        queue = deque([[src]])
        paths = []
        visited_depth = {src: 0}
        shortest_depth = None
        while queue:
            path = queue.popleft()
            node = path[-1]
            depth = len(path) - 1
            if shortest_depth is not None and depth > shortest_depth:
                continue
            if node == dst:
                paths.append(path)
                shortest_depth = depth
                continue
            for nbr in self.adj.get(node, {}):
                if nbr in path:
                    continue
                nd = depth + 1
                prev = visited_depth.get(nbr)
                if prev is None or nd <= prev:
                    visited_depth[nbr] = nd
                    queue.append(path + [nbr])
        self.paths_cache[key] = paths[:]
        return paths

    def first_shortest_path(self, src, dst):
        ps = self.ecmp_paths(src, dst)
        return ps[0] if ps else None

    # -------------------------
    # Helpers to send OF messages
    # -------------------------
    def add_flow(self, datapath, priority, match, actions, idle=FLOW_IDLE):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst,
                                idle_timeout=idle)
        datapath.send_msg(mod)

    # -------------------------
    # Install path WITHOUT NAT (normal host-to-host)
    # -------------------------
    def install_plain_path(self, src_ip, dst_ip, path, src_port, dst_port, client_mac=None, server_mac=None):
        if not path:
            return
        for i, dpid in enumerate(path):
            dp = self.datapaths.get(dpid)
            if not dp:
                continue
            parser = dp.ofproto_parser
            ofp = dp.ofproto

            if dpid == path[-1]:
                out_port = dst_port
            else:
                next_dpid = path[i+1]
                out_port = self.adj[dpid].get(next_dpid)
                if out_port is None:
                    continue

            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                    ipv4_src=src_ip, ipv4_dst=dst_ip)
            actions = [parser.OFPActionOutput(out_port)]
            self.add_flow(dp, 20, match, actions)

        # reverse path
        rev = list(reversed(path))
        for i, dpid in enumerate(rev):
            dp = self.datapaths.get(dpid)
            if not dp:
                continue
            parser = dp.ofproto_parser
            ofp = dp.ofproto

            if dpid == rev[-1]:
                out_port = src_port
            else:
                next_dpid = rev[i+1]
                out_port = self.adj[dpid].get(next_dpid)
                if out_port is None:
                    continue

            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                    ipv4_src=dst_ip, ipv4_dst=src_ip)
            actions = [parser.OFPActionOutput(out_port)]
            self.add_flow(dp, 20, match, actions)

    # -------------------------
    # Install path WITH NAT at edges (VIP -> real server)
    # -------------------------
    def install_nat_path(self, client_ip, client_mac, path, src_port,
                         real_srv_ip, srv_dpid, srv_port, srv_mac):
        """
        Forward: match (client_ip -> VIP), at last hop set IP dst=real_srv_ip and set eth_dst=srv_mac
        Reverse: match (real_srv_ip -> client_ip), at first hop from server set IP src=VIP and set eth_src=VIP_MAC
        """
        if not path:
            return

        # forward path (client -> VIP -> server)
        for i, dpid in enumerate(path):
            dp = self.datapaths.get(dpid)
            if not dp:
                continue
            parser = dp.ofproto_parser

            if dpid == path[-1]:  # last hop to server, rewrite IP+MAC
                out_port = srv_port
                actions = [
                    parser.OFPActionSetField(ipv4_dst=real_srv_ip),
                    parser.OFPActionSetField(eth_dst=srv_mac),
                    parser.OFPActionOutput(out_port)
                ]
            else:
                next_dpid = path[i+1]
                out_port = self.adj[dpid].get(next_dpid)
                if out_port is None:
                    continue
                actions = [parser.OFPActionOutput(out_port)]

            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                    ipv4_src=client_ip, ipv4_dst=self.VIP_IP)
            self.add_flow(dp, 30, match, actions)

        # reverse path (server -> client)
        rev = list(reversed(path))
        for i, dpid in enumerate(rev):
            dp = self.datapaths.get(dpid)
            if not dp:
                continue
            parser = dp.ofproto_parser

            if dpid == rev[0]:  # first hop leaving server: rewrite src IP to VIP and src MAC to VIP_MAC
                if len(rev) >= 2:
                    next_dpid = rev[1]
                    out_port = self.adj[dpid].get(next_dpid)
                    if out_port is None:
                        continue
                else:
                    out_port = src_port  # degenerate

                actions = [
                    parser.OFPActionSetField(ipv4_src=self.VIP_IP),
                    parser.OFPActionSetField(eth_src=self.VIP_MAC),
                    parser.OFPActionOutput(out_port)
                ]
            elif dpid == rev[-1]:  # last hop to client: set eth_src=VIP_MAC, eth_dst=client_mac
                out_port = src_port
                actions = [
                    parser.OFPActionSetField(eth_src=self.VIP_MAC),
                    parser.OFPActionSetField(eth_dst=client_mac),
                    parser.OFPActionOutput(out_port)
                ]
            else:
                next_dpid = rev[i+1]
                out_port = self.adj[dpid].get(next_dpid)
                if out_port is None:
                    continue
                actions = [parser.OFPActionOutput(out_port)]

            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                    ipv4_src=real_srv_ip, ipv4_dst=client_ip)
            self.add_flow(dp, 30, match, actions)

    # -------------------------
    # PacketIn
    # -------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match.get('in_port')

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        # Drop LLDP/IPv6 multicast early
        if eth.ethertype in (ether_types.ETH_TYPE_LLDP, ether_types.ETH_TYPE_IPV6) or eth.dst.startswith('33:33'):
            return

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        arp_pkt = pkt.get_protocol(arp.arp)

        # Learn hosts (IP -> attachment)
        if ip_pkt:
            self.hosts[ip_pkt.src] = (dpid, in_port, eth.src)
        elif arp_pkt and arp_pkt.src_ip != '0.0.0.0':
            self.hosts[arp_pkt.src_ip] = (dpid, in_port, eth.src)

        # --- Handle ARP for VIP: reply directly ---
        if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip == self.VIP_IP:
            self.reply_arp(datapath, in_port, eth.src, arp_pkt)
            return

        # --- IP handling ---
        if ip_pkt:
            src_ip = ip_pkt.src
            dst_ip = ip_pkt.dst

            # If traffic to VIP -> do WRR to a real server with NAT path
            if dst_ip == self.VIP_IP:
                # choose server
                srv_ip = self.get_next_server()
                if srv_ip not in self.hosts:
                    # server not learned yet: flood to help ARP learning
                    self.flood(datapath, in_port, msg)
                    return
                srv_dpid, srv_port, srv_mac = self.hosts[srv_ip]

                # build ECMP path from current switch to server's switch
                path = self.first_shortest_path(dpid, srv_dpid)
                if not path:
                    self.flood(datapath, in_port, msg)
                    return

                # need client info
                if src_ip not in self.hosts:
                    self.hosts[src_ip] = (dpid, in_port, eth.src)
                cli_dpid, cli_port, cli_mac = self.hosts[src_ip]

                # if PacketIn not at client's dpid, extend path from client's dpid
                if path[0] != cli_dpid:
                    path = self.first_shortest_path(cli_dpid, srv_dpid)

                # install NAT path both directions
                self.install_nat_path(src_ip, cli_mac, path, cli_port, srv_ip, srv_dpid, srv_port, srv_mac)
                self.logger.info("NAT path %s -> %s via %s : %s", src_ip, self.VIP_IP, srv_ip, path)

                # send the current packet along next hop
                out_port = self.next_hop_port(cli_dpid, path, cli_port, srv_port)
                actions = [parser.OFPActionOutput(out_port)] if out_port else []
                if actions:
                    data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
                    out = parser.OFPPacketOut(datapath=self.datapaths[cli_dpid],
                                              buffer_id=msg.buffer_id if datapath.id == cli_dpid else ofp.OFP_NO_BUFFER,
                                              in_port=in_port if datapath.id == cli_dpid else ofp.OFPP_CONTROLLER,
                                              actions=actions,
                                              data=data)
                    self.datapaths[cli_dpid].send_msg(out)
                return

            # Otherwise: normal host-to-host routing (shortest path)
            if dst_ip in self.hosts:
                dst_dpid, dst_port, dst_mac = self.hosts[dst_ip]
                path = self.first_shortest_path(dpid, dst_dpid)
                if not path:
                    self.flood(datapath, in_port, msg)
                    return

                # align path from true src attachment
                src_dpid, src_port, src_mac = self.hosts.get(src_ip, (dpid, in_port, eth.src))
                if path[0] != src_dpid:
                    path = self.first_shortest_path(src_dpid, dst_dpid)

                self.install_plain_path(src_ip, dst_ip, path, src_port, dst_port,
                                        client_mac=src_mac, server_mac=dst_mac)
                self.logger.info("Path %s -> %s : %s", src_ip, dst_ip, path)

                # push this packet to next hop
                out_port = self.next_hop_port(src_dpid, path, src_port, dst_port)
                if out_port:
                    data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
                    out = parser.OFPPacketOut(datapath=self.datapaths[src_dpid],
                                              buffer_id=msg.buffer_id if datapath.id == src_dpid else ofp.OFP_NO_BUFFER,
                                              in_port=in_port if datapath.id == src_dpid else ofp.OFPP_CONTROLLER,
                                              actions=[parser.OFPActionOutput(out_port)],
                                              data=data)
                    self.datapaths[src_dpid].send_msg(out)
                return

        # Fallback: flood to learn hosts
        self.flood(datapath, in_port, msg)

    # -------------------------
    # Utilities
    # -------------------------
    def next_hop_port(self, start_dpid, path, start_port, end_port):
        """Pick output port at the first hop along path from start_dpid."""
        if not path:
            return None
        if start_dpid == path[-1]:  # already at destination switch
            return end_port
        if start_dpid != path[0]:
            return None
        if len(path) == 1:
            return end_port
        next_dpid = path[1]
        return self.adj[start_dpid].get(next_dpid)

    def flood(self, datapath, in_port, msg):
        parser = datapath.ofproto_parser
        ofp = datapath.ofproto
        actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]
        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=msg.buffer_id,
                                  in_port=in_port,
                                  actions=actions,
                                  data=data)
        datapath.send_msg(out)

    def reply_arp(self, datapath, in_port, src_mac, arp_req):
        """Reply ARP who-has VIP -> VIP_MAC."""
        parser = datapath.ofproto_parser
        ofp = datapath.ofproto

        e = ethernet.ethernet(dst=src_mac, src=self.VIP_MAC, ethertype=ether_types.ETH_TYPE_ARP)
        a = arp.arp(opcode=arp.ARP_REPLY,
                    src_mac=self.VIP_MAC, src_ip=self.VIP_IP,
                    dst_mac=src_mac,     dst_ip=arp_req.src_ip)
        p = packet.Packet()
        p.add_protocol(e)
        p.add_protocol(a)
        p.serialize()

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=ofp.OFP_NO_BUFFER,
                                  in_port=ofp.OFPP_CONTROLLER,
                                  actions=[parser.OFPActionOutput(in_port)],
                                  data=p.data)
        datapath.send_msg(out)
        self.logger.debug("Sent ARP reply for VIP %s to %s", self.VIP_IP, arp_req.src_ip)
