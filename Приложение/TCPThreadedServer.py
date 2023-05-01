from datetime import datetime
from json import loads, dumps
import socket
from threading import Thread
import logging


class SocketWithData(socket.socket):
    _data = None

    def set_data(self, data):
        self._data = data

    def get_data(self):
        return self._data

    def accept(self): #  Подтверждение соединения с клиентом
        fd, addr = self._accept()
        sock = SocketWithData(self.family, self.type,
                              self.proto, fileno=fd)
        if socket.getdefaulttimeout() is None and self.gettimeout():
            sock.setblocking(True)
        return sock, addr


class TCPThreadedServer(Thread):
    def __init__(
            self,
            host,
            port,
            timeout=60,
            decode_json=True,
            on_connected_callback=None,
            on_receive_callback=None,
            on_disconnected_callback=None,
            debug=False,
            debug_data=False,
            state={},
            api={},
    ):

        self.host = host
        self.port = port
        self.timeout = timeout
        self.decode_json = decode_json
        self.on_connected_callback = on_connected_callback
        self.on_receive_callback = on_receive_callback
        self.on_disconnected_callback = on_disconnected_callback
        self.debug = debug
        self.debug_data = debug_data
        self.clients = []
        self.state = state
        self.api = api
        Thread.__init__(self)

    # run by the Thread object
    def run(self):
        if self.debug:
            logging.debug('SERVER Starting...')

        self.listen()

    def listen(self):
        # Создаем экземпляр сокета
        self.sock = SocketWithData(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Привязка сокета к хосту и порту
        self.sock.bind((self.host, self.port))
        if self.debug:
            logging.debug('SERVER Socket Bound %s %s', self.host, self.port)

        # Начинаем слушать клиента
        self.sock.listen(5)
        if self.debug:
            logging.debug('SERVER Listening...')

        while True:
            # Получаем объект клиента и адрес
            client, address = self.sock.accept()

            # Добавляем клиента в список
            self.clients.append(client)

            # Установка timeout для блокировки операций сокета
            client.settimeout(self.timeout)

            if self.debug:
                logging.debug('CLIENT Connected: %s', client)

            if self.on_connected_callback:
                self.on_connected_callback(
                    client, address, self.state, self.api)

            # Запуск поток для прослушивания клиента
            Thread(
                target=self.listen_to_client,
                args=(client, address, self.decode_json,
                      self.on_receive_callback, self.on_disconnected_callback)
            ).start()

    def listen_to_client(self, client, address, decode_json, on_receive_callback, on_disconnected_callback):
        # set a buffer size ( could be 2048 or 4096 / power of 2 )
        size = 1024*1024
        while True:
            try:
                d = client.recv(size)
                if d:
                    #messages = d.split(b'\n\r')
                    messages = d.split(b'\0')

                    for data in messages:
                        if data:
                            data = data.decode('utf-8')

                            if self.debug:
                                logging.debug(
                                    'CLIENT Data Received: %s', address)

                            if decode_json:
                                try:
                                    data = loads(data)
                                except Exception as e:
                                    logging.error(
                                        'CLIENT Json Failed: %s %s %s %s', data, '\n', e, '\n')
                                    client.close()
                                    break

                            if self.debug_data:
                                logging.debug('data: %s', data)

                            if on_receive_callback:
                                try:
                                    on_receive_callback(
                                        client, address, data, self.state, self.api)
                                except Exception as err:
                                    logging.error(
                                        'CLIENT Receive Callback Failed: %s', err)
                                    raise err

                else:
                    raise ValueError('CLIENT Disconnected')

            except Exception as err:
                logging.exception(err, exc_info=True)

                client.close()
                client_index = self.clients.index(client)

                self.clients.pop(client_index)

                if on_disconnected_callback:
                    try:
                        on_disconnected_callback(
                            client, address, self.state, self.api)
                    except Exception as err:
                        logging.debug('on_close_callback failed: %s', err)
                        logging.exception(err, exc_info=True)
                return False

    def send_all(self, cmd, data):
        for client in self.clients:
            # send each client a message
            res = {
                'cmd': cmd,
                'data': data
            }
            response = dumps(res, default=str)
            # add new line chr for TD
            response += '\n'
            client.send(response.encode('utf-8'))
