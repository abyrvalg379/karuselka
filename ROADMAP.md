# KARUSELKA — план разработки

> Отдельный Blender-аддон быстрого турнтейбла. Вынесен из LAMPOCHKA v3.2
> (решение 2026-08-29, имя выбрано 2026-08-31). Дизайн утверждён юзером.
> Юзкейс: шоурилы моделей — «пресет света (LAMPOCHKA v3.1) + турнтейбл =
> шоурил за две минуты».

## Статус: старт разработки (сессия #1)

Реализовать v1.0.0 по дизайну ниже. Паттерны и структура — как LAMPOCHKA
(`D:\AI\ZCode\Project\LAMPOCHKA\work`): extension (manifest, Blender 4.2+)
+ legacy (bl_info, 3.6+), мок-тесты без Blender, docs EN+RU, zips в
`out/v<версия>/`. Лицензия GPL-3.0-or-later, © Maksim Kovalev. Скилл
blender-addon доступен в сессии.

## Дизайн v1.0.0 (утверждён)

### Панель
Суб-панель/вкладка **KARUSELKA** в N-панели, компактная:
- Target (объект; фолбэк на активный при создании рига)
- Camera (своя или создаётся `LM Karuselka Cam`... имя: `Karuselka Cam`)
- Frames — кадров на полный оборот (дефолт 120; fps берётся из сцены)
- Rounds — оборотов (дефолт 1.0, float)
- Radius — 0 = auto (габарит объекта × 1.5; линза 50 мм даёт запас в кадр)
- Height — высота камеры относительно центра объекта
- Dir — CW/CCW (знак угла)
- Output — путь рендера (дефолт `//turntable/`)
- Кнопки: **Create Rig** / **Remove Rig** / **Render Turntable**

### Риг — Create Rig делает ВСЁ сразу, включая кейфреймы
1. Pivot-empty `Karuselka Pivot` в центре bbox объекта (мировой центр)
2. Камера — child pivot'а, локальная точка (radius, 0, height);
   **Track To → pivot** (орбита от парентинга, прицел от констрейнта —
   вращения не дублируются)
3. Кейфреймы `rotation_euler.z` на pivot'е: кадр 1 → 0°, кадр N →
   ±360° × Rounds; интерполяция **ПРИНУДИТЕЛЬНО LINEAR** (безье = непостоянная
   скорость — главная классическая ошибка турнтейблов)
4. Маркер `karuselka = 1` (custom prop) на всём своём — Remove Rig удаляет
   ТОЛЬКО своё: pivot, свою камеру, констрейнт со своей камеры, анимацию
5. DoF у созданной камеры выключен, линза 50 мм

### Рендер
- Render Turntable: frame_start=1, frame_end=Frames×Rounds, render.filepath,
  затем `bpy.ops.render.render('INVOKE_DEFAULT', animation=True)` —
  неблокирующе
- Настройки движка/сэмплов/формата НЕ трогаются
- Диапазон кадров сцены меняется только в момент рендера и остаётся
  видимым в таймлайне
- Repeat: повторный Create Rig обновляет существующий риг, не плодит
  (один риг за раз)

### Семантика подтверждена юзером
- Create Rig = риг + кейфреймы немедленно; таймлайн скрабится — камера
  уже облетает, ничего нажимать больше не надо
- Render Turntable ничего не создаёт

## Операторы и структура кода
- `karuselka.create_rig`, `karuselka.remove_rig`, `karuselka.render_turntable`
- PropertyGroup `Scene.karuselka` (target, camera, frames, rounds, radius,
  height, direction, output, статус рига через self["key"]-паттерн)
- Иконки сверять с enum Blender 5.x (урок LAMPOCHKA: 'ROTATE' не существует)

## Мок-тесты (~40 проверок)
- регистрация классов/указателей
- расчёт центра bbox и авто-радиуса
- число кейфреймов и линейность интерполяции
- знак направления, Rounds-множитель угла
- cleanup удаляет только своё (маркер), чужую камеру не трогает
- грабли мока из LAMPOCHKA: `remove(o, do_unlink=True)` kwarg,
  location-вектор с .x/.y, сокеты с живым is_linked

## Грабли, известные заранее (из LAMPOCHKA)
- `context.depsgraph` в модалках/операторах не существует →
  `context.evaluated_depsgraph_get()`
- Иконки — только из enum 5.x
- Extension: bl_info в legacy обязателен (в LAMPOCHKA v2.4.1/2.5.0 ушла
  регрессия — не повторять, legacy собирается скриптом с bl_info)
- Диагностика от юзера — через System Console сразу

## После v1.0.0 (кандидаты, не обещано)
- Высота орбиты анимируемая (волна камеры)
- Несколько пресетов камеры (фронт/три-четверти)
- Direct turntable GIF/WebM из рендера
