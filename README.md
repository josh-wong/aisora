# Aisora, an AI assistant for Signal

Aisora is an AI assistant for Signal with support for both Claude and Llama models.

## Features

- Natural language conversation with AI models in direct messages or in group chats by mentioning @Aisora
- Support for Claude-based and Llama-based LLMs
- Message history within conversations
- Logging of user data

## Maintenance support policy

Major, minor, and patch versions are supported only until the latest version is released. For example, when version 0.2.0 is released, version 0.1.0 will no longer be supported. Then, if version 0.2.1 is released, version 0.2.0 will no longer be supported.

> [!NOTE]
>
> Although this is neither standard nor best practice as a support policy, it has been adopted for ease of maintenance.

## Prerequisites

- Python 3.11 or later
- PostgreSQL database
- Signal Desktop application
- Anthropic API key (for Claude access)
- Ollama installation (for Llama models access)

## Install Aisora

1. Open **Terminal**. Then, clone this repository by running the following command:

   ```shell
   git clone https://github.com/josh-wong/aisora.git
   ```

   If you want to use Claude, run the following command:
   
   ```shell
   cd claude/aisora
   ```

   If you want to use Llama, run the following command:
   
   ```shell
   cd llama/aisora
   ```

2. Install the Python dependencies by running the following command:

   ```shell
   pip install -r requirements.txt
   ```

## Create the PostgreSQL database

1. Log in to your PostgreSQL instance as a PostgreSQL superuser by running the following command:

   ```shell
   sudo -u postgres psql
   ```

2. Create the database.

   If you're using Claude, run the following command:

   ```sql
   CREATE DATABASE aisora_claude;
   ```

   If you're using Llama, run the following command:

   ```sql
   CREATE DATABASE aisora_llama;
   ```

3. Exit PostgreSQL by running the following command:

   ```sql
   \q
   ```

4. Create the `query_log` table.

   If you're using Claude, run the following command:

   ```shell
   psql -U username -d aisora_claude -f setup_database.sql
   ```

   If you're using Llama, run the following command:
   
   ```shell
   psql -U username -d aisora_llama -f setup_database.sql
   ```

## Configure Aisora

Open **config_TEMPLATE.py**, and edit the following configurations as described in the configuration file:

   - `ANTHROPIC_API_KEY`
   - `DB_CONFIG`
   - `SIGNAL_NUMBER`
   - `SYSTEM_PROMPT`
   - `windows_model_path` (for Llama models only)
   
   > [!IMPORTANT]
   >
   > Be sure to remove "_TEMPLATE" from the filename before using it.

   
   > [!NOTE]
   >
   > The default Claude model is **claude-3-5-haiku-20241022**. You can change to a different Claude model in the configuration file.
   >
   > When using Llama models, make sure that you've downloaded a Llama .gguf file from Hugging Face. You must then specify the path of that model in the configuration file.

## Start Aisora

Start Aisora by running the following command:
   
   ```shell
   python aisora.py
   ```

## Stop Aisora

Stop Aisora by pressing **Ctrl + C** to stop the script or close Terminal.
