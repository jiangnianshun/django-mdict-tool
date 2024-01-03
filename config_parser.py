import configparser
import os
import psutil

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
user_config_path = os.path.join(ROOT_DIR, 'config.ini')

default_config = {
    'GENERAL': {
        'PROTOCOL': 'http',
        'HOST': '127.0.0.1',
        'PORT': '18000',
        'PATH': 'mdict/simple2'
    }
}

config = configparser.ConfigParser(interpolation=None)


def create_config():
    global config
    try:
        with open(user_config_path, 'w', encoding='utf-8') as f:
            config.write(f)
        os.chmod(user_config_path, 0o777)
    except PermissionError as e:
        print(e)


def get_config():
    global config, config_permission

    if os.path.exists(user_config_path):
        config.read(user_config_path, encoding='utf-8')
        if 'GENERAL' in config.keys():
            for k, v in default_config['GENERAL'].items():
                if k not in config['GENERAL'].keys():
                    config['GENERAL'][k] = str(v)
        else:
            config['GENERAL'] = default_config['GENERAL']
            create_config()
    else:
        config['GENERAL'] = default_config['GENERAL']
        create_config()
    return config


def set_config(sec, save_config):
    global config, config_permission
    con = get_config()
    for con_name, con_value in save_config.items():
        con[sec][con_name] = str(con_value)
    config = con
    create_config()


if not os.path.exists(user_config_path):
    config['GENERAL'] = default_config['GENERAL']
    create_config()

config.read(user_config_path, encoding='utf-8')
