# -*- coding: utf-8 -*-
"""
Перенос чатов и настроек из основной (Store) версии Claude Desktop в русскую копию.

Копирует:
- claude-code-sessions (файлы чатов local_*.json)
- local-agent-mode-sessions (настройки Cowork)
- ccd-session-secrets (ключи сессий)
- configLibrary (конфигурация Inference Gateway — БЕЗ ключей, ключи в ccd-session-secrets)

Запуск: python tools/migrate-chats.py
"""
import json, os, shutil, sys, subprocess, time

sys.stdout.reconfigure(encoding='utf-8')

SRC = os.path.join(os.environ['LOCALAPPDATA'], 'Claude-3p')
DST = os.path.expanduser(r'~\Claude-RU-Data')


def find_account_id(profile):
    """Определяет активный account id по config.json или папкам сессий."""
    cfg = os.path.join(profile, 'config.json')
    if os.path.exists(cfg):
        try:
            d = json.load(open(cfg, encoding='utf-8'))
            a = d.get('lastKnownAccountUuid')
            if a:
                return a
        except Exception:
            pass
    # fallback: папка с local-agent-mode-sessions
    lam = os.path.join(profile, 'local-agent-mode-sessions')
    if os.path.isdir(lam):
        subs = [x for x in os.listdir(lam) if os.path.isdir(os.path.join(lam, x))]
        if subs:
            return subs[0]
    return None


def main():
    if not os.path.isdir(SRC):
        print('Основная версия Claude не найдена:', SRC)
        sys.exit(1)
    os.makedirs(DST, exist_ok=True)

    src_acc = find_account_id(SRC)
    dst_acc = find_account_id(DST)
    print(f'Аккаунт основной версии: {src_acc}')
    print(f'Аккаунт русской копии:  {dst_acc}')
    if not dst_acc:
        dst_acc = src_acc
        print('Аккаунт копии неизвестен — кладём под аккаунт основной версии.')

    # закрываем копию, если запущена
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-Process Claude -ErrorAction SilentlyContinue | Where-Object {$_.Path -like '*Claude-RU*'} | Stop-Process -Force"],
                   capture_output=True)
    time.sleep(2)

    # 1. файлы чатов
    src_chats = os.path.join(SRC, 'claude-code-sessions', src_acc,
                             '00000000-0000-4000-8000-000000000001')
    dst_chats = os.path.join(DST, 'claude-code-sessions', dst_acc,
                             '00000000-0000-4000-8000-000000000001')
    if os.path.isdir(src_chats):
        os.makedirs(dst_chats, exist_ok=True)
        for f in os.listdir(src_chats):
            if f.startswith('local_') and f.endswith('.json') or f == 'archived-sessions.idx':
                shutil.copy2(os.path.join(src_chats, f), os.path.join(dst_chats, f))
        n = len([f for f in os.listdir(dst_chats) if f.startswith('local_')])
        print(f'Чаты: {n} файлов перенесено')

    # 2. настройки Cowork
    src_lam = os.path.join(SRC, 'local-agent-mode-sessions', src_acc)
    dst_lam = os.path.join(DST, 'local-agent-mode-sessions', dst_acc)
    if os.path.isdir(src_lam):
        os.makedirs(dst_lam, exist_ok=True)
        for sub in os.listdir(src_lam):
            s = os.path.join(src_lam, sub)
            if os.path.isdir(s):
                shutil.copytree(s, os.path.join(dst_lam, sub), dirs_exist_ok=True)
            else:
                shutil.copy2(s, os.path.join(dst_lam, sub))
        print('Настройки Cowork перенесены')

    # 3. секреты сессий и конфигурация
    for item in ['ccd-session-secrets', 'configLibrary', 'ccd-ids.json',
                 'ccd-session-presets.json', 'side-session-notes']:
        s = os.path.join(SRC, item)
        if os.path.exists(s):
            d = os.path.join(DST, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
            print(f'перенесено: {item}')

    print()
    print('Готово! Перезапустите русскую копию и проверьте список чатов.')


if __name__ == '__main__':
    main()
