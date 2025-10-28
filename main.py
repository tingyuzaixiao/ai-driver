import uvicorn

import server

if __name__ == "__main__":
    log_path = "/Users/zhangjiang/test"
    port = 8001
    app = server.init(log_path=log_path, port=port)

    uvicorn.run(app, host="127.0.0.1", port=port)