from json import dumps
import logging


class ServerClientException(Exception):
    pass


def pack_command(cmd, data):
    res = {
        'cmd': cmd,
        'data': data
    }

    response = dumps(res, default=str)
    response += '\n'

    return response.encode('utf-8')


def send(client, cmd, data):
    response = pack_command(cmd, data)

    logging.debug('send: %s', response)

    client.send(response)


def client_on_receive_callback(client, address, message, state, api):
    cmd = message['cmd']
    data = message['data']

    logging.debug('client: new message received: %s', message)

    if cmd == 'nick':
        logging.debug('client: "nick" cmd processed')

        state['nicknames'].append(data['nickname'])

        if state['is_master'] is False:
            send(client, 'reconnect', state['reserve_server_hosts'])
            return

        if data['reconnect'] is False:
            send(client, 'connect', 'Connected to server!')
            api['client_server'].send_all(
                'msg_join', f"{data['nickname']} joined!")

    elif (cmd == 'ok_message_join'):
        logging.debug('client: "ok_message_join" cmd processed')
        send(client, 'connect', 'Connected to server!')

    elif (cmd == 'ok_connect'):
        logging.debug('client: nick "ok_connect" cmd processed')
        send(client, 'history', state['history'])

    elif (cmd == 'ok_history'):
        logging.debug('client: "ok_history" cmd processed')
        send(client, 'servers', state['reserve_server_hosts'])

    elif cmd == 'msg':
        logging.debug('client: "msg" cmd processed: %s', data)
        if data:
            message_str = data['nickname'] + ': ' + data['msg']
            state['history'].append(message_str)

            api['client_server'].send_all('msg', message_str)
            api['sync_server'].send_all('history', state['history'])
            # sync_server.send_all('nicknames', state['nicknames'])
    else:
        raise (ServerClientException(f'client: unknown command: {cmd}'))


def client_on_connected_callback(client, address, state, api):
    logging.debug('client: new client connected')
    state['clients'].append(client)
    return


def client_on_disconnected_callback(client, address, state, api):
    logging.debug('client: client disconnected: %s, %s', client, address)

    clients = state['clients']

    if client in clients:
        index = clients.index(client)
        clients.remove(client)
        client.close()

        if index <= len(state['nicknames']):
            nickname = state['nicknames'][index]

            logging.debug(f'client: {nickname} left the chat!')

            api['client_server'].send_all("msg", f'{nickname} left the chat!')

            state['nicknames'].remove(nickname)
