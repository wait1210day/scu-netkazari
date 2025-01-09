#!/usr/bin/env python3

import socket
import sys
import struct
import random
import asyncio
import errno
from pytun import TunTapDevice


SERVER_IP = 'xxx.xxx.xxx.xxx'       # For server, IP
CLIENT_IFACE = 'wlan0'              # For client, sending package from which iface, use `None` for default

PROTO_HDR = b'\x66\xcc\xff\xff'
PROTO_HDR_LENGTH = len(PROTO_HDR)

TUN_LINK_MTU = 900
TUN_TRANSPORT_SIZE = TUN_LINK_MTU + 16

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

class KazariIO:
    sock: socket.socket

    def proto_recv_next(self, bufsize: int) -> tuple[bytes, tuple[str, int]]:
        pass

    def proto_send_next(self, payload: bytes) -> None:
        pass

    def proto_recv_next_checked(self, bufsize: int) -> tuple[bytes, tuple[str, int]]:
        while True:
            packet = self.proto_recv_next(bufsize)
            if packet is not None:
                return packet


class KazariTunnelClientIO(KazariIO):
    def __init__(self, ip: str, udp_port: int, iface: str = None):
        self.server_ip = ip
        self.server_port = udp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.proto_tx_seq = 0
        self.proto_rx_seq = 0
        if iface is not None:
            self.sock.setsockopt(socket.SOL_SOCKET, 25, str(iface + '\0').encode())

    def udp_recv(self, bufsize: int) -> bytes:
        packet, addr = self.sock.recvfrom(bufsize)
        if addr[0] == self.server_ip and addr[1] == self.server_port:
            return packet
        return None
            
    def proto_recv_next(self, bufsize: int) -> tuple[bytes, tuple[str, int]]:
        payload = self.udp_recv(bufsize)
        if payload is None:
            return None
        # 8 bytes == 4 bytes of header + 4 bytes of seq number
        if len(payload) <= 8:
            return None
        if payload[:PROTO_HDR_LENGTH] != PROTO_HDR:
            return None

        seq = int.from_bytes(payload[PROTO_HDR_LENGTH:PROTO_HDR_LENGTH + 4], byteorder='big')
        if seq <= self.proto_rx_seq:
            return None

        self.proto_rx_seq = seq
        return (payload[PROTO_HDR_LENGTH + 4:], (self.server_ip, self.server_port))
        
    def proto_send_next(self, payload: bytes) -> None:
        self.proto_tx_seq += 1
        udp_payload = PROTO_HDR + self.proto_tx_seq.to_bytes(4, byteorder='big') + payload
        self.sock.sendto(udp_payload, (self.server_ip, self.server_port))


class KazariTunnelServerIO(KazariIO):
    def __init__(self, listen_addr: str, udp_port: int):
        self.listen_addr = listen_addr
        self.port = udp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((listen_addr, udp_port))
        self.proto_rx_seq = 0
        self.proto_tx_seq = 0
        self.client_ip: None | str = None
        self.client_port: None | int = None

    def set_client_address(self, ip: str, port: int) -> None:
        self.client_ip = ip
        self.client_port = port
    
    def proto_recv_next(self, bufsize: int) -> tuple[bytes, tuple[str, int]]:
        payload, addr = self.sock.recvfrom(bufsize)
        if len(payload) <= 8:
            return None
        if payload[:PROTO_HDR_LENGTH] != PROTO_HDR:
            return None

        seq = int.from_bytes(payload[PROTO_HDR_LENGTH:PROTO_HDR_LENGTH + 4], byteorder='big')
        if seq <= self.proto_rx_seq:
            return None

        self.proto_rx_seq = seq
        return (payload[PROTO_HDR_LENGTH + 4:], addr)

    def proto_send_next(self, payload: bytes) -> None:
        self.proto_tx_seq += 1
        udp_payload = PROTO_HDR + self.proto_tx_seq.to_bytes(4, byteorder='big') + payload
        self.sock.sendto(udp_payload, (self.client_ip, self.client_port))


def handle_packet_arrival(packet: bytes, tun: TunTapDevice) -> None:
    if packet == b'HEARTBEAT':
        return
    


async def handle_peer_io(io: KazariIO, tun_ip: str) -> None:
    # Create TUN virtual device
    tun = TunTapDevice(name='kztun0')
    tun.addr = tun_ip
    tun.netmask = '255.255.255.0'
    tun.mtu = TUN_LINK_MTU
    tun.up()

    def on_recv():
        packet = None
        try:
            result = io.proto_recv_next(1024)
            if result is None:
                return
            packet = result[0]
        except socket.error as e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                return
            else:
                print(f'IO error: {err}')

        if packet == b'HEARTBEAT':
            print('recv: peer heartbeat')
        elif packet[:7] == b'PAYLOAD':
            payload = packet[7:]
            print(f'got payload {len(payload)} bytes')
            tun.write(payload)
            #print(payload)
        else:
            print(f'unrecognized packet: {packet}')
        # handle_packet_arrival(packet, tun)

    def on_tun_recv():
        packet = tun.read(TUN_TRANSPORT_SIZE)
        io.proto_send_next(b'PAYLOAD' + packet)
        print(f'sent payload {len(packet)} bytes')

    async def on_send_heartbeat():
        while True:
            io.proto_send_next(b'HEARTBEAT')
            await asyncio.sleep(1)

    io.sock.setblocking(False)
    loop.add_reader(io.sock.fileno(), on_recv)
    loop.add_reader(tun.fileno(), on_tun_recv)

    await on_send_heartbeat()
    

def server_main():
    io = KazariTunnelServerIO('0.0.0.0', 53)
    
    # Waiting for handshake
    print('handshake: waiting for handshake SYN')
    handshake_payload, client_addr = io.proto_recv_next_checked(256)
    print(f'handshake: request from {client_addr[0]}:{client_addr[1]}')
    handshake_syn, handshake_id = struct.unpack('3sI', handshake_payload)
    if handshake_syn.decode() != 'SYN':
        print('handshake: invalid request')
    print(f'handshake: got SYN with id={handshake_id}, sending reply ACK with id={handshake_id + 1}')
    io.set_client_address(client_addr[0], client_addr[1])
    io.proto_send_next(struct.pack('3sI', 'ACK'.encode(), handshake_id + 1))
    print(f'handshake: done')

    loop.run_until_complete(handle_peer_io(io, '10.1.1.1'))


def client_main():
    io = KazariTunnelClientIO(SERVER_IP, 53, CLIENT_IFACE)
    
    # Handshake stage
    handshake_id = random.randint(0x0000, 0xffff)
    io.proto_send_next(struct.pack('3sI', 'SYN'.encode(), handshake_id))
    print(f'handshake: sent SYN with id={handshake_id}, waiting for ACK response')
    handshake_ack, handshake_ack_id = struct.unpack('3sI', io.proto_recv_next_checked(256)[0])
    if handshake_ack.decode() != 'ACK':
        print('handshake: invalid response')
        return
    print(f'handshake: got reply ACK with id={handshake_ack_id}')
    if handshake_ack_id != handshake_id + 1:
        print('handshake: invalid id in response')
        return
    
    print('handshake: done')

    loop.run_until_complete(handle_peer_io(io, '10.1.1.2'))


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'server':
        server_main()
    elif mode == 'client':
        client_main()
    else:
        print('invalid mode')
