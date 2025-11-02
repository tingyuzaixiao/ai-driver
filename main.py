import json
from pathlib import Path

import uvicorn

import server

def load_config_basic(file_path='config/config.json'):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            config_data = json.load(file)
        return config_data
    except FileNotFoundError:
        print(f"错误：配置文件 '{file_path}' 未找到。")
        return None
    except json.JSONDecodeError as e:
        print(f"错误：配置文件解析失败 - {e}")
        return None

def main():
    current_path = Path.cwd()
    config_path = current_path / "configs/config.json"
    config_dict = load_config_basic(config_path.as_posix())

    app = server.init(base_dir=current_path.as_posix(),
                      platform_url=config_dict["platform_url"],
                      config_file=config_dict["config_file"],
                      train_module_path=config_dict["train_module_path"],
                      train_script=config_dict["train_script"],
                      description=config_dict["description"],
                      port=config_dict["port"],
                      register_max_retries=config_dict["register_max_retries"])

    uvicorn.run(app, host="127.0.0.1", port=config_dict["port"])

if __name__ == "__main__":
    main()