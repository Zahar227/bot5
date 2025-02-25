import telebot
from mnemonic import Mnemonic
from eth_account import Account
from web3 import Web3
import time
import pickle
import os
from concurrent.futures import ThreadPoolExecutor

# Включаем HDWallet функции
Account.enable_unaudited_hdwallet_features()

# Ваши ключи
BOT_API_KEY = '7369094582:AAG-ZfcgAIPS44rwiV7xgqz4P268bgdtqbw'

# Список HTTP-нод для автоматического переключения
NODE_URLS = [
    "https://ethereum-rpc.publicnode.com",
    "https://eth.meowrpc.com",
    "https://eth.drpc.org",
    "https://rpc.mevblocker.io/fast",
    "https://rpc.mevblocker.io/fullprivacy",
    "https://eth.rpc.blxrbdn.com",
    "https://rpc.ankr.com/eth",
    "https://rpc.mevblocker.io/fast",
    "https://eth.llamarpc.com",
    "https://rpc.eth.gateway.fm",
    "https://gateway.tenderly.co/public/mainnet",
    "https://eth1.lava.build"
]

# Индекс текущей ноды
current_node_index = 0

# Функция для получения рабочего экземпляра Web3
def get_web3_instance():
    global current_node_index
    for _ in range(len(NODE_URLS)):  # Перебираем ноды по кругу
        node_url = NODE_URLS[current_node_index]
        w3 = Web3(Web3.HTTPProvider(node_url))

        if w3.is_connected():
            print(f"✅ Подключено к Ethereum через {node_url}")
            return w3  # Возвращаем рабочий экземпляр Web3

        print(f"⚠️ Нода {node_url} недоступна, переключаюсь...")
        current_node_index = (current_node_index + 1) % len(NODE_URLS)
        time.sleep(1)

    print("🚨 Все ноды недоступны!")
    raise Exception("Не удалось подключиться ни к одной ноде!")

# Подключение к первой доступной ноде
w3 = get_web3_instance()

# Создание бота
bot = telebot.TeleBot(BOT_API_KEY)

# Путь к файлу для хранения кэша
CACHE_FILE = 'nonce_cache.pkl'

# Функция для загрузки кэша из файла
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'rb') as f:
            try:
                return pickle.load(f)
            except EOFError:
                return {}
    return {}

# Функция для сохранения кэша в файл
def save_cache(cache):
    with open(CACHE_FILE, 'wb') as f:
        pickle.dump(cache, f)

# Загружаем кэш при старте программы
nonce_cache = load_cache()

# Функция генерации кошелька
def generate_wallet():
    mnemo = Mnemonic("english")
    seed_phrase = mnemo.generate(strength=128)  # 12 слов (128 бит энтропии)
    acct = Account.from_mnemonic(seed_phrase)
    address = acct.address
    return seed_phrase, address

# Функция проверки активности кошелька через nonce с автоматическим переключением ноды
def check_activity(address):
    global w3, current_node_index

    if address in nonce_cache:
        return nonce_cache[address]

    attempts = 0
    while attempts < len(NODE_URLS):  # Пробуем переключиться на рабочую ноду
        try:
            nonce = w3.eth.get_transaction_count(address)
            nonce_cache[address] = nonce  # Кэшируем результат
            return nonce
        except Exception as e:
            print(f"Ошибка запроса к ноде {NODE_URLS[current_node_index]}: {e}")
            current_node_index = (current_node_index + 1) % len(NODE_URLS)  # Переключаемся на следующую ноду
            w3 = get_web3_instance()  # Обновляем Web3
            attempts += 1

    print("🚨 Все ноды недоступны!")
    return 0  # Если все ноды не работают, считаем кошелек неактивным

# Функция проверки активности для нескольких кошельков
def check_multiple_wallets(wallets):
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_results = executor.map(lambda wallet: (wallet, check_activity(wallet[1])), wallets)

        for wallet, nonce in future_results:
            results.append((wallet[0], wallet[1], nonce))
            nonce_cache[wallet[1]] = nonce

    save_cache(nonce_cache)
    return results

# Обработка команды /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Я могу генерировать ETH-адреса, проверять их активность и предоставлять сид-фразы.")

# Функция для проверки активности тестового кошелька
def test_wallet_activity(seed_phrase, message):
    try:
        acct = Account.from_mnemonic(seed_phrase)
        address = acct.address
        nonce = check_activity(address)

        response = (
            f"Тестовый кошелек:\n"
            f"Сид-фраза: {seed_phrase}\n"
            f"Адрес: {address}\n"
            f"Количество транзакций (nonce): {nonce}"
        )
        bot.send_message(message.chat.id, response)

        if nonce > 0:
            bot.send_message(message.chat.id, "Этот кошелек активен!")
        else:
            bot.send_message(message.chat.id, "Этот кошелек неактивен (транзакций нет).")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при проверке кошелька: {e}")

# Обработка команды /test_wallet
@bot.message_handler(commands=['test_wallet'])
def test_wallet(message):
    test_seed_phrase = "fluid giant mosquito sure prefer truth rare harsh nature urge relax sort"
    test_wallet_activity(test_seed_phrase, message)

# Обработка команды /generate
@bot.message_handler(commands=['generate'])
def generate(message):
    bot.send_message(message.chat.id, "Ищу активные кошельки, это может занять некоторое время...")

    count = 0
    while True:
        wallets = [generate_wallet() for _ in range(10)]  # Генерация 10 кошельков
        activities = check_multiple_wallets(wallets)  # Проверка активности кошельков

        for seed_phrase, address, nonce in activities:
            count += 1

            if count % 1000 == 0:
                progress_message = f"Проверено {count} кошельков. Последний адрес: {address}, Транзакции (nonce): {nonce}"
                bot.send_message(message.chat.id, progress_message)

            if nonce > 0:  # Если кошелек имеет транзакции
                response = f"Сгенерированная сид-фраза: {seed_phrase}\nАдрес: {address}\nКоличество транзакций: {nonce}"
                bot.send_message(message.chat.id, response)
                return  # Останавливаем цикл после нахождения активного кошелька

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен и готов к работе.")
    bot.polling()