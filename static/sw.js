const CACHE_NAME = 'handshake-v10'; // Поменяли версию!
const ASSETS_TO_CACHE = [
    '/',
    '/static/css/style.css', 
    '/static/img/icon.png', // Указываем тот же файл, что в манифесте
    '/static/manifest.json'
];

// Установка Service Worker
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Кэшируем ресурсы');
                return cache.addAll(ASSETS_TO_CACHE);
            })
    );
});

// Активация
self.addEventListener('activate', (event) => {
    console.log('Service Worker активирован');
});

// Перехват запросов (обязательно для PWA)
self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                // Возвращаем файл из кэша, если он там есть, иначе идем в сеть
                return response || fetch(event.request);
            })
    );
});