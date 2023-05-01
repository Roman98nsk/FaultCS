

```bash
#main server 
HOST=127.0.0.1 PORT=8000 SYNC_PORT=7000 python server.py
# slave server 
HOST=127.0.0.1 PORT=8001 SYNC_PORT=7001 MAIN_HOST=127.0.0.1 MAIN_PORT=7000  python server.py

# client
HOST=127.0.0.1 PORT=7000 python client.py
```



```
python -m venv
```