#!/usr/bin/env python3

import socket
import sys
import time
import argparse

# action can be reflect or drop 
action = "drop"
test = 0

def test_data(data, n_rcvd):
    n_read = len (data);
    for i in range(n_read):
        expected = (n_rcvd + i) & 0xff
        byte_got = ord (data[i])
        if (byte_got != expected):
            print(f"Difference at byte {n_rcvd + i}. Expected {expected} got {byte_got}")
    return n_read

def handle_connection(connection, client_address):
    print(f"Received connection from {repr(client_address)}")
    n_rcvd = 0
    try:
        while True:
            data = connection.recv(4096)
            if not data:
                break;
            if (test == 1):
                n_rcvd += test_data (data, n_rcvd)
            if (action != "drop"):
                connection.sendall(data)
    finally:
        connection.close()
def run_tcp_server(ip, port):
    print(f"Starting TCP server {repr(ip)}:{repr(port)}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_address = (ip, int(port))
    sock.bind(server_address)
    sock.listen(1)
    while True:
        connection, client_address = sock.accept()
        handle_connection (connection, client_address)
def run_udp_server(ip, port):
    print(f"Starting UDP server {repr(ip)}:{repr(port)}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_address = (ip, int(port))
    sock.bind(server_address)
    while True:
        if (action != "drop"):
            data, addr = sock.recvfrom(4096)
            #snd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto (data, addr)

def run_server(ip, port, proto):
    if (proto == "tcp"):
        run_tcp_server(ip, port)
    elif (proto == "udp"):
        run_udp_server(ip, port)

def prepare_data(power):
    buf = [i & 0xff for i in range(pow(2, power))]
    return bytearray(buf)

def run_tcp_client(ip, port):
    print(f"Starting TCP client {repr(ip)}:{repr(port)}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = (ip, int(port))
    sock.connect(server_address)

    data = prepare_data(16)
    n_rcvd = 0
    n_sent = len (data)
    try:
        sock.sendall(data)

        timeout = time.time() + 2
        while n_rcvd < n_sent and time.time() < timeout:
            tmp = sock.recv(1500)
            tmp = bytearray (tmp)
            n_read = len(tmp)
            for i in range(n_read):
                if (data[n_rcvd + i] != tmp[i]):
                    print(f"Difference at byte {n_rcvd + i}. Sent {data[n_rcvd + i]} got {tmp[i]}")
            n_rcvd += n_read

        if (n_rcvd < n_sent or n_rcvd > n_sent):
            print(f"Sent {n_sent} and got back {n_rcvd}")
        else:
            print("Got back what we've sent!!");

    finally:
        sock.close()
def run_udp_client(ip, port):
    print(f"Starting UDP client {repr(ip)}:{repr(port)}")
    n_packets = 100
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = (ip, int(port))
    data = prepare_data(10)
    try:
        for _ in range(n_packets):
            sock.sendto(data, server_address)
    finally:
        sock.close()
def run_client(ip, port, proto):
    if (proto == "tcp"):
        run_tcp_client(ip, port)
    elif (proto == "udp"):
        run_udp_client(ip, port)
def run(mode, ip, port, proto):
    if (mode == "server"):
        run_server (ip, port, proto)
    elif (mode == "client"):
        run_client (ip, port, proto)
    else:
        raise Exception("Unknown mode. Only client and server supported")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', action='store', dest='mode')
    parser.add_argument('-i', action='store', dest='ip')
    parser.add_argument('-p', action='store', dest='port')
    parser.add_argument('-proto', action='store', dest='proto')
    parser.add_argument('-a', action='store', dest='action')
    parser.add_argument('-t', action='store', dest='test')
    results = parser.parse_args()
    action = results.action
    test = results.test
    run(results.mode, results.ip, results.port, results.proto)
    #if (len(sys.argv)) < 4:
    #    raise Exception("Usage: ./dummy_app <mode> <ip> <port> [<action> <test>]")
    #if (len(sys.argv) == 6):
    #    action = sys.argv[4]
    #    test = int(sys.argv[5])
    #run (sys.argv[1], sys.argv[2], int(sys.argv[3]))
