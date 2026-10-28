# Claude Desktop RU — русский языковой пакет для Claude Desktop (Windows)

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Платформа](https://img.shields.io/badge/platform-Windows-lightgrey)](#)
[![Лицензия MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Строк переведено](https://img.shields.io/badge/%D0%BF%D0%B5%D1%80%D0%B5%D0%B2%D0%B5%D0%B4%D0%B5%D0%BD%D0%BE-38%20892%20%D1%81%D1%82%D1%80%D0%BE%D0%BA-success)](translations/ru.json)

**Русификация интерфейса Claude Desktop для Windows с установкой в отдельную папку.**
Официальная версия из Microsoft Store остаётся нетронутой — обе работают одновременно.

| | |
|---|---|
| 📦 Поддерживаемая версия | Claude Desktop **4.29.0** (MSIX, Store) |
| 🌐 Строк переведено | 38 892 из 39 482 (~98,5%) |
| 🔒 Изменение Store-версии | **нет** — ставится отдельная копия |
| 🛠 Зависимости | Python 3.10+ (только stdlib) |

> Аналогичные проекты: [claude-desktop-zh-cn](https://github.com/ICERainbow666/claude-desktop-zh-cn) (китайский),
> [claude-desktop-zh-tw](https://github.com/YuukiReina2023/Claude-zh-TW-LanguagePack) (тайваньский).
> Русского не существовало — теперь есть.

## Как это работает

1. Скрипт `build.py` копирует установленное приложение Claude в `C:\Users\<user>\Claude-RU`.
2. В копии патчатся два внутренних asar-архива:
   - `app.asar` — карта локалей main-процесса получает `ru`, разрешается переменная
     `CLAUDE_USER_DATA_DIR` (нужна для отдельной папки данных и параллельного запуска);
   - `ion-dist.asar` — в i18n-каталог добавляются `ru.json` (~39 000 переведённых строк)
     и `ru` в списки языков рендерера (в т.ч. в пикер языков в настройках).
3. Пересчитываются контрольные суммы (SHA256 + блочные integrity) asar-архивов
   и обновляется манифест целостности в `claude.exe`.
4. Создаётся лаунчер `launch-ru.vbs`, задающий отдельную папку данных
   `C:\Users\<user>\Claude-RU-Data` и запускающий копию без окна консоли.

**Ни один файл в `WindowsApps` не изменяется.** Оригинальная Store-версия продолжает
работать как обычно — обе копии запускаются одновременно.

## Установка

### Способ 1 — готовый EXE (проще всего)

1. Скачайте **ClaudeDesktopRuSetup.exe** со страницы
   [Releases](https://github.com/arhi442/claude-desktop-ru/releases).
2. Запустите его (права администратора не нужны).
3. Дождитесь надписи «Готово».

Ничего устанавливать не нужно: Python и все переводы уже внутри EXE.

### Способ 2 — из исходников

```
git clone https://github.com/arhi442/claude-desktop-ru.git
cd claude-desktop-ru
python build.py
```

Требования: Windows 10/11, Python 3.10+ (только стандартная библиотека),
установленный из Microsoft Store Claude Desktop.

### После установки

Запуск: через `launch-ru.vbs` в папке Claude-RU (создайте ярлык).
Оригинальный Claude из Store продолжает работать одновременно.

Язык: русский выбирается по локали Windows, также есть в Settings → Language.

## Перенос чатов из основной версии

Чаты хранятся в `%LOCALAPPDATA%\<профиль>\claude-code-sessions\<accountId>` и
скопировать их можно обычным копированием папки под нужный account id копии
(см. `tools/migrate-chats.py`).

## Обновление при выходе новой версии Claude

1. `python tools/translate.py` — переводит новые строки (EN-словарь `cache.json`
   переиспользуется, переводятся только добавленные строки через бесплатный
   эндпоинт Google Translate).
2. `python build.py` — пересборка под новую версию (скрипт сам находит файлы по
   содержимому, а не по именам).

## Структура

```
build.py                  — сборка копии с русификацией (главный скрипт)
translations/ru.json      — русский каталог (~39 000 строк, ion-dist)
translations/dynamic-ru.json — динамический каталог (49 строк)
translations/cache.json   — кэш переводов EN→RU (для переиспользования)
tools/translate.py        — генерация/доперевод каталога
tools/migrate-chats.py    — перенос чатов из основной версии
```

## Технические детали

- **Asar integrity**: Electron проверяет SHA256-хэш заголовка каждого asar (вшит в exe)
  и блочные хэши каждого файла. Мы пересчитываем всё: `make_integrity()` обязательно
  генерирует `ceil(size/4MiB)` блочных хэшей — ошибка в их числе приводит к фатальному
  падению приложения (`asar_file_validator.cc: Streaming ASAR file block hash failed`).
- **Параллельный запуск**: Electron-замок single-instance общий, поэтому копии даётся
  своя папка через `CLAUDE_USER_DATA_DIR`. В упакованной сборке переменная принудительно
  удаляется из env — это отключается точечным патчем равной длины (`delete` → `void`).
- **MSIX-целостность**: мы не трогаем Store-файлы, поэтому подпись пакета остаётся валидной.

## Лицензия и ограничения

- Проект не связан с Anthropic. Claude — товарный знак Anthropic, PBC.
- Перевод выполнен автоматически (Google Translate) с ручными исправлениями ICU-форм,
  плейсхолдеров и тегов; возможны неточности.
- Используйте на свой риск.

## ⭐ Поддержите проект

Если пакет оказался полезен — поставьте ⭐ звёздочку вверху страницы.
Это единственный способ узнать автору, что работа не зря, и помогает
проекту найти другие люди, ищущие русский Claude Desktop.
Нашли неточный перевод — откройте [Issue](https://github.com/arhi442/claude-desktop-ru/issues),
поправим.

## Похожие проекты

- [claude-desktop-zh-cn](https://github.com/ICERainbow666/claude-desktop-zh-cn) — китайский (упрощённый) языковой пакет
- [claude-desktop-zh-tw](https://github.com/YuukiReina2023/Claude-zh-TW-LanguagePack) — китайский (тайваньский) языковой пакет
- [LifeActor/Claude_zh-CN_LanguagePack](https://github.com/LifeActor/Claude_zh-CN_LanguagePack) — китайский для Claude Code и Desktop

## Частые вопросы

**Безопасно ли это?** Да: ни один файл оригинального Claude Desktop не изменяется —
ставится отдельная копия. Подпись MSIX-пакета Store-версии остаётся валидной.

**Поймёт ли антивирус установщик как угрозу?** EXE — это PyInstaller-обёртка обычного
Python-скрипта; исходный код открыт и лежит в этом же репозитории, можно собрать его самому.

**Пропадут ли чаты?** Нет: чаты основной версии не трогаются; в копию их можно перенести
скриптом `tools/migrate-chats.py`.

**Что с обновлениями Claude?** После обновления Store-версии запустите установку заново —
переведённые ранее строки берутся из кэша, переводятся только новые.

**Почему часть текста осталась английской?** Бренды (Claude, Anthropic), технические
термины (API, MCP, SSO) и плейсхолдеры (`{count}`) намеренно не переводятся; часть
текстов приходит с сервера и переводом не покрывается.

## Известные ограничения

- После обновления Store-версии русификацию нужно пересобрать (см. «Обновление»).
- Копия стартует с чистым профилем: войдите заново или настройте Inference Gateway
  (конфигурация `configLibrary` основной версии копируется скриптом миграции).
- Часть текстов приходит с сервера claude.ai и переводом не покрывается.

---

### Поиск по ключевым словам

Русский Claude Desktop, русификатор Claude Desktop, Claude Desktop на русском,
русский язык интерфейс Claude, Claude Desktop localization Russian,
RU языковой пакет Claude, перевод Claude Desktop, Claude Desktop RU langpack,
русификация Anthropic Claude, Claude Desktop сменить язык, русский интерфейс Claude app,
Claude Desktop Windows русский, как сделать Claude на русском, Claude RU.
