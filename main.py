import os
import subprocess
import tempfile
from git import Repo
import requests
from typing import Dict, List, Optional
from urllib.parse import urlparse
import json
import time
import sys
import random
import threading # Для запуска анимации в отдельном потоке

class RepositoryDocumenter:
    """
    Класс для документирования репозиториев GitHub с использованием локальной LLM (Ollama).
    Клонирует репозиторий, сканирует файлы, анализирует их с помощью LLM и генерирует README.md.
    """

    def __init__(self, repo_path: str, model_name: str = "saiga", ollama_url: str = "http://localhost:11434/api/generate"):
        """
        Инициализирует RepositoryDocumenter.

        Args:
            repo_path (str): Локальный путь к репозиторию или URL Git репозитория.
            model_name (str): Имя модели Ollama для использования (по умолчанию "saiga").
            ollama_url (str): URL-адрес API Ollama (по умолчанию "http://localhost:11434/api/generate").
        """
        self.repo_path = repo_path
        self.model_name = model_name
        self.ollama_url = ollama_url
        self.temp_dir = None
        self.repo = None
        self.initialize_repository()
        
        # Директории и файлы, которые следует игнорировать при сканировании
        self.ignore_dirs = ['.git', '__pycache__', 'node_modules', 'venv', 'env', '.idea', '.vscode', '.github']
        self.ignore_files = ['.gitignore', 'README.md', 'LICENSE', 'CONTRIBUTING.md', 'CODE_OF_CONDUCT.md']
        
        # Сопоставление расширений файлов с языками программирования
        self.file_extensions = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.kt': 'Kotlin',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.sh': 'Bash',
            '.md': 'Markdown',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SASS',
            '.json': 'JSON',
            '.yml': 'YAML',
            '.yaml': 'YAML',
            '.toml': 'TOML',
            '.dockerfile': 'Docker',
            '.sql': 'SQL',
            '.c': 'C',
            '.cpp': 'C++',
            '.h': 'C/C++ Header',
            '.hpp': 'C++ Header',
            '.cs': 'C#',
            '.swift': 'Swift',
            '.r': 'R',
            '.pl': 'Perl',
            '.lua': 'Lua',
            '.vue': 'Vue.js',
            '.jsx': 'React JSX',
            '.tsx': 'React TSX'
        }

    def initialize_repository(self):
        """
        Инициализирует репозиторий из локального пути или URL.
        Если это URL, репозиторий клонируется во временную директорию.
        """
        if self.repo_path.startswith(('http://', 'https://', 'git://')):
            # Определяем путь к директории, где запущен скрипт
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.temp_dir = os.path.join(script_dir, "temp_repos")
            
            # Создаем временную директорию, если ее нет
            os.makedirs(self.temp_dir, exist_ok=True)

            sys.stdout.write(f"Клонируем репозиторий во временную директорию: {self.temp_dir}\n")
            sys.stdout.flush()
            try:
                # Клонируем репозиторий в поддиректорию внутри temp_repos
                repo_name = urlparse(self.repo_path).path.split('/')[-1]
                if repo_name.endswith('.git'):
                    repo_name = repo_name[:-4]
                clone_path = os.path.join(self.temp_dir, repo_name)
                
                # Если директория уже существует, удаляем ее перед клонированием
                if os.path.exists(clone_path):
                    import shutil
                    sys.stdout.write(f"Обнаружена существующая директория {clone_path}. Удаляем...\n")
                    sys.stdout.flush()
                    try:
                        shutil.rmtree(clone_path)
                    except Exception as e:
                        sys.stdout.write(f"Не удалось удалить существующую директорию {clone_path}: {e}\n")
                        sys.stdout.flush()
                        raise Exception(f"Ошибка при очистке существующей директории: {e}")

                self.repo = Repo.clone_from(self.repo_path, clone_path)
                self.repo_path = clone_path # Обновляем repo_path на фактический путь клонированного репо
            except Exception as e:
                self.repo = None
                raise Exception(f"Ошибка при клонировании репозитория: {e}")
        else:
            if not os.path.exists(self.repo_path):
                self.repo = None
                raise Exception(f"Путь не существует: {self.repo_path}")
            try:
                self.repo = Repo(self.repo_path)
            except Exception as e:
                self.repo = None
                raise Exception(f"Ошибка при открытии репозитория: {e}")

    def cleanup(self):
        """Очищает временные файлы, если репозиторий был клонирован во временную директорию."""
        # Проверяем, что self.temp_dir был установлен (т.е. репозиторий был клонирован)
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            print(f"Удаляем временную директорию: {self.temp_dir}")
            
            # Явно закрываем репозиторий, чтобы освободить файловые дескрипторы
            if self.repo:
                try:
                    self.repo.close()
                    self.repo = None # Устанавливаем в None после закрытия
                except Exception as e:
                    print(f"Предупреждение: Не удалось закрыть объект репозитория: {e}")

            # Механизм повторных попыток для rmtree при PermissionError (часто встречается в Windows)
            max_retries = 5
            for i in range(max_retries):
                try:
                    shutil.rmtree(self.temp_dir)
                    print(f"Временная директория {self.temp_dir} успешно удалена.")
                    break # Выход из цикла, если успешно
                except PermissionError as e:
                    if i < max_retries - 1:
                        print(f"Ошибка доступа при удалении {self.temp_dir}. Повторная попытка через 1 секунду... ({e})")
                        time.sleep(1)
                    else:
                        print(f"Не удалось удалить временную директорию {self.temp_dir} после {max_retries} попыток. Пожалуйста, удалите вручную. ({e})")
                except Exception as e:
                    print(f"Ошибка при удалении временной директории {self.temp_dir}: {e}")
                    break # Выход при других типах ошибок

    def get_repo_info(self) -> Dict:
        """
        Получает базовую информацию о репозитории, включая имя, описание,
        список файлов, информацию о последнем коммите, статистику по языкам
        и URL удаленного репозитория.

        Returns:
            Dict: Словарь с информацией о репозитории.
        """
        repo_name = "неизвестно" # Default fallback
        remote_url = self._get_remote_url()
        if remote_url:
            parsed_url = urlparse(remote_url)
            path_parts = parsed_url.path.split('/')
            if path_parts:
                repo_name = path_parts[-1]
                if repo_name.endswith('.git'):
                    repo_name = repo_name[:-4]
        elif self.repo_path: # Fallback to local path if no remote URL
            # Если репозиторий был клонирован, self.repo_path уже будет указывать на поддиректорию
            # внутри temp_repos, поэтому os.path.basename(self.repo_path) даст корректное имя.
            repo_name = os.path.basename(self.repo_path)

        return {
            "name": repo_name,
            "description": "Автоматически сгенерированное описание проекта",
            "files": self._scan_repository(),
            "last_commit": self._get_last_commit_info(),
            "language_stats": self._get_language_stats(),
            "remote_url": remote_url # Убедимся, что remote_url всегда возвращается
        }

    def _scan_repository(self) -> List[Dict]:
        """
        Сканирует репозиторий, собирая информацию о файлах,
        игнорируя служебные директории и файлы.

        Returns:
            List[Dict]: Список словарей, каждый из которых содержит информацию о файле.
        """
        files_info = []
        
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            
            for file in files:
                if file in self.ignore_files:
                    continue
                
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.repo_path)
                file_ext = os.path.splitext(file)[1].lower()
                
                file_info = {
                    "path": rel_path,
                    "extension": file_ext,
                    "language": self.file_extensions.get(file_ext, "Unknown"),
                    "content": self._read_file_content(file_path),
                    "analysis": None
                }
                
                files_info.append(file_info)
        
        return files_info

    def _read_file_content(self, file_path: str) -> Optional[str]:
        """
        Читает содержимое файла, пытаясь использовать различные кодировки
        для предотвращения ошибок.

        Args:
            file_path (str): Путь к файлу.

        Returns:
            Optional[str]: Содержимое файла в виде строки или None в случае ошибки.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return content
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                    return content
            except Exception as e:
                print(f"Не удалось прочитать файл {file_path} с кодировкой latin-1: {e}")
                return None
        except Exception as e:
            print(f"Ошибка при чтении файла {file_path}: {e}")
            return None

    def _get_last_commit_info(self) -> Dict:
        """
        Получает информацию о последнем коммите репозитория.
        Обрабатывает случай, когда репозиторий не инициализирован.

        Returns:
            Dict: Словарь с хэшем, сообщением, автором и датой последнего коммита.
                  Пустой словарь, если информация недоступна.
        """
        if not self.repo:
            print("Репозиторий не инициализирован, не удалось получить информацию о коммитах.")
            return {}
        try:
            commit = self.repo.head.commit
            return {
                "hash": commit.hexsha,
                "message": commit.message.strip(),
                "author": f"{commit.author.name} <{commit.author.email}>",
                "date": commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            print(f"Не удалось получить информацию о коммитах: {e}")
            return {}

    def _get_remote_url(self) -> str:
        """
        Получает URL удаленного репозитория.
        Обрабатывает случай, когда репозиторий не инициализирован.

        Returns:
            str: URL удаленного репозитория или пустая строка, если не найден.
        """
        if not self.repo:
            # Если репозиторий не инициализирован, но repo_path был URL, используем его
            if self.repo_path.startswith(('http://', 'https://', 'git://')):
                return self.repo_path
            return ""
        try:
            remote = self.repo.remote()
            return next(remote.urls) if remote.urls else ""
        except Exception as e:
            print(f"Не удалось получить URL удаленного репозитория: {e}")
            return ""

    def _get_language_stats(self) -> Dict:
        """
        Анализирует статистику по языкам программирования в репозитории,
        подсчитывая количество файлов для каждого языка.

        Returns:
            Dict: Словарь, где ключи - языки, а значения - количество файлов.
        """
        stats = {}
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in self.file_extensions:
                    lang = self.file_extensions[ext]
                    stats[lang] = stats.get(lang, 0) + 1
        
        return stats

    def _print_status(self, message: str, progress: Optional[int] = None):
        """
        Выводит сообщение о статусе и опционально прогресс-бар в консоль.
        Этот метод предназначен для вывода *неанимированных* сообщений.
        Анимированный прогресс-бар обрабатывается функцией run_with_loading_animation.
        """
        if progress is not None:
            # Этот блок не должен вызываться напрямую из методов класса,
            # если run_with_loading_animation используется для общей анимации.
            # Оставлен для отладки или специфических случаев.
            bar_length = 40
            filled_length = int(bar_length * progress / 100)
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            sys.stdout.write(f'\r[{bar}] {progress:3}% {message}')
            sys.stdout.flush()
        else:
            print(message)
            sys.stdout.flush()

    def analyze_with_llm(self, prompt: str, current_task_description: str = "", 
                         response_mime_type: Optional[str] = None, response_schema: Optional[Dict] = None) -> str:
        """
        Отправляет запрос в LLM через Ollama API.

        Args:
            prompt (str): Промпт для LLM.
            current_task_description (str): Описание текущей задачи для отображения в статусе.
            response_mime_type (Optional[str]): MIME-тип ожидаемого ответа (например, "application/json").
            response_schema (Optional[Dict]): JSON-схема ожидаемого ответа.

        Returns:
            str: Ответ от LLM. Пустая строка в случае ошибки.
        """
        headers = {'Content-Type': 'application/json'}
        data = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False # Мы не используем потоковую передачу для этого случая
        }
        if response_mime_type:
            data["format"] = response_mime_type.split('/')[-1] # Ollama использует 'json' вместо 'application/json'
        if response_schema:
            data["options"] = {"response_schema": response_schema} # Это может варьироваться в зависимости от конкретной реализации Ollama
        
        response = None # Инициализируем response как None
        try:
            response = requests.post(self.ollama_url, headers=headers, data=json.dumps(data), timeout=300)
            response.raise_for_status()
            
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе к Ollama для '{current_task_description}': {e}")
            if response is not None and hasattr(response, 'text'):
                print(f"Ответ сервера: {response.text}")
            else:
                print("Нет ответа от сервера или ошибка подключения.")
            return ""
        except json.JSONDecodeError:
            response_text = "Ответ не получен"
            if response is not None and hasattr(response, 'text'):
                try:
                    response_text = response.text
                except Exception:
                    pass
            print(f"Ошибка декодирования JSON ответа от Ollama для '{current_task_description}': {response_text}")
            return ""
        except Exception as e:
            print(f"Неизвестная ошибка при запросе к LLM для '{current_task_description}': {e}")
            return ""

    def analyze_file(self, file_info: Dict) -> Dict:
        """
        Анализирует содержимое одного файла с помощью LLM,
        формируя структурированный анализ. Особое внимание уделяется цели файла.

        Args:
            file_info (Dict): Словарь с информацией о файле, включая его содержимое.

        Returns:
            Dict: Обновленный словарь с информацией о файле, содержащий анализ LLM.
        """
        if not file_info["content"] or file_info["language"] in ["Unknown", "JSON", "YAML", "TOML", "Markdown"]:
            return file_info
        
        prompt_template = f"""
        Ты - опытный тимлид и главный архитектор проекта. Твоя задача - проанализировать предоставленный фрагмент кода и предоставить информацию в следующем формате, используя русский язык и markdown разметку.
        Будь точным, лаконичным и максимально полезным для понимания проекта.
        **Особое внимание удели основной ЦЕЛИ и РОЛИ этого файла в контексте всего проекта, как будто ты объясняешь это новому члену команды.**
        **Избегай любых формулировок, которые могли бы намекнуть на то, что текст сгенерирован ИИ. Пиши естественно, как человек.**
        
        Пример желаемого тона и стиля:
        "Этот файл - сердце нашего модуля аутентификации. Здесь мы не только обрабатываем входные данные пользователя, но и обеспечиваем безопасность сессий. Важно понимать, что каждое изменение здесь влияет на общую стабильность системы."

        ### Назначение файла
        Краткое описание на русском языке (1-2 предложения), объясняющее основную цель и роль файла в контексте проекта. Например: "Этот файл отвечает за маршрутизацию HTTP-запросов", "Здесь реализована бизнес-логика для обработки заказов", "Этот модуль содержит утилитарные функции для работы с датами".

        ### Основные компоненты
        - **Классы**: Список названий классов, определенных в файле, с очень кратким описанием каждого.
        - **Функции/Методы**: Список названий функций или методов, определенных в файле, с очень кратким описанием каждого.
        - **Переменные/Константы**: Список ключевых глобальных переменных или констант, определенных в файле, с очень кратким описанием.

        ### Зависимости
        Список внешних библиотек, модулей или фреймворков, которые импортируются или используются в файле.

        ### Дополнительная информация
        Любая другая полезная информация, например, паттерны проектирования, особенности реализации, потенциальные проблемы или важные комментарии.

        ---
        Файл: {file_info["path"]}
        Язык: {file_info["language"]}
        Содержимое файла:
        ```{file_info["language"].lower().replace(' ', '')}
        {{chunk_content}}
        ```
        """
        
        max_chunk_size = 5000
        content = file_info["content"]
        chunks = [content[i:i+max_chunk_size] for i in range(0, len(content), max_chunk_size)]
        
        analysis_results = []
        combine_message = None # Initialize combine_message
        for i, chunk in enumerate(chunks):
            # Сообщение о прогрессе будет обрабатываться run_with_loading_animation
            chunk_prompt = prompt_template.replace("{{chunk_content}}", chunk)
            analysis = self.analyze_with_llm(chunk_prompt, f"анализ файла {file_info['path']} (часть {i+1}/{len(chunks)})")
            if analysis:
                analysis_results.append(analysis)
            else:
                print(f"Не удалось получить анализ для части {i+1} файла {file_info['path']}")
        
        if len(analysis_results) > 1:
            combine_message = f"Объединяем {len(analysis_results)} частей анализа для {file_info['path']}"
            combine_prompt = f"""
            Ты получил несколько частей анализа одного и того же файла. Объедини их в единый связный анализ, 
            сохраняя структуру: "Назначение файла", "Основные компоненты", "Зависимости", "Дополнительная информация".
            **Особое внимание удели основной ЦЕЛИ и РОЛИ этого файла в контексте всего проекта, как будто ты объясняешь это новому члену команды.**
            **Избегай любых формулировок, которые могли бы намекнуть на то, что текст сгенерирован ИИ. Пиши естественно, как человек.**
            Убедись, что информация не дублируется и представлена лаконично.

            Части анализа:
            {chr(10).join(analysis_results)}
            """
            file_info["analysis"] = self.analyze_with_llm(combine_prompt, f"объединение анализа для {file_info['path']}")
        elif analysis_results:
            file_info["analysis"] = analysis_results[0]
        else:
            file_info["analysis"] = "Не удалось получить анализ файла."
            
        file_info["_combine_message"] = combine_message # Store message in file_info
        return file_info # Only return file_info

    def generate_readme(self, repo_info: Dict) -> str:
        """
        Генерирует полный README.md на основе анализа репозитория.

        Args:
            repo_info (Dict): Словарь с полной информацией о репозитории.

        Returns:
            str: Сгенерированное содержимое README.md в формате Markdown.
        """
        print("Начинаем анализ файлов для генерации README...")
        total_files = len(repo_info["files"])
        for i, file_info in enumerate(repo_info["files"]):
            # Прогресс будет отображаться в run_with_loading_animation
            file_info = self.analyze_file(file_info)
            repo_info["files"][i] = file_info 
            
        github_user = ""
        github_repo_name = ""
        if "github.com" in repo_info["remote_url"]:
            try:
                parsed_url = urlparse(repo_info["remote_url"])
                path_parts = [part for part in parsed_url.path.split('/') if part]
                if len(path_parts) >= 2:
                    github_user = path_parts[-2]
                    github_repo_name = path_parts[-1].replace('.git', '')
            except IndexError:
                pass

        # Определяем JSON-схему для ожидаемого ответа от LLM
        response_schema = {
            "type": "OBJECT",
            "properties": {
                "project_description": {"type": "STRING", "description": "Краткое, цепляющее описание проекта. 1-2 предложения."},
                "project_overview_content": {"type": "STRING", "description": "Подробный обзор проекта, его целей и архитектуры. Не менее 3-4 предложений."},
                "features_content": {"type": "STRING", "description": "Список ключевых функций и возможностей проекта в виде маркированного списка. Каждый пункт должен быть на русском языке."},
                "technologies_content": {"type": "STRING", "description": "Список основных технологий, языков программирования и фреймворков, использованных в проекте, в виде маркированного списка. Каждый пункт должен быть на русском языке."},
                "installation_content": {"type": "STRING", "description": "Подробные инструкции по установке и запуску проекта. Включите команды для клонирования, установки зависимостей (примеры для pip, npm) и запуска. Используйте блоки кода Markdown."},
                "usage_examples_content": {"type": "STRING", "description": "Практические примеры использования проекта. Включите фрагменты кода или сценарии, демонстрирующие основной функционал. Используйте блоки кода Markdown."},
                "project_structure_description": {"type": "STRING", "description": "Краткое вводное описание логики структуры проекта. Не более 2-3 предложений."}
            },
            "required": [
                "project_description",
                "project_overview_content",
                "features_content",
                "technologies_content",
                "installation_content",
                "usage_examples_content",
                "project_structure_description"
            ]
        }

        # Инструкции для LLM, чтобы он генерировал JSON
        llm_prompt_for_sections = f"""
        Ты - опытный тимлид и главный архитектор проекта. Твоя задача - сгенерировать контент для различных секций README.md.
        Сгенерируй JSON-объект, строго соответствующий следующей схеме. Все текстовые поля должны быть на русском языке.
        Будь максимально полезным и информативным, как будто ты объясняешь проект новому члену команды.
        Избегай любых формулировок, которые могли бы намекнуть на то, что текст сгенерирован ИИ. Пиши естественно, как человек.

        Информация о проекте для анализа:
        Название репозитория: {repo_info["name"]}
        URL репозитория: {repo_info["remote_url"]}
        Основные языки (по количеству файлов): {', '.join(repo_info["language_stats"].keys()) if repo_info["language_stats"] else "Не определены"}
        Последний коммит:
            Сообщение: {repo_info["last_commit"].get("message", "неизвестно")}
            Автор: {repo_info["last_commit"].get("author", "неизвестно")}
            Дата: {repo_info["last_commit"].get("date", "неизвестно")}

        Анализ ключевых файлов (используй эту информацию для формирования разделов):
        {self._format_files_analysis(repo_info["files"])}

        ---
        Сгенерируй JSON-объект, содержащий контент для секций README.md, согласно предоставленной схеме.
        """
        
        print("Запрашиваем контент секций README у LLM...")
        json_content_str = self.analyze_with_llm(llm_prompt_for_sections, "контент секций README", 
                                                 response_mime_type="application/json", response_schema=response_schema)
        
        try:
            generated_sections = json.loads(json_content_str)
        except json.JSONDecodeError as e:
            print(f"Ошибка декодирования JSON ответа от LLM: {e}")
            print(f"Полученный ответ: {json_content_str}")
            # В случае ошибки декодирования, используем пустые строки для секций
            generated_sections = {
                "project_description": "Не удалось сгенерировать описание проекта.",
                "project_overview_content": "Не удалось сгенерировать обзор проекта.",
                "features_content": "Не удалось сгенерировать функциональные возможности.",
                "technologies_content": "Не удалось сгенерировать технологический стек.",
                "installation_content": "Не удалось сгенерировать инструкции по установке.",
                "usage_examples_content": "Не удалось сгенерировать примеры использования.",
                "project_structure_description": "Не удалось сгенерировать описание структуры проекта."
            }

        # Сам шаблон README
        readme_template_content = f"""
<p align="center"><img src="https://i.gifer.com/GwyA.gif" width="200"/></p>
<h3 align="center">check out my channels</h3>
<div id="badges" align="center">
    <a href="http://t.me/+13262155064">
        <img src="https://w7.pngwing.com/pngs/1/41/png-transparent-telegram-button-icon.png" alt="telegram Badge" height="30px"/>
    </a>
    <a href="https://www.youtube.com/@Mr.Helperus">
        <img src="https://img.shields.io/badge/YouTube-red?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube Badge"/>
    </a>
    <a href="https://www.tiktok.com/@4elobrek9_original">
        <img src="https://w7.pngwing.com/pngs/262/918/png-transparent-tiktok-button-icon.png" alt="TikTok Badge" height="30px" />
    </a>
    <a href="https://discord.gg/qsvPPE9YvJ">
        <img src="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTl21OxPjOzA5qABz2Hle_7SoOxtIoOOsHXBQ&s" alt="Discord Badge" height="35px"/>
    </a>
</div>
</p>
<p align="center"><img src="https://komarev.com/ghpvc/?username=4elobre9&style=flat-square&color=blue" alt=""></p>
<h1 align="center">読者の皆さん、こんにちは。 <img src="https://media.giphy.com/media/hvRJCLFzcasrR4ia7z/giphy.gif" width="40"></h1>
<p align="center"><img src="https://cdna.artstation.com/p/assets/images/images/028/102/058/original/pixel-jeff-matrix-s.gif?1593487263" width="600" height="300" /></p>

### :woman_technologist: About Me :
Я Full Stack разработчик.
- 🔱 Я работаю инженером-программистом и вношу свой вклад во фронтенд для создания веб-приложений. <img src="h" alt="" height="20px" />
- ⚙️ Я пишу ботов для Discord и их бэкенд-примеры на своем Discord сервере. <a href="https://discord.gg/qsvPPE9YvJ">
        <img src="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTT4je-CowV-arhhLNwE84rd___C9IiS1-gHPxB_mM1oqbsAJEeX71iH5QHBZ28EhFhf68&usqp=CAU" alt="" height="20px" />
    </a>
- ⚡ В свободное время я решаю задачи на GeeksforGeeks и прокачиваю свой мозг.

---

# {repo_info["name"]}
<p>
"""
        # Добавляем иконки для обнаруженных языков в начало README
        devicon_map = {
            'Python': 'https://github.com/devicons/devicon/blob/master/icons/python/python-original.svg?raw=true',
            'JavaScript': 'https://github.com/devicons/devicon/blob/master/icons/javascript/javascript-original.svg?raw=true',
            'TypeScript': 'https://github.com/devicons/devicon/blob/master/icons/typescript/typescript-original.svg?raw=true',
            'Java': 'https://github.com/devicons/devicon/blob/master/icons/java/java-original-wordmark.svg?raw=true',
            'Go': 'https://github.com/devicons/devicon/blob/master/icons/go/go-original.svg?raw=true',
            'Rust': 'https://github.com/devicons/devicon/blob/master/icons/rust/rust-plain.svg?raw=true',
            'Ruby': 'https://github.com/devicons/devicon/blob/master/icons/ruby/ruby-original.svg?raw=true',
            'PHP': 'https://github.com/devicons/devicon/blob/master/icons/php/php-original.svg?raw=true',
            'HTML': 'https://github.com/devicons/devicon/blob/master/icons/html5/html5-original.svg?raw=true',
            'CSS': 'https://github.com/devicons/devicon/blob/master/icons/css3/css3-plain-wordmark.svg?raw=true',
            'React JSX': 'https://github.com/devicons/devicon/blob/master/icons/react/react-original.svg?raw=true',
            'Vue.js': 'https://github.com/devicons/devicon/blob/master/icons/vuejs/vuejs-original.svg?raw=true',
            'NodeJS': 'https://github.com/devicons/devicon/blob/master/icons/nodejs/nodejs-original.svg?raw=true',
            'MySQL': 'https://github.com/devicons/devicon/blob/master/icons/mysql/mysql-original-wordmark.svg?raw=true',
            'Git': 'https://github.com/devicons/devicon/blob/master/icons/git/git-original-wordmark.svg?raw=true',
            'Spring': 'https://github.com/devicons/devicon/blob/master/icons/spring/spring-original-wordmark.svg?raw=true',
            'Material UI': 'https://github.com/devicons/devicon/blob/master/icons/materialui/materialui-original.svg?raw=true',
            'Flutter': 'https://github.com/devicons/devicon/blob/master/icons/flutter/flutter-original.svg?raw=true',
            'Redux': 'https://github.com/devicons/devicon/blob/master/icons/redux/redux-original.svg?raw=true',
            'Gatsby': 'https://github.com/devicons/devicon/blob/master/icons/gatsby/gatsby-original.svg?raw=true',
            'AWS': 'https://github.com/devicons/devicon/blob/master/icons/amazonwebservices/amazonwebservices-plain-wordmark.svg?raw=true',
            'Postman': 'https://www.vectorlogo.zone/logos/getpostman/getpostman-icon.svg',
        }
        for lang, count in repo_info["language_stats"].items():
            if lang in devicon_map:
                readme_template_content += f'<img src="{devicon_map[lang]}" title="{lang}" alt="{lang}" width="40" height="40"/> '
        readme_template_content += '\n</p>\n\n'

        # Добавляем бейджи проекта
        if github_user and github_repo_name:
            readme_template_content += f"""
![GitHub repo size](https://img.shields.io/github/repo-size/{github_user}/{github_repo_name})
![GitHub last commit](https://img.shields.io/github/last-commit/{github_user}/{github_repo_name})
![GitHub top language](https://img.shields.io/github/languages/top/{github_user}/{github_repo_name})
"""
        readme_template_content += f"""
        
{generated_sections.get("project_description", "Краткое описание проекта не сгенерировано.")}

## Содержание

- [Описание](#описание)
- [Функциональные возможности](#функциональные-возможности)
- [Технологический стек](#технологический-стек)
- [Установка](#установка)
- [Примеры использования](#примеры-использования)
- [Лицензия](#лицензия)
- [Контакты](#контакты)

## Описание
{generated_sections.get("project_overview_content", "Обзор проекта не сгенерирован.")}

## Функциональные возможности
{generated_sections.get("features_content", "Функциональные возможности не сгенерированы.")}

## Технологический стек
{generated_sections.get("technologies_content", "Технологический стек не сгенерирован.")}

## Установка
{generated_sections.get("installation_content", "Инструкции по установке не сгенерированы.")}

## Примеры использования
{generated_sections.get("usage_examples_content", "Примеры использования не сгенерированы.")}

## Структура проекта
{generated_sections.get("project_structure_description", "Описание структуры проекта не сгенерировано.")}
{{project_structure_content}}

## Вклад
{{contributing_content}}

## Лицензия
{{license_content}}

## Контакты
- **TELEGRAM**: [4elobrek9](http://t.me/+13262155064)
- **GitHub**: [4elobrek9](https://github.com/4elobrek9)
- **Discord**: [qsvPPE9YvJ](https://discord.gg/qsvPPE9YvJ)
- **TikTok**: [4elobrek9_original](https://www.tiktok.com/@4elobrek9_original)

---

### 🔥 My Stats :
[![Top Langs](https://github-readme-stats.vercel.app/api/top-langs/?username=4elobre9&layout=compact&theme=vision-friendly-dark)](https://github.com/anuraghazra/github-readme-stats)

---

### ✍️ Blog Posts : 
- [Help me understand this software. I wrote it in delirium](https://github.com/4elobrek9/JARVIS)

---

Спасибо за внимание! Надеюсь, вы найдете этот репозиторий полезным!
<p align="center"><img src="https://media.giphy.com/media/LnQJEfWOk1Zprd6IA/giphy.gif" width="50"></p>
"""
        
        final_readme = self._postprocess_readme(readme_template_content, repo_info)
        
        return final_readme

    def _format_files_analysis(self, files: List[Dict]) -> str:
        """
        Форматирует анализ файлов для включения в промпт генерации README.

        Args:
            files (List[Dict]): Список словарей с информацией о файлах и их анализом.

        Returns:
            str: Отформатированная строка с анализом файлов.
        """
        formatted = []
        for file in files:
            if file["analysis"] and file["analysis"] != "Не удалось получить анализ файла.":
                formatted.append(f"### Файл: `{file['path']}`\nЯзык: {file['language']}\n\n{file['analysis']}\n")
        return "\n".join(formatted) if formatted else "Анализ файлов недоступен."

    def _postprocess_readme(self, content: str, repo_info: Dict) -> str:
        """
        Постобработка сгенерированного README.
        Убеждается, что все части шаблона присутствуют и заполнены на русском языке.
        """
        final_readme = content

        # Структура проекта генерируется автоматически, поэтому для нее не нужна заглушка LLM
        if "{{project_structure_content}}" in final_readme:
            project_structure_str = "```\n"
            for root, dirs, files in os.walk(self.repo_path):
                level = root.replace(self.repo_path, '').count(os.sep)
                indent = ' ' * 4 * (level)
                project_structure_str += f'{indent}{os.path.basename(root)}/\n'
                subindent = ' ' * 4 * (level + 1)
                for f in files:
                    if f not in self.ignore_files:
                        project_structure_str += f'{subindent}{f}\n'
            project_structure_str += "```\n"
            final_readme = final_readme.replace("{{project_structure_content}}", project_structure_str)
        
        if "{{contributing_content}}" in final_readme:
            final_readme = final_readme.replace("{{contributing_content}}", """Мы приветствуем вклад в этот проект! Если вы хотите внести свой вклад, пожалуйста, следуйте этим рекомендациям:
<ol>
    <li>Форкните репозиторий.</li>
    <li>Создайте новую ветку для ваших изменений: <code>git checkout -b feature/your-feature-name</code></li>
    <li>Внесите свои изменения и закоммитьте их: <code>git commit -m "Add new feature"</code></li>
    <li>Отправьте изменения в свой форк: <code>git push origin feature/your-feature-name</code></li>
    <li>Создайте Pull Request.</li>
</ol>
Мы всегда рады новым идеям и помощи в развитии проекта!""")
        
        if "{{license_content}}" in final_readme:
            license_file_found = False
            for file in repo_info["files"]:
                if file["path"].lower() == "license":
                    final_readme = final_readme.replace("{{license_content}}", f"Этот проект лицензирован под лицензией, указанной в файле [`{file['path']}`]({repo_info['remote_url']}/blob/main/{file['path']}).")
                    license_file_found = True
                    break
            if not license_file_found:
                final_readme = final_readme.replace("{{license_content}}", "Этот проект лицензирован под лицензией MIT. Подробности можно найти в файле [LICENSE](LICENSE).") # Предлагаем MIT по умолчанию

        return final_readme

    def save_readme(self, content: str, output_path: str = "README.md"):
        """
        Сохраняет сгенерированное содержимое README.md в указанный файл.

        Args:
            content (str): Содержимое README.md.
            output_path (str): Путь для сохранения файла.
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"\nREADME.md успешно сохранён в {output_path}")
        except Exception as e:
            print(f"\nОшибка при сохранении README.md в {output_path}: {e}")

# --- Функции для консольной анимации ---
def run_with_loading_animation(func, *args, **kwargs):
    """
    Запускает функцию, отображая при этом консольную анимацию загрузки.
    """
    messages = [
        "Инициализируем репозиторий...",
        "Сканируем файлы проекта...",
        "Подсчитывает котят в репозитории...",
        "Отправляем запрос нейросети...",
        "Готовит план по захвату человечества...",
        "Обдумывает причины этого не делать...",
        "Анализируем структуру проекта...",
        "Читаем мысли разработчиков...",
        "Собираем информацию о файлах...",
        "Ищет мотивацию для работы...",
        "Формируем промпт для LLM...",
        "Переводит код на язык единорогов...",
        "Ожидает ответа от Ollama...",
        "Генерирует умные мысли...",
        "Полирует markdown разметку...",
        "Проверяет наличие печенек...",
        "Составляет список зависимостей...",
        "Пишет секцию 'Обо мне' для README...",
        "Добавляет бейджики и гифки...",
        "Убеждается, что код не сломает продакшн...",
        "Финальные штрихи...",
        "Почти готово! Держитесь...",
        "Гладит собаку...",
        "Размышляет о смысле жизни...",
        "Проверяет, не забыли ли чего-нибудь...",
        "Наводит порядок в байтах...",
        "Заваривает кофе для себя...",
        "Рисует ASCII-арт...",
        "Оптимизирует неоптимизируемое...",
        "Ищет потерянные биты...",
        "Думает о завтрашнем дне...",
        "Завершает последние штрихи...",
        "Проверяет, не сбежал ли код...",
        "Ищет баги под диваном...",
        "Пытается понять почерк разработчика...",
        "Пересчитывает все запятые...",
        "Медитирует над алгоритмами...",
        "Готовится к следующему запросу...",
        "Заряжает батарейки...",
        "Думает о пицце...",
        "Расшифровывает мысли пользователя...",
        "Улыбается и машет...",
        "Проверяет, все ли коты на месте...",
        "Обновляет базу данных анекдотов...",
        "Размышляет о квантовой механике...",
        "Ищет идеальный шрифт...",
        "Перебирает варианты названий...",
        "Планирует мировой тур...",
        "Считает звезды...",
        "Отправляет телепатические сигналы...",
        "Занимается йогой..."
    ]
    
    total_steps = 100 # Прогресс от 0 до 100
    current_step = 0.0 # Используем float для более плавного прогресса
    
    # Запускаем функцию в отдельном потоке, чтобы не блокировать UI
    result = [None] # Используем список для передачи результата из потока
    exception: List[Optional[Exception]] = [None] # Явно указываем тип для Pylance

    def target_func():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=target_func)
    thread.start()

    # Получаем ширину терминала для корректной очистки строки
    try:
        terminal_width = os.get_terminal_size().columns
    except OSError:
        terminal_width = 80 # Заглушка, если не удалось определить ширину

    while True:
        if not thread.is_alive():
            # Если поток завершился, быстро доводим прогресс до 100%
            if current_step < total_steps:
                current_step = total_steps # Сразу ставим 100%
                message = "Готово!"
            else:
                break # Выходим из цикла, когда 100% достигнуто и поток завершен
        else:
            # Пока поток работает, прогресс идет до 99%
            if current_step < 50:
                progress_increment = random.uniform(1.0, 3.0) # Быстрее в начале
            elif current_step < 90:
                progress_increment = random.uniform(0.5, 1.5) # Умеренно
            else: # current_step >= 90
                progress_increment = random.uniform(0.1, 0.5) # Очень медленно в конце
            
            current_step = min(current_step + progress_increment, 99.0) # Никогда не достигаем 100% пока поток жив
            message = random.choice(messages)
        
        bar_length = 40
        filled_length = int(bar_length * current_step / total_steps)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        
        # Очищаем всю строку перед записью
        sys.stdout.write('\r' + ' ' * terminal_width + '\r') 
        sys.stdout.write(f'[{bar}] {int(current_step):3}% {message}')
        sys.stdout.flush()
        
        time.sleep(0.2) # Увеличена задержка для более медленной анимации

    thread.join() # Ждем завершения потока

    if exception[0]:
        # Очищаем строку перед выводом сообщения об ошибке
        sys.stdout.write('\r' + ' ' * terminal_width + '\r')
        sys.stdout.flush()
        raise exception[0]
    
    sys.stdout.write('\r' + ' ' * terminal_width + '\r') # Окончательно очищаем строку прогресса
    sys.stdout.flush()
    return result[0]

if __name__ == "__main__":
    print("Добро пожаловать в Генератор README.md!")
    print("Для работы скрипта убедитесь, что у вас установлен и запущен Ollama,")
    print("и что модель 'saiga' (или выбранная вами) загружена.")
    print("Например, запустите в терминале: ollama run saiga")
    print("-" * 50)

    repo_path_input = input("Пожалуйста, введите URL Git репозитория (например, https://github.com/user/repo.git): ")
    
    # Опциональные параметры с разумными значениями по умолчанию
    # output_path = input("Введите путь для сохранения README.md (по умолчанию: README.md) или нажмите Enter: ") or 'README.md'
    model_name = input("Введите имя модели Ollama (по умолчанию: saiga) или нажмите Enter: ") or 'saiga'
    ollama_url = input("Введите URL-адрес API Ollama (по умолчанию: http://localhost:11434/api/generate) или нажмите Enter: ") or 'http://localhost:11434/api/generate'

    documenter = None 
    try:
        # Инициализация Documenter обернута анимацией
        documenter = run_with_loading_animation(RepositoryDocumenter, repo_path_input, model_name, ollama_url)
        
        # Если инициализация репозитория прошла успешно, продолжаем
        if documenter is not None and documenter.repo: # Добавлена проверка documenter is not None
            # Имя репозитория теперь корректно извлекается в get_repo_info
            repo_info = run_with_loading_animation(documenter.get_repo_info)
            
            # Выводим имя репозитория, полученное из get_repo_info
            print(f"\nАнализируем репозиторий: {repo_info['name']}") 
            print(f"Найдено файлов: {len(repo_info['files'])}")
            print(f"Основные языки: {', '.join(repo_info['language_stats'].keys()) if repo_info['language_stats'] else 'Не определены'}")
            
            # Определяем путь для сохранения README с именем репозитория
            repo_name_for_file = repo_info['name'].replace(' ', '_').replace('/', '_').replace('\\', '_') # Очистка для имени файла
            output_path = f"README_FOR_{repo_name_for_file}.md"
            print(f"README.md будет сохранён как: {output_path}")

            print("\nНачинаем генерацию README.md. Это может занять некоторое время...")
            # Генерация README обернута анимацией
            readme_content = run_with_loading_animation(documenter.generate_readme, repo_info)
            documenter.save_readme(readme_content, output_path)
        else:
            print("\nНе удалось инициализировать репозиторий. Проверьте URL или путь.")

    except Exception as e:
        print(f"\nПроизошла критическая ошибка: {e}")
    finally:
        if documenter:
            documenter.cleanup()
