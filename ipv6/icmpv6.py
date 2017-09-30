from scapy.all import *
import binascii
from multiprocessing.pool import ThreadPool
from copy import copy
from ipv6 import get_source_address, createIPv6, getMacAddress, grabRawSrc

class ICMPv6:
    def init(self):
        None

    def echoAllNodes(self, receive=False):
        ip_packet = createIPv6()
        ip_packet.fields["version"] = 6L
        ip_packet.fields["tc"] = 0L
        ip_packet.fields["nh"] = 58
        ip_packet.fields["hlim"] = 1
        ip_packet.fields["dst"] = "ff02::1"
        if "src" not in ip_packet.fields:
            ip_packet.fields["src"] = get_source_address(ip_packet)


        """
               #ICMPv6 Packet
               0                   1                   2                   3
               0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
              +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
              |     Type      |     Code      |          Checksum             |
              +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
              |                                                               |
              +                         Message Body                          +
              |                                                               |
              +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
        """


        icmp_packet = ICMPv6EchoRequest()
        icmp_packet.fields["code"] = 0
        icmp_packet.fields["seq"] = 1
        icmp_packet.fields["type"] = 128
        data = "e3d3f15500000000f7f0010000000000101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f3031323334353637"
        icmp_packet.fields["data"] = binascii.unhexlify(data)

        # if receive is true, set up listener
        if receive:
            build_lfilter = lambda (packet): ICMPv6EchoReply in packet
            pool = ThreadPool(processes=1)
            async_result = pool.apply_async(self.listenForEcho,[build_lfilter])

        send(ip_packet / icmp_packet,verbose=False)

        # if receive, return response
        if receive:
            responseDict = {}
            return_val = async_result.get()
            for response in return_val:
                ip = response[IPv6].src
                rawSrc = copy(response[IPv6])
                rawSrc.remove_payload()
                rawSrc = grabRawSrc(rawSrc)
                mac = getMacAddress(rawSrc)
                responseDict[ip] = {"mac":mac}
            return responseDict



    def echoAllNodeNames(self, receive=False):
        ip_packet = createIPv6()
        ip_packet.fields["dst"] = "ff02::1"

        if "src" not in ip_packet.fields:
            ip_packet.fields["src"] = get_source_address(ip_packet)

        icmp_packet = ICMPv6NIQueryName()
        icmp_packet.fields["code"] = 0
        icmp_packet.fields["type"] = 139
        icmp_packet.fields["unused"] = 0L
        icmp_packet.fields["flags"] = 0L
        icmp_packet.fields["qtype"] = 2
        icmp_packet.fields["data"] = (0, 'ff02::1')

        # set up sniffer if receive
        if receive:
            build_lfilter = lambda (packet): ICMPv6NIReplyName in packet
            pool = ThreadPool(processes=1)
            async_result = pool.apply_async(self.listenForEcho,[build_lfilter])

        send(ip_packet / icmp_packet)

        # return response if receive
        if receive:
            responseDict = {}
            return_val = async_result.get()
            for response in return_val:
                ip = response[IPv6].src
                rawSrc = copy(response[IPv6])
                rawSrc.remove_payload()
                rawSrc = grabRawSrc(rawSrc)
                mac = getMacAddress(rawSrc)
                device_name = response[ICMPv6NIReplyName].fields["data"][1][1].strip()
                responseDict[ip] = {"mac":mac,"device_name":device_name}
            return responseDict


    def echoMulticastQuery(self, receive=False):
        ip_packet = createIPv6()
        ip_packet.fields["dst"] = "ff02::1"
        ip_packet.fields["nh"] = 0

        router_alert = RouterAlert()
        router_alert.fields["otype"] = 5
        router_alert.fields["value"] = 0
        router_alert.fields["optlen"] = 2

        padding = PadN()
        padding.fields["otype"] = 1
        padding.fields["optlen"] = 0

        ip_ext = IPv6ExtHdrHopByHop()
        ip_ext.fields["nh"] = 58
        ip_ext.fields["options"] = [router_alert,padding]
        ip_ext.fields["autopad"] = 1

        if "src" not in ip_packet.fields:
            ip_packet.fields["src"] = get_source_address(ip_packet)

        icmp_packet = ICMPv6MLQuery()
        icmp_packet.fields["code"] = 0
        icmp_packet.fields["reserved"] = 0
        icmp_packet.fields["mladdr"] = "::"
        flags = "02"
        qqic = "7d" #125
        numberOfSources = "0000"
        raw = Raw()
        raw.fields["load"] =  binascii.unhexlify(flags + qqic + numberOfSources)

        payload = ip_packet/ip_ext/icmp_packet/raw

        if receive:
            filter = lambda (packet): IPv6 in packet
            ###Add function here
            responseDict = {}
            responses = self.send_receive(payload,filter,8)
            for response in responses:
                if self.isMulticastReportv2(response):
                    reports = self.parseMulticastReport(response[Raw])
                    ip = response[IPv6].src
                    rawSrc = copy(response[IPv6])
                    rawSrc.remove_payload()
                    rawSrc = grabRawSrc(rawSrc)
                    mac = getMacAddress(rawSrc)
                    if ip in responseDict:
                        responseDict[ip]["multicast_report"] += reports
                    else:
                        responseDict[ip] = {"mac":mac,"multicast_report":reports}
            return responseDict
        else:
            send(payload)



    def send_receive(self,payload,filter,timeout=2):
        build_lfilter = filter
        pool = ThreadPool(processes=1)
        async_result = pool.apply_async(self.listenForEcho,[build_lfilter,timeout])

        send(payload)

        responses = async_result.get()
        return responses

    def isMulticastReportv2(self,response):
        if Raw in response and binascii.hexlify(str(response[Raw]))[0:2] == "8f":
            return True



    def parseMulticastReport(self,payload):
        responseDict = []
        raw_packet = binascii.hexlify(str(payload))
        type = raw_packet[0:2]
        code = raw_packet[2:4]
        cksum = raw_packet[4:8]
        reserved = raw_packet[8:12]
        num_of_records = int(raw_packet[12:16],16)

        for record in xrange(num_of_records):
            offset = (16 + (40 * record))
            record_data = raw_packet[offset:(offset + 40)]
            record_type = record_data[0:2]
            data_len = record_data[2:4]
            num_of_sources = record_data[4:8]
            multicast_address = record_data[8:40]
            multicast_address = ':'.join([multicast_address[i:i+4] for i in range(0, len(multicast_address), 4)])
            multicast_address = IPv6(dst = multicast_address).fields["dst"]
            responseDict.append({"record_type": record_type,
                                 "multicast_address":multicast_address,
                                 "service":self.getService(multicast_address)})

        return responseDict

    def getService(self,multicast_address):
        serviceDict = {"ff02::202":"RPC",
            "ff02::fb":"mDNS",
            "ff02::1:3":"LLMNR",
            "ff02::c":"SSDP",
            "ff02::116":"SRVLOC",
            "ff02::123":"SVRLOC-DA",
            "ff05::2":"OSPFv3",
            "ff02::2":"Router",
            "ff02::1000":"SLP",
            "ff02::2:ff2e:b774": "FreeBSD"}
        if multicast_address in serviceDict:
            return serviceDict[multicast_address]
        else:
            return ""

    def listenForEcho(self,build_lfilter,timeout=2):
        response = sniff(lfilter=build_lfilter, timeout=timeout)
        return response