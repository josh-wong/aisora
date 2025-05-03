import subprocess
import json
import time
import os
import signal
import psutil
import anthropic
import uuid
from config import ANTHROPIC_API_KEY, SIGNAL_NUMBER, SYSTEM_PROMPT
from db_utils import log_conversation, get_recent_conversation_history

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

def send_signal_message(to_number, message, proc):
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
                    "recipient": [to_number],
                    "message": part
                },
                "id": int(time.time())
            }
            json_str = json.dumps(json_request) + "\n"
            proc.stdin.write(json_str)
            proc.stdin.flush()
            print(f"Sent message part to {to_number} via JSON-RPC")
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
            message_data = envelope.get("dataMessage", {})
            message_text = message_data.get("message")
            
            # Check if the message is in a group chat.
            is_group = False
            group_id = None
            if "groupInfo" in message_data:
                is_group = True
                group_id = message_data["groupInfo"].get("groupId")

            if source and message_text:
                yield source, message_text, is_group, group_id

def main():
    kill_existing_signal_cli()
    proc = start_signal_cli_jsonrpc()
    print("Listening for incoming messages...")

    # Store conversation IDs.
    conversations = {}

    while True:
        if proc.poll() is not None:
            print("Detected that signal-cli has stopped. Restarting...")
            proc = start_signal_cli_jsonrpc()
            time.sleep(2) # Add a small wait time to ensure signal-cli is ready.

        try:
            for sender, message, is_group, group_id in listen_for_messages(proc):
                print(f"Received from {sender}: {message}")

                # Get or create conversation ID for this sender.
                if sender not in conversations:
                    conversations[sender] = str(uuid.uuid4())

                try:
                    answer = ask_claude(message, conversations[sender])
                    print(f"Claude's answer: {answer}")
                    
                    # Log the conversation.
                    log_conversation(sender, message, answer, conversations[sender], is_group, group_id)
                    
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            send_signal_message(sender, answer, proc)
                            print(f"Successfully sent message to {sender} (attempt {attempt + 1})")
                            break
                        except Exception as send_error:
                            print(f"Failed to send message (attempt {attempt + 1}): {send_error}")
                            if attempt == max_retries - 1:
                                print("Maximum retries reached, message may not have been sent")
                            time.sleep(2)
                except Exception as e:
                        print(f"Error getting Claude's response: {e}")
                        answer = "Sorry, there was an error processing your request."
                        send_signal_message(sender, answer, proc)
                        time.sleep(1)

        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(5)
            kill_existing_signal_cli()
            proc = start_signal_cli_jsonrpc()
            time.sleep(2)

if __name__ == "__main__":
    main()
