import subprocess
import sys
from colorama import init, Fore, Style

# Инициализация Colorama для поддержки цветов в консоли
init(autoreset=True)

def print_banner():
    """
    Выводит красивый ASCII-арт баннер.
    """
    banner_art = """
    ██████╗  ██████╗ ██████╗ ████████╗  ██████╗   ██████╗
    ██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝ ██╔════╝  ██╔════╝
    ██████╔╝██║   ██║██████╔╝   ██║    ██║  ███╗╚█████╗
    ██╔══██╗██║   ██║██╔══██╗   ██║    ██║   ██║ ╚═══██╗
    ██║  ██║╚██████╔╝██║  ██║   ██║    ╚██████╔╝██████╔╝
    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝     ╚═════╝ ╚═════╝
    """
    print(Fore.CYAN + Style.BRIGHT + banner_art)
    print(Fore.YELLOW + Style.BRIGHT + "            Bot Launcher & Real-time Monitor v1.0")
    print("-" * 60)

def stylize_log(line):
    """
    Применяет стили к строке лога в зависимости от ее содержимого.
    """
    line = line.strip()
    if not line:
        return ""

    # Стандартные уровни логирования
    if "ERROR" in line or "error" in line.lower():
        return Fore.RED + Style.BRIGHT + f"[🔥 ERROR] {line}"
    elif "WARNING" in line or "warn" in line.lower():
        return Fore.YELLOW + Style.BRIGHT + f"[⚠️ WARN]  {line}"
    elif "CRITICAL" in line:
        return Fore.RED + Style.BRIGHT + f"[💥 CRIT]  {line}"
    
    # Кастомные события для красоты
    elif "одобряет заказ" in line.lower():
        return Fore.GREEN + Style.BRIGHT + f"[✅ APPROVE] {line}"
    elif "отклоняет заказ" in line.lower():
        return Fore.MAGENTA + Style.BRIGHT + f"[❌ DECLINE] {line}"
    elif "новое подтверждение оплаты" in line.lower():
        return Fore.BLUE + Style.BRIGHT + f"[💰 PAYMENT] {line}"
    elif "новый пользователь" in line.lower():
        return Fore.GREEN + f"[👤 NEW USER] {line}"
    elif "заказ создан" in line.lower():
        return Fore.CYAN + f"[🛒 NEW ORDER] {line}"
    elif "запускает бота" in line.lower():
         return Fore.WHITE + Style.BRIGHT + f"[🚀 SYSTEM] {line}"
    
    # Логи по умолчанию
    else:
        return Fore.WHITE + f"[ℹ️ INFO]  {line}"

def run_bot():
    """
    Запускает bot.py как дочерний процесс и отслеживает его вывод.
    """
    print(stylize_log("Запускает бота... Нажмите Ctrl+C для остановки."))
    
    # Запускаем bot.py, перехватывая его стандартный вывод (stdout)
    # и стандартный вывод ошибок (stderr) в один поток.
    try:
        process = subprocess.Popen(
            [sys.executable, "bot.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1  # Включаем построчную буферизацию
        )

        # Читаем вывод бота в реальном времени
        for line in iter(process.stdout.readline, ''):
            print(stylize_log(line))

        # Ожидаем завершения процесса
        process.wait()
        if process.returncode != 0:
            print(stylize_log(f"Бот завершился с кодом ошибки: {process.returncode}"))

    except FileNotFoundError:
        print(stylize_log("ОШИБКА: Файл 'bot.py' не найден. Убедитесь, что он находится в той же папке."))
    except KeyboardInterrupt:
        print(stylize_log("\nПолучен сигнал прерывания (Ctrl+C). Завершаю работу бота..."))
        process.terminate()  # Корректно останавливаем процесс
        process.wait()
        print(stylize_log("Бот успешно остановлен."))
    except Exception as e:
        print(stylize_log(f"Произошла критическая ошибка: {e}"))


if __name__ == "__main__":
    print_banner()
    run_bot()
