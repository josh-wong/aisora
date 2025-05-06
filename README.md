# Claugnal

Claugnal is a Claude-based AI assistant for Signal.

## Features

- Natural language conversation with a Claude-based LLM in direct messages or in group chats by mentioning @Claugnal
- Message history within conversations
- Logging of user data.

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

## Install Claugnal

1. Open **Terminal**. Then, clone this repository by running the following command:

   ```shell
   git clone https://github.com/josh-wong/claugnal.git
   cd claugnal
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

2. Create the database by running the following command:

   ```sql
   CREATE DATABASE claugnal;
   ```

3. Exit PostgreSQL by running the following command:

   ```sql
   \q
   ```

4. Create the query_log table by running the following command:

   ```shell
   psql -U username -d claugnal -f setup_database.sql
   ```

## Configure Claugnal

Open **config_TEMPLATE.py**, and edit the following configurations as described in the configuration file:

   - `ANTHROPIC_API_KEY`
   - `DB_CONFIG`
   - `SIGNAL_NUMBER`
   - `SYSTEM_PROMPT`
   
   > [!IMPORTANT]
   >
   > Be sure to remove "_TEMPLATE" from the filename before using it.

   
   > [!NOTE]
   >
   > The default Claude model that Claugnal uses **claude-3-5-haiku-20241022**. You can change to a different Claude model in the configuration file.
   >
   > In addition, you can set `max_tokens` and `temperature` to different values, according to your needs.

## Start Claugnal

Start Claugnal by running the following command:
   
   ```shell
   python chatbot.py
   ```

## Stop Claugnal

Stop Claugnal by pressing **Ctrl + C** to stop the script or close Terminal.
