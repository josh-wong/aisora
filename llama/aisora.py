# This script is designed to run indefinitely, listening for incoming messages and responding as needed.
import subprocess
import json
import time
import os
import signal
import psutil
import uuid
import re
import traceback
from llama_cpp import Llama
import atexit
from config import AI_CONFIG, LLAMA_MODEL_PATH, SIGNAL_CONFIG, USAGE_CONFIG, SYSTEM_PROMPT
from db_utils import log_conversation, get_recent_conversation_history, get_db_connection
from psycopg2.extras import RealDictCursor
from location_utils import get_location_from_phone_number, clear_location_cache

# Extract commonly used configuration variables.
USE_LLAMA = AI_CONFIG['use_llama']
MODEL_CONFIG = AI_CONFIG['model']
SIGNAL_NUMBER = SIGNAL_CONFIG['phone_number']
AI_ASSISTANT_NICKNAME = SIGNAL_CONFIG['assistant_nickname']
NOTIFICATION_RECIPIENTS = SIGNAL_CONFIG['notification_recipients']
ACTIVE_CHAT_PERIOD_DAYS = SIGNAL_CONFIG['active_chat_period_days']
USAGE_LIMITS_ENABLED = USAGE_CONFIG['enabled']
DEFAULT_DAILY_MESSAGE_LIMIT = USAGE_CONFIG['daily_message_limit']
LIMIT_WARNING_THRESHOLD = USAGE_CONFIG['warning']['threshold']
LIMIT_WARNING_MESSAGE = USAGE_CONFIG['warning']['message']
LIMIT_REACHED_MESSAGE = USAGE_CONFIG['limit_reached_message']

# Function to extract the  model name from the model file path.
def get_model_name_from_path():
    """Extract a clean model name from the LLAMA_MODEL_PATH"""
    try:
        # Extract the filename from the path.
        filename = os.path.basename(LLAMA_MODEL_PATH)
        
        # Remove the file extension.
        if filename.endswith('.gguf'):
            filename = filename[:-5]
        
        # Remove any hyphens.
        clean_name = filename.replace('-', ' ')
        
        # Make it more readable with proper capitalization.
        # Handle specific known model names.
        if 'llama' in clean_name.lower():
            # For Llama models, capitalize the "L" in Llama.
            parts = clean_name.split()
            for i, part in enumerate(parts):
                if 'llama' in part.lower():
                    parts[i] = part.replace('llama', 'Llama')
            clean_name = ' '.join(parts)
        
        return clean_name
    except Exception as e:
        print(f"Error extracting model name from path: {e}")
        return "Llama model" # Default fallback name.

# Set an environment variable to enable IP-based location fallback.
os.environ['ALLOW_IP_FALLBACK'] = 'true'

llama_model = None

# Initialize the Llama model.
if USE_LLAMA:
    try:
        print(f"Loading Llama model from {LLAMA_MODEL_PATH}")
        print(f"Using GPU configuration: {MODEL_CONFIG}")
        
        # Extract the GPU-specific settings from MODEL_CONFIG.
        gpu_params = {
            'n_ctx': MODEL_CONFIG.get('context_window'),
            'n_batch': MODEL_CONFIG.get('n_batch'),
            'n_gpu_layers': MODEL_CONFIG.get('n_gpu_layers'),
            'offload_kqv': MODEL_CONFIG.get('offload_kqv'),
            'main_gpu': MODEL_CONFIG.get('main_gpu'),
            'tensor_split': MODEL_CONFIG.get('tensor_split'),
            'verbose': MODEL_CONFIG.get('verbose')
        }
        
        llama_model = Llama(
            model_path=LLAMA_MODEL_PATH,
            **gpu_params
        )
        print("Llama model loaded successfully with GPU acceleration!")
    except Exception as e:
        print(f"Error loading Llama model: {e}")
        print(traceback.format_exc())
        exit(1)
else:
    print(f"Error loading Llama model")

def format_response(text):
    # Ensure code blocks are preserved.
    # First, identify and extract code blocks with triple backticks.
    code_blocks = []
    in_code_block = False
    code_block_content = ""
    code_block_language = ""
    
    lines = text.split('\n')
    clean_lines = []
    
    for i, line in enumerate(lines):
        # Check for code block start/end.
        if line.strip().startswith('```'):
            if not in_code_block:
                # Start of code block
                in_code_block = True
                code_block_content = ""
                code_block_language = line.strip()[3:].strip() # Extract language if specified.
                continue
            else:
                # End of code block
                in_code_block = False
                code_blocks.append((code_block_language, code_block_content, i))  # Track the end index.
                clean_lines.append(f"[CODE_BLOCK_START_{len(code_blocks)-1}]")
                clean_lines.append(f"[CODE_BLOCK_END_{len(code_blocks)-1}]")
                continue
        
        if in_code_block:
            code_block_content += line + "\n"
        else:
            clean_lines.append(line)

    # Process the text without code blocks.
    text = "\n".join(clean_lines)
    
    # Remove any unwanted Llama format tokens from the regular text (not code blocks)
    unwanted_tokens = ["<|assistant|>", "<|/assistant|>", "<|user|>", "<|/user|>", "<|system|>", "<|/system|>"]
    for token in unwanted_tokens:
        text = text.replace(token, "")
    
    # Replace various bullet styles with a unified bullet style.
    text = text.replace('- ', '• ').replace('* ', '• ')
    
    # Split text into lines, and then process it.
    lines = text.split('\n')
    formatted = []
    last_was_bullet = False
    in_bullet_list = False
    last_was_empty = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        is_bullet = line.startswith('• ')
        is_empty = len(line) == 0
        
        # Handle bullet points.
        if is_bullet:
            if not in_bullet_list:
                # Add blank lines before the first bullet in a list.
                formatted.append('')
                formatted.append('')
                in_bullet_list = True
            formatted.append(line) # Add a bullet point.
            last_was_bullet = True
            last_was_empty = False
        # Handle paragraph transitions.
        elif not is_empty and i > 0 and not last_was_empty and not last_was_bullet:
            # This is a new paragraph (not after a bullet or empty line).
            # Add a double line break before a new paragraph.
            formatted.append('')
            formatted.append('')
            formatted.append(line)
            last_was_bullet = False
            last_was_empty = False
            in_bullet_list = False
        # Handle the end of a bulleted list.
        elif last_was_bullet and not is_empty:
            # Transition from bullets to text.
            formatted.append('')
            formatted.append('')
            formatted.append(line)
            last_was_bullet = False
            last_was_empty = False
            in_bullet_list = False
        # Handle regular content.
        elif not is_empty:
            formatted.append(line)
            last_was_bullet = False
            last_was_empty = False
        # Track empty lines.
        else:
            last_was_empty = True
            # Only add one empty line to avoid excessive spacing.
            if not (i > 0 and not formatted[-1]):
                formatted.append('')
    
    result = '\n'.join(formatted)
    
    # Ensure each bullet starts on a new line.
    result = result.replace(' • ', '\n• ')
    
    # Clean up any instances of more than two consecutive newlines.
    while '\n\n\n' in result:
        result = result.replace('\n\n\n', '\n\n')
    
    # Reinsert code blocks back into the text.
    for i, (language, content) in enumerate(code_blocks):
        marker = f"[CODE_BLOCK_{i}]"
        lang_str = language if language else ""
        formatted_block = f"\n```{lang_str}\n{content}```\n"
        result = result.replace(marker, formatted_block)
    
    return result

def kill_existing_signal_cli():
    print("Stopping any existing Signal CLI services...")
    for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and "signal-cli" in cmdline:
                print(f"Terminating existing signal-cli process: PID {proc.info['pid']}")
                os.kill(proc.info['pid'], signal.SIGKILL)
                time.sleep(3)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(2)

def start_signal_cli_jsonrpc():
    proc = subprocess.Popen(
        ["signal-cli", "-u", SIGNAL_NUMBER, "jsonRpc"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return proc

def split_message(message, max_length=500):
    if len(message) <= max_length:
        return [message]
    
    parts = []
    current_part = ""
    
    # Split on paragraphs first to preserve structure.
    paragraphs = message.split('\n\n')
    
    for paragraph in paragraphs:
        # If adding this paragraph exceeds max length and we already have content, then break it onto a new paragraph.
        if current_part and len(current_part) + len(paragraph) + 2 > max_length:
            parts.append(current_part)
            current_part = paragraph
        elif current_part:
            current_part += '\n\n' + paragraph
        else:
            current_part = paragraph
    
    if current_part:
        parts.append(current_part)
    
    # Add part numbers to indicate responses length.
    return [f"{part}\n[{i+1}/{len(parts)}]" for i, part in enumerate(parts)]

def send_signal_message(to_number, message, proc, group_id=None):
    if not message.strip():
        print("Error: Empty message, not sending.")
        return
    
    try:
        # Split the message if needed.
        message_parts = split_message(message)
        
        for part in message_parts:
            json_request = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": {
                    "message": part
                },
                "id": int(time.time())
            }
            
            # Set the recipient differently based on whether this is a group message.
            if group_id:
                json_request["params"]["groupId"] = group_id
            else:
                json_request["params"]["recipient"] = [to_number]
            
            json_str = json.dumps(json_request) + "\n"
            proc.stdin.write(json_str)
            proc.stdin.flush()
            print(f"Sent message part {'to group ' + group_id if group_id else 'to ' + to_number} via JSON-RPC")
            if len(message_parts) > 1:
                time.sleep(3)
    except Exception as e:
        print(f"Failed to send message via JSON-RPC: {e}")

def format_conversation_history(history):
    formatted = []
    for entry in history:
        formatted.extend([
            {"role": "user", "content": entry['query']},
            {"role": "assistant", "content": entry['response']}
        ])
    return formatted

def ask_llama(question, conversation_id=None):
    """Query the Llama model with the provided question and conversation history."""
    # Start timing the response.
    start_time = time.time()
    
    messages = []
    
    # Include the conversation history if available.
    if conversation_id:
        history = get_recent_conversation_history(conversation_id)
        if history:
            # Format the history into a conversation format Llama can understand.
            for entry in history:
                messages.append({"role": "user", "content": entry['query']})
                messages.append({"role": "assistant", "content": entry['response']})
    
    # Add the current question.
    messages.append({"role": "user", "content": question})
    
    # Create a prompt with the system prompt and the conversation history.
    prompt = f"<|system|>\n{SYSTEM_PROMPT}\n<|/system|>\n\n"
    
    # Add the conversation history.
    for msg in messages:
        if msg["role"] == "user":
            prompt += f"<|user|>\n{msg['content']}\n<|/user|>\n\n"
        else:
            prompt += f"<|assistant|>\n{msg['content']}\n<|/assistant|>\n\n"
    
    # Add the final user message if it's not already included.
    if not messages or messages[-1]["role"] != "user":
        prompt += f"<|user|>\n{question}\n<|/user|>\n\n"
    
    # Request a completion from the assistant.
    prompt += "<|assistant|>\n"
    
    # Generate a response from Llama.
    completion = llama_model.create_completion(
        prompt=prompt,
        max_tokens=MODEL_CONFIG.get('max_tokens'),
        temperature=MODEL_CONFIG.get('temperature'),
        stop=["<|user|>", "<|system|>", "<|/assistant|>"]
    )
    
    # Calculate the response time.
    end_time = time.time()
    response_time = end_time - start_time
    print(f"Response time: {response_time:.2f} seconds")
    
    # Extract the model information.
    model_name = get_model_name_from_path()
    model_provider = "Meta"
    
    # Create a response object with both the text response and model information.
    class ResponseWithModelInfo:
        def __init__(self, text, model_provider, model_name, model_response_time):
            self.text = text
            self.model_provider = model_provider
            self.model_name = model_name
            self.model_response_time = model_response_time
            
        def __str__(self):
            return self.text
    
    # Extract and format the response.
    response_text = completion["choices"][0]["text"]
    formatted_response = format_response(response_text)
    
    # Create and return the response object.
    result = ResponseWithModelInfo(
        formatted_response,
        model_provider,
        model_name,
        response_time
    )
    
    return result

def check_user_message_limit(sender):
    """
    Check if a user has reached their daily message limit.
    Returns (has_reached_limit, messages_used, messages_limit).
    """
    # If usage limits are disabled, always return False.
    if not USAGE_LIMITS_ENABLED:
        return False, 0, 0
        
    # Use the default message limit for all users.
    user_limit = DEFAULT_DAILY_MESSAGE_LIMIT
    
    # If unlimited messages (limit=0), return False.
    if user_limit == 0:
        return False, 0, 0
        
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get the timestamp of the first message today for this user.
                cur.execute("""
                    SELECT MIN(timestamp) as first_message
                    FROM query_log
                    WHERE sender = %s
                    AND timestamp::date = CURRENT_DATE
                """, (sender,))
                result = cur.fetchone()
                
                # If there are no messages today, the user is under the limit.
                if not result or not result['first_message']:
                    return False, 0, user_limit
                
                # Get the start of the 24-hour period (from their first message today).
                start_time = result['first_message']
                
                # Count messages in the 24-hour period since their first message today.
                cur.execute("""
                    SELECT COUNT(*) as message_count
                    FROM query_log
                    WHERE sender = %s
                    AND timestamp >= %s
                    AND timestamp < %s + INTERVAL '24 hours'
                """, (sender, start_time, start_time))
                count_result = cur.fetchone()
                
                message_count = count_result['message_count'] if count_result else 0
                
                # Check if the user has reached their limit.
                # Use >= to check if they've reached their limit with previous messages.
                # The current message will be allowed if they haven't yet reached the limit.
                has_reached_limit = message_count >= user_limit
                
                return has_reached_limit, message_count, user_limit
                
    except Exception as e:
        print(f"Error checking message limit for {sender}: {e}")
        import traceback
        traceback.print_exc()
        # If there's an error, default to not limiting.
        return False, 0, 0

def format_limit_message(messages_used, messages_limit):
    """Format a friendly message about the user's limit status by using configurable templates."""
    # Add 1 to messages_used to account for the current message being processed.
    # This gives the user an accurate count that includes their current message.
    adjusted_messages_used = messages_used + 1
    messages_remaining = messages_limit - adjusted_messages_used
    
    if messages_remaining < 0:
        # The user has reached or exceeded their limit.
        return LIMIT_REACHED_MESSAGE.format(limit=messages_limit)
    elif messages_remaining <= LIMIT_WARNING_THRESHOLD:
        # The user is approaching their limit.
        return LIMIT_WARNING_MESSAGE.format(
            used=adjusted_messages_used,
            limit=messages_limit,
            remaining=messages_remaining
        )
    else:
        return None # No need for a warning message.

def listen_for_messages(proc):
    while True:
        line = proc.stdout.readline()
        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("jsonrpc") == "2.0" and data.get("method") == "receive":
            params = data.get("params", {})
            envelope = params.get("envelope", {})
            source = envelope.get("source")
            
            # Extract the sender's name if available.
            sender_name = None
            if "sourceName" in envelope:
                sender_name = envelope.get("sourceName")
            
            message_data = envelope.get("dataMessage", {})
            message_text = message_data.get("message")
            
            # Check if the message is in a group chat.
            is_group = False
            group_id = None
            if "groupInfo" in message_data:
                is_group = True
                group_id = message_data["groupInfo"].get("groupId")
            
            # Check for mentions in the message metadata.
            mentions = message_data.get("mentions", [])
            is_mentioned = False
            for mention in mentions:
                if mention.get("number") == SIGNAL_NUMBER:
                    is_mentioned = True
                    print(f"Bot was officially mentioned in metadata: {mention}")
                    break
            
            if source and message_text:
                yield source, message_text, is_group, group_id, is_mentioned, sender_name

def check_for_mention(message):
    """Check if the assistant was mentioned in the message"""
    # Print debug information to help diagnose the issue.
    print(f"Checking for mention in message: {message}")
    print(f"Raw message bytes: {repr(message.encode())}")
    print(f"Looking for mentions of nickname: {AI_ASSISTANT_NICKNAME}")
    
    # Look for various encodings of the @ symbol that Signal might use.
    replacements = {
        '￼': '@',
        '\ufffc': '@', # Another possible replacement character
        '\xef\xbf\xbc': '@', # UTF-8 bytes for the object replacement character
        '\uFEFF': '@', # Zero-width, no-break space
        '﹫': '@', # Alternative @ symbol (U+FE6B)
    }
    
    processed_message = message
    for char, replacement in replacements.items():
        processed_message = processed_message.replace(char, replacement)
    
    print(f"Processed message after replacement: {processed_message}")
    
    # Create patterns to match potential @mentions with the AI's nickname.
    # Escape potential regex special characters in the name.
    nickname = re.escape(AI_ASSISTANT_NICKNAME)
    
    # Define multiple patterns to catch different ways the assistant might be mentioned
    patterns = [
        rf'@{nickname}',                      # @Nickname
        rf'@\s*{nickname}',                   # @ Nickname (with space)
        # rf'{nickname}',                       # Just the nickname (might have false positives, so this is currently disabled)
    ]
    
    # Check each pattern.
    for pattern in patterns:
        match = re.search(pattern, processed_message, re.IGNORECASE)
        if match:
            print(f"Found mention match with pattern: {pattern}")
            print(f"Match object: {match.group(0)}")
            return True
            
    # Try again with the raw message as a fallback.
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            print(f"Found mention match in raw message with pattern: {pattern}")
            print(f"Match object: {match.group(0)}")
            return True
    
    # If no patterns matched, print the following message.
    print("No mention patterns matched")
    return False

def remove_mention(message):
    """Remove the mention from the message to avoid confusing the AI"""
    nickname = re.escape(AI_ASSISTANT_NICKNAME)
    
    # Look for various encodings of the @ symbol that Signal might use.
    replacements = {
        '￼': '@',
        '\ufffc': '@', 
        '\xef\xbf\xbc': '@',
        '\uFEFF': '@',
        '﹫': '@',
    }
    
    processed_message = message
    for char, replacement in replacements.items():
        processed_message = processed_message.replace(char, replacement)
    
    patterns = [
        rf'@{nickname}',
        rf'@\s*{nickname}',
    ]
    
    result = processed_message
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Clean up extra whitespace.
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result

def send_notification(message, proc, notify_to=None):
    """Send notification messages to specified numbers or a default list."""
    # If no recipients specified, check for a notification list in the configuration file.
    try:
        # Determine the recipients for the notification.
        if notify_to:
            # Use explicitly provided recipients.
            recipients = notify_to
        elif NOTIFICATION_RECIPIENTS == "active_chats":
            # Get a list of all users who have active conversations with the assistant.
            recipients = get_active_chat_participants()
        else:
            # Use the configured list of notification recipients.
            recipients = NOTIFICATION_RECIPIENTS
        
        # Ensure recipients is a list.
        if not isinstance(recipients, list):
            recipients = [recipients]
        
        # Remove duplicates.
        recipients = list(set(recipients))
        
        for recipient in recipients:
            try:
                send_signal_message(recipient, message, proc)
                print(f"Notification sent to {recipient}: {message}")
            except Exception as e:
                print(f"Failed to send notification to {recipient}: {e}")
    except Exception as e:
        print(f"Error in send_notification: {e}")

def format_mentions_for_db(message):
    """Format message to replace replacement characters with proper @ symbol for database storage"""
    # Look for various encodings of the @ symbol that Signal might use.
    replacements = {
        '￼': '@',
        '\ufffc': '@', 
        '\xef\xbf\xbc': '@',
        '\uFEFF': '@', 
        '﹫': '@',
    }
    
    processed_message = message
    for char, replacement in replacements.items():
        processed_message = processed_message.replace(char, replacement)
    
    # Ensure the AI_ASSISTANT_NICKNAME is properly captured in mentions.
    nickname = AI_ASSISTANT_NICKNAME
    
    # Look for partial mentions that might be missing the nickname.
    partial_mention_pattern = r'@\s*(?!' + re.escape(nickname) + r')'
    if re.search(partial_mention_pattern, processed_message):
        # If there's an @ without the nickname, make sure to add it.
        processed_message = re.sub(partial_mention_pattern, '@' + nickname + ' ', processed_message)
    
    return processed_message

def get_active_chat_participants():
    """Get a list of all user phone numbers who have active conversations with the assistant."""
    participants = []
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Query for unique phone numbers that have sent messages within the configured active period.
                cur.execute("""
                    SELECT DISTINCT sender
                    FROM query_log
                    WHERE timestamp > NOW() - INTERVAL %s
                    AND sender IS NOT NULL
                    AND sender != %s
                """, (f"{ACTIVE_CHAT_PERIOD_DAYS} days", SIGNAL_NUMBER,))
                
                results = cur.fetchall()
                for result in results:
                    if result['sender'] and isinstance(result['sender'], str) and result['sender'].startswith('+'):
                        participants.append(result['sender'])
                
                print(f"Found {len(participants)} active chat participants for notifications")
        return participants
    except Exception as e:
        print(f"Error getting active chat participants: {e}")
        import traceback
        traceback.print_exc()
        # If the list can't be retrieved, return just the assistant's number as a fallback.
        return [SIGNAL_NUMBER]

def get_active_chat_groups():
    """Get a list of all group IDs where the assistant has been active in the last 8 days"""
    groups = []
    try:
        # First check the data type of is_group.
        column_type = get_group_column_type()
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Query for unique group IDs within the configured active period. Then, adapt the query based on the column type.
                if column_type and 'text' in column_type.lower():
                    # For text data type, compare it with the 't' or 'true' string.
                    cur.execute("""
                        SELECT DISTINCT group_id
                        FROM query_log
                        WHERE timestamp > NOW() - INTERVAL %s
                        AND (is_group = 't' OR is_group = 'true')
                        AND group_id IS NOT NULL
                    """, (f"{ACTIVE_CHAT_PERIOD_DAYS} days",))
                else:
                    # Otherwise, check for the boolean data type or an unknown data type.
                    cur.execute("""
                        SELECT DISTINCT group_id
                        FROM query_log
                        WHERE timestamp > NOW() - INTERVAL %s
                        AND CAST(is_group AS BOOLEAN) = TRUE
                        AND group_id IS NOT NULL
                    """, (f"{ACTIVE_CHAT_PERIOD_DAYS} days",))
                
                results = cur.fetchall()
                for result in results:
                    if result['group_id']:
                        groups.append(result['group_id'])
                
                print(f"Found {len(groups)} active group chats for notifications.")
        return groups
    except Exception as e:
        print(f"Error getting active group chats: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_group_column_type():
    """Check the data type of the is_group column in the query_log table."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'query_log' 
                    AND column_name = 'is_group'
                """)
                result = cur.fetchone()
                if result:
                    print(f"is_group column type: {result[1]}")
                    return result[1]
                else:
                    print("is_group column not found")
                    return None
    except Exception as e:
        print(f"Error checking is_group column type: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    kill_existing_signal_cli()
    proc = start_signal_cli_jsonrpc()
    print("Listening for incoming messages...") # Send a startup notification.
    startup_message = f"🟢 {AI_ASSISTANT_NICKNAME} is online and ready to respond."
    try:
        # Send to individual users.
        recipients = []
        if NOTIFICATION_RECIPIENTS == "active_chats":
            recipients = get_active_chat_participants()
        elif isinstance(NOTIFICATION_RECIPIENTS, list):
            recipients = NOTIFICATION_RECIPIENTS
        else:
            recipients = [NOTIFICATION_RECIPIENTS]
        
        # Remove duplicates.
        recipients = list(set(recipients))
        
        # Send message to each recipient.
        for recipient in recipients:
            try:
                send_signal_message(recipient, startup_message, proc)
                print(f"Sent startup notification to {recipient}")
                time.sleep(2) # Add a brief delay between messages.
            except Exception as e:
                print(f"Failed to send startup notification to {recipient}: {e}")
        
        # Also send to active group chats if configured to use active_chats.
        if NOTIFICATION_RECIPIENTS == "active_chats":
            group_ids = get_active_chat_groups()
            for group_id in group_ids:
                try:
                    send_signal_message(SIGNAL_NUMBER, startup_message, proc, group_id)
                    print(f"Sent startup notification to group {group_id}")
                    time.sleep(5) # Add a brief delay between messages.
                except Exception as e:
                    print(f"Failed to send startup notification to group {group_id}: {e}")
    except Exception as e:
        print(f"Error sending startup notifications: {e}")
        import traceback
        traceback.print_exc()
      # Register the cleanup function to send notification on shutdown.
    def cleanup_handler():
        try:
            print("Assistant shutting down. Sending notification...")
            shutdown_message = f"📴 {AI_ASSISTANT_NICKNAME} is offline and will respond when online."
            
            # Start a new signal-cli process specifically for sending shutdown notifications.
            # This ensures notifications get sent even if the main process is terminating.
            try:
                shutdown_proc = start_signal_cli_jsonrpc()
                print("Started separate signal-cli process for shutdown notifications")
                
                # Get recipients based on configuration.
                recipients = []
                if NOTIFICATION_RECIPIENTS == "active_chats":
                    recipients = get_active_chat_participants()
                elif isinstance(NOTIFICATION_RECIPIENTS, list):
                    recipients = NOTIFICATION_RECIPIENTS
                else:
                    recipients = [NOTIFICATION_RECIPIENTS]
                
                # Remove duplicates.
                recipients = list(set(recipients))
                
                # Send a notification to each recipient.
                for recipient in recipients:
                    try:
                        send_signal_message(recipient, shutdown_message, shutdown_proc)
                        print(f"Sent shutdown notification to {recipient}")
                        time.sleep(2) # Add a brief delay between messages.
                    except Exception as e:
                        print(f"Failed to send shutdown notification to {recipient}: {e}")
                
                # Also send to active group chats if configured to use active_chats.
                if NOTIFICATION_RECIPIENTS == "active_chats":
                    group_ids = get_active_chat_groups()
                    for group_id in group_ids:
                        try:
                            send_signal_message(SIGNAL_NUMBER, shutdown_message, shutdown_proc, group_id)
                            print(f"Sent shutdown notification to group {group_id}")
                            time.sleep(5) # Add a brief delay between messages.
                        except Exception as e:
                            print(f"Failed to send shutdown notification to group {group_id}: {e}")
                
                # Allow time for notifications to be sent.
                time.sleep(10)
                
                # Properly terminate the shutdown notification process.
                shutdown_proc.terminate()
                shutdown_proc.wait(timeout=2)
                
            except Exception as e:
                print(f"Error with shutdown notification process: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            print(f"Error during shutdown notification: {e}")
            import traceback
            traceback.print_exc()

    # Register the cleanup function to run when the script exits.
    atexit.register(cleanup_handler)

    # Store conversation IDs.
    conversations = {}
    last_cache_clear = time.time()
    cache_clear_interval = 3600  # Clear location cache every hour.

    while True:
        if proc.poll() is not None:
            print("Detected that signal-cli has stopped. Restarting...")
            proc = start_signal_cli_jsonrpc()
            time.sleep(3) # Add a small wait time to ensure signal-cli is ready.

        # Periodically clear the location cache to ensure fresh lookups.
        current_time = time.time()
        if current_time - last_cache_clear > cache_clear_interval:
            clear_location_cache()
            last_cache_clear = current_time
            print("Location cache cleared due to scheduled refresh.")

        try:
            for sender, message, is_group, group_id, is_mentioned, sender_name in listen_for_messages(proc):
                print(f"Received from {sender}: {message}")
                
                # Try to extract location from phone number if it starts with a +.
                country = city = possible_carrier = location = None
                if sender and isinstance(sender, str) and sender.startswith('+'):
                    # Force a refresh on each message to ensure that the latest data is available.
                    location_info = get_location_from_phone_number(sender, force_refresh=True)
                    if location_info:
                        country = location_info.get('country')
                        city = location_info.get('city')
                        possible_carrier = location_info.get('possible_carrier')
                        location = location_info.get('location')
                        print(f"Extracted location from phone number: {country}, {city}, {possible_carrier}, {location}")
                
                # Only respond if it's a direct message OR if it's a group message that mentions the assistant.
                # First check official mentions from the metadata, then fall back to text-based detection.
                should_respond = not is_group or (is_group and (is_mentioned or check_for_mention(message)))

                if should_respond:
                    # Apply limits to both direct messages and group chats.
                    has_reached_limit, messages_used, messages_limit = check_user_message_limit(sender)
                    if has_reached_limit:
                        limit_message = format_limit_message(messages_used, messages_limit)
                        print(f"User {sender} has reached their limit: {messages_used}/{messages_limit}")
                        
                        # Send the limit message to the appropriate destination.
                        if is_group and group_id:
                            # For group messages, respond in the group chat.
                            send_signal_message(SIGNAL_NUMBER, limit_message, proc, group_id)
                        else:
                            # For direct messages, respond directly to the sender.
                            send_signal_message(sender, limit_message, proc)
                        continue

                    # Store the warning message for later if the user is approaching their limit.
                    warn_message = None
                    if messages_limit > 0:  # If there is a limit (not unlimited)
                        # Check if the user needs to be warned about approaching limits.
                        warn_message = format_limit_message(messages_used, messages_limit)
                        if warn_message:
                            print(f"User {sender} approaching limit: {messages_used}/{messages_limit}")

                    # Create or get conversation ID for this sender or group.
                    convo_key = group_id if is_group and group_id else sender
                    if convo_key not in conversations:
                        conversations[convo_key] = str(uuid.uuid4())
                    # Remove the mention from the message if it's a group message.
                    processed_message = remove_mention(message) if is_group else message
                    
                    try:
                        # Call the appropriate Llama model based on the configuration.
                        if USE_LLAMA:
                            response_object = ask_llama(processed_message, conversations[convo_key])
                            
                            if isinstance(response_object, str):
                                answer = response_object
                                # No model info available if it's just a string.
                                model_provider = "Meta"
                                model_name = get_model_name_from_path()
                                model_response_time = None
                            else:
                                # Extract both the answer text and the model info.
                                answer = response_object.text if hasattr(response_object, 'text') else str(response_object)
                                
                                # Get the model information.
                                if hasattr(response_object, 'model_name'):
                                    model_provider = response_object.model_provider
                                    model_name = response_object.model_name
                                    model_response_time = response_object.model_response_time
                                    print(f"Response has model_response_time: {model_response_time}")
                                else:
                                    model_provider = "Meta"
                                    model_name = get_model_name_from_path()
                                    model_response_time = None
                                    
                            print(f"Llama's answer: {answer}")
                        else:
                            print(f"Error processing message with Llama model.")
                            answer = "Error processing your request with the Llama model."
                            model_provider = None
                            model_name = None
                            model_response_time = None
                        
                        # Log the conversation with all location data available.
                        formatted_message = format_mentions_for_db(message)
                        log_conversation(
                            sender, 
                            formatted_message, 
                            answer, 
                            conversations[convo_key], 
                            is_group, 
                            group_id, 
                            sender_name,
                            country,
                            city,
                            possible_carrier,
                            location,
                            model_provider,
                            model_name,
                            model_response_time
                        )
                        
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                if is_group and group_id:
                                    # For group messages, send to the group and mention the original sender.
                                    send_signal_message(sender, answer, proc, group_id)
                                    print(f"Successfully sent group message to group ID {group_id} with mention to {sender} (attempt {attempt + 1})")
                                else:
                                    # For direct messages, use the sender's number.
                                    send_signal_message(sender, answer, proc)
                                    print(f"Successfully sent direct message to {sender} (attempt {attempt + 1})")
                                
                                # After successfully sending the response, send the warning message if needed.
                                if warn_message:
                                    time.sleep(1) # Add a brief delay between messages.
                                    print("Sending limit warning message after response")
                                    if is_group and group_id:
                                        # For group messages, respond in the group chat.
                                        send_signal_message(SIGNAL_NUMBER, warn_message, proc, group_id)
                                    else:
                                        # For direct messages, respond directly to the sender.
                                        send_signal_message(sender, warn_message, proc)
                                
                                # Break the retry loop after successful sending.
                                break
                            except Exception as send_error:
                                print(f"Failed to send message (attempt {attempt + 1}): {send_error}")
                                if attempt == max_retries - 1:
                                    print("Maximum retries reached, message may not have been sent")
                                time.sleep(2)
                    except Exception as e:
                        print(f"Error getting AI response: {e}")
                        answer = "Sorry, there was an error processing your request."
                        if is_group and group_id:
                            send_signal_message(sender, answer, proc, group_id)
                        else:
                            send_signal_message(sender, answer, proc)
                        time.sleep(1)
                else:
                    print("Message not addressed to assistant, ignoring.")

        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(5)
            kill_existing_signal_cli()
            proc = start_signal_cli_jsonrpc()
            time.sleep(2)

if __name__ == "__main__":
    main()
