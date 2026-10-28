# -*- coding: utf-8 -*-
r"""
Сборщик русского языкового пакета Claude Desktop (Windows).

Полный пайплайн:
1. Находит установленную версию Claude Desktop (MSIX/WindowsApps).
2. Копирует её в отдельную папку (не трогает оригинал!).
3. Патчит app.asar: карта локалей main-процесса + разрешение CLAUDE_USER_DATA_DIR
   (параллельный запуск рядом со Store-версией).
4. Патчит ion-dist.asar: русские каталоги i18n/ru.json + ru в списках языков рендерера.
5. Пересчитывает все integrity-хэши (SHA256 + блочные) и обновляет хэши
   в exe-манифесте целостности.
6. Создаёт лаунчер (vbs) с отдельной папкой данных.

Запуск:  python build.py
Результат: C:\Users\<user>\Claude-RU\ + лаунчер

Требования: Python 3.10+ (только stdlib), Claude Desktop 4.29+ установлен из Store.
"""
import json, hashlib, struct, os, re, sys, shutil, subprocess, glob

sys.stdout.reconfigure(encoding='utf-8')

# ============ конфигурация ============
INSTALL_DIR = os.path.expanduser(r'~\Claude-RU')           # куда ставить копию
DATA_DIR = os.path.expanduser(r'~\Claude-RU-Data')          # папка данных копии
BS = 4194304                                                 # размер блока integrity

LOCALES_ARRAY = b'"en-US","de-DE","fr-FR","ko-KR","ja-JP","es-419","es-ES","it-IT","hi-IN","pt-BR","id-ID"'
LOCALES_ARRAY_RU = LOCALES_ARRAY + b',"ru"'

# ============ утилиты asar ============

def read_asar(path):
    """Читает asar: возвращает (bytes, header, data_start)."""
    data = open(path, 'rb').read()
    i = data.find(b'{"files"')
    if i < 0:
        raise RuntimeError('не найден заголовок asar в ' + path)
    dec = json.JSONDecoder()
    header, jend = dec.raw_decode(data[i:].decode('utf-8', errors='replace'))
    pad = (4 - ((i + jend) % 4)) % 4
    data_start = i + jend + pad
    return data, header, data_start


def make_integrity(blob, bs=BS):
    """integrity-запись с полным и блочными SHA256 (ВАЖНО: блоков ceil(size/bs)!)."""
    blocks = [hashlib.sha256(blob[k:k+bs]).hexdigest() for k in range(0, len(blob), bs)]
    return {'algorithm': 'SHA256', 'hash': hashlib.sha256(blob).hexdigest(),
            'blockSize': bs, 'blocks': blocks}


def pack_asar(header, blobs_in_order):
    """Собирает asar из header и списка blob'ов. Возвращает bytes."""
    hdr_json = json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    jl = len(hdr_json)
    nds = (16 + jl + 3) & ~3
    pad_n = nds - 16 - jl
    hdr = struct.pack('<IIII', 4, nds - 8, nds - 12, jl) + hdr_json + b'\x00' * pad_n
    return hdr + b''.join(blobs_in_order)


def update_exe_hashes(exe_path, hashes):
    """Обновляет integrity-манифест в exe (JSON в конце файла, хэши SHA256 hex)."""
    exe = open(exe_path, 'rb').read()
    for old_hex, new_hex in hashes:
        old = ('"value":"' + old_hex + '"').encode()
        new = ('"value":"' + new_hex + '"').encode()
        assert len(old) == len(new), 'длина хэшей должна совпадать'
        assert exe.count(old) == 1, f'хэш {old_hex[:16]} не найден в exe'
        exe = exe.replace(old, new)
    open(exe_path, 'wb').write(exe)


def find_claude():
    out = subprocess.check_output(
        ['powershell', '-NoProfile', '-Command', '(Get-AppxPackage -Name Claude).InstallLocation'],
        text=True).strip()
    if not out or not os.path.isdir(out):
        raise RuntimeError('Claude Desktop не найден. Установите его из Microsoft Store.')
    return out


# ============ патч app.asar ============

def build_app_asar(src_path, dst_path):
    data, header, ds = read_asar(src_path)
    build = header['files']['.vite']['files']['build']['files']

    pre_info = build['index.pre.js']
    pre = data[ds+int(pre_info['offset']) : ds+int(pre_info['offset'])+int(pre_info['size'])]
    # разрешить CLAUDE_USER_DATA_DIR (параллельный запуск), равная длина
    old1 = b'delete e.CLAUDE_USER_DATA_DIR'
    new1 = b'void   e.CLAUDE_USER_DATA_DIR'
    if pre.count(old1) != 1:
        raise RuntimeError('код main изменился: не найден delete CLAUDE_USER_DATA_DIR')
    pre_new = pre.replace(old1, new1)

    # карта локалей main-процесса (имя fwt/hxt может меняться — ищем по содержимому)
    m = re.search(rb'\w+\{en:"en-US",de:"de-DE",fr:"fr-FR",ko:"ko-KR",ja:"ja-JP","es-419":"es-419",es:"es-ES",it:"it-IT",hi:"hi-IN",pt:"pt-BR",id:"id-ID"\}', data)
    if not m:
        raise RuntimeError('карта локалей main не найдена')
    main_old = m.group(0)
    main_new = main_old[:-1] + b',ru:"ru"}'

    # собираем по-файлово с пересчётом смещений и integrity (с дедупликацией по offset)
    uniq = {}
    def collect(d, path):
        for name, info in d.items():
            if 'files' in info:
                collect(info['files'], path + name + '/')
            elif info.get('offset') is not None:
                o = int(info['offset'])
                if o not in uniq:
                    uniq[o] = (path + name, info)
    collect(header['files'], '')
    patches = {'.vite/build/index.pre.js': pre_new}
    blobs, plan, no = [], {}, 0
    for o in sorted(uniq.keys()):
        name, info = uniq[o]
        blob = patches.get(name) or data[ds+o : ds+o+int(info['size'])]
        # главный бандл: патч карты локалей
        if name not in patches and b'en:"en-US"' in blob[:10000000] and main_old in blob and name.endswith('.js') and int(info['size']) > 5000000:
            blob = blob.replace(main_old, main_new)
            patches[name] = blob
        plan[o] = (no, blob)
        blobs.append(blob)
        no += len(blob)

    def update(d, path=''):
        for name, info in d.items():
            if 'files' in info:
                update(info['files'], path + name + '/')
            elif info.get('offset') is not None:
                nno, blob = plan[int(info['offset'])]
                info['offset'] = str(nno)
                if path + name in patches:
                    info['size'] = len(blob)
                    info['integrity'] = make_integrity(blob)
    update(header['files'])

    out = pack_asar(header, blobs)
    open(dst_path, 'wb').write(out)
    print(f'  app.asar: {len(out)} байт (было {len(data)})')
    return hashlib.sha256(out[16:16+jl]).hexdigest() if False else None  # hash посчитает вызывающий


# ============ патч ion-dist.asar ============

def build_ion_dist(src_path, dst_path, ru_main, ru_dyn, app_hash):
    data, header, ds = read_asar(src_path)

    def get_blob(path):
        parts = path.split('/')
        d = header['files']
        for p in parts[:-1]:
            d = d[p]['files']
        info = d[parts[-1]]
        return data[ds+int(info['offset']) : ds+int(info['offset'])+int(info['size'])]

    # JS-патчи (имена бандлов ищем по содержимому)
    patches = {}
    # 1) списки локалей рендерера
    for o_blob in None,:
        pass
    uniq = {}
    def collect(d, path):
        for name, info in d.items():
            if 'files' in info:
                collect(info['files'], path + name + '/')
            elif info.get('offset') is not None:
                oo = int(info['offset'])
                if oo not in uniq:
                    uniq[oo] = (path + name, info)
    collect(header['files'], '')

    patched_names = {}
    for o in sorted(uniq.keys()):
        name, info = uniq[o]
        blob = data[ds+o : ds+o+int(info['size'])]
        if name.endswith('.js') and int(info['size']) > 300000 and blob.count(LOCALES_ARRAY) >= 2:
            patches[name] = blob.replace(LOCALES_ARRAY, LOCALES_ARRAY_RU)
            patched_names['locales'] = name
        # пикер языков
        if blob.count(b'"id-ID":{name:"Indonesian (Indonesia)",localName:"Indonesia (Indonesia)"}}') == 1 and name.endswith('.js'):
            pk_old = b'"id-ID":{name:"Indonesian (Indonesia)",localName:"Indonesia (Indonesia)"}}'
            patches[name] = patches.get(name, blob).replace(
                pk_old, pk_old[:-1] + b',"ru":{name:"Russian",localName:"' + 'русский'.encode() + b'"}}')
        # KYC language
        if blob.count(b'case"id-ID":return["language","id"];default:return t}') == 1:
            patches[name] = patches.get(name, blob).replace(
                b'case"id-ID":return["language","id"];default:return t}',
                b'case"id-ID":return["language","id"];case"ru":return["language","ru"];default:return t}')
        # cronstrue/dayjs локали
        if blob.count(b'"hi-IN":"en","pt-BR":"pt_BR","id-ID":"id"}') == 1:
            patches[name] = patches.get(name, blob).replace(
                b'"hi-IN":"en","pt-BR":"pt_BR","id-ID":"id"}',
                b'"hi-IN":"en","pt-BR":"pt_BR","id-ID":"id","ru":"ru"}')

    # пересборка
    blobs, plan, no = [], {}, 0
    for o in sorted(uniq.keys()):
        name, info = uniq[o]
        blob = patches.get(name) or data[ds+o : ds+o+int(info['size'])]
        plan[o] = (no, blob)
        blobs.append(blob)
        no += len(blob)
    nf = {}
    for path, blob in [('i18n/ru.json', ru_main), ('i18n/dynamic/ru.json', ru_dyn)]:
        nf[path] = no
        blobs.append(blob)
        no += len(blob)

    def update(d, path=''):
        for name, info in d.items():
            if 'files' in info:
                update(info['files'], path + name + '/')
            elif info.get('offset') is not None:
                nno, blob = plan[int(info['offset'])]
                info['offset'] = str(nno)
                if path + name in patches:
                    info['size'] = len(blob)
                    info['integrity'] = make_integrity(blob)
    update(header['files'])

    header['files']['i18n']['files']['ru.json'] = {
        'size': len(ru_main), 'offset': str(nf['i18n/ru.json']), 'integrity': make_integrity(ru_main)}
    header['files']['i18n']['files']['dynamic']['files']['ru.json'] = {
        'size': len(ru_dyn), 'offset': str(nf['i18n/dynamic/ru.json']), 'integrity': make_integrity(ru_dyn)}

    out = pack_asar(header, blobs)
    open(dst_path, 'wb').write(out)
    print(f'  ion-dist.asar: {len(out)} байт (было {len(data)})')

    # хэши заголовков для exe-манифеста
    app_data = open(dst_path + '.apphash', 'w')
    return out


def header_hash(asar_bytes):
    i = asar_bytes.find(b'{"files"')
    dec = json.JSONDecoder()
    _, jend = dec.raw_decode(asar_bytes[i:].decode('utf-8', errors='replace'))
    return hashlib.sha256(asar_bytes[16:16+jend]).hexdigest()


def main():
    print('=== Сборка русского Claude Desktop ===')
    claude = find_claude()
    res = os.path.join(claude, 'app', 'resources')
    print(f'Найден Claude: {claude}')
    version = os.path.basename(claude).split('_')[1]
    print(f'Версия: {version}')

    # переводы
    ru_main = open(os.path.join(os.path.dirname(__file__), '..', 'translations', 'ru.json'), 'rb').read()
    ru_dyn = open(os.path.join(os.path.dirname(__file__), '..', 'translations', 'dynamic-ru.json'), 'rb').read()
    print(f'Перевод: {len(json.loads(ru_main))} ключей')

    # 1. копия приложения
    print('1/5 Копирую приложение...')
    if os.path.exists(INSTALL_DIR):
        subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-Process Claude -ErrorAction SilentlyContinue | Where-Object {$_.Path -like '*Claude-RU*'} | Stop-Process -Force"], capture_output=True)
        import time; time.sleep(2)
    os.makedirs(INSTALL_DIR, exist_ok=True)
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    f"Copy-Item -Path '{claude}\\*' -Destination '{INSTALL_DIR}' -Recurse -Force"], check=True)

    # 2. app.asar
    print('2/5 Патчу app.asar...')
    app_out = os.path.join(INSTALL_DIR, 'app', 'resources', 'app.asar')
    # сначала оригинальные хэши для exe
    _, orig_header, _ = read_asar(os.path.join(res, 'app.asar'))
    data_orig = open(os.path.join(res, 'app.asar'), 'rb').read()
    _, orig_ion_header, _ = read_asar(os.path.join(res, 'ion-dist.asar'))
    data_ion = open(os.path.join(res, 'ion-dist.asar'), 'rb').read()
    old_app_hash = header_hash(data_orig)
    old_ion_hash = header_hash(data_ion)

    build_app_asar(os.path.join(res, 'app.asar'), app_out)
    new_app_bytes = open(app_out, 'rb').read()
    new_app_hash = header_hash(new_app_bytes)

    # 3. ion-dist.asar
    print('3/5 Патчу ion-dist.asar...')
    ion_out = os.path.join(INSTALL_DIR, 'app', 'resources', 'ion-dist.asar')
    build_ion_dist(os.path.join(res, 'ion-dist.asar'), ion_out, ru_main, ru_dyn, new_app_hash)
    new_ion_bytes = open(ion_out, 'rb').read()
    new_ion_hash = header_hash(new_ion_bytes)

    # 4. хэши в exe
    print('4/5 Обновляю хэши в exe...')
    update_exe_hashes(os.path.join(INSTALL_DIR, 'app', 'claude.exe'),
                      [(old_app_hash, new_app_hash), (old_ion_hash, new_ion_hash)])

    # 5. лаунчер
    print('5/5 Создаю лаунчер...')
    os.makedirs(DATA_DIR, exist_ok=True)
    vbs = os.path.join(INSTALL_DIR, 'launch-ru.vbs')
    open(vbs, 'w', encoding='utf-8').write(
        f'''\' Запуск русифицированной копии Claude с отдельной папкой данных
Set sh = CreateObject("WScript.Shell")
sh.Environment("PROCESS")("CLAUDE_USER_DATA_DIR") = "{DATA_DIR}"
sh.Run """{INSTALL_DIR}\\app\\claude.exe""", 1, False
''')
    print()
    print(f'Готово! Запуск: {vbs}')
    print(f'Папка данных: {DATA_DIR}')
    print('Store-версия не изменена. Обе могут работать одновременно.')


if __name__ == '__main__':
    main()
