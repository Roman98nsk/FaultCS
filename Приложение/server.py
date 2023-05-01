from datetime import datetime
import os
import logging
import time
import math
import threading


from TCPThreadedServer import TCPThreadedServer
from server_client_callbacks import client_on_connected_callback, client_on_disconnected_callback, client_on_receive_callback
from server_sync_callbacks import server_on_connected_callback, \
    server_on_disconnected_callback, server_on_receive_callback, \
    is_master_server, connect_to_master_server

server_id = math.ceil(time.time_ns() / 1000)

logging.basicConfig(
    format=f'%(asctime)s - {server_id} - %(levelname)s - %(message)s',
    level=logging.DEBUG
)


def main():
    if 'HOST' not in os.environ:
        print(datetime.now(), 'no env.HOST')
        exit(1)

    if 'PORT' not in os.environ:
        print(datetime.now(), 'no env.PORT')
        exit(1)

    if 'SYNC_PORT' not in os.environ:
        print(datetime.now(), 'no env.SYNC_PORT')
        exit(1)

    api = {
        "client_server": None,
        "sync_server": None,
    }

    state = {
        'id': server_id,
        'is_master': False,
        'host': os.environ['HOST'],
        'port': int(os.environ['PORT']),
        'sync_port': int(os.environ['SYNC_PORT']),
        'master_host': None,
        'master_port': None,
        # Соединение резервного с главным
        'master_server_client': None,
        'history': [],
        'nicknames': [],
        'clients': [],
        # хранятся подключения резервных серверов к главному
        'reserve_servers': [],
        'reserve_server_hosts': [],
    }

    state['reserve_server_hosts'] = [
        {
            'id': server_id,
            'host': state['host'],
            'port': state['port'],
            'sync_port': state['sync_port'],
        }
    ]

    state['is_master'] = is_master_server(
        state['id'], state['reserve_server_hosts'])

    logging.debug('starting with state %s', state)

    api['client_server'] = TCPThreadedServer(
        state['host'],
        state['port'],
        timeout=86400,
        decode_json=True,
        on_connected_callback=client_on_connected_callback,
        on_receive_callback=client_on_receive_callback,
        on_disconnected_callback=client_on_disconnected_callback,
        debug=True,
        debug_data=True,
        state=state,
        api=api
    )

    api['sync_server'] = TCPThreadedServer(
        state['host'],
        state['sync_port'],
        timeout=86400,
        decode_json=True,
        on_connected_callback=server_on_connected_callback,
        on_receive_callback=server_on_receive_callback,
        on_disconnected_callback=server_on_disconnected_callback,
        debug=True,
        debug_data=True,
        state=state,
        api=api
    )

    def thread_except_hook(args):
        logging.fatal(args)
        logging.fatal('exit = 1')
        os._exit(1)

    threading.excepthook = thread_except_hook

    api['client_server'].start()
    api['sync_server'].start()

    logging.debug('started')

    if 'MAIN_HOST' in os.environ and 'MAIN_PORT' in os.environ:
        state['master_host'] = os.environ['MAIN_HOST']
        state['master_port'] = int(os.environ['MAIN_PORT'])

        connect_to_master_server(state)


if __name__ == "__main__":
    main()
