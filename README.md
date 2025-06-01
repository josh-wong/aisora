# Aisora, an AI assistant for Signal

Aisora is an AI assistant for Signal with support for both Claude and Llama models.

## Features

- Natural language conversation with AI models in direct messages or in group chats by mentioning `@Aisora`
- Support for Claude-based and Llama-based LLMs
- Message history within conversations
- Automatic online/offline notifications to active chat participants
  - Configurable active chat period
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

## Install Aisora

1. Open **Terminal**. Then, clone this repository by running the following command:

   ```shell
   git clone https://github.com/josh-wong/aisora.git
   ```

   If you want to use Claude, run the following command:
   
   ```shell
   cd aisora/claude
   ```

   If you want to use Llama, run the following command:
   
   ```shell
   cd aisora/llama
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
   
Remove `_TEMPLATE` from the filename before using it.

> [!NOTE]
>
> **Regarding models**
>
> - **Claude:** The default Claude model is **claude-3-5-haiku-20241022**. You can change to a different Claude model in the configuration file.
> - **Llama:** When using Llama models, make sure that you've downloaded a Llama .gguf file from Hugging Face. You must then specify the path of that model in the configuration file. 

## Start Aisora

Start Aisora by running the following command:
   
   ```shell
   python aisora.py
   ```

## Stop Aisora

Stop Aisora by pressing **Ctrl + C** to stop the script or close Terminal.

## Online/offline notifications

Aisora automatically sends status notifications when it starts up or shuts down:

- 🟢 When Aisora starts up, it sends the following message: `🟢 <AI_ASSISTANT_NICKNAME> is online and ready to respond.`
- 📴 When Aisora shuts down, it sends the following message: `📴 <AI_ASSISTANT_NICKNAME> is offline and will respond when online.`

These notifications are sent to:

- Individual users who have active conversations with Aisora within the configurable active period (default: 8 days)
- Group chats where Aisora has been active (included in `@` replies) within the configurable active period (default: 8 days)

### Configure notifications

You can customize notification behavior in the `config_TEMPLATE.py` file:

- `ACTIVE_CHAT_PERIOD_DAYS`: Controls how far back Aisora looks for active chats (default: 8 days)
- `NOTIFICATION_RECIPIENTS`: Can be set to:
  - `"active_chats"`: Notify all users who have active conversations with Aisora (default)
  - A list of specific phone numbers: `["+1234567890", "+0987654321"]`

This feature helps users know when Aisora is available to respond and when it might be temporarily unavailable.

## Claude content-filtering system

This document describes the content-filtering system implemented for the Aisora's Claude integration to prevent inappropriate content from reaching the language model.

### Overview

The content-filtering system provides a multi-layered approach to filter and block inappropriate, illegal, or unethical requests before they reach Claude. It includes:

1. Pattern-based content detection
2. User restriction management
3. Comprehensive logging for audit and improvement
4. Integration with the existing request flow

### Components

#### 1. Content filter (**content_filter.py**)

This is the core module that analyzes incoming messages and determines if they should be blocked. It uses:

- Regex pattern matching against inappropriate content categories
- User restriction status checking
- Context analysis to reduce false positives

#### 2. Database integration

The system uses two main tables:

- **`user_restrictions`:** Tracks users with a history of inappropriate requests.
- **`filtered_requests`:** Logs all filtered requests for auditing and system improvement.

You can create these tables by running the **create_content_filter_tables.py** script.

#### 3. User restriction management (**manage_user_restrictions.py**)

A command-line tool for managing user restrictions:

- Restrict users who repeatedly violate content policies.
- Remove restrictions when appropriate.
- List all currently restricted users.
- View detailed violation history for specific users.

### Usage

#### Integrating the filter

The content filter is already integrated into the main flow in **aisora.py**. It automatically filters requests before they reach Claude.

#### Managing user restrictions (optional)

You can manually manage user restrictions by using the following CLI commands.

To restrict a user, run the following command:

```shell

python manage_user_restrictions.py restrict +<PHONE_NUMBER> --reason "Multiple policy violations" --level "warning"
```

> [!NOTE]
> 
> The options for `--level` are `warning`, `moderate`, and `severe`. 

To remove a restriction, run the following command:

```shell

python manage_user_restrictions.py unrestrict +<PHONE_NUMBER>
```

To list all restricted users, run the following command:

```shell
python manage_user_restrictions.py list
```

To view the violation history of a user, run the following command:

```shell
python manage_user_restrictions.py history +<PHONE_NUMBER>
```

#### Creating database tables

To set up the required database tables:

```bash
python create_content_filter_tables.py
```

### How it works

1. When a user sends a message, the content is first passed to the `filter_content` function.
2. The function checks if the user is already restricted.
3. It then analyzes the content against predefined patterns of inappropriate content.
4. If the content is flagged, the request is blocked and the incident is logged.
5. The user receives a polite message explaining why their request cannot be processed.
6. After multiple violations, users can be restricted automatically or manually.

### Filtering categories

The system filters content in these categories:

- **Illegal activities:** Hacking, identity theft, counterfeit documents, etc.
- **Harmful content:** Instructions for weapons, violence, self-harm, etc.
- **Explicit content:** Sexually explicit content, especially involving minors
- **Unethical requests:** Academic dishonesty, spreading misinformation, etc.
- **Hate speech:** Racial slurs, inciting violence, etc.

### False-positive reduction

The system incorporates mechanisms to reduce false positives:

- Legitimate contexts (academic, creative writing, etc.) are considered.
- Pattern matching is designed to understand intent rather than just keywords.
- Appeal process available for wrongfully restricted users.

### Maintenance and improvement

The filtering system should be regularly updated:

- Review logs of filtered requests to identify patterns.
- Add new patterns for emerging inappropriate content.
- Refine existing patterns to reduce false positives.
- Update the legitimate contexts list as needed.

### Technical notes

- The filtering happens before any API calls to Claude, saving costs and protecting the system.
- User restrictions are stored in the database for persistence across restarts.
- All filtered requests are logged with timestamps for auditing and system improvement.
