#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'order_system.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Couldn't import Django.") from exc

    # 检查是否是 runserver 命令并且没有指定端口
    is_runserver = 'runserver' in sys.argv
    is_port_specified = any(':' in arg or arg.isdigit() for arg in sys.argv[2:])

    if is_runserver and not is_port_specified:
        sys.argv.append('8080')

    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
