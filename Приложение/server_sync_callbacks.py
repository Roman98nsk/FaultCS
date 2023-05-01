from json import loads, dumps
import logging
from pprint import pformat
from TCPThreadedServer import SocketWithData
import socket
from threading import Thread


class ServerSyncException(Exception):
    pass


def get_server_id(server):
    return server['id']

# Сортируем список серверов в порядке возрастания по полю id
def sort_servers(servers):
    servers.sort(key=get_server_id,)

# Определяет является ли сервер главный.
# Главный тот, кто первый в списке, а тот кто первый id наименьший
def is_master_server(server_id, servers):
    if len(servers) > 0:
        first_server = servers[0]
        return first_server['id'] == server_id
    return False

# Если сервера нет в списке серверов, то добавляем
def add_reserve_server(servers, new_server):
    exists = False

    for server in servers:
        if server['id'] == new_server['id']:
            exists = True
            break

    if exists is False:
        logging.debug('sync: add new server %s', new_server)
        servers.append(new_server)

# Актуализируем список с серверами
def refresh_state(state):
    # Сортируем список с серверами
    sort_servers(state['reserve_server_hosts'])

    state['is_master'] = is_master_server(
        state['id'], state['reserve_server_hosts'])
    # print("REFRESH!!!! ", state['id'], state['reserve_server_hosts'])

    logging.debug('sync: refresh state')
    logging.debug(pformat(state))

# Упаковываем команду в json
def pack_command(cmd, data):
    res = {
        'cmd': cmd,
        'data': data
    }

    response = dumps(res, default=str)
    response += '\n'

    return response.encode('utf-8')

# Общая функция отправки сообщений
def send(client, cmd, data):
    response = pack_command(cmd, data)

    logging.debug('sync: send: %s', response)

    client.send(response)

# Главный сервер получает сообщения от резервного
def server_on_receive_callback(client, address, message, state, api):
    cmd = message['cmd']
    data = message['data']

    logging.debug('sync: new message received: %s, %s', message, data)

    logging.debug('state %s', state)

    if cmd == 'hello':
        send(client, 'history', state['history'])

        client.set_data(data)

        add_reserve_server(state['reserve_server_hosts'], data)

        refresh_state(state)

        api['sync_server'].send_all('servers', {
            'servers': state['reserve_server_hosts'],
            'is_master': state['is_master']
        })
        api['client_server'].send_all('servers', state['reserve_server_hosts'])
    else:
        raise (ServerSyncException(f'sync: unknown command: {cmd}'))



def server_on_connected_callback(reserve_server, address, state, api):
    logging.debug('sync: server connected: %s, %s', reserve_server, address)
    state['reserve_servers'].append(reserve_server)


def server_on_disconnected_callback(reserve_server, address, state, api):
    logging.debug('sync: server disconnected: %s, %s', reserve_server, address)

    data = reserve_server.get_data()

    reserve_servers = state['reserve_servers']
    reserve_server_hosts = state['reserve_server_hosts']

    if reserve_server in reserve_servers:
        logging.debug('sync: remove server %s', reserve_server)
        reserve_servers.remove(reserve_server)

    index = None

    for i, reserve_server_host in enumerate(reserve_server_hosts):
        if reserve_server_host['id'] == data['id']:
            index = i
            break

    if index is not None:
        logging.debug('sync: remove reserve_server_host by index %s', index)
        del reserve_server_hosts[index]

    reserve_server.close()

    refresh_state(state)

    api['client_server'].send_all('servers', state['reserve_server_hosts'])
    return

def say_hello(sync_client, state):
    hello_data = {
        'id': state['id'],
        'host': state['host'],
        'port': state['port'],
        'sync_port': state['sync_port'],
    }

    send(sync_client, 'hello', hello_data)

# Подключение серверов к главному
def connect_to_master_server(state):
    # SocketWithData
    sync_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sync_client.connect((state['master_host'], state['master_port']))
    state['master_server_client'] = sync_client
    # у каждого сервера свой state
    say_hello(sync_client, state)

    sync_thread = Thread(target=server_history_sync,
                         args=[state])
    sync_thread.start()

    logging.debug('sync started')

# Переподключение к новому главному серверу
def reconnect_to_master_server(state):
    logging.debug('sync: reconnecting to master server')

    sync_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    master_server = state['reserve_server_hosts'][0]

    sync_client.connect((master_server['host'], master_server['sync_port']))

    state['master_server_client'] = sync_client

    say_hello(sync_client, state)

# Главный сервер отсылает актуальную историю резервным
# Синхронизация истории
def server_history_sync(state):
    size = 1024*1024
    while True:
        try:
            sync_client = state['master_server_client']
            # Резервный получает сообщение от главного
            d = sync_client.recv(size)
            # Если главный сервер накрылся закрываем с ним соединение
            if d == b'':
                sync_client.close()
                # Удаляем бывший главноый сервер из списка серверов
                state['reserve_server_hosts'].pop(0)
                # print("state['reserve_server_hosts']", state['reserve_server_hosts'])
                # Актуализируем данные в списке серверов
                refresh_state(state)

                if state['is_master'] is True:
                    logging.debug(
                        'sync: i am new master server, stop reconnect')
                    state['master_server_client'] = None
                    break

                reconnect_to_master_server(state)
                continue

            # Если с главным сервером все хорошо отсылаем
            # резервным актуальную историю
            if d:
                messages = d.split(b'\0')

                for message_raw in messages:
                    if message_raw:
                        message_raw = message_raw.decode('utf-8')

                        try:
                            message = loads(message_raw)
                            cmd = message['cmd']
                            data = message['data']
                        except Exception as error:
                            logging.error(
                                'SYNC_CLIENT Json Failed: %s, %s', message, error)
                            # sync_client.close()
                            break

                        logging.debug('sync: message: %s ', message)

                        if cmd == 'history':
                            state['history'] = data
                        elif cmd == 'servers':
                            state['reserve_server_hosts'] = data['servers']
                            refresh_state(state)

                            if data['is_master'] is False:
                                sync_client.close()
                                reconnect_to_master_server(state)

                        else:
                            logging.error("unknown cmd %s", cmd)

                    else:
                        raise ValueError('SYNC_CLIENT Disconnected')
        except Exception as error:
            logging.exception(error, exc_info=True)
            sync_client.close()
