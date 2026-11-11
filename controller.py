"""Ryu OF1.3 learning switch with congestion-triggered background-flow filtering.

Mode: SDN_MODE=baseline (monitor only) or SDN_MODE=adaptive (temporary drop).
Background congestion traffic is TCP destination port 5001, exam is TCP 9999.
"""
import os
import time
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp

EXAM_PORT = 9999
BACKGROUND_PORT = 5001
MODE = os.environ.get('SDN_MODE', 'adaptive').lower()
# Threshold is measured in BYTES PER SECOND of existing background flow.
THRESHOLD_BPS = int(os.environ.get('BACKGROUND_THRESHOLD_BPS', 150000))
BLOCK_SECONDS = int(os.environ.get('BACKGROUND_BLOCK_SECONDS', 8))

class ExamNetworkController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.previous = {}
        self.last_block = {}
        self.monitor_thread = hub.spawn(self.monitor)
        self.logger.info('Exam controller mode=%s threshold=%d B/s', MODE, THRESHOLD_BPS)

    def add_flow(self, dp, priority, match, actions, hard_timeout=0):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        instructions = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority, match=match,
                                      instructions=instructions, hard_timeout=hard_timeout))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        dp = ev.msg.datapath
        self.add_flow(dp, 0, dp.ofproto_parser.OFPMatch(),
                      [dp.ofproto_parser.OFPActionOutput(dp.ofproto.OFPP_CONTROLLER, dp.ofproto.OFPCML_NO_BUFFER)])

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change(self, ev):
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[ev.datapath.id] = ev.datapath
        elif ev.state == DEAD_DISPATCHER:
            self.datapaths.pop(ev.datapath.id, None)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        msg, dp = ev.msg, ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        src, dst = eth.src, eth.dst
        learned = self.mac_to_port.setdefault(dp.id,{})
        learned[src] = in_port
        out_port = learned.get(dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        ip = pkt.get_protocol(ipv4.ipv4)
        seg = pkt.get_protocol(tcp.tcp)
        if out_port != ofp.OFPP_FLOOD:
            if ip and seg and seg.dst_port in (EXAM_PORT, BACKGROUND_PORT):
                match = parser.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=ip.src,
                                        ipv4_dst=ip.dst, tcp_dst=seg.dst_port)
                priority = 100 if seg.dst_port == EXAM_PORT else 20
                self.add_flow(dp, priority, match, actions)
                if seg.dst_port == EXAM_PORT:
                    self.logger.info('EXAM FLOW s%s %s -> %s', dp.id, ip.src, ip.dst)
            elif ip and seg:
                # Keep unrelated TCP flows separate; never install an overly broad
                # eth_dst rule that would hide subsequent exam/background flows.
                match = parser.OFPMatch(eth_type=0x0800, ip_proto=6,
                                        ipv4_src=ip.src, ipv4_dst=ip.dst,
                                        tcp_src=seg.src_port, tcp_dst=seg.dst_port)
                self.add_flow(dp, 5, match, actions)
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                    in_port=in_port, actions=actions,
                    data=msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None))

    def monitor(self):
        while True:
            for dp in list(self.datapaths.values()):
                dp.send_msg(dp.ofproto_parser.OFPFlowStatsRequest(dp))
            hub.sleep(2)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply(self, ev):
        dp = ev.msg.datapath
        now = time.monotonic()
        exam_bytes = sum(stat.byte_count for stat in ev.msg.body if stat.priority == 100)
        bg_bytes = sum(stat.byte_count for stat in ev.msg.body if stat.priority == 20)
        key = dp.id
        previous = self.previous.get(key)
        self.previous[key] = (now, exam_bytes, bg_bytes)
        if not previous:
            return
        interval = max(now - previous[0], 0.001)
        bg_rate = max(0, bg_bytes - previous[2]) / interval
        exam_rate = max(0, exam_bytes - previous[1]) / interval
        self.logger.info('MONITOR switch=%s exam=%.1fKB/s background=%.1fKB/s',
                         key, exam_rate/1024, bg_rate/1024)
        if MODE != 'adaptive' or bg_rate < THRESHOLD_BPS or key != 1:
            return
        if now - self.last_block.get(key, -1e9) < BLOCK_SECONDS + 2:
            return
        self.last_block[key] = now
        match = dp.ofproto_parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=BACKGROUND_PORT)
        self.add_flow(dp, 200, match, [], hard_timeout=BLOCK_SECONDS)
        self.logger.warning('CONGESTION: temporarily BLOCKED TCP/%s for %ss on s1 (%.1f KB/s)',
                            BACKGROUND_PORT, BLOCK_SECONDS, bg_rate/1024)
