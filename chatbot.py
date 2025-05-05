# This script is designed to run indefinitely, listening for incoming messages and responding as needed.
import subprocess
import json
import time
import os
import signal
import psutil
import anthropic
import uuid
import re
from config import ANTHROPIC_API_KEY, SIGNAL_NUMBER, SYSTEM_PROMPT, AI_ASSISTANT_NICKNAME
from db_utils import log_conversation, get_recent_conversation_history
from location_utils import get_location_from_phone_number, clear_location_cache

# Set an environment variable to enable IP-based location fallback.
os.environ['ALLOW_IP_FALLBACK'] = 'true'

# Connect to Claude.
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def format_response(text):
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
    
    return result

def kill_existing_signal_cli():
    print("Stopping any existing Signal CLI services...")
    for proc in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and "signal-cli" in cmdline:
                print(f"Terminating existing signal-cli process: PID {proc.info['pid']}")
                os.kill(proc.info['pid'], signal.SIGKILL)
                time.sleep(2)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(1)

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
            print(f"Sent message part {' to group ' + group_id if group_id else ' to ' + to_number} via JSON-RPC")
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

def ask_claude(question, conversation_id=None):
    messages = [{"role": "user", "content": question}]
    
    if conversation_id:
        history = get_recent_conversation_history(conversation_id)
        if history:
            messages = format_conversation_history(history) + messages
    
    response = claude.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    return format_response(response.content[0].text)

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

def main():
    kill_existing_signal_cli()
    proc = start_signal_cli_jsonrpc()
    print("Listening for incoming messages...")

    # Store conversation IDs.
    conversations = {}
    last_cache_clear = time.time()
    cache_clear_interval = 3600  # Clear location cache every hour.

    while True:
        if proc.poll() is not None:
            print("Detected that signal-cli has stopped. Restarting...")
            proc = start_signal_cli_jsonrpc()
            time.sleep(2) # Add a small wait time to ensure signal-cli is ready.

        # Periodically clear the location cache to ensure fresh lookups.
        current_time = time.time()
        if current_time - last_cache_clear > cache_clear_interval:
            clear_location_cache()
            last_cache_clear = current_time
            print("Location cache cleared due to scheduled refresh")

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
                    # Create or get conversation ID for this sender or group.
                    convo_key = group_id if is_group and group_id else sender
                    if convo_key not in conversations:
                        conversations[convo_key] = str(uuid.uuid4())

                    # Remove the mention from the message if it's a group message.
                    processed_message = remove_mention(message) if is_group else message
                    
                    try:
                        answer = ask_claude(processed_message, conversations[convo_key])
                        print(f"Claude's answer: {answer}")
                        
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
                            location
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
                                break
                            except Exception as send_error:
                                print(f"Failed to send message (attempt {attempt + 1}): {send_error}")
                                if attempt == max_retries - 1:
                                    print("Maximum retries reached, message may not have been sent")
                                time.sleep(2)
                    except Exception as e:
                        print(f"Error getting Claude's response: {e}")
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
