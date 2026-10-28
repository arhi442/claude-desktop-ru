# -*- coding: utf-8 -*-
r"""
Claude Desktop RU — установщик-обёртка.
Запускается без Python: EXE содержит build.py и переводы.
Использует системный Python, если он есть; иначе распаковывает перевод
и предлагает инструкцию.

Простой поток:
1. Найти Claude Desktop (Store).
2. Выполнить сборку (как build.py).
"""
import os, sys, json, io, glob, time  # glob/time нужны build.py при работе из EXE

sys.stdout.reconfigure(encoding='utf-8')


def main():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    build_py = os.path.join(base, 'build.py')
    ru_json = os.path.join(base, 'translations', 'ru.json')

    if not os.path.exists(build_py):
        # PyInstaller one-file: build.py идёт бандлом
        print('ОШИБКА: build.py не найден рядом с EXE.')
        input('Нажмите Enter для выхода...')
        sys.exit(1)

    print('=== Claude Desktop RU — установщик русского языка ===')
    print()

    # запускаем build.py из текущего процесса
    sys.path.insert(0, base)
    import importlib.util
    spec = importlib.util.spec_from_file_location('cdru_build', build_py)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        mod.main()
    except Exception as e:
        print()
        print(f'ОШИБКА: {e}')
        print('Проверьте, что Claude Desktop установлен из Microsoft Store')
        print('и запущен ли этот установщик от обычного пользователя (не требуется админ).')
        input('Нажмите Enter для выхода...')
        sys.exit(1)

    print()
    input('Готово! Нажмите Enter для выхода...')


if __name__ == '__main__':
    main()
