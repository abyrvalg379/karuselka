# KARUSELKA — план разработки

> Отдельный Blender-аддон быстрого турнтейбла. Вынесен из LAMPOCHKA v3.2
> (решение 2026-08-29, имя выбрано 2026-08-31). Юзкейс: шоурилы моделей —
> «пресет света (LAMPOCHKA v3.1) + турнтейбл = шоурил за две минуты».
> Автор: Maksim Kovalev, GPL-3.0-or-later. Утверждённый дизайн v1.0.0 и
> полная история — в git (`git log --stat`).

## Текущее состояние: v1.4.0 (2026-09-04)

Панель N > KARUSELKA, вся живая (без пересборки рига):
- **Scope**: Target (фолбэк — активный объект) или Collection — турнтейбл
  всей сборки; общий bbox только по геометрии (хелпер-пустышки/свет не
  искажают центр и радиус)
- **Mode**: Camera (орбита) / Object (вращается объект: корни иерархий
  парентятся к `KARUSELKA_Empty`, камера статична)
- **Center**: Bounds / 3D Cursor (переключение на живом риге)
- **Timing**: Frames/Rounds/Dir — ретаймят кейфреймы и таймлайн живьём;
  Create Rig ставит таймлайн 1..N и прыгает на кадр 1
- **Placement**: Radius (0 = авто = габарит скоупа × Margin 2.5), Height
- **Камера**: своя или создаётся (50 мм, DoF off, клипы 0.1/100 — дефолты
  Blender); Lens/DoF/клипы правятся из панели живьём; Keep Settings —
  пересборка наследует предыдущую камеру
- **Shot presets**: Front / Three-Quarter / Top / Hero в один клик +
  пользовательские .json-пресеты (папка в Preferences, живой подхват, Save)
- **Start Angle**: угол орбиты в кадре 1 (прописан в пресеты и ретайм)
- **Выход**: Resolution (Scene / Square 1080 / 1080p / 1440p / 4K / 2048×858),
  Samples (Scene / Draft 32 / Normal 128 / High 256 — маппинг на движок
  с гардами от K-Cycles), Format (PNG / MP4 / WebM); автонейминг
  `<asset>_turntable` (asset = имя .blend-проекта, фолбэк — скоуп)
- rig-камера = scene.camera (Remove Rig возвращает прежнюю); render
  предупреждает при отсутствии света; один риг за раз; Remove удаляет
  только своё (маркер `karuselka=1`)

Инфра: extension (4.2+) + legacy (3.6+); сборка ТОЛЬКО через `build.py`
(регекс версии `^version` якорить — иначе матчится schema_version); тесты:
моки 160/160 (py3.14, `tests/test_mock.py`), live headless Blender 5.2
(`tests/live_check.py`), диагностика живой сцены `tests/diag_random_cam.py`
и по сокету 9876 (сервер возвращает stdout).

## История релизов
- **v1.4.0** — Shot presets (Front/3-4/Top/Hero + .json-папка + Save),
  Start Angle; починена двойная конвертация угла (radians×2)
- **v1.3.1** — assetname = имя .blend-проекта (фолбэк — скоуп); пресет 2048×858 — assetname = имя .blend-проекта (фолбэк — скоуп); пресет 2048×858
- **v1.3.0** — Output-пресеты: Resolution / Samples / Format (MP4, WebM)
- **v1.2.2** — Center: Bounds / 3D Cursor, живое переключение
- **v1.2.1** — bbox только по геометрии (пустышки не искажают центр)
- **v1.2.0** — Collection-скоуп: сборный bbox/центр/радиус; клипы — дефолты Blender
- **v1.1.x** — Keep Settings, Margin, режимы Camera/Object (парентинг корня
  иерархии), вся панель живая; ревизия: spin-прыжок (stale matrix_world →
  `Matrix.Translation(-center)`), last_radius фолбэк, мёртвый код удалён
- **v1.0.x** — база + хотфиксы: прыжок на кадр 1 (камера не «в рандомном месте»),
  rig-камера = scene.camera («пустой вид из камеры»), slotted actions
  (нет `Action.fcurves` → layers/strips/channelbags)
- Кейс «чёрный вид из камеры» = NaN в `view_camera_offset` вьюпорта юзера —
  не аддон; уроки в blender-addon-lessons

## План

### v1.5.0 — Движение камеры
- Анимируемая высота (волна): Height Start/End на длину рига, LINEAR
- Наклон плоскости орбиты (Axis Tilt) — опционально

### Инфраструктура (параллельно, без версии)
- GitHub-репо abyrvalg379/karuselka + demo GIF в README (без гифки репо
  не смотрят — аудит профиля)
- extensions.blender.org — публикация extension-версии
- Тест-матрица: 4.2 LTS / 4.5 / 5.x headless-прогон live_check
- Демо-сцена для скриншота панели

### Кандидаты (не обещано)
- Preview-кнопка: OpenGL/Workbench черновик до чистового рендера
- GIF через внешний ffmpeg.exe
- Несколько ригов одновременно (суффиксы KARUSELKA_Empty)
- Кеш panel-скана через depsgraph-хендлер (сцены 100k+ объектов)
- Undo-безопасные панельные правки (операторы вместо update-колбэков) —
  сначала задокументировать ограничение
- Auto DoF: фокус в центр объекта
- Spin + своя камера: восстановление исходного парентинга камеры

### Не делаем
- Интерактивное размещение/модалки, свет/HDRI — территория LAMPOCHKA;
  интеграция = пресеты света LAMPOCHKA + турнтейбл KARUSELKA
