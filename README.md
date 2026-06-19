# RAM Price Observer

Сервис для мониторинга цен на оперативную память в российских интернет-магазинах. Автоматически собирает данные с DNS, Citilink, М.Видео, Regard и Onlinetrade, дедуплицирует товары по артикулу производителя и показывает историю изменения цены по каждому магазину на интерактивном графике. Позволяет сравнить до 4 модулей ОЗУ по характеристикам и ценам в одном окне.

**Рабочий деплой:** https://ramcompare.vercel.app

---

## Технологии

| Слой | Стек |
|------|------|
| Backend | Python 3.13, Django 4.2 |
| База данных | SQLite |
| Парсинг HTML | BeautifulSoup4, lxml |
| Парсинг JS-сайтов | zendriver (headless Chrome) |
| HTTP-клиент | requests\[socks\] |
| Графики | Plotly 5 |
| Деплой | Vercel, WhiteNoise |

---

## Скриншоты

### Каталог с фильтрами и сортировкой
![Каталог](screenshots/catalog.png)
*Боковая панель с фильтрами по бренду, типу DDR, частоте и ценовому диапазону. Нижняя полоса сравнения активируется при добавлении товаров.*

### Страница товара — история цен
![История цен](screenshots/detail.png)
*Интерактивный линейный график Plotly с отдельной линией для каждого магазина и таблица актуальных предложений с трендами роста/снижения цены.*

### Сравнение модулей
![Сравнение](screenshots/compare.png)
*Таблица сравнения 2–4 модулей: лучшие значения по частоте, объёму, CAS-задержке и минимальной цене подсвечиваются автоматически.*

---

## Установка и запуск локально

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/diddyFR1986/ram-price-observer.git
cd ram-price-observer
```

### 2. Создайте и активируйте виртуальное окружение

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

### 4. Настройте переменные окружения

Создайте файл `.env` в корне проекта:

```env
DEBUG=True
SECRET_KEY=any-random-string-here
SCRAPE_CITY=Екатеринбург
SCRAPE_PROXY_URL=
```

### 5. Примените миграции

```bash
python manage.py migrate
```

### 6. (Опционально) Создайте суперпользователя

```bash
python manage.py createsuperuser
```

### 7. Запустите сервер

```bash
python manage.py runserver
```

Откройте в браузере: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## Наполнение данными

Для загрузки актуальных цен запустите парсинг:

```bash
# Все площадки сразу
python manage.py scrape

# Только одна площадка
python manage.py scrape --source dns
python manage.py scrape --source citilink
python manage.py scrape --source mvideo
python manage.py scrape --source regard
python manage.py scrape --source onlinetrade
```

Запуск парсинга также доступен прямо из интерфейса каталога через кнопку «Обновить цены».

---

## Структура проекта

```
├── products/          # Каталог, детальная страница, сравнение
├── scraper/           # Парсеры торговых площадок (DNS, Citilink, …)
├── analytics/         # Plotly-графики истории цен
├── templates/         # HTML-шаблоны
├── static/            # CSS и SVG-ассеты
├── config/            # Настройки Django
└── requirements.txt
```
