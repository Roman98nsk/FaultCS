
from datetime import datetime
from json import loads, dumps
import socket
import threading
import os
import logging

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

client_server = None

state = {
    'nickname': None,
    'history': [],
    'servers': [],
}

class NoServersError(Exception):
    pass


class ServerClient():
    _client = None

    def get_client(self):
        return self._client

    def set_client(self, client):
        logging.debug('set new socket client: %s', client)
        self._client = client


server_client = ServerClient()
# server_client.set_client()


def send(cmd, data=None):
    res = {
        'cmd': cmd,
        'data': data
    }

    response = dumps(res, default=str)
    response += '\n'

    logging.debug('send %s', response)

    server_client.get_client().send(response.encode('utf-8'))


def reconnect(real_reaconnect=True):
    logging.debug('starting reconnect: %s', state['servers'])

    if len(state['servers']) == 0:
        logging.debug('reconnect: server list empty')
        raise NoServersError('empty servers list')

    connected = False

    bad_servers = []

    logging.debug('reconnect: close current server connection')
    server_client.get_client().close()

    for server in state['servers']:
        host = server['host']
        port = server['port']

        logging.debug('reconnect: try connect to server %s:%s', host, port)

        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((host, port))
            server_client.set_client(client)
            connected = True
            logging.debug('connected to %s:%s', host, port)
            break
        except Exception as err:
            logging.debug('reconnect: connection failed: %s', err)
            bad_servers.append(server)

    if len(bad_servers) > 0:
        logging.debug('reconnect: removing bad servers: %s', bad_servers)

        for bad_server in bad_servers:
            index = state['servers'].index(bad_server)
            state['servers'].pop(index)

    logging.debug('reconnect: actual server list: %s', state['servers'])

    if connected == False:
        logging.debug('reconnect failed')
        raise NoServersError('cannot connect to any server')

    send(
        'nick', {"nickname": state['nickname'], "reconnect": real_reaconnect})


def receive():
    size = 1024*1024

    while True:

        # Receive Message From Server
        # If 'NICK' Send Nickname
        d = server_client.get_client().recv(size)

        logging.debug('receive messages from server >>>%s<<<', d)

        if d == b'':
            reconnect()
            continue

        messages = d.split(b'\n')

        for message_raw in messages:
            logging.debug('receive message (raw): %s', message_raw)

            if message_raw:
                message_raw = message_raw.decode('utf-8')

                command = loads(message_raw)

                logging.debug('receive message (parsed): %s', command)

                cmd = command['cmd']
                data = command['data']

                if cmd == 'msg_join':
                    logging.debug('"msg_join" cmd processed')
                    print(data)

                elif (cmd == 'connect'):
                    logging.debug('"connect" cmd processed')
                    send('ok_connect')

                elif cmd == 'history':
                    logging.debug('"history" cmd processed: %s', data)
                    for item in data:
                        print(item)
                    send('ok_history')

                elif cmd == 'servers':
                    logging.debug('"servers" cmd processed: %s', data)
                    state['servers'] = data

                elif cmd == 'msg':
                    logging.debug('"msg" cmd processed: %s', data)
                    print(data)

                elif cmd == 'reconnect':
                    logging.debug('"reconnect" cmd processed: %s', data)
                    state['servers'] = data
                    reconnect(False)

                else:
                    logging.error(f'unknown cmd %s %s', cmd, data)


def write():
    print('connected')
    while True:
        try:
            send('msg', {
                'nickname': state['nickname'],
                'msg': input(),
            })
        except Exception as err:
            logging.error(err)
            break


def thread_except_hook(args):
    logging.fatal(args)
    logging.fatal('exit = 1')
    os._exit(1)


if __name__ == "__main__":
    if 'HOST' not in os.environ:
        print(datetime.now(), 'no env.HOST')
        exit(1)

    if 'PORT' not in os.environ:
        print(datetime.now(), 'no env.PORT')
        exit(1)

    # Choosing Nickname
    if 'NICKNAME' in os.environ:
        state['nickname'] = os.environ['NICKNAME']
    else:
        state['nickname'] = input("Choose your nickname: ")

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(
        (os.environ['HOST'], int(os.environ['PORT'])))

    server_client.set_client(client)

    send('nick', {"nickname": state['nickname'], "reconnect": False})

    threading.excepthook = thread_except_hook

    receive_thread = threading.Thread(target=receive)
    receive_thread.start()

    write_thread = threading.Thread(target=write)
    write_thread.start()
